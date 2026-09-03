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
import theme


def build_sample() -> dict:
    """Runs a fresh resume + cover letter build against the fixture JD.
    Returns {"resume": {...}, "coverletter": {...}} -- each value is that
    build_tailored_*() call's own return dict ({} on failure, or the real
    data plus an _output_paths key on success)."""
    logger = logging.getLogger("resume_pipeline")
    if not logger.handlers:
        try:
            output_root = os.path.join(
                os.path.dirname(PROJECT_ROOT), "output", "morgan"
            )
            os.makedirs(output_root, exist_ok=True)
            timestamp = datetime.datetime.now().isoformat().replace(":", "-")
            log_path = os.path.join(output_root, f"pipeline_run_{timestamp}.log")
            handler = logging.FileHandler(log_path, encoding="utf-8")
            formatter = logging.Formatter(
                "%(asctime)s - %(levelname)s - %(message)s",
                datefmt="%Y-%m-%d %H:%M:%S",
            )
            handler.setFormatter(formatter)
            logger.addHandler(handler)
            logger.setLevel(logging.INFO)
            logger.info("Sample build started")
        except Exception as e:
            cli_art.detail(f"Could not initialize logging: {e}", level=cli_art.NORMAL)

    if not os.path.exists(SAMPLE_JD_PATH):
        cli_art.console.print(
            f"  {theme.colorize_icon('error')} Sample fixture not found: {SAMPLE_JD_PATH}",
            soft_wrap=True,
        )
        if logger.handlers:
            logger.error(f"Sample fixture not found: {SAMPLE_JD_PATH}")
        return {"resume": {}, "coverletter": {}}

    # Clear any leftover checkpoint so this is always a full, fresh run --
    # a stale partial checkpoint from an earlier interrupted attempt would
    # silently skip steps this is specifically meant to exercise.
    job_key = jd_manager.compute_job_key(SAMPLE_JD_PATH)
    jd_manager.delete_checkpoint(job_key)

    engine = orchestrator.ResumeEngine()

    cli_art.console.rule("Building Sample Resume", style="dim")
    resume_result = engine.build_tailored_resume(
        jd_path=SAMPLE_JD_PATH,
        master_resume={},
        job_key=job_key,
    )

    cli_art.console.rule("Building Sample Cover Letter", style="dim")
    coverletter_result = engine.build_tailored_coverletter(SAMPLE_JD_PATH)

    result = {"resume": resume_result, "coverletter": coverletter_result}
    resume_ok = bool(result["resume"])
    coverletter_ok = bool(result["coverletter"])
    if logger.handlers:
        logger.info(
            f"Sample build complete: resume={'ok' if resume_ok else 'failed'}, "
            f"coverletter={'ok' if coverletter_ok else 'failed'}"
        )
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
