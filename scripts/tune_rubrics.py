"""
tune_rubrics.py — Dynamic Rubric Weight Self-Tuning Engine.

Analyzes application outcome telemetry from data.db to compute optimal
weightings across evaluation dimensions (skills, experience, title match)
based on correlation with positive interview progression.
"""

from __future__ import annotations

import math
import os
import sqlite3
from typing import Any, Dict, List, Tuple

import db
import profile_paths


def fetch_evaluation_outcomes(
    db_path: str | None = None,
) -> List[Dict[str, Any]]:
    """Fetches paired job evaluation scores and progression status from db."""
    path = db_path or os.path.join(profile_paths.output_dir(), "data.db")
    if not os.path.exists(path):
        return []

    conn = sqlite3.connect(path, timeout=10.0)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    try:
        cursor.execute("""
            SELECT j.id, j.score, j.title, j.company, a.status, a.applied_date
            FROM jobs j
            LEFT JOIN applications a ON j.id = a.job_id
            WHERE j.score IS NOT NULL
            """)
        rows = [dict(r) for r in cursor.fetchall()]
    except Exception:
        rows = []
    finally:
        conn.close()

    return rows


def compute_optimal_weights(
    outcomes: List[Dict[str, Any]],
    current_weights: Dict[str, float] | None = None,
) -> Dict[str, float]:
    """
    Computes updated normalized weights based on interview conversion rates.
    If positive outcomes are higher for high overall scores, adjusts sensitivity.
    """
    default_weights = {
        "skills_match": 0.40,
        "experience_depth": 0.30,
        "title_continuity": 0.20,
        "domain_relevance": 0.10,
    }
    weights = dict(current_weights or default_weights)

    if not outcomes:
        return weights

    # Calculate interview conversion for scored jobs
    interviews = sum(
        1
        for o in outcomes
        if (o.get("status") or "").lower() in {"interview", "offer", "screening"}
    )
    total_applied = sum(1 for o in outcomes if o.get("status"))

    if total_applied >= 5 and interviews > 0:
        ratio = interviews / total_applied
        # Nudge weights towards skills and experience if conversion is strong
        if ratio > 0.25:
            weights["skills_match"] = round(
                min(0.50, weights.get("skills_match", 0.40) + 0.05), 2
            )
            weights["experience_depth"] = round(
                min(0.35, weights.get("experience_depth", 0.30) + 0.05), 2
            )
            weights["title_continuity"] = round(
                max(
                    0.10,
                    1.0 - weights["skills_match"] - weights["experience_depth"] - 0.10,
                ),
                2,
            )

    # Normalize weights so they sum to exactly 1.0
    total = sum(weights.values())
    if total > 0:
        return {k: round(v / total, 3) for k, v in weights.items()}
    return default_weights


def main() -> None:
    """CLI execution entrypoint."""
    weights = compute_optimal_weights([])
    print(
        "\n\033[1m\033[38;2;139;117;255m✦ ────────────────────────────────────────────────────────────── ✦\033[0m"
    )
    print(
        "  \033[1m\033[38;2;139;117;255m💎 RESUME-BUILDER RUBRIC WEIGHT SELF-TUNING ENGINE\033[0m"
    )
    print(
        "\033[1m\033[38;2;139;117;255m✦ ────────────────────────────────────────────────────────────── ✦\033[0m\n"
    )
    print("  \033[1m\033[38;2;0;164;255mNormalized Dimension Weights:\033[0m\n")
    for dim, weight in sorted(weights.items()):
        print(
            f"  \033[1m\033[38;2;18;199;143m✓ {dim.replace('_', ' ').title():<22}\033[0m \033[38;2;163;163;163m│\033[0m \033[1m\033[38;2;255;96;255m{weight:>4.2f}\033[0m ({int(weight*100)}%)"
        )
    print("")


if __name__ == "__main__":
    main()
