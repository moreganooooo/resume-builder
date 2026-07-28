#!/usr/bin/env python3
"""
bootstrap_timeline.py

Builds a canonical company/role/date timeline from a new user's resume
and/or LinkedIn export, and matches every other extracted achievement
against it -- see bootstrap_bullet_bank.py for how this fits into the
overall ingestion flow.
"""

import os
import re
import sys
from typing import Optional

from pydantic import BaseModel

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
if SCRIPT_DIR not in sys.path:
    sys.path.insert(0, SCRIPT_DIR)

from bootstrap_extractors import EXTRACTION_MODEL, RawAchievement, WorkExperienceEntry  # noqa: E402
from gemini_client import GeminiClient  # noqa: E402


class TimelineEntry(BaseModel):
    company: str
    title: Optional[str] = None
    start_date: Optional[str] = None
    end_date: Optional[str] = None
    needs_review: bool = False
    conflict_note: Optional[str] = None


class TimelineMatchResult(BaseModel):
    matched_company: Optional[str] = None


def _normalize_company_name(name: str) -> str:
    """Lowercase, strip non-alphanumerics, for fuzzy same-company matching
    across documents that might spell a company name slightly differently."""
    return re.sub(r"[^a-z0-9]", "", name.lower())


def _extract_year(date_str: str | None) -> int | None:
    if not date_str:
        return None
    match = re.search(r"(19|20)\d{2}", date_str)
    return int(match.group(0)) if match else None


def _ranges_roughly_overlap(start_a, end_a, start_b, end_b) -> bool:
    """True if the two year ranges overlap at all. A missing/unparseable
    date on either side is treated as an open bound rather than a forced
    mismatch, since we'd rather under-flag than nag the user over dates
    we can't even parse."""
    ya_start, ya_end = _extract_year(start_a), _extract_year(end_a)
    yb_start, yb_end = _extract_year(start_b), _extract_year(end_b)
    if ya_start is None or yb_start is None:
        return True
    lo_a, hi_a = ya_start, (ya_end or 9999)
    lo_b, hi_b = yb_start, (yb_end or 9999)
    return lo_a <= hi_b and lo_b <= hi_a


def _year_in_range(year: int, start_date: str | None, end_date: str | None) -> bool:
    start_year = _extract_year(start_date) or 0
    end_year = _extract_year(end_date) or 9999
    return start_year <= year <= end_year


def build_timeline(by_source: dict[str, list[WorkExperienceEntry]]) -> list[TimelineEntry]:
    """
    Merges WorkExperienceEntry lists from the resume/LinkedIn documents
    (by_source keyed "linkedin_export"/"resume") into one canonical
    timeline. LinkedIn wins on date range when a same-company entry also
    appears in the resume with a differing-but-overlapping range. A
    same-company entry whose ranges disagree enough to suggest genuinely
    different stints is flagged needs_review instead of silently resolved.
    """
    primary = by_source.get("linkedin_export", [])
    secondary = by_source.get("resume", [])
    by_key: dict[str, TimelineEntry] = {}

    for e in primary:
        by_key[_normalize_company_name(e.company)] = TimelineEntry(
            company=e.company, title=e.title, start_date=e.start_date, end_date=e.end_date,
        )

    for e in secondary:
        key = _normalize_company_name(e.company)
        if key not in by_key:
            by_key[key] = TimelineEntry(
                company=e.company, title=e.title, start_date=e.start_date, end_date=e.end_date,
            )
            continue
        existing = by_key[key]
        if existing.start_date == e.start_date and existing.end_date == e.end_date:
            continue
        if _ranges_roughly_overlap(existing.start_date, existing.end_date, e.start_date, e.end_date):
            continue
        by_key[key] = TimelineEntry(
            company=existing.company,
            title=existing.title or e.title,
            start_date=existing.start_date,
            end_date=existing.end_date,
            needs_review=True,
            conflict_note=(
                f"LinkedIn shows {existing.start_date}-{existing.end_date}, "
                f"resume shows {e.start_date}-{e.end_date}"
            ),
        )

    return list(by_key.values())


def _llm_match(raw_text: str, timeline: list[TimelineEntry]) -> str | None:
    """LLM-assisted fallback for achievements whose wording implies a role
    ("while I was doing outbound sales") without a hint that matches any
    timeline entry by exact company/date/title substring."""
    options = "\n".join(
        f"- {e.company} ({e.title or 'unknown title'}, {e.start_date or '?'}-{e.end_date or '?'})"
        for e in timeline
    )
    raw, _ = GeminiClient.generate(
        model=EXTRACTION_MODEL,
        system_instruction=(
            "Given an achievement description and a list of a person's past "
            "roles, decide which single role (if any) this achievement most "
            "plausibly belongs to, based on context clues in the wording. "
            "Return matched_company as null if you are not reasonably confident."
        ),
        contents=f"Achievement: {raw_text}\n\nRoles:\n{options}",
        response_schema=TimelineMatchResult,
        temperature=0.0,
    )
    data = GeminiClient.parse_json(raw)
    matched = data.get("matched_company") or None
    if matched is None:
        return None

    # The model returns free-text, not a constrained choice from `options` --
    # validate it actually names one of the real timeline entries (same
    # normalization used everywhere else in this file) before trusting it,
    # so a hallucinated or reworded company name can't get treated as a
    # confident match. Return the entry's canonical spelling, not the
    # model's own wording, so callers always see a real timeline company.
    matched_key = _normalize_company_name(matched)
    for entry in timeline:
        if _normalize_company_name(entry.company) == matched_key:
            return entry.company
    return None


def match_to_timeline(
    achievement: RawAchievement, timeline: list[TimelineEntry], dry_run: bool = False,
) -> tuple[str, str]:
    """Returns (company, confidence). confidence is 'high'/'medium' for a
    real match, 'low' for the Misc./Unassigned fallback."""
    if achievement.company_hint:
        hint_key = _normalize_company_name(achievement.company_hint)
        for entry in timeline:
            if _normalize_company_name(entry.company) == hint_key:
                return entry.company, achievement.confidence

    if achievement.date_hint:
        year = _extract_year(achievement.date_hint)
        if year is not None:
            matches = [e for e in timeline if _year_in_range(year, e.start_date, e.end_date)]
            if len(matches) == 1:
                return matches[0].company, "medium"

    if achievement.title_hint:
        title_lower = achievement.title_hint.lower()
        matches = [e for e in timeline if e.title and title_lower in e.title.lower()]
        if len(matches) == 1:
            return matches[0].company, "medium"

    if dry_run:
        print(f"[DRY RUN] would ask the LLM to match: {achievement.raw_text[:60]!r}")
        return "Misc. / Unassigned", "low"

    if timeline:
        matched = _llm_match(achievement.raw_text, timeline)
        if matched:
            return matched, "medium"

    return "Misc. / Unassigned", "low"
