"""
validate_resume.py — Deterministic checks for the parts of ResumeDesignSystem.md
that require generated text (Summary, Skills, Bullets, Why) rather than fixed
content. Pure function: takes a normalized resume_data dict and an already-
loaded style_rules dict, returns a list of violation strings. No filesystem
access, no LLM calls -- everything here is mechanically checkable.
"""

import re

_METRIC_PATTERN = re.compile(r"\$?\d[\d,.]*[%MK]?\b", re.IGNORECASE)
_PRONOUN_PATTERN = re.compile(
    r"\b(i|me|my|we|our|she|her|hers|he|him|his)\b", re.IGNORECASE
)
_FIRST_WORD_PATTERN = re.compile(r"[^\w]*(\w+)")
_TITLE_CASE_MINOR_WORDS = {
    "a",
    "an",
    "and",
    "as",
    "at",
    "but",
    "by",
    "for",
    "in",
    "nor",
    "of",
    "on",
    "or",
    "so",
    "the",
    "to",
    "up",
    "vs",
    "via",
    "with",
}
# A number directly preceded by "<letter>-" or "<letter>–" (e.g. the "12"
# in "K-12" or "K–12") is part of a compound label, not a metric.
_COMPOUND_LABEL_PREFIX = re.compile(r"[A-Za-z][-–—]$")
# The unit symbols that can trail a number. These have to be consumed
# before looking for the context word, and folded into the signature:
# _METRIC_PATTERN ends in `[%MK]?\b`, and since "%" is not a word char
# there is no boundary between it and the following space, so the optional
# group backtracks to empty and "%"/"+" are never part of the match. That
# left every percentage and every "N+" with an EMPTY context word, so
# "100% on-time", "100+ campaigns" and "100+ assets" all collapsed to the
# same signature and cross-reported as duplicates -- defeating the whole
# point of the context word below. ("M"/"K" are word chars and so were
# always captured fine.)
_METRIC_UNIT_SUFFIX = re.compile(r"^[%+]+")
# The word (if any) immediately adjacent to a number, e.g. "member" in
# "12-member" or "Performer" in "Top 10 Performer" -- used so two bullets
# that happen to share a bare number in unrelated contexts ("K-12" aside,
# also plain coincidences like a "10-person team" vs "Top 10 Performer")
# aren't treated as the same metric repeated.
_METRIC_CONTEXT_WORD = re.compile(r"^[%+]*[-–—]?\s?(\w+)")
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
                violations.append(
                    f"Bullet uses forbidden opener '{opener}': {bullet!r}"
                )
    return violations


def get_all_metrics(resume_data: dict) -> list[str]:
    """
    Every numeric metric currently used across the CV (Summary + all
    bullets), in document order. Exposed for retry-prompt construction:
    same whack-a-mole risk get_opening_verbs() below already solves for
    opening verbs -- a fix for one duplicate-metric pair, or filler content
    added to lengthen a bullet for an unrelated widow fix, can introduce a
    number that collides with some other, unflagged bullet, since
    uniqueness is a whole-CV constraint, not a pairwise one.
    """
    summary = _strip_html(resume_data.get("SUMMARY_TEXT", ""))
    metrics = [number for number, _sig in _extract_metric_signatures(summary)]
    for bullet in _all_bullets(resume_data):
        metrics.extend(number for number, _sig in _extract_metric_signatures(bullet))
    return metrics


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


def opening_verb(bullet: str) -> str | None:
    """The word the whole-CV uniqueness rule keys on, or None if this
    bullet doesn't have one (numbers don't count as verbs)."""
    match = _FIRST_WORD_PATTERN.match(bullet)
    if not match:
        return None
    first_word = match.group(1).lower()
    if first_word[0].isdigit():
        return None
    return first_word


def uniqueness_keys(bullet: str) -> tuple[set[str], str | None]:
    """One bullet's whole-CV uniqueness fingerprint: (metric signatures,
    opening verb).

    Exposed for orchestrator.mine_bullet_bank(), which uses it to avoid
    *selecting* a colliding set in the first place. Deliberately the same
    function the checks below report on -- a second, separately-derived
    notion of "collision" would drift from this one and the miner would
    quietly stop preventing the violations this module raises.
    """
    return {sig for _n, sig in _extract_metric_signatures(bullet)}, opening_verb(bullet)


