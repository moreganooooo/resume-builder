"""Lightweight banner/symbols for resume-builder's CLI, in job_automater's
cli_art.py style (rich Console/Panel) but trimmed down -- no hand-drawn ASCII
block art, just a clean styled banner."""

import os
import random
import time

from rich import box
from rich.console import Console
from rich.live import Live
from rich.markdown import Markdown
from rich.panel import Panel
from rich.table import Table
from rich.text import Text
from rich.theme import Theme as RichTheme

import followup
import jd_manager
import theme

# Overrides Rich's automatic quoted-text highlighting (its default
# "repr.str" is a dim ANSI green, distinct from -- and clashing with --
# theme.SUCCESS's brighter flat green) so any auto-highlighted quoted
# substring anywhere in this app's output stays on-palette.
console = Console(theme=RichTheme({"repr.str": theme.SUCCESS}))

SUCCESS = f"[bold {theme.SUCCESS}]{theme.colorize_icon('success')}[/bold {theme.SUCCESS}]"
ERROR = f"[bold {theme.ERROR}]{theme.colorize_icon('error')}[/bold {theme.ERROR}]"
WARNING = f"[bold {theme.WARNING}]{theme.colorize_icon('warning')}[/bold {theme.WARNING}]"
HINT = f"[bold {theme.INFO}]{theme.colorize_icon('hint')}[/bold {theme.INFO}]"

# Re-exported so menu.py/picker.py's existing `cli_art.QUESTIONARY_STYLE`
# references keep working unchanged.
QUESTIONARY_STYLE = theme.QUESTIONARY_STYLE

# Unified table header styling (used across all render_*_table functions)
TABLE_HEADER_STYLE = f"bold {theme.BRAND_ACCENT}"


def display_error(message: str) -> None:
    """A failure reads with real visual weight -- a bordered panel, not a
    bare icon-prefixed line."""
    body = f"[bold {theme.ERROR}]{theme.colorize_icon('error')}[/bold {theme.ERROR}] {message}"
    console.print(Panel(body, border_style=theme.ERROR, box=box.ROUNDED, padding=(0, 2)))


def display_success(message: str) -> None:
    """Stays lightweight (no border) -- this is the common case and a
    bordered panel for every success would get old fast."""
    console.print(f"[bold {theme.SUCCESS}]{theme.colorize_icon('success')}[/bold {theme.SUCCESS}] {message}")

# Raw block-letter lines, no markup -- color now comes from the diagonal
# gradient applied per-character in display_main_banner(), not a blanket
# style wrapper.
MAIN_BANNER_LINES = [
    "██████╗ ███████╗███████╗██╗   ██╗███╗   ███╗███████╗",
    "██╔══██╗██╔════╝██╔════╝██║   ██║████╗ ████║██╔════╝",
    "██████╔╝█████╗  ███████╗██║   ██║██╔████╔██║█████╗  ",
    "██╔══██╗██╔══╝  ╚════██║██║   ██║██║╚██╔╝██║██╔══╝  ",
    "██║  ██║███████╗███████║╚██████╔╝██║ ╚═╝ ██║███████╗",
    "╚═╝  ╚═╝╚══════╝╚══════╝ ╚═════╝ ╚═╝     ╚═╝╚══════╝",
    "",
    "██████╗ ██╗   ██╗██╗██╗     ██████╗ ███████╗██████╗ ",
    "██╔══██╗██║   ██║██║██║     ██╔══██╗██╔════╝██╔══██╗",
    "██████╔╝██║   ██║██║██║     ██║  ██║█████╗  ██████╔╝",
    "██╔══██╗██║   ██║██║██║     ██║  ██║██╔══╝  ██╔══██╗",
    "██████╔╝╚██████╔╝██║███████╗██████╔╝███████╗██║  ██║",
    "╚═════╝  ╚═════╝ ╚═╝╚══════╝╚═════╝ ╚══════╝╚═╝  ╚═╝",]

SUBTITLE = "Custom Resumes & Cover Letters, Powered by Gemini\n"


