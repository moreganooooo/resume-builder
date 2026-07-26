"""
validate_pdf_text.py -- Post-render check that pdfminer.six (a stand-in for how an
ATS actually parses the file) can extract everything the resume JSON intended,
straight from the generated PDF's real text layer.

validate_resume.py only ever sees the pre-render JSON -- a rendering bug (font
substitution, ligatures, a keyword split by an unexpected line-break) would still
pass that check while silently corrupting what an ATS actually reads. This is
advisory only: pdfminer's own extraction has its own quirks, so a hit here means
"go look," not "the PDF is broken."
"""

import re

from pdfminer.high_level import extract_text

_TYPOGRAPHIC_SUBSTITUTIONS = {
    "‘": "'", "’": "'",   # curly single quotes
    "“": '"', "”": '"',  # curly double quotes
    "–": "-", "—": "-",  # en dash, em dash
    " ": " ",                 # non-breaking space
}


def _normalize(text: str) -> str:
    """Collapse whitespace and common typographic substitutions PDF rendering
    introduces so those don't look like dropped content."""
    text = text or ""
    for original, replacement in _TYPOGRAPHIC_SUBSTITUTIONS.items():
        text = text.replace(original, replacement)
    return re.sub(r"\s+", " ", text).strip().lower()


def _all_bullets(resume_data: dict) -> list[str]:
    bullets = []
    for job in resume_data.get("EXPERIENCE", []):
        bullets.extend(job.get("achievements", []) or [])
    return bullets


def validate_pdf_text(pdf_path: str, resume_data: dict) -> list[str]:
    """
    Extracts text from the rendered PDF and checks that every bullet and skills
    line from the source resume JSON survived intact in the PDF's text layer.
    Returns a list of warning strings (empty if nothing looks wrong).
    """
    try:
        extracted = _normalize(extract_text(pdf_path))
    except Exception as e:
        return [f"Could not parse generated PDF for verification: {e}"]

    warnings = []
    for bullet in _all_bullets(resume_data):
        if _normalize(bullet) not in extracted:
            warnings.append(f"Bullet not found intact in PDF text layer: {bullet[:80]}")

    for skill_line in resume_data.get("SKILLS", []) or []:
        if _normalize(skill_line) not in extracted:
            warnings.append(f"Skills line not found intact in PDF text layer: {skill_line[:80]}")

    return warnings
