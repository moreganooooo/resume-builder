"""resume-builder CLI -- a Click skin over the existing tailor+render
pipeline (scripts/orchestrator.py). No pipeline internals live here; every
command just calls orchestrator.run_pipeline()."""

import os
import sys

import click

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import questionary

import cli_art
import orchestrator
import jd_manager
import profile_paths
import batch_evaluate
import picker
import menu
import scan as scan_module
import liveness as liveness_module
import polish as polish_module


def _should_proceed(count: int, skip_confirm: bool) -> bool:
    """Confirmation gate for anything that scores every pending JD (real
    Gemini cost, one call per JD). skip_confirm=True (the --yes flag)
    bypasses the prompt entirely."""
    if skip_confirm:
        return True
    return click.confirm(f"About to evaluate {count} pending JD(s) -- one real Gemini call each. Continue?")


@click.group(invoke_without_command=True)
@click.option("--profile", default=None, help="Override RESUME_PROFILE for this invocation only.")
@click.pass_context
def cli(ctx, profile):
    """resume-builder: tailor and render resumes per job description."""
    if profile:
        profile_paths.set_active_profile(profile)
    if ctx.invoked_subcommand is None:
        menu.run_interactive_menu()


@cli.command()
@click.argument("jd_file", type=click.Path(exists=True))
@click.option("--master", default=None, help="Path to master resume JSON (optional)")
@click.option("--output", default=None, help="Output JSON filename (optional)")
def tailor(jd_file, master, output):
    """Tailor + render a resume for a single JD file."""
    cli_art.display_banner(f"Tailoring: {jd_file}")
    completed, failed = orchestrator.run_pipeline(
        jd_path=jd_file, master_resume_path=master, output_filename=output,
    )
    if failed and not completed:
        raise SystemExit(1)


@cli.command(name="run")
@click.option("--master", default=None, help="Path to master resume JSON (optional)")
@click.option("--pick", is_flag=True, default=False, help="Interactively select which pending JD(s) to tailor")
@click.option("--yes", is_flag=True, default=False, help="Skip the confirmation prompt for --pick")
def run_batch(master, pick, yes):
    """Batch-process every pending JD in jds/."""
    if not pick:
        cli_art.display_banner("Batch run: all pending JDs")
        orchestrator.run_pipeline(master_resume_path=master)
        return

    def _process_one(path):
        completed, failed = orchestrator.run_pipeline(jd_path=path, master_resume_path=master)
        return completed > 0

    picker.pick_and_process(jd_manager.get_pending_jds(), _process_one, "tailor", skip_confirm=yes)


@cli.command()
@click.argument("jd_file", required=False, type=click.Path(exists=True))
@click.option("--pick", is_flag=True, default=False, help="Interactively select which pending JD(s) to generate a cover letter for")
@click.option("--yes", is_flag=True, default=False, help="Skip the confirmation prompt for --pick")
def coverletter(jd_file, pick, yes):
    """Generate + render a cover letter for a single JD file."""
    if pick and jd_file:
        cli_art.display_error("Pass a JD file OR --pick, not both.")
        raise SystemExit(1)
    if not pick and not jd_file:
        cli_art.display_error("Pass a JD file, or use --pick to select interactively.")
        raise SystemExit(1)

    engine = orchestrator.ResumeEngine()

    if pick:
        def _process_one(path):
            cli_art.display_banner(f"Cover letter: {path}")
            return bool(engine.build_tailored_coverletter(path))

        picker.pick_and_process(
            jd_manager.get_pending_jds(), _process_one, "generate a cover letter for", skip_confirm=yes,
        )
        return

    cli_art.display_banner(f"Cover letter: {jd_file}")
    result = engine.build_tailored_coverletter(jd_file)
    if not result:
        raise SystemExit(1)


