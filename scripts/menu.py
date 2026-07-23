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

import json
import os
import subprocess
import sys

import questionary

import bootstrap_bullet_bank
import bootstrap_menu
import build_sample
import bullet_bank_menu
import cli_art
import dashboard as dashboard_module
import doctor
import followup
import git_update
import maintenance
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
    questionary.Choice(title=f"{theme.ICONS['bullet_bank']}  Update My Knowledge\n", value="update_knowledge"),
    questionary.Separator("── Discovery ──"),
    questionary.Choice(title=f"{theme.ICONS['discovery']}  Scan for New Postings", value="scan"),
    questionary.Choice(title=f"{theme.ICONS['discovery']}  Check Posting Liveness\n", value="liveness"),
    questionary.Separator("── Evaluation ──"),
    questionary.Choice(title=f"{theme.ICONS['evaluate']}  Evaluate ALL Pending Roles\n", value="evaluate_all"),
    questionary.Separator("── Build ──"),
    questionary.Choice(title=f"{theme.ICONS['build']}  Customize Resume for ALL Pending Roles (batch)", value="tailor_all"),
    questionary.Choice(title=f"{theme.ICONS['build']}  Polish a Resume or Cover Letter with Gemini\n", value="polish"),
    questionary.Separator("── Browse ──"),
    questionary.Choice(title=f"{theme.ICONS['utility']}  Browse & Manage Jobs", value="browse_jobs"),
    questionary.Choice(title=f"{theme.ICONS['evaluate']}  Career Dashboard\n", value="career_dashboard"),
    questionary.Separator("── Bullet Bank ──"),
    questionary.Choice(title=f"{theme.ICONS['bullet_bank']}  Manage Bullet Bank\n", value="bullet_bank"),
    questionary.Separator("── Maintenance ──"),
    questionary.Choice(title=f"{theme.ICONS['utility']}  Maintenance", value="maintenance"),
    questionary.Separator("── Utility ──"),
    questionary.Choice(title=f"{theme.ICONS['hint']}  Help", value="help"),
    questionary.Choice(title=f"{theme.ICONS['utility']}  Exit\n", value="exit"),
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
        cli_art.console.print(f"\nCreated profiles/{name}/. Add this to your shell profile, then restart your "
              f"shell (or run `export RESUME_PROFILE={name}` for this session only):\n")
        cli_art.console.print(f"  export RESUME_PROFILE={name}\n")
        profile_paths.set_active_profile(name)

    return bootstrap_menu.run_bootstrap_menu()


