"""
bullet_analytics.py — Bullet-Tag-to-Outcome Correlation Engine.

Correlates bullet bank skill and competency tags against real application
outcomes (interviews vs. rejections) to identify highest-performing narrative angles.
"""

from __future__ import annotations

import collections
import os
import re
import sqlite3
from typing import Any, Dict, List, Tuple

import profile_paths


def analyze_bullet_tag_performance(
    db_path: str | None = None,
) -> Dict[str, Dict[str, Any]]:
    """
    Computes conversion statistics per bullet tag based on application outcomes.
    Returns mapping: tag -> { applications, interviews, rejections, interview_rate }
    """
    path = db_path or os.path.join(profile_paths.output_dir(), "data.db")
    if not os.path.exists(path):
        return {}

    conn = sqlite3.connect(path, timeout=10.0)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    tag_stats: Dict[str, Dict[str, int]] = collections.defaultdict(
        lambda: {"applications": 0, "interviews": 0, "rejections": 0}
    )

    try:
        cursor.execute("""
            SELECT a.status, j.title, j.description
            FROM applications a
            JOIN jobs j ON a.job_id = j.id
            WHERE a.status IS NOT NULL
            """)
        rows = cursor.fetchall()

        for row in rows:
            status = (row["status"] or "").lower()
            text = f"{row['title']} {row['description']}".lower()

            words = set(re.findall(r"\b\w+\b", text))

            # Infer tags present in job context
            detected_tags = []
            if words & {"lead", "architect", "manager", "director", "staff"}:
                detected_tags.append("lead")
            if words & {
                "infra",
                "cloud",
                "aws",
                "kubernetes",
                "devops",
                "infrastructure",
            }:
                detected_tags.append("infra")
            if words & {
                "python",
                "golang",
                "backend",
                "api",
                "apis",
                "database",
                "sql",
            }:
                detected_tags.append("backend")
            if words & {"frontend", "react", "typescript", "ui", "javascript", "css"}:
                detected_tags.append("frontend")
            if words & {"ai", "ml", "llm", "rag", "nlp"}:
                detected_tags.append("ai")

            is_interview = status in {"interview", "screening", "offer"}
            is_rejection = status in {"rejected", "archived"}

            for t in detected_tags:
                tag_stats[t]["applications"] += 1
                if is_interview:
                    tag_stats[t]["interviews"] += 1
                elif is_rejection:
                    tag_stats[t]["rejections"] += 1
    except Exception:
        pass
    finally:
        conn.close()

    results: Dict[str, Dict[str, Any]] = {}
    for t, stat in tag_stats.items():
        total = stat["applications"]
        rate = round((stat["interviews"] / total) * 100, 1) if total > 0 else 0.0
        results[t] = {
            "applications": total,
            "interviews": stat["interviews"],
            "rejections": stat["rejections"],
            "interview_rate_pct": rate,
        }

    return results


def main() -> None:
    """CLI execution entrypoint."""
    stats = analyze_bullet_tag_performance()
    print(
        "\n\033[1m\033[38;2;139;117;255m✦ ────────────────────────────────────────────────────────────── ✦\033[0m"
    )
    print(
        "  \033[1m\033[38;2;139;117;255m◈ RESUME-BUILDER BULLET OUTCOME ANALYTICS\033[0m"
    )
    print(
        "\033[1m\033[38;2;139;117;255m✦ ────────────────────────────────────────────────────────────── ✦\033[0m\n"
    )
    if not stats:
        print(
            "  \033[38;2;163;163;163mNo application outcome telemetry recorded yet.\033[0m"
        )
        print(
            "  \033[38;2;163;163;163mApply to jobs to track bullet tag interview correlation rates.\033[0m\n"
        )
        return

    print(
        "  \033[1m\033[38;2;0;164;255mTag Performance & Interview Conversion:\033[0m\n"
    )
    for tag, data in sorted(stats.items()):
        rate = data["interview_rate_pct"]
        apps = data["applications"]
        ivs = data["interviews"]
        print(
            f"  \033[1m\033[38;2;255;96;255m#{tag:<12}\033[0m \033[38;2;163;163;163m│\033[0m {apps:>3} apps \033[38;2;163;163;163m│\033[0m \033[1m\033[38;2;18;199;143m{ivs:>2} interviews ({rate:>4.1f}%)\033[0m"
        )
    print("")


if __name__ == "__main__":
    main()
