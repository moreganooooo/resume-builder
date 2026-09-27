"""Benchmark evaluator models under the real fit-evaluation code path.

Unlike the old one-model spot check, this harness treats the current evaluator
as a noisy control rather than ground truth.  Each selected JD is evaluated by
all candidates and repeated on the control model.  The run uses ResumeEngine's
real profile context, prompts, schemas, deterministic commute/stress/stretch
logic, and final scoring math, while intercepting persistence so no JD or DB
state can change.

Usage:
    RESUME_PROFILE=morgan python scripts/compare_eval_model.py --limit 5
    RESUME_PROFILE=morgan python scripts/compare_eval_model.py \
        --models gemini-3.1-flash-lite gemma-4-31b-it gemma-4-26b-a4b-it \
        --control-runs 2 --output /tmp/eval-model-benchmark.json

The JSON report is checkpointed after every attempt and contains raw final
results, failures, latency, model metadata, and aggregate deltas.  It is the
experiment artifact; stdout is only a progress view.
"""

from __future__ import annotations

import argparse
import contextlib
import copy
import hashlib
import json
import math
import os
import statistics
import sys
import time
from datetime import datetime, timezone
from typing import Any
from unittest.mock import patch

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import profile_paths
from dotenv import load_dotenv

load_dotenv(profile_paths.env_path(), override=True)

import jd_manager  # noqa: E402
import orchestrator  # noqa: E402

DEFAULT_CANDIDATES = (
    "gemini-3.1-flash-lite",
    "gemma-4-31b-it",
    "gemma-4-26b-a4b-it",
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
                    os.path.join(profile_paths.jds_dir(profile), os.path.basename(value)),
                ]
            )
        found = next((os.path.abspath(p) for p in candidates if os.path.isfile(p)), None)
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
def _read_only_evaluator(model: str):
    """Select one model and turn every known persistence exit into a trap."""
    original_eval_model = orchestrator.EVAL_MODEL
    original_fallbacks = orchestrator.SCORING_FALLBACKS

    def _forbidden(*args, **kwargs):
        raise RuntimeError("benchmark blocked an attempted persistent write")

    orchestrator.EVAL_MODEL = model
    orchestrator.SCORING_FALLBACKS = {}
    try:
        targets = [(jd_manager, "save_evaluation")]
        for name in ("save_json", "atomic_write_json", "update_job"):
            if hasattr(jd_manager, name):
                targets.append((jd_manager, name))
        with contextlib.ExitStack() as stack:
            for module, name in targets:
                stack.enter_context(patch.object(module, name, _forbidden))
            yield
    finally:
        orchestrator.EVAL_MODEL = original_eval_model
        orchestrator.SCORING_FALLBACKS = original_fallbacks


def _run_once(engine, path: str, model: str, stage_models: list[str]) -> dict:
    calls: list[dict] = []
    original_generate = orchestrator.GeminiClient.generate

    def _generate(*args, **kwargs):
        call = dict(kwargs)
        if args:
            call["model"] = args[0]
        stage = "capability" if len(calls) == 0 else "recruiter" if len(calls) == 1 else "extra"
        requested = str(call.get("model", ""))
        if stage in stage_models:
            call["model"] = model
        started = time.monotonic()
        text, meta = original_generate(**call)
        calls.append(
            {
                "stage": stage,
                "requested_model": requested,
                "forced_model": str(call.get("model", "")),
                "elapsed_seconds": round(time.monotonic() - started, 3),
                "meta": _clean(meta),
                "response_present": bool(text),
            }
        )
        return text, meta

    before_hash = _sha256(path)
    started = time.monotonic()
    with _read_only_evaluator(model), patch.object(
        orchestrator.GeminiClient, "generate", side_effect=_generate
    ):
        result = engine.evaluate_fit(path)
    after_hash = _sha256(path)
    if before_hash != after_hash:
        raise RuntimeError("JD changed despite the read-only benchmark guard")
    return {
        "status": "ok" if result is not None else "empty",
        "elapsed_seconds": round(time.monotonic() - started, 3),
        "calls": calls,
        "evaluation": _clean(result),
    }


