"""work_constraints.py -- deterministic detection of a posting's physical and
phone demands, judged against a profile's own `work_constraints:` block in
scan_filters.yml.

WHY THIS IS PYTHON, NOT A PROMPT INSTRUCTION

The recruiter evaluator was left to decide on its own which job duties were
"deal-breakers", and on 2026-09-14 it zeroed a profile's local retail and
clerical roles over ordinary duties ("operate multi-line phone systems"),
the job title itself, and over-qualification -- while the physical demands
that actually matter to that candidate were flagged inconsistently. Physical
requirements are formulaic text ("lift up to 50 pounds", "stand for extended
periods") that a regex reads the same way every time; the prompt now tells
the model to leave them to this module.

Measured against that profile's 1,628-posting corpus before thresholds were
chosen: lifting weights cluster at 10-35 lbs (65 postings, mostly office
boilerplate) and 50 lbs (38, mostly retail/warehouse). The naive standing
pattern hit "ability to sit and/or stand at a desk ... for extended periods"
-- a desk job -- which is why a sit/alternate cue in the same sentence voids
a standing match. "Call center" alone hit a company's recruiting-inbox name
("Global Call Center (GCC)"), so it needs an environment/role word after it.

Inert unless the profile opts in: detect() with empty settings returns [].
"""

from __future__ import annotations

import re

BLOCKER = "blocker"
PENALTY = "penalty"

_NEGATION_RE = re.compile(
    r"\b(no|not|never|without|zero|isn't|aren't|doesn't|don't|minimal)\b", re.I
)
_NEGATION_WINDOW = 40

# A sit/stand choice or an event-only context makes a standing phrase the
# opposite of what the constraint is about.
_STANDING_VOIDERS = re.compile(
    r"\bsit(?:s|ting)?\b|\balternat\w*|\bseated\b|\bspecial events?\b|\bduring events?\b",
    re.I,
)

_STANDING_RE = re.compile(
    r"\bstand(?:ing)?\b[^.\n;]{0,40}?\b(?:long|extended|prolonged|entire|full|majority)\b"
    r"[^.\n;]{0,15}?\b(?:periods?|shifts?|hours|day)\b"
    r"|\b(?:be|being|stay|remain|spend|spending)\b[^.\n;]{0,25}?\bon\s+(?:your|their|one's)\s+feet\b"
    r"|\bstand(?:ing)?\s+for\s+(?:up\s+to\s+)?\d+\s*\+?\s*(?:consecutive\s+)?hours\b"
    r"|\b(?:constant|continuous)\s+standing\b",
    re.I,
)

_LIFT_RE = re.compile(
    r"\b(?:lift|lifting|carry|carrying|move|moving|push|pull)\b[^.\n;]{0,60}?"
    r"\b(\d{2,3})\s*\+?\s*(?:lbs?\.?|pounds)\b",
    re.I,
)
_FREQUENT_RE = re.compile(
    r"\b(?:frequent(?:ly)?|regular(?:ly)?|routine(?:ly)?|repeated(?:ly)?|constant(?:ly)?|continuous(?:ly)?|daily)\b",
    re.I,
)
_OCCASIONAL_RE = re.compile(r"\b(?:occasional(?:ly)?|rarely|infrequent(?:ly)?)\b", re.I)

_MANUAL_LABOR_RE = re.compile(
    r"\bunload(?:ing)?\s+(?:the\s+)?(?:trucks?|freight|deliveries|shipments|containers)\b"
    r"|\btruck\s+unload\w*"
    r"|\bfreight\s+(?:processing|team)\b",
    re.I,
)

_PHONE_HEAVY_RE = re.compile(
    r"\bhigh[- ]volume\s+(?:of\s+)?(?:inbound\s+|outbound\s+)?(?:phone\s+|telephone\s+)?calls?\b"
    r"|\bhigh\s+call\s+volume\b"
    r"|\bcall\s+cent(?:er|re)\s+(?:environment|experience|setting|role|agent|representative)\b"
    r"|\bcold[- ]call(?:s|ing)?\b"
    r"|\boutbound\s+(?:sales\s+)?(?:phone\s+)?calls\b"
    r"|\b(?:majority|most)\s+of\s+(?:the|your)\s+(?:day|time|shift)\b[^.\n;]{0,30}?\bphone\b"
    r"|\b\d{2,3}\s*\+?\s*(?:outbound\s+|inbound\s+)?(?:phone\s+)?calls\s+(?:per|a|each)\s+(?:day|hour|shift)\b",
    re.I,
)

