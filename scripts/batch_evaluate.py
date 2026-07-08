"""
batch_evaluate.py -- the shared "evaluate every pending JD" scoring loop,
reused by both `resume evaluate` (batch mode) and `resume run --pick` (the
interactive picker). Real Gemini cost: one call per pending JD. See
docs/superpowers/specs/2026-07-05-batch-evaluate-and-picker-design.md.
"""

import os
import time

import jd_manager
import orchestrator

# Keeps evaluate_fit() calls under this account's Gemini API tier (15 RPM
# for gemini-3.1-flash-lite): 60s / 15 = 4.0s minimum spacing, plus a
# buffer so a rolling-window quota counter doesn't still trip it.
SECONDS_BETWEEN_CALLS = 4.5


def _sort_key(result: dict) -> tuple:
    """Errored entries always sort last, regardless of score; otherwise
    highest composite_score first. Safe against a missing/None score on
    an errored entry -- `or 0` defaults it before negating."""
    return (1 if result.get("error") else 0, -(result.get("composite_score") or 0))


def evaluate_all_pending(pending_paths: list = None, skip_evaluated: bool = True) -> list:
    """
    Runs ResumeEngine.evaluate_fit() over every path in pending_paths
    (defaults to jd_manager.get_pending_jds() if None). Returns a list of
    {job_key, source_file, company_name, job_title, composite_score,
    recommendation, hard_blockers, error} sorted via _sort_key() --
    highest score first, errored entries always last. A JD that fails to
    evaluate gets error=True instead of crashing the whole batch.

    skip_evaluated=True (default) skips any JD that already carries a
    persisted _evaluation (jd_manager.save_evaluation() from a prior run)
    -- pass False to force re-evaluating everything, overwriting existing
    scores.
    """
    if pending_paths is None:
        pending_paths = jd_manager.get_pending_jds()

    if skip_evaluated:
        already_evaluated = sum(1 for p in pending_paths if jd_manager.read_evaluation(p))
        if already_evaluated:
            pending_paths = [p for p in pending_paths if not jd_manager.read_evaluation(p)]
            print(f"Skipping {already_evaluated} already-evaluated JD(s); evaluating {len(pending_paths)} new one(s).")

    engine = orchestrator.ResumeEngine()
    results = []

    for i, path in enumerate(pending_paths):
        if i > 0:
            time.sleep(SECONDS_BETWEEN_CALLS)
        job_title, company_name = jd_manager.extract_job_meta(path)
        print(f"  [{i + 1}/{len(pending_paths)}] Evaluating {company_name or os.path.basename(path)}...")
        evaluation = engine.evaluate_fit(path)

        if not evaluation:
            results.append({
                "job_key": jd_manager.compute_job_key(path),
                "source_file": path,
                "company_name": company_name or "unknown",
                "job_title": job_title or "unknown",
                "composite_score": None,
                "recommendation": None,
                "hard_blockers": [],
                "error": True,
            })
            continue

        jd_manager.save_evaluation(path, evaluation)

        results.append({
            "job_key": jd_manager.compute_job_key(path),
            "source_file": path,
            "company_name": company_name or "unknown",
            "job_title": job_title or "unknown",
            "composite_score": evaluation.get("composite_score"),
            "recommendation": evaluation.get("recommendation"),
            "hard_blockers": evaluation.get("hard_blockers") or [],
            "error": False,
        })

    results.sort(key=_sort_key)
    return results
