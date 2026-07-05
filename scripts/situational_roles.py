"""
situational_roles.py — the deterministic half of the "hybrid gate" for
situational/optional work-history entries (IDEAS.md, resolved 2026-07-04).

A keyword pre-check per optional company against the JD text; only
companies clearing this gate are even presented to the builder as
candidates. The LLM (guided by tailor_resume.md's own section) makes the
actual go/no-go call among cleared candidates -- this module never decides
whether a situational role actually gets used, only whether it's even a
candidate worth mentioning.

bank_tag values must match bullet-bank-keepers-audited.csv's "Role /
Company" column exactly -- confirmed 2026-07-05 that KU Payroll Office and
DeJoy, Knauff & Blood are tagged more tersely there ("Payroll", "DeJoy")
than their proper display names used on the actual resume.
"""

import re

SITUATIONAL_MIN_BULLETS = 2

SITUATIONAL_ROLES = {
    "Humane Society of Greater Kansas City": {
        "bank_tag": "Humane Society of Greater Kansas City",
        "trigger_keywords": [r"animal welfare", r"animal shelter", r"animal rescue", r"humane society", r"veterinary"],
    },
    "Unisource Document Products": {
        "bank_tag": "Unisource Document Products",
        "trigger_keywords": [r"print production", r"document management", r"print services", r"document solutions"],
    },
    "Kansas Colloquies": {
        "bank_tag": "Kansas Colloquies",
        "trigger_keywords": [r"journalism", r"newspaper", r"editorial", r"\breporter\b", r"news writing"],
    },
    "KU Payroll Office": {
        "bank_tag": "Payroll",
        "trigger_keywords": [r"payroll processing", r"payroll administration", r"\bpayroll\b"],
    },
    "DeJoy, Knauff & Blood": {
        "bank_tag": "DeJoy",
        "trigger_keywords": [r"tax preparation", r"tax compliance", r"bookkeeping", r"\baudit\b", r"accounting clerk"],
    },
    # USitek is a deliberate blend (clerical + graphic design) -- neither
    # signal alone is specific enough (generic admin roles and generic
    # design roles are both common and unrelated to this niche combo), so
    # detection requires both an admin-ish AND a design-ish term present.
    "USitek": {
        "bank_tag": "USitek",
        "admin_keywords": [r"clerical", r"administrative support", r"administrative assistant"],
        "design_keywords": [r"graphic design"],
    },
}


def _any_match(patterns: list, text_lower: str) -> bool:
    return any(re.search(pattern, text_lower) for pattern in patterns)


def detect_situational_candidates(jd_text: str) -> list:
    """Returns the list of situational-role display names whose keyword
    gate matched jd_text; [] if none did."""
    text_lower = (jd_text or "").lower()
    candidates = []

    for display_name, config in SITUATIONAL_ROLES.items():
        if display_name == "USitek":
            if _any_match(config["admin_keywords"], text_lower) and _any_match(config["design_keywords"], text_lower):
                candidates.append(display_name)
            continue
        if _any_match(config["trigger_keywords"], text_lower):
            candidates.append(display_name)

    return candidates


def bank_minimums_for(candidates: list) -> dict:
    """Maps each candidate's bank_tag to SITUATIONAL_MIN_BULLETS, for
    mine_bullet_bank()'s extra_company_minimums parameter."""
    return {SITUATIONAL_ROLES[name]["bank_tag"]: SITUATIONAL_MIN_BULLETS for name in candidates}
