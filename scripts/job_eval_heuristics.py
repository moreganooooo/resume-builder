"""
job_eval_heuristics.py -- Deterministic evaluation heuristics for job descriptions:
1. Ghost Job Heuristics & Stale Postings Detection (Item 10)
2. Pay Transparency & Salary Extraction Engine (Item 11)
3. Visa Sponsorship & Relocation Filter (Item 13)
"""

import re
from typing import Any, Dict, Optional


def extract_salary_range(text: str) -> Dict[str, Any]:
    """
    Extracts salary range, currency, and frequency from job posting text.
    Returns:
        {
            "min_salary": float or None,
            "max_salary": float or None,
            "currency": "USD" or None,
            "period": "annual" | "hourly" | None,
            "raw_match": str or None,
        }
    """
    if not text:
        return {
            "min_salary": None,
            "max_salary": None,
            "currency": None,
            "period": None,
            "raw_match": None,
        }

    # Common patterns:
    # $120,000 - $160,000 / year
    # $120k - $160k
    # $60 - $85 / hr
    # $130,000 to $170,000 per annum
    range_regex = re.compile(
        r"(?:\$|USD\s*)(\d{1,3}(?:,\d{3})+|\d{2,3}k|\d{2,3})\s*(?:-|–|—|to)\s*(?:\$|USD\s*)?(\d{1,3}(?:,\d{3})+|\d{2,3}k|\d{2,3})\s*(?:/|\s*(?:per|a)\s*)?(year|annum|yr|hr|hour)?",
        re.IGNORECASE,
    )

    match = range_regex.search(text)
    if not match:
        # Check for single salary point, e.g. "$140,000/year" or "Base salary: $150,000"
        single_regex = re.compile(
            r"(?:salary|compensation|pay):\s*(?:\$|USD\s*)(\d{1,3}(?:,\d{3})+|\d{2,3}k)\s*(?:/|\s*(?:per|a)\s*)?(year|annum|yr|hr|hour)?",
            re.IGNORECASE,
        )
        single_match = single_regex.search(text)
        if single_match:
            raw_val, period_raw = single_match.groups()
            val = _parse_number(raw_val)
            period = (
                "hourly"
                if (period_raw and "h" in period_raw.lower()) or (val and val < 300)
                else "annual"
            )
            return {
                "min_salary": val,
                "max_salary": val,
                "currency": "USD",
                "period": period,
                "raw_match": single_match.group(0),
            }
        return {
            "min_salary": None,
            "max_salary": None,
            "currency": None,
            "period": None,
            "raw_match": None,
        }

    raw_min, raw_max, period_raw = match.groups()
    val_min = _parse_number(raw_min)
    val_max = _parse_number(raw_max)

    period = "annual"
    if period_raw and ("hr" in period_raw.lower() or "hour" in period_raw.lower()):
        period = "hourly"
    elif val_max and val_max < 300:
        period = "hourly"

    return {
        "min_salary": val_min,
        "max_salary": val_max,
        "currency": "USD",
        "period": period,
        "raw_match": match.group(0),
    }


def _parse_number(s: str) -> Optional[float]:
    if not s:
        return None
    s = s.lower().replace(",", "").replace("$", "").strip()
    if s.endswith("k"):
        try:
            return float(s[:-1]) * 1000.0
        except ValueError:
            return None
    try:
        return float(s)
    except ValueError:
        return None


