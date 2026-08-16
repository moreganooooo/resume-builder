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

import contextlib
import json
import os
import shutil
import subprocess
import sys

import questionary

import bootstrap_bullet_bank
import bootstrap_menu
import build_sample
import bullet_bank_menu
import charm_prompt
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
import stale_sweep
import scan as scan_module
import liveness as liveness_module
import polish as polish_module
import theme
import skills_menu

def _icon_title(icon_name: str, label: str) -> list:
    """Build a questionary Choice title as [icon_tuple, text_tuple] so the
    icon renders in its theme color via prompt_toolkit's native styling."""
    return [theme.questionary_icon_tuple(icon_name), ("", f"  {label}")]


def _build_choices() -> list:
    """Built fresh on every call, not a module-level constant -- _icon_title()
    bakes the actual glyph character into each Choice.title at call time by
    reading theme.ICONS, so a module-level list would freeze whatever icon
    set was active at import time. That broke _confirm_icon_set()'s own
    promise ("the rest of the same session reflects the choice immediately")
    for exactly the Main Menu it's answered from: a user who picked Unicode
    on their very first prompt still saw Nerd Font glyphs on every menu
    render for the rest of the session, because _CHOICES had already been
    built (at import time, before that prompt ever ran) and never rebuilt.

    2026-08 menu collapse: a design audit found the previous 15 flat
    selectable items (grouped only by section separators) exceeded a
    first-time user's working memory. This is now a 7-item tree -- Find
    Jobs / Build Documents / Bullet Bank / Track & Follow Up / Settings &
    Upkeep, plus New User? Start Here! / Help / Exit -- with every leaf
    action moved into one of the category submenu builders below
    (_build_find_jobs_choices() etc.), each following this same
    build-fresh-per-call discipline for the same reason."""
    return [
        questionary.Choice(title=[("class:new_user", "--> New User? Start Here!")], value="bootstrap"),
        questionary.Separator(" "),
        questionary.Choice(title=_icon_title("discovery", "Find Jobs"), value="find_jobs"),
        questionary.Choice(title=_icon_title("build", "Build Documents"), value="build_documents"),
        questionary.Choice(title=_icon_title("bullet_bank", "Bullet Bank"), value="bullet_bank"),
        questionary.Choice(title=_icon_title("evaluate", "Track & Follow Up"), value="track_followup"),
        questionary.Choice(title=_icon_title("utility", "Settings & Upkeep"), value="settings_upkeep"),
        questionary.Separator(" "),
        questionary.Choice(title=_icon_title("hint", "Help"), value="help"),
        questionary.Choice(title=_icon_title("utility", "Exit"), value="exit"),
    ]


def _build_find_jobs_choices() -> list:
    """Built fresh per call -- see _build_choices()'s docstring for why.
    The "↳" nested-choice prefix reuses bullet_bank_menu.py's own
    optional-follow-up styling (see its _build_choices(), ~line 360) --
    the audit specifically praised that pattern for signaling "you're one
    level down from the main menu" and asked for it here too."""
    return [
        questionary.Choice(title=_icon_title("discovery", "↳ Scan for New Jobs"), value="scan"),
        questionary.Choice(title=_icon_title("discovery", "↳ Add Job Description Manually"), value="add_manual_jd"),
        questionary.Choice(title=_icon_title("discovery", "↳ Check Job Posting Liveness"), value="liveness"),
        questionary.Choice(title=_icon_title("evaluate", "↳ Evaluate Pending Roles"), value="evaluate_all"),
        questionary.Choice(title=_icon_title("utility", "↳ Archive Stale Postings"), value="stale_sweep"),
        questionary.Choice(title="Back", value="back"),
    ]


def _build_build_documents_choices() -> list:
    """Built fresh per call -- see _build_choices()'s docstring for why."""
    return [
        questionary.Choice(title=_icon_title("build", "↳ Customize Resume for Specific Role(s)"), value="tailor_pick"),
        questionary.Choice(title=_icon_title("build", "↳ Customize Resume for All Pending Roles (Batch Run)"), value="tailor_all"),
        questionary.Choice(title=_icon_title("build", "↳ Write Cover Letter for Specific Role(s)"), value="coverletter_pick"),
        questionary.Choice(title=_icon_title("build", "↳ Polish a Resume or Cover Letter With Gemini"), value="polish"),
        questionary.Choice(title="Back", value="back"),
    ]


def _build_track_followup_choices() -> list:
    """Built fresh per call -- see _build_choices()'s docstring for why."""
    return [
        questionary.Choice(title=_icon_title("utility", "↳ Browse & Manage Jobs"), value="browse_jobs"),
        questionary.Choice(title=_icon_title("evaluate", "↳ Career Dashboard"), value="career_dashboard"),
        questionary.Choice(title="Back", value="back"),
    ]


def _build_settings_upkeep_choices() -> list:
    """Built fresh per call -- see _build_choices()'s docstring for why
    (the last-run label below is itself state that can change between
    renders, same reasoning that already applied when this list lived
    inline in what was then _handle_maintenance)."""
    last_run = maintenance.get_last_run("doctor")
    last_run_label = f"(last run: {last_run[:10]})" if last_run else "(never run)"
    return [
        questionary.Choice(title=_icon_title("utility", f"↳ Run Doctor Checks {last_run_label}"), value="doctor"),
        questionary.Choice(title=_icon_title("bullet_bank", "↳ View & Manage Profile Skills"), value="manage_skills"),
        questionary.Choice(title=_icon_title("utility", "↳ Manage Scraping, Boards & Search Queries"), value="manage_scraping"),
        questionary.Choice(title=_icon_title("utility", "↳ Generate Sample Resume + Cover Letter (QA)"), value="build_sample"),
        questionary.Choice(title=_icon_title("utility", "↳ Check for GitHub Updates"), value="check_updates"),
        questionary.Choice(title=_icon_title("utility", "↳ Manage Profiles (Rename / Delete)"), value="manage_profiles"),
        questionary.Choice(title="Back", value="back"),
    ]


def _run_leaf_submenu(prompt: str, build_choices, session_stats: dict) -> None:
    """Shared loop for the three category submenus (Find Jobs, Build
    Documents, Track & Follow Up) introduced by the 2026-08 menu collapse
    -- each just dispatches straight into a real _HANDLERS leaf action,
    exactly like these entries used to fire from the old flat main menu,
    so a leaf's own "what's next" chain (_run_with_chain/offer_next_steps)
    keeps firing completely unchanged. The only difference is landing
    back in this same submenu afterward instead of the main menu -- the
    same "loop until Back" shape _handle_settings_upkeep (née
    _handle_maintenance) already used, now shared by all four category
    submenus."""
    use_alt = _should_use_alt_screen()
    while True:
        if use_alt:
            sys.stdout.write("\x1b[2J\x1b[H")
            sys.stdout.flush()
            cli_art.display_main_banner(reveal=False)
            cli_art.display_footer_commands()
            
        choice = cli_art.select(prompt, choices=build_choices())
        if not choice or choice == "back":
            return
        _run_with_chain(choice, session_stats)


def _handle_find_jobs(session_stats: dict) -> None:
    _run_leaf_submenu("Find Jobs", _build_find_jobs_choices, session_stats)


def _handle_build_documents(session_stats: dict) -> None:
    _run_leaf_submenu("Build Documents", _build_build_documents_choices, session_stats)


def _handle_track_followup(session_stats: dict) -> None:
    _run_leaf_submenu("Track & Follow Up", _build_track_followup_choices, session_stats)


# Main-menu entries that navigate into a category submenu rather than
# firing a real _HANDLERS action directly -- dispatched separately in
# run_interactive_menu() (not through _run_with_chain/_HANDLERS) because
# they need session_stats threaded through to the leaf action chosen
# inside, which a no-argument _HANDLERS callable can't accept. "Bullet
# Bank" and "Settings & Upkeep" are NOT here even though they also open a
# submenu -- both already have a real, no-argument _handle_* function
# (bullet_bank_menu.run_bullet_bank_menu() / _handle_settings_upkeep())
# that owns its own loop and never needed a leaf-level chain prompt, so
# they stay wired through _HANDLERS/_run_with_chain exactly as before.
_SUBMENUS = {
    "find_jobs": _handle_find_jobs,
    "build_documents": _handle_build_documents,
    "track_followup": _handle_track_followup,
}


def _flourish_line() -> "questionary.Separator":
    """Echoes cli_art.display_exit_footer()'s sparkle motif and full-width
    dashed rule here too, so it's visible under Exit on every menu
    render, not just after actually choosing it. Built fresh per call
    (not a _CHOICES constant) so its width tracks the terminal's actual
    current size, same reasoning as cli_art._sparkle_field().

    A real questionary.Separator, not a disabled Choice -- tried that
    first (custom title=[("class:exit_flourish", ...)] for the pink
    accent color), but questionary's choice renderer only skips the
    leading "- " marker for an actual Separator instance (isinstance
    check), never for a Choice regardless of its disabled value. Only a
    real Separator renders clean, which costs the custom color: its
    render path does "{}".format(choice.title), a plain str.format, so a
    style-tuple list would print its literal Python repr instead of
    rendering -- title has to be a plain string, picking up the
    generic "separator" class color (the same blue as the other
    "── Section ──" headers) instead of exit_flourish's pink."""
    label = "✦  resume-builder  ✦"
    # -4: rough allowance for the list's own pointer/indent prefix (see
    # cli_art._sparkle_field's docstring for the same reasoning against
    # the banner panel's border+padding overhead).
    available = max(cli_art.console.width - 4, len(label))
    pad_total = available - len(label)
    left = pad_total // 2
    right = pad_total - left
    return questionary.Separator("─" * left + label + "─" * right)