def _lerp_hex(start_hex: str, end_hex: str, t: float) -> str:
    """Linearly interpolates between two '#rrggbb' colors at t in [0, 1]."""
    start_rgb = tuple(int(start_hex[i:i + 2], 16) for i in (1, 3, 5))
    end_rgb = tuple(int(end_hex[i:i + 2], 16) for i in (1, 3, 5))
    mixed = tuple(round(start_rgb[c] + (end_rgb[c] - start_rgb[c]) * t) for c in range(3))
    return "#{:02x}{:02x}{:02x}".format(*mixed)


def _gradient_grid(lines: list, start_hex: str, end_hex: str) -> list:
    """Returns a per-character color grid (list of list of hex strings,
    parallel to `lines`) -- a diagonal sweep from start_hex (top-left) to
    end_hex (bottom-right), keyed by (row + col) / (max_row + max_col)."""
    max_row = max(len(lines) - 1, 1)
    max_col = max((len(line) for line in lines), default=1)
    max_col = max(max_col - 1, 1)
    denom = max_row + max_col

    grid = []
    for row, line in enumerate(lines):
        grid.append([_lerp_hex(start_hex, end_hex, (row + col) / denom) for col in range(len(line))])
    return grid


def _render_grid(lines: list, grid: list, threshold: int = None) -> Text:
    """Builds one multi-line Rich Text from lines/grid. threshold is the
    max (row + col) diagonal index to reveal; None reveals everything."""
    text = Text()
    for row, line in enumerate(lines):
        for col, ch in enumerate(line):
            if threshold is not None and (row + col) > threshold:
                text.append(" ")
            else:
                text.append(ch, style=grid[row][col])
        text.append("\n")
    return text


def _reveal_banner(lines: list, grid: list, render_frame) -> None:
    """Drives a rich.live.Live diagonal-wipe reveal. render_frame(threshold)
    returns the Rich renderable for a given frame (threshold=None means
    fully revealed). Falls back to a single fully-revealed print when
    stdout isn't a real terminal (piped output, non-interactive contexts,
    tests) -- Live's redraws don't compose safely with non-TTY output."""
    if not console.is_terminal:
        console.print(render_frame(None))
        return

    max_row = max(len(lines) - 1, 1)
    max_col = max((len(line) for line in lines), default=1)
    max_col = max(max_col - 1, 1)
    max_threshold = max_row + max_col

    frame_count = 30
    total_seconds = 1.6
    with Live(console=console, refresh_per_second=30, transient=False) as live:
        for frame in range(frame_count + 1):
            threshold = round(max_threshold * frame / frame_count)
            live.update(render_frame(threshold))
            time.sleep(total_seconds / frame_count)


def _stats_line_text() -> str:
    """Real, live data -- no new persistence. pending count comes from
    jd_manager.get_pending_jds(); tailored count comes from the append-only
    tracker CSV, NOT from jds/completed/'s file count -- archive_jd() moves
    files out of that directory, which would make an "All-Time" total go
    down. This walks the whole JD corpus, so it is expensive: call it once
    and reuse the string, never once per animation frame."""
    pending = len(jd_manager.get_pending_jds())
    tailored = jd_manager.count_completed_resumes()
    return f"{pending} Roles Currently Awaiting Resume Creation · {tailored} Resumes Customized All-Time"


def display_main_banner() -> None:
    grid = _gradient_grid(MAIN_BANNER_LINES, theme.BRAND, theme.BRAND_ACCENT)
    # Hoisted out of render_frame deliberately: the stats are constant for the
    # length of the animation, but calling this per-frame walked the entire JD
    # corpus 31 times and turned a 1.6s reveal into ~27s -- the first thing
    # every user ever experiences. Compute once, close over the string.
    stats_line = _stats_line_text()

    def render_frame(threshold):
        body = _render_grid(MAIN_BANNER_LINES, grid, threshold=threshold)
        body.append(SUBTITLE, style="bold")
        body.append(stats_line, style=theme.INFO)
        return Panel(body, border_style=theme.BRAND, box=box.DOUBLE, padding=(1, 2))

    _reveal_banner(MAIN_BANNER_LINES, grid, render_frame)


def display_stats_line() -> None:
    console.print(_stats_line_text(), style=theme.INFO)


TIPS = [
    "resume run --pick lets you interactively choose which pending JDs to tailor, instead of the whole batch.",
    "resume test -v lists every test by name instead of just dots.",
    "New here? The menu's top \"New User? Start Here!\" option bootstraps a bullet bank from your existing resume or LinkedIn export.",
    "resume polish lets you conversationally tweak an already-generated resume or cover letter.",
    "Evaluating a JD persists its score onto the file itself, so \"Customize Resume for a Specific JD\" never re-scores it.",
]


