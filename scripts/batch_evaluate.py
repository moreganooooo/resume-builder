"""
batch_evaluate.py -- the shared "evaluate every pending JD" scoring loop,
reused by both `resume evaluate` (batch mode) and `resume run --pick` (the
interactive picker). Real Gemini cost: TWO calls per pending JD (capability
+ recruiter, both EVAL_MODEL -- the split-agent design evaluate_fit()
was upgraded to). Scoring calls stay on EVAL_MODEL and pass
SCORING_FALLBACKS, so they never reach gemini-3.5-flash-lite, whose
scores moved well past run-to-run noise (2026-09-15). See
docs/superpowers/specs/2026-07-05-batch-evaluate-and-picker-design.md.
"""

import contextlib
import logging
import os
import time

import cli_art
import dedup_pending_roles
import jd_manager
import jd_source
import orchestrator
import theme
from gemini_client import SustainedFailureError

# Keeps evaluate_fit() calls under this account's Gemini API tier (15 RPM
# for gemini-3.1-flash-lite / EVAL_MODEL). evaluate_fit() now makes TWO
# back-to-back calls per JD (capability + recruiter, both EVAL_MODEL,
# with no pacing between them) rather than one -- this constant used to
# assume one call/JD (60s / 15 = 4.0s minimum), which at 2 calls/JD was
# actually running at ~2/4.5s =~ 26.7 RPM, nearly double the 15 RPM cap,
# and produced a constant stream of HTTP 429s and exponential-backoff
# stalls on any real batch run. 15 RPM / 2 calls-per-JD = 7.5 JD/min = 8.0s
# minimum spacing, plus a buffer so a rolling-window quota counter doesn't
# still trip it.
SECONDS_BETWEEN_CALLS = (
    0.0
    if (
        os.environ.get("CI") == "true"
        or os.environ.get("RESUME_BUILDER_TESTING") == "1"
    )
    else 9.0
)

# Consecutive roles that came back with no evaluation before the batch stops.
# Each failed role has already spent 2 calls x 6 retries of up to ~90s
# backoff, so on a day when every scoring model is 503ing, grinding through
# the rest of a 100+ role backlog costs hours and scores nothing. Unscored
# roles stay pending, so the next run picks up exactly where this one quit.
CONSECUTIVE_FAILURE_LIMIT = 3


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


def _result_row(identifier, job_key, job_title, company_name, evaluation) -> dict:
    """One row of evaluate_all_pending()'s return list. evaluation=None is
    the errored shape -- every score key present but empty, so callers
    (cli_art.render_fit_table) never have to special-case it."""
    evaluation = evaluation or {}
    return {
        "job_key": job_key,
        "source_file": identifier,
        "company_name": company_name or "unknown",
        "job_title": job_title or "unknown",
        "composite_score": evaluation.get("composite_score"),
        "fit_score": evaluation.get("fit_score"),
        "interview_odds_score": evaluation.get("interview_odds_score"),
        "practical_pursue_score": evaluation.get("practical_pursue_score"),
        "recommendation": evaluation.get("recommendation"),
        "why": evaluation.get("why") or "",
        "hard_blockers": evaluation.get("hard_blockers") or [],
        "experience_blockers": evaluation.get("experience_blockers") or [],
        "posting_legitimacy": evaluation.get("posting_legitimacy") or "",
        "posting_age_days": evaluation.get("posting_age_days"),
        "error": not evaluation,
    }


@contextlib.contextmanager
def _resolved(identifier: str):
    """jd_source.resolved_jd(), but a totally unknown identifier is handed
    back unchanged instead of raising.

    An entry that is neither a file on disk nor a row in the database is
    a JD that moved or a row that was deleted between building the work
    list and reaching it. The old file-only loop let evaluate_fit() fail
    on it and recorded one errored row; raising here would instead end
    the batch over a single stale entry.
    """
    try:
        context = jd_source.resolved_jd(identifier)
    except LookupError:
        yield identifier, False
        return
    try:
        with context as resolved:
            yield resolved
    except LookupError:
        yield identifier, False


