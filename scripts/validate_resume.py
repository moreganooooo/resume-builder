"""
validate_resume.py — Deterministic checks for the parts of ResumeDesignSystem.md
that require generated text (Summary, Skills, Bullets, Why) rather than fixed
content. Pure function: takes a normalized resume_data dict and an already-
loaded style_rules dict, returns a list of violation strings. No filesystem
access, no LLM calls -- everything here is mechanically checkable.
"""

import re

_METRIC_PATTERN = re.compile(r"\$?\d[\d,.]*[%MK]?\b", re.IGNORECASE)
_PRONOUN_PATTERN = re.compile(r"\b(i|me|my|we|our|she|her|hers|he|him|his)\b", re.IGNORECASE)
_FIRST_WORD_PATTERN = re.compile(r"[^\w]*(\w+)")
_TITLE_CASE_MINOR_WORDS = {
    "a", "an", "and", "as", "at", "but", "by", "for", "in", "nor", "of",
    "on", "or", "so", "the", "to", "up", "vs", "via", "with",
}
# A number directly preceded by "<letter>-" or "<letter>–" (e.g. the "12"
# in "K-12" or "K–12") is part of a compound label, not a metric.
_COMPOUND_LABEL_PREFIX = re.compile(r"[A-Za-z][-–—]$")
# The word (if any) immediately adjacent to a number, e.g. "member" in
# "12-member" or "Performer" in "Top 10 Performer" -- used so two bullets
# that happen to share a bare number in unrelated contexts ("K-12" aside,
# also plain coincidences like a "10-person team" vs "Top 10 Performer")
# aren't treated as the same metric repeated.
_METRIC_CONTEXT_WORD = re.compile(r"^[-–—]?\s?(\w+)")
# tailor_resume.md wraps the Summary's first sentence (identity + years of
# experience) in <strong> tags -- used to isolate "the remaining sentences"
# so the specificity check below doesn't credit the years-of-experience
# figure itself as the proof point it's checking for.
_STRONG_TAG_PATTERN = re.compile(r"<strong>.*?</strong>", re.IGNORECASE | re.DOTALL)


def _strip_html(text: str) -> str:
    return re.sub(r"<[^>]+>", "", text or "")


def _all_bullets(resume_data: dict) -> list[str]:
    bullets = []
    for job in resume_data.get("EXPERIENCE", []):
        bullets.extend(job.get("achievements", []))
    for entry in resume_data.get("EDUCATION", []):
        bullets.extend(entry.get("bullets", []))
    return bullets


def check_summary_specificity(resume_data: dict) -> list[str]:
    """
    tailor_resume.md requires the Summary's sentences after the opening
    years-of-experience line to include "at least one concrete, checkable
    specific -- a real metric, a named tool/platform, or a named scope."
    Nothing enforced that: a real shipped resume had zero metrics in
    sentences 2-5, four consecutive sentences of the shape "[Verb]s
    [abstract noun phrase] to [abstract outcome]" (B29, phase-9-backlog.md).

    Only the metric half of the rule is mechanically checkable here --
    detecting a "named tool/platform" would need a verified-tools list,
    which this module deliberately doesn't load (see module docstring:
    pure function, no filesystem access).

    Deliberately NOT part of validate()'s blocking checks, and not gated
    on -- same reasoning as check_keyword_coverage() below. A first attempt
    at making this blocking caused a real `resume sample` build to fail
    outright: the retry loop's fix_contents only ever contains resume_data
    + the already-selected bullets (no fresh KB material, by cost-saving
    design -- see orchestrator.py), and those bullets' metrics are already
    claimed by metrics_rules' "appears at most ONCE across the entire CV"
    rule, so the model oscillated between "no metric" and "duplicate
    metric" for all 4 attempts with no way out. Reported for a human to
    see (or for `resume polish`), not auto-corrected.

    Only fires when a remainder actually exists: a bare one-sentence
    Summary is a different, narrower problem (no "narrative bridge / exit
    story" at all) than the one this rule targets -- a *populated*
    remainder that never earns its place with a real proof point, which is
    what the real shipped resume that prompted this check actually had.
    """
    raw = resume_data.get("SUMMARY_TEXT", "") or ""
    if not raw:
        return []
    remainder = _strip_html(_STRONG_TAG_PATTERN.sub("", raw, count=1))
    if remainder.strip() and not _METRIC_PATTERN.search(remainder):
        return [
            "Summary has no concrete metric beyond the opening years-of-experience figure -- "
            f"consider adding a real proof point (metric, named tool/platform, or named scope) "
            f"to the remaining sentences: {_strip_html(raw)!r}"
        ]
    return []


