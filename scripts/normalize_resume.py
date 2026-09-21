"""
normalize_resume.py — Unconditional post-processing for content that has
zero legitimate per-JD variation. Runs on the builder's raw output before
critique and before the validator (validate_resume.py) sees it, so those
downstream steps only ever deal with already-correct fixed content and
formatting, never the builder's attempt at it.
"""

import re

import profile_paths

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

# A profile whose roster splits one employer into several stints keys those
# rows -- and the bullet bank's tags -- as "Company — Stint Title", because
# mine_bullet_bank()'s roster allowlist is exact-match and both rows need
# distinct names. That key is bookkeeping, not display text: it reached the
# rendered resume as a job-meta line reading "mIQroTech Inc. — Lead Data
# Scientist" directly above a job-title of "Lead Data Scientist" (observed
# 2026-09-16, both stints).
#
# Deliberately NOT a blanket "strip everything after an em dash": a real
# company name may legitimately contain one. The suffix is removed only when
# it is exactly this entry's own title, which is the annotation case and
# cannot collide with a genuine name.
_STINT_SUFFIX_SEPARATORS = ("—", "–", "-")


def _strip_stint_annotation(company: str, title: str) -> str:
    """ "mIQroTech Inc. — Lead Data Scientist" + title "Lead Data Scientist"
    -> "mIQroTech Inc.". Returns company unchanged when the suffix is not
    the title, or when stripping would leave nothing."""
    if not company or not title:
        return company
    for sep in _STINT_SUFFIX_SEPARATORS:
        head, found, tail = company.rpartition(sep)
        if found and tail.strip().casefold() == title.strip().casefold():
            return head.strip() or company
    return company


# Dates are numeric MM/YYYY per style_rules.yaml ("Dates always numeric
# (08/2016 not August 2016)") and tailor_resume.md, but the builder model
# honors that unevenly -- a real build emitted "05/2021 – May 2022", numeric
# start and spelled-out end, which recruiter_score.yaml then marks down as
# "Mixed date formats". The rule is already in the prompt, so this is a
# deterministic cleanup rather than more prompt text.
_MONTHS = {
    "jan": "01",
    "feb": "02",
    "mar": "03",
    "apr": "04",
    "may": "05",
    "jun": "06",
    "jul": "07",
    "aug": "08",
    "sep": "09",
    "oct": "10",
    "nov": "11",
    "dec": "12",
}
_SPELLED_MONTH_YEAR = re.compile(r"\b([A-Za-z]{3,9})\.?\s+(\d{4})\b")


def _numeric_period(period: str) -> str:
    """ "05/2021 – May 2022" -> "05/2021 – 05/2022". Leaves anything it does
    not recognize (notably "Present") untouched."""
    if not period:
        return period

    def _sub(match):
        month = _MONTHS.get(match.group(1)[:3].casefold())
        return f"{month}/{match.group(2)}" if month else match.group(0)

    return _SPELLED_MONTH_YEAR.sub(_sub, period)


def _and_to_ampersand(text: str) -> str:
    return re.sub(r"\band\b", "&", text, flags=re.IGNORECASE)


def _sanitize_group_starts(raw, bullet_count: int) -> dict:
    """Normalizes one entry's achievement_group_starts to a clean
    {str(index) -> label} map. The model supplies zero-based string indices
    into `achievements`; anything out of range, non-numeric, empty-labeled,
    or duplicate-indexed is dropped rather than trusted -- renderers walk
    achievements in order and would otherwise mislabel or crash. An absent
    or empty map (the normal case) stays {}."""
    if not isinstance(raw, dict) or bullet_count <= 0:
        return {}
    cleaned: dict = {}
    for key, label in raw.items():
        try:
            index = int(str(key).strip())
        except (TypeError, ValueError):
            continue
        if not 0 <= index < bullet_count:
            continue
        label = str(label or "").strip()
        if not label or str(index) in cleaned:
            continue
        cleaned[str(index)] = label
    # A group start at index 0 is meaningless (the first bullet already
    # begins the entry); drop it so renderers never print a dangling label.
    cleaned.pop("0", None)
    return cleaned


def grouped_achievements(job: dict) -> list:
    """Splits one EXPERIENCE entry's bullets into labeled segments:
    [(label_or_None, [bullets...]), ...], in document order. Renderers use
    this to honor achievement_group_starts (craft-area sub-headers); an
    entry with no group starts comes back as [(None, all_bullets)] so every
    caller keeps a single code path. Expects the map AFTER
    _sanitize_group_starts -- indices are trusted here."""
    achievements = job.get("achievements") or []
    group_starts = job.get("achievement_group_starts") or {}
    if not group_starts:
        return [(None, list(achievements))]
    starts = sorted(int(k) for k in group_starts)
    segments = []
    if starts[0] > 0:
        segments.append((None, achievements[: starts[0]]))
    for i, start in enumerate(starts):
        end = starts[i + 1] if i + 1 < len(starts) else len(achievements)
        segments.append((group_starts[str(start)], achievements[start:end]))
    return [(label, bullets) for label, bullets in segments if bullets]


