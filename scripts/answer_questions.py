"""Classification and deterministic handling for application questions."""

from __future__ import annotations

import re
from enum import Enum


class QuestionKind(str, Enum):
    EEO = "eeo"
    LEGAL = "legal"
    SALARY = "salary"
    WHY_COMPANY = "why_company"
    WHY_ROLE = "why_role"
    BEHAVIORAL = "behavioral"
    EXPERIENCE_WITH_TOOL = "experience_with_tool"
    GENERAL = "general"


_RULES: tuple[tuple[QuestionKind, tuple[str, ...]], ...] = (
    (
        QuestionKind.EEO,
        (
            r"\b(identify|identifies|identification)\b.*\b(gender|race|ethnic|veteran|disab)",
            r"\b(gender|race|ethnic|veteran|disab)\w*\b.*\b(identify|prefer|status)\b",
            r"\b(are you|do you have|what is your)\b.*\b(veteran|disab|gender|race|ethnic)\b",
        ),
    ),
    (
        QuestionKind.LEGAL,
        (
            r"\b(legally authorized|authorized to work|right to work|work authorization)\b",
            r"\b(require|need|now or in the future).*\b(sponsor|visa)\b",
            r"\b(sponsorship|immigration status|eligible to work)\b",
        ),
    ),
    (
        QuestionKind.SALARY,
        (
            r"\b(salary|compensation|pay|wage|remuneration|rate)\b.*\b(expect|desired|require|range|target)\b",
            r"\b(expect|desired|require|target)\b.*\b(salary|compensation|pay|wage|rate)\b",
            r"\b(salary|compensation|pay)\s+expectations?\b",
            r"\bhow much\b.*\b(earn|make|expect)\b",
        ),
    ),
    (
        QuestionKind.WHY_COMPANY,
        (
            r"\bwhy\b.*\b(work|join|interested).*\b(at|with|for)\b",
            r"\bwhy\s+(this|our)\s+company\b",
            r"\bwhat attracts you\b.*\b(company|organization|us)\b",
        ),
    ),
    (
        QuestionKind.WHY_ROLE,
        (
            r"\bwhy\b.*\b(role|position|job|opportunity)\b",
            r"\bwhy are you interested\b",
            r"\bwhat interests you\b.*\b(role|position|job)\b",
        ),
    ),
    (
        QuestionKind.BEHAVIORAL,
        (
            r"\b(tell|describe|give|share)\b.*\b(time|example|situation|experience)\b",
            r"\bhow did you\b.*\b(handle|deal|respond|resolve)\b",
            r"\bwhat would you do\b.*\b(conflict|disagree|challenge)\b",
        ),
    ),
    (
        QuestionKind.EXPERIENCE_WITH_TOOL,
        (
            r"\bhow many years\b.*\b(with|using|of experience)\b",
            r"\b(experience|proficiency|熟練)\b.*\b(using|with)\b",
            r"\bhave you used\b",
        ),
    ),
)


def classify_question(text: str) -> QuestionKind:
    """Classify a question, prioritizing sensitive categories."""
    normalized = " ".join((text or "").split()).lower()
    for kind, patterns in _RULES:
        if any(re.search(pattern, normalized, re.IGNORECASE) for pattern in patterns):
            return kind
    return QuestionKind.GENERAL


def sensitive_response(kind: QuestionKind, profile_yaml: dict) -> str | None:
    """Return a deterministic response for sensitive questions."""
    if kind == QuestionKind.EEO:
        return (
            "I do not provide an automated response to voluntary "
            "self-identification questions. Please answer this question yourself."
        )
    if kind != QuestionKind.LEGAL:
        return None
    settings = (profile_yaml or {}).get("application_answers") or {}
    if settings.get("work_authorization") is not None:
        value = settings["work_authorization"]
        return str(value)
    if settings.get("requires_sponsorship") is not None:
        value = settings["requires_sponsorship"]
        return str(value)
    return "Please answer this work-authorization question yourself."