def display_tip() -> None:
    """Boxed and shown last in the launch sequence -- reads as a distinct
    callout rather than blending into the stats line above it."""
    console.print()  # Blank line before tip for separation
    tip = random.choice(TIPS)
    console.print(Panel(
        f"{theme.colorize_icon('hint')}  Did you know? {tip}",
        border_style=theme.BRAND_ACCENT, box=box.ROUNDED, padding=(0, 2),
    ))


def display_breadcrumb() -> None:
    """Replaces a full banner repaint on menu loop-back -- one line, not
    another full-width panel every time an action finishes."""
    console.print()  # Blank line before breadcrumb for separation
    console.rule(f"[bold {theme.BRAND}]›[/bold {theme.BRAND}] resume-builder", style="dim", align="left")


def display_whats_next_panel() -> None:
    console.print(f"\n[bold {theme.BRAND}]What's next?[/bold {theme.BRAND}]")


def display_bootstrap_intro(doc_count: int) -> None:
    body = (
        f"Here's what's about to happen:\n\n"
        f"I'll read through your {doc_count} document(s) and pull out real "
        f"achievements, figure out which company each one belongs to, tag "
        f"them by skill area, then run them through a quality-check, "
        f"cleanup, and rewrite pipeline so you end up with a polished "
        f"bullet bank.\n\n"
        f"Two of these steps make real API calls and can take a few "
        f"minutes — I'll let you know before each one."
    )
    console.print(Panel(body, title="New User Bootstrap", border_style=theme.SUCCESS, box=box.ROUNDED, padding=(1, 2)))


# Same four tiers as orchestrator.FitEvaluationSchema's `recommendation`
# Literal -- sourced from theme.py so this table and picker.py's checkbox
# list are provably one palette, not two hand-maintained copies. "Skip"
# is intentionally not dimmed here (it was previously "red dim" in this
# file only) -- unified to match picker.py's plain-hex treatment.
_RECOMMENDATION_COLORS = theme.RECOMMENDATION_COLORS


def display_banner(subtitle: str = "") -> None:
    """Direct single-command invocations (e.g. `resume tailor file.json`)
    get the same lightweight rule-line treatment as menu loop-backs
    (display_breadcrumb()) rather than a full boxed panel -- consistent
    with "don't repaint a whole banner for one action", and theme.BRAND
    instead of a hardcoded "cyan"."""
    title = f"[bold {theme.BRAND}]›[/bold {theme.BRAND}] resume-builder"
    if subtitle:
        title += f" [dim]— {subtitle}[/dim]"
    console.rule(title, style="dim", align="left")


def _short_why(why: str, max_len: int = 70) -> str:
    """Truncates evaluate_fit()'s full 2-4 sentence `why` to a single
    short descriptor for compact table display -- the full text is still
    persisted in full (jd_manager.save_evaluation()) for anyone who wants
    to read the whole rationale, this is just the at-a-glance version."""
    why = (why or "").strip()
    if not why:
        return "-"
    first_sentence = why.split(". ")[0].rstrip(".")
    if len(first_sentence) <= max_len:
        return first_sentence
    return first_sentence[:max_len].rstrip() + "..."


# Mirrors orchestrator.STALE_POSTING_THRESHOLD_DAYS -- kept as a plain
# constant here rather than importing orchestrator (a heavy module with
# its own Gemini client dependency) into this presentation layer just
# for one number.
_POSTING_AGE_STALE_DAYS = 7
_POSTING_AGE_VERY_STALE_DAYS = 21


def _posting_age_cell(days: int | None) -> str:
    """Colored "Nd" cell for how long a posting's been up -- green within
    the not-yet-penalized window, amber into the scoring-penalty range,
    red well past it. "-" when no post date or scan-discovery fallback
    was available at all (see jd_manager.compute_posting_age_days())."""
    if days is None:
        return "-"
    if days <= _POSTING_AGE_STALE_DAYS:
        color = theme.SUCCESS
    elif days <= _POSTING_AGE_VERY_STALE_DAYS:
        color = theme.WARNING
    else:
        color = theme.ERROR
    return f"[{color}]{days}d[/{color}]"