def _menu_choices() -> list:
    """_build_choices()'s result (minus "New User? Start Here!" once a profile is actually
    set up -- for a returning user it's dead weight at the top of every
    single menu render; guest mode, no real profile yet, see
    _confirm_active_profile(), always keeps it: it's the only choice that
    does anything until a real profile exists, run_interactive_menu()'s
    own guest-mode guard blocks everything else) plus the flourish, with
    a blank line above and below it for breathing room -- otherwise it
    sits flush against the bottom of the terminal, hard to notice."""
    all_choices = _build_choices()
    if os.environ.get("RESUME_GUEST_MODE") or not _profile_is_set_up():
        choices = all_choices
    else:
        choices = [c for c in all_choices if getattr(c, "value", None) != "bootstrap"]
    return choices + [questionary.Separator(" "), _flourish_line(), questionary.Separator(" ")]


def _build_scan_source_choices() -> list:
    """Built fresh per call -- see _build_choices()'s docstring for why."""
    return [
        questionary.Choice(title=_icon_title("discovery", "All (default)"), value="all"),
        questionary.Choice(title=_icon_title("discovery", "JobRight only"), value="jobright"),
        questionary.Choice(title=_icon_title("discovery", "LinkedIn only"), value="linkedin"),
        questionary.Choice(title=_icon_title("discovery", "Public job boards only (RemoteOK, TheMuse, etc.)"), value="boards"),
        questionary.Choice(title=_icon_title("discovery", "Direct-to-ATS only (Greenhouse, Ashby, Lever, etc.)"), value="ats"),
    ]


def _confirm_active_profile() -> bool:
    """Startup gate -- always runs, so nobody silently inherits whoever's
    shell last set RESUME_PROFILE on a shared computer. A self-identified
    new person chooses between jumping into real setup now or browsing
    the menu first as a guest (see run_interactive_menu()'s guest-mode
    guard for what "browsing" actually allows).

    Returns False if the user cancelled (Ctrl-C/Esc) at either prompt here,
    True otherwise -- run_interactive_menu() exits immediately on False,
    the same as Ctrl-C on the main menu's own select() does. Previously
    None from .ask() (Ctrl-C) fell through both `if`s uncaught: the first
    prompt's cancel silently became "I'm new here", and the second
    prompt's cancel silently became "Look around the main menu first"
    (guest mode) -- the one moment a user would most expect Ctrl-C to just
    quit instead routed them into onboarding/guest flows they never chose."""
    import profile_paths

    names = sorted(
        n for n in os.listdir(profile_paths.PROFILES_DIR)
        if os.path.isdir(os.path.join(profile_paths.PROFILES_DIR, n))
    )
    current = profile_paths.active_profile()
    # cli_art.select() is a thin wrapper around questionary.select().ask()
    # (bakes in QUESTIONARY_STYLE) -- it still returns raw None on Ctrl-C/
    # Esc exactly like the direct .ask() call this replaced, so the
    # `choice is None` check below (the actual Ctrl-C-fallthrough fix,
    # see this function's docstring) keeps working unchanged.
    choice = cli_art.select(
        f"Who's using resume-builder? (currently: {current})",
        choices=names + ["I'm new here", "Manage profiles..."],
        default=current if current in names else names[0],
        erase_when_done=True,
    )

    if choice == "Manage profiles...":
        _handle_manage_profiles()
        return run_profile_selector()

    if choice in names:
        profile_paths.set_active_profile(choice)
        return True

    if choice is None:
        return False

    # "I'm new here"
    path = cli_art.select(
        "Welcome! Jump into new-user setup now, or look around the main menu first?",
        choices=["Start new user setup now", "Look around the main menu first"],
    )

    if path is None:
        return False

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
        return True

    # "Look around the main menu first" -- guest mode. Deliberately does
    # NOT set RESUME_PROFILE (which would default-resolve to "morgan" and
    # silently act as her); run_interactive_menu()'s guard blocks every
    # choice except bootstrap/exit until real setup happens instead.
    os.environ["RESUME_GUEST_MODE"] = "1"
    return True


def _confirm_icon_set() -> None:
    """First-launch icon-set prompt (B33): theme.py's own import-time
    resolution already picked a reasonable default (Nerd Font in a real
    terminal, Unicode otherwise) before this ever runs -- this is what
    turns that guess into a real, permanent answer. Runs once per profile,
    ever: an explicit RESUME_BUILDER_ICONS override or an already-
    persisted choice both mean there's nothing left to ask. Must run
    after _confirm_active_profile() so the answer is saved against the
    right profile, not whatever RESUME_PROFILE defaulted to before the
    user was identified."""
    import ui_config

    if os.environ.get("RESUME_BUILDER_ICONS"):
        return
    if ui_config.get_icon_set() is not None:
        return
    if not cli_art.console.is_terminal:
        return

    nerd_row = "  ".join(theme._NERD_ICONS[k] for k in ("success", "error", "warning", "build", "bullet_bank"))
    unicode_row = "  ".join(theme._UNICODE_ICONS[k] for k in ("success", "error", "warning", "build", "bullet_bank"))
    cli_art.console.print("\nOne-time setup: which of these rows looks right in this terminal?")
    cli_art.console.print(f"  Nerd Font:  {nerd_row}")
    cli_art.console.print(f"  Unicode:    {unicode_row}")
    cli_art.console.print(
        "[dim]If the Nerd Font row shows boxes or question marks instead of icons, pick Unicode.[/dim]"
    )

    choice = cli_art.select(
        "Which one?",
        choices=[
            questionary.Choice(title="Nerd Font (the row above with the icons, if they rendered)", value="nerd"),
            questionary.Choice(title="Unicode (plain symbols, works everywhere)", value="unicode"),
        ],
    )
    if not choice:
        return

    ui_config.save_icon_set(choice)
    theme.set_icon_set(choice)


def _print_source_docs_instructions(source_docs_dir: str) -> None:
    """The proactive "here's what to do first" message for an empty
    source_documents/ folder -- shown whether this is a just-created
    profile's very first visit or a returning profile that's cleared the
    folder out again. Rich's [link=...] markup renders as a real clickable
    hyperlink in terminals that support OSC 8 (most modern ones); it
    degrades to plain unstyled text everywhere else -- either way the raw
    path/URL stays visible in the message itself, never hidden behind an
    opaque label."""
    from rich.panel import Panel
    from rich import box

    content = (
        f"Go to your source folder ([link=file://{source_docs_dir}]{source_docs_dir}[/link]) "
        "and drop in any documentation related to your job search. Your current resume and "
        "LinkedIn profile (exporting your profile as a PDF is perfect -- "
        "[link=https://www.linkedin.com/help/linkedin/answer/a541960]see LinkedIn's instructions "
        "here[/link]) are a great place to start. You can also consider things like:\n\n"
        "  ✦ Letters of recommendation\n"
        "  ✦ Public LinkedIn recommendations\n"
        "  ✦ Certifications\n"
        "  ✦ Patents you own (look at you go!)\n"
        "  ✦ Writing samples\n\n"
        "[bold]Once you're finished, restart this program and click New User again to continue![/bold]"
    )
    
    cli_art.console.print()
    cli_art.console.print(Panel(
        content,
        title=f"[bold {theme.BRAND}]Setup Instructions[/bold {theme.BRAND}]",
        border_style=theme.BRAND_ACCENT,
        box=box.ROUNDED,
        padding=(1, 2)
    ))
    cli_art.console.print()


def _profile_is_set_up(profile: str = None) -> bool:
    """Whether the active (or named) profile has a real knowledge base.

    Deliberately asks *whether* a profile exists, not *how* it came to
    exist. "Drop New Knowledge" used to gate on the presence of
    bootstrap/checkpoint.json -- evidence of having gone through the
    bootstrap wizard -- which told Morgan's own 628-bullet, 1,144-JD profile
    it hadn't been set up yet, because her knowledge base predates the
    wizard. A profile hand-assembled, restored from a Syncthing peer, or
    migrated from another machine is just as set up as a bootstrapped one.
    """
    import profile_paths

    try:
        name = profile or profile_paths.active_profile()
        return os.path.isdir(os.path.join(profile_paths.PROFILES_DIR, name)) and \
            os.path.isdir(profile_paths.kb_dir(name))
    except ValueError:
        return False


