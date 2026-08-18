"""Batch Skill-Gap Priority Radar Module.

Aggregates missing skills across evaluated job postings and generates
ranked skill acquisition priority radars.
"""

from __future__ import annotations

import collections
import json
import os
import sqlite3
from typing import Any, Dict, List, Optional, Tuple


def compute_skill_radar_from_db(
    conn_or_path: sqlite3.Connection | str, top_n: int = 15
) -> List[Tuple[str, int, float]]:
    """Aggregates missing skills from the evaluated jobs in SQLite database.

    Returns:
        List of (skill_name, occurrence_count, percentage_of_jobs).
    """
    if isinstance(conn_or_path, str):
        if not os.path.exists(conn_or_path):
            return []
        conn = sqlite3.connect(conn_or_path)
        conn.row_factory = sqlite3.Row
        should_close = True
    else:
        conn = conn_or_path
        conn.row_factory = sqlite3.Row
        should_close = False

    try:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT raw_json FROM jobs WHERE raw_json IS NOT NULL AND raw_json != ''"
        )
        rows = cursor.fetchall()

        total_jobs = 0
        skill_counter: collections.Counter[str] = collections.Counter()

        for row in rows:
            raw_str = row["raw_json"]
            try:
                data = json.loads(raw_str)
                total_jobs += 1
                # Look for missing_skills, missing_keywords, or evaluation gaps
                missing = []
                if "missing_skills" in data and isinstance(
                    data["missing_skills"], list
                ):
                    missing.extend(data["missing_skills"])
                elif "_evaluation" in data and isinstance(data["_evaluation"], dict):
                    eval_data = data["_evaluation"]
                    if "missing_skills" in eval_data and isinstance(
                        eval_data["missing_skills"], list
                    ):
                        missing.extend(eval_data["missing_skills"])
                    elif "skill_gaps" in eval_data and isinstance(
                        eval_data["skill_gaps"], list
                    ):
                        missing.extend(eval_data["skill_gaps"])

                for s in missing:
                    if isinstance(s, str) and s.strip():
                        skill_counter[s.strip().lower()] += 1
            except Exception:
                continue

        if total_jobs == 0:
            return []

        results = []
        for skill, count in skill_counter.most_common(top_n):
            pct = round((count / total_jobs) * 100.0, 1)
            results.append((skill, count, pct))

        return results
    finally:
        if should_close:
            conn.close()


def render_skill_radar_ascii(
    radar_data: List[Tuple[str, int, float]], bar_width: int = 25
) -> str:
    """Renders skill priority radar as an ASCII bar chart."""
    if not radar_data:
        return "No skill gap telemetry available."

    lines = [
        "╔══════════════════════════════════════════════════════════════════════╗",
        "║                     SKILL-GAP PRIORITY RADAR                         ║",
        "╚══════════════════════════════════════════════════════════════════════╝",
        "",
    ]

    max_count = max(item[1] for item in radar_data) if radar_data else 1
    for skill, count, pct in radar_data:
        bar_len = int((count / max_count) * bar_width)
        chart_bar = "█" * bar_len + "░" * (bar_width - bar_len)
        lines.append(f"{skill[:20]:<20} │ {chart_bar} │ {count:>2} jobs ({pct:>4.1f}%)")

    return "\n".join(lines)


def main() -> None:
    """CLI execution entrypoint."""
    db_path = os.path.join("output", "morgan", "data.db")
    if not os.path.exists(db_path):
        db_path = "data.db"
    radar = compute_skill_radar_from_db(db_path)
    print(
        "\n\033[1m\033[38;2;139;117;255m✦ ────────────────────────────────────────────────────────────── ✦\033[0m"
    )
    print(
        "  \033[1m\033[38;2;139;117;255m💎 RESUME-BUILDER SKILL-GAP PRIORITY RADAR\033[0m"
    )
    print(
        "\033[1m\033[38;2;139;117;255m✦ ────────────────────────────────────────────────────────────── ✦\033[0m\n"
    )
    print(render_skill_radar_ascii(radar))
    print("")


if __name__ == "__main__":
    main()
