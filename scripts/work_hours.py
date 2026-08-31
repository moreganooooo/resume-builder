"""work_hours.py -- read a posting's stated hours per week, then gate on a range.

WHY THIS EXISTS SEPARATELY FROM employment_type.py

"Part-time" is one label covering two jobs that have nothing to do with
each other. A 5-hour-a-week role and a 30-hour-a-week role are both
"part_time" to every provider schema, but one is a side commitment and
the other is most of a working life. The employment-type gate cannot tell
them apart, because the distinction is not in the field it reads.

WHAT THE CORPUS ACTUALLY SUPPORTS

Measured on this profile's 2,068-posting corpus on 2026-08-31:

    hours stated, all postings         48 / 2,068     2.3%
    hours stated, PART-TIME postings    9 /    35    25.7%

So this is not a filter for the whole list, and presenting it as one
would be dishonest. It is a REFINEMENT of part-time roles, where a
quarter of postings do state a number -- and the observed values land
exactly on the distinction worth drawing: 10-20, 19, 20, 20-25, 24, 24-30,
25, 30, 35-40, 40. Two clusters, and the gap between them is real.

THE FALSE-POSITIVE THAT DOMINATES THIS FIELD

"24 hours" and "48 hours" appear constantly in job postings, and almost
never mean a schedule -- "we respond within 24 hours", "48 hours notice",
"40 hours of PTO", "hours of operation". Matching a number next to the
word "hours" would read a response-time promise as a work week.

So a match REQUIRES an explicit weekly unit next to the figure ("per
week", "/week", "a week", "hours weekly"). That is what makes the number
a schedule rather than a duration. Postings that state hours some other
way are not detected, and are kept -- the same unknown-is-kept rule the
location and employment gates follow, for the same reason: a role that
fits and got dropped for not phrasing itself detectably is a worse
outcome than one that needs eyeballing.
"""

from __future__ import annotations

import re

# The weekly unit is mandatory, not optional. Without it "24 hours" is a
# response-time promise far more often than a schedule -- see the module
# docstring. `hrs`/`hr` are included because postings abbreviate.
_UNIT = r"(?:hours?|hrs?\.?|hr\.?)"
_PER_WEEK = r"(?:\s*(?:/|per|a|each)\s*(?:week|wk)\b|\s+weekly\b)"

# Ranges first: "10-20 hours per week" read by the single-figure pattern
# would report a flat 10, losing the top of the band. Both en dash and em
# dash appear in real postings ("20-25 hours per week" was live in this
# corpus with a true en dash).
_RANGE_RE = re.compile(
    r"\b(\d{1,2})\s*(?:-|--|–|—|to|and)\s*(\d{1,2})\s*" + _UNIT + _PER_WEEK,
    re.I,
)
_SINGLE_RE = re.compile(r"\b(\d{1,2})\s*" + _UNIT + _PER_WEEK, re.I)

# Also matches the inverted phrasing, which is common in part-time ads:
# "a minimum of 20 hours weekly" is caught above, but "20+ hours" and
# "up to 25 hours a week" carry a direction worth keeping.
_AT_LEAST_RE = re.compile(
    r"\b(?:at\s+least|minimum\s+of|min(?:imum)?\.?|more\s+than)\s+(\d{1,2})\s*"
    + _UNIT
    + _PER_WEEK,
    re.I,
)
_UP_TO_RE = re.compile(
    r"\b(?:up\s+to|no\s+more\s+than|max(?:imum)?\.?(?:\s+of)?)\s+(\d{1,2})\s*"
    + _UNIT
    + _PER_WEEK,
    re.I,
)

# A work week outside this band is not a schedule. 80-hour weeks are a
# figure of speech and 1-hour weeks are not jobs; both show up in prose
# ("80 hours of PTO per week" does not parse, but a typo could).
_MIN_PLAUSIBLE = 2
_MAX_PLAUSIBLE = 80


def _plausible(value: float) -> bool:
    return _MIN_PLAUSIBLE <= value <= _MAX_PLAUSIBLE


def parse_hours(text: str) -> dict | None:
    """Extract stated hours per week.

    Returns {"min", "max", "text"} or None when nothing weekly is stated.
    `min` and `max` are equal for a single figure. Direction-carrying
    phrasings leave the other bound as None: "up to 25 hours a week"
    states a ceiling and says nothing about the floor, and filling one in
    would invent a fact the posting did not state.
    """
    if not text:
        return None

    match = _RANGE_RE.search(text)
    if match:
        low, high = float(match.group(1)), float(match.group(2))
        if low > high:
            low, high = high, low
        if _plausible(low) and _plausible(high):
            return {"min": low, "max": high, "text": _clean(match.group(0))}

    match = _AT_LEAST_RE.search(text)
    if match:
        low = float(match.group(1))
        if _plausible(low):
            return {"min": low, "max": None, "text": _clean(match.group(0))}

    match = _UP_TO_RE.search(text)
    if match:
        high = float(match.group(1))
        if _plausible(high):
            return {"min": None, "max": high, "text": _clean(match.group(0))}

    match = _SINGLE_RE.search(text)
    if match:
        value = float(match.group(1))
        if _plausible(value):
            return {"min": value, "max": value, "text": _clean(match.group(0))}

    return None


def _clean(raw: str) -> str:
    return " ".join(raw.split())


def evaluate_hours(text: str, config: dict) -> tuple[bool, str]:
    """Returns (passes, reason). Inert unless a bound is configured.

    The comparison is OVERLAP, not containment: a posting offering 10-30
    hours satisfies someone wanting 20-40, because 20-30 is available to
    both. Requiring the posting's whole band to sit inside the user's
    would reject every flexible role, which is most of the part-time
    postings that state a range at all.
    """
    config = config or {}
    want_min = config.get("min_hours_per_week")
    want_max = config.get("max_hours_per_week")
    if not isinstance(want_min, (int, float)):
        want_min = None
    if not isinstance(want_max, (int, float)):
        want_max = None
    if want_min is None and want_max is None:
        return True, ""

    parsed = parse_hours(text)
    if not parsed:
        return True, "hours not stated; kept for review"

    low = parsed["min"]
    high = parsed["max"]
    # An open-ended bound cannot conflict on that side. "At least 20
    # hours" has no ceiling to compare against a ceiling.
    if want_max is not None and low is not None and low > want_max:
        return False, (
            f"stated {parsed['text']} starts above your {want_max:g}-hour ceiling"
        )
    if want_min is not None and high is not None and high < want_min:
        return False, (
            f"stated {parsed['text']} tops out below your {want_min:g}-hour floor"
        )
    return True, f"stated {parsed['text']} overlaps your range"


def describe_range(config: dict) -> str:
    """One phrase for the settings header. '' when unset."""
    config = config or {}
    low = config.get("min_hours_per_week")
    high = config.get("max_hours_per_week")
    if isinstance(low, (int, float)) and isinstance(high, (int, float)):
        return f"{low:g}-{high:g} hrs/week"
    if isinstance(low, (int, float)):
        return f"{low:g}+ hrs/week"
    if isinstance(high, (int, float)):
        return f"up to {high:g} hrs/week"
    return ""


__all__ = [
    "describe_range",
    "evaluate_hours",
    "parse_hours",
]