def _handle_update_knowledge() -> bool:
    """"Update My Knowledge" -- lets a returning profile (one that's
    already been through Phase 0 at least once) drop new source documents
    into the same source_documents/ folder and re-run just the parts they
    choose: the bullet bank (Phase 0 ingestion + the six-stage pipeline)
    and/or profile & background documents (Phase 0.5 -- cv.md/profile.yml/
    background guide). Phase 0 ingestion itself always runs when there are
    new files, since that's what actually processes them; --scope only
    gates what runs after it. See IDEAS_ARCHIVE.md for the full design
    writeup, including why this is safe to re-run today (most pipeline
    stages checkpoint by bullet-text content, not position)."""
    import profile_paths

    if not os.path.exists(bootstrap_bullet_bank.CHECKPOINT_PATH):
        cli_art.console.print(
            "This profile hasn't been set up yet -- use \"New User? Start Here!\" first."
        )
        return False

    source_docs_dir = os.path.join(profile_paths.kb_dir(), "bootstrap", "source_documents")
    os.makedirs(source_docs_dir, exist_ok=True)
    files = [
        f for f in os.listdir(source_docs_dir)
        if os.path.isfile(os.path.join(source_docs_dir, f))
    ]
    if not files:
        _print_source_docs_instructions(source_docs_dir)
        return False

    scope_choices = questionary.checkbox(
        f"Found {len(files)} document(s). What would you like to update with them?",
        choices=[
            questionary.Choice(title="Bullet Bank", value="bullets", checked=True),
            questionary.Choice(
                title="Profile & Background Documents (cv.md, profile.yml, background guide)",
                value="profile", checked=True,
            ),
        ],
        style=cli_art.QUESTIONARY_STYLE,
    ).ask()
    if not scope_choices:
        cli_art.console.print("Nothing selected -- nothing to update.")
        return False
    scope = "both" if len(scope_choices) == 2 else scope_choices[0]

    proceed = questionary.confirm(
        f"Ready to process {len(files)} document(s)?", default=True, style=cli_art.QUESTIONARY_STYLE,
    ).ask()
    if not proceed:
        return False

    cli_art.display_bootstrap_intro(len(files))
    script_path = os.path.join(bootstrap_bullet_bank.SCRIPT_DIR, "bootstrap_bullet_bank.py")
    result = subprocess.run([sys.executable, script_path, "--scope", scope])
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
    cli_art.console.print()
    cli_art.console.print(f"[bold]Archetype:[/bold] {evaluation.get('archetype') or 'unknown'}")
    cli_art.console.print(f"[bold]Composite score:[/bold] {evaluation.get('composite_score')}/5")
    cli_art.console.print(f"[bold]Recommendation:[/bold] {evaluation.get('recommendation') or 'unknown'}")
    cli_art.console.print()
    dimension_scores = evaluation.get("dimension_scores") or {}
    if dimension_scores:
        dims = ", ".join(f"{cli_art._FIT_DIMENSION_LABELS.get(k, k)}: {v}" for k, v in dimension_scores.items())
        cli_art.console.print(f"[bold]Dimensions:[/bold] {dims}")
    if evaluation.get("hard_blockers"):
        cli_art.console.print(f"[bold]Hard blockers:[/bold] {', '.join(evaluation['hard_blockers'])}")
    if evaluation.get("why"):
        cli_art.console.print(f"[bold]Why:[/bold] {evaluation['why']}")
    if dimension_scores or evaluation.get("hard_blockers") or evaluation.get("why"):
        cli_art.console.print()
    legitimacy = evaluation.get("posting_legitimacy")
    if legitimacy and legitimacy != "High Confidence":
        color = theme.WARNING if legitimacy == "Proceed with Caution" else theme.ERROR
        cli_art.console.print(f"[bold {color}]Posting legitimacy: {legitimacy}[/bold {color}] -- {evaluation.get('posting_legitimacy_notes', '')}")
    liveness = row.get("liveness")
    if liveness:
        cli_art.console.print(f"[bold]Last liveness check:[/bold] {liveness.get('result')} ({(liveness.get('checked_at') or '')[:10]}) -- {liveness.get('reason', '')}")
    cli_art.console.print("")


def _handle_update_application_status(row: dict) -> None:
    choices = [questionary.Choice(title=s, value=s) for s in jd_manager.APPLICATION_STATUSES]
    status = questionary.select(
        "Mark this application as:", choices=choices, style=cli_art.QUESTIONARY_STYLE,
    ).ask()
    if not status:
        return
    jd_manager.save_application_status(row["path"], status)
    row["application"] = jd_manager.read_application_status(row["path"])
    cli_art.console.print(f"Marked {row['company'] or row['path']} as {status}.")


def _handle_log_followup(row: dict) -> None:
    application = row.get("application")
    status = (application or {}).get("status") or "Applied"
    jd_manager.save_application_status(row["path"], status, log_followup=True)
    row["application"] = jd_manager.read_application_status(row["path"])
    cli_art.console.print(f"Logged a follow-up for {row['company'] or row['path']}.")


def _handle_draft_outreach(row: dict) -> None:
    try:
        with open(row["path"], "r", encoding="utf-8") as f:
            jd_data = json.load(f)
    except (json.JSONDecodeError, OSError, UnicodeDecodeError):
        jd_data = {}
    contacts = orchestrator.find_jd_contacts(jd_data) if isinstance(jd_data, dict) else []
    if not contacts:
        cli_art.console.print(
            "No real contacts found for this JD -- this only works for JobRight-sourced "
            "postings (or a personal company/school connection), and only when one was found."
        )
        return

    if len(contacts) == 1:
        contact = contacts[0]
    else:
        choice_labels = [
            questionary.Choice(title=f"{c['name']} -- {c['title'] or '?'} ({c['connection_type']})", value=i)
            for i, c in enumerate(contacts)
        ]
        picked = questionary.select("Who would you like to reach out to?", choices=choice_labels, style=cli_art.QUESTIONARY_STYLE).ask()
        if picked is None:
            return
        contact = contacts[picked]

    engine = orchestrator.ResumeEngine()
    with cli_art.console.status(f"Drafting a message to {contact['name']}...", spinner="dots"):
        message = engine.draft_outreach_message(row["path"], contact)
    if not message:
        cli_art.display_error("Couldn't draft a message -- no parseable result.")
        return

    cli_art.console.print(
        f"\n[bold]To:[/bold] {contact['name']} ({contact['title'] or '?'}, {contact['connection_type']})"
    )
    if contact.get("linkedin_url"):
        cli_art.console.print(f"[bold]Profile:[/bold] {contact['linkedin_url']}")
    cli_art.console.print(f"\n{message}\n")