def render_fit_table(results: list, start_index: int = 1, title: str | None = None) -> None:
    """Renders batch_evaluate.evaluate_all_pending()'s result list -- or a
    page-sized slice of it -- as a Rich Table, colored by recommendation
    tier (modeled on job_automater's display_job_table(), cli.py:73-142).
    results is expected pre-sorted (evaluate_all_pending() already sorts
    best-first, errors-last). start_index numbers the "#" column from an
    arbitrary offset so a paginated caller (picker.pick_and_process())
    can show true positions (51, 52, ...) instead of every page
    restarting at 1. title overrides the panel's title -- defaults to a
    plain count for non-paginated callers. The "Why" column is a short
    excerpt, not the model's full reasoning -- lets a lower-scored-but-
    higher-priority role get spot-checked at a glance instead of needing
    to open its JD JSON to see why it scored the way it did."""
    table = Table(box=box.SIMPLE_HEAD, show_header=True, header_style=TABLE_HEADER_STYLE)
    table.add_column("#", justify="right", style="dim")
    table.add_column("Score", justify="right")
    table.add_column("Recommendation")
    table.add_column("Company")
    table.add_column("Title")
    table.add_column("Posted", justify="right")
    table.add_column("Why")

    for i, r in enumerate(results, start_index):
        if r["error"]:
            table.add_row(str(i), f"[{theme.ERROR}]ERROR[/{theme.ERROR}]", "-", r["company_name"], r["job_title"], "-", "-")
            continue
        color = _RECOMMENDATION_COLORS.get(r["recommendation"], theme.MUTED)
        legitimacy = r.get("posting_legitimacy")
        recommendation_text = f"[{color}]{r['recommendation']}[/{color}]"
        if legitimacy and legitimacy != "High Confidence":
            flag_color = theme.WARNING if legitimacy == "Proceed with Caution" else theme.ERROR
            recommendation_text += f" [{flag_color}]({theme.colorize_icon('warning')} {legitimacy})[/{flag_color}]"
        table.add_row(
            str(i),
            f"[{color}]{r['composite_score']:.2f}/5[/{color}]",
            recommendation_text,
            r["company_name"],
            r["job_title"],
            _posting_age_cell(r.get("posting_age_days")),
            _short_why(r.get("why")),
        )

    legend = "  ".join(f"[{color}]■[/{color}] {tier}" for tier, color in _RECOMMENDATION_COLORS.items())
    console.print(Panel(
        table, title=title or f"{len(results)} JD(s) evaluated", subtitle=legend,
        border_style=theme.BRAND, box=box.ROUNDED,
    ))


def _liveness_cell(liveness: dict | None) -> str:
    if not liveness or not liveness.get("checked_at"):
        return "-"
    date = liveness["checked_at"][:10]
    result = liveness.get("result", "")
    color = {"active": theme.SUCCESS, "likely_active": theme.SUCCESS, "expired": theme.ERROR}.get(result, theme.WARNING)
    return f"[{color}]{result or '?'}[/{color}] ({date})"


_FOLLOWUP_COLORS = {"overdue": theme.ERROR, "cold": theme.MUTED, "waiting": theme.SUCCESS}


def _followup_cell(application: dict | None) -> str:
    if not application:
        return "-"
    status = application.get("status", "?")
    urgency = followup.compute_urgency(application)
    if not urgency:
        return status
    color = _FOLLOWUP_COLORS.get(urgency, theme.MUTED)
    return f"{status} [{color}]({urgency})[/{color}]"


_NARROW_TERMINAL_COLUMNS = 110


