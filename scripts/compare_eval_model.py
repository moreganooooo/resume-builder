"""Benchmark evaluator models under the real fit-evaluation code path.

Unlike the old one-model spot check, this harness treats the current evaluator
as a noisy control rather than ground truth. Each selected JD is evaluated by
all candidates and repeated on the control model. The run uses ResumeEngine's
real profile context, prompts, schemas, deterministic commute/stress/stretch
logic, and final scoring math. Each JD is copied into a temporary sandbox and
all known persistence exits are blocked, so the real source file and DB remain
outside the experiment.

Usage:
    RESUME_PROFILE=morgan python scripts/compare_eval_model.py --limit 5
    RESUME_PROFILE=morgan python scripts/compare_eval_model.py \
        --models gemini:gemini-3.1-flash-lite \
          nvidia:google/gemma-4-31b-it \
          nvidia:nvidia/nemotron-3.5-lightning-30b-a3b \
          nvidia:openai/gpt-oss-20b \
        --control-runs 2 --output /tmp/eval-model-benchmark.json

The JSON report is checkpointed after every attempt and contains raw final
results, failures, latency, model metadata, and aggregate deltas. It is the
experiment artifact; stdout is only a progress view.
"""

from __future__ import annotations

import argparse
import contextlib
import hashlib
import json
import math
import os
import shutil
import statistics
import sys
import tempfile
import time
from datetime import datetime, timezone
from typing import Any

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import profile_paths
from dotenv import load_dotenv

load_dotenv(profile_paths.env_path(), override=True)

import jd_manager  # noqa: E402
import orchestrator  # noqa: E402
from nvidia_client import NvidiaNimClient  # noqa: E402

DEFAULT_CANDIDATES = (
    "gemini:gemini-3.1-flash-lite",
    "nvidia:google/gemma-4-31b-it",
    "nvidia:nvidia/nemotron-3.5-lightning-30b-a3b",
    "nvidia:openai/gpt-oss-20b",
)
DEFAULT_JDS = (
    "jds/morgan/2026-09-13_Allego_SeniorCustomerMarketingCommunityManager.json",
    "jds/morgan/2026-09-13_Block_B2BMarketingManagerContentSocial.json",
    "jds/morgan/2026-09-13_Directive_PRCommunicationsManagerRemoteUSDirective.json",
    "jds/morgan/2026-09-13_ComputerTaskGroup_MarketingManagerI.json",
    "jds/morgan/2026-09-13_Dropbox_ProgramManagerCustomersRemoteUS.json",
)
NUMERIC_METRICS = (
    "composite_score",
    "fit_score",
    "interview_odds_score",
    "practical_pursue_score",
    "level_plausibility",
    "domain_fit",
    "skills_overlap",
    "evidence_strength",
    "funnel_friction",
    "remote_quality",
)
CATEGORICAL_METRICS = ("recommendation", "role_track")


def _sha256(path: str) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _short_name(path: str) -> str:
    base = os.path.basename(path).removesuffix(".json")
    parts = base.split("_")
    return f"{parts[1]} | {'_'.join(parts[2:])}"[:80] if len(parts) >= 3 else base


def _resolve_paths(paths: list[str], profile: str) -> list[str]:
    selected = paths or list(DEFAULT_JDS)
    resolved = []
    for value in selected:
        candidates = [value]
        if not os.path.isabs(value):
            candidates.extend(
                [
                    os.path.join(profile_paths.PROJECT_ROOT, value),
                    os.path.join(profile_paths.jds_dir(profile), value),
                    os.path.join(
                        profile_paths.jds_dir(profile), os.path.basename(value)
                    ),
                ]
            )
        found = next(
            (os.path.abspath(p) for p in candidates if os.path.isfile(p)), None
        )
        if found is None:
            raise FileNotFoundError(value)
        resolved.append(found)
    return resolved


