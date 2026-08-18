"""Company Blacklist Filter Module.

Filters out predatory employers, scam staffing agencies, and user-blacklisted
companies from the job ingestion pipeline.
"""

from __future__ import annotations

import json
import os
import re
from typing import Dict, Optional, Tuple

# Built-in baseline list of known predatory staffing shops, scam agencies,
# and high-friction employers
DEFAULT_BLACKLIST: Dict[str, str] = {
    "crossover": "High churn, invasive tracking software, predatory contracts",
    "crossover for work": "High churn, invasive tracking software, predatory contracts",
    "revature": "Mandatory 2-year lock-in contracts with exit penalty fees",
    "smoothstack": "Liquidated damages penalty clauses and lock-in contracts",
    "fDM group": "Long-term lock-in contract structure",
    "motion recruitment": "High-volume spam agency with fake job postings",
    "cybercoders": "Third-party resume harvesting agency with generic job postings",
    "robert half": "Third-party staffing aggregator with stale/ghost postings",
}


def normalize_company_name(name: str) -> str:
    """Normalize company name for fuzzy/case-insensitive matching."""
    if not name:
        return ""
    # Strip corporate suffixes and punctuation
    cleaned = re.sub(
        r"\b(inc|llc|ltd|corp|corporation|gmbh|co|plc)\b\.?",
        "",
        name.lower(),
        flags=re.IGNORECASE,
    )
    cleaned = re.sub(r"[^\w\s]", "", cleaned)
    return " ".join(cleaned.split())


def load_blacklist(custom_path: Optional[str] = None) -> Dict[str, str]:
    """Loads combined blacklist from built-in defaults and custom JSON file."""
    blacklist = dict(DEFAULT_BLACKLIST)
    if custom_path and os.path.isfile(custom_path):
        try:
            with open(custom_path, "r", encoding="utf-8") as f:
                custom_data = json.load(f)
                if isinstance(custom_data, dict):
                    for k, v in custom_data.items():
                        blacklist[k.strip().lower()] = str(v)
                elif isinstance(custom_data, list):
                    for item in custom_data:
                        if isinstance(item, str):
                            blacklist[item.strip().lower()] = "User blacklisted"
                        elif isinstance(item, dict) and "company" in item:
                            blacklist[item["company"].strip().lower()] = item.get(
                                "reason", "User blacklisted"
                            )
        except Exception:
            pass
    return blacklist


def is_blacklisted(
    company_name: str,
    custom_path: Optional[str] = None,
    blacklist_data: Optional[Dict[str, str]] = None,
) -> Tuple[bool, Optional[str]]:
    """Checks if a company is present on the blacklist.

    Returns:
        (True, reason) if blacklisted, (False, None) otherwise.
    """
    if not company_name:
        return False, None

    normalized = normalize_company_name(company_name)
    if not normalized:
        return False, None

    active_blacklist = (
        blacklist_data if blacklist_data is not None else load_blacklist(custom_path)
    )

    # Check exact match
    for blacklisted_comp, reason in active_blacklist.items():
        norm_blacklisted = normalize_company_name(blacklisted_comp)
        if (
            normalized == norm_blacklisted
            or norm_blacklisted in normalized
            or normalized in norm_blacklisted
        ):
            return True, reason

    return False, None


def main() -> None:
    """CLI execution entrypoint."""
    blacklist = load_blacklist()
    print(
        "\n\033[1m\033[38;2;139;117;255m✦ ────────────────────────────────────────────────────────────── ✦\033[0m"
    )
    print(
        "  \033[1m\033[38;2;139;117;255m💎 RESUME-BUILDER COMPANY BLACKLIST DIRECTORY\033[0m"
    )
    print(
        "\033[1m\033[38;2;139;117;255m✦ ────────────────────────────────────────────────────────────── ✦\033[0m\n"
    )
    print(
        f"  \033[1m\033[38;2;0;164;255mActive Blacklisted Employers ({len(blacklist)} total):\033[0m\n"
    )
    for company, reason in sorted(blacklist.items()):
        print(
            f"  \033[1m\033[38;2;255;123;153m✖ {company.title():<22}\033[0m \033[38;2;163;163;163m│ {reason}\033[0m"
        )
    print("")


if __name__ == "__main__":
    main()
