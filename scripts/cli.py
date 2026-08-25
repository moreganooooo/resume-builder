"""resume-builder CLI -- a Click skin over the existing tailor+render
pipeline (scripts/orchestrator.py). No pipeline internals live here; every
command just calls orchestrator.run_pipeline()."""

import os
import sys

import click

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# MUST run before any import below: cli_art -> jd_manager resolves
# JDS_DIR = profile_paths.jds_dir() at module level, so an unresolvable
# RESUME_PROFILE would otherwise abort this process with a raw traceback
import profile_paths  # noqa: E402

if __name__ == "__main__" and not profile_paths.preflight_profile():
    sys.exit(2)

import batch_evaluate
import bootstrap_menu
import build_sample

# No `import questionary` here: this module's own prompts now go through
# cli_art.select()/confirm()/checkbox(), which own the shared style. Tests
# that need to intercept a prompt patch cli_art.questionary.* -- the module
# where the call actually happens -- rather than reaching it through a
# re-export here, which worked only because module objects are singletons.
import cli_art
import doctor
import jd_manager
import liveness as liveness_module
import maintenance
import menu
import orchestrator
import picker
import polish as polish_module
import scan as scan_module
import theme

import dashboard as dashboard_module


def _read_version() -> str:
    """Reads the `version = "..."` line from pyproject.toml directly
    rather than importlib.metadata.version("resume-builder") -- this
    project is never actually `pip install`-ed (just a plain venv +
    requirements.txt per CLAUDE.md's Setup section), so package metadata
    is never registered and that lookup would always raise
    PackageNotFoundError. Also avoids tomllib, which isn't available on
    the 3.10 floor this project still supports."""
    import re

    pyproject_path = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "pyproject.toml"
    )
    try:
        with open(pyproject_path, "r", encoding="utf-8") as f:
            match = re.search(r'^version\s*=\s*"([^"]+)"', f.read(), re.MULTILINE)
        return match.group(1) if match else "unknown"
    except OSError:
        return "unknown"


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
@click.version_option(version=_read_version(), prog_name="resume-builder")
@click.option(
    "--profile", default=None, help="Override RESUME_PROFILE for this invocation only."
)
@click.option(
    "--verbose",
    is_flag=True,
    default=False,
    help="Show debug-level log output (e.g. best-effort SQLite sync failures) that's normally suppressed.",
)
@click.pass_context
def cli(ctx, profile, verbose):
    """resume-builder: tailor and render resumes per job description."""
    if verbose:
        import logging

        logging.basicConfig(level=logging.DEBUG)
    if profile:
        profile_paths.set_active_profile(profile)
    if ctx.invoked_subcommand is None:
        menu.run_interactive_menu()


@cli.command(name="discover-employers")
@click.option(
    "--apply",
    "apply_",
    is_flag=True,
    default=False,
    help="Write the entries (default: dry run)",
)
@click.option("--limit", default=60, help="Max employers to probe")
@click.option("--search-term", default=None, help="What to search locally")
def discover_employers_cmd(apply_, limit, search_term):
    """Find local employers with public ATS boards and track them.

    Aggregators (Indeed/Adzuna/Jooble) say WHICH employers are hiring
    near you; their own text is teaser-only. This finds those employers'
    real ATS boards so scan_ats.py scrapes the full descriptions.
    """
    import discover_local_employers

    cli_art.display_banner("Discover Local Employers")
    hits = discover_local_employers.discover(limit=limit, search_term=search_term)
    path = discover_local_employers.tracked_companies_path()
    if not hits:
        cli_art.console.print(
            "\n  No new local employers with public ATS boards found.\n",
            soft_wrap=True,
        )
        return
    cli_art.console.print(
        f"\n  Found [cyan]{len(hits)}[/cyan] local employer(s) with a public board:\n",
        soft_wrap=True,
    )
    for hit in hits:
        cli_art.console.print(
            f"    {hit['name']}  [dim]{hit['provider']} · "
            f"{hit['postings']} open role(s)[/dim]",
            soft_wrap=True,
        )
    if not apply_:
        cli_art.console.print(
            "\n  Dry run -- nothing written. Re-run with --apply to track these.\n",
            soft_wrap=True,
        )
        return
    backup = discover_local_employers.append_entries(hits, path)
    cli_art.console.print(
        f"\n  {cli_art.SUCCESS} Added {len(hits)} employer(s). Backup: {backup}\n",
        soft_wrap=True,
    )


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
        jd_path=jd_file,
        master_resume_path=master,
        output_filename=output,
    )
    if failed and not completed:
        raise SystemExit(1)
    menu.offer_next_steps("tailor", jd_file=jd_file, from_cli=True)


