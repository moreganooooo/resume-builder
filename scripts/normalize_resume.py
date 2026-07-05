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

# normalize() runs on every retry/trim pass, sometimes several times over the
# same resume_data -- strip a previously-applied "(Now X)" rename suffix
# before using the company name as a fixed_content lookup key, so a 2nd+
# pass doesn't silently miss COMPANY_META/CLIENTS/etc. lookups just because
# the 1st pass already renamed the field it reads its key from.
_RENAME_SUFFIX_PATTERN = re.compile(r"\s*\(Now [^)]+\)$")


def _and_to_ampersand(text: str) -> str:
    return re.sub(r"\band\b", "&", text, flags=re.IGNORECASE)


def normalize(resume_data: dict, include_optional_clients: bool = True) -> dict:
    """Returns a new dict; never mutates the input.

    `include_optional_clients=False` drops non-essential client rosters (see
    fixed_content.CLIENTS) -- used by orchestrator's trim loop as a free,
    non-LLM trim step before the more expensive LLM-driven ones.
    """
    result = dict(resume_data)

    result.update(fixed_content.CONTACT_INFO)
    result.pop("PORTFOLIO_URL", None)
    result.pop("PORTFOLIO_DISPLAY", None)

    result["CERTIFICATIONS"] = list(fixed_content.CERTIFICATIONS)
    result["EDUCATION"] = fixed_content.build_education(
        result.get("KU_ACHIEVEMENT_KEY", ""),
        result.get("KCKCC_ACHIEVEMENT_KEY", ""),
    )

    if result.get("EXPERIENCE"):
        new_experience = []
        for job in result["EXPERIENCE"]:
            job = dict(job)
            company = _RENAME_SUFFIX_PATTERN.sub("", job.get("company", ""))

            meta = fixed_content.COMPANY_META.get(company)
            if meta:
                if "size_revenue" in meta:
                    job["size_revenue"] = meta["size_revenue"]
                if "location" in meta:
                    job["location"] = meta["location"]

            rename_note = fixed_content.COMPANY_RENAME_NOTE.get(company)
            if rename_note:
                job["company"] = f"{company} (Now {rename_note})"

            fixed_title = fixed_content.COMPANY_FIXED_TITLE.get(company)
            if fixed_title:
                job["title"] = fixed_title

            descriptor = fixed_content.COMPANY_TITLE_DESCRIPTOR.get(company)
            if descriptor and job.get("title") and not job["title"].rstrip().endswith(f"({descriptor})"):
                job["title"] = f"{job['title']} ({descriptor})"

            if company == "Treering Yearbooks":
                job["career_note"] = fixed_content.CAREER_NOTE

            clients = fixed_content.CLIENTS.get(company)
            if clients and (clients["essential"] or include_optional_clients):
                job["clients"] = clients["list"]
            else:
                job.pop("clients", None)

            new_experience.append(job)
        result["EXPERIENCE"] = new_experience

    for key, value in _SECTION_DEFAULTS.items():
        result[key] = value

    if result.get("TAGLINE"):
        result["TAGLINE"] = _and_to_ampersand(result["TAGLINE"]).upper()

    return result
