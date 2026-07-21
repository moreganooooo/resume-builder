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
import bullet_bank_menu
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
    questionary.Choice(title=[("class:new_user", "--> New User? Start Here!\n")], value="bootstrap"),
    questionary.Separator("── Discovery ──"),
    questionary.Choice(title=f"{theme.ICONS['discovery']}  Scan for New Postings", value="scan"),
    questionary.Choice(title=f"{theme.ICONS['discovery']}  Check Posting Liveness\n", value="liveness"),
    questionary.Separator("── Evaluation ──"),
    questionary.Choice(title=f"{theme.ICONS['evaluate']}  Evaluate ALL Pending Roles\n", value="evaluate_all"),
    questionary.Separator("── Build ──"),
    questionary.Choice(title=f"{theme.ICONS['build']}  Customize Resume for ALL Pending Roles (batch)", value="tailor_all"),
    questionary.Choice(title=f"{theme.ICONS['build']}  Polish a Resume or Cover Letter with Gemini\n", value="polish"),
    questionary.Separator("── Browse ──"),
    questionary.Choice(title=f"{theme.ICONS['utility']}  Browse & Manage Jobs\n", value="browse_jobs"),
    questionary.Separator("── Utility ──"),
    questionary.Choice(title=f"{theme.ICONS['hint']}  Help", value="help"),
    questionary.Choice(title=f"{theme.ICONS['utility']}  Exit\n", value="exit"),
    questionary.Separator("── Bullet Bank ──"),
    questionary.Choice(title=f"{theme.ICONS['bullet_bank']}  Manage Bullet Bank", value="bullet_bank"),
]


_SCAN_SOURCE_CHOICES = [
    questionary.Choice(title=f"{theme.ICONS['discovery']}  Both (default)", value="both"),
    questionary.Choice(title=f"{theme.ICONS['discovery']}  JobRight only", value="jobright"),
    questionary.Choice(title=f"{theme.ICONS['discovery']}  LinkedIn only", value="linkedin"),
]


def _confirm_active_profile() -> None:
    """Startup gate -- always runs, so nobody silently inherits whoever's
    shell last set RESUME_PROFILE on a shared computer. A self-identified
    new person chooses between jumping into real setup now or browsing
    the menu first as a guest (see run_interactive_menu()'s guest-mode
    guard for what "browsing" actually allows)."""
    import profile_paths

    names = sorted(
        n for n in os.listdir(profile_paths.PROFILES_DIR)
        if os.path.isdir(os.path.join(profile_paths.PROFILES_DIR, n))
    )
    current = profile_paths.active_profile()
    choice = questionary.select(
        f"Who's using resume-builder? (currently: {current})",
        choices=names + ["I'm new here"],
        default=current if current in names else names[0],
        style=cli_art.QUESTIONARY_STYLE,
    ).ask()

    if choice in names:
        profile_paths.set_active_profile(choice)
        return

    # "I'm new here"
    path = questionary.select(
        "Welcome! Jump into new-user setup now, or look around the main menu first?",
        choices=["Start new user setup now", "Look around the main menu first"],
        style=cli_art.QUESTIONARY_STYLE,
    ).ask()

    if path == "Start new user setup now":
        # Signal to _handle_bootstrap() that this is genuinely a new
        # person, not Morgan's own default -- without this, RESUME_PROFILE
        # is still unset here, so active_profile() resolves to "morgan"
        # (whose profile always exists), and the name-prompt would be
        # skipped entirely, routing a real new user's documents straight
        # into Morgan's own knowledge_base/.
        os.environ["RESUME_GUEST_MODE"] = "1"
        _handle_bootstrap()
        if os.environ.get("RESUME_PROFILE"):
            os.environ.pop("RESUME_GUEST_MODE", None)
        return

    # "Look around the main menu first" -- guest mode. Deliberately does
    # NOT set RESUME_PROFILE (which would default-resolve to "morgan" and
    # silently act as her); run_interactive_menu()'s guard blocks every
    # choice except bootstrap/exit until real setup happens instead.
    os.environ["RESUME_GUEST_MODE"] = "1"


def _print_source_docs_instructions(source_docs_dir: str) -> None:
    """The proactive "here's what to do first" message for an empty
    source_documents/ folder -- shown whether this is a just-created
    profile's very first visit or a returning profile that's cleared the
    folder out again. Rich's [link=...] markup renders as a real clickable
    hyperlink in terminals that support OSC 8 (most modern ones); it
    degrades to plain unstyled text everywhere else -- either way the raw
    path/URL stays visible in the message itself, never hidden behind an
    opaque label."""
    cli_art.console.print(
        f"Go to your source folder ([link=file://{source_docs_dir}]{source_docs_dir}[/link]) "
        "and drop in any documentation related to your job search. Your current resume and "
        "LinkedIn profile (exporting your profile as a PDF is perfect -- "
        "[link=https://www.linkedin.com/help/linkedin/answer/a541960]see LinkedIn's instructions "
        "here[/link]) are a great place to start. You can also consider things like:\n\n"
        "  - Letters of recommendation\n"
        "  - Public LinkedIn recommendations\n"
        "  - Certifications\n"
        "  - Patents you own (look at you go!)\n"
        "  - Writing samples\n\n"
        "Once you're finished, restart this program and click New User again to continue!"
    )


