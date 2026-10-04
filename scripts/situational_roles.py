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


def load_situational_roles(profile: str | None = None) -> dict:
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
        "clerical_swap": data.get("clerical_swap") or {},
    }


def _any_match(patterns: list, text_lower: str) -> bool:
    return any(re.search(pattern, text_lower) for pattern in patterns)


def detect_situational_candidates(jd_text: str, roles_data: dict | None = None) -> list:
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


def bank_minimums_for(candidates: list, roles_data: dict | None = None) -> dict:
    """Maps each candidate's bank_tag to the situational minimum, for
    mine_bullet_bank()'s extra_company_minimums parameter."""
    if roles_data is None:
        roles_data = load_situational_roles()
    roles = roles_data["roles"]
    min_bullets = roles_data["situational_min_bullets"]
    return {roles[name]["bank_tag"]: min_bullets for name in candidates}


def detect_clerical_swap(job_title: str, roles_data: dict | None = None) -> dict | None:
    """Returns {"replaces": [...], "adds": [...]} when job_title marks a
    clerical/administrative posting, else None.

    On such a posting the clerical situational roles (adds) take the place
    of the marketing roles named in replaces; on every other posting the
    clerical roles stay out entirely. Gated on the TITLE only -- body text
    like "administrative support" or "data entry" appears in plenty of
    marketing postings -- and a title that also matches an exclude keyword
    ("Marketing Coordinator / Administrative Assistant") stays marketing.
    Config lives under situational_roles.yaml's clerical_swap: key."""
    if roles_data is None:
        roles_data = load_situational_roles()
    cfg = roles_data.get("clerical_swap") or {}
    title_lower = (job_title or "").lower()
    if not title_lower or not cfg.get("title_keywords"):
        return None
    if not _any_match(cfg["title_keywords"], title_lower):
        return None
    if _any_match(cfg.get("exclude_title_keywords", []), title_lower):
        return None
    return {
        "replaces": list(cfg.get("replaces", [])),
        "adds": list(cfg.get("adds", [])),
    }


def apply_clerical_swap(profile_data: dict, swap: dict | None) -> dict:
    """profile_data with the swap's replaced roles dropped and its added
    roles marked swap_active, so roster/floor/ceiling/prompt code treats
    them as unconditional for this build. A no-op copy when swap is None."""
    if not swap:
        return profile_data
    replaces, adds = set(swap["replaces"]), set(swap["adds"])
    roles = []
    for role in profile_data.get("roles") or []:
        name = str(role.get("name", "")).strip()
        if name in replaces:
            continue
        roles.append({**role, "swap_active": True} if name in adds else role)
    return {**profile_data, "roles": roles}


def strip_clerical_roles(profile_data: dict, roles_data: dict | None = None) -> dict:
    """profile_data with the clerical swap's `adds` roles removed -- for
    non-clerical builds, so the prompt's role rules/roster can't offer them."""
    cfg = (roles_data if roles_data is not None else load_situational_roles()).get(
        "clerical_swap"
    ) or {}
    adds = set(cfg.get("adds") or [])
    if not adds:
        return profile_data
    roles = [
        r
        for r in profile_data.get("roles") or []
        if str(r.get("name", "")).strip() not in adds
    ]
    return {**profile_data, "roles": roles}
