"""
picker.py -- the shared "confirm gate -> evaluate every pending JD ->
checkbox picker -> process each selection" flow. Used by resume run
--pick, resume coverletter --pick, and the interactive menu's own
tailor-pick/coverletter-pick items -- one implementation instead of four.
"""

import os

import click
import questionary

import cli_art
import batch_evaluate
import jd_manager
import theme

# Sourced from theme.py so picker.py's checkbox list and cli_art.py's fit
# table are provably one palette -- see theme.RECOMMENDATION_STYLES for
# the exact values ("Skip" stays unbolded, deliberately de-emphasized).
_RECOMMENDATION_STYLES = theme.RECOMMENDATION_STYLES


def should_proceed(count: int, skip_confirm: bool, action: str = "evaluate") -> bool:
    """Standalone copy of cli._should_proceed's exact logic -- duplicated
    rather than imported, since cli.py will import menu.py (for the bare-
    invocation menu launch) which imports this module; cli.py importing
    picker.py directly too is fine, but picker.py must not import cli.py
    back, to avoid a cycle. action customizes the confirmation's verb --
    "evaluate" (default) fits evaluate-then-pick flows; pass a different
    verb (e.g. "tailor") for a batch action that doesn't itself evaluate
    anything, so the prompt doesn't imply a Gemini call that isn't real."""
    if skip_confirm:
        return True
    return click.confirm(f"About to {action} {count} pending JD(s) -- one real Gemini call each. Continue?")


def pick_and_process(pending_paths: list, process_one, action_verb: str, skip_confirm: bool = False) -> tuple:
    """
    Shared flow: confirm gate -> batch_evaluate.evaluate_all_pending() ->
    cli_art.render_fit_table() -> questionary.checkbox() (labeled via
    action_verb) -> process_one(path) for each selected path. Returns
    (completed, failed) -- both 0 if aborted, empty, or nothing
    selected/evaluable. process_one(path) should return truthy on
    success, falsy on failure.
    """
    if not pending_paths:
        cli_art.console.print("Nothing to pick from -- no pending JDs.")
        return (0, 0)
    if not should_proceed(len(pending_paths), skip_confirm):
        cli_art.console.print("Aborted.")
        return (0, 0)

    cli_art.display_banner(f"Evaluating {len(pending_paths)} pending JD(s) for picker")
    # Always evaluates everything fresh here, unlike "Evaluate ALL Pending
    # JDs"'s skip-already-evaluated default -- this picker's whole point is
    # a complete, current checkbox list, not one silently missing anything
    # already scored from a previous run.
    results = batch_evaluate.evaluate_all_pending(pending_paths, skip_evaluated=False)
    valid = [r for r in results if not r["error"]]
    if not valid:
        cli_art.console.print("Nothing could be evaluated -- no picker to show.")
        return (0, 0)

    cli_art.render_fit_table(results)

    choices = [
        questionary.Choice(
            title=f"{r['composite_score']:.2f}/5 | {r['recommendation']} | {r['company_name']} | {r['job_title']}",
            value=r["source_file"],
        )
        for r in valid
    ]
    selected_paths = questionary.checkbox(
        f"Select JD(s) to {action_verb}:", choices=choices, style=cli_art.QUESTIONARY_STYLE,
    ).ask()
    if not selected_paths:
        cli_art.console.print("No jobs selected, nothing to do.")
        return (0, 0)

    completed = 0
    failed = 0
    for path in selected_paths:
        if process_one(path):
            completed += 1
        else:
            failed += 1
    cli_art.console.print(f"\nPicked batch summary: {completed} completed, {failed} failed.")
    return (completed, failed)


def pick_one_pending_jd(pending_paths: list) -> str | None:
    """Lightweight single-choice picker over pending_paths -- no fit
    evaluation, no Gemini call, just labeled via jd_manager.extract_job_meta()
    (a free, deterministic parse of the JD file itself). Used by the menu's
    merged "for a Specific JD" entries (tailor/coverletter), which used to
    prompt for an arbitrary filesystem path."""
    if not pending_paths:
        cli_art.console.print("Nothing to pick from -- no pending JDs.")
        return None

    choices = []
    for path in pending_paths:
        title, company = jd_manager.extract_job_meta(path)
        label = f"{company} - {title}" if (company or title) else os.path.basename(path)
        choices.append(questionary.Choice(title=label, value=path))

    return questionary.select(
        "Which JD?", choices=choices, style=cli_art.QUESTIONARY_STYLE,
    ).ask()


def pick_one_evaluated_jd(pending_paths: list) -> str | None:
    """Single-choice picker restricted to pending JDs carrying a persisted
    _evaluation (jd_manager.save_evaluation(), written by a prior
    "Evaluate" run) -- sorted best composite_score first, each choice
    labeled with its score/recommendation. A JD with no _evaluation simply
    isn't eligible; it needs to be evaluated first."""
    evaluated = []
    for path in pending_paths:
        evaluation = jd_manager.read_evaluation(path)
        if not evaluation:
            continue
        title, company = jd_manager.extract_job_meta(path)
        evaluated.append((evaluation, path, title, company))

    if not evaluated:
        cli_art.console.print(
            "Nothing to pick from -- no evaluated JDs yet.\n"
            "Hint: Don't see the role you're expecting? Run an evaluation "
            "on it first (Evaluate ALL Pending JDs or Evaluate a Specific "
            "JD) -- then it'll appear in this list."
        )
        return None

    evaluated.sort(key=lambda item: -(item[0].get("composite_score") or 0))

    choices = []
    for evaluation, path, title, company in evaluated:
        score_style = _RECOMMENDATION_STYLES.get(evaluation.get("recommendation"), "")
        label = [
            (score_style, f"{evaluation.get('composite_score'):.2f}/5 | {evaluation.get('recommendation')}"),
            ("", f" | {company or '?'} | {title or os.path.basename(path)}"),
        ]
        choices.append(questionary.Choice(title=label, value=path))

    return questionary.select(
        "Which JD?", choices=choices, style=cli_art.QUESTIONARY_STYLE,
    ).ask()
