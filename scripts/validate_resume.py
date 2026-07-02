"""
validate_resume.py — Deterministic checks for the parts of ResumeDesignSystem.md
that require generated text (Summary, Skills, Bullets, Why) rather than fixed
content. Pure function: takes a normalized resume_data dict and an already-
loaded style_rules dict, returns a list of violation strings. No filesystem
access, no LLM calls -- everything here is mechanically checkable.
"""

import re

_METRIC_PATTERN = re.compile(r"\$?\d[\d,.]*[%MK]?\b", re.IGNORECASE)
_PRONOUN_PATTERN = re.compile(r"\b(i|me|my|we|our)\b", re.IGNORECASE)
_FIRST_WORD_PATTERN = re.compile(r"[^\w]*(\w+)")


def _strip_html(text: str) -> str:
    return re.sub(r"<[^>]+>", "", text or "")


def _all_bullets(resume_data: dict) -> list[str]:
    bullets = []
    for job in resume_data.get("EXPERIENCE", []):
        bullets.extend(job.get("achievements", []))
    return bullets


def _check_forbidden_phrases(resume_data: dict, style_rules: dict) -> list[str]:
    violations = []
    phrases = [p.lower() for p in style_rules.get("forbidden_phrases", [])]
    haystacks = (
        [_strip_html(resume_data.get("SUMMARY_TEXT", ""))]
        + resume_data.get("SKILLS", [])
        + [_strip_html(resume_data.get("WHY_TEXT", ""))]
        + _all_bullets(resume_data)
    )
    for text in haystacks:
        lowered = text.lower()
        for phrase in phrases:
            if phrase in lowered:
                violations.append(f"Forbidden phrase '{phrase}' found in: {text!r}")
    return violations


def _check_forbidden_openers(resume_data: dict, style_rules: dict) -> list[str]:
    violations = []
    openers = [o.lower() for o in style_rules.get("forbidden_openers", [])]
    for bullet in _all_bullets(resume_data):
        lowered = bullet.lower()
        for opener in openers:
            if lowered.startswith(opener):
                violations.append(f"Bullet uses forbidden opener '{opener}': {bullet!r}")
    return violations


def _check_unique_opening_verbs(resume_data: dict) -> list[str]:
    violations = []
    seen = {}
    for bullet in _all_bullets(resume_data):
        match = _FIRST_WORD_PATTERN.match(bullet)
        if not match:
            continue
        first_word = match.group(1).lower()
        if first_word[0].isdigit():
            continue
        if first_word in seen:
            violations.append(
                f"Opening verb '{first_word}' is not unique across the CV "
                f"(used in both {seen[first_word]!r} and {bullet!r})"
            )
        else:
            seen[first_word] = bullet
    return violations


def _check_bullet_lengths(resume_data: dict, style_rules: dict) -> list[str]:
    violations = []
    limits = style_rules.get("bullet_structure", {})
    two_liner_max = limits.get("two_liner_max_chars", 220)
    for bullet in _all_bullets(resume_data):
        if len(bullet) > two_liner_max:
            violations.append(f"Bullet exceeds {two_liner_max}-char two-liner max ({len(bullet)} chars): {bullet!r}")
    return violations


def _check_skills_line_lengths(resume_data: dict, style_rules: dict) -> list[str]:
    violations = []
    max_chars = style_rules.get("skills_section", {}).get("line_max_chars", 110)
    for line in resume_data.get("SKILLS", []):
        plain = re.sub(r"\*\*(.+?)\*\*", r"\1", line)
        if len(plain) > max_chars:
            violations.append(f"Skills line exceeds {max_chars}-char max ({len(plain)} chars): {line!r}")
    return violations


def _check_pronouns_outside_why(resume_data: dict) -> list[str]:
    violations = []
    checked_fields = {
        "SUMMARY_TEXT": _strip_html(resume_data.get("SUMMARY_TEXT", "")),
    }
    checked_fields.update({f"SKILLS[{i}]": s for i, s in enumerate(resume_data.get("SKILLS", []))})
    checked_fields.update({f"BULLET[{i}]": b for i, b in enumerate(_all_bullets(resume_data))})
    for field_name, text in checked_fields.items():
        if _PRONOUN_PATTERN.search(text):
            violations.append(f"Pronoun found outside the Why section, in {field_name}: {text!r}")
    return violations


def _check_metric_uniqueness(resume_data: dict) -> list[str]:
    violations = []
    summary = _strip_html(resume_data.get("SUMMARY_TEXT", ""))
    bullets = _all_bullets(resume_data)
    summary_metrics = set(m.lower() for m in _METRIC_PATTERN.findall(summary))
    seen_in_bullets: dict = {}
    for bullet in bullets:
        for metric in _METRIC_PATTERN.findall(bullet):
            key = metric.lower()
            if key in summary_metrics:
                violations.append(f"Metric '{metric}' should appear only once across the resume, but appears in both the Summary and a bullet: {bullet!r}")
            elif key in seen_in_bullets:
                violations.append(
                    f"Metric '{metric}' appears more than once, in both "
                    f"{seen_in_bullets[key]!r} and {bullet!r}"
                )
            else:
                seen_in_bullets[key] = bullet
    return violations


def _check_experience_completeness(resume_data: dict) -> list[str]:
    violations = []
    for i, job in enumerate(resume_data.get("EXPERIENCE", [])):
        missing = [f for f in ("title", "company", "period") if not job.get(f)]
        if missing:
            violations.append(f"Experience entry {i} is missing required field(s) {missing}: {job!r}")
        if not job.get("achievements"):
            violations.append(f"Experience entry {i} ({job.get('company', 'unknown company')!r}) has no achievement bullets")
    return violations


def validate(resume_data: dict, style_rules: dict) -> list[str]:
    violations: list[str] = []
    violations.extend(_check_forbidden_phrases(resume_data, style_rules))
    violations.extend(_check_forbidden_openers(resume_data, style_rules))
    violations.extend(_check_unique_opening_verbs(resume_data))
    violations.extend(_check_bullet_lengths(resume_data, style_rules))
    violations.extend(_check_skills_line_lengths(resume_data, style_rules))
    violations.extend(_check_pronouns_outside_why(resume_data))
    violations.extend(_check_metric_uniqueness(resume_data))
    violations.extend(_check_experience_completeness(resume_data))
    return violations