def _handle_bootstrap() -> bool:
    import profile_paths
    import shutil

    is_existing = _profile_is_set_up()

    if not is_existing or os.environ.get("RESUME_GUEST_MODE"):
        # Run the Go wizard binary that presents the new-user onboarding
        # UI if Go is installed. Otherwise, fall back to Python-native questionary.
        if shutil.which("go") is None:
            cli_art.console.print()
            cli_art.console.print(f"[{theme.BRAND}]✦ Go not found -- Falling back to terminal wizard ✦[/{theme.BRAND}]")
            
            profile_name = questionary.text(
                "Profile name (e.g., 'morgan'):",
                style=cli_art.QUESTIONARY_STYLE,
                validate=lambda text: True if text.strip() != "" else "Profile name cannot be empty."
            ).ask()
            if not profile_name:
                return False
            
            source_choice = questionary.select(
                "Source of your career data:",
                choices=["Resume PDF", "LinkedIn export (JSON)", "Manual markdown"],
                style=cli_art.QUESTIONARY_STYLE
            ).ask()
            if not source_choice:
                return False
            
            source_map = {
                "Resume PDF": "pdf",
                "LinkedIn export (JSON)": "linkedin",
                "Manual markdown": "manual"
            }
            source_choice_val = source_map[source_choice]
            
            ingest_path = ""
            if source_choice_val != "manual":
                allowed_exts = [".pdf"] if source_choice_val == "pdf" else [".json"]
                ingest_path = picker.interactive_file_picker(
                    f"Browse and select your source {source_choice_val.upper()} file:",
                    allowed_extensions=allowed_exts
                )
                if not ingest_path:
                    return False
            
            create_bullet = questionary.confirm(
                "Build the bullet-bank now?",
                default=True,
                style=cli_art.QUESTIONARY_STYLE
            ).ask()
            if create_bullet is None:
                return False
            
            data = {
                "profile_name": profile_name.strip(),
                "source_choice": source_choice_val,
                "ingest_path": ingest_path,
                "create_bullet": bool(create_bullet)
            }
        else:
            result = subprocess.run(
                ["go", "run", "./dashboard/cmd/bootstrap"],
                cwd=os.path.abspath(os.path.join(os.path.dirname(__file__), "..")),
                capture_output=True,
                text=True,
            )
            if result.returncode != 0:
                cli_art.friendly_subprocess_error(result.stderr, "starting the setup wizard")
                return False
            try:
                data = json.loads(result.stdout.strip())
            except json.JSONDecodeError as exc:
                cli_art.friendly_error(
                    exc, "reading the setup wizard's answers",
                    fix="Run `resume doctor`, then try New User Setup again.")
                return False
        
        name = data.get("profile_name")
        if name:
            bootstrap_bullet_bank.create_new_profile(name)
            profile_paths.set_active_profile(name)
            
            source_path = data.get("ingest_path")
            if source_path and os.path.exists(source_path):
                dest_dir = os.path.join(profile_paths.PROFILES_DIR, name, "knowledge_base", "bootstrap", "source_documents")
                os.makedirs(dest_dir, exist_ok=True)
                shutil.copy(source_path, dest_dir)
                cli_art.cli_info(f"Copied source document: {os.path.basename(source_path)} to your profile's source_documents folder.")
            
            if data.get("create_bullet"):
                # Automatically run express auto-pilot onboarding!
                return bootstrap_menu._run_express_setup(interactive=False)

    # Continue with the existing detailed bootstrap menu (phase selection, etc.)
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

    if not _profile_is_set_up():
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

    scope_choices = cli_art.checkbox(
        f"Found {len(files)} document(s). What would you like to update with them?",
        choices=[
            questionary.Choice(title="Bullet Bank", value="bullets", checked=True),
            questionary.Choice(
                title="Profile & Background Documents (cv.md, profile.yml, background guide)",
                value="profile", checked=True,
            ),
        ],
    )
    if not scope_choices:
        cli_art.console.print("Nothing selected -- nothing to update.")
        return False
    scope = "both" if len(scope_choices) == 2 else scope_choices[0]

    proceed = charm_prompt.confirm(
        f"Ready to process {len(files)} document(s)?", default=True,
    )
    if not proceed:
        return False

    cli_art.display_bootstrap_intro(len(files))
    script_path = os.path.join(bootstrap_bullet_bank.SCRIPT_DIR, "bootstrap_bullet_bank.py")
    result = subprocess.run([sys.executable, script_path, "--scope", scope])
    return result.returncode == 0


def _handle_scan() -> bool:
    choice = cli_art.select("Which source(s)?", choices=_build_scan_source_choices())
    if not choice:
        return False
    sources = None if choice == "all" else [choice]
    written = scan_module.run_scan(sources)
    return written > 0


def _handle_add_manual_jd() -> bool:
    """Manually add a job description by pasting the details/text directly."""
    import profile_paths
    import jd_manager
    import uuid
    import datetime
    from atomic_write import atomic_write

    cli_art.console.print()
    cli_art.console.print(f"[bold]Add Job Description Manually[/bold]")
    cli_art.console.print("Please enter the job details below:")
    cli_art.console.print()

    job_title = questionary.text(
        "Job Title:",
        style=cli_art.QUESTIONARY_STYLE,
        validate=lambda text: True if text.strip() != "" else "Job title cannot be empty."
    ).ask()
    if not job_title:
        return False

    company_name = questionary.text(
        "Company Name:",
        style=cli_art.QUESTIONARY_STYLE,
        validate=lambda text: True if text.strip() != "" else "Company name cannot be empty."
    ).ask()
    if not company_name:
        return False

    source_url = questionary.text(
        "Source URL (optional, press Enter to skip):",
        style=cli_art.QUESTIONARY_STYLE
    ).ask()
    if source_url is None:
        return False

    description = questionary.text(
        "Paste the Job Description text (Press Esc then Enter to finish):",
        multiline=True,
        style=cli_art.QUESTIONARY_STYLE,
        validate=lambda text: True if text.strip() != "" else "Job description cannot be empty."
    ).ask()
    if not description:
        return False

    # Standardize filename: company_title.json
    safe_company = "".join(c if c.isalnum() else "_" for c in company_name.strip()).lower()
    safe_title = "".join(c if c.isalnum() else "_" for c in job_title.strip()).lower()
    filename = f"{safe_company}_{safe_title}_{str(uuid.uuid4())[:8]}.json"
    
    jds_dir = profile_paths.jds_dir()
    os.makedirs(jds_dir, exist_ok=True)
    filepath = os.path.join(jds_dir, filename)

    job_data = {
        "job_title": job_title.strip(),
        "company_name": company_name.strip(),
        "source_url": source_url.strip() if source_url else "",
        "source_job_id": str(uuid.uuid4()),
        "description": description.strip(),
        "date_added": datetime.datetime.now().isoformat()
    }

    try:
        with atomic_write(filepath, "w", encoding="utf-8") as f:
            json.dump(job_data, f, indent=2)
        cli_art.cli_info(f"Successfully saved manual JD to: {filepath}")
        return True
    except Exception as e:
        cli_art.friendly_error(e, "saving manual job description")
        return False


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
    cli_art.console.print(f"[bold]Fit:[/bold] {evaluation.get('fit_score')}/5  "
                           f"[bold]Interview odds:[/bold] {evaluation.get('interview_odds_score')}/5  "
                           f"[bold]Practical pursue:[/bold] {evaluation.get('practical_pursue_score')}/5")
    cli_art.console.print(f"[bold]Recommendation:[/bold] {evaluation.get('recommendation') or 'unknown'}")
    cli_art.console.print()
    cli_art.console.rule(style=f"dim {theme.BRAND_ACCENT}")
    cli_art.console.print()
    has_dimensions = False
    for group_label, subscores_key, labels in cli_art._FIT_DIMENSION_GROUPS:
        subscores = evaluation.get(subscores_key) or {}
        if not subscores:
            continue
        has_dimensions = True
        dims = ", ".join(f"{labels.get(k, k)}: {v}" for k, v in subscores.items())
        cli_art.console.print(f"[bold]{group_label}:[/bold] {dims}")
    if evaluation.get("recruiter_read"):
        cli_art.console.print(f"[bold]Recruiter read:[/bold] {evaluation['recruiter_read']}")
    if evaluation.get("hard_blockers"):
        cli_art.console.print(f"[bold]Hard blockers:[/bold] {', '.join(evaluation['hard_blockers'])}")
    if evaluation.get("why"):
        cli_art.console.print(f"[bold]Why:[/bold] {evaluation['why']}")
    if has_dimensions or evaluation.get("hard_blockers") or evaluation.get("why"):
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
    status = cli_art.select("Mark this application as:", choices=choices)
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
        # cli_art.select() still returns raw None on cancel (not collapsed
        # the way cli_art.confirm() collapses to False), so `is None` here
        # keeps correctly distinguishing "cancelled" from a real pick of
        # index 0 (falsy but valid).
        picked = cli_art.select("Who would you like to reach out to?", choices=choice_labels)
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
        # `is None` (not falsy) -- -1 is a real, valid pick here ("address
        # generically"), and cli_art.select() still returns raw None on
        # cancel rather than collapsing it.
        picked = cli_art.select("Who should this follow-up be addressed to?", choices=choice_labels)
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

    sent = charm_prompt.confirm("Did you send this?", default=False)
    if sent:
        _handle_log_followup(row)


def _browse_single_action(row: dict) -> bool:
    while True:
        action_choices = [questionary.Choice(title="View More Details", value="details")]
        if row["status"] == "Pending":
            action_choices.append(questionary.Choice(title=_icon_title("build", "Tailor Resume"), value="tailor"))
        if row["status"] == "Completed":
            action_choices.append(questionary.Choice(title=_icon_title("build", "Write Cover Letter"), value="coverletter"))
            action_choices.append(questionary.Choice(title="Update Application Status", value="update_status"))
            if row.get("application"):
                action_choices.append(questionary.Choice(title="Log a Follow-up Sent", value="log_followup"))
                if followup.compute_urgency(row["application"]) == "overdue":
                    action_choices.append(questionary.Choice(title="Draft Follow-Up Message", value="draft_followup"))
        action_choices.append(questionary.Choice(title="Draft Outreach Message", value="outreach"))
        action_choices.append(questionary.Choice(title=_icon_title("utility", "Archive"), value="archive"))
        action_choices.append(questionary.Choice(title="Back", value="back"))

        action = cli_art.select(
            f"{row['company'] or '?'} -- {row['title'] or '?'}: choose an action",
            choices=action_choices,
        )

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
            target = row["company"] or row["path"]
            if not cli_art.confirm_destructive("Archive", target):
                continue
            jd_manager.archive_jd(row["path"])
            cli_art.console.print(f"Archived {target}.")
            return True


