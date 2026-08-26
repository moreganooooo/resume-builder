"""
funnel_drilldown.py — End-to-end recruitment funnel drill-down and bottleneck diagnostics.

Analyzes candidate progression across Discovered -> Evaluated -> High-Fit -> Tailored ->
Applied -> Interview -> Offer, diagnosing exact conversion friction and drop-off reasons.
"""

import os
import sys
from typing import Any

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
if SCRIPT_DIR not in sys.path:
    sys.path.insert(0, SCRIPT_DIR)

import cli_art
import db
import profile_paths
import theme
from rich.console import Console
from rich.panel import Panel
from rich.table import Table


def compute_funnel_metrics(profile: str = None) -> dict[str, Any]:
    """Computes comprehensive recruitment funnel conversion rates and bottleneck diagnostics."""
    name = profile or profile_paths.active_profile()
    conn = db.get_db(name)
    try:
        # 1. Total jobs discovered
        total_discovered = conn.execute("SELECT COUNT(*) FROM jobs;").fetchone()[0]

        # 2. Total jobs evaluated
        evaluated_rows = conn.execute(
            "SELECT final_score, status, deal_breakers FROM jobs WHERE final_score IS NOT NULL;"
        ).fetchall()
        total_evaluated = len(evaluated_rows)

        # 3. High fit (score >= 4.0, on this codebase's 0-5 composite scale --
        # see platform_analytics.py's matching quadrant thresholds)
        high_fit_rows = [r for r in evaluated_rows if (r[0] or 0) >= 4.0]
        total_high_fit = len(high_fit_rows)

        # Moderate fit (3.5 <= score < 4.0)
        moderate_fit_rows = [r for r in evaluated_rows if 3.5 <= (r[0] or 0) < 4.0]
        total_moderate_fit = len(moderate_fit_rows)

        # Low fit (< 3.5)
        low_fit_rows = [r for r in evaluated_rows if (r[0] or 0) < 3.5]
        total_low_fit = len(low_fit_rows)

        # 4. Tailored / Completed resumes
        tailored_count = conn.execute(
            "SELECT COUNT(DISTINCT id) FROM jobs WHERE status IN ('completed', 'applied', 'interview', 'offer', 'responded', 'rejected', 'archived');"
        ).fetchone()[0]

        # 5. Applied from application_log or jobs status
        applied_count = conn.execute(
            "SELECT COUNT(DISTINCT id) FROM jobs WHERE status IN ('applied', 'interview', 'offer', 'responded', 'rejected');"
        ).fetchone()[0]

        # 6. Responses / Interviews
        interview_count = conn.execute(
            "SELECT COUNT(DISTINCT id) FROM jobs WHERE status IN ('interview', 'offer');"
        ).fetchone()[0]

        # 7. Offers
        offer_count = conn.execute(
            "SELECT COUNT(DISTINCT id) FROM jobs WHERE status = 'offer';"
        ).fetchone()[0]

        # Bottleneck calculations
        filter_drop = max(0, total_discovered - total_evaluated)
        score_drop = max(0, total_evaluated - total_high_fit)
        unapplied_gap = max(0, total_high_fit - applied_count)

        # Conversion rates
        eval_rate = (
            (total_evaluated / total_discovered * 100) if total_discovered > 0 else 0.0
        )
        fit_rate = (
            (total_high_fit / total_evaluated * 100) if total_evaluated > 0 else 0.0
        )
        tailor_rate = (
            (tailored_count / total_high_fit * 100) if total_high_fit > 0 else 0.0
        )
        apply_rate = (
            (applied_count / total_high_fit * 100) if total_high_fit > 0 else 0.0
        )
        interview_rate = (
            (interview_count / applied_count * 100) if applied_count > 0 else 0.0
        )
        offer_rate = (
            (offer_count / interview_count * 100) if interview_count > 0 else 0.0
        )

        return {
            "profile": name,
            "stages": {
                "discovered": total_discovered,
                "evaluated": total_evaluated,
                "high_fit": total_high_fit,
                "moderate_fit": total_moderate_fit,
                "low_fit": total_low_fit,
                "tailored": tailored_count,
                "applied": applied_count,
                "interview": interview_count,
                "offer": offer_count,
            },
            "rates": {
                "eval_rate": eval_rate,
                "fit_rate": fit_rate,
                "tailor_rate": tailor_rate,
                "apply_rate": apply_rate,
                "interview_rate": interview_rate,
                "offer_rate": offer_rate,
            },
            "bottlenecks": {
                "filter_drop": filter_drop,
                "score_drop": score_drop,
                "unapplied_gap": unapplied_gap,
            },
        }
    finally:
        conn.close()


