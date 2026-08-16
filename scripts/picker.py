"""
picker.py -- the shared "confirm gate -> evaluate every pending JD ->
checkbox picker -> process each selection" flow. Used by resume run
--pick, resume coverletter --pick, and the interactive menu's own
tailor-pick/coverletter-pick items -- one implementation instead of four.
"""

import os
import json

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
    anything, so the prompt doesn't imply a Gemini call that isn't real.

    A change here to the confirmation wording/behavior should be checked
    against cli._should_proceed() too -- these two copies aren't kept in
    sync automatically, only by convention."""
    if skip_confirm:
        return True
    return bool(questionary.confirm(
        f"About to {action} {count} pending JD(s) -- one real Gemini call each. Continue?",
        style=cli_art.QUESTIONARY_STYLE,
    ).ask())


def _truncate(text: str, max_len: int) -> str:
    """Ellipsize text to at most max_len characters, "..." included --
    pagination already bounds how many checkbox rows show at once, but a
    single row's company/title pair had no width bound of its own, so a
    long company or title wrapped mid-row on a narrow terminal instead of
    staying one row per selectable item."""
    if max_len <= 0:
        return ""
    if len(text) <= max_len:
        return text
    if max_len <= 3:
        return text[:max_len]
    return text[: max_len - 3] + "..."


# Fixed-width columns shared between render_picker_header()'s header line
# and every checkbox row below it, so the checkbox rows -- now the only
# place a JD's data actually renders -- line up under the header instead
# of the header and rows drifting out of alignment. REC_W (20) is sized
# to the longest real value, "Low-priority pursue".
_IDX_W = 4
_SCORE_W = 7
_REC_W = 20
_POSTED_W = 8
_STATUS_W = 10


def _company_title_budget(width: int, extra_fixed: int = 0) -> tuple:
    """Splits what's left of width -- after the fixed-width columns
    (index/score/recommendation/posted[/status]) and their separators --
    between company and title. 35/65, since job titles tend to run
    longer than company names, with a floor so both stay legible even on
    a narrow terminal. extra_fixed adds any columns beyond the shared
    index/score/recommendation/posted set (browse_and_select_jds' own
    Status column)."""
    # 6 columns' own trailing two-space separators (12) + render_picker_header's
    # Panel border/padding overhead (4) -- the header renders inside that Panel,
    # the checkbox rows below it don't, so without this the header (with its
    # extra chrome) wraps at a width the plain checkbox rows fit fine at,
    # breaking the very alignment this budget exists to guarantee.
    fixed = _IDX_W + _SCORE_W + _REC_W + _POSTED_W + extra_fixed + 16
    # Floor is deliberately low (18, not e.g. 30) -- a higher floor here
    # used to force `available` above what an ordinary 80-column terminal
    # actually has left, which guaranteed the header Panel wrapped onto a
    # second line on exactly the terminal width this needs to fit.
    available = max(width - fixed, 18)
    company_budget = max(int(available * 0.35), 8)
    title_budget = max(available - company_budget, 10)
    return company_budget, title_budget


def _row_cell(text, width: int, justify: str = "left") -> str:
    """Pads/truncates one cell to width -- the plain-text half of the
    header/row alignment contract (see render_picker_header's docstring
    in cli_art.py)."""
    text = _truncate(str(text), width)
    return text.rjust(width) if justify == "right" else text.ljust(width)


def _format_row(cells: list, widths: list, justifies: list, styles: list) -> list:
    """Builds a questionary Choice title -- a list of (style, text)
    tuples -- with each cell padded to the matching width in `widths`,
    so the row lines up under render_picker_header()'s header line."""
    return [
        (style, _row_cell(text, width, justify) + "  ")
        for text, width, justify, style in zip(cells, widths, justifies, styles)
    ]


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
        cli_art.render_picker_instructions()

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

        header = f"{len(selected)} selected so far -- pick this page's role(s):"
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
        company_budget, title_budget = _company_title_budget(cli_art.console.width)
        legend = "  ".join(f"[{color}]■[/{color}] {tier}" for tier, color in theme.RECOMMENDATION_COLORS.items())
        cli_art.render_picker_header(
            title=f"Page {current_page}/{total_pages} [{progress_bar}] -- rows {start + 1}-{end} of {len(results)} JD(s) evaluated",
            columns=[
                ("#", _IDX_W, "right"), ("Score", _SCORE_W, "right"),
                ("Recommendation", _REC_W, "left"), ("Company", company_budget, "left"),
                ("Title", title_budget, "left"), ("Posted", _POSTED_W, "right"),
            ],
            legend=legend,
        )

    def choices_for_page(start, end, selected):
        company_budget, title_budget = _company_title_budget(cli_art.console.width)
        choices = []
        for i, r in enumerate(results[start:end], start=start + 1):
            if r["error"]:
                continue
            style = _RECOMMENDATION_STYLES.get(r["recommendation"], "")
            posted = f"{r['posting_age_days']}d" if r.get("posting_age_days") is not None else "-"
            row = _format_row(
                [i, f"{r['composite_score']:.2f}/5", r["recommendation"] or "", r["company_name"] or "", r["job_title"] or "", posted],
                [_IDX_W, _SCORE_W, _REC_W, company_budget, title_budget, _POSTED_W],
                ["right", "right", "left", "left", "left", "right"],
                ["", style, style, "", "", ""],
            )
            choices.append(questionary.Choice(title=row, value=r["source_file"], checked=r["source_file"] in selected))
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
    # Use a Rich Text object so the numeric counts are plain (unstyled)
    # — tests assert against the raw substring "1 completed, 0 failed".
    from rich.text import Text

    msg = Text("\nPicked batch summary: ")
    msg.append(str(completed))
    msg.append(" completed, ")
    msg.append(str(failed))
    msg.append(" failed.")
    cli_art.console.print(msg)
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
            try:
                with open(path, "r", encoding="utf-8") as _f:
                    jd_data = json.load(_f)
            except (json.JSONDecodeError, OSError, UnicodeDecodeError):
                jd_data = {}
            rows.append({
                "path": path, "status": "Pending", "evaluation": evaluation,
                "liveness": jd_manager.read_liveness(path),
                "application": jd_manager.read_application_status(path),
                "title": title, "company": company,
                "description": jd_data.get("description", "") or "",
                "source_platform": jd_data.get("source_platform", "") or "",
                "source_url": jd_data.get("source_url") or jd_data.get("application_url", "") or "",
                "company_website": jd_data.get("company_website", "") or "",
                "skills": jd_data.get("skills") or [],
                "research": jd_manager.read_research(path),
                "coverage": jd_manager.read_coverage(path),
            })
    if "Completed" in statuses:
        for path in jd_manager.get_completed_jds():
            evaluation = jd_manager.read_evaluation(path)
            if not evaluation:
                continue
            title, company = jd_manager.extract_job_meta(path)
            try:
                with open(path, "r", encoding="utf-8") as _f:
                    jd_data = json.load(_f)
            except (json.JSONDecodeError, OSError, UnicodeDecodeError):
                jd_data = {}
            rows.append({
                "path": path, "status": "Completed", "evaluation": evaluation,
                "liveness": jd_manager.read_liveness(path),
                "application": jd_manager.read_application_status(path),
                "title": title, "company": company,
                "description": jd_data.get("description", "") or "",
                "source_platform": jd_data.get("source_platform", "") or "",
                "source_url": jd_data.get("source_url") or jd_data.get("application_url", "") or "",
                "company_website": jd_data.get("company_website", "") or "",
                "skills": jd_data.get("skills") or [],
                "research": jd_manager.read_research(path),
                "coverage": jd_manager.read_coverage(path),
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
        company_budget, title_budget = _company_title_budget(cli_art.console.width, extra_fixed=_STATUS_W + 2)
        legend = "  ".join(f"[{color}]■[/{color}] {tier}" for tier, color in theme.RECOMMENDATION_COLORS.items())
        cli_art.render_picker_header(
            title=f"Page {start // page_size + 1}/{total_pages} -- rows {start + 1}-{end} of {len(rows)} evaluated JD(s)",
            columns=[
                ("#", _IDX_W, "right"), ("Score", _SCORE_W, "right"),
                ("Recommendation", _REC_W, "left"), ("Company", company_budget, "left"),
                ("Title", title_budget, "left"), ("Posted", _POSTED_W, "right"),
                ("Status", _STATUS_W, "left"),
            ],
            legend=legend,
        )

    def choices_for_page(start, end, selected):
        company_budget, title_budget = _company_title_budget(cli_art.console.width, extra_fixed=_STATUS_W + 2)
        choices = []
        for i, r in enumerate(rows[start:end], start=start + 1):
            evaluation = r["evaluation"]
            style = _RECOMMENDATION_STYLES.get(evaluation.get("recommendation"), "")
            posted = evaluation.get("posting_age_days")
            row = _format_row(
                [
                    i, f"{evaluation.get('composite_score', 0):.2f}/5", evaluation.get("recommendation") or "",
                    r["company"] or "?", r["title"] or os.path.basename(r["path"]),
                    f"{posted}d" if posted is not None else "-", r["status"],
                ],
                [_IDX_W, _SCORE_W, _REC_W, company_budget, title_budget, _POSTED_W, _STATUS_W],
                ["right", "right", "left", "left", "left", "right", "left"],
                ["", style, style, "", "", "", ""],
            )
            choices.append(questionary.Choice(title=row, value=r["path"], checked=r["path"] in selected))
        return choices

    selected = _paginated_checkbox(len(rows), render_page, choices_for_page, page_size=page_size)
    if not selected:
        return []
    return [r for r in rows if r["path"] in selected]


def interactive_file_picker(prompt: str, start_dir: str = None, allowed_extensions: list = None) -> str:
    """A gorgeous, interactive TUI file picker that lets users navigate folders
    and pick files without tedious path-typing.
    """
    import sys
    if not start_dir:
        start_dir = os.path.expanduser("~/Downloads")
        if not os.path.exists(start_dir):
            start_dir = os.getcwd()
            
    current_dir = os.path.abspath(start_dir)
    
    while True:
        # Clear screen
        sys.stdout.write("\x1b[2J\x1b[H")
        sys.stdout.flush()
        
        cli_art.display_compact_banner("Interactive File Picker")
        cli_art.console.print(f"✦ [{theme.BRAND}]Current Directory:[/{theme.BRAND}] {current_dir}\n")
        
        choices = []
        # Parent directory choice
        parent_dir = os.path.dirname(current_dir)
        if parent_dir != current_dir:
            choices.append(questionary.Choice("📁 .. (Go Up)", value=".."))
            
        try:
            items = sorted(os.listdir(current_dir))
        except Exception as e:
            cli_art.console.print(f"[{theme.ERROR}]Error listing directory: {e}[/{theme.ERROR}]")
            questionary.press_any_key_to_continue().ask()
            # fallback to parent directory
            current_dir = parent_dir
            continue
            
        folders = []
        files = []
        
        for item in items:
            if item.startswith("."):
                continue # Skip hidden files
            full_path = os.path.join(current_dir, item)
            if os.path.isdir(full_path):
                folders.append(item)
            elif os.path.isfile(full_path):
                if allowed_extensions:
                    ext = os.path.splitext(item)[1].lower()
                    if ext in allowed_extensions:
                        files.append(item)
                else:
                    files.append(item)
                    
        # Add folders to choices
        for f in sorted(folders, key=lambda s: s.lower()):
            choices.append(questionary.Choice(f"📁 {f}/", value=os.path.join(current_dir, f)))
            
        # Add files to choices
        for f in sorted(files, key=lambda s: s.lower()):
            choices.append(questionary.Choice(f"📄 {f}", value=os.path.join(current_dir, f)))
            
        choices.append(questionary.Choice("❌ [Cancel]", value="__cancel__"))
        
        selected = questionary.select(
            prompt,
            choices=choices,
            style=cli_art.QUESTIONARY_STYLE
        ).ask()
        
        if not selected or selected == "__cancel__":
            return ""
            
        if selected == "..":
            current_dir = parent_dir
        elif os.path.isdir(selected):
            current_dir = selected
        else:
            return selected