def _browse_bulk_action(rows: list) -> bool:
    any_pending = any(r["status"] == "Pending" for r in rows)
    all_completed = all(r["status"] == "Completed" for r in rows)

    action_choices = [questionary.Choice(title=_icon_title("evaluate", "Compare Selected"), value="compare")]
    if any_pending:
        action_choices.append(questionary.Choice(title=_icon_title("build", "Tailor Resumes for Selected"), value="tailor"))
    if all_completed:
        action_choices.append(questionary.Choice(title=_icon_title("build", "Write Cover Letters for Selected"), value="coverletter"))
    action_choices.append(questionary.Choice(title=_icon_title("utility", "Archive Selected"), value="archive"))
    action_choices.append(questionary.Choice(title="Back", value="back"))

    action = cli_art.select(f"{len(rows)} JD(s) selected: choose an action", choices=action_choices)

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
        if not cli_art.confirm_destructive("Archive", f"{len(rows)} JD(s)"):
            return False
        for r in rows:
            jd_manager.archive_jd(r["path"])
        cli_art.console.print(f"Archived {len(rows)} JD(s).")
        return True


def _handle_browse_jobs() -> bool:
    """Launch the interactive dashboard to browse, evaluate, and manage jobs.
    The dashboard provides a superior interactive experience with real-time
    actions (liveness, tailor, status updates) compared to the old CLI picker."""
    success, msg = dashboard_module.run()
    if not success:
        cli_art.cli_error(msg)
        return False
    return True


def _handle_tailor_pick() -> bool:
    """Main-menu shortcut straight into the multi-select picker, scoped
    to Pending JDs, for tailoring one or a few specific roles without
    detouring through Browse & Manage Jobs' own action submenu."""
    selected = picker.browse_and_select_jds(statuses=["Pending"])
    if not selected:
        return False
    completed_count = 0
    for row in selected:
        completed, _failed = orchestrator.run_pipeline(jd_path=row["path"])
        completed_count += completed
    return completed_count > 0


def _handle_coverletter_pick() -> bool:
    """Main-menu shortcut straight into the multi-select picker, scoped
    to Completed JDs (a resume already exists to match), for writing a
    cover letter for one or a few specific roles."""
    selected = picker.browse_and_select_jds(statuses=["Completed"])
    if not selected:
        return False
    engine = orchestrator.ResumeEngine()
    successes = sum(1 for row in selected if engine.build_tailored_coverletter(row["path"]))
    return successes > 0


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
    scroll_region_modified = False

    # Clear screen and draw the compact banner!
    sys.stdout.write("\x1b[2J\x1b[H")
    sys.stdout.flush()
    cli_art.display_compact_banner("SETTINGS & UPKEEP | DOCTOR CHECKS")

    # Draw the gorgeous execution footer static at the bottom row (row = rows)
    cli_art.display_execution_footer()

    # Set dynamic scroll region to freeze rows 1-4 (header) and the bottom row (footer)
    import shutil
    import profile_paths
    columns, rows = shutil.get_terminal_size()
    sys.stdout.write(f"\x1b[5;{rows-1}r")
    sys.stdout.write("\x1b[5;1H")
    sys.stdout.flush()
    scroll_region_modified = True

    try:
        checks = doctor.run_checks()
        run_tests = charm_prompt.confirm(
            "Also run the full test suite? (slower, ~20s)", default=True,
        )
        test_result = None
        if run_tests:
            with cli_art.console.status("Running test suite...", spinner="dots"):
                test_result = doctor.run_test_suite()
        cli_art.render_doctor_report(checks, test_result)
        maintenance.record_run("doctor")

        # Define mapping of repairable checks and their corresponding auto-repair instructions
        REPAIRABLE_CHECKS = {
            "Dashboard theme sync (Go)": {
                "description": "Regenerate the Go TUI color theme to match theme.py",
                "command": [sys.executable, "scripts/sync_dashboard_theme.py"],
            },
            "Python packages (requirements.txt)": {
                "description": "Install missing pip packages in your virtual environment",
                "func": lambda c: [sys.executable, "-m", "pip", "install"] + c["detail"].replace("missing: ", "").split(", ")
            },
            "Playwright npm package": {
                "description": "Run 'npm install' to install browser automation dependencies",
                "command": ["npm", "install"],
            },
            "Playwright Chromium browser": {
                "description": "Download and install Chromium for PDF generation",
                "command": ["npx", "playwright", "install", "chromium"],
            },
            "GEMINI_API_KEY": {
                "description": "Provide a Gemini API Key and write it to your active .env file",
                "special": "gemini_api"
            }
        }

        failed_repairs = [c for c in checks if not c["passed"] and c["name"] in REPAIRABLE_CHECKS]

        if failed_repairs:
            cli_art.console.print()
            cli_art.console.print(f"[bold {theme.WARNING}]✦  AUTO-REPAIR AVAILABLE  ✦[/bold {theme.WARNING}]")
            cli_art.console.print("The Doctor detected that some of the failed checks can be repaired automatically:")
            for c in failed_repairs:
                desc = REPAIRABLE_CHECKS[c["name"]]["description"]
                cli_art.console.print(f"  • [bold]{c['name']}[/bold]: {desc}")
            cli_art.console.print()
            
            should_repair = charm_prompt.confirm(
                "Would you like me to attempt to repair these issues automatically?",
                default=True
            )
            if should_repair:
                for c in failed_repairs:
                    cli_art.console.print(f"\n[bold {theme.INFO}]Repairing: {c['name']}...[/bold {theme.INFO}]")
                    rule = REPAIRABLE_CHECKS[c["name"]]
                    
                    if rule.get("special") == "gemini_api":
                        key_val = questionary.text(
                            "Enter your GEMINI_API_KEY:",
                            style=cli_art.QUESTIONARY_STYLE
                        ).ask()
                        if key_val:
                            env_p = profile_paths.env_path()
                            lines = []
                            if os.path.exists(env_p):
                                with open(env_p, "r", encoding="utf-8") as f:
                                    lines = f.readlines()
                            
                            replaced = False
                            for i, l in enumerate(lines):
                                if l.strip().startswith("GEMINI_API_KEY="):
                                    lines[i] = f"GEMINI_API_KEY={key_val.strip()}\n"
                                    replaced = True
                                    break
                            if not replaced:
                                lines.append(f"GEMINI_API_KEY={key_val.strip()}\n")
                            
                            with open(env_p, "w", encoding="utf-8") as f:
                                f.writelines(lines)
                            
                            cli_art.console.print(f"[{theme.SUCCESS}]✓ GEMINI_API_KEY written to {env_p}![/{theme.SUCCESS}]")
                        else:
                            cli_art.console.print(f"[{theme.ERROR}]✗ GEMINI_API_KEY setup skipped.[/{theme.ERROR}]")
                    else:
                        if "command" in rule:
                            cmd = rule["command"]
                        else:
                            cmd = rule["func"](c)
                        
                        try:
                            res = subprocess.run(cmd, cwd=profile_paths.PROJECT_ROOT, capture_output=True, text=True)
                            if res.returncode == 0:
                                cli_art.console.print(f"[{theme.SUCCESS}]✓ {c['name']} repaired successfully![/{theme.SUCCESS}]")
                            else:
                                cli_art.console.print(f"[{theme.ERROR}]✗ Repair failed for {c['name']}: {res.stderr.strip()}[/{theme.ERROR}]")
                        except Exception as err:
                            cli_art.console.print(f"[{theme.ERROR}]✗ Repair failed for {c['name']}: {err}[/{theme.ERROR}]")
                
                # Re-run checks to verify repairs!
                cli_art.console.print(f"\n[bold {theme.INFO}]Re-running Doctor checks to verify repairs...[/bold {theme.INFO}]")
                checks = doctor.run_checks()
                cli_art.render_doctor_report(checks, test_result)

    finally:
        if scroll_region_modified:
            sys.stdout.write("\x1b[r")
            sys.stdout.flush()
    _pause_and_return()


def _handle_build_sample() -> None:
    """QA smoke test: builds a resume + cover letter against the permanent
    fixtures/sample_jd.txt fixture, using the exact same engine calls a
    real JD gets -- but bypassing orchestrator.run_pipeline() entirely, so
    nothing gets moved into jds/<profile>/completed/ or logged as a real
    completed application. Safe to run any time, by anyone, before ever
    touching a real JD -- exactly the point of having it."""
    scroll_region_modified = False

    # Clear screen and draw the compact banner!
    sys.stdout.write("\x1b[2J\x1b[H")
    sys.stdout.flush()
    cli_art.display_compact_banner("SETTINGS & UPKEEP | BUILD SAMPLE")

    # Draw the gorgeous execution footer static at the bottom row (row = rows)
    cli_art.display_execution_footer()

    # Set dynamic scroll region to freeze rows 1-4 (header) and the bottom row (footer)
    import shutil
    columns, rows = shutil.get_terminal_size()
    sys.stdout.write(f"\x1b[5;{rows-1}r")
    sys.stdout.write("\x1b[5;1H")
    sys.stdout.flush()
    scroll_region_modified = True

    try:
        result = build_sample.build_sample()
        if result["resume"] and result["coverletter"]:
            cli_art.display_success(
                f"Sample resume + cover letter built:\n"
                f"  {result['resume']['_output_paths']['pdf']}\n"
                f"  {result['coverletter']['_output_paths']['pdf']}"
            )
        else:
            cli_art.display_error("Sample build failed -- see output above for details.")
    finally:
        if scroll_region_modified:
            sys.stdout.write("\x1b[r")
            sys.stdout.flush()
    _pause_and_return()


