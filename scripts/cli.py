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
import batch_evaluate
import scan as scan_module
import liveness as liveness_module


def _should_proceed(count: int, skip_confirm: bool) -> bool:
    """Confirmation gate for anything that scores every pending JD (real
    Gemini cost, one call per JD). skip_confirm=True (the --yes flag)
    bypasses the prompt entirely."""
    if skip_confirm:
        return True
    return click.confirm(f"About to evaluate {count} pending JD(s) -- one real Gemini call each. Continue?")


@click.group()
def cli():
    """resume-builder: tailor and render resumes per job description."""


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

    pending = jd_manager.get_pending_jds()
    if not pending:
        cli_art.console.print("Nothing to pick from -- no pending JDs.")
        return
    if not _should_proceed(len(pending), yes):
        cli_art.console.print("Aborted.")
        return

    cli_art.display_banner(f"Evaluating {len(pending)} pending JD(s) for picker")
    results = batch_evaluate.evaluate_all_pending(pending)
    valid = [r for r in results if not r["error"]]
    if not valid:
        cli_art.console.print("Nothing could be evaluated -- no picker to show.")
        return

    choices = [
        questionary.Choice(
            title=f"{r['composite_score']}/5 | {r['recommendation']} | {r['company_name']} | {r['job_title']}",
            value=r["source_file"],
        )
        for r in valid
    ]
    selected_paths = questionary.checkbox("Select JD(s) to tailor:", choices=choices).ask()
    if not selected_paths:
        cli_art.console.print("No jobs selected, nothing to do.")
        return

    completed = 0
    failed = 0
    for path in selected_paths:
        c, f = orchestrator.run_pipeline(jd_path=path, master_resume_path=master)
        completed += c
        failed += f
    cli_art.console.print(f"\nPicked batch summary: {completed} completed, {failed} failed.")


@cli.command()
@click.argument("jd_file", required=False, type=click.Path(exists=True))
@click.option("--pick", is_flag=True, default=False, help="Interactively select which pending JD(s) to generate a cover letter for")
@click.option("--yes", is_flag=True, default=False, help="Skip the confirmation prompt for --pick")
def coverletter(jd_file, pick, yes):
    """Generate + render a cover letter for a single JD file."""
    if pick and jd_file:
        cli_art.console.print(f"{cli_art.ERROR} Pass a JD file OR --pick, not both.")
        raise SystemExit(1)
    if not pick and not jd_file:
        cli_art.console.print(f"{cli_art.ERROR} Pass a JD file, or use --pick to select interactively.")
        raise SystemExit(1)

    if pick:
        pending = jd_manager.get_pending_jds()
        if not pending:
            cli_art.console.print("Nothing to pick from -- no pending JDs.")
            return
        if not _should_proceed(len(pending), yes):
            cli_art.console.print("Aborted.")
            return

        cli_art.display_banner(f"Evaluating {len(pending)} pending JD(s) for picker")
        results = batch_evaluate.evaluate_all_pending(pending)
        valid = [r for r in results if not r["error"]]
        if not valid:
            cli_art.console.print("Nothing could be evaluated -- no picker to show.")
            return

        choices = [
            questionary.Choice(
                title=f"{r['composite_score']}/5 | {r['recommendation']} | {r['company_name']} | {r['job_title']}",
                value=r["source_file"],
            )
            for r in valid
        ]
        selected_paths = questionary.checkbox("Select JD(s) to generate a cover letter for:", choices=choices).ask()
        if not selected_paths:
            cli_art.console.print("No jobs selected, nothing to do.")
            return

        engine = orchestrator.ResumeEngine()
        completed = 0
        failed = 0
        for path in selected_paths:
            cli_art.display_banner(f"Cover letter: {path}")
            result = engine.build_tailored_coverletter(path)
            if result:
                completed += 1
            else:
                failed += 1
        cli_art.console.print(f"\nPicked batch summary: {completed} completed, {failed} failed.")
        return

    cli_art.display_banner(f"Cover letter: {jd_file}")
    engine = orchestrator.ResumeEngine()
    result = engine.build_tailored_coverletter(jd_file)
    if not result:
        raise SystemExit(1)


@cli.command()
@click.argument("jd_file", required=False, type=click.Path(exists=True))
@click.option("--yes", is_flag=True, default=False, help="Skip the confirmation prompt for batch mode")
def evaluate(jd_file, yes):
    """Score a JD's fit (go/no-go) without building a resume. Omit JD_FILE to evaluate every pending JD."""
    if jd_file is None:
        pending = jd_manager.get_pending_jds()
        if not pending:
            cli_art.console.print("Nothing to evaluate -- no pending JDs.")
            return
        if not _should_proceed(len(pending), yes):
            cli_art.console.print("Aborted.")
            return

        cli_art.display_banner(f"Evaluating {len(pending)} pending JD(s)")
        results = batch_evaluate.evaluate_all_pending(pending)

        cli_art.console.print(f"\n{'#':<4}{'Score':<8}{'Rec.':<20}{'Company':<25}{'Title'}")
        for i, r in enumerate(results, 1):
            score_str = "ERROR" if r["error"] else f"{r['composite_score']}/5"
            rec_str = r["recommendation"] or "-"
            cli_art.console.print(f"{i:<4}{score_str:<8}{rec_str:<20}{r['company_name']:<25}{r['job_title']}")
        cli_art.console.print()
        return

    cli_art.display_banner(f"Evaluating: {jd_file}")
    engine = orchestrator.ResumeEngine()
    result = engine.evaluate_fit(jd_file)
    if not result:
        cli_art.console.print(f"{cli_art.ERROR} Evaluation failed -- no parseable result.")
        raise SystemExit(1)

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
def liveness_cmd():
    """Check every pending JD's source_url, moving expired ones to jds/expired/."""
    cli_art.display_banner("Checking posting liveness")
    liveness_module.run_liveness_check()


if __name__ == "__main__":
    cli()
