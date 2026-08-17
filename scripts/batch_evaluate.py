"""
batch_evaluate.py -- the shared "evaluate every pending JD" scoring loop,
reused by both `resume evaluate` (batch mode) and `resume run --pick` (the
interactive picker). Real Gemini cost: TWO calls per pending JD (capability
+ recruiter, both BUILDER_MODEL -- the split-agent design evaluate_fit()
was upgraded to). See
docs/superpowers/specs/2026-07-05-batch-evaluate-and-picker-design.md.
"""

import os
import time

import cli_art
import jd_manager
import orchestrator
import theme

# Keeps evaluate_fit() calls under this account's Gemini API tier (15 RPM
# for gemini-3.1-flash-lite / BUILDER_MODEL). evaluate_fit() now makes TWO
# back-to-back calls per JD (capability + recruiter, both BUILDER_MODEL,
# with no pacing between them) rather than one -- this constant used to
# assume one call/JD (60s / 15 = 4.0s minimum), which at 2 calls/JD was
# actually running at ~2/4.5s =~ 26.7 RPM, nearly double the 15 RPM cap,
# and produced a constant stream of HTTP 429s and exponential-backoff
# stalls on any real batch run. 15 RPM / 2 calls-per-JD = 7.5 JD/min = 8.0s
# minimum spacing, plus a buffer so a rolling-window quota counter doesn't
# still trip it.
SECONDS_BETWEEN_CALLS = 9.0


def _sort_key(result: dict) -> tuple:
    """Errored entries always sort last, regardless of score; otherwise
    highest composite_score first. Safe against a missing/None score on
    an errored entry -- `or 0` defaults it before negating."""
    return (1 if result.get("error") else 0, -(result.get("composite_score") or 0))


def split_evaluated(pending_paths: list) -> tuple:
    """Splits pending_paths into (already_evaluated, unevaluated), based on
    whether each already carries a persisted _evaluation
    (jd_manager.read_evaluation()). Lets a caller show an accurate
    confirmation count *before* asking to proceed, instead of confirming
    against the full pending count and only filtering afterward."""
    already_evaluated = [p for p in pending_paths if jd_manager.read_evaluation(p)]
    unevaluated = [p for p in pending_paths if not jd_manager.read_evaluation(p)]
    return already_evaluated, unevaluated


def evaluate_all_pending(
    pending_paths: list = None, skip_evaluated: bool = True
) -> list:
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
        already_evaluated, pending_paths = split_evaluated(pending_paths)
        if already_evaluated:
            cli_art.print_literal(
                f"Skipping {len(already_evaluated)} already-evaluated JD(s); evaluating {len(pending_paths)} new one(s)."
            )

    engine = orchestrator.ResumeEngine()
    results = []

    with cli_art.new_progress() as progress:
        task = progress.add_task(
            f"[bold {theme.BRAND}]Evaluating JDs...", total=len(pending_paths)
        )
        for i, path in enumerate(pending_paths):
            if i > 0:
                time.sleep(SECONDS_BETWEEN_CALLS)
            job_title, company_name = jd_manager.extract_job_meta(path)
            label = company_name or os.path.basename(path)
            progress.update(
                task,
                description=f"[{i + 1}/{len(pending_paths)}] Weighing the fit for {label}...",
            )
            evaluation = engine.evaluate_fit(path)

            if not evaluation:
                results.append(
                    {
                        "job_key": jd_manager.compute_job_key(path),
                        "source_file": path,
                        "company_name": company_name or "unknown",
                        "job_title": job_title or "unknown",
                        "composite_score": None,
                        "fit_score": None,
                        "interview_odds_score": None,
                        "practical_pursue_score": None,
                        "recommendation": None,
                        "why": "",
                        "hard_blockers": [],
                        "posting_legitimacy": "",
                        "posting_age_days": None,
                        "error": True,
                    }
                )
                progress.advance(task)
                continue

            job_key = jd_manager.compute_job_key(path)
            jd_manager.save_evaluation(path, evaluation)

            # A JD Morgan's already said no to (Skip) shouldn't sit in the
            # pending list forever -- archive it immediately rather than
            # waiting for a manual pass. archive_jd() moves the file, so this
            # has to happen after compute_job_key()/save_evaluation() above,
            # both of which need it still at its original path.
            if evaluation.get("recommendation") == "Skip":
                path = jd_manager.archive_jd(path)

            results.append(
                {
                    "job_key": job_key,
                    "source_file": path,
                    "company_name": company_name or "unknown",
                    "job_title": job_title or "unknown",
                    "composite_score": evaluation.get("composite_score"),
                    "fit_score": evaluation.get("fit_score"),
                    "interview_odds_score": evaluation.get("interview_odds_score"),
                    "practical_pursue_score": evaluation.get("practical_pursue_score"),
                    "recommendation": evaluation.get("recommendation"),
                    "why": evaluation.get("why") or "",
                    "hard_blockers": evaluation.get("hard_blockers") or [],
                    "posting_legitimacy": evaluation.get("posting_legitimacy") or "",
                    "posting_age_days": evaluation.get("posting_age_days"),
                    "error": False,
                }
            )
            progress.advance(task)

    results.sort(key=_sort_key)
    return results