def _handle_settings_upkeep() -> bool:
    """Settings & Upkeep -- the general home for background/administrative
    tasks (renamed from "Maintenance" in the 2026-08 menu collapse; same
    function, same loop-until-Back shape) -- doctor checks today, room
    for more later (per Morgan's original ask) without needing a new
    top-level menu entry each time. Deliberately does NOT duplicate
    "Manage Bullet Bank"'s own already-built Ongoing Maintenance section
    (triage_needs_review.py/retire_rewrite_queue.py, done 2026-07-15) --
    that stays exactly where it is; this houses genuinely cross-cutting
    tasks that aren't bullet-bank-specific."""
    use_alt = _should_use_alt_screen()
    while True:
        if use_alt:
            sys.stdout.write("\x1b[2J\x1b[H")
            sys.stdout.flush()
            cli_art.display_compact_banner("SETTINGS & UPKEEP")
            cli_art.display_footer_commands()
            cli_art.console.print()

        choice = cli_art.select("Settings & Upkeep", choices=_build_settings_upkeep_choices())
        if not choice or choice == "back":
            return False
        if choice == "doctor":
            _handle_run_doctor()
            continue
        if choice == "manage_skills":
            skills_menu.run_skills_menu()
            continue
        if choice == "manage_scraping":
            _handle_manage_scraping()
            continue
        if choice == "build_sample":
            _handle_build_sample()
            continue
        if choice == "check_updates":
            _handle_check_updates()
            continue
        if choice == "manage_profiles":
            _handle_manage_profiles()
            continue


def _handle_manage_scraping():
    import yaml
    import profile_paths
    
    use_alt = _should_use_alt_screen()
    profile = profile_paths.active_profile()
    
    filters_path = os.path.join(profile_paths.board_scanner_dir(profile), "scan_filters.yml")
    profile_path = os.path.join(profile_paths.profile_dir(profile), "profile.yml")
    
    while True:
        if use_alt:
            sys.stdout.write("\x1b[2J\x1b[H")
            sys.stdout.flush()
            cli_art.display_compact_banner("MANAGE SCRAPING, BOARDS & QUERIES")
            cli_art.display_footer_commands()
            cli_art.console.print()
            
        choices = [
            questionary.Choice("🔌 Toggle Active Job Boards (Enable/Disable)", value="toggle_boards"),
            questionary.Choice("➕ Add Custom RSS Job Board Feed", value="add_board"),
            questionary.Choice("➖ Delete/Remove Custom RSS Job Board Feed", value="delete_board"),
            questionary.Choice("🔍 Edit LinkedIn Boolean Search Queries", value="linkedin_queries"),
            questionary.Choice("🎯 Edit Title Keyword Filters (Positive/Negative)", value="title_filters"),
            questionary.Choice("Back", value="back")
        ]
        
        choice = cli_art.select("Manage Scraping & Filters:", choices=choices)
        if not choice or choice == "back":
            return
            
        if choice == "toggle_boards":
            _handle_toggle_boards(filters_path)
            continue
        if choice == "add_board":
            _handle_add_custom_board(filters_path)
            continue
        if choice == "delete_board":
            _handle_delete_custom_board(filters_path)
            continue
        if choice == "linkedin_queries":
            _handle_edit_linkedin_queries(profile_path)
            continue
        if choice == "title_filters":
            _handle_edit_title_filters(filters_path)
            continue


def _handle_toggle_boards(filters_path):
    import yaml
    import scan_boards
    
    with open(filters_path, "r", encoding="utf-8") as f:
        filters = yaml.safe_load(f) or {}
        
    enabled_boards = filters.get("enabled_boards")
    if enabled_boards is None:
        enabled_boards = list(scan_boards.BOARD_PROVIDERS)
        
    choices = []
    for b in scan_boards.BOARD_PROVIDERS:
        name = cli_art.format_board_name(b)
        choices.append(questionary.Choice(name, value=b, checked=b in enabled_boards))
        
    selected = questionary.checkbox(
        "Select active job boards (Space to check/uncheck):",
        choices=choices,
        style=cli_art.QUESTIONARY_STYLE
    ).ask()
    
    if selected is None:
        return
        
    filters["enabled_boards"] = list(selected)
    with open(filters_path, "w", encoding="utf-8") as f:
        yaml.safe_dump(filters, f, default_flow_style=False, allow_unicode=True)
        
    cli_art.cli_info("Active job boards updated successfully!")
    _pause_and_return()


def _handle_add_custom_board(filters_path):
    import yaml
    
    with open(filters_path, "r", encoding="utf-8") as f:
        filters = yaml.safe_load(f) or {}
        
    custom_feeds = filters.get("custom_feeds") or []
    
    feed_name = questionary.text(
        "Enter custom board name (e.g., 'Golang Jobs'):",
        style=cli_art.QUESTIONARY_STYLE,
        validate=lambda text: True if text.strip() != "" else "Name cannot be empty."
    ).ask()
    if not feed_name:
        return
        
    feed_url = questionary.text(
        "Enter RSS Feed URL:",
        style=cli_art.QUESTIONARY_STYLE,
        validate=lambda text: True if text.strip().startswith(("http://", "https://")) else "Must be a valid HTTP/HTTPS URL."
    ).ask()
    if not feed_url:
        return
        
    custom_feeds.append({
        "name": feed_name.strip(),
        "url": feed_url.strip()
    })
    filters["custom_feeds"] = custom_feeds
    
    with open(filters_path, "w", encoding="utf-8") as f:
        yaml.safe_dump(filters, f, default_flow_style=False, allow_unicode=True)
        
    cli_art.cli_info(f"Custom RSS board '{feed_name}' added successfully!")
    _pause_and_return()


def _handle_delete_custom_board(filters_path):
    import yaml
    
    with open(filters_path, "r", encoding="utf-8") as f:
        filters = yaml.safe_load(f) or {}
        
    custom_feeds = filters.get("custom_feeds") or []
    if not custom_feeds:
        cli_art.display_warning("No custom RSS feeds configured.")
        _pause_and_return()
        return
        
    choices = []
    for i, feed in enumerate(custom_feeds):
        choices.append(questionary.Choice(f"{feed['name']} ({feed['url']})", value=i))
    choices.append(questionary.Choice("Cancel", value="cancel"))
    
    selected = cli_art.select("Select custom board to delete:", choices=choices)
    if selected == "cancel" or selected is None:
        return
        
    deleted = custom_feeds.pop(selected)
    filters["custom_feeds"] = custom_feeds
    
    with open(filters_path, "w", encoding="utf-8") as f:
        yaml.safe_dump(filters, f, default_flow_style=False, allow_unicode=True)
        
    cli_art.cli_info(f"Custom board '{deleted['name']}' removed successfully!")
    _pause_and_return()


def _handle_edit_linkedin_queries(profile_path):
    import yaml
    import time
    
    with open(profile_path, "r", encoding="utf-8") as f:
        profile_data = yaml.safe_load(f) or {}
        
    queries = profile_data.get("linkedin_search_queries") or []
    
    while True:
        sys.stdout.write("\x1b[2J\x1b[H")
        sys.stdout.flush()
        cli_art.display_compact_banner("EDIT LINKEDIN BOOLEAN QUERIES")
        
        cli_art.console.print("Current Boolean search queries used on LinkedIn:\n")
        if not queries:
            cli_art.console.print("  [yellow](None configured -- falling back to target roles)[/yellow]\n")
        else:
            for q in queries:
                cli_art.console.print(f"  • [cyan]\"{q}\"[/cyan]")
            cli_art.console.print()
            
        choices = [
            questionary.Choice("➕ Add New Boolean Query String", value="add"),
            questionary.Choice("➖ Delete/Remove Boolean Query String", value="delete"),
            questionary.Choice("Back", value="back")
        ]
        
        act = cli_art.select("Edit Queries:", choices=choices)
        if not act or act == "back":
            break
            
        if act == "add":
            new_q = questionary.text(
                "Enter your new Boolean Query:",
                style=cli_art.QUESTIONARY_STYLE,
                validate=lambda text: True if text.strip() != "" else "Query cannot be empty."
            ).ask()
            if new_q:
                queries.append(new_q.strip())
                profile_data["linkedin_search_queries"] = queries
                with open(profile_path, "w", encoding="utf-8") as f:
                    yaml.safe_dump(profile_data, f, default_flow_style=False, allow_unicode=True)
                cli_art.cli_info("Boolean query added successfully!")
                time.sleep(1)
        elif act == "delete":
            if not queries:
                cli_art.display_warning("No queries to delete.")
                time.sleep(1)
                continue
            choices_del = [questionary.Choice(q, value=q) for q in queries] + ["Cancel"]
            to_del = cli_art.select("Select query to remove:", choices=choices_del)
            if to_del and to_del != "Cancel":
                queries.remove(to_del)
                profile_data["linkedin_search_queries"] = queries
                with open(profile_path, "w", encoding="utf-8") as f:
                    yaml.safe_dump(profile_data, f, default_flow_style=False, allow_unicode=True)
                cli_art.cli_info("Boolean query removed successfully!")
                time.sleep(1)


