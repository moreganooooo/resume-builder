"""Lightweight banner/symbols for resume-builder's CLI, in job_automater's
cli_art.py style (rich Console/Panel) but trimmed down -- no hand-drawn ASCII
block art, just a clean styled banner."""

from questionary import Style
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

console = Console()

SUCCESS = "[bold green]✓[/bold green]"
ERROR = "[bold red]✗[/bold red]"
WARNING = "[bold yellow]⚠[/bold yellow]"

# Ported from job_automater/cli.py:47-57 (its `custom_style`) so every
# questionary prompt in this project -- old (--pick checkboxes) and new
# (the interactive menu) -- shares one consistent theme.
QUESTIONARY_STYLE = Style([
    ('qmark', 'fg:#673ab7 bold'),
    ('question', 'bold'),
    ('answer', 'fg:#2196f3 bold'),
    ('pointer', 'fg:#673ab7 bold'),
    ('highlighted', 'fg:#673ab7 bold'),
    ('selected', 'fg:#4caf50'),
    ('separator', 'fg:#cc5454'),
    ('instruction', ''),
    ('text', ''),
])

# Recommendation values match orchestrator.py's FitEvaluationSchema Literal
# exactly: "Strong pursue", "Selective pursue", "Low-priority pursue", "Skip".
_RECOMMENDATION_COLORS = {
    "Strong pursue": "green",
    "Selective pursue": "cyan",
    "Low-priority pursue": "yellow",
    "Skip": "red dim",
}


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
            f"[{color}]{r['composite_score']}/5[/{color}]",
            f"[{color}]{r['recommendation']}[/{color}]",
            r["company_name"],
            r["job_title"],
        )

    console.print(table)