@cli.command(name="run")
@click.option("--master", default=None, help="Path to master resume JSON (optional)")
@click.option(
    "--pick",
    is_flag=True,
    default=False,
    help="Interactively select which pending JD(s) to tailor",
)
@click.option(
    "--yes", is_flag=True, default=False, help="Skip the confirmation prompt for --pick"
)
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
            task = progress.add_task(
                f"[bold {theme.BRAND}]Processing JDs...", total=len(pending)
            )
            for i, jd_path in enumerate(pending, 1):
                company, title = jd_manager.extract_job_meta(jd_path)
                progress.update(
                    task, description=f"[{i}/{len(pending)}] {company} — {title}"
                )
                c, f = orchestrator.run_pipeline(
                    jd_path=jd_path, master_resume_path=master
                )
                completed += c
                failed += f
                progress.advance(task)

        cli_art.display_success(
            f"Batch complete: {completed} tailored, {failed} failed"
        )
        return

    def _process_one(path):
        completed, failed = orchestrator.run_pipeline(
            jd_path=path, master_resume_path=master
        )
        return completed > 0

    picker.pick_and_process(
        jd_manager.get_pending_jds(), _process_one, "tailor", skip_confirm=yes
    )


@cli.command()
@click.argument("jd_file", required=False, type=click.Path(exists=True))
@click.option(
    "--pick",
    is_flag=True,
    default=False,
    help="Interactively select which pending JD(s) to generate a cover letter for",
)
@click.option(
    "--yes", is_flag=True, default=False, help="Skip the confirmation prompt for --pick"
)
@click.option(
    "--referral",
    default=None,
    help="Referral contact for this specific application (e.g. \"Jane Doe, former coworker\") -- named in the letter's opening paragraph. Not valid with --pick, since one referral can't apply to multiple JDs.",
)
def coverletter(jd_file, pick, yes, referral):
    """Generate + render a cover letter for a single JD file."""
    if pick and jd_file:
        cli_art.display_error("Pass a JD file OR --pick, not both.")
        raise SystemExit(1)
    if not pick and not jd_file:
        cli_art.display_error("Pass a JD file, or use --pick to select interactively.")
        raise SystemExit(1)
    if pick and referral:
        cli_art.display_error(
            "--referral isn't valid with --pick -- one referral can't apply to multiple JDs."
        )
        raise SystemExit(1)

    engine = orchestrator.ResumeEngine()

    if referral:
        jd_manager.save_referral(jd_file, referral)

    if pick:

        def _process_one(path):
            cli_art.display_banner(f"Cover letter: {path}")
            return bool(engine.build_tailored_coverletter(path))

        picker.pick_and_process(
            jd_manager.get_pending_jds(),
            _process_one,
            "generate a cover letter for",
            skip_confirm=yes,
        )
        return

    cli_art.display_banner(f"Cover letter: {jd_file}")
    result = engine.build_tailored_coverletter(jd_file)
    if not result:
        raise SystemExit(1)
    menu.offer_next_steps("coverletter", jd_file=jd_file, from_cli=True)


