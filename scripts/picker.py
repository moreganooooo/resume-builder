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


_PAGE_SIZE = 50

# Sentinel values for the extra "turn the page" / "confirm" entries
# appended to each page's checkbox choices -- distinguishable from any
# real JD path/source_file since those always contain a "/" or file
# extension.
_NAV_PREV = "__browse_prev_page__"
_NAV_NEXT = "__browse_next_page__"
_NAV_DONE = "__browse_done__"


def _paginated_checkbox(count: int, render_page, choices_for_page, page_size: int = _PAGE_SIZE) -> set:
    """Shared pagination engine behind every large multi-select JD picker
    in this program (the interactive menu's Browse & Manage Jobs /
    Customize Resume for Specific Role(s) / Write Cover Letter for
    Specific Role(s), and the `resume run --pick` / `resume coverletter
    --pick` CLI flows) -- callers differ only in what a "row" is
    (list_all_evaluated_jds() dicts vs. batch_evaluate results) and how
    it's rendered/turned into a Choice, both supplied as callbacks so
    this function itself stays data-shape-agnostic:

    - render_page(start, end): prints that page's bordered "blue box"
      table (e.g. cli_art.render_pipeline_table()/render_fit_table()).
    - choices_for_page(start, end, selected): returns that page's real
      (non-nav) questionary.Choice list, `checked=` reflecting `selected`
      so a revisited page shows prior checks.

    Bounding both the table and the checkbox to one page at a time (page
    a page_size, not every evaluated JD/pending JD at once) is what
    fixes 1000+ JDs otherwise dumping an unbounded console.print() that
    permanently eats terminal scrollback. "Previous page" / "Next page" /
    "Done" are appended -- behind a Separator, bold/colored for
    visibility -- as extra choices in that same checkbox list, so paging
    and selecting happen in one widget. Selections persist across page
    turns via a running set, keyed on whatever value each Choice carries.
    Returns that final set -- empty if count is 0, the prompt is aborted
    (Ctrl-C), or nothing ends up checked."""
    if count == 0:
        return set()

    selected: set = set()
    total_pages = (count + page_size - 1) // page_size
    page = 0

    while True:
        start = page * page_size
        end = min(start + page_size, count)
        render_page(start, end)

        real_choices = choices_for_page(start, end, selected)
        page_values = {c.value for c in real_choices}
        choices = list(real_choices)
        choices.append(questionary.Separator())
        if page > 0:
            choices.append(questionary.Choice(
                title=[(f"fg:{theme.BRAND_ACCENT} bold", f"{theme.ICONS['prev']} Previous page")], value=_NAV_PREV,
            ))
        if page < total_pages - 1:
            choices.append(questionary.Choice(
                title=[(f"fg:{theme.BRAND_ACCENT} bold", f"{theme.ICONS['next']} Next page")], value=_NAV_NEXT,
            ))
        choices.append(questionary.Choice(
            title=[(f"fg:{theme.SUCCESS} bold", f"{theme.ICONS['success']} Done -- confirm {len(selected)} selected")], value=_NAV_DONE,
        ))

        header = f"Select JD(s) (space to check, enter to confirm this page, {len(selected)} selected so far):"
        result = questionary.checkbox(header, choices=choices, style=cli_art.QUESTIONARY_STYLE).ask()
        if result is None:
            return set()

        nav_choice = None
        for value in result:
            if value in (_NAV_PREV, _NAV_NEXT, _NAV_DONE):
                nav_choice = value
            else:
                selected.add(value)
        for value in page_values:
            if value not in result:
                selected.discard(value)

        if nav_choice == _NAV_PREV:
            page -= 1
        elif nav_choice == _NAV_NEXT:
            page += 1
        else:
            break

    return selected


def pick_and_process(
    pending_paths: list, process_one, action_verb: str, skip_confirm: bool = False, page_size: int = _PAGE_SIZE,
) -> tuple:
    """
    Shared flow: confirm gate -> batch_evaluate.evaluate_all_pending() ->
    paginated blue-box table + checkbox (via _paginated_checkbox()) ->
    process_one(path) for each selected path, best-score-first. Returns
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

    total_pages = (len(results) + page_size - 1) // page_size

    def render_page(start, end):
        current_page = start // page_size + 1
        progress_filled = min(current_page, total_pages)
        progress_bar = "█" * progress_filled + "░" * (total_pages - progress_filled)
        cli_art.render_fit_table(
            results[start:end], start_index=start + 1,
            title=f"Page {current_page}/{total_pages} [{progress_bar}] -- rows {start + 1}-{end} of {len(results)} JD(s) evaluated",
        )

    def choices_for_page(start, end, selected):
        choices = []
        for i, r in enumerate(results[start:end], start=start + 1):
            if r["error"]:
                continue
            choices.append(questionary.Choice(
                title=f"{i:>4}  {r['composite_score']:.2f}/5 | {r['recommendation']} | {r['company_name']} | {r['job_title']}",
                value=r["source_file"], checked=r["source_file"] in selected,
            ))
        return choices

    selected = _paginated_checkbox(len(results), render_page, choices_for_page, page_size=page_size)
    if not selected:
        cli_art.console.print("No jobs selected, nothing to do.")
        return (0, 0)

    ordered_paths = [r["source_file"] for r in valid if r["source_file"] in selected]
    completed = 0
    failed = 0
    for path in ordered_paths:
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


def browse_and_select_jds(statuses: list | None = None, page_size: int = _PAGE_SIZE) -> list:
    """The shared browse-and-act entry point: paginated blue-box table +
    checkbox (via _paginated_checkbox()) over every evaluated JD (pending
    or completed, or just one status if statuses is passed) so one or
    many can be selected at once. Each checkbox row only needs to carry
    enough to identify itself against the table above it (#,
    score/recommendation, company, title) -- the table already shows
    posting age, liveness, and follow-up so the checkbox line doesn't
    repeat them. Returns a list of the selected rows
    (list_all_evaluated_jds()'s dict shape, best-score-first) -- empty if
    there's nothing to show, the prompt is aborted (Ctrl-C), or nothing
    gets checked."""
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

    total_pages = (len(rows) + page_size - 1) // page_size

    def render_page(start, end):
        cli_art.render_pipeline_table(
            rows[start:end], start_index=start + 1,
            title=f"Page {start // page_size + 1}/{total_pages} -- rows {start + 1}-{end} of {len(rows)} evaluated JD(s)",
        )

    def choices_for_page(start, end, selected):
        choices = []
        for i, r in enumerate(rows[start:end], start=start + 1):
            evaluation = r["evaluation"]
            score_style = _RECOMMENDATION_STYLES.get(evaluation.get("recommendation"), "")
            label = [
                ("", f"{i:>4}  "),
                (score_style, f"{evaluation.get('composite_score'):.2f}/5 | {evaluation.get('recommendation')}"),
                ("", f" | {r['company'] or '?'} | {r['title'] or os.path.basename(r['path'])}"),
            ]
            choices.append(questionary.Choice(title=label, value=r["path"], checked=r["path"] in selected))
        return choices

    selected = _paginated_checkbox(len(rows), render_page, choices_for_page, page_size=page_size)
    if not selected:
        return []
    return [r for r in rows if r["path"] in selected]


