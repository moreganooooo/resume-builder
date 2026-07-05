"""Lightweight banner/symbols for resume-builder's CLI, in job_automater's
cli_art.py style (rich Console/Panel) but trimmed down -- no hand-drawn ASCII
block art, just a clean styled banner."""

from rich.console import Console
from rich.panel import Panel

console = Console()

SUCCESS = "[bold green]✓[/bold green]"
ERROR = "[bold red]✗[/bold red]"
WARNING = "[bold yellow]⚠[/bold yellow]"


def display_banner(subtitle: str = "") -> None:
    body = "[bold cyan]RESUME BUILDER[/bold cyan]"
    if subtitle:
        body += f"\n[dim]{subtitle}[/dim]"
    console.print(Panel(body, border_style="cyan"))
