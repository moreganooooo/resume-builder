"""
Run the REAL evaluation prompts and candidate context through an NVIDIA NIM
model and compare against each JD's stored evaluation. Read-only: nothing is
saved to any JD or data.db; raw outputs go to scratch/nim-results/.

It reuses the production path up to the model call --
`ResumeEngine.build_fit_evaluation_context()`, `evaluate_capability.md`,
`evaluate_recruiter.md` and their pydantic schemas -- so the only variable is
the model. The stored baseline was produced by the Gemini evaluator, and
scores drift between runs of that too (see CLAUDE.md), so read deltas as
"same ballpark / same verdict" rather than exact agreement.

Usage:
    RESUME_PROFILE=dominick python scripts/nim_eval_compare.py
    RESUME_PROFILE=dominick python scripts/nim_eval_compare.py --n 8
    python scripts/nim_eval_compare.py --model google/gemma-4-31b-it path1.json ...
"""

import argparse
import glob
import json
import os
import statistics
import sys
import time
from typing import Any

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import jd_manager  # noqa: E402
import nim_smoke_test as nim  # loads the profile .env  # noqa: E402
import orchestrator  # noqa: E402
import profile_paths  # noqa: E402
from schemas import CapabilityEvaluationSchema, RecruiterEvaluationSchema  # noqa: E402


def _pick_jds(n: int) -> list[str]:
    """Evaluated JDs spread evenly across the stored composite range."""
    scored = []
    for path in sorted(glob.glob(os.path.join(profile_paths.jds_dir(), "*.json"))):
        ev = jd_manager.read_evaluation(path)
        if ev and ev.get("composite_score") is not None:
            scored.append((ev["composite_score"], path))
    scored.sort()
    if len(scored) <= n:
        return [p for _, p in scored]
    step = (len(scored) - 1) / (n - 1)
    return [scored[round(i * step)][1] for i in range(n)]


def _mean(d: dict[str, Any] | None) -> float | None:
    vals = [v for v in (d or {}).values() if isinstance(v, (int, float))]
    return round(statistics.mean(vals), 2) if vals else None


def _run_stage(
    client,
    model,
    prompt_file,
    schema_cls,
    context,
    engine,
    temperature=0.0,
    reasoning_effort="none",
) -> dict:
    schema = schema_cls.model_json_schema()
    result = nim._structured_call(
        client,
        model,
        [
            {"role": "system", "content": engine.load_prompt(prompt_file)},
            {"role": "user", "content": context},
        ],
        schema,
        temperature=temperature,
        max_tokens=8000,
        reasoning_effort=nim.effort_override(reasoning_effort),
    )
    if result["ok"]:
        try:
            result["parsed"] = json.loads(result["text"])
            schema_cls.model_validate(result["parsed"])
            result["schema_valid"] = True
        except Exception as exc:  # noqa: BLE001 — invalid output is a finding
            result.setdefault("parsed", None)
            result["schema_valid"] = False
            result["schema_error"] = str(exc)[:300]
    return result


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", default=nim.DEFAULT_MODEL)
    ap.add_argument("--n", type=int, default=6)
    ap.add_argument("--temperature", type=float, default=0.0)
    ap.add_argument("--reasoning-effort", choices=nim.REASONING_EFFORTS, default="auto")
    ap.add_argument("--no-warmup", action="store_true")
    ap.add_argument("jds", nargs="*")
    args = ap.parse_args()

    client = nim._client()
    engine = orchestrator.ResumeEngine()
    paths = args.jds or _pick_jds(args.n)
    print(f"\nModel: {args.model}   JDs: {len(paths)}\n")
    if not args.no_warmup:
        nim.warmup(client, args.model)

    summary: list[dict[str, Any]] = []
    for path in paths:
        name = os.path.basename(path).replace(".json", "")[:58]
        base = jd_manager.read_evaluation(path) or {}
        jd_text = jd_manager.read_jd_text(path)
        context = engine.build_fit_evaluation_context(jd_text, [])
        print(f"{name}\n  context: {len(context):,} chars")

        started = time.perf_counter()
        cap = _run_stage(
            client,
            args.model,
            "evaluate_capability.md",
            CapabilityEvaluationSchema,
            context,
            engine,
            args.temperature,
            args.reasoning_effort,
        )
        rec = _run_stage(
            client,
            args.model,
            "evaluate_recruiter.md",
            RecruiterEvaluationSchema,
            context,
            engine,
            args.temperature,
            args.reasoning_effort,
        )
        elapsed = round(time.perf_counter() - started, 1)

        row: dict[str, Any] = {"jd": name, "seconds": elapsed}
        for label, stage in (("capability", cap), ("recruiter", rec)):
            if not stage["ok"]:
                row[label] = f"FAIL {stage.get('diagnosis')} [{stage['error'][:100]}]"
            elif not stage.get("schema_valid"):
                row[label] = f"INVALID {stage.get('schema_error', '')[:120]}"
        cap_parsed = cap.get("parsed")
        rec_parsed = rec.get("parsed")
        cd = cap_parsed if isinstance(cap_parsed, dict) else {}
        rd = rec_parsed if isinstance(rec_parsed, dict) else {}
        row.update(
            {
                "fit_mean": (
                    _mean(cd.get("fit_subscores")),
                    _mean(base.get("fit_subscores")),
                ),
                "odds_mean": (
                    _mean(rd.get("interview_odds_subscores")),
                    _mean(base.get("interview_odds_subscores")),
                ),
                "pursue_mean": (
                    _mean(rd.get("practical_pursue_subscores")),
                    _mean(base.get("practical_pursue_subscores")),
                ),
                "recommendation": (
                    rd.get("recommendation"),
                    base.get("recommendation"),
                ),
                "blockers": (
                    len(rd.get("hard_blockers") or []),
                    len(base.get("hard_blockers") or []),
                ),
                "gaps": (
                    len(cd.get("capability_gaps") or []),
                    len(base.get("capability_gaps") or []),
                ),
                "stored_composite": base.get("composite_score"),
                "tokens_in": (cap.get("tokens") or {}).get("in"),
                "mode": cap.get("mode"),
                "timing": (cap.get("diagnosis"), rec.get("diagnosis")),
            }
        )
        summary.append(row)
        for k, v in row.items():
            if k not in ("jd",):
                print(f"  {k:<15} {v}")
        print()
        nim._save(
            args.model,
            "eval_" + name[:30],
            {"ok": True, "row": row, "capability": cap, "recruiter": rec},
        )

    print("(tuples are (nim, stored baseline))")
    ok = [r for r in summary if isinstance(r["fit_mean"][0], (int, float))]
    agree = sum(1 for r in ok if r["recommendation"][0] == r["recommendation"][1])
    print(
        f"\nscored {len(ok)}/{len(summary)} JDs; recommendation matched stored on {agree}"
    )


if __name__ == "__main__":
    main()