def _handle_edit_title_filters(filters_path):
    import yaml
    import time
    
    with open(filters_path, "r", encoding="utf-8") as f:
        filters = yaml.safe_load(f) or {}
        
    title_filter = filters.get("title_filter") or {"positive": [], "negative": []}
    
    while True:
        sys.stdout.write("\x1b[2J\x1b[H")
        sys.stdout.flush()
        cli_art.display_compact_banner("EDIT TITLE KEYWORD FILTERS")
        
        cli_art.console.print("These keywords filter all standard job board listings.\n")
        
        pos = title_filter.get("positive") or []
        neg = title_filter.get("negative") or []
        
        cli_art.console.print(f"[green]✔ POSITIVE KEYWORDS[/green] (at least one MUST be present):")
        if not pos:
            cli_art.console.print("  (Empty -- all titles pass)")
        else:
            cli_art.console.print(f"  {', '.join(pos)}")
            
        cli_art.console.print(f"\n[red]✘ NEGATIVE KEYWORDS[/red] (if present, job is skipped):")
        if not neg:
            cli_art.console.print("  (None configured)")
        else:
            cli_art.console.print(f"  {', '.join(neg)}")
        cli_art.console.print()
        
        choices = [
            questionary.Choice("➕ Add Positive Keyword", value="add_pos"),
            questionary.Choice("➕ Add Negative Keyword", value="add_neg"),
            questionary.Choice("➖ Delete Positive Keyword", value="del_pos"),
            questionary.Choice("➖ Delete Negative Keyword", value="del_neg"),
            questionary.Choice("Back", value="back")
        ]
        
        act = cli_art.select("Action:", choices=choices)
        if not act or act == "back":
            break
            
        if act == "add_pos":
            k = questionary.text("Enter positive title keyword:", style=cli_art.QUESTIONARY_STYLE).ask()
            if k:
                pos.append(k.strip())
                title_filter["positive"] = sorted(list(set(pos)))
                filters["title_filter"] = title_filter
                with open(filters_path, "w", encoding="utf-8") as f:
                    yaml.safe_dump(filters, f, default_flow_style=False, allow_unicode=True)
                cli_art.cli_info("Positive filter updated!")
                time.sleep(1)
        elif act == "add_neg":
            k = questionary.text("Enter negative title keyword:", style=cli_art.QUESTIONARY_STYLE).ask()
            if k:
                neg.append(k.strip())
                title_filter["negative"] = sorted(list(set(neg)))
                filters["title_filter"] = title_filter
                with open(filters_path, "w", encoding="utf-8") as f:
                    yaml.safe_dump(filters, f, default_flow_style=False, allow_unicode=True)
                cli_art.cli_info("Negative filter updated!")
                time.sleep(1)
        elif act == "del_pos":
            if not pos:
                continue
            choices_del = [questionary.Choice(x, value=x) for x in pos] + ["Cancel"]
            to_del = cli_art.select("Select positive keyword to remove:", choices=choices_del)
            if to_del and to_del != "Cancel":
                pos.remove(to_del)
                title_filter["positive"] = pos
                filters["title_filter"] = title_filter
                with open(filters_path, "w", encoding="utf-8") as f:
                    yaml.safe_dump(filters, f, default_flow_style=False, allow_unicode=True)
                cli_art.cli_info("Positive keyword removed!")
                time.sleep(1)
        elif act == "del_neg":
            if not neg:
                continue
            choices_del = [questionary.Choice(x, value=x) for x in neg] + ["Cancel"]
            to_del = cli_art.select("Select negative keyword to remove:", choices=choices_del)
            if to_del and to_del != "Cancel":
                neg.remove(to_del)
                title_filter["negative"] = neg
                filters["title_filter"] = title_filter
                with open(filters_path, "w", encoding="utf-8") as f:
                    yaml.safe_dump(filters, f, default_flow_style=False, allow_unicode=True)
                cli_art.cli_info("Negative keyword removed!")
                time.sleep(1)


def _handle_manage_profiles():
    import shutil
    import profile_paths
    use_alt = _should_use_alt_screen()
    while True:
        if use_alt:
            sys.stdout.write("\x1b[2J\x1b[H")
            sys.stdout.flush()
            cli_art.display_compact_banner("SETTINGS & UPKEEP | PROFILE MANAGEMENT")
            cli_art.display_footer_commands()
            cli_art.console.print()
        names = sorted(
            n for n in os.listdir(profile_paths.PROFILES_DIR)
            if os.path.isdir(os.path.join(profile_paths.PROFILES_DIR, n))
        )
        if not names:
            cli_art.display_warning("No profiles exist.")
            return

        choice = cli_art.select(
            "Manage Profiles:",
            choices=[
                questionary.Choice(title="Rename profile", value="rename"),
                questionary.Choice(title="Delete profile", value="delete"),
                questionary.Choice(title="Back", value="back"),
            ]
        )
        if not choice or choice == "back":
            return

        target = cli_art.select(
            f"Select profile to {choice}:",
            choices=names + ["Cancel"]
        )
        if not target or target == "Cancel":
            continue

        if choice == "delete":
            confirm = questionary.confirm(f"Are you sure you want to completely delete the profile '{target}' and all its data? This cannot be undone.").ask()
            if not confirm:
                continue
            for _label, path in profile_paths.sync_roots(target):
                if os.path.exists(path):
                    shutil.rmtree(path)
            cli_art.display_success(f"Profile '{target}' deleted.")

            if target == profile_paths.active_profile():
                if os.environ.get("RESUME_PROFILE"):
                    del os.environ["RESUME_PROFILE"]

        elif choice == "rename":
            new_name = questionary.text(f"New name for '{target}':").ask()
            if not new_name or new_name in names:
                cli_art.display_error("Invalid or duplicate name.")
                continue

            for _label, path in profile_paths.sync_roots(target):
                if os.path.exists(path):
                    parent = os.path.dirname(path)
                    new_path = os.path.join(parent, new_name)
                    os.rename(path, new_path)

            cli_art.display_success(f"Profile '{target}' renamed to '{new_name}'.")
            if target == profile_paths.active_profile():
                profile_paths.set_active_profile(new_name)


def _offer_discovery_backfill() -> bool:
    """Offers to date postings that carry no age signal at all, so they
    become sweepable. Returns True if any were actually stamped.

    Offered here rather than as its own menu entry because this is the
    only moment a user is looking at the number that makes it matter --
    "N postings were left alone" is the question, and this is the answer.
    A standalone "Backfill Discovery Dates" item would be discoverable by
    nobody and meaningful out of context to no one."""
    preview = stale_sweep.backfill_discovery_dates(dry_run=True)
    if not preview["candidate_count"]:
        return False

    cli_art.cli_info(
        f"{preview['candidate_count']} of those can be dated from when this app "
        "first saved them, which would let future sweeps see them.")
    # Named plainly: this edits the JD files, and the date is inferred
    # rather than published, so the user should know both before agreeing.
    if not cli_art.confirm_destructive(
            "Add an estimated first-seen date to",
            f"{preview['candidate_count']} undated posting(s)"):
        cli_art.cli_info("Left them undated.")
        return False

    result = stale_sweep.backfill_discovery_dates(dry_run=False)
    cli_art.cli_success(f"Dated {result['stamped_count']} posting(s).")
    return result["stamped_count"] > 0


def _handle_stale_sweep() -> bool:
    """Archives postings past an age threshold into jds/<profile>/expired/.

    Scoring already devalues stale postings (orchestrator's
    STALE_POSTING_* curve), but ranking only changes ORDER -- it cannot
    shrink a queue that has grown past a thousand entries. This changes
    membership. The two thresholds are deliberately different: scoring
    starts penalizing at day 3, archiving defaults to day 30, because
    getting the ordering wrong costs a scroll and getting the membership
    wrong costs a real lead.

    Always previews before it moves anything -- with a queue this size,
    "trust me" is not an acceptable interaction."""
    raw = cli_art.text(
        "Archive postings older than how many days?",
        default=str(stale_sweep.DEFAULT_STALE_ARCHIVE_DAYS),
    )
    if raw is None:
        return False
    try:
        threshold = int(str(raw).strip())
        if threshold < 1:
            raise ValueError("threshold must be at least 1 day")
    except ValueError:
        cli_art.cli_warning(f"'{raw}' isn't a whole number of days -- nothing was archived.")
        return False

    preview = stale_sweep.preview_sweep(threshold)
    to_archive = preview["to_archive"]

    if not to_archive:
        cli_art.cli_success(
            f"Nothing to archive -- no pending postings are {threshold}+ days old.")
        return False

    cli_art.cli_info(
        f"{len(to_archive)} posting(s) are {threshold}+ days old. "
        f"{preview['to_keep_count']} would stay.")
    if preview["oldest_kept_days"] is not None:
        cli_art.detail(f"   Oldest kept: {preview['oldest_kept_days']}d  "
                       f"Newest moved: {preview['newest_moved_days']}d", level=cli_art.NORMAL)
    if preview["skipped_no_age_count"]:
        # Deliberately surfaced rather than buried: these are postings the
        # sweep is choosing NOT to touch because it can't tell how old they
        # are, and a user wondering why their queue didn't shrink as much
        # as expected deserves the reason -- plus the fix, offered right
        # here where the number that motivates it is on screen.
        cli_art.cli_info(
            f"{preview['skipped_no_age_count']} posting(s) have no post date and were left alone.")
        if _offer_discovery_backfill():
            preview = stale_sweep.preview_sweep(threshold)
            to_archive = preview["to_archive"]
            if not to_archive:
                cli_art.cli_success(
                    f"Nothing to archive -- no pending postings are {threshold}+ days old.")
                return True
            cli_art.cli_info(
                f"Now {len(to_archive)} posting(s) are {threshold}+ days old.")

    # A sample, not all 800 rows -- scan.py's documented anti-spam rule.
    for row in to_archive[:5]:
        cli_art.detail(f"   {row['company']} — {row['title']} ({row['age_days']}d)",
                       level=cli_art.NORMAL)
    if len(to_archive) > 5:
        cli_art.detail(f"   ...and {len(to_archive) - 5} more", level=cli_art.NORMAL)

    if not cli_art.confirm_destructive(
            "Archive", f"{len(to_archive)} stale posting(s) to expired/ (reversible)"):
        cli_art.cli_info("Nothing was archived.")
        return False

    result = stale_sweep.run_sweep(threshold)
    cli_art.cli_success(f"Archived {result['archived_count']} posting(s) to expired/.")
    for err in result["errors"]:
        cli_art.cli_warning(f"Couldn't archive {os.path.basename(err['path'])}: {err['error']}")
    return True


