"""Lightweight banner/symbols for resume-builder's CLI, in job_automater's
cli_art.py style (rich Console/Panel) but trimmed down -- no hand-drawn ASCII
block art, just a clean styled banner."""

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

import jd_manager
import theme

# Overrides Rich's automatic quoted-text highlighting (its default
# "repr.str" is a dim ANSI green, distinct from -- and clashing with --
# theme.SUCCESS's brighter flat green) so any auto-highlighted quoted
# substring anywhere in this app's output stays on-palette.
console = Console(theme=RichTheme({"repr.str": theme.SUCCESS}))

SUCCESS = f"[bold {theme.SUCCESS}]{theme.ICONS['success']}[/bold {theme.SUCCESS}]"
ERROR = f"[bold {theme.ERROR}]{theme.ICONS['error']}[/bold {theme.ERROR}]"
WARNING = f"[bold {theme.WARNING}]{theme.ICONS['warning']}[/bold {theme.WARNING}]"
HINT = f"[bold {theme.INFO}]{theme.ICONS['hint']}[/bold {theme.INFO}]"

# Re-exported so menu.py/picker.py's existing `cli_art.QUESTIONARY_STYLE`
# references keep working unchanged.
QUESTIONARY_STYLE = theme.QUESTIONARY_STYLE


def display_error(message: str) -> None:
    """A failure reads with real visual weight -- a bordered panel, not a
    bare icon-prefixed line."""
    body = f"[bold {theme.ERROR}]{theme.ICONS['error']}[/bold {theme.ERROR}] {message}"
    console.print(Panel(body, border_style=theme.ERROR, box=box.ROUNDED, padding=(0, 2)))


