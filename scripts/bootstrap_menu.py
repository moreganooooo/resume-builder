"""bootstrap_menu.py -- the resumable "New User? Start Here!" submenu:
shows status across all 8 onboarding steps (Phase 0 ingestion, Phase 0.5
profile setup, and the 6 bullet-bank pipeline stages) and lets a user run
any one of them individually, instead of the old flow's single opaque
subprocess covering everything at once with no way to see -- or resume
from -- wherever it was left off.

Deliberately does NOT duplicate progress-tracking logic for stages 1-6:
bootstrap_bullet_bank.PIPELINE_STAGES and bullet_bank_menu.STAGES are the
exact same six scripts/outputs (audit -> cluster -> rewrite ->
audit_keepers -> score_keeper_gems -> embed), so this reuses
bullet_bank_menu.STAGES/_stage_status()/_handle_choice() directly rather
than reimplementing them.
"""

import os

import questionary

import bootstrap_bullet_bank
import bootstrap_profile
import bullet_bank_menu
import cli_art
import theme


def _phase0_status() -> tuple:
    """(status, detail) for document ingestion -- same (done, total)
    convention bullet_bank_menu.py's progress functions use."""
    source_docs_dir = bootstrap_bullet_bank.SOURCE_DOCS_DIR
    if not os.path.isdir(source_docs_dir):
        return ("Never run", "no source documents uploaded yet")

    files = [f for f in os.listdir(source_docs_dir) if os.path.isfile(os.path.join(source_docs_dir, f))]
    total = len(files)
    if total == 0:
        return ("Never run", "no source documents uploaded yet")

    checkpoint = bootstrap_bullet_bank._load_checkpoint()
    done = sum(1 for f in files if checkpoint.get(f, {}).get("status") == "done")
    if done < total:
        return ("In progress", f"{done}/{total} processed ({total - done} pending)")
    return ("Up to date", f"{total} document(s) processed")


def _phase05_status() -> tuple:
    """(status, detail) for profile setup. cv.md is the last artifact
    run_profile_setup() writes, so its absence means an interrupted run
    even if profile.yml made it to disk -- mirrors bullet_bank_menu.py's
    own "final output file is the real completion signal" convention.

    Locked until Phase 0 (ingestion) itself reports "Up to date" --
    run_profile_setup() drafts identity/tags/cv.md from what ingestion
    extracted (bootstrap_bullet_bank.DRAFT_CSV_PATH), and running it first
    fires a real, paid Gemini call against an empty achievements string
    (B16). This was previously just a body comment in bootstrap_profile.py's
    module docstring, unenforced -- now it's an actual gate, and "Locked"
    is visible in this same status table rather than discoverable only by
    reading source."""
    if _phase0_status()[0] != "Up to date":
        return ("Locked", "finish Step 0 (ingestion) first")
    if not os.path.exists(bootstrap_profile.PROFILE_YML_PATH):
        return ("Never run", "")
    if not os.path.exists(bootstrap_profile.CV_MD_PATH):
        return ("In progress", "profile.yml written, cv.md not yet drafted")
    return ("Up to date", "")


def _run_phase0() -> bool:
    """Returns True if ingestion actually ran, False if it just printed
    instructions for an empty source-docs folder, or was blocked because
    GEMINI_API_KEY still isn't set -- the caller uses this so backing out
    of an empty/blocked Step 0 doesn't fire the "what's next?" chain.

    Stops before run_ingestion() if collect_secrets() reports the key
    wasn't set (deferred "later") rather than proceeding anyway -- ingestion
    calls the Gemini API for every document, and proceeding without a key
    was B16's false-green chain (a 403 quietly checkpointed as "done" with
    nothing extracted)."""
    source_docs_dir = bootstrap_bullet_bank.SOURCE_DOCS_DIR
    os.makedirs(source_docs_dir, exist_ok=True)
    files = [f for f in os.listdir(source_docs_dir) if os.path.isfile(os.path.join(source_docs_dir, f))]
    if not files:
        # Deferred import: menu.py imports this module, so importing menu
        # at this module's top level would be circular -- safe here since
        # it only runs once both modules are already fully loaded.
        import menu
        menu._print_source_docs_instructions(source_docs_dir)
        return False

    secrets = bootstrap_profile.collect_secrets()
    if not secrets["gemini_key_set"]:
        print(
            f"\n{theme.colorize_icon_ansi('warning')}  Skipping ingestion -- GEMINI_API_KEY isn't set yet. "
            "Every document ingestion processes needs it. Add it to your profile's .env, then come back "
            "to this step."
        )
        return False

    summary = bootstrap_bullet_bank.run_ingestion()
    bootstrap_bullet_bank.print_ingestion_summary(summary)
    return True