@cli.command(name="package")
@click.argument("jd_file", required=False, type=click.Path(exists=True))
@click.option("--master", default=None, help="Path to master resume JSON (optional)")
@click.option(
    "--output", default=None, help="Output JSON filename (single-JD mode only)"
)
@click.option(
    "--referral",
    default=None,
    help='Referral contact for this specific application (e.g. "Jane Doe, VP Product")',
)
@click.option(
    "--force",
    is_flag=True,
    default=False,
    help="Proceed even if fit score recommends 'Skip'",
)
@click.option(
    "--skip-liveness",
    is_flag=True,
    default=False,
    help="Skip the posting URL liveness check",
)
@click.option(
    "--skip-fit", is_flag=True, default=False, help="Skip the fit evaluation check"
)
@click.option(
    "--pick",
    is_flag=True,
    default=False,
    help="Interactively select which pending JD(s) to package",
)
@click.option(
    "--yes",
    is_flag=True,
    default=False,
    help="Skip confirmation prompt for --pick or batch mode",
)
def package_cmd(
    jd_file, master, output, referral, force, skip_liveness, skip_fit, pick, yes
):
    """Build a complete application package (Resume + Cover Letter + DOCX/PDF) with liveness and fit gates."""
    if pick and jd_file:
        cli_art.display_error("Pass a JD file OR --pick, not both.")
        raise SystemExit(1)
    if not pick and not jd_file and referral:
        cli_art.display_error("--referral requires a specific JD file.")
        raise SystemExit(1)
    if pick and referral:
        cli_art.display_error(
            "--referral isn't valid with --pick -- one referral can't apply to multiple JDs."
        )
        raise SystemExit(1)

    if pick:
        engine = orchestrator.ResumeEngine()

        def _process_one(path):
            cli_art.display_banner(f"Packaging: {path}")
            res = engine.build_application_package(
                jd_path=path,
                master_resume=None,
                force=force,
                skip_liveness=skip_liveness,
                skip_fit=skip_fit,
                interactive=True,
            )
            if res and res.get("status") == "completed":
                cli_art.render_application_package_hud(res)
                return True
            return False

        picker.pick_and_process(
            jd_manager.get_pending_jds(),
            _process_one,
            "build a full application package for",
            skip_confirm=yes,
        )
        return

    if jd_file:
        cli_art.display_banner(f"Packaging: {jd_file}")
        completed, failed = orchestrator.run_application_package(
            jd_path=jd_file,
            master_resume_path=master,
            output_filename=output,
            referral=referral,
            force=force,
            skip_liveness=skip_liveness,
            skip_fit=skip_fit,
        )
        if failed and not completed:
            raise SystemExit(1)
        menu.offer_next_steps("package", jd_file=jd_file, from_cli=True)
        return

    # Batch run for all pending JDs
    cli_art.display_banner("Batch Application Package: all pending JDs")
    pending = jd_manager.get_pending_jds()
    if not pending:
        cli_art.console.print("Nothing to process -- no pending JDs.")
        return

    if not _should_proceed(len(pending), yes):
        cli_art.console.print("Batch packaging canceled.")
        return

    completed, failed = orchestrator.run_application_package(
        jd_path=None,
        master_resume_path=master,
        force=force,
        skip_liveness=skip_liveness,
        skip_fit=skip_fit,
    )
    cli_art.display_success(f"Batch complete: {completed} packaged, {failed} failed")


@cli.command(name="build")
@click.argument("jd_file", required=False, type=click.Path(exists=True))
@click.option("--master", default=None, help="Path to master resume JSON (optional)")
@click.option(
    "--output", default=None, help="Output JSON filename (single-JD mode only)"
)
@click.option(
    "--referral", default=None, help="Referral contact for this specific application"
)
@click.option(
    "--force",
    is_flag=True,
    default=False,
    help="Proceed even if fit score recommends 'Skip'",
)
@click.option(
    "--skip-liveness",
    is_flag=True,
    default=False,
    help="Skip the posting URL liveness check",
)
@click.option(
    "--skip-fit", is_flag=True, default=False, help="Skip the fit evaluation check"
)
@click.option(
    "--pick",
    is_flag=True,
    default=False,
    help="Interactively select which pending JD(s) to package",
)
@click.option("--yes", is_flag=True, default=False, help="Skip confirmation prompt")
@click.pass_context
def build_cmd(ctx, **kwargs):
    """Alias for 'package': build a full application package for a job."""
    ctx.invoke(package_cmd, **kwargs)