def _check_unique_opening_verbs(resume_data: dict) -> list[str]:
    violations = []
    seen = {}
    for bullet in _all_bullets(resume_data):
        first_word = opening_verb(bullet)
        if first_word is None:
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
        return [
            f"Tagline exceeds {max_chars}-char max ({len(tagline)} chars) and will wrap to a 2nd line: {tagline!r}"
        ]
    return []


def _check_bullet_lengths(resume_data: dict, style_rules: dict) -> list[str]:
    violations = []
    limits = style_rules.get("bullet_structure", {})
    two_liner_max = limits.get("two_liner_max_chars", 220)
    for bullet in _all_bullets(resume_data):
        if len(bullet) > two_liner_max:
            violations.append(
                f"Bullet exceeds {two_liner_max}-char two-liner max ({len(bullet)} chars): {bullet!r}"
            )
    return violations


def bullets_with_short_widow(
    bullets: list[str], style_rules: dict
) -> list[tuple[str, int]]:
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
    limits = style_rules.get("bullet_structure", {})
    one_liner_max = limits.get("one_liner_max_chars", 108)
    widow_min_words = limits.get("widow_min_words", 5)
    bullets = [
        bullet
        for job in resume_data.get("EXPERIENCE", [])
        for bullet in job.get("achievements", [])
    ]
    return [
        f"Bullet is {len(bullet)} chars and wraps to a 2nd line at the {one_liner_max}-char "
        f"mark but leaves only a {word_count}-word widow there (fewer than the required "
        f"{widow_min_words}) -- either trim it to {one_liner_max} chars or fewer to fit one "
        f"line, or lengthen it past {one_liner_max} chars so the 2nd line carries at least "
        f"{widow_min_words} words: {bullet!r}"
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
            # Spell out BOTH edges of the legal zone and name the dead band.
            # Stating only the max_chars limit (as this message used to) is
            # unactionable: it reads as "get shorter", but every length from
            # max_chars+1 to max_chars+widow_min_chars-1 is illegal, so a model
            # nudging the line down a few chars at a time never escapes and
            # burns every validator retry. Real 2026-08-12 build failure.
            wrap_min = max_chars + widow_min_chars
            violations.append(
                f"Skills line is {length} chars, which lands in the {max_chars + 1}-{wrap_min - 1} "
                f"dead band -- it wraps to a 2nd line but leaves only a {remainder}-char widow there "
                f"(fewer than the {widow_min_chars} required). NO length in {max_chars + 1}-{wrap_min - 1} "
                f"is valid, so shortening it slightly will fail again. Go to one of the two legal "
                f"targets: cut it to {max_chars} chars or fewer to fit on one line, or add skills to "
                f"reach {wrap_min}-{2 * max_chars} chars so the 2nd line carries real content: {line!r}"
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
    checked_fields.update(
        {f"SKILLS[{i}]": s for i, s in enumerate(resume_data.get("SKILLS", []))}
    )
    checked_fields.update(
        {f"BULLET[{i}]": b for i, b in enumerate(_all_bullets(resume_data))}
    )
    for field_name, text in checked_fields.items():
        if _PRONOUN_PATTERN.search(text):
            violations.append(
                f"Pronoun found outside the Why section, in {field_name}: {text!r}"
            )
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
        if _COMPOUND_LABEL_PREFIX.search(text[max(0, start - 2) : start]):
            continue
        tail = text[match.end() : match.end() + 20]
        suffix_match = _METRIC_UNIT_SUFFIX.match(tail)
        suffix = suffix_match.group(0) if suffix_match else ""
        # Suffix is part of the display number too, so a retry prompt's
        # metric inventory distinguishes "100+" from "100%" instead of
        # listing two identical-looking "100"s.
        number = match.group(0) + suffix
        context_match = _METRIC_CONTEXT_WORD.match(tail)
        context = context_match.group(1).lower() if context_match else ""
        results.append((number, _metric_signature(number, context)))
    return results


def _metric_signature(number: str, context: str) -> str:
    """
    The key two metric mentions must share to count as the same figure.

    The context word (see _METRIC_CONTEXT_WORD) stops a bare "12" in two
    unrelated places from reading as a repeat. But for a big, specific
    figure it causes the opposite error: "$20M, 2,932-account portfolio"
    and "$20M+ portfolio" take different context words and stop colliding,
    though a reader plainly sees the same $20M twice. A figure that is
    distinctive on its own -- currency, a magnitude suffix, or 4+ digits --
    therefore keys on the number alone. Small bare integers keep the
    context word, because 3/10/12 genuinely do coincide across unrelated
    facts.
    """
    # "+" is an approximation marker, not part of the figure: "$20M" and
    # "$20M+" are one fact stated twice.
    core = number.lower().rstrip("+")
    digits = re.sub(r"\D", "", core)
    # A 4-digit year clears the digit-count bar but is a date, not a
    # metric -- two bullets naming the same year aren't citing one figure.
    is_year = len(digits) == 4 and 1900 <= int(digits) <= 2099
    distinctive = not is_year and (
        core.startswith("$") or core.endswith(("m", "k")) or len(digits) >= 4
    )
    # "$20M" and "20M" are the same figure written two ways.
    core = core.replace("$", "").replace(",", "")
    return core if distinctive else f"{core}|{context}"


def _check_metric_uniqueness(resume_data: dict) -> list[str]:
    violations = []
    summary = _strip_html(resume_data.get("SUMMARY_TEXT", ""))
    bullets = _all_bullets(resume_data)
    summary_signatures = {sig for _, sig in _extract_metric_signatures(summary)}
    seen_in_bullets: dict = {}
    for bullet in bullets:
        # Per-bullet, so a single bullet citing the same figure twice for a
        # legitimate reason ("22% reply rates ... exceeding the 22% industry
        # average") isn't reported against ITSELF -- that produced an
        # "in both X and X" message showing the model one identical string
        # twice, which it cannot act on.
        seen_in_this_bullet = set()
        for number, signature in _extract_metric_signatures(bullet):
            if signature in seen_in_this_bullet:
                continue
            seen_in_this_bullet.add(signature)
            if signature in summary_signatures:
                violations.append(
                    f"Metric '{number}' should appear only once across the resume, but appears in both the Summary and a bullet: {bullet!r}"
                )
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
            violations.append(
                f"Experience entry {i} is missing required field(s) {missing}: {job!r}"
            )
        if not job.get("achievements"):
            violations.append(
                f"Experience entry {i} ({job.get('company', 'unknown company')!r}) has no achievement bullets"
            )
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

    present = [
        _normalize_company(job.get("company", ""))
        for job in resume_data.get("EXPERIENCE", [])
    ]
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
        if "career break" in entry or "professional development" in entry:
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


def check_keyword_coverage(
    resume_data: dict, jd_keywords: dict, ats_match_rules: dict
) -> dict:
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
    haystack = " ".join(
        [
            _strip_html(resume_data.get("SUMMARY_TEXT", "")),
            _strip_html(resume_data.get("WHY_TEXT", "")),
            " ".join(resume_data.get("SKILLS", [])),
            " ".join(_all_bullets(resume_data)),
            " ".join(job.get("title", "") for job in resume_data.get("EXPERIENCE", [])),
        ]
    ).lower()

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


def _check_hallucinated_tools(resume_data: dict) -> list[str]:
    """
    Checks if any skills or tools mentioned in the SKILLS section of the resume are
    not present in the verified tools list or master profile configuration.
    """
    import json
    import os
    import re

    # Locate knowledge base for the active profile. Previously this called
    # profile_paths.get_kb_dir() -- a function that has never existed
    # (the real one is kb_dir()) -- so the except branch's hardcoded
    # profiles/morgan/knowledge_base fallback fired unconditionally, on
    # every call, for every profile. Harmless only by coincidence, since
    # the sole real profile is named "morgan"; for any other profile this
    # silently validated tools against a different person's knowledge
    # base. Let failures genuinely propagate now -- validating against
    # the wrong profile's data is worse than a loud crash (F3).
    import profile_paths
    import yaml

    kb_dir = profile_paths.kb_dir()

    verified_tools_path = os.path.join(kb_dir, "verified_tools.json")
    profile_yml_path = os.path.join(kb_dir, "profile.yml")

    allowed_terms = {
        # Common general-purpose categories and terms
        "management",
        "strategy",
        "coaching",
        "ops",
        "enablement",
        "onboarding",
        "copywriting",
        "writing",
        "design",
        "brand",
        "voice",
        "tone",
        "analytics",
        "reporting",
        "metrics",
        "training",
        "governance",
        "automation",
        "campaigns",
        "process mapping",
        "diagramming",
        "templates",
        "hygiene",
        "crm",
        "esp",
        "lead generation",
        "prospecting",
        "b2b",
        "lifecycle marketing",
        "customer marketing",
        # Lifecycle and campaign marketing core competencies
        "segmentation",
        "retention",
        "drip",
        "email",
        "lifecycle",
        "marketing",
        "customer",
        "journey",
        "funnel",
        "flow",
        "flows",
        "testing",
        "a/b testing",
        "optimization",
        "acquisition",
        "engagement",
        "nurture",
        "newsletters",
        "trigger",
        "triggers",
        # Design & creative core skills
        "typography",
        "layout",
        "ideation",
        "visual storytelling",
        "presentation design",
        "graphic design",
        "creative direction",
        "brand identity",
        "art direction",
        # AI & modern workflow competencies
        "prompt engineering",
        "prompting",
        "ai",
        "ai-assisted",
        "ai-accelerated",
        "workflow automation",
        "data pipeline design",
        "content transformation",
        # Content strategy competencies
        "content strategy",
        "content marketing",
        "derivative content",
        "content repurposing",
        "editorial calendar",
        "integrated marketing",
        "campaign messaging",
    }

    # 1. Load verified tools
    if os.path.exists(verified_tools_path):
        try:
            with open(verified_tools_path, "r", encoding="utf-8") as f:
                data = json.load(f)
                for tool in data.get("tools", []):
                    allowed_terms.add(tool["name"].lower())
                    # Also add category name words
                    if tool.get("category"):
                        for w in re.split(r"[,;/ \s]+", tool["category"].lower()):
                            if len(w) > 3:
                                allowed_terms.add(w)
        except Exception:
            pass
    else:
        for fallback_tool in [
            "outreach.io",
            "outreach",
            "salesforce",
            "salesforce crm",
            "hubspot",
            "vidyard",
            "persistiq",
            "mailchimp",
            "mindnode",
            "canva",
            "google sheets",
            "thnks",
        ]:
            allowed_terms.add(fallback_tool.lower())

    # 2. Load profile.yml
    pdata = {}
    if os.path.exists(profile_yml_path):
        try:
            with open(profile_yml_path, "r", encoding="utf-8") as f:
                pdata = yaml.safe_load(f) or {}
        except Exception:
            pdata = {}
    else:
        try:
            pdata = profile_paths.profile_yaml() or {}
        except Exception:
            pdata = {}

    if pdata:
        # Add tags and their keywords
        for tag in pdata.get("tags", []):
            allowed_terms.add(tag["name"].lower())
            for kw in tag.get("keywords", []):
                allowed_terms.add(kw.lower())
        # Add target roles
        target_roles = pdata.get("target_roles", {}) or {}
        for role_group in ["primary", "secondary"]:
            for role in target_roles.get(role_group, []):
                for w in role.lower().split():
                    if len(w) > 3:
                        allowed_terms.add(w)

    # Standard synonyms
    synonyms = {
        "sf": "salesforce crm",
        "sfdc": "salesforce crm",
        "salesforce": "salesforce crm",
        "excel": "google sheets / g-connector",
        "google sheet": "google sheets / g-connector",
        "sheets": "google sheets / g-connector",
        "illustrator": "adobe creative suite",
        "photoshop": "adobe creative suite",
        "indesign": "adobe creative suite",
        "html": "html (email)",
        "css": "html (email)",
        "persistiq": "persist",
    }
    for syn in synonyms:
        allowed_terms.add(syn)

    violations = []
    skills = resume_data.get("SKILLS", []) or []
    for line in skills:
        # Strip bold header category part e.g. "**Sales Operations:** Salesforce CRM"
        clean_line = re.sub(r"^\*\*.+?\*\*[:\-]?\s*", "", line)
        parts = []
        for p in re.split(r"[,;|]", clean_line):
            clean_part = p.strip().strip("[]()\"'").lower()
            if clean_part:
                parts.append((p.strip(), clean_part))

        for orig_part, part in parts:
            # Check if this part (e.g. "salesforce crm") directly matches or contains/is-contained-in
            # any of our allowed terms, or if the individual words in it are allowed.
            matched = False
            if part in allowed_terms:
                matched = True
            else:
                # Substring check
                for allowed in allowed_terms:
                    if part in allowed or allowed in part:
                        matched = True
                        break

            # If not matched as a whole phrase, check if each word in it is a common/allowed word
            if not matched:
                words = [
                    w.strip("(),./") for w in part.split() if len(w.strip("(),./")) > 2
                ]
                if words and all(
                    w in allowed_terms or any(w in a or a in w for a in allowed_terms)
                    for w in words
                ):
                    matched = True

            if not matched:
                violations.append(
                    f"Strict Semantic Guardrail: Hallucinated skill or tool detected: {orig_part!r} "
                    f"(not present in verified_tools.json or profile.yml)"
                )

    return violations


def _check_bullet_star_quality(resume_data: dict) -> list[str]:
    """
    Programmatic STAR/XYZ Syntax Quality Grader.
    Scores each EXPERIENCE bullet point on whether it complies with the
    Google XYZ formula (Accomplished [X] as measured by [Y] by doing [Z]) or STAR.
    Requires each experience achievement bullet to have:
      - A strong active verb (e.g. Led, Optimized, Spearheaded) (30 points)
      - A quantified metric or evidence (e.g. 15%, $20K, 12-member, etc.) (40 points)
      - An outcome or causal connector indicating a business result (30 points)
    If the score is below 70, a validation violation is raised.
    """
    active_verbs = {
        "accelerated",
        "accomplished",
        "achieved",
        "acquired",
        "acted",
        "adapted",
        "addressed",
        "administered",
        "advised",
        "advocated",
        "aligned",
        "allocated",
        "analyzed",
        "anchored",
        "answered",
        "anticipated",
        "applied",
        "appointed",
        "appraised",
        "approved",
        "arbitrated",
        "architected",
        "arranged",
        "articulated",
        "assembled",
        "assessed",
        "assigned",
        "assisted",
        "attained",
        "audited",
        "authored",
        "authorized",
        "automated",
        "awarded",
        "balanced",
        "bargained",
        "benchmarked",
        "blended",
        "blocked",
        "bolstered",
        "boosted",
        "bought",
        "branded",
        "bridged",
        "budgeted",
        "built",
        "calculated",
        "calibrated",
        "campaigned",
        "capitalized",
        "captured",
        "carried",
        "cartographed",
        "carved",
        "cataloged",
        "categorized",
        "caught",
        "caused",
        "centralized",
        "certified",
        "chaired",
        "challenged",
        "championed",
        "channeled",
        "charted",
        "checked",
        "chose",
        "chronicled",
        "circulated",
        "cited",
        "clarified",
        "classified",
        "cleared",
        "closed",
        "co-authored",
        "coached",
        "coalesced",
        "collaborated",
        "collated",
        "collected",
        "combined",
        "commanded",
        "commended",
        "commissioned",
        "committed",
        "communicated",
        "compared",
        "compiled",
        "completed",
        "composed",
        "compounded",
        "computed",
        "conceived",
        "conceptualized",
        "conciliated",
        "conducted",
        "conferred",
        "configured",
        "forecasted",
        "formulated",
        "fostered",
        "founded",
        "framed",
        "franchised",
        "fulfilled",
        "funded",
        "gained",
        "gathered",
        "generated",
        "governed",
        "graded",
        "graduated",
        "granted",
        "grew",
        "grouped",
        "guaranteed",
        "guided",
        "halved",
        "handled",
        "harbored",
        "harvested",
        "headed",
        "heightened",
        "helped",
        "heralded",
        "hired",
        "hosted",
        "hypothesized",
        "identified",
        "illustrated",
        "implemented",
        "imported",
        "improved",
        "improvised",
        "increased",
        "indexed",
        "indoctrinated",
        "induced",
        "influenced",
        "informed",
        "infused",
        "initiated",
        "injected",
        "innovated",
        "inspected",
        "inspired",
        "installed",
        "instigated",
        "instituted",
        "instructed",
        "insured",
        "integrated",
        "intended",
        "intensified",
        "interfaced",
        "interpreted",
        "intervened",
        "interviewed",
        "introduced",
        "invented",
        "inventoried",
        "investigated",
        "invested",
        "invigorated",
        "invited",
        "involved",
        "isolated",
        "issued",
        "itemized",
        "joined",
        "journaled",
        "judged",
        "justified",
        "kept",
        "keyed",
        "kindled",
        "launched",
        "lectured",
        "led",
        "licensed",
        "lightened",
        "linked",
        "liquidated",
        "listened",
        "litigated",
        "lobbied",
        "located",
        "logged",
        "lowered",
        "maintained",
        "managed",
        "mapped",
        "marketed",
        "mastered",
        "maximized",
        "measured",
        "mediated",
        "mentored",
        "merged",
        "met",
        "mined",
        "minimized",
        "modeled",
        "moderated",
        "modified",
        "monitored",
        "motivated",
        "mounted",
        "multiplied",
        "navigated",
        "negotiated",
        "nested",
        "netted",
        "neutralized",
        "nominated",
        "normalized",
        "noticed",
        "notified",
        "nurtured",
        "objected",
        "observed",
        "obtained",
        "occupied",
        "offered",
        "officiated",
        "offset",
        "onboarded",
        "opened",
        "operated",
        "orchestrated",
        "ordered",
        "organized",
        "oriented",
        "originated",
        "outperformed",
        "outsourced",
        "overcame",
        "overhauled",
        "oversaw",
        "owned",
        "packaged",
        "paired",
        "paneled",
        "parlayed",
        "participated",
        "partnered",
        "passed",
        "patented",
        "patrolled",
        "penned",
        "perceived",
        "performed",
        "persuaded",
        "phased",
        "piloted",
        "pinpointed",
        "pioneered",
        "placed",
        "planned",
        "played",
        "policed",
        "portrayed",
        "positioned",
        "posted",
        "practiced",
        "predicted",
        "prepared",
        "prescribed",
        "presented",
        "presided",
        "prevented",
        "priced",
        "prioritized",
        "processed",
        "procured",
        "produced",
        "profiled",
        "programmed",
        "projected",
        "promoted",
        "prompted",
        "proofread",
        "propagated",
        "proposed",
        "prosecuted",
        "protected",
        "proved",
        "provided",
        "provisioned",
        "pruned",
        "publicized",
        "published",
        "purchased",
        "pursued",
        "quadrupled",
        "qualified",
        "quantified",
        "quelled",
        "queried",
        "questioned",
        "queued",
        "raised",
        "ranked",
        "rated",
        "reached",
        "realigned",
        "reaped",
        "rebuilt",
        "recalculated",
        "recalled",
        "received",
        "recognized",
        "recommend",
        "recommended",
        "reconciled",
        "recorded",
        "recovered",
        "recruited",
        "rectified",
        "redesigned",
        "redeveloped",
        "reduced",
        "referred",
        "refinanced",
        "refined",
        "reframed",
        "regulated",
        "rehabilitated",
        "reinforced",
        "reintroduced",
        "reinvested",
        "rejuvenated",
        "related",
        "released",
        "relieved",
        "remedied",
        "remodeled",
        "renegotiated",
        "renovated",
        "reorganized",
        "repaired",
        "repatriated",
        "replaced",
        "replied",
        "reported",
        "represented",
        "reproduced",
        "reprogrammed",
        "requested",
        "required",
        "rescued",
        "researched",
        "reserved",
        "resettled",
        "resolved",
        "respected",
        "responded",
        "restored",
        "restructured",
        "retained",
        "retrieved",
        "revamped",
        "revealed",
        "reverenced",
        "reversed",
        "reviewed",
        "revised",
        "revitalized",
        "revived",
        "rewarded",
        "routed",
        "safeguarded",
        "salvaged",
        "saved",
        "scaled",
        "scanned",
        "scheduled",
        "schooled",
        "screened",
        "scrutinized",
        "secured",
        "segmented",
        "selected",
        "sensed",
        "separated",
        "served",
        "serviced",
        "settled",
        "shaded",
        "shaped",
        "shared",
        "shepherded",
        "shielded",
        "shipped",
        "shortened",
        "showed",
        "shrank",
        "sidestepped",
        "signaled",
        "simplified",
        "simulated",
        "singled",
        "sketched",
        "skilled",
        "slashed",
        "smoothed",
        "socialized",
        "sold",
        "solicited",
        "solved",
        "sorted",
        "sourced",
        "sparked",
        "spearheaded",
        "specialized",
        "specified",
        "spectated",
        "spent",
        "spoke",
        "sponsored",
        "spread",
        "stabilized",
        "staffed",
        "staged",
        "standardized",
        "steered",
        "stimulated",
        "stipulated",
        "stopped",
        "strategized",
        "streamlined",
        "strengthened",
        "stressed",
        "structured",
        "studied",
        "subdivided",
        "subcontracted",
        "submitted",
        "substantiated",
        "substituted",
        "subverted",
        "succeeded",
        "suggested",
        "summarized",
        "superseded",
        "supervised",
        "supplied",
        "supported",
        "surpassed",
        "surveyed",
        "swept",
        "symbolized",
        "synergized",
        "synthesized",
        "systematized",
        "tabulated",
        "tackled",
        "tagged",
        "tailored",
        "targeted",
        "taught",
        "teamed",
        "telecasted",
        "tempered",
        "tended",
        "terminated",
        "tested",
        "testified",
        "themed",
        "thickened",
        "thrived",
        "tied",
        "tightened",
        "tolerated",
        "tooled",
        "topographed",
        "traced",
        "tracked",
        "traded",
        "trained",
        "transacted",
        "transcribed",
        "transferred",
        "transformed",
        "translated",
        "transmitted",
        "transported",
        "traversed",
        "treasured",
        "treated",
        "triaged",
        "triggered",
        "trimmed",
        "tripled",
        "troubleshot",
        "turned",
        "tutored",
        "typeset",
        "umpired",
        "uncovered",
        "underwrote",
        "unfolded",
        "unified",
        "united",
        "unleashed",
        "unlocked",
        "unveiled",
        "updated",
        "upgraded",
        "upholstered",
        "urged",
        "ushered",
        "utilized",
        "vacated",
        "validated",
        "valued",
        "vanquished",
        "vectored",
        "veered",
        "ventured",
        "verbalized",
        "verified",
        "versed",
        "vetoed",
        "vetted",
        "viewed",
        "visited",
        "visualized",
        "voiced",
        "volunteered",
        "voted",
        "vouched",
        "waged",
        "waived",
        "walked",
        "wanted",
        "warned",
        "warranted",
        "washed",
        "watched",
        "weathered",
        "weighed",
        "welcomed",
        "welded",
        "whipped",
        "widened",
        "will",
        "winnowed",
        "wired",
        "withdrew",
        "withstood",
        "won",
        "worked",
        "wrote",
        "yielded",
        "zoned",
    }

    result_indicators = [
        "resulting",
        "driving",
        "to increase",
        "to optimize",
        "to boost",
        "to reduce",
        "to scale",
        "boosting",
        "reducing",
        "growing",
        "capturing",
        "securing",
        "generating",
        "delivering",
        "optimizing",
        "expanding",
        "leading to",
        "which led to",
        "to support",
        "to enable",
        "to drive",
        "to facilitate",
        "thereby",
        "saving",
        "exceeding",
        "surpassing",
        "achieving",
        "reclaiming",
        "attaining",
        "outperforming",
        "increasing",
        "optimising",
        "capturing",
        "facilitating",
        "saving",
        "trimming",
        "shaping",
        "streamlining",
        "empowering",
        "enhancing",
    ]

    # A number is the strongest form of XYZ's "as measured by," but it
    # isn't the only legitimate one -- a promotion, a leadership hand-off,
    # or a named stakeholder outcome are real evidence of impact too.
    # Without this, the metric check alone (40 of 100 points) makes it
    # mathematically impossible for any purely qualitative bullet to ever
    # clear the 70-point threshold, regardless of how well-written it is
    # (see docs/review/master_audit_document.md F9).
    QUALITATIVE_EVIDENCE_PHRASES = [
        "promoted to",
        "promoted from",
        "recognized by",
        "recognized for",
        "selected to",
        "selected as",
        "trusted with",
        "trusted to",
        "became the go-to",
        "became a trusted",
        "praised by",
        "praised for",
        "adopted company-wide",
        "adopted org-wide",
        "asked to lead",
        "tapped to lead",
        "handpicked",
        "entrusted with",
        "earned the trust of",
        "rebuilt trust with",
        "restored confidence",
        "chosen to lead",
        "recommended by",
        "nominated for",
        "named as",
        "appointed to",
    ]

    violations = []
    for job in resume_data.get("EXPERIENCE", []):
        company = job.get("company", "unknown company")
        if (
            "career break" in company.lower()
            or "professional development" in company.lower()
        ):
            continue
        for bullet in job.get("achievements", []):
            score = 100
            reasons = []

            # 1. Action Verb check
            verb = opening_verb(bullet)
            if not verb or verb not in active_verbs:
                score -= 30
                reasons.append("no strong past-tense active verb found at start")

            lowered = bullet.lower()

            # 2. Metric or qualitative-evidence check. Only the full
            # 40-point penalty (no metric AND no qualitative evidence)
            # should be enough to fail a bullet on this axis alone; a
            # bullet with strong qualitative evidence of impact costs less.
            metrics = _extract_metric_signatures(bullet)
            has_qualitative_evidence = any(
                phrase in lowered for phrase in QUALITATIVE_EVIDENCE_PHRASES
            )
            if not metrics and not has_qualitative_evidence:
                score -= 40
                reasons.append(
                    "no quantified metric or qualitative evidence of impact found"
                )
            elif not metrics:
                score -= 15
                reasons.append(
                    "no quantified metric (qualitative evidence of impact present)"
                )

            # 3. Outcome / Causal Connector check
            has_outcome = any(indicator in lowered for indicator in result_indicators)
            if not has_outcome:
                score -= 30
                reasons.append("no explicit business outcome or causal connector found")

            if score < 70:
                violations.append(
                    f"STAR/XYZ Quality Grader (Score {score}/100) inside [{company}]: "
                    f"Bullet lacks sufficient STAR structure (reasons: {', '.join(reasons)}). "
                    f"Please reformulate bullet to follow the XYZ format ('Accomplished [X], as measured by [Y], by doing [Z]'): {bullet!r}"
                )
    return violations


def _check_boilerplate_and_cliches(resume_data: dict) -> list[str]:
    """
    Checks for generic AI-sounding clichés and boilerplate phrases that degrade signaling value,
    ensuring Morgan's authentic, bold, systems-driven voice is maintained.
    """
    cliches = [
        "proven track record",
        "results-oriented professional",
        "results-driven professional",
        "highly motivated",
        "passion for innovation",
        "cross-functional collaboration",
        "dynamic team player",
        "strong communication skills",
        "strategic visionary",
        "synergistic approach",
        "leverage my skills",
        "thought leader",
        "out of the box",
        "go-to person",
        "value-add",
        "best-in-class",
        "passionate about",
        "proven track record of",
    ]
    violations = []

    haystacks = (
        [_strip_html(resume_data.get("SUMMARY_TEXT", ""))]
        + resume_data.get("SKILLS", [])
        + [_strip_html(resume_data.get("WHY_TEXT", ""))]
        + _all_bullets(resume_data)
    )

    for text in haystacks:
        lowered = text.lower()
        for phrase in cliches:
            if re.search(rf"\b{re.escape(phrase)}\b", lowered):
                violations.append(
                    f"Voice Authenticity Guardrail: Generic AI cliché phrase '{phrase}' detected. "
                    f"Rewrite with authentic, direct, active-voice descriptions: {text!r}"
                )
    return violations


def validate(
    resume_data: dict,
    style_rules: dict,
    role_roster: list[str] = None,
    role_bullet_minimums: dict = None,
    enforce_star: bool = False,
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
    violations.extend(_check_hallucinated_tools(resume_data))
    violations.extend(_check_pronouns_outside_why(resume_data))
    violations.extend(_check_metric_uniqueness(resume_data))
    violations.extend(_check_experience_completeness(resume_data))
    violations.extend(_check_role_roster(resume_data, role_roster or []))
    violations.extend(_check_role_order(resume_data, role_roster or []))
    violations.extend(_check_bullet_counts(resume_data, role_bullet_minimums or {}))
    if enforce_star or style_rules.get("enforce_star", False):
        violations.extend(_check_bullet_star_quality(resume_data))
        violations.extend(_check_boilerplate_and_cliches(resume_data))
    return violations
