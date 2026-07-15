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
    console.print(Panel(body, title="New User Bootstrap", border_style="#4caf50", box=box.ROUNDED, padding=(1, 2)))


# Same four tiers as orchestrator.FitEvaluationSchema's `recommendation`
# Literal -- sourced from theme.py so this table and picker.py's checkbox
# list are provably one palette, not two hand-maintained copies. "Skip"
# is intentionally not dimmed here (it was previously "red dim" in this
# file only) -- unified to match picker.py's plain-hex treatment.
_RECOMMENDATION_COLORS = theme.RECOMMENDATION_COLORS


def display_banner(subtitle: str = "") -> None:
    body = "[bold cyan]RESUME BUILDER[/bold cyan]"
    if subtitle:
        body += f"\n[dim]{subtitle}[/dim]"
    console.print(Panel(body, border_style="cyan"))


def render_fit_table(results: list) -> None:
    """Renders batch_evaluate.evaluate_all_pending()'s result list as a
    Rich Table, colored by recommendation tier (modeled on job_automater's
    display_job_table(), cli.py:73-142). results is expected pre-sorted
    (evaluate_all_pending() already sorts best-first, errors-last)."""
    table = Table(box=box.SIMPLE_HEAD, show_header=True, header_style="bold magenta")
    table.add_column("#", justify="right", style="dim")
    table.add_column("Score", justify="right")
    table.add_column("Recommendation")
    table.add_column("Company")
    table.add_column("Title")

    for i, r in enumerate(results, 1):
        if r["error"]:
            table.add_row(str(i), f"[{theme.ERROR}]ERROR[/{theme.ERROR}]", "-", r["company_name"], r["job_title"])
            continue
        color = _RECOMMENDATION_COLORS.get(r["recommendation"], "white")
        table.add_row(
            str(i),
            f"[{color}]{r['composite_score']:.2f}/5[/{color}]",
            f"[{color}]{r['recommendation']}[/{color}]",
            r["company_name"],
            r["job_title"],
        )

    legend = "  ".join(f"[{color}]■[/{color}] {tier}" for tier, color in _RECOMMENDATION_COLORS.items())
    console.print(Panel(
        table, title=f"{len(results)} JD(s) evaluated", subtitle=legend,
        border_style=theme.BRAND, box=box.ROUNDED,
    ))


def display_applications_tracker(content: str) -> None:
    """Renders data/applications.md's raw markdown content directly in the
    terminal via Rich's built-in Markdown renderer -- the table and each
    row's clickable "[Apply](source_url)" link render as-is, no custom
    parsing needed since the file is already valid GFM markdown."""
    console.print(Markdown(content))