@cli.command()
@click.argument("jd_file", required=False, type=click.Path(exists=True))
@click.option(
    "--yes",
    is_flag=True,
    default=False,
    help="Skip the confirmation prompt for batch mode",
)
@click.option(
    "--refresh",
    is_flag=True,
    default=False,
    help="Re-evaluate every pending JD in batch mode, even ones already scored",
)
def evaluate(jd_file, yes, refresh):
    """Score a JD's fit (go/no-go) without building a resume. Omit JD_FILE to evaluate every pending JD."""
    if jd_file is None:
        # Files AND database-only rows. get_pending_jds() alone lists only
        # files, which is the larger half of the backlog missing.
        unevaluated_files, database_only = picker.unevaluated_roles()
        pending = jd_manager.get_pending_jds()
        if not pending and not database_only:
            cli_art.console.print("Nothing to evaluate -- no pending JDs.")
            return

        if refresh:
            to_evaluate = pending + database_only
            already_evaluated = []
        else:
            already_evaluated = [p for p in pending if p not in unevaluated_files]
            to_evaluate = unevaluated_files + database_only
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

            msg = Text(
                f"{len(already_evaluated)} already-evaluated JD(s) will be skipped"
            )
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
        cli_art.console.print(
            f"[dim]Archived to {archived_path} (Skip recommendation).[/dim]"
        )

    cli_art.console.print(
        f"\n[bold]Archetype:[/bold] {result.get('archetype', 'unknown')}"
    )
    cli_art.console.print(
        f"[bold]Composite score:[/bold] {result['composite_score']}/5"
    )
    cli_art.console.print(
        f"[bold]Fit:[/bold] {result.get('fit_score')}/5  "
        f"[bold]Interview odds:[/bold] {result.get('interview_odds_score')}/5  "
        f"[bold]Practical pursue:[/bold] {result.get('practical_pursue_score')}/5"
    )
    cli_art.console.print(
        f"[bold]Recommendation:[/bold] {result.get('recommendation', 'unknown')}\n"
    )

    for label, scores, weights in (
        ("Fit", result.get("fit_subscores", {}), orchestrator.FIT_SUBSCORE_WEIGHTS),
        (
            "Interview odds",
            result.get("interview_odds_subscores", {}),
            orchestrator.INTERVIEW_ODDS_WEIGHTS,
        ),
        (
            "Practical pursue",
            result.get("practical_pursue_subscores", {}),
            orchestrator.PRACTICAL_PURSUE_WEIGHTS,
        ),
    ):
        cli_art.console.print(f"  [bold]{label}[/bold]")
        for dim, weight in weights.items():
            cli_art.console.print(
                f"    {dim:<26} {scores.get(dim, '-')}/5  (weight {weight:.0%})"
            )

    blockers = result.get("hard_blockers") or []
    if blockers:
        cli_art.console.print(f"\n{cli_art.WARNING} Hard blockers:")
        for b in blockers:
            cli_art.console.print(f"  - {b}")

    cli_art.console.print(f"\n[bold]Why:[/bold] {result.get('why', '')}\n")
    menu.offer_next_steps("evaluate", from_cli=True)


@cli.command(name="scan")
@click.option(
    "--source",
    "sources",
    multiple=True,
    default=None,
    help="Source to scan (jobright, linkedin, boards -- public job boards like RemoteOK/TheMuse, "
    "ats -- direct-to-ATS like Greenhouse/Ashby/Lever). Repeatable. Default: all configured sources.",
)
@click.option(
    "--no-verify",
    is_flag=True,
    default=False,
    help="Skip the real-browser liveness check on newly-found postings (faster, but a posting an "
    "API/RSS feed still lists as open despite already being taken down may slip through).",
)
def scan_cmd(sources, no_verify):
    """Scan configured sources and write new postings into jds/."""
    cli_art.display_banner("Scanning for new postings")
    scan_module.run_scan(list(sources) if sources else None, verify=not no_verify)
    menu.offer_next_steps("scan", from_cli=True)


@cli.command(name="liveness")
@click.option(
    "--refresh",
    is_flag=True,
    default=False,
    help="Re-check every pending JD's liveness, even ones checked within the recency window",
)
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


@cli.group(name="location")
def location_group():
    """Manage location settings, commute radius, and company address enrichment."""
    pass


@location_group.command(name="enrich")
@click.option(
    "--all",
    "all_statuses",
    is_flag=True,
    default=False,
    help="Enrich all job statuses, not just pending",
)
@click.option(
    "--allow-search-backup",
    is_flag=True,
    default=False,
    help="Allow Gemini Search Grounding ultra-backup",
)
@click.option(
    "--limit",
    "-n",
    type=int,
    default=None,
    help="Maximum number of job postings to process",
)
def location_enrich(all_statuses, allow_search_backup, limit):
    """Enrich company work facility addresses for precise commute filtering."""
    import location_enricher

    cli_art.display_banner("Enriching Company Locations")
    statuses = (
        ["pending", "active", "applied", "interviewing"]
        if all_statuses
        else ["pending"]
    )
    results = location_enricher.enrich_profile_locations(
        statuses=statuses, allow_search_backup=allow_search_backup, limit=limit
    )
    cli_art.display_success(
        f"Enriched {results['total_processed']} jobs: {results['resolved']} resolved facility addresses "
        f"({results['search_calls_used']} search calls used)."
    )