DEFAULTS = {
    "no_prolonged_standing": False,
    "no_manual_labor": False,
    # Lifting at or under max_lift_lbs is fine; frequent lifting above it,
    # or any lifting at/over heavy_lift_lbs, is a blocker; occasional
    # lifting between the two costs lift_penalty.
    "max_lift_lbs": None,
    "heavy_lift_lbs": 40,
    "lift_penalty": 0.30,
    "phone_heavy_penalty": 0.0,
    # Multiplies the stress-signal penalty (per category and cap) for an
    # onsite/hybrid posting: an in-person job has to be calm to be worth it.
    "onsite_stress_multiplier": 1.0,
}


def merged(settings: dict | None) -> dict:
    out = dict(DEFAULTS)
    out.update(
        {k: v for k, v in (settings or {}).items() if k in DEFAULTS and v is not None}
    )
    return out


def is_enabled(settings: dict | None) -> bool:
    s = merged(settings)
    return bool(
        s["no_prolonged_standing"]
        or s["no_manual_labor"]
        or s["max_lift_lbs"]
        or s["phone_heavy_penalty"]
        or s["onsite_stress_multiplier"] != 1.0
    )


_CLAUSE_ENDS = (".", "\n", ";")


def _sentence(text: str, match: re.Match) -> str:
    """The clause around a match. Semicolons count as boundaries: "Regular
    lifting of up to 30 pounds; occasional heavier lifting" is two facts,
    and reading them as one let "occasional" downgrade the regular one."""
    start = max(text.rfind(c, 0, match.start()) for c in _CLAUSE_ENDS) + 1
    ends = [i for i in (text.find(c, match.end()) for c in _CLAUSE_ENDS) if i != -1]
    end = min(ends) if ends else len(text)
    return " ".join(text[start:end].split())[:200]


def _negated(text: str, match: re.Match) -> bool:
    return bool(
        _NEGATION_RE.search(
            text[max(0, match.start() - _NEGATION_WINDOW) : match.start()]
        )
    )


def detect(text: str, settings: dict | None) -> list[dict]:
    """Findings as {"kind", "severity", "text", "penalty"}; [] when the
    profile has no constraints configured. One finding per kind -- the first
    qualifying match -- since what matters is whether the demand exists."""
    if not text or not is_enabled(settings):
        return []
    s = merged(settings)
    text = text.replace("\\n", "\n")
    findings: list[dict] = []

    if s["no_prolonged_standing"]:
        for m in _STANDING_RE.finditer(text):
            sentence = _sentence(text, m)
            if _negated(text, m) or _STANDING_VOIDERS.search(sentence):
                continue
            findings.append(
                {
                    "kind": "standing",
                    "severity": BLOCKER,
                    "text": sentence,
                    "penalty": 0.0,
                }
            )
            break

    if s["max_lift_lbs"]:
        worst = None
        for m in _LIFT_RE.finditer(text):
            lbs = int(m.group(1))
            if lbs <= s["max_lift_lbs"] or _negated(text, m):
                continue
            sentence = _sentence(text, m)
            if lbs >= s["heavy_lift_lbs"] or (
                _FREQUENT_RE.search(sentence) and not _OCCASIONAL_RE.search(sentence)
            ):
                worst = {
                    "kind": "lifting",
                    "severity": BLOCKER,
                    "text": sentence,
                    "penalty": 0.0,
                }
                break
            if worst is None:
                worst = {
                    "kind": "lifting",
                    "severity": PENALTY,
                    "text": sentence,
                    "penalty": float(s["lift_penalty"]),
                }
        if worst:
            findings.append(worst)

    if s["no_manual_labor"]:
        for m in _MANUAL_LABOR_RE.finditer(text):
            if _negated(text, m):
                continue
            findings.append(
                {
                    "kind": "manual_labor",
                    "severity": BLOCKER,
                    "text": _sentence(text, m),
                    "penalty": 0.0,
                }
            )
            break

    if s["phone_heavy_penalty"]:
        for m in _PHONE_HEAVY_RE.finditer(text):
            if _negated(text, m):
                continue
            findings.append(
                {
                    "kind": "phone_heavy",
                    "severity": PENALTY,
                    "text": _sentence(text, m),
                    "penalty": float(s["phone_heavy_penalty"]),
                }
            )
            break

    return findings


__all__ = ["BLOCKER", "PENALTY", "DEFAULTS", "detect", "is_enabled", "merged"]