def _apply_company_metadata(
    job: dict, company: str, fixed_content, include_optional_clients: bool
) -> None:
    """Applies the profile's per-company fixed content onto one job in place.

    Covers size/revenue and location metadata, rename notes, fixed titles
    and title descriptors, the career note, and the client roster.
    """
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
    if (
        descriptor
        and job.get("title")
        and not job["title"].rstrip().endswith(f"({descriptor})")
    ):
        job["title"] = f"{job['title']} ({descriptor})"

    if (
        fixed_content.CAREER_NOTE_COMPANY
        and company == fixed_content.CAREER_NOTE_COMPANY
    ):
        job["career_note"] = fixed_content.CAREER_NOTE

    clients = fixed_content.CLIENTS.get(company)
    if clients and (clients["essential"] or include_optional_clients):
        job["clients"] = clients["list"]
    else:
        job.pop("clients", None)


def normalize(resume_data: dict, include_optional_clients: bool = True) -> dict:
    """Returns a new dict; never mutates the input.

    `include_optional_clients=False` drops non-essential client rosters (see
    fixed_content.CLIENTS) -- used by orchestrator's trim loop as a free,
    non-LLM trim step before the more expensive LLM-driven ones.
    """
    fixed_content = profile_paths.fixed_content_module()
    result = dict(resume_data)

    result.update(fixed_content.CONTACT_INFO)
    result.pop("PORTFOLIO_URL", None)
    result.pop("PORTFOLIO_DISPLAY", None)

    # design_only entries (see profile_paths.has_design_only_credentials())
    # only belong on the page when the builder decided the JD has real
    # graphic-design responsibilities -- default False when the field was
    # never asked (a profile with no design_only entries at all).
    include_design_credentials = bool(result.get("INCLUDE_DESIGN_CREDENTIALS"))

    result["CERTIFICATIONS"] = [
        cert
        for cert in fixed_content.CERTIFICATIONS
        if include_design_credentials or not cert.get("design_only")
    ]
    # Fixed like certifications: a profile's patents never vary per JD.
    result["PATENTS"] = [
        dict(p) for p in (getattr(fixed_content, "PATENTS", None) or [])
    ]
    # EDU_ACHIEVEMENT_KEY_<n> fields are numbered by profile_paths.
    # education_achievement_slots()'s order (see orchestrator.py's
    # build_education_achievement_schema_fields(), which built the schema
    # the builder answered against) -- mapped back to institution names
    # here so build_education() doesn't need to know about slot numbers.
    achievement_keys = {
        institution: result.get(f"EDU_ACHIEVEMENT_KEY_{i}", "")
        for i, (institution, _options) in enumerate(
            profile_paths.education_achievement_slots(), 1
        )
    }
    result["EDUCATION"] = [
        edu
        for edu in fixed_content.build_education(achievement_keys)
        if include_design_credentials or not edu.get("design_only")
    ]

    if result.get("EXPERIENCE"):
        new_experience = []
        career_break_entry = getattr(fixed_content, "CAREER_BREAK_ENTRY", None)
        has_break_already = any(
            "career break" in str(job.get("company", "")).lower()
            for job in result["EXPERIENCE"]
        )

        for job in result["EXPERIENCE"]:
            job = dict(job)
            job["achievement_group_starts"] = _sanitize_group_starts(
                job.get("achievement_group_starts"),
                len(job.get("achievements") or []),
            )
            company = _RENAME_SUFFIX_PATTERN.sub("", job.get("company", ""))
            # Before the fixed_content lookups below, so they key off the real
            # company name rather than a roster stint key that would match
            # nothing in COMPANY_META/CLIENTS/etc.
            company = _strip_stint_annotation(company, job.get("title", ""))
            job["company"] = company
            if job.get("period"):
                job["period"] = _numeric_period(job["period"])

            if (
                career_break_entry
                and not has_break_already
                and company == "Treering Yearbooks"
            ):
                new_experience.append(dict(career_break_entry))
                has_break_already = True

            _apply_company_metadata(
                job, company, fixed_content, include_optional_clients
            )

            new_experience.append(job)
        result["EXPERIENCE"] = new_experience

    for key, value in _SECTION_DEFAULTS.items():
        result[key] = value

    if result.get("TAGLINE"):
        result["TAGLINE"] = _and_to_ampersand(result["TAGLINE"]).upper()

    return result