def _reference_by_jd(attempts: list[dict], control: str) -> dict[str, dict]:
    grouped: dict[str, list[dict]] = {}
    for attempt in attempts:
        if attempt["model"] == control and attempt["status"] == "ok":
            grouped.setdefault(attempt["jd_sha256"], []).append(attempt["evaluation"])
    refs = {}
    for jd_hash, rows in grouped.items():
        ref: dict[str, Any] = {}
        for metric in NUMERIC_METRICS:
            vals = [r.get(metric) for r in rows if isinstance(r.get(metric), (int, float))]
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
            "median_elapsed_seconds": statistics.median(r["elapsed_seconds"] for r in ok) if ok else None,
            "metrics": {},
        }
        for metric in NUMERIC_METRICS:
            deltas = []
            signed = []
            for row in ok:
                value = row["evaluation"].get(metric)
                reference = references.get(row["jd_sha256"], {}).get(metric)
                if isinstance(value, (int, float)) and isinstance(reference, (int, float)):
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
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("paths", nargs="*", help="JD files; defaults to five varied stored JDs")
    parser.add_argument("--profile", default=os.environ.get("RESUME_PROFILE"))
    parser.add_argument("--models", nargs="+", default=list(DEFAULT_CANDIDATES))
    parser.add_argument("--control-model", default=orchestrator.EVAL_MODEL)
    parser.add_argument("--control-runs", type=int, default=2)
    parser.add_argument("--candidate-runs", type=int, default=1)
    parser.add_argument("--stage", choices=("both", "capability", "recruiter"), default="both")
    parser.add_argument("--limit", type=int)
    parser.add_argument("--output", default="eval-model-benchmark.json")
    parser.add_argument("--resume", action="store_true", help="Resume matching attempts from --output")
    args = parser.parse_args(argv)

    if not args.profile:
        args.profile = profile_paths.active_profile()
    if args.control_model not in args.models:
        args.models.insert(0, args.control_model)
    if args.control_runs < 1 or args.candidate_runs < 1:
        parser.error("run counts must be positive")
    profile_paths.set_active_profile(args.profile)
    paths = _resolve_paths(args.paths, args.profile)
    if args.limit:
        paths = paths[: args.limit]
    stage_models = ["capability", "recruiter"] if args.stage == "both" else [args.stage]

    report = {
        "schema_version": 1,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "config": {
            "profile": args.profile,
            "models": args.models,
            "control_model": args.control_model,
            "control_runs": args.control_runs,
            "candidate_runs": args.candidate_runs,
            "stage": args.stage,
            "fallbacks_disabled": True,
            "persistence_blocked": True,
        },
        "jds": [
            {"path": path, "name": _short_name(path), "sha256": _sha256(path)} for path in paths
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
        _attempt_key(r["model"], r["run"], r["jd_sha256"])
        for r in report["attempts"]
    }
    engine = orchestrator.ResumeEngine()

    for jd in report["jds"]:
        for model in args.models:
            run_count = args.control_runs if model == args.control_model else args.candidate_runs
            for run in range(1, run_count + 1):
                key = _attempt_key(model, run, jd["sha256"])
                if key in completed:
                    continue
                print(f"{jd['name']} | {model} | run {run}/{run_count}", flush=True)
                base = {
                    "jd_path": jd["path"],
                    "jd_name": jd["name"],
                    "jd_sha256": jd["sha256"],
                    "model": model,
                    "run": run,
                }
                try:
                    base.update(_run_once(engine, jd["path"], model, stage_models))
                except Exception as exc:  # noqa: BLE001 - failures are benchmark data
                    base.update(
                        {
                            "status": "error",
                            "elapsed_seconds": None,
                            "calls": [],
                            "evaluation": None,
                            "error_type": type(exc).__name__,
                            "error": str(exc),
                        }
                    )
                    print(f"  ERROR: {type(exc).__name__}: {exc}", flush=True)
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