@cli.command(name="reconcile")
@click.option(
    "--apply",
    is_flag=True,
    default=False,
    help="Apply corrections to data.db (defaults to dry-run).",
)
@click.option(
    "--profile",
    default=None,
    help="Profile name (defaults to active profile).",
)
def reconcile_cmd(apply: bool, profile: str | None):
    """Reconciles SQLite database job statuses with actual filesystem locations.

    The filesystem is the primary source of truth for job status. This command
    detects drift and syncs data.db to match directory structure.
    """
    import shutil
    from datetime import datetime

    import reconcile_jd_status

    target_profile = profile or profile_paths.active_profile()
    db_path = os.path.join(profile_paths.PROFILES_DIR, target_profile, "data.db")
    jds_dir = profile_paths.jds_dir(target_profile)

    if not os.path.exists(db_path):
        cli_art.display_error(f"No database found at {db_path}")
        raise SystemExit(1)

    if apply:
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        backup = f"{db_path}.backup-{stamp}"
        shutil.copy2(db_path, backup)
        cli_art.console.print(f"✓ Database backed up to {backup}")

    stats = reconcile_jd_status.reconcile(db_path, jds_dir, apply_changes=apply)
    verb = "Corrected" if apply else "Would correct"

    cli_art.display_banner("Job Status Reconciliation")
    cli_art.console.print(f"  Database rows:      {stats['scanned']}")
    cli_art.console.print(f"  Files on disk:      {stats['files_on_disk']}")
    cli_art.console.print(
        f"  No matching file:   {stats['no_file']} (scan-sourced rows left untouched)"
    )
    cli_art.console.print(f"  {verb}:          {stats['updates']}")

    for transition, count in stats["transitions"].most_common():
        cli_art.console.print(f"      {transition:<28} {count}")

    if apply:
        cli_art.display_success(
            "Reconciliation complete: "
            + ", ".join(f"{s}={n}" for s, n in stats["status_after"].most_common())
        )
    else:
        cli_art.console.print(
            "\n[yellow]Dry run only. Pass --apply to write corrections to database.[/yellow]"
        )


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
@click.option(
    "--skip-tests",
    is_flag=True,
    default=False,
    help="Skip the test-suite run (just the fast checks).",
)
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


@cli.command(name="stats")
@click.option(
    "--platform",
    is_flag=True,
    default=False,
    help="Show only source-platform yield breakdown.",
)
@click.option(
    "--companies",
    is_flag=True,
    default=False,
    help="Show only company concentration & agency detector.",
)
@click.option(
    "--scatter",
    is_flag=True,
    default=False,
    help="Show only bullet bank score vs. coverage scatter.",
)
@click.option(
    "--heatmap",
    is_flag=True,
    default=False,
    help="Show only bullet bank vs. market demand heatmap.",
)
@click.option(
    "--radar",
    is_flag=True,
    default=False,
    help="Show application strategy radar for top pending/evaluated jobs.",
)
@click.option(
    "--funnel",
    is_flag=True,
    default=False,
    help="Show recruitment funnel drill-down and bottleneck diagnostics.",
)
def stats_cmd(platform, companies, scatter, heatmap, radar, funnel):
    """Surfaces pipeline intelligence: source-platform yield, company concentration,

    score-vs-coverage scatter, bullet-bank market demand, strategy radar, and funnel drill-down.
    """
    import platform_analytics

    if funnel:
        import funnel_drilldown

        m = funnel_drilldown.compute_funnel_metrics()
        funnel_drilldown.render_funnel_drilldown(m)
        return

    if radar:
        import picker
        import strategy_radar

        evaluated = picker.list_all_evaluated_jds()
        if evaluated:
            top_job = evaluated[0]
            report = strategy_radar.analyze_job_strategy(top_job)
            strategy_radar.render_strategy_radar_hud(report)
        else:
            cli_art.console.print(
                "[dim]No evaluated jobs available for Strategy Radar.[/]"
            )
        return

    show_all = not (platform or companies or scatter or heatmap)

    plat_data = (
        platform_analytics.compute_source_platform_breakdown()
        if (show_all or platform)
        else None
    )
    comp_data = (
        platform_analytics.compute_company_concentration()
        if (show_all or companies)
        else None
    )
    scat_data = (
        platform_analytics.compute_score_vs_coverage_scatter()
        if (show_all or scatter)
        else None
    )
    heat_data = (
        platform_analytics.compute_bullet_bank_heatmap()
        if (show_all or heatmap)
        else None
    )

    cli_art.render_analytics_report(
        platform_stats=plat_data,
        company_stats=comp_data,
        scatter_stats=scat_data,
        heatmap_stats=heat_data,
    )


