"""Application Follow-Up Scheduler & Email Drafter Module.

Identifies applications awaiting response past 7-day and 14-day milestones
and generates contextual follow-up emails.
"""

from __future__ import annotations

import datetime
import os
import sqlite3
from typing import Any, Dict, List


def get_pending_followups(
    conn_or_path: sqlite3.Connection | str, threshold_days: int = 7
) -> List[Dict[str, Any]]:
    """Finds jobs where status is 'applied' or 'submitted' and elapsed time exceeds threshold."""
    if isinstance(conn_or_path, str):
        if not os.path.exists(conn_or_path):
            return []
        conn = sqlite3.connect(conn_or_path, timeout=10.0)
        conn.row_factory = sqlite3.Row
        should_close = True
    else:
        conn = conn_or_path
        conn.row_factory = sqlite3.Row
        should_close = False

    try:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT id, title, company, status, updated_at, created_at
            FROM jobs
            WHERE status IN ('applied', 'submitted', 'pending')
            ORDER BY updated_at ASC
        """)
        rows = cursor.fetchall()
        now = datetime.datetime.now()

        due_followups = []
        for r in rows:
            date_str = r["updated_at"] or r["created_at"]
            if not date_str:
                continue
            try:
                # Handle SQLite timestamp format
                dt = datetime.datetime.fromisoformat(
                    date_str.replace("Z", "+00:00").split(".")[0]
                )
                elapsed = (now - dt).days
                if elapsed >= threshold_days:
                    due_followups.append(
                        {
                            "id": r["id"],
                            "title": r["title"],
                            "company": r["company"],
                            "status": r["status"],
                            "elapsed_days": elapsed,
                        }
                    )
            except Exception:
                continue

        return due_followups
    finally:
        if should_close:
            conn.close()


def draft_followup_email(
    role: str,
    company: str,
    elapsed_days: int,
    candidate_name: str = "[Candidate Name]",
) -> str:
    """Generates a tailored follow-up email draft based on days elapsed."""
    if elapsed_days < 10:
        # 1st Follow-up (1 week)
        subject = f"Following up on {role} Application - {candidate_name}"
        body = (
            f"Dear Hiring Team at {company},\n\n"
            f"I hope this week is going well for you! I wanted to follow up on my recent application for the "
            f"{role} position.\n\n"
            f"I remains very interested in joining {company} and contributing to your team's ongoing initiatives. "
            f"Please let me know if there are any additional materials or details I can provide to support my application.\n\n"
            f"Thank you for your time and consideration,\n{candidate_name}"
        )
    else:
        # 2nd Follow-up (2 weeks+)
        subject = f"Checking In: {role} Application Status - {candidate_name}"
        body = (
            f"Dear Hiring Team at {company},\n\n"
            f"I am writing to briefly check in on the status of the hiring process for the {role} role.\n\n"
            f"I continue to be very enthusiastic about the work {company} is doing and would welcome the opportunity "
            f"to discuss how my background aligns with the team's needs.\n\n"
            f"Thank you again for your consideration,\n{candidate_name}"
        )

    return f"Subject: {subject}\n\n{body}"


def main() -> None:
    """CLI execution entrypoint."""
    db_path = os.path.join("output", "morgan", "data.db")
    if not os.path.exists(db_path):
        db_path = "data.db"
    pending = get_pending_followups(db_path)
    print(
        "\n\033[1m\033[38;2;139;117;255m✦ ────────────────────────────────────────────────────────────── ✦\033[0m"
    )
    print(
        "  \033[1m\033[38;2;139;117;255m💎 RESUME-BUILDER APPLICATION FOLLOW-UP SCHEDULER\033[0m"
    )
    print(
        "\033[1m\033[38;2;139;117;255m✦ ────────────────────────────────────────────────────────────── ✦\033[0m\n"
    )
    if not pending:
        print(
            "  \033[1m\033[38;2;18;199;143m✓ No applications currently pending follow-up (>7 days).\033[0m\n"
        )
        return

    print(
        f"  \033[1m\033[38;2;0;164;255mApplications Requiring Follow-Up ({len(pending)} total):\033[0m\n"
    )
    for app in pending:
        days = app["elapsed_days"]
        color = "\033[38;2;255;123;153m" if days >= 14 else "\033[38;2;245;239;52m"
        print(
            f"  {color}⏱ {days:>2}d ago\033[0m \033[38;2;163;163;163m│\033[0m \033[1m{app['title']}\033[0m @ {app['company']}"
        )
    print("")


if __name__ == "__main__":
    main()