def _check_forbidden_phrases(resume_data: dict, style_rules: dict) -> list[str]:
    """
    Word-boundary matching, not plain substring: a bare-substring check made
    "leverage" flag "leveraged"/"leveraging" too, even though those inflected
    forms are handled separately (and more leniently) by style_rules.yaml's
    own vague_verbs guidance. The list already lists inflected forms it
    actually wants caught as their own explicit entries (synergized, synergy,
    synergies), so exact-word matching is the intended behavior, not a
    loosening of it.
    """
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
            if re.search(rf"\b{re.escape(phrase)}\b", lowered):
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


def _check_tagline_length(resume_data: dict, style_rules: dict) -> list[str]:
    """
    tailor_resume.md used to say "target 70-80 characters" for the tagline
    fitting one printed line at 14pt -- but a real 65-char tagline
    ("CAMPAIGN CRM STRATEGIST | CAMPAIGN STRATEGY & LIFECYCLE MARKETING")
    wrapped to 2 lines anyway. Empirically measured (Playwright, actual
    DM Sans 14pt rendering at the real 7.5in content width): realistic
    uppercase taglines run ~0.117-0.119in/char, so even 65 chars can exceed
    the available width. This uses a conservative 60-char cap with margin
    for that per-character variance -- 56 as of the 2026-08-06 tagline
    font bump (14pt -> 15pt); see style_rules.yaml's tagline.max_chars.
    """
    max_chars = style_rules.get("tagline", {}).get("max_chars", 56)
    tagline = resume_data.get("TAGLINE", "")
    if len(tagline) > max_chars:
        return [f"Tagline exceeds {max_chars}-char max ({len(tagline)} chars) and will wrap to a 2nd line: {tagline!r}"]
    return []


def _check_bullet_lengths(resume_data: dict, style_rules: dict) -> list[str]:
    violations = []
    limits = style_rules.get("bullet_structure", {})
    two_liner_max = limits.get("two_liner_max_chars", 220)
    for bullet in _all_bullets(resume_data):
        if len(bullet) > two_liner_max:
            violations.append(f"Bullet exceeds {two_liner_max}-char two-liner max ({len(bullet)} chars): {bullet!r}")
    return violations


def bullets_with_short_widow(bullets: list[str], style_rules: dict) -> list[tuple[str, int]]:
    """Returns (bullet, widow_word_count) for every bullet that clears
    one_liner_max_chars but not two_liner_max_chars, and whose implied 2nd
    line -- the text past one_liner_max_chars -- has fewer than
    widow_min_words words (style_rules.yaml's bullet_structure).

    Same char-count-as-proxy-for-wrap-point approach as
    _check_skills_line_lengths: no live render is available at validation
    time, so the text past one_liner_max_chars stands in for "what spills
    to line 2." Shared by _check_bullet_widows() below (feeds the
    pre-render fix loop, independent of final page count) and
    orchestrator.py's _short_widow_bullets() (feeds the page-overflow trim
    step) so the two never drift onto different thresholds.
    """
    limits = style_rules.get("bullet_structure", {})
    one_liner_max = limits.get("one_liner_max_chars", 108)
    two_liner_max = limits.get("two_liner_max_chars", 220)
    widow_min_words = limits.get("widow_min_words", 5)

    results = []
    for bullet in bullets:
        length = len(bullet)
        if length <= one_liner_max or length > two_liner_max:
            continue
        remainder = bullet[one_liner_max:].strip()
        word_count = len(remainder.split())
        if word_count < widow_min_words:
            results.append((bullet, word_count))
    return results


