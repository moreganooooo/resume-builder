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

import jd_manager
import theme

console = Console()

SUCCESS = f"[bold {theme.SUCCESS}]{theme.ICONS['success']}[/bold {theme.SUCCESS}]"
ERROR = f"[bold {theme.ERROR}]{theme.ICONS['error']}[/bold {theme.ERROR}]"
WARNING = f"[bold {theme.WARNING}]{theme.ICONS['warning']}[/bold {theme.WARNING}]"
HINT = f"[bold {theme.INFO}]{theme.ICONS['hint']}[/bold {theme.INFO}]"

# Re-exported so menu.py/picker.py's existing `cli_art.QUESTIONARY_STYLE`
# references keep working unchanged.
QUESTIONARY_STYLE = theme.QUESTIONARY_STYLE

# Block-letter title banner, same ansi_shadow-style box-drawing glyphs as
# job_automater-main's MAIN_BANNER -- stacked on two lines since "RESUME
# BUILDER" is too long for one line at this scale (each line is 53 columns,
# safe for any real terminal width).
MAIN_BANNER = """
[bold #4dabf7]
██████╗ ███████╗███████╗██╗   ██╗███╗   ███╗███████╗
██╔══██╗██╔════╝██╔════╝██║   ██║████╗ ████║██╔════╝
██████╔╝█████╗  ███████╗██║   ██║██╔████╔██║█████╗
██╔══██╗██╔══╝  ╚════██║██║   ██║██║╚██╔╝██║██╔══╝
██║  ██║███████╗███████║╚██████╔╝██║ ╚═╝ ██║███████╗
╚═╝  ╚═╝╚══════╝╚══════╝ ╚═════╝ ╚═╝     ╚═╝╚══════╝

██████╗ ██╗   ██╗██╗██╗     ██████╗ ███████╗██████╗
██╔══██╗██║   ██║██║██║     ██╔══██╗██╔════╝██╔══██╗
██████╔╝██║   ██║██║██║     ██║  ██║█████╗  ██████╔╝
██╔══██╗██║   ██║██║██║     ██║  ██║██╔══╝  ██╔══██╗
██████╔╝╚██████╔╝██║███████╗██████╔╝███████╗██║  ██║
╚═════╝  ╚═════╝ ╚═╝╚══════╝╚═════╝ ╚══════╝╚═╝  ╚═╝
[/bold #4dabf7]
[dim]          Tailored resumes & cover letters, powered by Gemini[/dim]
"""


def display_main_banner() -> None:
    console.print(Panel(MAIN_BANNER, border_style="#4caf50", box=box.DOUBLE, padding=(1, 2)))


def display_whats_next_panel() -> None:
    console.print(Panel("What's next?", border_style="#4caf50", box=box.ROUNDED, padding=(0, 2)))


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
    table = Table(box=None, show_header=True, header_style="bold magenta")
    table.add_column("#", justify="right", style="dim")
    table.add_column("Score", justify="right")
    table.add_column("Recommendation")
    table.add_column("Company")
    table.add_column("Title")

    for i, r in enumerate(results, 1):
        if r["error"]:
            table.add_row(str(i), "[red]ERROR[/red]", "-", r["company_name"], r["job_title"])
            continue
        color = _RECOMMENDATION_COLORS.get(r["recommendation"], "white")
        table.add_row(
            str(i),
            f"[{color}]{r['composite_score']:.2f}/5[/{color}]",
            f"[{color}]{r['recommendation']}[/{color}]",
            r["company_name"],
            r["job_title"],
        )

    console.print(table)


def display_applications_tracker(content: str) -> None:
    """Renders data/applications.md's raw markdown content directly in the
    terminal via Rich's built-in Markdown renderer -- the table and each
    row's clickable "[Apply](source_url)" link render as-is, no custom
    parsing needed since the file is already valid GFM markdown."""
    console.print(Markdown(content))
