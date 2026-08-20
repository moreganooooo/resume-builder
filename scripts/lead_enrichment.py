"""
lead_enrichment.py — Recruiter & Hiring Manager Lead Enrichment.

Generates targeted search dorks and CRM contact stubs for recruiters,
engineering leaders, and hiring managers associated with target job postings.
"""

from __future__ import annotations

import os
import urllib.parse
from typing import Any, Dict, List

import db


def generate_outreach_dorks(company: str, title: str) -> Dict[str, str]:
    """
    Generates tailored Google/LinkedIn search dorks to identify hiring managers
    and recruiters for a company and role.
    """
    clean_company = company.strip()
    clean_title = title.strip()

    # Dork 1: Technical Hiring Manager (Director/VP/Engineering Manager)
    hm_query = f'site:linkedin.com/in ("{clean_company}") ("Engineering Manager" OR "Director of Engineering" OR "VP of Engineering" OR "Head of Engineering")'

    # Dork 2: Technical Recruiter / Talent Acquisition
    recruiter_query = f'site:linkedin.com/in ("{clean_company}") ("Technical Recruiter" OR "Talent Partner" OR "Head of Talent")'

    # Dork 3: Peer Engineers on the team
    peer_query = f'site:linkedin.com/in ("{clean_company}") ("{clean_title}")'

    return {
        "hiring_manager_search_url": f"https://www.google.com/search?q={urllib.parse.quote(hm_query)}",
        "recruiter_search_url": f"https://www.google.com/search?q={urllib.parse.quote(recruiter_query)}",
        "peer_search_url": f"https://www.google.com/search?q={urllib.parse.quote(peer_query)}",
        "hiring_manager_query": hm_query,
        "recruiter_query": recruiter_query,
        "peer_query": peer_query,
    }


def create_lead_placeholder(
    company: str,
    role_type: str = "Recruiter",
    name: str = "Pending Discovery",
    conn: Any = None,
) -> str:
    """Creates a CRM contact lead placeholder in data.db."""
    dorks = generate_outreach_dorks(company, "Software Engineer")
    notes = f"Generated Lead Search: {dorks['recruiter_search_url']}"
    contact_data = {
        "name": name,
        "company": company,
        "title": role_type,
        "notes": notes,
    }
    return db.upsert_contact(contact_data, conn=conn)


def main() -> None:
    """CLI execution entrypoint."""
    print(
        "\n\033[1m\033[38;2;139;117;255m✦ ────────────────────────────────────────────────────────────── ✦\033[0m"
    )
    print(
        "  \033[1m\033[38;2;139;117;255m◈ RESUME-BUILDER RECRUITER & LEAD ENRICHMENT\033[0m"
    )
    print(
        "\033[1m\033[38;2;139;117;255m✦ ────────────────────────────────────────────────────────────── ✦\033[0m\n"
    )
    sample_dorks = generate_outreach_dorks("Datadog", "Senior Software Engineer")
    print(
        "  \033[1m\033[38;2;0;164;255mSample Search Dork Patterns (Datadog - Senior Software Engineer):\033[0m"
    )
    print(
        f"  \033[1m\033[38;2;18;199;143m✓ Hiring Manager Dork:\033[0m \033[38;2;163;163;163m{sample_dorks['hiring_manager_query']}\033[0m"
    )
    print(
        f"  \033[1m\033[38;2;18;199;143m✓ Recruiter Dork:     \033[0m \033[38;2;163;163;163m{sample_dorks['recruiter_query']}\033[0m\n"
    )


if __name__ == "__main__":
    main()