def _evaluate_one(engine, identifier: str, on_label=None) -> dict:
    """Scores a single JD, whether it is a file path or a database-only
    job id, and returns one _result_row().

    jd_source.resolved_jd() is what makes the second case work: it hands
    back a temp file for a database row and syncs the saved _evaluation
    back into that row on exit, so every file-oriented call below
    (extract_job_meta, evaluate_fit, save_evaluation, compute_job_key)
    stays unchanged.
    """
    with _resolved(identifier) as (path, is_database_backed):
        job_title, company_name = jd_manager.extract_job_meta(path)
        # Reported back rather than returned, because the caller wants it
        # on the progress bar BEFORE the (slow) evaluate_fit call below,
        # not after the row comes back.
        if on_label:
            on_label(company_name or os.path.basename(path))
        evaluation = engine.evaluate_fit(path)
        if not evaluation:
            return _result_row(
                identifier,
                jd_manager.compute_job_key(path),
                job_title,
                company_name,
                None,
            )

        job_key = jd_manager.compute_job_key(path)
        jd_manager.save_evaluation(path, evaluation)

        # A JD Morgan's already said no to (Skip) shouldn't sit in the
        # pending list forever -- archive it immediately rather than
        # waiting for a manual pass. archive_jd() moves the file, so this
        # has to happen after compute_job_key()/save_evaluation() above,
        # both of which need it still at its original path. A
        # database-only job takes set_status() instead: archive_jd()
        # would move its TEMP file into jds/archived/ and leave exactly
        # the stray JD jd_source exists to avoid.
        skipped = evaluation.get("recommendation") == "Skip"
        source = identifier if is_database_backed else path
        if skipped and not is_database_backed:
            source = jd_manager.archive_jd(path)
            _archive_copies_of(
                lambda: dedup_pending_roles.archive_copies_of_file(source)
            )

    # Outside the context ON PURPOSE. Leaving the block runs sync_back(),
    # which writes the temp file's payload over the row -- including its
    # status. Archiving inside the block therefore set "archived" and had
    # it immediately reset to "pending", silently leaving every skipped
    # scan row in the pending list.
    if skipped and is_database_backed:
        jd_source.set_status(identifier, "archived")
        _archive_copies_of(lambda: dedup_pending_roles.archive_copies_of_id(identifier))

    return _result_row(source, job_key, job_title, company_name, evaluation)


def _archive_copies_of(archive_fn) -> None:
    """A Skip archives the posting; this also archives its other pending
    copies (dedup_pending_roles.archive_copies_of), so the posting actually
    leaves the list. Best-effort -- never fails the evaluation."""
    try:
        archive_fn()
    except Exception as exc:
        logging.warning(f"batch_evaluate: could not archive duplicate copies: {exc}")


def _report_early_stop(remaining: int) -> None:
    """Tells the user why the batch quit and that nothing was lost."""
    cli_art.print_literal(
        "Stopped early: Gemini kept failing, several calls in a row came "
        "back with no score. Google's servers are likely overloaded. "
        f"{remaining} role(s) were not attempted, and every unscored role is "
        "still pending -- run this again later and it picks up where it "
        "left off."
    )