def _check_bullet_widows(resume_data: dict, style_rules: dict) -> list[str]:
    """
    style_rules.yaml's bullet_structure has declared a widow_rule ("Never
    wrap to a second line with fewer than 5 words") and widow_min_words: 5
    since it was written, but nothing ever checked it -- _check_bullet_lengths
    above only catches a bullet that blows through the 220-char two-liner
    ceiling entirely, never one that just clears the 120-char one-liner
    ceiling and strands a 2-3 word scrap on its own second line. That short
    second line is exactly the shape of a live complaint: several bullets
    render with an odd, stub-like final line -- on a resume that already
    fits in 2 pages, so orchestrator.py's page-overflow trim step (which
    already knew how to fix this) never even ran.

    EXPERIENCE achievements only, deliberately not _all_bullets() (which
    also pulls in EDUCATION): Education bullets are fixed Python content
    from fixed_content.py, assembled directly with no LLM in the loop, so
    a widow violation there has no fix the retry loop could ever apply --
    it would just burn all 4 attempts and fail the build. Matches
    orchestrator.py's _short_widow_bullets(), which is EXPERIENCE-only for
    the same reason.
    """
    widow_min_words = style_rules.get("bullet_structure", {}).get("widow_min_words", 5)
    bullets = [
        bullet
        for job in resume_data.get("EXPERIENCE", [])
        for bullet in job.get("achievements", [])
    ]
    return [
        f"Bullet wraps to a 2nd line but leaves only a {word_count}-word widow "
        f"(fewer than the required {widow_min_words}) -- tighten it to fit one line, "
        f"or lengthen it so the 2nd line isn't a stray scrap: {bullet!r}"
        for bullet, word_count in bullets_with_short_widow(bullets, style_rules)
    ]


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


def _title_case_violations_in_phrase(phrase: str) -> list[str]:
    """
    Flags words (or hyphenated sub-parts, e.g. the "assisted" in "AI-assisted")
    that aren't capitalized, skipping the standard lowercase minor words
    (and, of, with, etc.) except when they open the phrase.
    """
    violations = []
    words = phrase.strip().split()
    for word_index, word in enumerate(words):
        if word == "&":
            continue
        for part in word.split("-"):
            core = part.strip("(),./")
            if not core or not core[0].isalpha():
                continue
            if word_index > 0 and core.lower() in _TITLE_CASE_MINOR_WORDS:
                continue
            if not core[0].isupper():
                violations.append(word)
                break
    return violations


def _check_skills_title_case(resume_data: dict) -> list[str]:
    violations = []
    for line in resume_data.get("SKILLS", []):
        match = re.match(r"^\*\*(.+?):\*\*\s*(.*)$", line)
        if not match:
            continue
        label, items_text = match.groups()
        bad_words = _title_case_violations_in_phrase(label)
        for item in items_text.split(","):
            bad_words.extend(_title_case_violations_in_phrase(item))
        if bad_words:
            violations.append(
                f"Skills line has word(s) not in Title Case ({', '.join(bad_words)}): {line!r}"
            )
    return violations


def _check_pronouns_outside_why(resume_data: dict) -> list[str]:
    """
    Deliberately does not check EXPERIENCE[i]["career_note"]: that field is
    hand-authored fixed content (fixed_content.CAREER_NOTE), unconditionally
    reapplied by normalize_resume.normalize() on every pass including inside
    the fix-retry loop, so a pronoun violation there could never be resolved
    by the LLM and would hard-fail the pipeline every run. tailor_resume.md's
    "Career Note" section documents it as a second, deliberate exception to
    the no-pronouns rule, alongside Why.
    """
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


def _normalize_company(name) -> str:
    """Company name reduced to lowercase alphanumerics and single spaces.

    Punctuation is dropped because this project's own sources disagree on it
    for the same employer: `profile.yml` says "Element 8 / Strategy LLC" while
    `cv.md` says "Element 8 + Strategy, LLC". The builder writes the work
    history from the KB, so it emits the KB's spelling -- and a roster check
    that compares punctuation reports a company as missing that is sitting
    right there in the document. That false "missing" then burns the
    validator's limited fix attempts asking for an entry that already exists.
    """
    return " ".join(re.sub(r"[^0-9a-z]+", " ", str(name).casefold()).split())


