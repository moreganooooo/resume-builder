"""Deterministic safety checks for generated application answers."""

from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass(frozen=True)
class Violation:
    kind: str
    detail: str
    soft: bool = False


_NUMBER = re.compile(r"(?<![A-Za-z])(?:\$?\d[\d,.]*%?(?:[KMB])?)", re.IGNORECASE)
_VAGUE = re.compile(
    r"\b(significant(?:ly)?|substantial(?:ly)?|major|dramatic(?:ally)?|"
    r"considerable|meaningful)\b",
    re.IGNORECASE,
)


def _numbers(text: str) -> set[str]:
    return {re.sub(r"[,$]", "", m.group(0)).lower().rstrip("%") for m in _NUMBER.finditer(text or "")}


def _tool_names(ledger: dict | None) -> set[str]:
    names: set[str] = set()
    for item in (ledger or {}).get("tools", []):
        if isinstance(item, dict):
            name = item.get("name")
        else:
            name = item
        if name:
            names.add(str(name).strip().lower())
    return names


def check_answer(
    text: str,
    context,
    evidence,
    char_limit: int | None = None,
    question: str = "",
    verified_tools: dict | None = None,
) -> list[Violation]:
    """Return warnings without mutating or silently rewriting the answer."""
    allowed = " ".join(
        str(value or "")
        for value in (
            getattr(context, "jd_text", ""),
            getattr(context, "research_summary", ""),
            getattr(context, "compensation_context", ""),
            question,
            getattr(evidence, "text", evidence or ""),
        )
    )
    answer_numbers = _numbers(text)
    allowed_numbers = _numbers(allowed)
    violations = [
        Violation("foreign_number", f"Number {number!r} is not present in the job evidence.")
        for number in sorted(answer_numbers - allowed_numbers)
        if len(re.sub(r"\D", "", number)) >= 2
    ]

    tools = _tool_names(verified_tools)
    if tools:
        for match in re.finditer(r"\b[A-Z][A-Za-z0-9+#.-]{2,}\b", text or ""):
            name = match.group(0).lower()
            if name in {"I", "The", "This", "That", "With", "For", "And"}:
                continue
            if name not in tools and name in {"salesforce", "hubspot", "tableau", "sap", "jira", "asana"}:
                violations.append(Violation("unknown_tool", f"Tool {match.group(0)!r} is not verified."))
    company = (getattr(context, "company", "") or "").strip()
    if _VAGUE.search(text or ""):
        violations.append(Violation("vague_magnitude", "Use a concrete, checkable result where possible.", soft=True))
    if char_limit is not None and len(text or "") > char_limit:
        violations.append(Violation("too_long", f"Answer is {len(text)} characters; limit is {char_limit}."))
    return violations
