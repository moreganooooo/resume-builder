"""
mission_control.py — Multi-Panel Terminal Mission Control Cockpit.

Aggregates operational telemetry across ingestion, scoring, outreach deadlines,
conversion funnels, and data integrity into a consolidated executive status screen.
"""

from __future__ import annotations

import os
import sqlite3
from typing import Any, Dict

import db
import profile_paths


def get_mission_control_summary(
    db_path: str | None = None,
) -> Dict[str, Any]:
    """Compiles multi-panel metrics for CLI and dashboard rendering."""
    path = db_path or os.path.join(profile_paths.output_dir(), "data.db")
    if not os.path.exists(path):
        return {
            "total_jobs": 0,
            "pending_eval": 0,
            "applied_count": 0,
            "interview_count": 0,
            "offer_count": 0,
            "contacts_count": 0,
            "system_health": "No Database Found",
        }

    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    try:
        cursor.execute("SELECT COUNT(*) as cnt FROM jobs")
        total_jobs = cursor.fetchone()["cnt"]

        cursor.execute("SELECT COUNT(*) as cnt FROM jobs WHERE status = 'pending'")
        pending_eval = cursor.fetchone()["cnt"]

        cursor.execute(
            "SELECT COUNT(*) as cnt FROM applications WHERE status = 'applied'"
        )
        applied = cursor.fetchone()["cnt"]

        cursor.execute(
            "SELECT COUNT(*) as cnt FROM applications WHERE status IN ('interview', 'screening')"
        )
        interviews = cursor.fetchone()["cnt"]

        cursor.execute(
            "SELECT COUNT(*) as cnt FROM applications WHERE status = 'offer'"
        )
        offers = cursor.fetchone()["cnt"]

        cursor.execute("SELECT COUNT(*) as cnt FROM contacts")
        contacts = cursor.fetchone()["cnt"]

        health_data = db.run_integrity_check(conn=conn)
        health_status = "Healthy" if health_data.get("healthy") else "Degraded"

        return {
            "total_jobs": total_jobs,
            "pending_eval": pending_eval,
            "applied_count": applied,
            "interview_count": interviews,
            "offer_count": offers,
            "contacts_count": contacts,
            "system_health": health_status,
        }
    except Exception:
        return {
            "total_jobs": 0,
            "pending_eval": 0,
            "applied_count": 0,
            "interview_count": 0,
            "offer_count": 0,
            "contacts_count": 0,
            "system_health": "Error Reading Telemetry",
        }
    finally:
        conn.close()


def render_mission_control_ascii(summary: Dict[str, Any]) -> str:
    """Renders a structured multi-panel terminal dashboard view."""
    border = "═" * 60
    return f"""
╔{border}╗
║                    MISSION CONTROL COCKPIT                 ║
╠{border}╣
║  [ PIPELINE QUEUE ]              [ FUNNEL CONVERSION ]     ║
║  Total Ingested : {summary['total_jobs']:<5}          Applied       : {summary['applied_count']:<5}     ║
║  Pending Eval   : {summary['pending_eval']:<5}          Interviews    : {summary['interview_count']:<5}     ║
║                                  Offers        : {summary['offer_count']:<5}     ║
╠{border}╣
║  [ NETWORK & CRM ]               [ SYSTEM HEALTH ]         ║
║  Enriched Leads : {summary['contacts_count']:<5}          Integrity     : {summary['system_health']:<10} ║
╚{border}╝
""".strip()


def main() -> None:
    """CLI execution entrypoint."""
    summary = get_mission_control_summary()
    print(
        "\n\033[1m\033[38;2;139;117;255m✦ ────────────────────────────────────────────────────────────── ✦\033[0m"
    )
    print(
        "  \033[1m\033[38;2;139;117;255m💎 RESUME-BUILDER MISSION CONTROL COCKPIT\033[0m"
    )
    print(
        "\033[1m\033[38;2;139;117;255m✦ ────────────────────────────────────────────────────────────── ✦\033[0m\n"
    )
    print(render_mission_control_ascii(summary))
    print("")


if __name__ == "__main__":
    main()
