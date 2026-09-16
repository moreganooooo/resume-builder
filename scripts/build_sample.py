"""build_sample.py — the `sample` command: runs the full tailor+render
pipeline against a permanent, fixed JD fixture (fixtures/sample_jd.txt)
purely as a QA smoke test, so bullet writing, summary formatting, and PDF
visual details can be eyeballed before ever touching a real JD.

Deliberately does NOT go through orchestrator.run_pipeline() -- that
function moves the source JD into jds/<profile>/completed/ and logs a
"completed application" row into jd_tracker_log.csv/applications.md on
success, both of which are correct for a real job but wrong for a fixture
meant to be re-run indefinitely. This calls ResumeEngine.build_tailored_
resume()/build_tailored_coverletter() directly instead, which do the real
generation work (same bullet-writing/audit/build/render pipeline a real
JD gets) with none of jd_manager's completion tracking.

fixtures/sample_jd.txt lives outside jds/<profile>/ entirely so it's never
picked up by get_pending_jds() during a batch `resume run` -- it can only
ever be processed by explicitly invoking this command.
"""

import datetime
import logging
import os

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(SCRIPT_DIR)
SAMPLE_JD_PATH = os.path.join(PROJECT_ROOT, "fixtures", "sample_jd.txt")

import cli_art
import jd_manager
import orchestrator
import profile_paths
import theme


def _resolve_sample_jd_path() -> str:
    """Prefers a profile-specific fixture (profiles/<name>/sample_jd.txt)
    over the shared fixtures/sample_jd.txt -- the shared one is a single,
    permanent, field-specific JD (marketing), so a profile in a different
    field (e.g. data science) needs its own realistic test JD or nothing
    in its bullet bank matches and the smoke test proves nothing useful.
    Falls back to the shared fixture, unchanged, when a profile hasn't
    added its own -- scoped to the active profile's own directory rather
    than fixtures/ so this can never affect a profile that hasn't opted
    in (including whatever profile is active during a test run)."""
    try:
        profile_specific = os.path.join(profile_paths.profile_root(), "sample_jd.txt")
        if os.path.exists(profile_specific):
            return profile_specific
    except Exception:
        pass
    return SAMPLE_JD_PATH


def build_sample() -> dict:
    """Runs a fresh resume + cover letter build against the fixture JD.
    Returns {"resume": {...}, "coverletter": {...}} -- each value is that
    build_tailored_*() call's own return dict ({} on failure, or the real
    data plus an _output_paths key on success)."""
    logger = logging.getLogger("resume_pipeline")
    log_path = None
    import db as _db

    if not logger.handlers and not _db._is_unisolated_test_write():
        try:
            log_root = profile_paths.logs_dir()
            os.makedirs(log_root, exist_ok=True)
            timestamp = datetime.datetime.now().isoformat().replace(":", "-")
            log_path = os.path.join(log_root, f"pipeline_run_{timestamp}.log")
            handler = logging.FileHandler(log_path, encoding="utf-8")
            formatter = logging.Formatter(
                "%(asctime)s - %(levelname)s - %(message)s",
                datefmt="%Y-%m-%d %H:%M:%S",
            )
            handler.setFormatter(formatter)
            logger.addHandler(handler)
            logger.setLevel(logging.INFO)
            logger.info("Sample build started")
            cli_art.console.export_text(clear=True)  # discard stale transcript
        except Exception as e:
            cli_art.detail(f"Could not initialize logging: {e}", level=cli_art.NORMAL)
            log_path = None

    sample_jd_path = _resolve_sample_jd_path()

    # The shared fixture is permanently marketing-specific (see
    # _resolve_sample_jd_path's own docstring) -- silently running a
    # non-marketing profile's smoke test against it produces a build that
    # "succeeds" without proving anything about that profile's own bullet
    # bank, since nothing in it will match. Surfaced once here rather
    # than only in a comment, since that's exactly how this went unnoticed
    # for every profile except the one that happened to add its own.
    if sample_jd_path == SAMPLE_JD_PATH:
        cli_art.console.print(
            f"  {theme.colorize_icon('warning')} Using the shared marketing sample JD "
            f"-- add profiles/<name>/sample_jd.txt for a profile-specific smoke test.",
            soft_wrap=True,
        )

    if not os.path.exists(sample_jd_path):
        cli_art.console.print(
            f"  {theme.colorize_icon('error')} Sample fixture not found: {sample_jd_path}",
            soft_wrap=True,
        )
        if logger.handlers:
            logger.error(f"Sample fixture not found: {sample_jd_path}")
        return {"resume": {}, "coverletter": {}}

    # Recover the active log file's path even if a prior call in this same
    # process already attached the handler (log_path would otherwise be
    # None here, and the transcript below would have nowhere to go).
    if log_path is None:
        for h in logger.handlers:
            if isinstance(h, logging.FileHandler):
                log_path = h.baseFilename
                break

    # Clear any leftover checkpoint so this is always a full, fresh run --
    # a stale partial checkpoint from an earlier interrupted attempt would
    # silently skip steps this is specifically meant to exercise.
    job_key = jd_manager.compute_job_key(sample_jd_path)
    jd_manager.delete_checkpoint(job_key)

    engine = orchestrator.ResumeEngine()

    cli_art.console.rule("Building Sample Resume", style="dim")
    resume_result = engine.build_tailored_resume(
        jd_path=sample_jd_path,
        master_resume={},
        job_key=job_key,
        interactive=True,
    )

    cli_art.console.rule("Building Sample Cover Letter", style="dim")
    coverletter_result = engine.build_tailored_coverletter(sample_jd_path)

    result = {"resume": resume_result, "coverletter": coverletter_result}
    resume_ok = bool(result["resume"])
    coverletter_ok = bool(result["coverletter"])
    if logger.handlers:
        logger.info(
            f"Sample build complete: resume={'ok' if resume_ok else 'failed'}, "
            f"coverletter={'ok' if coverletter_ok else 'failed'}"
        )
    if log_path:
        orchestrator.append_console_transcript(log_path)
    return result


def main():
    result = build_sample()
    resume_ok = bool(result["resume"])
    coverletter_ok = bool(result["coverletter"])

    cli_art.console.rule("Sample Build Summary", style="dim")
    if resume_ok:
        cli_art.console.print(
            f"  {theme.colorize_icon('success')} Resume PDF:       {result['resume']['_output_paths']['pdf']}",
            soft_wrap=True,
        )
    else:
        cli_art.console.print(
            f"  {theme.colorize_icon('error')} Resume build failed.", soft_wrap=True
        )
    if coverletter_ok:
        cli_art.console.print(
            f"  {theme.colorize_icon('success')} Cover letter PDF: {result['coverletter']['_output_paths']['pdf']}",
            soft_wrap=True,
        )
    else:
        cli_art.console.print(
            f"  {theme.colorize_icon('error')} Cover letter build failed.",
            soft_wrap=True,
        )

    if not (resume_ok and coverletter_ok):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