@cli.command(name="rag")
@click.argument("query", required=True)
@click.option("--top-bullets", default=5, help="Number of top bullets to retrieve.")
@click.option(
    "--top-evidence", default=3, help="Number of top evidence clusters to retrieve."
)
@click.option(
    "--top-chunks", default=3, help="Number of top document chunks to retrieve."
)
@click.option(
    "--index-docs",
    is_flag=True,
    help="Force re-indexing of knowledge base markdown documents.",
)
def rag_cmd(query, top_bullets, top_evidence, top_chunks, index_docs):
    """Semantic Vector RAG search across bullet bank, evidence guide, and knowledge docs."""
    import vector_store
    from rich.panel import Panel

    if index_docs:
        count = vector_store.index_knowledge_documents()
        cli_art.console.print(
            f"[{theme.SUCCESS}]✓ Indexed {count} knowledge document chunks.[/{theme.SUCCESS}]"
        )

    res = vector_store.query_rag(
        query,
        top_k_bullets=top_bullets,
        top_k_evidence=top_evidence,
        top_k_chunks=top_chunks,
    )

    cli_art.console.print()
    cli_art.console.print(
        Panel(
            f"[bold {theme.BRAND}]VECTOR RAG KNOWLEDGE RETRIEVAL[/]\n"
            f"[dim]Query:[/] [bold]{query}[/]",
            border_style=theme.BRAND,
            padding=(0, 2),
        )
    )

    # Document chunks
    if res.get("doc_chunks"):
        cli_art.console.print(
            f"[bold {theme.BRAND}]📑 Matched Document Chunks ({len(res['doc_chunks'])})[/]"
        )
        for ch in res["doc_chunks"]:
            source = ch.get("source_file", "Doc")
            score = ch.get("score", 0.0)
            text = ch.get("text", "")
            cli_art.console.print(
                f"  • [bold]{source}[/] [dim](chunk #{ch.get('chunk_id')}, relevance: {score:.2f})[/]\n"
                f'    [dim italic]"{text[:220]}..."[/]\n'
            )

    # Evidence clusters
    if res.get("evidence"):
        cli_art.console.print(
            f"[bold {theme.BRAND_ACCENT}]📖 Matched Evidence Clusters ({len(res['evidence'])})[/]"
        )
        for ev in res["evidence"]:
            name = ev.get("cluster", "Cluster")
            score = ev.get("score", 0.0)
            metric = ev.get("metric", "N/A")
            quote = ev.get("quote", "")
            cli_art.console.print(
                f"  • [bold]{name}[/] [dim](relevance: {score:.2f})[/]\n"
                f"    [green]Key Metric:[/] {metric}\n"
                f'    [dim italic]"{quote[:180]}..."[/]\n'
            )

    # Bullets
    if res.get("bullets"):
        cli_art.console.print(
            f"[bold {theme.BRAND}]🎯 Matched Bullet Bank Achievements ({len(res['bullets'])})[/]"
        )
        for b in res["bullets"]:
            bullet_text, role, tags, score = b
            cli_art.console.print(
                f"  • [dim][{role}][/] {bullet_text} [cyan]({score:.2f})[/]"
            )
    cli_art.console.print()