def _handle_draft_followup(row: dict) -> None:
    """Only offered (see _browse_single_action) when
    followup.compute_urgency() is "overdue" -- career-ops's own spec never
    drafts for "waiting" (too soon) or "cold" (already had two with no
    response; a different action, not another message). Reuses
    find_jd_contacts() -- same real-contact-or-none logic as outreach,
    except a missing contact doesn't block drafting here, it just means a
    generically-addressed message (career-ops's own behavior: an unknown
    contact still gets a follow-up, just not a named one)."""
    application = row.get("application") or {}
    follow_up_count = application.get("follow_up_count", 0)

    try:
        with open(row["path"], "r", encoding="utf-8") as f:
            jd_data = json.load(f)
    except (json.JSONDecodeError, OSError, UnicodeDecodeError):
        jd_data = {}
    contacts = orchestrator.find_jd_contacts(jd_data) if isinstance(jd_data, dict) else []

    contact = None
    if len(contacts) == 1:
        contact = contacts[0]
    elif len(contacts) > 1:
        choice_labels = [
            questionary.Choice(title=f"{c['name']} -- {c['title'] or '?'} ({c['connection_type']})", value=i)
            for i, c in enumerate(contacts)
        ]
        choice_labels.append(questionary.Choice(title="No specific contact -- address generically", value=-1))
        picked = questionary.select(
            "Who should this follow-up be addressed to?", choices=choice_labels, style=cli_art.QUESTIONARY_STYLE,
        ).ask()
        if picked is None:
            return
        if picked != -1:
            contact = contacts[picked]

    engine = orchestrator.ResumeEngine()
    with cli_art.console.status("Drafting a follow-up message...", spinner="dots"):
        message = engine.draft_followup_message(row["path"], follow_up_count, contact)
    if not message:
        cli_art.display_error("Couldn't draft a follow-up -- no parseable result.")
        return

    cli_art.console.print(f"\n{message}\n")

    sent = questionary.confirm(
        "Did you send this?", default=False, style=cli_art.QUESTIONARY_STYLE,
    ).ask()
    if sent:
        _handle_log_followup(row)


def _browse_single_action(row: dict) -> bool:
    while True:
        action_choices = [questionary.Choice(title="View More Details", value="details")]
        if row["status"] == "Pending":
            action_choices.append(questionary.Choice(title=f"{theme.ICONS['build']}  Tailor Resume", value="tailor"))
        if row["status"] == "Completed":
            action_choices.append(questionary.Choice(title=f"{theme.ICONS['build']}  Write Cover Letter", value="coverletter"))
            action_choices.append(questionary.Choice(title="Update Application Status", value="update_status"))
            if row.get("application"):
                action_choices.append(questionary.Choice(title="Log a Follow-up Sent", value="log_followup"))
                if followup.compute_urgency(row["application"]) == "overdue":
                    action_choices.append(questionary.Choice(title="Draft Follow-Up Message", value="draft_followup"))
        action_choices.append(questionary.Choice(title="Draft Outreach Message", value="outreach"))
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
        if action == "update_status":
            _handle_update_application_status(row)
            continue
        if action == "log_followup":
            _handle_log_followup(row)
            continue
        if action == "draft_followup":
            _handle_draft_followup(row)
            continue
        if action == "outreach":
            _handle_draft_outreach(row)
            continue
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


def _handle_career_dashboard() -> bool:
    """Hands the terminal over entirely to the vendored Go dashboard
    (dashboard/) -- unlike every other handler here, this isn't
    questionary-driven; the dashboard is its own full-screen TUI that
    takes over stdio until the user quits it (`q`)."""
    success, message = dashboard_module.run()
    if not success:
        cli_art.display_error(message)
    return False


def _handle_polish() -> bool:
    polish_module.run(None)
    return False


def _handle_bullet_bank() -> bool:
    bullet_bank_menu.run_bullet_bank_menu()
    return False


def _handle_run_doctor() -> None:
    checks = doctor.run_checks()
    run_tests = questionary.confirm(
        "Also run the full test suite? (slower, ~20s)", default=True, style=cli_art.QUESTIONARY_STYLE,
    ).ask()
    test_result = doctor.run_test_suite() if run_tests else None
    cli_art.render_doctor_report(checks, test_result)
    maintenance.record_run("doctor")


