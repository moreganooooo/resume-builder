"""stress_signals.py -- deterministic detection of intrinsic role-stress
language in a posting's body text.

WHY THIS IS DETECTION ONLY, NOT A SCORE OR A GATE

Every other body-text detector in this codebase (work_hours.py,
compensation.py, the unpaid-work keyword scan referenced in CLAUDE.md)
started plausible and turned out wrong on first measurement: "24 hours"
read as a work week instead of a response-time SLA, a $50 stipend read
as salary, "volunteer" hit the company's own volunteering PROGRAM rather
than unpaid work. There is no reason to expect stress phrases behave any
better, and "fast-paced environment" in particular is suspected culture
boilerplate that may fire on a large fraction of postings regardless of
actual pace -- see docs/superpowers/specs/2026-09-01-stress-challenge-scoring-design.md.

So this module only DETECTS and reports which phrases matched -- it does
not decide pass/fail and does not compute a 1-5 score. It ships as a
corpus-measurement tool (`scripts/measure_stress_signals.py`) first. A
score or gate is a later, separate step, and only for whichever
categories measurement shows are both common enough and precise enough
to be worth surfacing -- the same order work_hours.py and compensation.py
were built in.

NEGATION

A posting that says "no on-call rotation" or "no weekend work required"
is stating the ABSENCE of a stressor, which is the opposite fact from a
plain match. Each category with a plausible negated form checks a
window around the match for a negation cue before counting it as a hit.
"""

from __future__ import annotations

import re

_NEGATION_WINDOW = 40

_NEGATION_RE = re.compile(
    r"\b(no|not|none|never|without|zero|isn't|aren't|don't|doesn't|"
    r"free\s+of|eliminat\w*)\b",
    re.I,
)


class StressSignal:
    __slots__ = ("category", "label", "text")

    def __init__(self, category: str, label: str, text: str):
        self.category = category
        self.label = label
        self.text = text

    def __repr__(self) -> str:
        return f"StressSignal({self.category!r}, {self.text!r})"

    def __eq__(self, other) -> bool:
        return (
            isinstance(other, StressSignal)
            and self.category == other.category
            and self.text == other.text
        )


# Each entry: (category, label, pattern, negatable).
# `negatable=True` means a nearby negation cue voids the match --
# reserved for phrases with a common, meaningful negated form ("no
# on-call rotation"). Phrases without a natural negated form (a posting
# essentially never says "not fast-paced") skip the check, since it
# would just mask real matches on stray nearby negatives.
_CATEGORIES = (
    (
        "high_call_volume",
        "High call volume",
        re.compile(
            r"\bhigh[- ]volume\s+(?:of\s+)?calls?\b"
            r"|\bhigh\s+call\s+volume\b"
            r"|\bhigh-volume\s+(?:call\s+)?queue\b",
            re.I,
        ),
        True,
    ),
    (
        "fast_paced",
        "Fast-paced environment",
        re.compile(r"\bfast[- ]paced\s+environment\b", re.I),
        False,
    ),
    (
        "aggressive_targets",
        "Aggressive targets/quotas",
        re.compile(
            r"\baggressive\s+(?:targets?|quotas?|goals?)\b"
            r"|\bmeet\s+(?:or\s+exceed\s+)?quotas?\b"
            r"|\bstrict(?:ly)?\s+enforced\s+kpis?\b",
            re.I,
        ),
        True,
    ),
    (
        "on_call",
        "On-call / after-hours availability",
        re.compile(
            r"\bon-call\s+rotation\b"
            r"|\b24/7\s+(?:availability|coverage|support)\b"
            r"|\bafter-hours\s+(?:support|coverage|availability)\b"
            r"|\bweekend\s+coverage\b",
            re.I,
        ),
        True,
    ),
    (
        "fire_fighting",
        "Fire-fighting / understaffed pace",
        re.compile(
            r"\bfire[- ]fighting\b"
            r"|\bwears?\s+many\s+hats\b"
            r"|\bfast-changing\s+priorities\b"
            r"|\bthrives?\s+in\s+ambiguity\b",
            re.I,
        ),
        False,
    ),
)


def _is_negated(text: str, match: re.Match) -> bool:
    start = max(0, match.start() - _NEGATION_WINDOW)
    context = text[start : match.start()]
    return bool(_NEGATION_RE.search(context))


def detect(text: str) -> list[StressSignal]:
    """Returns every matched stress signal, in document order.

    Duplicate (category, matched text) pairs within one posting are
    collapsed -- a posting saying "quota" three times is one signal, not
    three, when what's being reported is which stressors are present.
    """
    if not text:
        return []
    found: list[StressSignal] = []
    seen: set[tuple[str, str]] = set()
    for category, label, pattern, negatable in _CATEGORIES:
        for match in pattern.finditer(text):
            if negatable and _is_negated(text, match):
                continue
            matched_text = " ".join(match.group(0).split())
            key = (category, matched_text.lower())
            if key in seen:
                continue
            seen.add(key)
            found.append(StressSignal(category, label, matched_text))
    return found


def categories(text: str) -> list[str]:
    """Deduped category labels present, in category-declaration order --
    the display-friendly summary ("High call volume", "Aggressive
    targets/quotas") rather than every individual phrase match."""
    hits = detect(text)
    present = {s.category for s in hits}
    return [label for category, label, _, _ in _CATEGORIES if category in present]


__all__ = ["StressSignal", "categories", "detect"]
