"""resume-builder CLI -- a Click skin over the existing tailor+render
pipeline (scripts/orchestrator.py). No pipeline internals live here; every
command just calls orchestrator.run_pipeline()."""

import os
import sys

import click

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# No `import questionary` here: this module's own prompts now go through
# cli_art.select()/confirm()/checkbox(), which own the shared style. Tests
# that need to intercept a prompt patch cli_art.questionary.* -- the module
# where the call actually happens -- rather than reaching it through a
# re-export here, which worked only because module objects are singletons.
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
import doctor
import maintenance
import dashboard as dashboard_module
import build_sample
import theme
import bootstrap_menu


def _should_proceed(count: int, skip_confirm: bool) -> bool:
    """Confirmation gate for anything that scores every pending JD (real
    Gemini cost, one call per JD). skip_confirm=True (the --yes flag)
    bypasses the prompt entirely.

    picker.should_proceed() is a deliberate standalone copy of this exact
    logic (see its own docstring for why it can't just import this
    function) -- a change here to the confirmation wording/behavior should
    be checked against that copy too, or the two prompts will drift."""
    if skip_confirm:
        return True
    return cli_art.confirm(
        f"About to evaluate {count} pending JD(s) -- one real Gemini call each. Continue?",
    )


# "What's next?" after a CLI command completes now lives in menu.py as
# offer_next_steps(..., from_cli=True) -- this used to be a separate
# implementation with its own vocabulary (Show Help/Return to Main Menu/
# Exit, no _CHAIN suggestions at all); see menu.py's offer_next_steps()
# docstring for the unification. Call sites below pass from_cli=True to
# get that flat extra-choices behavior instead of menu.py's own
# loop-back-into-the-menu shape.


@click.group(invoke_without_command=True)
@click.option("--profile", default=None, help="Override RESUME_PROFILE for this invocation only.")
@click.pass_context
def cli(ctx, profile):
    """resume-builder: tailor and render resumes per job description."""
    if profile:
        profile_paths.set_active_profile(profile)
    if ctx.invoked_subcommand is None:
        menu.run_interactive_menu()


@cli.command(name="bootstrap")
def bootstrap_cmd():
    """New-user setup: ingest source documents, draft your profile, then
    build the bullet bank -- the same "New User? Start Here!" flow the
    interactive menu offers, reachable directly without a banner detour."""
    bootstrap_menu.run_bootstrap_menu()


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
    menu.offer_next_steps("tailor", jd_file=jd_file, from_cli=True)


@cli.command(name="run")
@click.option("--master", default=None, help="Path to master resume JSON (optional)")
@click.option("--pick", is_flag=True, default=False, help="Interactively select which pending JD(s) to tailor")
@click.option("--yes", is_flag=True, default=False, help="Skip the confirmation prompt for --pick")
def run_batch(master, pick, yes):
    """Batch-process every pending JD in jds/."""
    if not pick:
        cli_art.display_banner("Batch run: all pending JDs")
        pending = jd_manager.get_pending_jds()
        if not pending:
            cli_art.console.print("Nothing to process -- no pending JDs.")
            return

        completed = 0
        failed = 0
        with cli_art.new_progress() as progress:
            task = progress.add_task(f"[bold {theme.BRAND}]Processing JDs...", total=len(pending))
            for i, jd_path in enumerate(pending, 1):
                jd = jd_manager.read_jd_json(jd_path)
                company = jd.get("company", "?")
                title = jd.get("title", "?")
                progress.update(task, description=f"[{i}/{len(pending)}] {company} — {title}")
                c, f = orchestrator.run_pipeline(jd_path=jd_path, master_resume_path=master)
                completed += c
                failed += f
                progress.advance(task)

        cli_art.display_success(f"Batch complete: {completed} tailored, {failed} failed")
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
    menu.offer_next_steps("coverletter", jd_file=jd_file, from_cli=True)


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
            # Print plain text so tests that assert on the raw substring
            # (e.g. "1 already-evaluated JD(s) will be skipped") match.
            from rich.text import Text
            msg = Text(f"{len(already_evaluated)} already-evaluated JD(s) will be skipped")
            cli_art.console.print(msg)

        cli_art.display_banner(f"Evaluating {len(to_evaluate)} pending JD(s)")
        results = batch_evaluate.evaluate_all_pending(to_evaluate, skip_evaluated=False)
        cli_art.render_fit_table(results)
        menu.offer_next_steps("evaluate", from_cli=True)
        return

    cli_art.display_banner(f"Evaluating: {jd_file}")
    engine = orchestrator.ResumeEngine()
    with cli_art.console.status("Weighing the fit...", spinner="dots"):
        result = engine.evaluate_fit(jd_file)
    if not result:
        cli_art.display_error("Evaluation failed -- no parseable result.")
        raise SystemExit(1)
    jd_manager.save_evaluation(jd_file, result)

    if result.get("recommendation") == "Skip":
        archived_path = jd_manager.archive_jd(jd_file)
        cli_art.console.print(f"[dim]Archived to {archived_path} (Skip recommendation).[/dim]")

    cli_art.console.print(f"\n[bold]Archetype:[/bold] {result.get('archetype', 'unknown')}")
    cli_art.console.print(f"[bold]Composite score:[/bold] {result['composite_score']}/5")
    cli_art.console.print(f"[bold]Fit:[/bold] {result.get('fit_score')}/5  "
                           f"[bold]Interview odds:[/bold] {result.get('interview_odds_score')}/5  "
                           f"[bold]Practical pursue:[/bold] {result.get('practical_pursue_score')}/5")
    cli_art.console.print(f"[bold]Recommendation:[/bold] {result.get('recommendation', 'unknown')}\n")

    for label, scores, weights in (
        ("Fit", result.get("fit_subscores", {}), orchestrator.FIT_SUBSCORE_WEIGHTS),
        ("Interview odds", result.get("interview_odds_subscores", {}), orchestrator.INTERVIEW_ODDS_WEIGHTS),
        ("Practical pursue", result.get("practical_pursue_subscores", {}), orchestrator.PRACTICAL_PURSUE_WEIGHTS),
    ):
        cli_art.console.print(f"  [bold]{label}[/bold]")
        for dim, weight in weights.items():
            cli_art.console.print(f"    {dim:<26} {scores.get(dim, '-')}/5  (weight {weight:.0%})")

    blockers = result.get("hard_blockers") or []
    if blockers:
        cli_art.console.print(f"\n{cli_art.WARNING} Hard blockers:")
        for b in blockers:
            cli_art.console.print(f"  - {b}")

    cli_art.console.print(f"\n[bold]Why:[/bold] {result.get('why', '')}\n")
    menu.offer_next_steps("evaluate", from_cli=True)