def compute_ghost_job_probability(
    jd_text: str,
    posting_age_days: Optional[int] = None,
    repost_count: int = 0,
) -> Dict[str, Any]:
    """
    Evaluates probability (0.0 to 1.0) that a job posting is a 'ghost job'
    (evergreen posting, resume-harvesting, or stale unfilled vacancy).
    """
    prob = 0.0
    flags = []

    # 1. Posting age heuristics
    if posting_age_days is not None:
        if posting_age_days >= 60:
            prob += 0.45
            flags.append(f"Posting is very old ({posting_age_days} days)")
        elif posting_age_days >= 30:
            prob += 0.25
            flags.append(f"Posting is stale ({posting_age_days} days)")

    # 2. Repost frequency
    if repost_count >= 3:
        prob += 0.35
        flags.append(f"Frequently reposted ({repost_count} times)")
    elif repost_count >= 1:
        prob += 0.15
        flags.append("Reposted listing")

    # 3. Evergreen / Generic phrasing
    lowered = (jd_text or "").lower()
    evergreen_patterns = [
        (
            r"\b(?:talent community|talent pool|future opportunities|pipeline building|always looking for)\b",
            0.35,
            "Generic talent pool indicator",
        ),
        (
            r"\b(?:ongoing need|multiple openings across teams|general application)\b",
            0.25,
            "Broad unspecified opening",
        ),
        (
            r"\b(?:no current opening|exploratory conversations)\b",
            0.40,
            "Explicit exploratory/no immediate hire statement",
        ),
    ]

    for pattern, weight, reason in evergreen_patterns:
        if re.search(pattern, lowered):
            prob += weight
            flags.append(reason)

    # 4. Short / Thin description penalty
    if len(lowered.strip()) < 300:
        prob += 0.20
        flags.append("Thin/minimal job description (<300 chars)")

    final_prob = min(1.0, round(prob, 2))
    return {
        "ghost_probability": final_prob,
        "is_ghost_risk": final_prob >= 0.50,
        "risk_flags": flags,
    }


def classify_visa_sponsorship(jd_text: str) -> Dict[str, Any]:
    """
    Classifies visa sponsorship and US work authorization stance.
    Returns:
        {
            "status": "sponsors" | "no_sponsorship" | "unknown",
            "reason": str or None,
            "us_citizenship_required": bool,
        }
    """
    lowered = (jd_text or "").lower()

    # Explicit no sponsorship
    no_sponsor_patterns = [
        r"without (?:the )?need for sponsorship",
        r"not offering sponsorship",
        r"unable to sponsor",
        r"no (?:visa )?sponsorship",
        r"will not sponsor",
        r"cannot sponsor",
        r"must be authorized to work in the (?:us|united states) without",
        r"must be legally authorized to work in the united states without sponsorship",
    ]
    for pat in no_sponsor_patterns:
        if re.search(pat, lowered):
            return {
                "status": "no_sponsorship",
                "reason": "Explicit no-sponsorship clause",
                "us_citizenship_required": False,
            }

    # Clearance / Citizenship strict requirements
    clearance_patterns = [
        r"u\.?s\.? citizenship (?:is )?required",
        r"must be a u\.?s\.? citizen",
        r"security clearance required",
        r"active secret clearance",
        r"ts/sci",
    ]
    for pat in clearance_patterns:
        if re.search(pat, lowered):
            return {
                "status": "no_sponsorship",
                "reason": "US Citizenship or Security Clearance required",
                "us_citizenship_required": True,
            }

    # Explicit sponsorship offered
    sponsor_patterns = [
        r"visa sponsorship (?:is )?available",
        r"sponsorship (?:is )?provided",
        r"will provide sponsorship",
        r"h-?1b (?:transfers?|sponsorship) (?:supported|available|provided)",
    ]
    for pat in sponsor_patterns:
        if re.search(pat, lowered):
            return {
                "status": "sponsors",
                "reason": "Explicit sponsorship offered",
                "us_citizenship_required": False,
            }

    return {
        "status": "unknown",
        "reason": None,
        "us_citizenship_required": False,
    }


def main() -> None:
    """CLI execution entrypoint."""
    print(
        "\n\033[1m\033[38;2;139;117;255m✦ ────────────────────────────────────────────────────────────── ✦\033[0m"
    )
    print(
        "  \033[1m\033[38;2;139;117;255m💎 RESUME-BUILDER JOB EVALUATION HEURISTICS\033[0m"
    )
    print(
        "\033[1m\033[38;2;139;117;255m✦ ────────────────────────────────────────────────────────────── ✦\033[0m\n"
    )
    print("  \033[1m\033[38;2;0;164;255mActive Deterministic Heuristic Models:\033[0m")
    print(
        "    \033[1m\033[38;2;18;199;143m✓ Ghost Job Probability Engine\033[0m \033[38;2;163;163;163m(posting age, repost count, evergreen patterns)\033[0m"
    )
    print(
        "    \033[1m\033[38;2;18;199;143m✓ Pay Transparency Extractor\033[0m  \033[38;2;163;163;163m(annual / hourly regex parsing)\033[0m"
    )
    print(
        "    \033[1m\033[38;2;18;199;143m✓ Visa Sponsorship Classifier\033[0m \033[38;2;163;163;163m(H-1B, clearance, citizenship)\033[0m\n"
    )


if __name__ == "__main__":
    main()