def _handle_bootstrap() -> bool:
    import profile_paths

    try:
        current = profile_paths.active_profile()
        is_existing = os.path.isdir(os.path.join(profile_paths.PROFILES_DIR, current)) and \
            os.path.isdir(profile_paths.kb_dir(current))
    except ValueError:
        is_existing = False

    if not is_existing or os.environ.get("RESUME_GUEST_MODE"):
        # Either the active profile (whatever it resolved to) has no real
        # knowledge_base/ yet, or RESUME_GUEST_MODE marks this as a
        # self-identified new person (Task 15's gate) -- without the
        # guest-mode check, a brand-new user reaching this via "Start new
        # user setup now" would resolve to Morgan's own already-existing
        # profile (RESUME_PROFILE unset defaults to "morgan") and this
        # prompt would be skipped entirely, routing their documents into
        # her knowledge_base/ instead of a new one.
        name = questionary.text(
            "What's your name (used as your profile ID, e.g. 'dominick')?"
        ).ask()
        if not name:
            return False
        bootstrap_bullet_bank.create_new_profile(name)
        print(f"\nCreated profiles/{name}/. Add this to your shell profile, then restart your "
              f"shell (or run `export RESUME_PROFILE={name}` for this session only):\n")
        print(f"  export RESUME_PROFILE={name}\n")
        profile_paths.set_active_profile(name)

    # Recomputed fresh (not bootstrap_bullet_bank.SOURCE_DOCS_DIR) --
    # that module-level constant was resolved once at import time, before
    # a brand-new profile created above could ever change RESUME_PROFILE.
    source_docs_dir = os.path.join(profile_paths.kb_dir(), "bootstrap", "source_documents")
    os.makedirs(source_docs_dir, exist_ok=True)
    files = [
        f for f in os.listdir(source_docs_dir)
        if os.path.isfile(os.path.join(source_docs_dir, f))
    ]

    if not files:
        _print_source_docs_instructions(source_docs_dir)
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


def _print_evaluation_detail(row: dict) -> None:
    evaluation = row["evaluation"]
    cli_art.console.print(f"\n[bold]{row['company'] or '?'} -- {row['title'] or '?'}[/bold] ({row['status']})")
    cli_art.console.print(f"[bold]Archetype:[/bold] {evaluation.get('archetype') or 'unknown'}")
    cli_art.console.print(f"[bold]Composite score:[/bold] {evaluation.get('composite_score')}/5")
    cli_art.console.print(f"[bold]Recommendation:[/bold] {evaluation.get('recommendation') or 'unknown'}")
    dimension_scores = evaluation.get("dimension_scores") or {}
    if dimension_scores:
        dims = ", ".join(f"{cli_art._FIT_DIMENSION_LABELS.get(k, k)}: {v}" for k, v in dimension_scores.items())
        cli_art.console.print(f"[bold]Dimensions:[/bold] {dims}")
    if evaluation.get("hard_blockers"):
        cli_art.console.print(f"[bold]Hard blockers:[/bold] {', '.join(evaluation['hard_blockers'])}")
    if evaluation.get("why"):
        cli_art.console.print(f"[bold]Why:[/bold] {evaluation['why']}")
    legitimacy = evaluation.get("posting_legitimacy")
    if legitimacy and legitimacy != "High Confidence":
        color = theme.WARNING if legitimacy == "Proceed with Caution" else theme.ERROR
        cli_art.console.print(f"[bold {color}]Posting legitimacy: {legitimacy}[/bold {color}] -- {evaluation.get('posting_legitimacy_notes', '')}")
    liveness = row.get("liveness")
    if liveness:
        cli_art.console.print(f"[bold]Last liveness check:[/bold] {liveness.get('result')} ({(liveness.get('checked_at') or '')[:10]}) -- {liveness.get('reason', '')}")
    cli_art.console.print("")


def _browse_single_action(row: dict) -> bool:
    while True:
        action_choices = [questionary.Choice(title="View More Details", value="details")]
        if row["status"] == "Pending":
            action_choices.append(questionary.Choice(title=f"{theme.ICONS['build']}  Tailor Resume", value="tailor"))
        if row["status"] == "Completed":
            action_choices.append(questionary.Choice(title=f"{theme.ICONS['build']}  Write Cover Letter", value="coverletter"))
        action_choices.append(questionary.Choice(title=f"{theme.ICONS['utility']}  Archive", value="archive"))
        action_choices.append(questionary.Choice(title="Back", value="back"))

        action = questionary.select(
            f"{row['company'] or '?'} -- {row['title'] or '?'}: choose an action",
            choices=action_choices, style=cli_art.QUESTIONARY_STYLE,
        ).ask()

        if not action or action == "back":
            return False
        if action == "details":
            _print_evaluation_detail(row)
            continue
        if action == "tailor":
            completed, _failed = orchestrator.run_pipeline(jd_path=row["path"])
            return completed > 0
        if action == "coverletter":
            engine = orchestrator.ResumeEngine()
            return bool(engine.build_tailored_coverletter(row["path"]))
        if action == "archive":
            jd_manager.archive_jd(row["path"])
            cli_art.console.print(f"Archived {row['company'] or row['path']}.")
            return True


