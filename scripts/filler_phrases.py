"""filler_phrases.py -- sentences that could sit in anyone's cover letter or
"Why [Company]?" section. Shared by validate_coverletter and validate_resume
so the two checks cannot drift apart.

Every pattern here came from real generated output (2026-09-14): "I thrive in
these high-stakes environments", "This technical depth drives my work",
"Let's build something impactful together", "These technical achievements
underscore my commitment to...", "...remains a core priority in my work",
"...is the core of my professional mission". Each spends a line saying nothing
a reader can check.
"""

from __future__ import annotations

import re

PATTERNS = [
    re.compile(p, re.IGNORECASE)
    for p in (
        r"\bthrive\s+in\b",
        r"\bhigh[- ]stakes\s+environments?\b",
        r"\blet'?s\s+build\b",
        r"\bsomething\s+(?:impactful|special|great|amazing)\b",
        r"\bdrives\s+my\s+work\b",
        r"\bpassionate\s+about\b",
        r"\bhit\s+the\s+ground\s+running\b",
        r"\bperfect\s+fit\b",
        r"\bmake\s+a\s+(?:meaningful|real|lasting)\s+(?:impact|difference)\b",
        r"\bdynamic\s+(?:team|environment)\b",
        r"\bfast[- ]paced\s+environment\b",
        r"\bteam\s+player\b",
        r"\bcore\s+of\s+my\s+professional\s+mission\b",
        r"\bexcited\s+(?:about|by)\s+the\s+(?:opportunity|prospect)\b",
        r"\bunderscores?\s+my\s+commitment\b",
        r"\b(?:remains?|is)\s+a\s+core\s+priority\b",
        r"\bdemonstrat\w*\s+my\s+(?:ability|commitment|dedication|passion)\b",
        r"\ba\s+testament\s+to\b",
        r"\bcommitment\s+to\s+excellence\b",
    )
]

_SENTENCE_SPLIT = re.compile(r"(?<=[.!?])\s+")
_TAGS = re.compile(r"<[^>]+>")


def filler_sentences(text: str) -> list[str]:
    """Sentences of text (HTML tags stripped) that match a filler pattern."""
    plain = _TAGS.sub(" ", text or "")
    return [
        " ".join(s.split())
        for s in _SENTENCE_SPLIT.split(plain)
        if s.strip() and any(p.search(s) for p in PATTERNS)
    ]


__all__ = ["PATTERNS", "filler_sentences"]