def render_funnel_drilldown(metrics: dict[str, Any], console: Console = None) -> None:
    """Renders visual Rich table and diagnostic analysis of the recruitment funnel."""
    c = console or cli_art.console
    stages = metrics["stages"]
    rates = metrics["rates"]
    bottlenecks = metrics["bottlenecks"]

    c.print()
    c.print(
        Panel(
            f"[bold {theme.BRAND}]APPLICATION FUNNEL DRILL-DOWN & BOTTLENECK DIAGNOSTICS[/]\n"
            f"[dim]Profile:[/] [bold]{metrics['profile']}[/]",
            border_style=theme.BRAND,
            padding=(0, 2),
        )
    )

    # Funnel Table
    table = Table(
        box=None,
        show_header=True,
        header_style=f"bold {theme.MUTED}",
        pad_edge=False,
    )
    table.add_column("Funnel Stage", style="bold", width=22)
    table.add_column("Volume", justify="right", width=10)
    table.add_column("Conversion", justify="right", width=14)
    table.add_column("Drop-Off / Friction", style="dim", width=34)

    # Discovered
    table.add_row(
        "1. Discovered",
        f"{stages['discovered']:,}",
        "100.0%",
        "— (Initial inbound pool)",
    )
    # Evaluated
    eval_style = theme.SUCCESS if rates["eval_rate"] >= 80 else theme.WARNING
    table.add_row(
        "2. Evaluated",
        f"{stages['evaluated']:,}",
        f"[{eval_style}]{rates['eval_rate']:.1f}%[/{eval_style}]",
        f"{bottlenecks['filter_drop']:,} pre-filtered / unparsed",
    )
    # High Fit (score >= 4.0)
    fit_style = theme.SUCCESS if rates["fit_rate"] >= 20 else theme.INFO
    table.add_row(
        "3. High-Fit (score ≥ 4.0)",
        f"{stages['high_fit']:,}",
        f"[{fit_style}]{rates['fit_rate']:.1f}%[/{fit_style}]",
        f"{stages['low_fit']:,} low (<3.5), {stages['moderate_fit']:,} moderate",
    )
    # Tailored
    table.add_row(
        "4. Tailored",
        f"{stages['tailored']:,}",
        f"{rates['tailor_rate']:.1f}%",
        f"{max(0, stages['high_fit'] - stages['tailored']):,} pending generation",
    )
    # Applied
    apply_style = theme.SUCCESS if rates["apply_rate"] >= 50 else theme.WARNING
    table.add_row(
        "5. Applied",
        f"{stages['applied']:,}",
        f"[{apply_style}]{rates['apply_rate']:.1f}%[/{apply_style}]",
        f"{bottlenecks['unapplied_gap']:,} high-fit not applied",
    )
    # Interview
    interview_style = theme.SUCCESS if rates["interview_rate"] >= 15 else theme.INFO
    table.add_row(
        "6. Interview",
        f"{stages['interview']:,}",
        f"[{interview_style}]{rates['interview_rate']:.1f}%[/{interview_style}]",
        f"{max(0, stages['applied'] - stages['interview']):,} pending / ghosted",
    )
    # Offer
    offer_style = theme.SUCCESS if stages["offer"] > 0 else theme.MUTED
    table.add_row(
        "7. Offer",
        f"{stages['offer']:,}",
        f"[{offer_style}]{rates['offer_rate']:.1f}%[/{offer_style}]",
        "Target outcome",
    )

    c.print(table)
    c.print()

    # Tactical Bottleneck Guidance
    c.print(f"[bold {theme.BRAND_ACCENT}]🔍 Tactical Recommendations:[/]")
    if bottlenecks["unapplied_gap"] > 10:
        c.print(
            f"  • [bold {theme.WARNING}]Application Inertia Bottleneck:[/] You have [bold]{bottlenecks['unapplied_gap']}[/] high-fit roles "
            "that haven't been applied to yet. Run `resume next` or `resume batch` to clear the backlog."
        )
    if stages["high_fit"] == 0 and stages["evaluated"] > 20:
        c.print(
            f"  • [bold {theme.WARNING}]Rubric Calibration:[/] 0 roles matched a score ≥ 4.0. Run `resume tune-rubrics` or enrich "
            "`evidence-guide.csv` to improve fit scoring accuracy."
        )
    if stages["applied"] > 0 and stages["interview"] == 0:
        c.print(
            "  • [bold {theme.INFO}]Response Pipeline:[/] Run `resume inbox-sync --apply` with valid email credentials to capture recruiter replies."
        )
    if bottlenecks["unapplied_gap"] <= 10 and stages["high_fit"] > 0:
        c.print(
            f"  • [bold {theme.SUCCESS}]Healthy Funnel:[/] High-fit pipeline conversion is active and well-balanced."
        )
    c.print()


if __name__ == "__main__":
    m = compute_funnel_metrics()
    render_funnel_drilldown(m)