@cli.command(name="strategy")
@click.option(
    "--jd", "jd_file", default=None, help="Specific JD file path or ID to analyze."
)
def strategy_cmd(jd_file):
    """Application Strategy Radar & Situation Room tactical coaching HUD."""
    import json

    import picker
    import strategy_radar

    job_data = None
    if jd_file:
        if os.path.exists(jd_file):
            with open(jd_file, "r", encoding="utf-8") as f:
                try:
                    job_data = json.load(f)
                except Exception:
                    job_data = {
                        "raw_text": open(jd_file, "r", encoding="utf-8").read(),
                        "title": os.path.basename(jd_file),
                    }
        else:
            evaluated = picker.list_all_evaluated_jds()
            for j in evaluated:
                if str(j.get("id")) == str(jd_file) or str(
                    j.get("source_job_id")
                ) == str(jd_file):
                    job_data = j
                    break
            if not job_data:
                cli_art.display_error(f"Could not find JD matching: {jd_file}")
                return
    else:
        evaluated = picker.list_all_evaluated_jds()
        if evaluated:
            job_data = evaluated[0]
        else:
            job_data = {
                "title": "Senior Lifecycle Marketing Specialist",
                "company": "Target Enterprise",
                "url": "https://boards.greenhouse.io/target/jobs/123",
                "description": "Lifecycle email campaigns, Salesforce CRM segmentation, and VOC feedback loops.",
            }

    report = strategy_radar.analyze_job_strategy(job_data)
    strategy_radar.render_strategy_radar_hud(report)


@cli.command(name="verify-sync")
@click.option("--profile", default=None, help="Profile to verify sync environment for.")
def verify_sync_cmd(profile: str = None):
    """Verifies Syncthing directories, .stignore rules, and SQLite WAL status."""
    import verify_syncthing

    success = verify_syncthing.render_syncthing_report(profile)
    if not success:
        sys.exit(1)


@cli.group(name="evidence")
def evidence_group():
    """Multi-Type Evidence Bank commands (STAR behavioral stories & negotiation levers)."""
    pass


@evidence_group.command(name="stories")
@click.option(
    "--archetype",
    default=None,
    help="Filter by archetype (e.g., ProblemSolving, Leadership, Innovation, UnderPressure).",
)
@click.option(
    "--tag",
    default=None,
    help="Filter by tag (e.g., marketing, operations, automation).",
)
@click.option("--query", "-q", default=None, help="Lexical search query.")
@click.option("--profile", default=None, help="Profile name.")
def evidence_stories_cmd(
    archetype: str = None, tag: str = None, query: str = None, profile: str = None
):
    """Browses and searches STAR/CAR behavioral stories."""
    import evidence_bank

    stories = evidence_bank.load_behavioral_stories(profile)
    filtered = evidence_bank.filter_stories(
        stories, archetype=archetype, tag=tag, query=query
    )
    evidence_bank.render_stories_terminal(filtered)


@evidence_group.command(name="negotiate")
@click.option(
    "--category",
    default=None,
    help="Filter by category (e.g., Compensation, RemoteFlexibility, ScopeLeadership).",
)
@click.option("--query", "-q", default=None, help="Lexical search query.")
@click.option("--profile", default=None, help="Profile name.")
def evidence_negotiate_cmd(
    category: str = None, query: str = None, profile: str = None
):
    """Browses and searches negotiation levers and talking points."""
    import evidence_bank

    levers = evidence_bank.load_negotiation_levers(profile)
    filtered = evidence_bank.filter_negotiation_levers(
        levers, category=category, query=query
    )
    evidence_bank.render_negotiation_terminal(filtered)


@evidence_group.command(name="list")
@click.option("--profile", default=None, help="Profile name.")
def evidence_list_cmd(profile: str = None):
    """Displays all behavioral stories and negotiation levers in the evidence bank."""
    import evidence_bank

    stories = evidence_bank.load_behavioral_stories(profile)
    levers = evidence_bank.load_negotiation_levers(profile)
    evidence_bank.render_stories_terminal(stories)
    evidence_bank.render_negotiation_terminal(levers)


@cli.command(name="timeline")
@click.argument("job_id_or_query")
@click.option("--profile", default=None, help="Profile name.")
def timeline_cmd(job_id_or_query: str, profile: str = None):
    """Displays full lifecycle milestone timeline for a specific job application."""
    import application_timeline

    res = application_timeline.get_single_application_timeline(job_id_or_query, profile)
    if not res:
        cli_art.display_error(f"No job found matching '{job_id_or_query}'.")
        return
    application_timeline.render_application_timeline_terminal(res)


@cli.command(name="agency-view")
@click.option(
    "--filter", "agency_filter", default=None, help="Filter by staffing agency name."
)
@click.option("--profile", default=None, help="Profile name.")
def agency_view_cmd(agency_filter: str = None, profile: str = None):
    """Aggregates multi-role agency relationships and ghost rates."""
    import application_timeline

    agencies = application_timeline.get_agency_relationships(
        profile, agency_filter=agency_filter
    )
    application_timeline.render_agency_view_terminal(agencies)


