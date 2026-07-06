"""
menu.py -- the interactive top-level menu launched by a bare `resume`
invocation (see cli.py's group callback). Modeled on job_automater's own
interactive() menu (job_automater/cli.py:954-1011): a while-loop
presenting a questionary.select() of every available action, dispatching
to the same underlying modules the Click commands already call, looping
back after each action until Exit (or a cancelled top-level prompt).
"""

import questionary

import cli_art
import orchestrator
import jd_manager
import batch_evaluate
import picker
import scan as scan_module
import liveness as liveness_module

_CHOICES = [
    questionary.Choice(title="Scan for new postings", value="scan"),
    questionary.Choice(title="Check posting liveness", value="liveness"),
    questionary.Choice(title="Evaluate all pending JDs", value="evaluate_all"),
    questionary.Choice(title="Evaluate a specific JD", value="evaluate_one"),
    questionary.Choice(title="Tailor -- pick from list", value="tailor_pick"),
    questionary.Choice(title="Tailor ALL pending JDs (batch)", value="tailor_all"),
    questionary.Choice(title="Tailor a specific JD", value="tailor_one"),
    questionary.Choice(title="Generate cover letter -- pick from list", value="coverletter_pick"),
    questionary.Choice(title="Generate cover letter for a specific JD", value="coverletter_one"),
    questionary.Choice(title="Exit", value="exit"),
]


def _handle_scan():
    scan_module.run_scan(None)


def _handle_liveness():
    liveness_module.run_liveness_check()


def _handle_evaluate_all():
    pending = jd_manager.get_pending_jds()
    if not pending:
        cli_art.console.print("Nothing to evaluate -- no pending JDs.")
        return
    if not picker.should_proceed(len(pending), skip_confirm=False):
        cli_art.console.print("Aborted.")
        return
    results = batch_evaluate.evaluate_all_pending(pending)
    cli_art.render_fit_table(results)


def _handle_evaluate_one():
    path = questionary.path("Path to the JD file:", style=cli_art.QUESTIONARY_STYLE).ask()
    if not path:
        return
    engine = orchestrator.ResumeEngine()
    result = engine.evaluate_fit(path)
    if not result:
        cli_art.console.print(f"{cli_art.ERROR} Evaluation failed -- no parseable result.")
        return
    cli_art.console.print(f"\n[bold]Archetype:[/bold] {result.get('archetype', 'unknown')}")
    cli_art.console.print(f"[bold]Composite score:[/bold] {result['composite_score']}/5")
    cli_art.console.print(f"[bold]Recommendation:[/bold] {result.get('recommendation', 'unknown')}\n")


def _handle_tailor_pick():
    def _process_one(path):
        completed, _failed = orchestrator.run_pipeline(jd_path=path)
        return completed > 0

    picker.pick_and_process(jd_manager.get_pending_jds(), _process_one, "tailor")


def _handle_tailor_all():
    pending = jd_manager.get_pending_jds()
    if not pending:
        cli_art.console.print("Nothing to tailor -- no pending JDs.")
        return
    if not picker.should_proceed(len(pending), skip_confirm=False):
        cli_art.console.print("Aborted.")
        return
    orchestrator.run_pipeline()


def _handle_tailor_one():
    path = questionary.path("Path to the JD file:", style=cli_art.QUESTIONARY_STYLE).ask()
    if not path:
        return
    orchestrator.run_pipeline(jd_path=path)


def _handle_coverletter_pick():
    engine = orchestrator.ResumeEngine()

    def _process_one(path):
        cli_art.display_banner(f"Cover letter: {path}")
        return bool(engine.build_tailored_coverletter(path))

    picker.pick_and_process(jd_manager.get_pending_jds(), _process_one, "generate a cover letter for")


def _handle_coverletter_one():
    path = questionary.path("Path to the JD file:", style=cli_art.QUESTIONARY_STYLE).ask()
    if not path:
        return
    engine = orchestrator.ResumeEngine()
    engine.build_tailored_coverletter(path)


_HANDLERS = {
    "scan": _handle_scan,
    "liveness": _handle_liveness,
    "evaluate_all": _handle_evaluate_all,
    "evaluate_one": _handle_evaluate_one,
    "tailor_pick": _handle_tailor_pick,
    "tailor_all": _handle_tailor_all,
    "tailor_one": _handle_tailor_one,
    "coverletter_pick": _handle_coverletter_pick,
    "coverletter_one": _handle_coverletter_one,
}


def run_interactive_menu() -> None:
    cli_art.display_banner("Interactive Menu")

    while True:
        cli_art.console.print()
        choice = questionary.select(
            "What would you like to do?", choices=_CHOICES, style=cli_art.QUESTIONARY_STYLE,
        ).ask()

        if choice == "exit" or not choice:
            cli_art.console.print("\n[cyan]Goodbye![/cyan]\n")
            break

        _HANDLERS[choice]()