def evaluate_all_pending(
    pending_paths: list | None = None,
    skip_evaluated: bool = True,
    evaluated_before: str | None = None,
) -> list:
    """
    Runs ResumeEngine.evaluate_fit() over every entry in pending_paths --
    each a JD file path OR a database-only job id -- and returns a list of
    {job_key, source_file, company_name, job_title, composite_score,
    recommendation, hard_blockers, error} sorted via _sort_key() --
    highest score first, errored entries always last. A JD that fails to
    evaluate gets error=True instead of crashing the whole batch.

    skip_evaluated=True (default) skips any JD that already carries a
    persisted _evaluation (jd_manager.save_evaluation() from a prior run)
    -- pass False to force re-evaluating everything, overwriting existing
    scores.

    evaluated_before re-evaluates roles whose persisted score predates
    that date, and is the reason skip_evaluated=False is no longer the
    only way to redo work. The flag alone used to be DEAD on the default
    path: the work list came from picker.unevaluated_roles(), which by
    definition contains nothing evaluated, so "force re-evaluate
    everything" walked the same never-evaluated backlog and silently
    changed nothing. Defaulting to picker.SCORING_EPOCH would be worse
    than dead -- it would spend an API call per role without being asked
    -- so the caller names the date.
    """
    auto_derived = pending_paths is None

    if pending_paths is None:
        import picker

        if evaluated_before is not None:
            file_paths, job_ids = picker.stale_roles(evaluated_before)
            pending_paths = file_paths + job_ids
            # Vintage already selected the set; a second filter on
            # "has an evaluation" would discard every stale role.
            skip_evaluated = False
        elif not skip_evaluated:
            # Asked to force, with no vintage: everything pending, so the
            # flag reaches roles that already carry a score.
            file_paths, job_ids = picker.pending_roles(evaluated_before="9999")
            pending_paths = file_paths + job_ids

    if pending_paths is None:
        # Both halves of the backlog, not just the file-backed one.
        # get_pending_jds() lists FILES, and most pending jobs are
        # database-only hash-keyed scan rows with no file -- defaulting to
        # it meant "evaluate every pending JD" silently skipped the larger
        # half (627 of 1,337 for this profile). picker.unevaluated_roles()
        # is the same function the banner counts with, so what the banner
        # promises is what actually gets evaluated.
        import picker

        file_paths, job_ids = picker.unevaluated_roles()
        pending_paths = file_paths + job_ids

    if skip_evaluated:
        already_evaluated, pending_paths = split_evaluated(pending_paths)
        if already_evaluated:
            cli_art.print_literal(
                f"Skipping {len(already_evaluated)} already-evaluated JD(s); evaluating {len(pending_paths)} new one(s)."
            )

    # Gate check runs only on an auto-derived work list, not an explicit
    # caller-supplied pick (resume run --pick choosing one specific JD
    # should still evaluate it) -- see find_retroactively_excluded_roles.py
    # for why this exists: scan_filters.yml can change after a role was
    # scraped but before it's evaluated, and nothing else re-checks that.
    if auto_derived and pending_paths:
        import find_retroactively_excluded_roles as fre
        import profile_paths

        pending_paths, gate_excluded = fre.filter_gate_passing(
            pending_paths, profile_paths.active_profile()
        )
        if gate_excluded:
            cli_art.print_literal(
                f"Excluding {len(gate_excluded)} role(s) that no longer pass today's "
                f"scan filters; evaluating {len(pending_paths)}. Run "
                "`python scripts/find_retroactively_excluded_roles.py` to review and "
                "archive them."
            )
            for finding in gate_excluded:
                cli_art.print_literal(
                    f"  [{finding['company']}] {finding['title']} -- "
                    + ", ".join(finding["gate_failures"])
                )

    engine = orchestrator.ResumeEngine()
    results = []
    consecutive_failures = 0
    stopped_after = None

    with cli_art.new_progress() as progress:
        task = progress.add_task(
            f"[bold {theme.BRAND}]Evaluating JDs...", total=len(pending_paths)
        )
        for i, identifier in enumerate(pending_paths):
            if i > 0:
                time.sleep(SECONDS_BETWEEN_CALLS)

            def label(name, index=i):
                progress.update(
                    task,
                    description=f"[{index + 1}/{len(pending_paths)}] Weighing the fit for {name}...",
                )

            try:
                result = _evaluate_one(engine, identifier, on_label=label)
            except SustainedFailureError:
                # generate() raises this after back-to-back exhausted calls.
                # Here that is the same signal as the counter below, so it
                # stops the batch the same way instead of escaping as a
                # traceback that throws away every result collected so far.
                stopped_after = i + 1
                break
            results.append(result)
            progress.advance(task)
            consecutive_failures = (
                consecutive_failures + 1 if result.get("error") else 0
            )
            if consecutive_failures >= CONSECUTIVE_FAILURE_LIMIT:
                stopped_after = i + 1
                break

    if stopped_after is not None:
        _report_early_stop(len(pending_paths) - stopped_after)

    results.sort(key=_sort_key)
    return results