def _handle_build_sample() -> None:
    """QA smoke test: builds a resume + cover letter against the permanent
    fixtures/sample_jd.txt fixture, using the exact same engine calls a
    real JD gets -- but bypassing orchestrator.run_pipeline() entirely, so
    nothing gets moved into jds/<profile>/completed/ or logged as a real
    completed application. Safe to run any time, by anyone, before ever
    touching a real JD -- exactly the point of having it."""
    result = build_sample.build_sample()
    if result["resume"] and result["coverletter"]:
        cli_art.display_success(
            f"Sample resume + cover letter built:\n"
            f"  {result['resume']['_output_paths']['pdf']}\n"
            f"  {result['coverletter']['_output_paths']['pdf']}"
        )
    else:
        cli_art.display_error("Sample build failed -- see output above for details.")


def _handle_maintenance() -> bool:
    """The general home for background/administrative tasks -- doctor
    checks today, room for more later (per Morgan's original ask) without
    needing a new top-level menu entry each time. Deliberately does NOT
    duplicate "Manage Bullet Bank"'s own already-built Ongoing Maintenance
    section (triage_needs_review.py/retire_rewrite_queue.py, done
    2026-07-15) -- that stays exactly where it is; this houses genuinely
    cross-cutting tasks that aren't bullet-bank-specific."""
    while True:
        last_run = maintenance.get_last_run("doctor")
        last_run_label = f"(last run: {last_run[:10]})" if last_run else "(never run)"
        choice = questionary.select(
            "Maintenance",
            choices=[
                questionary.Choice(title=f"Run Doctor Checks {last_run_label}", value="doctor"),
                questionary.Choice(title="Generate Sample Resume + Cover Letter (QA)", value="build_sample"),
                questionary.Choice(title="Check for GitHub Updates", value="check_updates"),
                questionary.Choice(title="Back", value="back"),
            ],
            style=cli_art.QUESTIONARY_STYLE,
        ).ask()
        if not choice or choice == "back":
            return False
        if choice == "doctor":
            _handle_run_doctor()
            continue
        if choice == "build_sample":
            _handle_build_sample()
            continue
        if choice == "check_updates":
            _handle_check_updates()
            continue


def _handle_help() -> bool:
    cli_art.display_help()
    return False


def _prompt_for_update() -> None:
    """Check for git updates and prompt the user if updates are available.
    This is called at startup before displaying the main menu."""
    if git_update.has_uncommitted_changes():
        cli_art.console.print(
            f"{cli_art.WARNING} You have uncommitted changes -- skipping update check."
        )
        return

    has_updates, message = git_update.check_for_updates()
    if not has_updates:
        return

    cli_art.console.print(f"\n{cli_art.HINT} Updates available: {message}")
    update = questionary.confirm(
        "Pull the latest changes from GitHub?",
        default=False,
        style=cli_art.QUESTIONARY_STYLE,
    ).ask()

    if update:
        success, result = git_update.pull_updates()
        if success:
            cli_art.console.print(f"{cli_art.SUCCESS} Updated successfully")
        else:
            cli_art.console.print(f"{cli_art.ERROR} Update failed: {result}")


def _handle_check_updates() -> bool:
    """Maintenance menu option to check for and apply updates."""
    if git_update.has_uncommitted_changes():
        cli_art.console.print(
            f"{cli_art.WARNING} You have uncommitted changes -- please commit or stash them first."
        )
        return False

    cli_art.console.print("\nChecking for updates...")
    has_updates, message = git_update.check_for_updates()

    if has_updates:
        cli_art.console.print(f"{cli_art.SUCCESS} Updates available: {message}")
        update = questionary.confirm(
            "Pull the latest changes?",
            default=True,
            style=cli_art.QUESTIONARY_STYLE,
        ).ask()

        if update:
            success, result = git_update.pull_updates()
            if success:
                cli_art.console.print(f"{cli_art.SUCCESS} Updated successfully\n")
                return True
            else:
                cli_art.console.print(f"{cli_art.ERROR} Update failed: {result}\n")
                return False
    else:
        cli_art.console.print(f"{cli_art.SUCCESS} {message}\n")
        return False


_HANDLERS = {
    "bootstrap": _handle_bootstrap,
    "update_knowledge": _handle_update_knowledge,
    "scan": _handle_scan,
    "liveness": _handle_liveness,
    "evaluate_all": _handle_evaluate_all,
    "tailor_all": _handle_tailor_all,
    "browse_jobs": _handle_browse_jobs,
    "career_dashboard": _handle_career_dashboard,
    "polish": _handle_polish,
    "help": _handle_help,
    "check_updates": _handle_check_updates,
    "bullet_bank": _handle_bullet_bank,
    "maintenance": _handle_maintenance,
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
    _prompt_for_update()
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