def render_pipeline_table(rows: list, start_index: int = 1, title: str | None = None) -> None:
    """Renders picker.list_all_evaluated_jds()'s row list -- or a
    page-sized slice of it -- as a bordered table (the "blue box" browse
    view). start_index numbers the "#" column from an arbitrary offset
    so a paginated caller (picker.browse_and_select_jds()) can show true
    positions (51, 52, ...) instead of every page restarting at 1. title
    overrides the panel's title -- defaults to a plain count for
    non-paginated callers.

    Nine columns with no explicit sizing used to mean Rich divided any
    width deficit evenly across all of them, eating the header text itself
    below ~120 columns ("Recom…", "Compa…", "Liven…") -- 80 and 100 are
    ordinary terminal widths, not edge cases (B22). Fixed widths on the
    short columns (#/Score/Posted/Status) protect their headers; Title
    gets the one `ratio` column so it absorbs whatever's left; Last
    Liveness/Follow-up -- the two least essential at a glance -- drop
    entirely below _NARROW_TERMINAL_COLUMNS rather than shrinking
    everything else past legibility."""
    narrow = console.width < _NARROW_TERMINAL_COLUMNS
    table = Table(box=box.SIMPLE_HEAD, show_header=True, header_style=TABLE_HEADER_STYLE, expand=True)
    table.add_column("#", justify="right", style="dim", width=3, no_wrap=True)
    table.add_column("Score", justify="right", width=6, no_wrap=True)
    table.add_column("Recommendation", min_width=15, no_wrap=True, overflow="ellipsis")
    table.add_column("Company", min_width=10, no_wrap=True, overflow="ellipsis")
    table.add_column("Title", ratio=1, min_width=15, no_wrap=True, overflow="ellipsis")
    table.add_column("Posted", justify="right", width=8, no_wrap=True)
    table.add_column("Status", width=10, no_wrap=True, overflow="ellipsis")
    if not narrow:
        table.add_column("Last Liveness", width=22, no_wrap=True, overflow="ellipsis")
        # 20 fits the longest real cell ("Interview (waiting)") without
        # truncating the urgency word itself -- that's the part that
        # actually matters at a glance, unlike Last Liveness's date.
        table.add_column("Follow-up", width=20, no_wrap=True, overflow="ellipsis")

    for i, r in enumerate(rows, start_index):
        evaluation = r["evaluation"]
        color = _RECOMMENDATION_COLORS.get(evaluation.get("recommendation"), theme.MUTED)
        cells = [
            str(i),
            f"[{color}]{evaluation.get('composite_score', 0):.2f}/5[/{color}]",
            f"[{color}]{evaluation.get('recommendation')}[/{color}]",
            r["company"] or "?",
            r["title"] or "?",
            _posting_age_cell(evaluation.get("posting_age_days")),
            r["status"],
        ]
        if not narrow:
            cells.append(_liveness_cell(r.get("liveness")))
            cells.append(_followup_cell(r.get("application")))
        table.add_row(*cells)

    subtitle = (
        "[dim]Last Liveness/Follow-up hidden below ~110 columns -- widen your terminal to see them[/dim]"
        if narrow else None
    )
    console.print(Panel(
        table, title=title or f"{len(rows)} evaluated JD(s)", subtitle=subtitle,
        border_style=theme.BRAND, box=box.ROUNDED,
    ))


def render_polish_table(rows: list, start_index: int = 1, title: str | None = None) -> None:
    """Renders polish.pick_polish_target()'s candidate list -- or a
    page-sized slice of it -- as a bordered table (the same "blue box"
    style as render_pipeline_table()/render_fit_table(), for visual
    consistency across every large picker in this program). Each row is
    {"path": ..., "label": "Resume" or "Cover Letter"} -- doc-type
    detection stays in polish.py to avoid a cli_art<->polish import
    cycle. start_index/title behave exactly like
    render_pipeline_table()'s."""
    table = Table(box=box.SIMPLE_HEAD, show_header=True, header_style=TABLE_HEADER_STYLE)
    table.add_column("#", justify="right", style="dim")
    table.add_column("Type")
    table.add_column("Filename")
    table.add_column("Modified", justify="right")

    for i, r in enumerate(rows, start_index):
        modified = time.strftime("%Y-%m-%d %H:%M", time.localtime(os.path.getmtime(r["path"])))
        table.add_row(str(i), r["label"], os.path.basename(r["path"]), modified)

    console.print(Panel(
        table, title=title or f"{len(rows)} document(s)", border_style=theme.BRAND, box=box.ROUNDED,
    ))


