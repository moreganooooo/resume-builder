"""
render_coverletter_docx.py — Builds an ATS-optimized .docx export of a
tailored cover letter directly from cover_letter_data (the same
lowercase-keyed dict render_coverletter.py consumes), using python-docx.

No embedded signature image (ATS-optimized fidelity call -- see
docs/superpowers/specs/2026-08-17-docx-exporter-design.md): typed name
only, matching what build_signature_block_html() degrades to anyway when a
profile has no signature.png.

Usage (standalone):
    python scripts/render_coverletter_docx.py output/json/my_letter_coverletter.json output/docx/my_letter_coverletter.docx

Called programmatically by orchestrator.py's build_tailored_coverletter().
"""

import argparse
import datetime
import json
import os
import re

import docx_theme
import profile_paths
from docx import Document


def _build_recipient_lines(
    company_name: str,
    contact_name: str = "",
    contact_title: str = "",
    location: str = "",
) -> list[str]:
    """Same recipient-line logic as render_coverletter.py's
    build_recipient_block_html(), minus the HTML wrapping."""
    lines = []
    if contact_name:
        contact_line = f"Attn: {contact_name}"
        if contact_title:
            contact_line += f", {contact_title}"
        lines.append(contact_line)
    elif company_name:
        lines.append(f"{company_name} Hiring Team")
    if company_name:
        lines.append(company_name)
    if location:
        lines.append(location)
    return lines


_CTRL_CHAR_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f]")


def _sanitize(obj):
    """Strip XML-illegal C0 control characters from every string in a
    nested dict/list (same guard as render_resume_docx._sanitize)."""
    if isinstance(obj, str):
        return _CTRL_CHAR_RE.sub("�", obj)
    if isinstance(obj, dict):
        return {k: _sanitize(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_sanitize(v) for v in obj]
    return obj


def render_coverletter_docx(cover_letter_data: dict, output_path: str) -> str:
    """
    Builds an ATS-optimized .docx from cover_letter_data and writes it to
    output_path. Returns output_path on success.
    """
    cover_letter_data = _sanitize(cover_letter_data)
    contact = profile_paths.fixed_content_module().CONTACT_INFO
    doc = Document()
    # The letter is set a notch larger and looser than the resume -- see
    # docx_theme's LETTER_* constants, transcribed from
    # coverletter-template.html.
    docx_theme.apply_document_theme(
        doc,
        body_pt=docx_theme.LETTER_BODY_PT,
        line_spacing=docx_theme.LETTER_LINE_SPACING,
    )
    body_pt = docx_theme.LETTER_BODY_PT

    # --- Header ---
    name_p = docx_theme.name_heading(doc, contact["NAME"])
    for run in name_p.runs:
        run.font.size = docx_theme.Pt(docx_theme.LETTER_NAME_PT)

    tagline = cover_letter_data.get("tagline", "")
    if tagline:
        paragraph = doc.add_paragraph()
        docx_theme.space(paragraph, after=3)
        docx_theme.pipe_join(
            paragraph,
            [part.strip() for part in str(tagline).split("|")],
            size_pt=docx_theme.LETTER_TAGLINE_PT,
        )

    contact_parts = [
        p
        for p in (
            contact.get("PHONE", ""),
            contact.get("EMAIL", ""),
            contact.get("LINKEDIN_DISPLAY", ""),
            contact.get("LOCATION", ""),
        )
        if p
    ]
    if contact_parts:
        paragraph = doc.add_paragraph()
        docx_theme.pipe_join(paragraph, contact_parts, size_pt=docx_theme.CONTACT_PT)
        # .header-rule: the grey line closing the letterhead. Drawn under
        # the contact row rather than as an empty paragraph of its own, so
        # it costs no vertical space on a one-page letter.
        docx_theme.space(paragraph, after=2)
        docx_theme.add_bottom_rule(paragraph)

    # --- Date ---
    # .letter-date's 28px top margin, and the blank line the template puts
    # after the date and after the address, expressed as paragraph spacing.
    date_p = docx_theme.body_paragraph(
        doc, datetime.date.today().strftime("%B %-d, %Y"), size_pt=body_pt
    )
    docx_theme.space(date_p, before=21, after=0)

    # --- Recipient block ---
    recipient_lines = _build_recipient_lines(
        cover_letter_data.get("company_name", ""),
        cover_letter_data.get("contact_name", ""),
        cover_letter_data.get("contact_title", ""),
        cover_letter_data.get("company_location", ""),
    )
    for index, line in enumerate(recipient_lines):
        paragraph = docx_theme.body_paragraph(doc, line, size_pt=body_pt)
        docx_theme.space(paragraph, before=22 if index == 0 else 0, after=0)

    # --- Greeting ---
    greeting = cover_letter_data.get("greeting", "")
    if greeting:
        paragraph = docx_theme.body_paragraph(doc, greeting, size_pt=body_pt)
        docx_theme.space(paragraph, before=22, after=6)

    # --- Body ---
    for paragraph_text in cover_letter_data.get("body_paragraphs", []):
        paragraph = docx_theme.body_paragraph(doc, paragraph_text, size_pt=body_pt)
        docx_theme.space(paragraph, after=7)

    # --- Sign-off (typed name only -- no embedded signature image) ---
    sign_off = cover_letter_data.get("sign_off", "")
    if sign_off:
        paragraph = docx_theme.body_paragraph(doc, sign_off, size_pt=body_pt)
        docx_theme.space(paragraph, before=13, after=0)
    name_line = docx_theme.body_paragraph(doc, contact["NAME"], size_pt=body_pt)
    # The PDF has a signature image here; this export deliberately does
    # not (see the module docstring), so the typed name takes its place
    # with the same breathing room above it.
    docx_theme.space(name_line, before=8, after=0)
    docx_theme.body_paragraph(
        doc, f"{contact['EMAIL']} | {contact['PHONE']}", size_pt=body_pt
    )

    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    doc.save(output_path)
    return output_path


def main():
    parser = argparse.ArgumentParser(
        description="Render a cover letter JSON file to .docx"
    )
    parser.add_argument("input_json")
    parser.add_argument("output_docx")
    args = parser.parse_args()
    with open(args.input_json, "r", encoding="utf-8") as f:
        cover_letter_data = json.load(f)
    render_coverletter_docx(cover_letter_data, args.output_docx)
    print(f"Cover letter DOCX rendered -> {args.output_docx}")


if __name__ == "__main__":
    main()