def _run_phase05() -> bool:
    """Returns True if profile setup actually ran, False if it was blocked
    -- Phase 0 not yet complete, or GEMINI_API_KEY still not set -- mirrors
    _run_phase0()'s "did this actually do anything" convention.

    Gated on _phase0_status() being "Up to date" (see _phase05_status()'s
    "Locked" state) rather than the unenforced body-comment dependency this
    used to rely on, and stops before run_profile_setup() the same way
    _run_phase0() stops before run_ingestion() when the key was deferred
    (B16)."""
    if _phase0_status()[0] != "Up to date":
        print(
            f"\n{theme.colorize_icon_ansi('warning')}  Step 0.5 needs Step 0 (document ingestion) finished "
            "first -- profile setup drafts your identity, tags, and cv.md from what ingestion extracted, "
            "and running it first would produce a blank, still-paid-for draft. Finish Step 0, then come "
            "back."
        )
        return False

    secrets = bootstrap_profile.collect_secrets()
    if not secrets["gemini_key_set"]:
        print(
            f"\n{theme.colorize_icon_ansi('warning')}  Skipping profile setup -- GEMINI_API_KEY isn't set "
            "yet. Add it to your profile's .env, then come back to this step."
        )
        return False

    bootstrap_profile.run_profile_setup()
    return True


def _build_choices() -> list:
    choices = [
        questionary.Choice(
            title=[("class:text", "0. Ingest Source Documents  "),
                   ("class:description", "(extract achievements from uploaded files)")],
            value="phase0",
        ),
        questionary.Choice(
            title=[("class:text", "0.5 Set Up Profile  "),
                   ("class:description", "(identity, profile.yml, cv.md draft)")],
            value="phase05",
        ),
    ]
    for stage in bullet_bank_menu.STAGES:
        choices.append(questionary.Choice(
            title=[("class:text", f"{stage['number']}. {stage['label']}  "),
                   ("class:description", f"({stage['description']})")],
            value=stage["key"],
        ))
    choices.append(questionary.Choice(title="Back to Main Menu", value="__back__"))
    return choices


def run_bootstrap_menu() -> bool:
    """Returns True if at least one phase actually ran (worth a "what's
    next" chain prompt back in menu.py), False if the user backed out
    without doing anything."""
    did_something = False
    while True:
        stage_rows = [
            (0, "Ingest Source Documents", *_phase0_status()),
            ("0.5", "Set Up Profile", *_phase05_status()),
        ]
        stage_rows += [
            (s["number"], s["label"], *bullet_bank_menu._stage_status(s))
            for s in bullet_bank_menu.STAGES
        ]
        cli_art.render_bullet_bank_status(stage_rows, [], title="Onboarding Progress")

        choice = questionary.select(
            "New User Setup:", choices=_build_choices(), style=cli_art.QUESTIONARY_STYLE,
        ).ask()
        if not choice or choice == "__back__":
            return did_something

        if choice == "phase0":
            did_something = _run_phase0() or did_something
        elif choice == "phase05":
            did_something = _run_phase05() or did_something
        else:
            bullet_bank_menu._handle_choice(choice)
            did_something = True
