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
# A number directly preceded by "<letter>-" or "<letter>–" (e.g. the "12"
# in "K-12" or "K–12") is part of a compound label, not a metric.
_COMPOUND_LABEL_PREFIX = re.compile(r"[A-Za-z][-–—]$")
# The word (if any) immediately adjacent to a number, e.g. "member" in
# "12-member" or "Performer" in "Top 10 Performer" -- used so two bullets
# that happen to share a bare number in unrelated contexts ("K-12" aside,
# also plain coincidences like a "10-person team" vs "Top 10 Performer")
# aren't treated as the same metric repeated.
_METRIC_CONTEXT_WORD = re.compile(r"^[-–—]?\s?(\w+)")


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


def get_opening_verbs(resume_data: dict) -> list[str]:
    """
    Every bullet's opening verb (lowercased, numeral-led bullets excluded),
    in bullet order. Exposed for retry-prompt construction: a fix asked to
    resolve one duplicate-verb pair, without seeing every verb already in
    use elsewhere in the CV, can pick a replacement that collides with some
    other, unflagged bullet -- whack-a-mole across retry attempts.
    """
    verbs = []
    for bullet in _all_bullets(resume_data):
        match = _FIRST_WORD_PATTERN.match(bullet)
        if not match:
            continue
        first_word = match.group(1).lower()
        if first_word[0].isdigit():
            continue
        verbs.append(first_word)
    return verbs


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
    """
    Wrapping a skills line onto a 2nd line is normal, unremarkable text
    wrapping -- not a defect on its own. Only flag it when the overflow
    would leave a short "widow" (a sliver of content stranded on its own
    line) or when it's long enough to spill onto a 3rd line.
    """
    violations = []
    skills_section = style_rules.get("skills_section", {})
    max_chars = skills_section.get("line_max_chars", 110)
    widow_min_chars = skills_section.get("widow_min_chars", 25)
    for line in resume_data.get("SKILLS", []):
        plain = re.sub(r"\*\*(.+?)\*\*", r"\1", line)
        length = len(plain)
        if length <= max_chars:
            continue
        remainder = length - max_chars
        if remainder < widow_min_chars:
            violations.append(
                f"Skills line wraps to a 2nd line but leaves a short widow "
                f"({remainder} chars past the {max_chars}-char limit) -- add or remove a skill so "
                f"the line either fits on one line or wraps to a fuller 2nd line ({length} chars total): {line!r}"
            )
        elif length > 2 * max_chars:
            violations.append(
                f"Skills line is long enough to wrap to a 3rd line ({length} chars, more than "
                f"double the {max_chars}-char limit) -- remove a skill or two: {line!r}"
            )
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


def _extract_metric_signatures(text: str) -> list[tuple[str, str]]:
    """
    Returns (display_number, signature) pairs, one per genuine metric
    occurrence. The signature combines the number with its immediately
    adjacent context word (if any), so "12-member" and a bare "12" followed
    by unrelated text aren't treated as the same metric repeated -- only
    the raw digits, with no way to tell whether two mentions describe the
    same fact or two different ones, was flagging things like "K-12" (a
    market segment) against an unrelated "12-member team" as a duplicate.
    Numbers embedded in compound labels like "K-12"/"K–12" are excluded
    entirely -- they aren't metrics at all.
    """
    results = []
    for match in _METRIC_PATTERN.finditer(text):
        start = match.start()
        if _COMPOUND_LABEL_PREFIX.search(text[max(0, start - 2):start]):
            continue
        number = match.group(0)
        context_match = _METRIC_CONTEXT_WORD.match(text[match.end():match.end() + 20])
        context = context_match.group(1).lower() if context_match else ""
        results.append((number, f"{number.lower()}|{context}"))
    return results


def _check_metric_uniqueness(resume_data: dict) -> list[str]:
    violations = []
    summary = _strip_html(resume_data.get("SUMMARY_TEXT", ""))
    bullets = _all_bullets(resume_data)
    summary_signatures = {sig for _, sig in _extract_metric_signatures(summary)}
    seen_in_bullets: dict = {}
    for bullet in bullets:
        for number, signature in _extract_metric_signatures(bullet):
            if signature in summary_signatures:
                violations.append(f"Metric '{number}' should appear only once across the resume, but appears in both the Summary and a bullet: {bullet!r}")
            elif signature in seen_in_bullets:
                violations.append(
                    f"Metric '{number}' appears more than once, in both "
                    f"{seen_in_bullets[signature]!r} and {bullet!r}"
                )
            else:
                seen_in_bullets[signature] = bullet
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
