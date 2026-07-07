"""
batch_evaluate.py -- the shared "evaluate every pending JD" scoring loop,
reused by both `resume evaluate` (batch mode) and `resume run --pick` (the
interactive picker). Real Gemini cost: one call per pending JD. See
docs/superpowers/specs/2026-07-05-batch-evaluate-and-picker-design.md.
"""

import jd_manager
import orchestrator


def _sort_key(result: dict) -> tuple:
    """Errored entries always sort last, regardless of score; otherwise
    highest composite_score first. Safe against a missing/None score on
    an errored entry -- `or 0` defaults it before negating."""
    return (1 if result.get("error") else 0, -(result.get("composite_score") or 0))


def evaluate_all_pending(pending_paths: list = None) -> list:
    """
    Runs ResumeEngine.evaluate_fit() over every path in pending_paths
    (defaults to jd_manager.get_pending_jds() if None). Returns a list of
    {job_key, source_file, company_name, job_title, composite_score,
    recommendation, hard_blockers, error} sorted via _sort_key() --
    highest score first, errored entries always last. A JD that fails to
    evaluate gets error=True instead of crashing the whole batch.
    """
    if pending_paths is None:
        pending_paths = jd_manager.get_pending_jds()

    engine = orchestrator.ResumeEngine()
    results = []

    for path in pending_paths:
        job_title, company_name = jd_manager.extract_job_meta(path)
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
