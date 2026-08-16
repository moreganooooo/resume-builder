"""
validate_pdf_text.py -- Post-render check that pdfminer.six (a stand-in for how an
ATS actually parses the file) can extract everything the resume JSON intended,
straight from the generated PDF's real text layer.

validate_resume.py only ever sees the pre-render JSON -- a rendering bug (font
substitution, ligatures, a keyword split by an unexpected line-break) would still
pass that check while silently corrupting what an ATS actually reads.

Two different kinds of finding come out of here, and they are NOT equally
advisory:

  - "not found intact" is advisory: pdfminer's own extraction has its own
    quirks, so a hit there means "go look," not "the PDF is broken."
  - ligature corruption is deterministic and real. It is not a pdfminer quirk;
    the PDF genuinely encodes "workflows" as "workflows" with a single U+FB02
    glyph, and an ATS keyword-matching "workflows" genuinely misses it. It gets
    its own warning wording for that reason -- reporting it as merely "not found
    intact" reads as *missing text*, which sends a reader hunting for content
    that was never missing while the real keyword damage goes unnoticed.
"""

import logging
import re

from pdfminer.high_level import extract_text

# pdfminer emits an unattributed "FontBBox" warning on every run against these
# templates' fonts; this module is the only caller, so it owns silencing it.
logging.getLogger("pdfminer").setLevel(logging.ERROR)

_TYPOGRAPHIC_SUBSTITUTIONS = {
    "‘": "'", "’": "'",   # curly single quotes
    "“": '"', "”": '"',  # curly double quotes
    "–": "-", "—": "-",  # en dash, em dash
    " ": " ",                 # non-breaking space
}


# Expanded during normalization so a ligature never *also* reads as dropped
# content -- the corruption itself is reported separately by _check_ligatures().
_LIGATURE_EXPANSIONS = {
    "\ufb00": "ff", "\ufb01": "fi", "\ufb02": "fl", "\ufb03": "ffi",
    "\ufb04": "ffl", "\ufb05": "st", "\ufb06": "st",
}
_LIGATURE_TOKEN = re.compile("\\S*[\ufb00-\ufb06]\\S*")

# Emphasis markup never survives into the PDF text layer: the renderer turns
# "**Label:**" into <strong>, so comparing the raw source string against the
# extracted text flagged every skills line on every single run. Asterisks are
# stripped outright rather than only unwrapping matched **...** pairs, since a
# stray unpaired marker would break the comparison exactly the same way.
_MARKUP_PATTERNS = (re.compile(r"<[^>]+>"), re.compile(r"\*"))

_MAX_LIGATURE_WORDS_LISTED = 8


def _normalize(text: str) -> str:
    """Collapse whitespace, strip emphasis markup, and fold the typographic
    substitutions PDF rendering introduces, so none of those look like dropped
    content."""
    text = text or ""
    for pattern in _MARKUP_PATTERNS:
        text = pattern.sub("", text)
    for original, replacement in _TYPOGRAPHIC_SUBSTITUTIONS.items():
        text = text.replace(original, replacement)
    for ligature, expansion in _LIGATURE_EXPANSIONS.items():
        text = text.replace(ligature, expansion)
    return re.sub(r"\s+", " ", text).strip().lower()


def _expand_ligatures(token: str) -> str:
    for ligature, expansion in _LIGATURE_EXPANSIONS.items():
        token = token.replace(ligature, expansion)
    return token


def _check_ligatures(extracted_raw: str) -> list[str]:
    """Reports words the PDF encodes with typographic ligatures -- deterministic
    ATS keyword damage, not a parsing artifact (see the module docstring)."""
    seen: dict[str, str] = {}
    for token in _LIGATURE_TOKEN.findall(extracted_raw or ""):
        seen.setdefault(_expand_ligatures(token), token)
    if not seen:
        return []

    listed = list(seen.items())[:_MAX_LIGATURE_WORDS_LISTED]
    detail = ", ".join(f"{bad!r} should read {good!r}" for good, bad in listed)
    if len(seen) > _MAX_LIGATURE_WORDS_LISTED:
        detail += f", and {len(seen) - _MAX_LIGATURE_WORDS_LISTED} more"
    return [
        f"PDF text layer contains {len(seen)} word(s) encoded with typographic "
        f"ligatures -- an ATS keyword-matching these will not match them: {detail}. "
        f"Fix belongs in the template CSS, not here: font-variant-ligatures: none; "
        f'font-feature-settings: "liga" 0, "clig" 0;'
    ]


def _all_bullets(resume_data: dict) -> list[str]:
    bullets = []
    for job in resume_data.get("EXPERIENCE", []):
        bullets.extend(job.get("achievements", []) or [])
    return bullets


def _check_keyword_coverage_pdf(extracted: str, jd_keywords: dict, resume_data: dict) -> list[str]:
    """Verify that any keyword matched in the resume data JSON also survives
    intact in the extracted PDF text layer."""
    if not jd_keywords:
        return []

    import validate_resume
    # We pass empty rules dict to check_keyword_coverage since we only want the matched list
    json_coverage = validate_resume.check_keyword_coverage(resume_data, jd_keywords, {})
    matched_in_json = json_coverage.get("matched", [])

    warnings = []
    for kw in matched_in_json:
        if not kw:
            continue
        normalized_kw = _normalize(kw)
        if normalized_kw not in extracted:
            warnings.append(
                f"ATS Keyword corrupted in PDF text layer: {kw!r} "
                f"(present in resume JSON but missing/unparseable in PDF)"
            )
    return warnings


