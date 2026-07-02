"""
normalize_resume.py — Unconditional post-processing for content that has
zero legitimate per-JD variation. Runs on the builder's raw output before
critique and before the validator (validate_resume.py) sees it, so those
downstream steps only ever deal with already-correct fixed content and
formatting, never the builder's attempt at it.
"""

import re

import fixed_content

_SECTION_DEFAULTS = {
    "SECTION_SUMMARY": "Professional Summary",
    "SECTION_SKILLS": "Skills",
    "SECTION_EXPERIENCE": "Work Experience",
    "SECTION_CERTIFICATIONS": "Training & Certifications",
    "SECTION_EDUCATION": "Education",
}


def _and_to_ampersand(text: str) -> str:
    return re.sub(r"\band\b", "&", text, flags=re.IGNORECASE)


def normalize(resume_data: dict) -> dict:
    """Returns a new dict; never mutates the input."""
    result = dict(resume_data)

    result["CERTIFICATIONS"] = list(fixed_content.CERTIFICATIONS)
    result["EDUCATION"] = fixed_content.build_education(
        result.get("KU_ACHIEVEMENT_KEY", ""),
        result.get("KCKCC_ACHIEVEMENT_KEY", ""),
    )

    for key, value in _SECTION_DEFAULTS.items():
        result[key] = value

    if result.get("TAGLINE"):
        result["TAGLINE"] = _and_to_ampersand(result["TAGLINE"]).upper()

    return result