@cli.command()
@click.argument("jd_file", required=False, type=click.Path(exists=True))
@click.option("--yes", is_flag=True, default=False, help="Skip the confirmation prompt for batch mode")
@click.option("--refresh", is_flag=True, default=False,
              help="Re-evaluate every pending JD in batch mode, even ones already scored")
def evaluate(jd_file, yes, refresh):
    """Score a JD's fit (go/no-go) without building a resume. Omit JD_FILE to evaluate every pending JD."""
    if jd_file is None:
        pending = jd_manager.get_pending_jds()
        if not pending:
            cli_art.console.print("Nothing to evaluate -- no pending JDs.")
            return

        if refresh:
            to_evaluate = pending
            already_evaluated = []
        else:
            already_evaluated, to_evaluate = batch_evaluate.split_evaluated(pending)
            if not to_evaluate:
                cli_art.console.print(
                    f"Nothing new to evaluate -- all {len(pending)} pending JD(s) already have a "
                    "score. Use --refresh to re-evaluate everything."
                )
                return

        if not _should_proceed(len(to_evaluate), yes):
            cli_art.console.print("Aborted.")
            return
        if already_evaluated:
            cli_art.console.print(f"({len(already_evaluated)} already-evaluated JD(s) will be skipped.)")

        cli_art.display_banner(f"Evaluating {len(to_evaluate)} pending JD(s)")
        results = batch_evaluate.evaluate_all_pending(to_evaluate, skip_evaluated=False)
        cli_art.render_fit_table(results)
        return

    cli_art.display_banner(f"Evaluating: {jd_file}")
    engine = orchestrator.ResumeEngine()
    with cli_art.console.status("Weighing the fit...", spinner="dots"):
        result = engine.evaluate_fit(jd_file)
    if not result:
        cli_art.display_error("Evaluation failed -- no parseable result.")
        raise SystemExit(1)
    jd_manager.save_evaluation(jd_file, result)

    scores = result.get("dimension_scores", {})
    cli_art.console.print(f"\n[bold]Archetype:[/bold] {result.get('archetype', 'unknown')}")
    cli_art.console.print(f"[bold]Composite score:[/bold] {result['composite_score']}/5")
    cli_art.console.print(f"[bold]Recommendation:[/bold] {result.get('recommendation', 'unknown')}\n")

    for dim, weight in orchestrator.FIT_DIMENSION_WEIGHTS.items():
        cli_art.console.print(f"  {dim:<22} {scores.get(dim, '-')}/5  (weight {weight:.0%})")

    blockers = result.get("hard_blockers") or []
    if blockers:
        cli_art.console.print(f"\n{cli_art.WARNING} Hard blockers:")
        for b in blockers:
            cli_art.console.print(f"  - {b}")

    cli_art.console.print(f"\n[bold]Why:[/bold] {result.get('why', '')}\n")


@cli.command(name="scan")
@click.option("--source", "sources", multiple=True, default=None,
              help="Source to scan (jobright, linkedin). Repeatable. Default: all configured sources.")
def scan_cmd(sources):
    """Scan configured sources and write new postings into jds/."""
    cli_art.display_banner("Scanning for new postings")
    scan_module.run_scan(list(sources) if sources else None)


@cli.command(name="liveness")
@click.option("--refresh", is_flag=True, default=False,
              help="Re-check every pending JD's liveness, even ones checked within the recency window")
def liveness_cmd(refresh):
    """Check every pending JD's source_url, moving expired ones to jds/expired/."""
    cli_art.display_banner("Checking posting liveness")
    liveness_module.run_liveness_check(refresh=refresh)


@cli.command()
@click.argument("file", required=False, type=click.Path(exists=True))
def polish(file):
    """Interactively polish an already-generated resume or cover letter."""
    polish_module.run(file)


@cli.command(name="help")
def help_cmd():
    """Prints the shortcuts cheat sheet (same content the interactive
    menu's Help entry shows -- see cli_art.HELP_ENTRIES)."""
    cli_art.display_help()


if __name__ == "__main__":
    cli()