def _check_role_roster(resume_data: dict, role_roster: list[str]) -> list[str]:
    """Every company the profile declares must have an EXPERIENCE entry.

    Nothing enforced this before, at any layer, and three employers -- Element
    8 / Strategy LLC, VML and Callahan Creek, the entire page-2 work history --
    were silently absent from the shipped resume. The roster reached the model
    as prose only; the one clause that said "every company must appear" lived
    in a schema `description`, and sanitize_schema() strips descriptions before
    they reach the API, so it was never actually sent. Meanwhile
    _check_experience_completeness() validates fields on entries that *are*
    present and structurally cannot see an absent company.

    Matching is deliberately loose -- normalized case/whitespace, and a
    containment test in either direction. The resume legitimately annotates a
    company name the profile states plainly ("Inside Sales Team" in profile.yml
    vs. "Inside Sales Team (Now Alleyoop)" in the document), and an exact-match
    check flags that as missing. That false positive isn't just noise: each one
    consumes an attempt from the validator's 4-attempt fix loop that a genuinely
    absent employer needed. This check exists to catch a company that is *gone*,
    so it should only fire when no entry mentions it at all.

    Situational roles are excluded by the caller: they're conditional by design
    and their absence is correct.
    """
    if not role_roster:
        return []

    present = [_normalize_company(job.get("company", ""))
               for job in resume_data.get("EXPERIENCE", [])]
    violations = []
    for company in role_roster:
        needle = _normalize_company(company)
        if not needle:
            continue
        if not any(needle in entry or entry in needle for entry in present if entry):
            violations.append(
                f"Role roster: {company!r} is declared in the profile but has no EXPERIENCE entry"
            )
    return violations


def _check_role_order(resume_data: dict, role_roster: list[str]) -> list[str]:
    """EXPERIENCE entries must appear in the same order as profile.yml's
    roles: list -- that list order is reverse-chronological by each role's
    actual period dates (verified against COMPANY_META / bullet-bank.md),
    so it's a fixed fact like Education's fixed order, not a per-JD
    judgment call the model should be re-deriving every run. Observed
    live: Mercor (08/2025) rendered after Inside Sales Team (10/2015-
    08/2016) and Treering (08/2016-08/2024), even though the roster order
    already had it first.

    Loose matching mirrors _check_role_roster() (title parentheticals like
    "(Now Alleyoop)"). A company missing entirely is _check_role_roster()'s
    job, not this one -- it's simply skipped here so one absence doesn't
    also register as a false order violation.
    """
    if not role_roster:
        return []

    normalized_roster = [_normalize_company(c) for c in role_roster]
    matched_indices = []
    for job in resume_data.get("EXPERIENCE", []):
        entry = _normalize_company(job.get("company", ""))
        if not entry:
            continue
        for i, needle in enumerate(normalized_roster):
            if needle and (needle in entry or entry in needle):
                matched_indices.append(i)
                break

    if matched_indices != sorted(matched_indices):
        return [
            "Work history order: EXPERIENCE entries are not in the profile's "
            "declared reverse-chronological order. Expected order: "
            + ", ".join(role_roster)
        ]
    return []


def _check_bullet_counts(resume_data: dict, role_bullet_minimums: dict) -> list[str]:
    """Each EXPERIENCE entry must meet its role's min_bullets floor from
    profile.yml -- the same floor build_role_rules_block()'s "Per-Role
    Bullet Count Targets" table already tells the model, with nothing
    checking it was followed. Observed live: Element 8 / Strategy LLC,
    VML, and Callahan Creek each shipped with 2 achievement bullets
    against a declared min_bullets of 3.

    Loose matching mirrors _check_role_roster() (title parentheticals like
    "(Now Alleyoop)"). A company with no declared minimum (absent from
    the roster, or the roster wasn't supplied) is skipped -- this check
    enforces a floor, not presence.
    """
    if not role_bullet_minimums:
        return []

    violations = []
    for job in resume_data.get("EXPERIENCE", []):
        entry = _normalize_company(job.get("company", ""))
        if not entry:
            continue
        for company, minimum in role_bullet_minimums.items():
            needle = _normalize_company(company)
            if needle and (needle in entry or entry in needle):
                count = len(job.get("achievements") or [])
                if count < minimum:
                    violations.append(
                        f"Bullet count: {job.get('company')!r} has {count} achievement "
                        f"bullet(s), below its required minimum of {minimum}"
                    )
                break
    return violations