def _handle_help() -> bool:
    cli_art.display_help()
    return False


def _prompt_for_update() -> None:
    """Check for git updates and prompt the user if updates are available.
    This is called at startup before displaying the main menu."""
    if git_update.has_uncommitted_changes():
        # Shown briefly, then erased (rich.live.Live's own transient=True
        # cleanup, the same mechanism a spinner uses to vanish when it's
        # done) -- a plain console.print() has no equivalent to
        # questionary's erase_when_done, so this is the same "readable,
        # then gone" treatment for a line that isn't an interactive prompt.
        # Skips the timed hold entirely under RESUME_BUILDER_MOTION=reduced
        # (same opt-out cli_art._reveal_banner() honors) since an
        # uninterruptible wait is exactly the kind of blocking motion that
        # flag exists to remove, not just visually simplify.
        message = f"{cli_art.WARNING} You have uncommitted changes -- skipping update check."
        if os.environ.get("RESUME_BUILDER_MOTION") == "reduced":
            cli_art.console.print(message)
        else:
            import time
            from rich.live import Live

            with Live(message, console=cli_art.console, transient=True):
                time.sleep(1.2)
        return

    # check_for_updates() does a real `git fetch origin main` with a 10s
    # timeout -- without this, every launch on a slow network/VPN can sit
    # idle after the banner for up to 10s with no indication anything is
    # happening.
    # Call check_for_updates() directly so tests that mock it and expect
    # no console output when there are no updates do not see transient
    # status spinner prints. The status spinner was primarily to give
    # feedback during a real `git fetch` network call; tests mock the
    # network call and expect silence on the no-update path.
    has_updates, message = git_update.check_for_updates()
    if not has_updates:
        return

    cli_art.console.print(f"\n{cli_art.HINT} Updates available: {message}")
    update = charm_prompt.confirm(
        "Pull the latest changes from GitHub?",
        default=False,
    )

    if update:
        success, result = git_update.pull_updates()
        if success:
            cli_art.console.print(f"{cli_art.SUCCESS} Updated successfully")
        else:
            # `result` here is git_update.pull_updates()'s own captured
            # stderr string, not an exception object -- friendly_error()
            # needs a real exception to classify, so this uses cli_error()
            # for the plain-English lead line and demotes the raw git
            # output via detail() instead of printing it at full weight.
            cli_art.cli_error("Update failed -- couldn't pull the latest changes.")
            cli_art.detail(result, level=cli_art.NORMAL)


def _handle_check_updates() -> bool:
    """Maintenance menu option to check for and apply updates."""
    scroll_region_modified = False

    # Clear screen and draw the compact banner!
    sys.stdout.write("\x1b[2J\x1b[H")
    sys.stdout.flush()
    cli_art.display_compact_banner("SETTINGS & UPKEEP | CHECK FOR UPDATES")

    # Draw the gorgeous execution footer static at the bottom row (row = rows)
    cli_art.display_execution_footer()

    # Set dynamic scroll region to freeze rows 1-4 (header) and the bottom row (footer)
    import shutil
    columns, rows = shutil.get_terminal_size()
    sys.stdout.write(f"\x1b[5;{rows-1}r")
    sys.stdout.write("\x1b[5;1H")
    sys.stdout.flush()
    scroll_region_modified = True

    try:
        if git_update.has_uncommitted_changes():
            cli_art.console.print(
                f"{cli_art.WARNING} You have uncommitted changes -- please commit or stash them first."
            )
            return False

        with cli_art.console.status("Checking for updates...", spinner="dots"):
            has_updates, message = git_update.check_for_updates()

        if has_updates:
            cli_art.console.print(f"{cli_art.SUCCESS} Updates available: {message}")
            update = charm_prompt.confirm(
                "Pull the latest changes?",
                default=True,
            )

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
    finally:
        if scroll_region_modified:
            sys.stdout.write("\x1b[r")
            sys.stdout.flush()
    _pause_and_return()


_HANDLERS = {
    "bootstrap": _handle_bootstrap,
    "update_knowledge": _handle_update_knowledge,
    "scan": _handle_scan,
    "add_manual_jd": _handle_add_manual_jd,
    "liveness": _handle_liveness,
    "evaluate_all": _handle_evaluate_all,
    "tailor_all": _handle_tailor_all,
    "tailor_pick": _handle_tailor_pick,
    "coverletter_pick": _handle_coverletter_pick,
    "browse_jobs": _handle_browse_jobs,
    "career_dashboard": _handle_career_dashboard,
    "polish": _handle_polish,
    "stale_sweep": _handle_stale_sweep,
    "help": _handle_help,
    "check_updates": _handle_check_updates,
    "bullet_bank": _handle_bullet_bank,
    "settings_upkeep": _handle_settings_upkeep,
}


_CHAIN = {
    # Not "Check Liveness" -- scan.run_scan() already runs a real
    # liveness verify pass by default on exactly the postings it just
    # found (career-ops's scan.mjs --verify, ported 2026-07-26), so
    # suggesting a liveness check on the same JDs immediately after
    # would just report back what verify already confirmed. Straight to
    # evaluate instead, same destination "liveness" itself chains to.
    "scan": [("Evaluate All JDs", "evaluate_all")],
    "liveness": [("Evaluate All JDs", "evaluate_all")],
    "evaluate_all": [("Customize Resume", "tailor_all"), ("Browse & Manage Jobs", "browse_jobs")],
    "tailor_all": [("Browse & Manage Jobs", "browse_jobs"), ("Polish with Gemini", "polish")],
    "tailor_pick": [("Write Cover Letter", "coverletter_pick"), ("Polish with Gemini", "polish")],
    "coverletter_pick": [("Polish with Gemini", "polish")],
}

# Same icon per destination value as _build_choices() above, so the "what's next"
# chain prompt stays visually consistent with the main menu instead of
# falling back to plain text.
_CHAIN_ICONS = {
    "liveness":         "discovery",
    "evaluate_all":     "evaluate",
    "tailor_all":       "build",
    "tailor_pick":      "build",
    "coverletter_pick": "build",
    "browse_jobs":      "utility",
    "polish":           "build",
}

# Labels for the session-end summary -- only actions worth reporting on
# exit get an entry; anything absent here (e.g. "polish", "scan",
# "liveness") just isn't tallied.
_SESSION_LABELS = {
    "tailor_all": "resumes tailored",
    "tailor_pick": "resumes tailored",
    "coverletter_pick": "cover letters written",
}


def _chain_choice_title(label: str, value: str):
    """Same icon-pairing _build_choices() uses (_CHAIN_ICONS, keyed by
    chain-destination value) so a "what's next?" suggestion renders
    exactly like a real menu entry instead of falling back to plain
    text."""
    icon_name = _CHAIN_ICONS.get(value)
    return _icon_title(icon_name, label) if icon_name else label


# cli.py's own Click command names for the handful that don't already
# match a _HANDLERS/_CHAIN key verbatim ("scan"/"liveness" already do,
# since cli.py's commands happen to share those names). Keeps the
# vocabulary mismatch offer_next_steps() was built to fix in exactly one
# place, instead of cli.py needing to know menu.py's internal key names.
_CLI_ACTION_TO_VALUE = {
    "tailor": "tailor_pick",
    "coverletter": "coverletter_pick",
    "evaluate": "evaluate_all",
}


