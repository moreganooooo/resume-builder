"""
situational_roles.py — the deterministic half of the "hybrid gate" for
situational/optional work-history entries (IDEAS.md, resolved 2026-07-04).

A keyword pre-check per optional company against the JD text; only
companies clearing this gate are even presented to the builder as
candidates. The LLM (guided by tailor_resume.md's own section) makes the
actual go/no-go call among cleared candidates -- this module never decides
whether a situational role actually gets used, only whether it's even a
candidate worth mentioning.

Situational-role data lives per-profile at profiles/<name>/situational_roles.yaml
(not hardcoded here) -- see profile_paths.situational_roles_path(). bank_tag
values must match that profile's bullet-bank-keepers-audited.csv's "Role /
Company" column exactly.
"""

import os
import re

import profile_paths
import yaml


def _make_fallback_situational_roles() -> dict:
    return {
        "situational_min_bullets": 2,
        "roles": {
            "Humane Society of Greater Kansas City": {
                "display_name": "Humane Society of Greater Kansas City",
                "bank_tag": "Humane Society of Greater Kansas City",
                "trigger_keywords": [
                    "animal welfare",
                    "animal shelter",
                    "animal rescue",
                    "humane society",
                    "veterinary",
                ],
            },
            "Unisource Document Products": {
                "display_name": "Unisource Document Products",
                "bank_tag": "Unisource Document Products",
                "trigger_keywords": [
                    "print production",
                    "print services",
                    "commercial printing",
                    "document solutions",
                    "print management",
                ],
            },
            "Kansas Colloquies": {
                "display_name": "Kansas Colloquies",
                "bank_tag": "Kansas Colloquies",
                "trigger_keywords": [
                    "journalism",
                    "newspaper",
                    "newsroom",
                    "investigative reporting",
                    r"\breporter\b",
                    "news writing",
                    "student newspaper",
                    "investigative journalism",
                ],
            },
            "KU Payroll Office": {
                "display_name": "KU Payroll Office",
                "bank_tag": "Payroll",
                "trigger_keywords": [
                    "payroll processing",
                    "payroll administration",
                    r"\bpayroll\b",
                ],
            },
            "DeJoy, Knauff & Blood": {
                "display_name": "DeJoy, Knauff & Blood",
                "bank_tag": "DeJoy",
                "trigger_keywords": [
                    "tax preparation",
                    "tax compliance",
                    "bookkeeping",
                    "tax audit",
                    "financial audit",
                    "accounting clerk",
                    "audit readiness",
                ],
            },
            "USitek": {
                "display_name": "USitek",
                "bank_tag": "USitek",
                "admin_keywords": [
                    "clerical",
                    "administrative support",
                    "administrative assistant",
                ],
                "design_keywords": ["graphic design"],
            },
        },
    }


def load_situational_roles(profile: str = None) -> dict:
    """Reads profiles/<profile>/situational_roles.yaml. Returns
    {"situational_min_bullets": int, "roles": {display_name: config_dict}}
    -- an empty {"situational_min_bullets": 2, "roles": {}} if the file
    doesn't exist yet (e.g. a freshly-bootstrapped profile with no
    situational roles defined)."""
    path = profile_paths.situational_roles_path(profile)
    if not os.path.exists(path):
        active = profile or profile_paths.active_profile()
        if active == "morgan":
            return _make_fallback_situational_roles()
        return {"situational_min_bullets": 2, "roles": {}}
    with open(path, "r") as f:
        data = yaml.safe_load(f) or {}
    roles = {entry["display_name"]: entry for entry in data.get("roles", [])}
    return {
        "situational_min_bullets": data.get("situational_min_bullets", 2),
        "roles": roles,
    }


def _any_match(patterns: list, text_lower: str) -> bool:
    return any(re.search(pattern, text_lower) for pattern in patterns)


def detect_situational_candidates(jd_text: str, roles_data: dict = None) -> list:
    """Returns the list of situational-role display names whose keyword
    gate matched jd_text; [] if none did."""
    if roles_data is None:
        roles_data = load_situational_roles()
    roles = roles_data["roles"]
    text_lower = (jd_text or "").lower()
    candidates = []

    for display_name, config in roles.items():
        if "admin_keywords" in config and "design_keywords" in config:
            if _any_match(config["admin_keywords"], text_lower) and _any_match(
                config["design_keywords"], text_lower
            ):
                candidates.append(display_name)
            continue
        if _any_match(config.get("trigger_keywords", []), text_lower):
            candidates.append(display_name)

    return candidates


def bank_minimums_for(candidates: list, roles_data: dict = None) -> dict:
    """Maps each candidate's bank_tag to the situational minimum, for
    mine_bullet_bank()'s extra_company_minimums parameter."""
    if roles_data is None:
        roles_data = load_situational_roles()
    roles = roles_data["roles"]
    min_bullets = roles_data["situational_min_bullets"]
    return {roles[name]["bank_tag"]: min_bullets for name in candidates}
