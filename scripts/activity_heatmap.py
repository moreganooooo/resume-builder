"""
activity_heatmap.py — Terminal Activity Pacing Heatmap.

Generates a GitHub-style ASCII/ANSI activity heatmap from data.db application
timestamps over the past 4 weeks to visualize search velocity and pacing.
"""

from __future__ import annotations

import collections
import datetime
import os
import sqlite3
from typing import Any, Dict, List

import profile_paths


def get_daily_application_counts(
    days: int = 28,
    db_path: str | None = None,
) -> Dict[str, int]:
    """Returns mapping of 'YYYY-MM-DD' -> application count."""
    path = db_path or os.path.join(profile_paths.output_dir(), "data.db")
    counts: Dict[str, int] = collections.defaultdict(int)

    # Initialize all dates in range with 0
    today = datetime.date.today()
    for i in range(days):
        d = today - datetime.timedelta(days=days - 1 - i)
        counts[d.strftime("%Y-%m-%d")] = 0

    if not os.path.exists(path):
        return dict(counts)

    conn = sqlite3.connect(path, timeout=10.0)
    cursor = conn.cursor()
    try:
        cursor.execute(
            """
            SELECT date(created_at) as app_date, COUNT(*) as cnt
            FROM applications
            WHERE created_at >= date('now', ?)
            GROUP BY date(created_at)
            """,
            (f"-{days} days",),
        )
        for row in cursor.fetchall():
            if row[0]:
                counts[row[0]] = row[1]
    except Exception:
        pass
    finally:
        conn.close()

    return dict(counts)


def render_heatmap_ascii(counts: Dict[str, int]) -> str:
    """Renders ASCII calendar heatmap blocks for daily counts."""
    blocks = ["·", "░", "▒", "▓", "█"]
    lines = ["Application Activity Heatmap (Past 4 Weeks):", ""]

    sorted_dates = sorted(counts.keys())
    # Group into weeks of 7 days
    weeks = [sorted_dates[i : i + 7] for i in range(0, len(sorted_dates), 7)]

    header = "       " + " ".join(f"W{i+1}" for i in range(len(weeks)))
    lines.append(header)

    days_of_week = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
    for day_idx in range(7):
        row_str = f" {days_of_week[day_idx]:3}  "
        for w in weeks:
            if day_idx < len(w):
                d = w[day_idx]
                cnt = counts.get(d, 0)
                char = blocks[0] if cnt == 0 else (blocks[min(cnt, 4)])
                row_str += f" {char} "
            else:
                row_str += "   "
        lines.append(row_str)

    lines.append("")
    lines.append(" Legend: · 0  ░ 1  ▒ 2  ▓ 3  █ 4+")
    return "\n".join(lines)


def main() -> None:
    """CLI execution entrypoint."""
    counts = get_daily_application_counts()
    print(
        "\n\033[1m\033[38;2;139;117;255m✦ ────────────────────────────────────────────────────────────── ✦\033[0m"
    )
    print(
        "  \033[1m\033[38;2;139;117;255m◈ RESUME-BUILDER APPLICATION ACTIVITY HEATMAP\033[0m"
    )
    print(
        "\033[1m\033[38;2;139;117;255m✦ ────────────────────────────────────────────────────────────── ✦\033[0m\n"
    )
    print(render_heatmap_ascii(counts))
    total_apps = sum(counts.values())
    print(
        f"\n  \033[1m\033[38;2;18;199;143m✓ Total 4-Week Applications:\033[0m \033[1m\033[38;2;255;96;255m{total_apps}\033[0m\n"
    )


if __name__ == "__main__":
    main()