def _clean(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(k): _clean(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_clean(v) for v in value]
    if isinstance(value, float) and (math.isnan(value) or math.isinf(value)):
        return None
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    return str(value)


def _atomic_json(path: str, payload: dict) -> None:
    path = os.path.abspath(path)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = f"{path}.tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(_clean(payload), fh, indent=2, sort_keys=True)
        fh.write("\n")
    os.replace(tmp, path)


@contextlib.contextmanager
def _patch_attribute(target, name: str, replacement):
    """Temporarily replace an attribute without importing unittest.

    Importing unittest.mock in this live benchmark caused the API clients'
    test-network guards to misclassify ordinary CLI runs as unit tests.
    """
    original = getattr(target, name)
    setattr(target, name, replacement)
    try:
        yield
    finally:
        setattr(target, name, original)


@contextlib.contextmanager
def _read_only_evaluator():
    """Disable model handoffs and turn every known persistence exit into a trap."""
    original_fallbacks = orchestrator.SCORING_FALLBACKS

    def _forbidden(*args, **kwargs):
        raise RuntimeError("benchmark blocked an attempted persistent write")

    orchestrator.SCORING_FALLBACKS = {}
    try:
        targets = [(jd_manager, "save_evaluation")]
        for name in ("save_json", "atomic_write_json", "update_job"):
            if hasattr(jd_manager, name):
                targets.append((jd_manager, name))
        with contextlib.ExitStack() as stack:
            for module, name in targets:
                stack.enter_context(_patch_attribute(module, name, _forbidden))
            yield
    finally:
        orchestrator.SCORING_FALLBACKS = original_fallbacks


def _split_candidate(candidate: str) -> tuple[str, str]:
    if ":" not in candidate:
        return "gemini", candidate
    provider, model = candidate.split(":", 1)
    if provider not in {"gemini", "nvidia"} or not model:
        raise ValueError(
            f"Invalid candidate {candidate!r}; use gemini:model or nvidia:publisher/model"
        )
    return provider, model


def _run_once(engine, path: str, candidate: str, stage_models: list[str]) -> dict:
    calls: list[dict] = []
    provider, model = _split_candidate(candidate)
    original_generate = orchestrator.GeminiClient.generate

    def _generate(*args, **kwargs):
        call = dict(kwargs)
        if args:
            positional = (
                "model",
                "system_instruction",
                "contents",
                "response_schema",
                "temperature",
            )
            call.update(dict(zip(positional, args)))
        stage = (
            "capability"
            if len(calls) == 0
            else "recruiter" if len(calls) == 1 else "extra"
        )
        requested = str(call.get("model", ""))
        selected_provider = "gemini"
        if stage in stage_models:
            call["model"] = model
            selected_provider = provider
        record = {
            "stage": stage,
            "requested_model": requested,
            "forced_provider": selected_provider,
            "forced_model": str(call.get("model", "")),
        }
        calls.append(record)
        started = time.monotonic()
        try:
            generate = (
                NvidiaNimClient.generate
                if selected_provider == "nvidia"
                else original_generate
            )
            text, meta = generate(**call)
        except Exception as exc:
            record.update(
                {
                    "elapsed_seconds": round(time.monotonic() - started, 3),
                    "error_type": type(exc).__name__,
                    "error": str(exc),
                    "response_present": False,
                }
            )
            raise
        record.update(
            {
                "elapsed_seconds": round(time.monotonic() - started, 3),
                "meta": _clean(meta),
                "response_present": bool(text),
            }
        )
        return text, meta

    source_hash = _sha256(path)
    started = time.monotonic()
    status = "error"
    result = None
    error: dict[str, str] = {}
    with tempfile.TemporaryDirectory(prefix="eval-model-benchmark-") as sandbox:
        sandbox_path = os.path.join(sandbox, os.path.basename(path))
        shutil.copy2(path, sandbox_path)
        try:
            with (
                _read_only_evaluator(),
                _patch_attribute(orchestrator.GeminiClient, "generate", _generate),
            ):
                result = engine.evaluate_fit(sandbox_path)
            status = "ok" if result is not None else "empty"
        except Exception as exc:  # noqa: BLE001 - failures are benchmark data
            error = {"error_type": type(exc).__name__, "error": str(exc)}
        sandbox_hash = _sha256(sandbox_path)

    if _sha256(path) != source_hash:
        raise RuntimeError("source JD changed despite sandboxing")
    payload = {
        "status": status,
        "elapsed_seconds": round(time.monotonic() - started, 3),
        "calls": calls,
        "evaluation": _clean(result),
        "source_sha256_after": source_hash,
        "sandbox_sha256_after": sandbox_hash,
        "sandbox_changed": sandbox_hash != source_hash,
    }
    payload.update(error)
    return payload


def _reference_by_jd(attempts: list[dict], control: str) -> dict[str, dict]:
    grouped: dict[str, list[dict]] = {}
    for attempt in attempts:
        if attempt["model"] == control and attempt["status"] == "ok":
            grouped.setdefault(attempt["jd_sha256"], []).append(attempt["evaluation"])
    refs = {}
    for jd_hash, rows in grouped.items():
        ref: dict[str, Any] = {}
        for metric in NUMERIC_METRICS:
            vals = [
                r.get(metric) for r in rows if isinstance(r.get(metric), (int, float))
            ]
            if vals:
                ref[metric] = statistics.median(vals)
        for metric in CATEGORICAL_METRICS:
            vals = [str(r.get(metric)) for r in rows if r.get(metric) is not None]
            if vals:
                ref[metric] = statistics.mode(vals)
        refs[jd_hash] = ref
    return refs


def _summarize(report: dict) -> dict:
    attempts = report["attempts"]
    references = _reference_by_jd(attempts, report["config"]["control_model"])
    summary: dict[str, dict] = {}
    for model in report["config"]["models"]:
        rows = [r for r in attempts if r["model"] == model]
        ok = [r for r in rows if r["status"] == "ok"]
        stats: dict[str, Any] = {
            "attempts": len(rows),
            "successes": len(ok),
            "success_rate": len(ok) / len(rows) if rows else None,
            "median_elapsed_seconds": (
                statistics.median(r["elapsed_seconds"] for r in ok) if ok else None
            ),
            "metrics": {},
        }
        for metric in NUMERIC_METRICS:
            deltas = []
            signed = []
            for row in ok:
                value = row["evaluation"].get(metric)
                reference = references.get(row["jd_sha256"], {}).get(metric)
                if isinstance(value, (int, float)) and isinstance(
                    reference, (int, float)
                ):
                    signed.append(value - reference)
                    deltas.append(abs(value - reference))
            if deltas:
                stats["metrics"][metric] = {
                    "mean_absolute_delta": statistics.fmean(deltas),
                    "median_absolute_delta": statistics.median(deltas),
                    "mean_signed_delta": statistics.fmean(signed),
                }
        for metric in CATEGORICAL_METRICS:
            comparable = 0
            matches = 0
            for row in ok:
                value = row["evaluation"].get(metric)
                reference = references.get(row["jd_sha256"], {}).get(metric)
                if value is not None and reference is not None:
                    comparable += 1
                    matches += value == reference
            if comparable:
                stats["metrics"][metric] = {
                    "agreement_rate": matches / comparable,
                    "comparable": comparable,
                }
        summary[model] = stats
    return summary


def _attempt_key(model: str, run: int, jd_hash: str) -> str:
    return f"{model}\0{run}\0{jd_hash}"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument(
        "paths", nargs="*", help="JD files; defaults to five varied stored JDs"
    )
    parser.add_argument("--profile", default=os.environ.get("RESUME_PROFILE"))
    parser.add_argument("--models", nargs="+", default=list(DEFAULT_CANDIDATES))
    parser.add_argument("--control-model", default=f"gemini:{orchestrator.EVAL_MODEL}")
    parser.add_argument("--control-runs", type=int, default=2)
    parser.add_argument("--candidate-runs", type=int, default=1)
    parser.add_argument(
        "--stage", choices=("both", "capability", "recruiter"), default="both"
    )
    parser.add_argument("--limit", type=int)
    parser.add_argument("--output", default="eval-model-benchmark.json")
    parser.add_argument(
        "--resume", action="store_true", help="Resume matching attempts from --output"
    )
    args = parser.parse_args(argv)

    if not args.profile:
        args.profile = profile_paths.active_profile()
    try:
        for candidate in [args.control_model, *args.models]:
            _split_candidate(candidate)
    except ValueError as exc:
        parser.error(str(exc))
    if args.control_model not in args.models:
        args.models.insert(0, args.control_model)
    if any(_split_candidate(item)[0] == "nvidia" for item in args.models):
        if not (os.environ.get("NVIDIA_API_KEY") or os.environ.get("NGC_API_KEY")):
            parser.error(
                "NVIDIA_API_KEY is required when --models includes nvidia:* candidates"
            )
    if args.control_runs < 1 or args.candidate_runs < 1:
        parser.error("run counts must be positive")
    profile_paths.set_active_profile(args.profile)
    paths = _resolve_paths(args.paths, args.profile)
    if args.limit:
        paths = paths[: args.limit]
    stage_models = ["capability", "recruiter"] if args.stage == "both" else [args.stage]

    report = {
        "schema_version": 2,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "config": {
            "profile": args.profile,
            "models": args.models,
            "control_model": args.control_model,
            "control_runs": args.control_runs,
            "candidate_runs": args.candidate_runs,
            "stage": args.stage,
            "candidate_syntax": "provider:model",
            "fallbacks_disabled": True,
            "persistence_blocked": True,
            "jd_sandboxed": True,
        },
        "jds": [
            {"path": path, "name": _short_name(path), "sha256": _sha256(path)}
            for path in paths
        ],
        "attempts": [],
        "summary": {},
    }
    if args.resume and os.path.isfile(args.output):
        with open(args.output, "r", encoding="utf-8") as fh:
            prior = json.load(fh)
        if prior.get("config") != report["config"] or prior.get("jds") != report["jds"]:
            parser.error("--resume report configuration or JD hashes do not match")
        report["attempts"] = prior.get("attempts", [])

    completed = {
        _attempt_key(r["model"], r["run"], r["jd_sha256"]) for r in report["attempts"]
    }
    engine = orchestrator.ResumeEngine()

    for jd in report["jds"]:
        for model in args.models:
            run_count = (
                args.control_runs
                if model == args.control_model
                else args.candidate_runs
            )
            for run in range(1, run_count + 1):
                key = _attempt_key(model, run, jd["sha256"])
                if key in completed:
                    continue
                print(f"{jd['name']} | {model} | run {run}/{run_count}", flush=True)
                provider, raw_model = _split_candidate(model)
                base = {
                    "jd_path": jd["path"],
                    "jd_name": jd["name"],
                    "jd_sha256": jd["sha256"],
                    "model": model,
                    "provider": provider,
                    "provider_model": raw_model,
                    "run": run,
                }
                base.update(_run_once(engine, jd["path"], model, stage_models))
                if base["status"] == "error":
                    print(
                        f"  ERROR: {base.get('error_type')}: {base.get('error')}",
                        flush=True,
                    )
                report["attempts"].append(base)
                report["summary"] = _summarize(report)
                _atomic_json(args.output, report)

    report["completed_at"] = datetime.now(timezone.utc).isoformat()
    report["summary"] = _summarize(report)
    _atomic_json(args.output, report)
    print(f"\nWrote {os.path.abspath(args.output)}")
    for model, stats in report["summary"].items():
        mad = stats["metrics"].get("composite_score", {}).get("mean_absolute_delta")
        print(
            f"  {model}: {stats['successes']}/{stats['attempts']} succeeded; "
            f"median {stats['median_elapsed_seconds']}; composite MAD {mad}"
        )
    print("No evaluation was persisted and every source JD hash was rechecked.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