@cli.command(name="scan-stream")
def scan_stream_cmd():
    """Starts interactive terminal viewport monitor reading NDJSON scan events from stdin."""
    import scan_stream

    scan_stream.run_live_monitor(sys.stdin)


@cli.command(name="funnel-drilldown")
@click.option("--profile", default=None, help="Profile to compute funnel metrics for.")
def funnel_drilldown_cmd(profile: str = None):
    """Recruitment funnel conversion drill-down and bottleneck diagnostics."""
    import funnel_drilldown

    m = funnel_drilldown.compute_funnel_metrics(profile)
    funnel_drilldown.render_funnel_drilldown(m)


@cli.command(name="compare")
@click.argument("target_a", required=True)
@click.argument("target_b", required=True)
@click.option("--profile", default=None, help="Profile name.")
def compare_cmd(target_a: str, target_b: str, profile: str = None):
    """Side-by-side comparison of two job postings / packages."""
    import job_compare

    ja = job_compare.load_job_target(target_a, profile=profile)
    jb = job_compare.load_job_target(target_b, profile=profile)
    if not ja or not jb:
        cli_art.console.print(
            f"[{theme.ERROR}]✗ Could not find both target jobs to compare. Check IDs or file paths.[/{theme.ERROR}]"
        )
        sys.exit(1)

    comp = job_compare.compare_jobs(ja, jb, profile=profile)
    job_compare.render_job_comparison(comp)


@cli.command(name="dashboard")
def dashboard_cmd():
    """Launches the career pipeline/progress dashboard (a full-screen Go
    TUI) against this profile's real tracker data."""
    success, message = dashboard_module.run()
    if not success:
        cli_art.display_error(message)
        sys.exit(1)


def _write_gemini_api_key(key_val: str) -> None:
    """Writes/replaces GEMINI_API_KEY in the active profile's .env --
    same logic menu.py's doctor auto-repair flow uses, so both paths
    stay consistent (F14)."""
    env_p = profile_paths.env_path()
    lines = []
    if os.path.exists(env_p):
        with open(env_p, "r", encoding="utf-8") as f:
            lines = f.readlines()
    replaced = False
    for i, line in enumerate(lines):
        if line.strip().startswith("GEMINI_API_KEY="):
            lines[i] = f"GEMINI_API_KEY={key_val.strip()}\n"
            replaced = True
            break
    if not replaced:
        lines.append(f"GEMINI_API_KEY={key_val.strip()}\n")
    os.makedirs(os.path.dirname(env_p), exist_ok=True)
    with open(env_p, "w", encoding="utf-8") as f:
        f.writelines(lines)


@cli.command(name="quickstart")
def quickstart_cmd():
    """One-shot setup check for a new profile/new machine: runs the same
    health checks as `resume doctor`, interactively fills in a missing
    GEMINI_API_KEY (the one step every fresh checkout actually needs a
    human for), and prints exact next-step commands for anything else
    that's still missing -- so a new user doesn't have to know CLAUDE.md's
    Setup section by heart before their first `resume run` (F14)."""
    cli_art.display_banner("Quickstart: checking your setup")
    checks = doctor.run_checks()
    cli_art.render_doctor_report(checks, None)

    api_key_check = next((c for c in checks if c["name"] == "GEMINI_API_KEY"), None)
    if api_key_check and not api_key_check["passed"]:
        cli_art.console.print()
        key_val = cli_art.text(
            "No GEMINI_API_KEY found -- enter it now to finish setup (leave blank to skip):",
        )
        if key_val and key_val.strip():
            _write_gemini_api_key(key_val)
            cli_art.display_success("GEMINI_API_KEY written -- re-checking...")
            checks = doctor.run_checks()
            cli_art.render_doctor_report(checks, None)

    remaining = [c for c in checks if not c["passed"]]
    if remaining:
        cli_art.console.print()
        cli_art.console.print(
            f"[bold {theme.WARNING}]Still needs attention:[/bold {theme.WARNING}]"
        )
        for c in remaining:
            cli_art.console.print(
                f"  • [bold]{c['name']}[/bold]: {c['fix'] or c['detail']}"
            )
    else:
        cli_art.display_success(
            "Everything checks out -- try `resume sample` to build a test resume, or `resume run` for a real one."
        )

    maintenance.record_run("doctor")


if __name__ == "__main__":
    cli()