def _browse_bulk_action(rows: list) -> bool:
    any_pending = any(r["status"] == "Pending" for r in rows)
    all_completed = all(r["status"] == "Completed" for r in rows)

    action_choices = [questionary.Choice(title=f"{theme.ICONS['evaluate']}  Compare Selected", value="compare")]
    if any_pending:
        action_choices.append(questionary.Choice(title=f"{theme.ICONS['build']}  Tailor Resumes for Selected", value="tailor"))
    if all_completed:
        action_choices.append(questionary.Choice(title=f"{theme.ICONS['build']}  Write Cover Letters for Selected", value="coverletter"))
    action_choices.append(questionary.Choice(title=f"{theme.ICONS['utility']}  Archive Selected", value="archive"))
    action_choices.append(questionary.Choice(title="Back", value="back"))

    action = questionary.select(
        f"{len(rows)} JD(s) selected: choose an action", choices=action_choices, style=cli_art.QUESTIONARY_STYLE,
    ).ask()

    if not action or action == "back":
        return False
    if action == "compare":
        cli_art.render_comparison_table(rows)
        return True
    if action == "tailor":
        # Completed JDs already have a resume -- silently skipped rather
        # than re-tailored, matching the old single-JD picker's constraint.
        completed_count = 0
        for r in rows:
            if r["status"] != "Pending":
                continue
            completed, _failed = orchestrator.run_pipeline(jd_path=r["path"])
            completed_count += completed
        return completed_count > 0
    if action == "coverletter":
        engine = orchestrator.ResumeEngine()
        successes = sum(1 for r in rows if engine.build_tailored_coverletter(r["path"]))
        return successes > 0
    if action == "archive":
        for r in rows:
            jd_manager.archive_jd(r["path"])
        cli_art.console.print(f"Archived {len(rows)} JD(s).")
        return True


def _handle_browse_jobs() -> bool:
    selected = picker.browse_and_select_jds()
    if not selected:
        return False
    if len(selected) == 1:
        return _browse_single_action(selected[0])
    return _browse_bulk_action(selected)


def _handle_polish() -> bool:
    polish_module.run(None)
    return False


def _handle_bullet_bank() -> bool:
    bullet_bank_menu.run_bullet_bank_menu()
    return False


def _handle_help() -> bool:
    cli_art.display_help()
    return False


_HANDLERS = {
    "bootstrap": _handle_bootstrap,
    "scan": _handle_scan,
    "liveness": _handle_liveness,
    "evaluate_all": _handle_evaluate_all,
    "tailor_all": _handle_tailor_all,
    "browse_jobs": _handle_browse_jobs,
    "polish": _handle_polish,
    "help": _handle_help,
    "bullet_bank": _handle_bullet_bank,
}


_CHAIN = {
    "scan": [("Check Liveness", "liveness")],
    "liveness": [("Evaluate All JDs", "evaluate_all")],
    "evaluate_all": [("Customize Resume", "tailor_all"), ("Browse & Manage Jobs", "browse_jobs")],
    "tailor_all": [("Browse & Manage Jobs", "browse_jobs"), ("Polish with Gemini", "polish")],
}

# Same icon per destination value as _CHOICES above, so the "what's next"
# chain prompt stays visually consistent with the main menu instead of
# falling back to plain text.
_CHAIN_ICONS = {
    "liveness":     theme.ICONS["discovery"],
    "evaluate_all": theme.ICONS["evaluate"],
    "tailor_all":   theme.ICONS["build"],
    "browse_jobs":  theme.ICONS["utility"],
    "polish":       theme.ICONS["build"],
}

# Labels for the session-end summary -- only actions worth reporting on
# exit get an entry; anything absent here (e.g. "polish", "scan",
# "liveness") just isn't tallied.
_SESSION_LABELS = {
    "tailor_all": "resumes tailored",
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

    def _choice_title(label: str, value: str) -> str:
        icon = _CHAIN_ICONS.get(value)
        return f"{icon}  {label}" if icon else label

    choices = [questionary.Choice(title=_choice_title(label, v), value=v) for label, v in next_options]
    choices.append(questionary.Choice(title=f"{theme.ICONS['utility']}  Back to Menu", value="__back__"))
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
    _confirm_active_profile()
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

        if os.environ.get("RESUME_GUEST_MODE") and choice != "bootstrap":
            cli_art.console.print(
                "[yellow]Take a look around! Choose \"New User? Start Here!\" when you're "
                "ready to set up your own profile -- nothing else runs until then.[/yellow]"
            )
            continue

        _run_with_chain(choice, session_stats)

        if os.environ.get("RESUME_GUEST_MODE") and os.environ.get("RESUME_PROFILE"):
            os.environ.pop("RESUME_GUEST_MODE", None)
