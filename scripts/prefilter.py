"""Capability Gate Pre-Filter Module.

Provides fast, lightweight pre-flight filtering of job descriptions
to catch hard deal-breakers (salary below floor, non-remote requirements,
banned keywords) before spending expensive LLM tokens.
"""

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional, Tuple


def evaluate_preflight_gate(
    job_text: str,
    deal_breakers: Optional[Dict[str, Any]] = None,
    required_remote: bool = False,
    salary_floor: Optional[int] = None,
    banned_keywords: Optional[List[str]] = None,
) -> Tuple[bool, List[str]]:
    """Evaluates whether a job posting passes initial hard deal-breaker criteria.

    Returns:
        (passes_gate, list_of_rejection_reasons)
    """
    if not job_text or not job_text.strip():
        return False, ["Empty job description"]

    reasons: List[str] = []
    text_lower = job_text.lower()

    deal_breakers = deal_breakers or {}
    req_remote = deal_breakers.get("require_remote", required_remote)
    floor = deal_breakers.get("salary_floor", salary_floor)
    banned = deal_breakers.get("banned_keywords", banned_keywords or [])

    # 1. Check strict remote requirement
    if req_remote:
        # Check for non-remote signals (on-site only)
        on_site_patterns = [
            r"\b100%\s*on-?site\b",
            r"\bon-?site\s+only\b",
            r"\bmust\s+work\s+in\s+office\s+5\s+days\b",
            r"\bno\s+remote\b",
            r"\bin-office\s+only\b",
        ]
        for pat in on_site_patterns:
            if re.search(pat, text_lower):
                reasons.append(
                    "Role requires 100% on-site work (fails remote-only criteria)"
                )
                break

    # 2. Check banned keywords (e.g. unpaid internship, secret clearance required)
    for kw in banned:
        if kw.lower() in text_lower:
            reasons.append(f"Contains banned keyword: '{kw}'")

    # 3. Check salary floor if explicit salary is mentioned in text
    if floor is not None and floor > 0:
        salary_match = re.search(
            r"\$([0-9]{2,3}),?([0-9]{3})(?:\s*-\s*\$([0-9]{2,3}),?([0-9]{3}))?",
            job_text,
        )
        if salary_match:
            try:
                min_val = int(salary_match.group(1) + salary_match.group(2))
                max_val = (
                    int(salary_match.group(3) + salary_match.group(4))
                    if salary_match.group(3)
                    else min_val
                )
                if max_val < floor:
                    reasons.append(
                        f"Advertised salary ceiling (${max_val:,}) is below floor threshold (${floor:,})"
                    )
            except Exception:
                pass

    passes = len(reasons) == 0
    return passes, reasons


def main() -> None:
    """CLI execution entrypoint."""
    print(
        "\n\033[1m\033[38;2;139;117;255m✦ ────────────────────────────────────────────────────────────── ✦\033[0m"
    )
    print(
        "  \033[1m\033[38;2;139;117;255m◈ RESUME-BUILDER ZERO-COST PRE-FLIGHT CAPABILITY GATE\033[0m"
    )
    print(
        "\033[1m\033[38;2;139;117;255m✦ ────────────────────────────────────────────────────────────── ✦\033[0m\n"
    )
    print("  \033[1m\033[38;2;0;164;255mActive Deal-Breaker Filters:\033[0m")
    print(
        "    \033[1m\033[38;2;18;199;143m✓ Hard On-Site Filter\033[0m   \033[38;2;163;163;163m(enforces 100% remote criteria)\033[0m"
    )
    print(
        "    \033[1m\033[38;2;18;199;143m✓ Salary Floor Filter\033[0m   \033[38;2;163;163;163m(rejects postings below compensation minimum)\033[0m"
    )
    print(
        "    \033[1m\033[38;2;18;199;143m✓ Banned Keyword Gate\033[0m   \033[38;2;163;163;163m(filters clearance requirements, unpaid terms)\033[0m\n"
    )


if __name__ == "__main__":
    main()