def check_keyword_coverage(resume_data: dict, jd_keywords: dict, ats_match_rules: dict) -> dict:
    """Deterministic JD-keyword coverage check (B18, phase-9-backlog.md).
    Neither half of this existed before: ats_match.yaml supplied weights
    and thresholds with no extraction/matching logic behind them, and
    extract_keywords.md's Step-1 output (jd_keywords, already computed
    before the builder ever runs) was never routed anywhere to be checked
    against the finished document. This is the matching logic, using
    ats_match.yaml's own threshold bands to report the result.

    Exact-match only: a keyword's phrase found verbatim (case-insensitive,
    word-bounded) anywhere in the resume text. No semantic/partial
    matching is attempted -- that would need its own LLM call, and is an
    honest limitation, not an oversight.

    Returns a report dict, never a pass/fail violation. A missing keyword
    the candidate genuinely doesn't have is not something the pipeline
    should invent to close the gap, so this is surfaced for a human to
    see, not auto-corrected the way validate()'s violations are."""
    haystack = " ".join([
        _strip_html(resume_data.get("SUMMARY_TEXT", "")),
        _strip_html(resume_data.get("WHY_TEXT", "")),
        " ".join(resume_data.get("SKILLS", [])),
        " ".join(_all_bullets(resume_data)),
        " ".join(job.get("title", "") for job in resume_data.get("EXPERIENCE", [])),
    ]).lower()

    all_keywords = (
        list(jd_keywords.get("tools", []))
        + list(jd_keywords.get("hard_skills", []))
        + list(jd_keywords.get("core_functions", []))
    )
    matched, missing = [], []
    for kw in all_keywords:
        if not kw:
            continue
        if re.search(rf"\b{re.escape(kw.lower())}\b", haystack):
            matched.append(kw)
        else:
            missing.append(kw)

    total = len(matched) + len(missing)
    score = round(100 * len(matched) / total) if total else 100

    thresholds = ats_match_rules.get("thresholds", {}) or {}
    if score >= thresholds.get("excellent_match", 85):
        band = "excellent_match"
    elif score >= thresholds.get("good_match", 70):
        band = "good_match"
    elif score >= thresholds.get("weak_match", 50):
        band = "weak_match"
    else:
        band = "poor_match"

    return {"score": score, "band": band, "matched": matched, "missing": missing}


def validate(
    resume_data: dict,
    style_rules: dict,
    role_roster: list[str] = None,
    role_bullet_minimums: dict = None,
) -> list[str]:
    """role_roster and role_bullet_minimums are optional so callers that
    legitimately validate a partial document (polish.py's single-section
    edits) aren't forced to supply them; omitting either skips its checks
    rather than failing them."""
    violations: list[str] = []
    violations.extend(_check_forbidden_phrases(resume_data, style_rules))
    violations.extend(_check_forbidden_openers(resume_data, style_rules))
    violations.extend(_check_unique_opening_verbs(resume_data))
    violations.extend(_check_tagline_length(resume_data, style_rules))
    violations.extend(_check_bullet_lengths(resume_data, style_rules))
    violations.extend(_check_bullet_widows(resume_data, style_rules))
    violations.extend(_check_skills_line_lengths(resume_data, style_rules))
    violations.extend(_check_skills_title_case(resume_data))
    violations.extend(_check_pronouns_outside_why(resume_data))
    violations.extend(_check_metric_uniqueness(resume_data))
    violations.extend(_check_experience_completeness(resume_data))
    violations.extend(_check_role_roster(resume_data, role_roster or []))
    violations.extend(_check_role_order(resume_data, role_roster or []))
    violations.extend(_check_bullet_counts(resume_data, role_bullet_minimums or {}))
    return violations
