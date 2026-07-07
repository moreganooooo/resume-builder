"""
menu.py -- the interactive top-level menu launched by a bare `resume`
invocation (see cli.py's group callback). Modeled on job_automater's own
interactive() menu (job_automater/cli.py:954-1011): a while-loop
presenting a questionary.select() of every available action, dispatching
to the same underlying modules the Click commands already call, looping
back after each action until Exit (or a cancelled top-level prompt).

Each _handle_* function returns a bool: whether it did something worth
offering a "what's next" chain prompt for (see _CHAIN/_run_with_chain in
the next section of this file) -- a no-op (nothing pending, declined
confirmation, zero results) returns False and goes straight back to the
main menu instead.
"""

import questionary

import cli_art
import orchestrator
import jd_manager
import batch_evaluate
import picker
import scan as scan_module
import liveness as liveness_module
import polish as polish_module

_CHOICES = [
    questionary.Choice(title="Scan for New Postings", value="scan"),
    questionary.Choice(title="Check Posting Liveness", value="liveness"),
    questionary.Choice(title="Evaluate ALL Pending JDs", value="evaluate_all"),
    questionary.Choice(title="Evaluate a Specific JD", value="evaluate_one"),
    questionary.Choice(title="Customize Resume for ALL Pending JDs (batch)", value="tailor_all"),
    questionary.Choice(title="Customize Resume for a Specific JD", value="tailor_one"),
    questionary.Choice(title="Write cover letter for a Specific JD", value="coverletter_one"),
    questionary.Choice(title="Polish a resume or cover letter", value="polish"),
    questionary.Choice(title="Exit", value="exit"),
]


def _handle_scan() -> bool:
    written = scan_module.run_scan(None)
    return written > 0


def _handle_liveness() -> bool:
    summary = liveness_module.run_liveness_check()
    if summary.get("error"):
        return False
    checked = summary["active"] + summary["likely_active"] + summary["expired"] + summary["uncertain"]
    return checked > 0


def _handle_evaluate_all() -> bool:
    pending = jd_manager.get_pending_jds()
    if not pending:
        cli_art.console.print("Nothing to evaluate -- no pending JDs.")
        return False
    if not picker.should_proceed(len(pending), skip_confirm=False):
        cli_art.console.print("Aborted.")
        return False
    results = batch_evaluate.evaluate_all_pending(pending)
    cli_art.render_fit_table(results)
    return bool(results)


def _handle_evaluate_one() -> bool:
    path = picker.pick_one_pending_jd(jd_manager.get_pending_jds())
    if not path:
        return False
    engine = orchestrator.ResumeEngine()
    result = engine.evaluate_fit(path)
    if not result:
        cli_art.console.print(f"{cli_art.ERROR} Evaluation failed -- no parseable result.")
        return False
    jd_manager.save_evaluation(path, result)
    cli_art.console.print(f"\n[bold]Archetype:[/bold] {result.get('archetype', 'unknown')}")
    cli_art.console.print(f"[bold]Composite score:[/bold] {result['composite_score']}/5")
    cli_art.console.print(f"[bold]Recommendation:[/bold] {result.get('recommendation', 'unknown')}\n")
    return True


def _handle_tailor_all() -> bool:
    pending = jd_manager.get_pending_jds()
    if not pending:
        cli_art.console.print("Nothing to tailor -- no pending JDs.")
        return False
    if not picker.should_proceed(len(pending), skip_confirm=False, action="tailor"):
        cli_art.console.print("Aborted.")
        return False
    completed, _failed = orchestrator.run_pipeline()
    return completed > 0


def _handle_tailor_one() -> bool:
    path = picker.pick_one_evaluated_jd(jd_manager.get_pending_jds())
    if not path:
        return False
    completed, _failed = orchestrator.run_pipeline(jd_path=path)
    return completed > 0


def _handle_coverletter_one() -> bool:
    # Sources from completed JDs (a resume already built), not pending --
    # a cover letter gets written after its resume the overwhelming
    # majority of the time.
    path = picker.pick_one_pending_jd(jd_manager.get_completed_jds())
    if not path:
        return False
    engine = orchestrator.ResumeEngine()
    return bool(engine.build_tailored_coverletter(path))


def _handle_polish() -> bool:
    polish_module.run(None)
    return False


_HANDLERS = {
    "scan": _handle_scan,
    "liveness": _handle_liveness,
    "evaluate_all": _handle_evaluate_all,
    "evaluate_one": _handle_evaluate_one,
    "tailor_all": _handle_tailor_all,
    "tailor_one": _handle_tailor_one,
    "coverletter_one": _handle_coverletter_one,
    "polish": _handle_polish,
}


_CHAIN = {
    "scan": [("Check Liveness", "liveness")],
    "liveness": [("Evaluate All JDs", "evaluate_all")],
    "evaluate_all": [("Customize Resume", "tailor_all")],
    "evaluate_one": [("Customize Resume", "tailor_all")],
    "tailor_all": [("Write Cover Letter", "coverletter_one"), ("Polish with Gemini", "polish")],
    "tailor_one": [("Write Cover Letter", "coverletter_one"), ("Polish with Gemini", "polish")],
    "coverletter_one": [("Polish with Gemini", "polish")],
}


def _run_with_chain(value: str) -> None:
    did_something = _HANDLERS[value]()
    next_options = _CHAIN.get(value)
    if not did_something or not next_options:
        return

    choices = [questionary.Choice(title=label, value=v) for label, v in next_options]
    choices.append(questionary.Choice(title="Back to Menu", value="__back__"))
    cli_art.display_whats_next_panel()
    choice = questionary.select(
        "Choose one:", choices=choices, style=cli_art.QUESTIONARY_STYLE,
    ).ask()

    if not choice or choice == "__back__":
        return
    _run_with_chain(choice)


def run_interactive_menu() -> None:
    cli_art.display_main_banner()

    while True:
        cli_art.console.print()
        choice = questionary.select(
            "What would you like to do?", choices=_CHOICES, style=cli_art.QUESTIONARY_STYLE,
        ).ask()

        if choice == "exit" or not choice:
            cli_art.console.print("\n[cyan]Goodbye![/cyan]\n")
            break

        _run_with_chain(choice)