def display_success(message: str) -> None:
    """Stays lightweight (no border) -- this is the common case and a
    bordered panel for every success would get old fast."""
    console.print(f"[bold {theme.SUCCESS}]{theme.ICONS['success']}[/bold {theme.SUCCESS}] {message}")

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
    jd_manager.get_pending_jds(); tailored count is jds/completed/'s file
    count (both already create their directory if missing)."""
    pending = len(jd_manager.get_pending_jds())
    tailored = len(jd_manager.get_completed_jds())
    return f"{pending} Roles Currently Awaiting Resume Creation · {tailored} Resumes Customized All-Time"


def display_main_banner() -> None:
    grid = _gradient_grid(MAIN_BANNER_LINES, theme.BRAND, theme.BRAND_ACCENT)

    def render_frame(threshold):
        body = _render_grid(MAIN_BANNER_LINES, grid, threshold=threshold)
        body.append(SUBTITLE, style="bold")
        body.append(_stats_line_text(), style=theme.INFO)
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
    tip = random.choice(TIPS)
    console.print(Panel(
        f"{theme.ICONS['hint']}  Did you know? {tip}",
        border_style=theme.BRAND_ACCENT, box=box.ROUNDED, padding=(0, 2),
    ))


def display_breadcrumb() -> None:
    """Replaces a full banner repaint on menu loop-back -- one line, not
    another full-width panel every time an action finishes."""
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


def render_fit_table(results: list) -> None:
    """Renders batch_evaluate.evaluate_all_pending()'s result list as a
    Rich Table, colored by recommendation tier (modeled on job_automater's
    display_job_table(), cli.py:73-142). results is expected pre-sorted
    (evaluate_all_pending() already sorts best-first, errors-last). The
    "Why" column is a short excerpt, not the model's full reasoning --
    lets a lower-scored-but-higher-priority role get spot-checked at a
    glance instead of needing to open its JD JSON to see why it scored
    the way it did."""
    table = Table(box=box.SIMPLE_HEAD, show_header=True, header_style="bold magenta")
    table.add_column("#", justify="right", style="dim")
    table.add_column("Score", justify="right")
    table.add_column("Recommendation")
    table.add_column("Company")
    table.add_column("Title")
    table.add_column("Why")

    for i, r in enumerate(results, 1):
        if r["error"]:
            table.add_row(str(i), f"[{theme.ERROR}]ERROR[/{theme.ERROR}]", "-", r["company_name"], r["job_title"], "-")
            continue
        color = _RECOMMENDATION_COLORS.get(r["recommendation"], "white")
        legitimacy = r.get("posting_legitimacy")
        recommendation_text = f"[{color}]{r['recommendation']}[/{color}]"
        if legitimacy and legitimacy != "High Confidence":
            flag_color = theme.WARNING if legitimacy == "Proceed with Caution" else theme.ERROR
            recommendation_text += f" [{flag_color}]({theme.ICONS['warning']} {legitimacy})[/{flag_color}]"
        table.add_row(
            str(i),
            f"[{color}]{r['composite_score']:.2f}/5[/{color}]",
            recommendation_text,
            r["company_name"],
            r["job_title"],
            _short_why(r.get("why")),
        )

    legend = "  ".join(f"[{color}]■[/{color}] {tier}" for tier, color in _RECOMMENDATION_COLORS.items())
    console.print(Panel(
        table, title=f"{len(results)} JD(s) evaluated", subtitle=legend,
        border_style=theme.BRAND, box=box.ROUNDED,
    ))


def _liveness_cell(liveness: dict | None) -> str:
    if not liveness or not liveness.get("checked_at"):
        return "-"
    date = liveness["checked_at"][:10]
    result = liveness.get("result", "")
    color = {"active": theme.SUCCESS, "likely_active": theme.SUCCESS, "expired": theme.ERROR}.get(result, theme.WARNING)
    return f"[{color}]{result or '?'}[/{color}] ({date})"


def render_pipeline_table(rows: list) -> None:
    """Renders picker.list_all_evaluated_jds()'s row list -- every
    evaluated JD, pending or completed, in one browsable table (the "List
    Jobs" / "View Pipeline" backlog item). rows is expected pre-sorted
    (list_all_evaluated_jds() already sorts best-first)."""
    table = Table(box=box.SIMPLE_HEAD, show_header=True, header_style="bold magenta")
    table.add_column("#", justify="right", style="dim")
    table.add_column("Score", justify="right")
    table.add_column("Recommendation")
    table.add_column("Company")
    table.add_column("Title")
    table.add_column("Status")
    table.add_column("Last Liveness")

    for i, r in enumerate(rows, 1):
        evaluation = r["evaluation"]
        color = _RECOMMENDATION_COLORS.get(evaluation.get("recommendation"), "white")
        table.add_row(
            str(i),
            f"[{color}]{evaluation.get('composite_score', 0):.2f}/5[/{color}]",
            f"[{color}]{evaluation.get('recommendation')}[/{color}]",
            r["company"] or "?",
            r["title"] or "?",
            r["status"],
            _liveness_cell(r.get("liveness")),
        )

    console.print(Panel(
        table, title=f"{len(rows)} evaluated JD(s)", border_style=theme.BRAND, box=box.ROUNDED,
    ))


_FIT_DIMENSION_LABELS = {
    "cv_profile_match": "CV Match", "north_star_alignment": "North Star", "remote_quality": "Remote",
    "level_fit": "Level Fit", "compensation": "Comp", "growth": "Growth", "time_to_offer": "Speed",
    "tech_tool_relevance": "Tools", "company_reputation": "Reputation", "cultural_signals": "Culture",
}


def render_comparison_table(rows: list) -> None:
    """Side-by-side comparison of 2+ already-evaluated JDs (the "Multi-job
    comparison mode" backlog item) -- one column per JD, one row per
    dimension, so a strength/weakness pattern is visible at a glance
    rather than needing to hold several single-JD views in your head."""
    table = Table(box=box.SIMPLE_HEAD, show_header=True, header_style="bold magenta")
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
    table.add_section()

    for dim, label in _FIT_DIMENSION_LABELS.items():
        _row(label, [r["evaluation"].get("dimension_scores", {}).get(dim, "-") for r in rows])

    console.print(Panel(
        table, title=f"Comparing {len(rows)} JD(s)", border_style=theme.BRAND, box=box.ROUNDED,
    ))


_STAGE_STATUS_COLORS = {"Up to date": theme.SUCCESS, "Stale": theme.WARNING, "In progress": theme.INFO}


def render_bullet_bank_status(stage_rows: list, maintenance_rows: list) -> None:
    """stage_rows: (number, label, status, detail) tuples, in pipeline
    order. maintenance_rows: (label, detail) tuples for the non-sequential
    triage/retire scripts."""
    table = Table(box=box.SIMPLE_HEAD, show_header=True, header_style="bold magenta")
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

    console.print(Panel(table, title="Bullet Bank Pipeline Status", border_style=theme.BRAND, box=box.ROUNDED))


# Single source of truth for the shortcuts cheat sheet -- both `resume
# help` (scripts/resume-cli.sh, which shells out to `python scripts/cli.py
# help`) and the interactive menu's Help entry render this same list, so
# there's exactly one place to update instead of two copies drifting apart.
HELP_ENTRIES = [
    ("resume", "launch the interactive menu"),
    ("resume activate", "cd into the project and activate the venv (stays active in this shell)"),
    ("resume cd", "just cd into the project"),
    ("resume run", "tailor+render every pending JD in jds/ (batch mode)"),
    ("resume run jds/x.txt", "tailor+render one specific JD file"),
    ("resume run --pick", "interactively select which pending JD(s) to tailor"),
    ("resume coverletter jds/x.txt", "generate + render a cover letter for one JD"),
    ("resume coverletter --pick", "interactively select which pending JD(s) to generate a cover letter for"),
    ("resume evaluate jds/x.txt", "score a JD's fit (go/no-go) without building a resume"),
    ("resume evaluate", "score every pending JD at once"),
    ("resume scan", "pull new postings from all configured sources into jds/"),
    ("resume scan --source jobright", "pull from just one source (jobright, linkedin)"),
    ("resume liveness", "check every pending JD's posting URL, move expired ones out"),
    ("resume polish", "interactively polish an already-generated resume/cover letter"),
    ("resume test", "run the full test suite (compact: dots + summary)"),
    ("resume test -v", "same, but lists every test by name"),
    ("resume test -vv", "same, but shows the app's own logging too"),
]


def display_help() -> None:
    table = Table(box=box.SIMPLE_HEAD, show_header=True, header_style="bold magenta")
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