def _check_coverletter_keyword_coverage_pdf(extracted: str, jd_keywords: dict, letter_data: dict) -> list[str]:
    """Verify that any keyword found in the cover letter JSON also survives
    intact in the extracted cover letter PDF text layer."""
    if not jd_keywords:
        return []

    all_keywords = (
        list(jd_keywords.get("tools", []))
        + list(jd_keywords.get("hard_skills", []))
        + list(jd_keywords.get("core_functions", []))
    )

    # Build a haystack of letter JSON content
    letter_haystack = _normalize(" ".join(letter_data.get("body_paragraphs", []) or []))

    warnings = []
    for kw in all_keywords:
        if not kw:
            continue
        normalized_kw = _normalize(kw)
        if normalized_kw in letter_haystack:
            if normalized_kw not in extracted:
                warnings.append(
                    f"ATS Keyword corrupted in Cover Letter PDF text layer: {kw!r} "
                    f"(present in cover letter JSON but missing/unparseable in PDF)"
                )
    return warnings


def validate_pdf_text(pdf_path: str, resume_data: dict, jd_keywords: dict = None) -> tuple[list[str], list[str]]:
    """
    Extracts text from the rendered PDF and checks that the tagline, summary,
    why-section text, every bullet, and every skills line from the source
    resume JSON survived intact in the PDF's text layer. Also verifies that all
    matched JD keywords are uncorrupted in the PDF.

    Returns (fatal, advisories) -- two categorically different findings down
    one channel used to collapse into a single warnings list, which let a
    missing/unparseable PDF read as just another soft note. `fatal` is
    non-empty only when the PDF itself couldn't be read at all (missing file,
    corrupt output); callers must treat that as a build failure, not print
    success, and not move the JD along. `advisories` are the soft notes
    (ligatures, a line not found intact) that are fine to report and proceed.
    """
    try:
        extracted_raw = extract_text(pdf_path)
    except Exception as e:
        return [f"Could not parse generated PDF for verification: {e}"], []

    extracted = _normalize(extracted_raw)

    # Ligature findings come first: they name a real, deterministic defect,
    # and burying them under advisory "not found intact" lines is what made
    # them unreadable in the first place.
    advisories = _check_ligatures(extracted_raw)

    # TAGLINE/SUMMARY_TEXT/WHY_TEXT used to be unchecked -- only EXPERIENCE
    # bullets and SKILLS lines were compared against the PDF's text layer,
    # even though SUMMARY_TEXT carries the single heaviest JD-keyword weight
    # of any section (summary_score.yaml's relevance_to_jd is 30/100) and is
    # exactly the kind of content a font-substitution or line-break bug would
    # silently corrupt without this catching it. WHY_TEXT is intentionally
    # blank on many builds (omitted to save space), so only check it when set.
    tagline = resume_data.get("TAGLINE") or ""
    if tagline and _normalize(tagline) not in extracted:
        advisories.append(f"Tagline not found intact in PDF text layer: {tagline[:80]}")

    summary_text = resume_data.get("SUMMARY_TEXT") or ""
    if summary_text and _normalize(summary_text) not in extracted:
        advisories.append(f"Summary not found intact in PDF text layer: {summary_text[:80]}")

    why_text = resume_data.get("WHY_TEXT") or ""
    if why_text and _normalize(why_text) not in extracted:
        advisories.append(f"Why-section text not found intact in PDF text layer: {why_text[:80]}")

    for bullet in _all_bullets(resume_data):
        if _normalize(bullet) not in extracted:
            advisories.append(f"Bullet not found intact in PDF text layer: {bullet[:80]}")

    for skill_line in resume_data.get("SKILLS", []) or []:
        if _normalize(skill_line) not in extracted:
            advisories.append(f"Skills line not found intact in PDF text layer: {skill_line[:80]}")

    # Verify matched keywords are not corrupted in PDF text layer
    if jd_keywords:
        advisories.extend(_check_keyword_coverage_pdf(extracted, jd_keywords, resume_data))

    return [], advisories


def validate_coverletter_pdf_text(pdf_path: str, letter_data: dict, jd_keywords: dict = None) -> list[str]:
    """
    Same check, cover-letter shaped: body paragraphs and the greeting instead
    of EXPERIENCE bullets and SKILLS lines.

    Exists because the cover letter is half of every application package and
    had no text-layer verification at all -- the resume-shaped function can't
    stand in for it, since letter_data has no EXPERIENCE or SKILLS key and
    would silently check nothing. Paragraphs are matched whole; a long
    paragraph that wraps is still one continuous run of text after
    normalization, exactly like a bullet.
    """
    try:
        extracted_raw = extract_text(pdf_path)
    except Exception as e:
        return [f"Could not parse generated cover-letter PDF for verification: {e}"]

    extracted = _normalize(extracted_raw)
    warnings = _check_ligatures(extracted_raw)

    for para in letter_data.get("body_paragraphs", []) or []:
        if _normalize(para) not in extracted:
            warnings.append(f"Paragraph not found intact in PDF text layer: {para[:80]}")

    greeting = letter_data.get("greeting") or ""
    if greeting and _normalize(greeting) not in extracted:
        warnings.append(f"Greeting not found intact in PDF text layer: {greeting[:80]}")

    # Verify placed cover letter keywords are not corrupted in PDF text layer
    if jd_keywords:
        warnings.extend(_check_coverletter_keyword_coverage_pdf(extracted, jd_keywords, letter_data))

    return warnings