@cli.command(name="scan")
@click.option("--source", "sources", multiple=True, default=None,
              help="Source to scan (jobright, linkedin, boards -- public job boards like RemoteOK/TheMuse, "
                   "ats -- direct-to-ATS like Greenhouse/Ashby/Lever). Repeatable. Default: all configured sources.")
@click.option("--no-verify", is_flag=True, default=False,
              help="Skip the real-browser liveness check on newly-found postings (faster, but a posting an "
                   "API/RSS feed still lists as open despite already being taken down may slip through).")
def scan_cmd(sources, no_verify):
    """Scan configured sources and write new postings into jds/."""
    cli_art.display_banner("Scanning for new postings")
    scan_module.run_scan(list(sources) if sources else None, verify=not no_verify)
    menu.offer_next_steps("scan", from_cli=True)


@cli.command(name="liveness")
@click.option("--refresh", is_flag=True, default=False,
              help="Re-check every pending JD's liveness, even ones checked within the recency window")
def liveness_cmd(refresh):
    """Check every pending JD's source_url, moving expired ones to jds/expired/."""
    cli_art.display_banner("Checking posting liveness")
    liveness_module.run_liveness_check(refresh=refresh)
    menu.offer_next_steps("liveness", from_cli=True)


@cli.command()
@click.argument("file", required=False, type=click.Path(exists=True))
def polish(file):
    """Interactively polish an already-generated resume or cover letter."""
    polish_module.run(file)


@cli.command(name="sample")
def sample_cmd():
    """Builds a resume + cover letter against the permanent fixtures/sample_jd.txt
    fixture -- a QA smoke test for bullet writing, summary formatting, and PDF
    visual details, safe to re-run any time without touching real JD tracking."""
    cli_art.display_banner("Sample build: fixtures/sample_jd.txt")
    result = build_sample.build_sample()
    if result["resume"] and result["coverletter"]:
        cli_art.display_success(
            f"Sample resume + cover letter built:\n"
            f"  {result['resume']['_output_paths']['pdf']}\n"
            f"  {result['coverletter']['_output_paths']['pdf']}"
        )
    else:
        cli_art.display_error("Sample build failed -- see output above for details.")
        raise SystemExit(1)


@cli.command(name="help")
def help_cmd():
    """Prints the shortcuts cheat sheet (same content the interactive
    menu's Help entry shows -- see cli_art.HELP_ENTRIES)."""
    cli_art.display_help()


@cli.command(name="doctor")
@click.option("--skip-tests", is_flag=True, default=False, help="Skip the test-suite run (just the fast checks).")
def doctor_cmd(skip_tests):
    """Checks dependencies, assets, and config, then runs the test suite -- a plain-English summary with a suggested fix per problem found."""
    cli_art.display_banner("Running doctor checks")
    checks = doctor.run_checks()
    test_result = None
    if not skip_tests:
        with cli_art.console.status("Running test suite...", spinner="dots"):
            test_result = doctor.run_test_suite()
    cli_art.render_doctor_report(checks, test_result)
    maintenance.record_run("doctor")


@cli.command(name="dashboard")
def dashboard_cmd():
    """Launches the career pipeline/progress dashboard (a full-screen Go
    TUI) against this profile's real tracker data."""
    success, message = dashboard_module.run()
    if not success:
        cli_art.display_error(message)
        sys.exit(1)


if __name__ == "__main__":
    cli()
