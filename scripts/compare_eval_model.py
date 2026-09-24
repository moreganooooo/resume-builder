"""
Compare evaluation scores from gemma-4-26b-a4b-it vs the stored baseline
on a small set of JDs. Does NOT save any results — read-only against the
stored evaluations and the API.

Usage:
    RESUME_PROFILE=morgan python scripts/compare_eval_model.py
    RESUME_PROFILE=morgan python scripts/compare_eval_model.py path1.json path2.json ...

Notes:
  - Makes 2 live API calls per JD (capability + recruiter).
  - gemma-4-26b-a4b-it has only been confirmed for grounded Search so far;
    this script is the test of whether it can do structured JSON generation.
  - If JSON mode is unsupported the run fails fast and says so clearly.
  - The Gemma 75s pacing applies, so 5 JDs takes ~6-7 minutes of wall-clock
    time due to the 75s spacing between Gemma calls.
"""

import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import profile_paths
from dotenv import load_dotenv

load_dotenv(profile_paths.env_path(), override=True)

import jd_manager  # noqa: E402 — must come after load_dotenv
import orchestrator  # noqa: E402
from gemini_client import GeminiClient  # noqa: E402

TEST_MODEL = "gemma-4-26b-a4b-it"

DEFAULT_JDS = [
    "jds/morgan/2026-09-13_Allego_SeniorCustomerMarketingCommunityManager.json",
    "jds/morgan/2026-09-13_Block_B2BMarketingManagerContentSocial.json",
    "jds/morgan/2026-09-13_Directive_PRCommunicationsManagerRemoteUSDirective.json",
    "jds/morgan/2026-09-13_ComputerTaskGroup_MarketingManagerI.json",
    "jds/morgan/2026-09-13_Dropbox_ProgramManagerCustomersRemoteUS.json",
]

_COLS = ("composite", "fit", "pursue", "rec")


def _short_name(path: str) -> str:
    base = os.path.basename(path).replace(".json", "")
    parts = base.split("_")
    # date_Company_Role -> "Company | Role"
    if len(parts) >= 3:
        return f"{parts[1]} | {'_'.join(parts[2:])}"[:60]
    return base[:60]


def _scores_from_eval(ev: dict) -> dict:
    return {
        "composite": ev.get("composite_score"),
        "fit": ev.get("fit_score"),
        "pursue": ev.get("practical_pursue_score"),
        "rec": ev.get("recommendation", "—"),
    }


def _run_test_eval(engine: orchestrator.ResumeEngine, jd_path: str) -> dict | None:
    """Run evaluate_fit with TEST_MODEL, returning the evaluation dict without saving."""
    original_eval_model = orchestrator.EVAL_MODEL
    original_scoring_fallbacks = orchestrator.SCORING_FALLBACKS
    saved_evals: list = []

    def _capture_save(path, ev, **kwargs):
        saved_evals.append(ev)

    # Patch model, fallbacks (no fallback for test — fail fast), and save
    orchestrator.EVAL_MODEL = TEST_MODEL
    orchestrator.SCORING_FALLBACKS = {}  # no fallback: surface failures directly
    original_save = jd_manager.save_evaluation
    jd_manager.save_evaluation = _capture_save  # type: ignore[assignment]

    try:
        result = engine.evaluate_fit(jd_path)
    finally:
        orchestrator.EVAL_MODEL = original_eval_model
        orchestrator.SCORING_FALLBACKS = original_scoring_fallbacks
        jd_manager.save_evaluation = original_save  # type: ignore[assignment]

    # evaluate_fit returns None on failure; saved_evals holds what would have
    # been persisted (the pre-rescore dict), result is the post-rescore one.
    return result


def _fmt(val) -> str:
    if val is None:
        return "—"
    if isinstance(val, float):
        return f"{val:.2f}"
    return str(val)


def main(jd_paths: list[str]) -> None:
    engine = orchestrator.ResumeEngine()

    print(f"\nComparing {TEST_MODEL} vs stored baseline")
    print(f"{'JD':<62}  {'metric':<10}  {'baseline':>8}  {'test':>8}  {'delta':>8}")
    print("-" * 102)

    for path in jd_paths:
        if not os.path.exists(path):
            print(f"SKIP (file not found): {path}")
            continue

        baseline_ev = jd_manager.read_evaluation(path) or {}
        baseline = _scores_from_eval(baseline_ev)
        name = _short_name(path)

        print(f"\n{name}")
        print(f"  Running {TEST_MODEL}...")

        try:
            test_result = _run_test_eval(engine, path)
        except Exception as e:
            print(f"  ERROR: {e}")
            continue

        if test_result is None:
            print(
                f"  FAILED: evaluate_fit returned None (model may not support JSON mode)"
            )
            continue

        test = _scores_from_eval(test_result)

        for metric in _COLS:
            bv = baseline.get(metric)
            tv = test.get(metric)
            if metric == "rec":
                delta = "" if bv == tv else "CHANGED"
                print(f"  {'rec':<10}  {str(bv):>20}  {str(tv):>20}  {delta}")
            else:
                delta = (
                    f"{(tv or 0) - (bv or 0):+.2f}"
                    if (bv is not None and tv is not None)
                    else "—"
                )
                print(f"  {metric:<10}  {_fmt(bv):>8}  {_fmt(tv):>8}  {delta:>8}")

    print("\nDone. No evaluations were saved.")


if __name__ == "__main__":
    paths = sys.argv[1:] or DEFAULT_JDS
    main(paths)