# (subscore dict key, display label) grouped by layer, so the
# comparison table can show a section header per layer instead of one
# flat list of 18 dimensions with no indication of what they mean.
_FIT_DIMENSION_GROUPS = [
    ("Fit", "fit_subscores", {
        "functional_alignment": "Functional", "north_star_alignment": "North Star",
        "level_plausibility": "Level Fit", "work_style_sustainability": "Sustainability",
        "tools_process_overlap": "Tools",
    }),
    ("Interview odds", "interview_odds_subscores", {
        "title_continuity": "Title Continuity", "evidence_match": "Evidence Match",
        "domain_credibility": "Domain Cred.", "recruiter_legibility": "Recruiter Legibility",
        "narrative_burden": "Narrative Burden", "funnel_friction": "Funnel Friction",
    }),
    ("Practical pursue", "practical_pursue_subscores", {
        "remote_quality": "Remote", "compensation_viability": "Comp", "growth_value": "Growth",
        "time_to_offer": "Speed", "company_reputation": "Reputation",
        "cultural_signals": "Culture", "posting_legitimacy_score": "Legitimacy",
    }),
]


def render_comparison_table(rows: list) -> None:
    """Side-by-side comparison of 2+ already-evaluated JDs (the "Multi-job
    comparison mode" backlog item) -- one column per JD, one row per
    dimension grouped under its layer (fit / interview odds / practical
    pursue), so a strength/weakness pattern is visible at a glance rather
    than needing to hold several single-JD views in your head."""
    table = Table(box=box.SIMPLE_HEAD, show_header=True, header_style=TABLE_HEADER_STYLE)
    table.add_column("")
    for r in rows:
        table.add_column(f"{r['company'] or '?'}\n{r['title'] or '?'}")

    def _row(label: str, values: list) -> None:
        table.add_row(label, *[str(v) for v in values])

    _row("Score", [f"{r['evaluation'].get('composite_score', 0):.2f}/5" for r in rows])
    _row("Recommendation", [
        f"[{_RECOMMENDATION_COLORS.get(r['evaluation'].get('recommendation'), 'white')}]"
        f"{r['evaluation'].get('recommendation')}[/{_RECOMMENDATION_COLORS.get(r['evaluation'].get('recommendation'), 'white')}]"
        for r in rows
    ])
    _row("Archetype", [r["evaluation"].get("archetype") or "-" for r in rows])
    _row("Posted", [_posting_age_cell(r["evaluation"].get("posting_age_days")) for r in rows])

    for group_label, subscores_key, labels in _FIT_DIMENSION_GROUPS:
        table.add_section()
        _row(f"[bold]{group_label}[/bold]", ["" for _ in rows])
        for dim, label in labels.items():
            _row(label, [r["evaluation"].get(subscores_key, {}).get(dim, "-") for r in rows])

    console.print(Panel(
        table, title=f"Comparing {len(rows)} JD(s)", border_style=theme.BRAND, box=box.ROUNDED,
    ))


_STAGE_STATUS_COLORS = {"Up to date": theme.SUCCESS, "Stale": theme.WARNING, "In progress": theme.INFO}


def render_bullet_bank_status(stage_rows: list, maintenance_rows: list, title: str = "Bullet Bank Pipeline Status") -> None:
    """stage_rows: (number, label, status, detail) tuples, in pipeline
    order. maintenance_rows: (label, detail) tuples for the non-sequential
    triage/retire scripts. title is overridable so bootstrap_menu.py can
    reuse this exact table shape for onboarding-phase status instead of
    carrying its own near-identical render function."""
    table = Table(box=box.SIMPLE_HEAD, show_header=True, header_style=TABLE_HEADER_STYLE)
    table.add_column("#", justify="right", style="dim")
    table.add_column("Stage")
    table.add_column("Status")

    for number, label, status, detail in stage_rows:
        color = _STAGE_STATUS_COLORS.get(status)
        status_text = f"[{color}]{status}[/{color}]" if color else f"[dim]{status}[/dim]"
        if detail:
            status_text += f" ({detail})"
        table.add_row(str(number), label, status_text)

    for label, detail in maintenance_rows:
        table.add_row("-", label, detail)

    console.print(Panel(table, title=title, border_style=theme.BRAND, box=box.ROUNDED))


