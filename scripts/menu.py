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

import os
import subprocess
import sys

import questionary

import bootstrap_bullet_bank
import cli_art
import orchestrator
import jd_manager
import batch_evaluate
import picker
import scan as scan_module
import liveness as liveness_module
import polish as polish_module
import theme

_CHOICES = [
    questionary.Choice(title=[("class:new_user", "--> New User? Start Here!")], value="bootstrap"),
    questionary.Separator("── Discovery ──"),
    questionary.Choice(title=f"{theme.ICONS['discovery']}  Scan for New Postings", value="scan"),
    questionary.Choice(title=f"{theme.ICONS['discovery']}  Check Posting Liveness", value="liveness"),
    questionary.Separator("── Evaluation ──"),
    questionary.Choice(title=f"{theme.ICONS['evaluate']}  Evaluate ALL Pending JDs", value="evaluate_all"),
    questionary.Choice(title=f"{theme.ICONS['evaluate']}  Evaluate a Specific JD", value="evaluate_one"),
    questionary.Separator("── Build ──"),
    questionary.Choice(title=f"{theme.ICONS['build']}  Customize Resume for ALL Pending JDs (batch)", value="tailor_all"),
    questionary.Choice(title=f"{theme.ICONS['build']}  Customize Resume for a Specific JD", value="tailor_one"),
    questionary.Choice(title=f"{theme.ICONS['build']}  Write cover letter for a Specific JD", value="coverletter_one"),
    questionary.Choice(title=f"{theme.ICONS['build']}  Polish a resume or cover letter", value="polish"),
    questionary.Separator("── Utility ──"),
    questionary.Choice(title=f"{theme.ICONS['utility']}  View Application Tracker", value="view_applications"),
    questionary.Choice(title=f"{theme.ICONS['utility']}  Exit", value="exit"),
]


_SCAN_SOURCE_CHOICES = [
    questionary.Choice(title="Both (default)", value="both"),
    questionary.Choice(title="JobRight only", value="jobright"),
    questionary.Choice(title="LinkedIn only", value="linkedin"),
]


def _handle_bootstrap() -> bool:
    os.makedirs(bootstrap_bullet_bank.SOURCE_DOCS_DIR, exist_ok=True)
    files = [
        f for f in os.listdir(bootstrap_bullet_bank.SOURCE_DOCS_DIR)
        if os.path.isfile(os.path.join(bootstrap_bullet_bank.SOURCE_DOCS_DIR, f))
    ]

    if not files:
        cli_art.console.print(
            "Looks like there's nothing in the source_documents folder yet. "
            "Drop in your resume, LinkedIn export, certificates, "
            "recommendation letters, or notes — then come back and select "
            "this again when you're ready!"
        )
        return False

    proceed = questionary.confirm(
        f"Looks like you've got {len(files)} document(s) to process. Ready to get started?",
        default=True,
        style=cli_art.QUESTIONARY_STYLE,
    ).ask()
    if not proceed:
        return False

    cli_art.display_bootstrap_intro(len(files))
    script_path = os.path.join(bootstrap_bullet_bank.SCRIPT_DIR, "bootstrap_bullet_bank.py")
    result = subprocess.run([sys.executable, script_path])
    return result.returncode == 0


def _handle_scan() -> bool:
    choice = questionary.select(
        "Which source(s)?", choices=_SCAN_SOURCE_CHOICES, style=cli_art.QUESTIONARY_STYLE,
    ).ask()
    if not choice:
        return False
    sources = None if choice == "both" else [choice]
    written = scan_module.run_scan(sources)
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
    already_evaluated, to_evaluate = batch_evaluate.split_evaluated(pending)
    if not to_evaluate:
        cli_art.console.print(f"Nothing new to evaluate -- all {len(pending)} pending JD(s) already have a score.")
        return False
    if not picker.should_proceed(len(to_evaluate), skip_confirm=False):
        cli_art.console.print("Aborted.")
        return False
    if already_evaluated:
        cli_art.console.print(f"({len(already_evaluated)} already-evaluated JD(s) will be skipped.)")
    results = batch_evaluate.evaluate_all_pending(to_evaluate, skip_evaluated=False)
    cli_art.render_fit_table(results)
    return bool(results)


def _handle_evaluate_one() -> bool:
    path = picker.pick_one_pending_jd(jd_manager.get_pending_jds())
    if not path:
        return False
    engine = orchestrator.ResumeEngine()
    result = engine.evaluate_fit(path)
    if not result:
        cli_art.display_error("Evaluation failed -- no parseable result.")
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


def _handle_view_applications() -> bool:
    if not os.path.exists(jd_manager.APPLICATIONS_MD):
        cli_art.console.print("No applications tracked yet -- nothing to view.")
        return False
    with open(jd_manager.APPLICATIONS_MD, "r", encoding="utf-8") as f:
        content = f.read()
    cli_art.display_applications_tracker(content)
    return True


_HANDLERS = {
    "bootstrap": _handle_bootstrap,
    "scan": _handle_scan,
    "liveness": _handle_liveness,
    "evaluate_all": _handle_evaluate_all,
    "evaluate_one": _handle_evaluate_one,
    "tailor_all": _handle_tailor_all,
    "tailor_one": _handle_tailor_one,
    "coverletter_one": _handle_coverletter_one,
    "polish": _handle_polish,
    "view_applications": _handle_view_applications,
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

# Labels for the session-end summary -- only actions worth reporting on
# exit get an entry; anything absent here (e.g. "polish", "scan",
# "liveness") just isn't tallied.
_SESSION_LABELS = {
    "tailor_all": "resumes tailored",
    "tailor_one": "resumes tailored",
    "coverletter_one": "cover letters written",
}


def _run_with_chain(value: str, session_stats: dict) -> None:
    did_something = _HANDLERS[value]()
    if did_something:
        label = _SESSION_LABELS.get(value)
        if label:
            session_stats[label] = session_stats.get(label, 0) + 1

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
    _run_with_chain(choice, session_stats)


def _session_summary(session_stats: dict) -> str:
    if not session_stats:
        return "No actions taken this session."
    parts = [f"{count} {label}" for label, count in session_stats.items()]
    return f"{cli_art.SUCCESS} " + " · ".join(parts) + " · Nice work."


def run_interactive_menu() -> None:
    cli_art.display_main_banner()
    cli_art.display_stats_line()
    cli_art.display_tip()

    session_stats = {}
    first_loop = True

    while True:
        if first_loop:
            first_loop = False
        else:
            cli_art.display_breadcrumb()
        cli_art.console.print()
        choice = questionary.select(
            "What would you like to do?", choices=_CHOICES, style=cli_art.QUESTIONARY_STYLE,
        ).ask()

        if choice == "exit" or not choice:
            cli_art.console.print(f"\n{_session_summary(session_stats)}\n")
            break

        _run_with_chain(choice, session_stats)
