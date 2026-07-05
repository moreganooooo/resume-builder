"""
validate_coverletter.py — Deterministic Python checks for cover letter
output, run after every Gemini call in
ResumeEngine.build_tailored_coverletter().

Mirrors validate_resume.py's conventions (word-boundary forbidden-phrase
matching, a flat list of violation strings) but scoped to what actually
applies to a cover letter -- no bullet/skills/tagline checks exist here,
since a cover letter has none of those structures.
"""

import re


def _check_forbidden_phrases(cover_letter_data: dict, style_rules: dict) -> list[str]:
    violations = []
    phrases = [p.lower() for p in style_rules.get("forbidden_phrases", [])]
    haystacks = (
        [cover_letter_data.get("greeting", "")]
        + cover_letter_data.get("body_paragraphs", [])
        + [cover_letter_data.get("sign_off", "")]
    )
    for text in haystacks:
        lowered = text.lower()
        for phrase in phrases:
            if re.search(rf"\b{re.escape(phrase)}\b", lowered):
                violations.append(f"Forbidden phrase '{phrase}' found in: {text!r}")
    return violations


def _check_paragraph_count(cover_letter_data: dict) -> list[str]:
    count = len(cover_letter_data.get("body_paragraphs", []))
    if count < 2 or count > 3:
        return [f"Expected 2-3 body paragraphs, got {count}"]
    return []


# Blunt heuristic, not a perfect one: a first-person letter addressed
# generically to "Hiring Team" shouldn't ever need to reference a third
# party by name/pronoun, so this is a reasonable v1 check -- but it would
# false-positive on a legitimate sentence naming someone else (e.g. "I
# worked with the hiring manager and her team"). Not a concern for this
# pass since letters don't name third parties without company research.
_THIRD_PERSON_PATTERN = re.compile(r"\b(Morgan Escott|Morgan|she|her|hers)\b", re.IGNORECASE)


def _check_third_person_slip(cover_letter_data: dict) -> list[str]:
    violations = []
    haystacks = (
        [("greeting", cover_letter_data.get("greeting", ""))]
        + [(f"body_paragraphs[{i}]", p) for i, p in enumerate(cover_letter_data.get("body_paragraphs", []))]
        + [("sign_off", cover_letter_data.get("sign_off", ""))]
    )
    for field_name, text in haystacks:
        if _THIRD_PERSON_PATTERN.search(text):
            violations.append(f"Third-person self-reference found in {field_name}: {text!r}")
    return violations


def validate(cover_letter_data: dict, style_rules: dict) -> list[str]:
    violations = []
    violations.extend(_check_forbidden_phrases(cover_letter_data, style_rules))
    violations.extend(_check_paragraph_count(cover_letter_data))
    violations.extend(_check_third_person_slip(cover_letter_data))
    return violations