def render_scan_report(source_results: list, total_written: int) -> None:
    """Renders scan.run_scan()'s per-source results -- one row per source
    in a summary table, then the actual new postings grouped under a
    themed divider per source. Deliberately doesn't print an
    "already known" line per skipped posting the way the old plain-print
    version did (noisy after the first run of the day, tens/hundreds of
    lines for zero new information) -- just a Skipped count in the
    summary table; anything genuinely new is what earns a visible line.
    source_results: [{"source", "fetched", "written", "skipped",
    "dropped_expired", "new_jobs": [{"company", "title"}], "warnings":
    [{"provider_id", "kind", "reason", "count"}], "error": str|None}, ...].
    "dropped_expired" is optional (only present when scan.run_scan()'s
    verify pass actually ran) -- a real Playwright check caught the
    posting as already-dead before it ever became a visible hit, distinct
    from "skipped" (already-known, not re-checked at all). "warnings" is
    pre-grouped by scan._summarize_warnings() (provider_id/kind/reason,
    most-frequent-first) -- e.g. workday HTTP 404s x44 renders as one row
    here, not 44 raw WARNING:root: lines the way the old plain-logging
    version did."""
    table = Table(box=box.SIMPLE_HEAD, show_header=True, header_style=TABLE_HEADER_STYLE)
    table.add_column("Source")
    table.add_column("Fetched", justify="right")
    table.add_column("New", justify="right")
    table.add_column("Skipped", justify="right")
    table.add_column("Expired", justify="right")
    table.add_column("Issues", justify="right")

    for r in source_results:
        if r.get("error"):
            table.add_row(r["source"], "-", "-", "-", "-", "-", style=theme.ERROR)
            continue
        new_count = r["written"]
        new_style = theme.SUCCESS if new_count else "dim"
        dropped = r.get("dropped_expired", 0)
        dropped_style = theme.WARNING if dropped else "dim"
        issue_count = sum(w["count"] for w in r.get("warnings", []))
        issue_style = theme.WARNING if issue_count else "dim"
        table.add_row(
            r["source"], str(r["fetched"]),
            f"[{new_style}]{new_count}[/{new_style}]", str(r["skipped"]),
            f"[{dropped_style}]{dropped}[/{dropped_style}]",
            f"[{issue_style}]{issue_count}[/{issue_style}]",
        )

    console.print(Panel(
        table, title="Scan Results", border_style=theme.BRAND, box=box.ROUNDED,
        subtitle=f"{total_written} new JD(s) written to jds/",
    ))

    for r in source_results:
        if not r.get("new_jobs"):
            continue
        console.print()
        console.rule(f"[bold {theme.BRAND}]{r['source']}[/bold {theme.BRAND}] — {len(r['new_jobs'])} new", style="dim", align="left")
        for job in r["new_jobs"]:
            console.print(f"  {theme.colorize_icon('success')} [bold]{job['company']}[/bold] — {job['title']}")

    _render_scan_warnings(source_results)


_WARNING_KIND_LABELS = {
    "provider_failed": "listing fetch failed",
    "posting_text_failed": "description fetch failed",
    # From run_provider.mjs's JSON error envelope (B27) -- a specific reason
    # instead of the generic "listing fetch failed" above.
    "auth": "auth failed",
    "quota": "quota exhausted",
    "network": "network error",
    "config": "misconfigured",
    # From scan_boards.py's own description-quality check (B36).
    "thin_description": "thin description",
}


def _render_scan_warnings(source_results: list) -> None:
    """One grouped table across every source with issues -- see
    render_scan_report()'s docstring for why grouping matters here."""
    rows = [
        (r["source"], w["provider_id"] or "-", _WARNING_KIND_LABELS.get(w["kind"], w["kind"]), w["reason"], w["count"])
        for r in source_results for w in r.get("warnings", [])
    ]
    if not rows:
        return

    console.print()
    console.rule(f"[bold {theme.WARNING}]{theme.colorize_icon('warning')} Issues[/bold {theme.WARNING}]", style="dim", align="left")
    table = Table(box=box.SIMPLE_HEAD, show_header=True, header_style=TABLE_HEADER_STYLE)
    table.add_column("Source")
    table.add_column("Provider")
    table.add_column("Stage")
    table.add_column("Reason")
    table.add_column("Count", justify="right")
    for source, provider_id, stage, reason, count in rows:
        table.add_row(source, provider_id, stage, reason, f"[{theme.WARNING}]{count}[/{theme.WARNING}]")
    console.print(table)


