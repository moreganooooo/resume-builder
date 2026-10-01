#!/usr/bin/env python3
"""Compare real resume-builder role-evaluation prompts on NVIDIA NIM models.

Read-only: nothing is saved to a JD or data.db. The script uses the actual
production fit context, capability/recruiter prompts, and Pydantic schemas.
Pass explicit JD paths for a fair model bake-off; automatic selection can see
only file-backed JDs and may omit database-only roles.

Example:
  RESUME_PROFILE=dominick python scripts/nim_eval_compare_nvidia_v2.py \
    --model nvidia/nemotron-3-super-120b-a12b \
    path/to/role-one.json path/to/role-two.json path/to/role-three.json
"""

import argparse
import glob
import json
import os
import re
import statistics
import sys
import time
from typing import Any

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import jd_manager  # noqa: E402
import nim_smoke_test_nvidia_v2 as nim  # noqa: E402
import orchestrator  # noqa: E402
import profile_paths  # noqa: E402
from schemas import CapabilityEvaluationSchema, RecruiterEvaluationSchema  # noqa: E402


def _pick_file_backed_jds(n: int) -> list[str]:
    """Fallback only; explicit positional JD paths are preferred."""
    scored: list[tuple[float, str]] = []
    for path in sorted(glob.glob(os.path.join(profile_paths.jds_dir(), "*.json"))):
        evaluation = jd_manager.read_evaluation(path)
        if evaluation and isinstance(evaluation.get("composite_score"), (int, float)):
            scored.append((float(evaluation["composite_score"]), path))
    scored.sort()
    if len(scored) <= n:
        return [path for _, path in scored]
    step = (len(scored) - 1) / (n - 1)
    return [scored[round(index * step)][1] for index in range(n)]


def _mean(values: dict[str, Any] | None) -> float | None:
    numeric = [
        value for value in (values or {}).values() if isinstance(value, (int, float))
    ]
    return round(statistics.mean(numeric), 2) if numeric else None


def _run_stage(
    client: Any,
    model: str,
    prompt_file: str,
    schema_cls: Any,
    context: str,
    engine: Any,
    temperature: float,
    reasoning_effort: str,
    max_tokens: int,
) -> dict[str, Any]:
    result = nim._structured_call(
        client,
        model,
        [
            {"role": "system", "content": engine.load_prompt(prompt_file)},
            {"role": "user", "content": context},
        ],
        schema_cls.model_json_schema(),
        temperature=temperature,
        max_tokens=max_tokens,
        reasoning_effort=nim.effort_override(reasoning_effort),
    )
    if result["ok"]:
        try:
            result["parsed"] = json.loads(result["text"])
            schema_cls.model_validate(result["parsed"])
            result["schema_valid"] = True
        except Exception as exc:  # noqa: BLE001
            result.setdefault("parsed", None)
            result["schema_valid"] = False
            result["schema_error"] = str(exc)[:300]
    return result


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", default=nim.DEFAULT_MODEL)
    parser.add_argument(
        "--n",
        type=int,
        default=3,
        help="only used when positional JD paths are omitted",
    )
    parser.add_argument("--temperature", type=float, default=0.0)
    parser.add_argument("--max-tokens", type=int, default=2500)
    parser.add_argument(
        "--reasoning-effort", choices=nim.REASONING_EFFORTS, default="auto"
    )
    parser.add_argument("--no-warmup", action="store_true")
    parser.add_argument(
        "jds", nargs="*", help="explicit evaluated JD JSON paths; strongly preferred"
    )
    args = parser.parse_args()

    client = nim._client()
    engine = orchestrator.ResumeEngine()
    paths = args.jds or _pick_file_backed_jds(args.n)
    if not paths:
        raise SystemExit(
            "No evaluated file-backed JDs found. Pass explicit JD JSON paths."
        )
    if not args.jds:
        print(
            "WARNING: automatic selection sees only file-backed JDs. Explicit paths are better for comparisons.\n"
        )

    print(
        f"\nModel: {args.model} | JDs: {len(paths)} | max tokens/stage: {args.max_tokens}\n"
    )
    if not args.no_warmup:
        nim.warmup(client, args.model)

    summary: list[dict[str, Any]] = []
    for path in paths:
        name = os.path.basename(path).removesuffix(".json")[:58]
        baseline = jd_manager.read_evaluation(path) or {}
        jd_text = jd_manager.read_jd_text(path)
        context = engine.build_fit_evaluation_context(jd_text, [])
        print(f"{name}\n context: {len(context):,} chars")

        started = time.perf_counter()
        capability = _run_stage(
            client,
            args.model,
            "evaluate_capability.md",
            CapabilityEvaluationSchema,
            context,
            engine,
            args.temperature,
            args.reasoning_effort,
            args.max_tokens,
        )
        recruiter = _run_stage(
            client,
            args.model,
            "evaluate_recruiter.md",
            RecruiterEvaluationSchema,
            context,
            engine,
            args.temperature,
            args.reasoning_effort,
            args.max_tokens,
        )
        elapsed = round(time.perf_counter() - started, 1)

        capability_data = capability.get("parsed") or {}
        recruiter_data = recruiter.get("parsed") or {}
        row: dict[str, Any] = {
            "jd": name,
            "path": path,
            "seconds": elapsed,
            "capability_status": (
                "OK"
                if capability.get("schema_valid")
                else f"FAIL {capability.get('diagnosis') or capability.get('schema_error', 'invalid JSON/schema')}"
            ),
            "recruiter_status": (
                "OK"
                if recruiter.get("schema_valid")
                else f"FAIL {recruiter.get('diagnosis') or recruiter.get('schema_error', 'invalid JSON/schema')}"
            ),
            "fit_mean": (
                _mean(capability_data.get("fit_subscores")),
                _mean(baseline.get("fit_subscores")),
            ),
            "odds_mean": (
                _mean(recruiter_data.get("interview_odds_subscores")),
                _mean(baseline.get("interview_odds_subscores")),
            ),
            "pursue_mean": (
                _mean(recruiter_data.get("practical_pursue_subscores")),
                _mean(baseline.get("practical_pursue_subscores")),
            ),
            "recommendation": (
                recruiter_data.get("recommendation"),
                baseline.get("recommendation"),
            ),
            "blockers": (
                len(recruiter_data.get("hard_blockers") or []),
                len(baseline.get("hard_blockers") or []),
            ),
            "gaps": (
                len(capability_data.get("capability_gaps") or []),
                len(baseline.get("capability_gaps") or []),
            ),
            "stored_composite": baseline.get("composite_score"),
            "tokens_in": (capability.get("tokens") or {}).get("in"),
            "modes": (capability.get("mode"), recruiter.get("mode")),
            "timing": (capability.get("diagnosis"), recruiter.get("diagnosis")),
        }
        summary.append(row)

        for key, value in row.items():
            if key not in {"jd", "path"}:
                print(f" {key:<19} {value}")
        print()
        nim._save(
            args.model,
            "eval_" + re.sub(r"[^A-Za-z0-9]+", "-", name)[:30],
            {"ok": True, "row": row, "capability": capability, "recruiter": recruiter},
        )

    print("(tuples are NVIDIA result, stored Gemini baseline)")
    comparable = [
        row for row in summary if isinstance(row["fit_mean"][0], (int, float))
    ]
    agreement = sum(
        1 for row in comparable if row["recommendation"][0] == row["recommendation"][1]
    )
    print(
        f"\nscored {len(comparable)}/{len(summary)} JDs; recommendation matched stored baseline on {agreement}"
    )


if __name__ == "__main__":
    main()