def offer_next_steps(
    action: str,
    session_stats: dict | None = None,
    *,
    jd_file: str | None = None,
    from_cli: bool = False,
) -> None:
    """The one "what's next?" prompt shown after any action completes --
    unifies what used to be two separate implementations with different
    vocabularies: this module's own _CHAIN-driven chain (icons,
    session-stat tracking, recursion back into _HANDLERS -- built for the
    interactive menu loop) and cli.py's own flatter version (Show Help/
    Return to Main Menu/Exit, plus a contextual "Polish this Resume/Cover
    Letter"). Both now go through here, so `resume tailor` from a bare
    shell prompt and picking "Customize Resume for Specific Role(s)" from
    the interactive menu land on an identical-looking prompt.

    `action` accepts either a real _HANDLERS/_CHAIN key (menu.py's own
    caller, _run_with_chain below) or one of cli.py's Click command names
    -- _CLI_ACTION_TO_VALUE maps the ones that don't already match.

    from_cli=True is cli.py's own case: a bare `resume <command>` has no
    interactive menu loop of its own to fall back into, so it spells out
    Show Help/Return to Main Menu/Exit explicitly, plus (when jd_file is
    set and the action just tailored a resume or wrote a cover letter) a
    contextual "Polish this Resume/Cover Letter" shortcut straight into
    polish_module.run(jd_file) -- distinct from the plain "polish" chain
    leaf, which prompts for a file interactively rather than acting on
    the one just built. from_cli=False (the default, menu.py's own call
    below) skips all of that: Help/Exit/the main menu itself are already
    one pick away from inside the menu loop, so it just offers a plain
    "Back to Menu" -- and, matching the old _run_with_chain's own gate,
    stays silent entirely when there's nothing to suggest.

    Guarded by the same is_terminal check cli.py's original
    _offer_next_steps carried -- piped/CI/test runs have no one there to
    answer a prompt, and questionary would otherwise hang or error."""
    if not cli_art.console.is_terminal:
        return

    # Clear screen and display a clean slate for the "What's Next?" prompt!
    sys.stdout.write("\x1b[2J\x1b[H")
    sys.stdout.flush()
    cli_art.display_compact_banner("Completed Actions & Next Steps")
    cli_art.display_footer_commands()

    value = _CLI_ACTION_TO_VALUE.get(action, action)
    
    # Trigger a premium, high-energy success celebration for milestones!
    if value in ("tailor_pick", "tailor_all", "coverletter_pick", "express"):
        if value == "express":
            cli_art.display_success_celebration(
                "Express Auto-pilot Setup Complete!",
                "We ingested your files, extracted your key achievements, populated your Bullet Bank, and built your tailored resume."
            )
        elif value == "coverletter_pick":
            cli_art.display_success_celebration(
                "Cover Letter Customized Successfully!",
                "Your cover letter has been perfectly tailored and aligned to match the target job description."
            )
        else:
            cli_art.display_success_celebration(
                "Resume Customized & Polished!",
                "All your achievement bullets have been dynamically rewritten and adapted for this specific role."
            )

    next_options = _CHAIN.get(value) or []
    choices = [questionary.Choice(title=_chain_choice_title(label, v), value=v) for label, v in next_options]

    last_pdf = os.environ.get("RESUME_BUILDER_LAST_PDF")
    if last_pdf and os.path.exists(last_pdf):
        choices.insert(0, questionary.Choice(title="↗ View Generated PDF", value="__view_pdf__"))

    if from_cli:
        if value in ("tailor_pick", "coverletter_pick") and jd_file:
            doc_type = "Resume" if value == "tailor_pick" else "Cover Letter"
            choices.insert(0, questionary.Choice(title=f"Polish this {doc_type}", value="__polish_this__"))
        choices.append(questionary.Choice(title=_icon_title("hint", "Show Help"), value="__help__"))
        choices.append(questionary.Choice(title=_icon_title("utility", "Return to Main Menu"), value="__menu__"))
        choices.append(questionary.Choice(title=_icon_title("utility", "Exit"), value="__exit__"))
    else:
        if not choices:
            # If we have a view_pdf option, we shouldn't return early even if there are no downstream chains!
            if not last_pdf or not os.path.exists(last_pdf):
                return
        choices.append(questionary.Choice(title=_icon_title("utility", "Back to Menu"), value="__back__"))

    cli_art.display_whats_next_panel()
    choice = cli_art.select("Choose one:", choices=choices)

    if not choice or choice in ("__back__", "__exit__"):
        return
    if choice == "__view_pdf__":
        if last_pdf and os.path.exists(last_pdf):
            if sys.platform == "darwin":
                subprocess.run(["open", last_pdf])
            elif sys.platform == "win32":
                os.startfile(last_pdf)
            else:
                subprocess.run(["xdg-open", last_pdf])
        # Re-offer the next steps recursively after opening the viewer
        offer_next_steps(action, session_stats, jd_file=jd_file, from_cli=from_cli)
        return
    if choice == "__help__":
        cli_art.display_help()
        return
    if choice == "__menu__":
        run_interactive_menu()
        return
    if choice == "__polish_this__":
        polish_module.run(jd_file)
        return

    # A real chain leaf was picked -- run it through the same dispatch a
    # main-menu pick would use, so session stats and any further chain
    # keep accumulating exactly as they would from inside the menu.
    _run_with_chain(choice, session_stats if session_stats is not None else {})


def _pause_and_return() -> None:
    cli_art.console.print()
    cli_art.console.print(f"[{theme.MUTED}]Press Enter to return to the menu...[/{theme.MUTED}]")
    if sys.stdin.isatty():
        try:
            sys.stdin.readline()
        except (KeyboardInterrupt, IOError):
            pass


def _run_with_chain(value: str, session_stats: dict) -> None:
    interactive_actions = {"career_dashboard", "browse_jobs", "bullet_bank", "settings_upkeep", "help"}
    
    action_titles = {
        "bootstrap": "Profile Bootstrapping Wizard",
        "update_knowledge": "Knowledge Base Update",
        "scan": "Job Search Scanner",
        "liveness": "Liveness Verification Check",
        "evaluate_all": "JD Evaluation & Fit Scoring",
        "tailor_all": "Resume & Cover Letter Customization",
        "tailor_pick": "Targeted Resume Customization",
        "coverletter_pick": "Targeted Cover Letter Customization",
        "polish": "Polishing Documents with Gemini",
        "stale_sweep": "Stale Application Sweep",
    }
    
    is_interactive = value in interactive_actions
    title = action_titles.get(value)
    
    scroll_region_modified = False
    
    if not is_interactive and title:
        # Clear screen and draw the compact banner!
        sys.stdout.write("\x1b[2J\x1b[H")
        sys.stdout.flush()
        cli_art.display_compact_banner(title)
        
        # Draw the gorgeous execution footer static at the bottom row (row = rows)
        cli_art.display_execution_footer()
        
        # Set dynamic scroll region to freeze rows 1-4 (header) and the bottom row (footer)
        columns, rows = shutil.get_terminal_size()
        sys.stdout.write(f"\x1b[5;{rows-1}r")
        sys.stdout.write("\x1b[5;1H")
        sys.stdout.flush()
        scroll_region_modified = True

    try:
        did_something = _HANDLERS[value]()
    finally:
        if scroll_region_modified:
            # Clean up: restore the scroll region back to the entire screen window
            sys.stdout.write("\x1b[r")
            sys.stdout.flush()

    if did_something:
        label = _SESSION_LABELS.get(value)
        if label:
            session_stats[label] = session_stats.get(label, 0) + 1

    if is_interactive:
        return

    if not did_something or not _CHAIN.get(value):
        _pause_and_return()
        return

    offer_next_steps(value, session_stats)


def _session_summary(session_stats: dict) -> str:
    if not session_stats:
        return "No actions taken this session."
    parts = [f"{count} {label}" for label, count in session_stats.items()]
    return f"{cli_art.SUCCESS} " + " · ".join(parts) + " · Nice work."


@contextlib.contextmanager
def _alternate_screen():
    """Switches the terminal to the alternate screen buffer and restores it at exit.
    Only writes ANSI escape codes when running interactively in a TTY.
    """
    is_interactive = sys.stdout.isatty() and not os.environ.get("RESUME_BUILDER_TESTING")
    if is_interactive:
        sys.stdout.write("\x1b[?1049h\x1b[H")
        sys.stdout.flush()
    try:
        yield
    finally:
        if is_interactive:
            sys.stdout.write("\x1b[?1049l")
            sys.stdout.flush()


def _should_use_alt_screen() -> bool:
    """Detects if we can safely run in alternate screen (fullscreen) mode."""
    if os.environ.get("RESUME_ALT_SCREEN") == "1":
        return True
    if os.environ.get("RESUME_ALT_SCREEN") == "0":
        return False
    # Graceful auto-detection: if terminal is at least 24 rows tall, we can go fullscreen!
    # This prevents the scrolling overflow issue on standard terminal screens.
    columns, rows = shutil.get_terminal_size()
    return rows >= 24


def run_interactive_menu() -> None:
    # Wrapped in an elegant fullscreen/alt-screen context manager.
    # Terminal size is auto-detected to ensure adequate height, or can be
    # explicitly controlled via the RESUME_ALT_SCREEN environment variable.
    use_alt = _should_use_alt_screen()
    ctx = _alternate_screen() if use_alt else contextlib.nullcontext()

    with ctx:
        cli_art.display_main_banner()
        if not _confirm_active_profile():
            # Ctrl-C/Esc at the profile gate -- exit now, same as Ctrl-C on the
            # main menu's own select() below, rather than falling through into
            # icon-set/update-check prompts and a menu the user never asked for.
            cli_art.display_exit_footer()
            return
        _confirm_icon_set()
        _prompt_for_update()
        cli_art.display_tip()

        session_stats = {}
        first_loop = True

        while True:
            if use_alt and not first_loop:
                # Clear terminal and home cursor
                sys.stdout.write("\x1b[2J\x1b[H")
                sys.stdout.flush()
                # Draw main banner instantly (reveal=False)
                cli_art.display_main_banner(reveal=False)
            elif first_loop:
                first_loop = False
            else:
                cli_art.display_breadcrumb()
            
            if use_alt:
                cli_art.display_footer_commands()

            cli_art.console.print()
            choice = cli_art.select("What would you like to do?", choices=_menu_choices())

            if choice == "exit" or not choice:
                cli_art.console.print(f"\n{_session_summary(session_stats)}\n")
                cli_art.display_exit_footer()
                break

            if os.environ.get("RESUME_GUEST_MODE") and choice != "bootstrap":
                cli_art.console.print(
                    f"[{theme.BRAND}]Take a look around! Choose \"New User? Start Here!\" when you're "
                    f"ready to set up your own profile -- nothing else runs until then.[/{theme.BRAND}]"
                )
                continue

            if choice in _SUBMENUS:
                _SUBMENUS[choice](session_stats)
            else:
                _run_with_chain(choice, session_stats)

            if os.environ.get("RESUME_GUEST_MODE") and os.environ.get("RESUME_PROFILE"):
                os.environ.pop("RESUME_GUEST_MODE", None)
