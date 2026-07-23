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


def list_all_evaluated_jds(statuses: list | None = None) -> list:
    """Every JD (pending or completed) carrying a persisted _evaluation,
    each as {"path", "status" ("Pending"/"Completed"), "evaluation",
    "liveness", "application", "title", "company"}, sorted best
    composite_score first. "application" is the real-world application
    progress (see jd_manager.save_application_status()) -- None until
    someone's marked it. Archived JDs are never included --
    jd_manager.get_pending_jds()/get_completed_jds() only scan their own
    directory, and jds/archived/ is a third, separate one neither
    touches. statuses restricts which of "Pending"/"Completed" get
    scanned at all (default: both) -- for callers whose action only
    makes sense against one status (e.g. tailoring only applies to
    Pending, a cover letter only to Completed)."""
    statuses = statuses or ["Pending", "Completed"]
    rows = []
    if "Pending" in statuses:
        for path in jd_manager.get_pending_jds():
            evaluation = jd_manager.read_evaluation(path)
            if not evaluation:
                continue
            title, company = jd_manager.extract_job_meta(path)
            rows.append({
                "path": path, "status": "Pending", "evaluation": evaluation,
                "liveness": jd_manager.read_liveness(path),
                "application": jd_manager.read_application_status(path),
                "title": title, "company": company,
            })
    if "Completed" in statuses:
        for path in jd_manager.get_completed_jds():
            evaluation = jd_manager.read_evaluation(path)
            if not evaluation:
                continue
            title, company = jd_manager.extract_job_meta(path)
            rows.append({
                "path": path, "status": "Completed", "evaluation": evaluation,
                "liveness": jd_manager.read_liveness(path),
                "application": jd_manager.read_application_status(path),
                "title": title, "company": company,
            })
    rows.sort(key=lambda r: -(r["evaluation"].get("composite_score") or 0))
    return rows


def browse_and_select_jds(statuses: list | None = None) -> list:
    """The shared browse-and-act entry point: renders every evaluated JD
    (pending or completed, or just one status if statuses is passed) as
    a table, then a questionary.checkbox() over the same rows so one or
    many can be selected at once. Returns a list of the selected rows
    (list_all_evaluated_jds()'s dict shape) -- empty if there's nothing
    to show or nothing gets checked."""
    rows = list_all_evaluated_jds(statuses=statuses)
    if not rows:
        if statuses == ["Pending"]:
            hint = "Nothing to browse -- no evaluated Pending JDs.\nHint: run \"Evaluate ALL Pending Roles\" first, then they'll appear here."
        elif statuses == ["Completed"]:
            hint = "Nothing to browse -- no Completed JDs yet.\nHint: tailor a resume for a role first, then it'll appear here."
        else:
            hint = "Nothing to browse -- no evaluated JDs yet.\nHint: run \"Evaluate ALL Pending Roles\" first, then they'll appear here."
        cli_art.console.print(hint)
        return []

    cli_art.render_pipeline_table(rows)

    choices = []
    for r in rows:
        evaluation = r["evaluation"]
        score_style = _RECOMMENDATION_STYLES.get(evaluation.get("recommendation"), "")
        label = [
            (score_style, f"{evaluation.get('composite_score'):.2f}/5 | {evaluation.get('recommendation')}"),
            ("", f" | {r['status']:<9} | {r['company'] or '?'} | {r['title'] or os.path.basename(r['path'])}"),
        ]
        choices.append(questionary.Choice(title=label, value=r["path"]))

    selected_paths = questionary.checkbox(
        "Select JD(s) (space to check, enter to confirm):", choices=choices, style=cli_art.QUESTIONARY_STYLE,
    ).ask()
    if not selected_paths:
        return []

    by_path = {r["path"]: r for r in rows}
    return [by_path[p] for p in selected_paths]