# Single source of truth for the shortcuts cheat sheet -- both `resume
# help` (scripts/resume-cli.sh, which shells out to `python scripts/cli.py
# help`) and the interactive menu's Help entry render this same list, so
# there's exactly one place to update instead of two copies drifting apart.
HELP_ENTRIES = [
    ("resume", "launch the interactive menu"),
    ("resume bootstrap", "new-user setup: ingest documents, draft your profile, build the bullet bank"),
    ("resume activate", "cd into the project and activate the venv (stays active in this shell)"),
    ("resume cd", "just cd into the project"),
    ("resume run", "tailor+render every pending JD in jds/ (batch mode)"),
    ("resume run jds/x.txt", "tailor+render one specific JD file"),
    ("resume run --pick", "interactively select which pending JD(s) to tailor"),
    ("resume coverletter jds/x.txt", "generate + render a cover letter for one JD"),
    ("resume coverletter --pick", "interactively select which pending JD(s) to generate a cover letter for"),
    ("resume evaluate jds/x.txt", "score a JD's fit (go/no-go) without building a resume"),
    ("resume evaluate", "score every pending JD at once"),
    ("resume scan", "pull new postings into jds/ (verifies each is actually live via headless browser by default)"),
    ("resume scan --source jobright", "pull from just one source (jobright, linkedin, boards, ats)"),
    ("resume scan --no-verify", "skip the liveness check on new postings (faster, but stale listings may slip through)"),
    ("resume liveness", "check every pending JD's posting URL, move expired ones out"),
    ("resume polish", "interactively polish an already-generated resume/cover letter"),
    ("resume test", "run the full test suite (compact: dots + summary)"),
    ("resume test -v", "same, but lists every test by name"),
    ("resume test -vv", "same, but shows the app's own logging too"),
    ("resume doctor", "check dependencies/assets/config, then run the test suite"),
    ("resume doctor --skip-tests", "same, but skip the (slower) test-suite run"),
]


def display_help() -> None:
    table = Table(box=box.SIMPLE_HEAD, show_header=True, header_style=TABLE_HEADER_STYLE)
    table.add_column("Command")
    table.add_column("What it does")
    for command, description in HELP_ENTRIES:
        table.add_row(command, description)
    console.print(Panel(table, title="resume-builder shortcuts", border_style=theme.BRAND, box=box.ROUNDED))


def display_applications_tracker(content: str) -> None:
    """Renders data/applications.md's raw markdown content directly in the
    terminal via Rich's built-in Markdown renderer -- the table and each
    row's clickable "[Apply](source_url)" link render as-is, no custom
    parsing needed since the file is already valid GFM markdown."""
    console.print(Markdown(content))


def render_doctor_report(checks: list, test_result: tuple | None = None) -> None:
    """checks: doctor.run_checks()'s result list. test_result: doctor.run_
    test_suite()'s (passed, summary) tuple, or None if the test-suite step
    was skipped/declined. Ends with a plain-English "N passed, M problems
    found" line and a one-line suggested fix per failing check, so nothing
    requires opening a JSON blob to act on."""
    table = Table(box=box.SIMPLE_HEAD, show_header=True, header_style=TABLE_HEADER_STYLE)
    table.add_column("Check")
    table.add_column("Status")
    table.add_column("Detail")

    failed = []
    for c in checks:
        icon = f"[{theme.SUCCESS}]{theme.colorize_icon('success')}[/{theme.SUCCESS}]" if c["passed"] else f"[{theme.ERROR}]{theme.colorize_icon('error')}[/{theme.ERROR}]"
        table.add_row(c["name"], icon, c["detail"])
        if not c["passed"]:
            failed.append(c)

    console.print(Panel(table, title="Doctor Checks", border_style=theme.BRAND, box=box.ROUNDED))

    if test_result is not None:
        test_passed, test_summary = test_result
        icon = SUCCESS if test_passed else ERROR
        console.print(f"\n{icon} Test suite: {test_summary}")

    if failed:
        console.print(f"\n[bold {theme.ERROR}]{len(failed)} problem(s) found:[/bold {theme.ERROR}]")
        for c in failed:
            console.print(f"  {theme.colorize_icon('warning')} {c['name']}: {c['fix']}")
    else:
        console.print(f"\n{SUCCESS} All checks passed.")
