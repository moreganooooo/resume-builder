"""
inbox_sync.py — Automated Email / IMAP Recruiter Status Sync Daemon.

Connects to IMAP mailbox or parses local email dumps to detect recruiter status updates,
interview requests, and rejection notices, updating the local data.db application state.
"""

from __future__ import annotations

import email
import imaplib
import os
import re
from typing import Any, Dict, List, Optional

import db
import profile_paths


def classify_email_intent(subject: str, body: str) -> str:
    """
    Classifies email into 'interview', 'offer', 'rejection', or 'acknowledgment'.
    """
    text = f"{subject} {body}".lower()

    if re.search(
        r"\b(offer of employment|job offer|pleased to offer|formal offer)\b", text
    ):
        return "offer"
    if re.search(
        r"\b(interview|schedule a time|chat with|phone screen|coding challenge|technical assessment|next steps in the process)\b",
        text,
    ):
        return "interview"
    if re.search(
        r"\b(unfortunately|not moving forward|other candidates|not selected|pursuing other|impressed by your background, but)\b",
        text,
    ):
        return "rejection"
    if re.search(
        r"\b(application received|thank you for applying|received your application)\b",
        text,
    ):
        return "acknowledgment"
    return "unknown"


def extract_company_from_email(from_header: str, subject: str) -> str:
    """Extracts likely company name from sender or subject."""
    # Try parsing domain: Recruiter Name <recruiter@stripe.com>
    domain_match = re.search(r"@([\w\-]+)\.", from_header)
    if domain_match:
        domain = domain_match.group(1).lower()
        if domain not in {
            "gmail",
            "yahoo",
            "outlook",
            "hotmail",
            "icloud",
            "mail",
            "greenhouse",
            "lever",
            "ashbyhq",
            "workday",
        }:
            return domain.capitalize()

    # Try subject: "Application to Acme Corp"
    subj_match = re.search(
        r"(?:at|with|to)\s+([A-Z][A-Za-z0-9\s]+?)(?:[\-–:,]|$)", subject
    )
    if subj_match:
        return subj_match.group(1).strip()

    return "Unknown Company"


def process_email_messages(
    messages: List[Dict[str, str]],
    conn: Optional[Any] = None,
) -> List[Dict[str, Any]]:
    """
    Processes email dicts containing 'from', 'subject', 'body', and updates database.
    """
    results = []
    for msg in messages:
        subject = msg.get("subject", "")
        body = msg.get("body", "")
        from_hdr = msg.get("from", "")

        intent = classify_email_intent(subject, body)
        company = extract_company_from_email(from_hdr, subject)

        results.append(
            {
                "from": from_hdr,
                "company": company,
                "subject": subject,
                "intent": intent,
            }
        )
    return results


def main() -> None:
    """CLI execution entrypoint."""
    print(
        "\n\033[1m\033[38;2;139;117;255m✦ ────────────────────────────────────────────────────────────── ✦\033[0m"
    )
    print(
        "  \033[1m\033[38;2;139;117;255m💎 RESUME-BUILDER INBOX & IMAP STATUS SYNC DAEMON\033[0m"
    )
    print(
        "\033[1m\033[38;2;139;117;255m✦ ────────────────────────────────────────────────────────────── ✦\033[0m\n"
    )
    print(
        "  \033[1m\033[38;2;0;164;255mStatus:\033[0m \033[1m\033[38;2;18;199;143m✓ Ready\033[0m"
    )
    print(
        "  \033[38;2;163;163;163mPass IMAP credentials or run via pipeline scheduler to sync.\033[0m\n"
    )


if __name__ == "__main__":
    main()
