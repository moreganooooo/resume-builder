"""
render_resume_docx.py — Builds an ATS-optimized .docx export of a tailored
resume directly from resume_data (the same uppercase-keyed dict
render_html.py consumes), using python-docx.

Usage (standalone):
    python scripts/render_resume_docx.py output/json/my_resume.json output/docx/my_resume.docx

Called programmatically by orchestrator.py's build_tailored_resume(), AFTER
the Step 7 trim-retry loop and its post-loop PDF text-layer check both
pass -- resume_data mutates across trim iterations (optional client rosters
dropped, the Why section dropped, LLM trim edits), so this must run on the
final, settled data, not the first successful PDF pass. See
docs/superpowers/specs/2026-08-17-docx-exporter-design.md.
"""

import argparse
import json
import os
import re

import docx_theme
import normalize_resume
from docx import Document


def _add_bold_first_sentence(paragraph, text: str) -> None:
    """SUMMARY_TEXT wraps its first sentence in a literal <strong> tag
    (an HTML-rendering convention -- see render_html.py's own comment on
    SUMMARY_TEXT). Strip the tag and apply run-level bold instead, since
    docx has no inline-markup story."""
    match = re.match(r"<strong>(.*?)</strong>(.*)", text, re.DOTALL)
    if match:
        bold_part, rest = match.groups()
        docx_theme.style_run(paragraph.add_run(bold_part), bold=True)
        if rest:
            docx_theme.style_run(paragraph.add_run(rest))
    else:
        docx_theme.style_run(paragraph.add_run(text))


def _add_bold_markdown_runs(paragraph, text: str) -> None:
    """SKILLS entries use "**Category:** Item, Item" markdown-style bold
    (the same convention render_html.py's build_skills_html() converts to
    <strong>) -- split on **...** and alternate bold/plain runs."""
    parts = re.split(r"\*\*(.+?)\*\*", text)
    for i, part in enumerate(parts):
        if not part:
            continue
        docx_theme.style_run(paragraph.add_run(part), bold=i % 2 == 1)


def _is_blank_or_null(value: str) -> bool:
    return not value or value.strip().lower() == "null"


def _write_header(doc, resume_data: dict) -> None:
    """Writes the name line, the tagline and the contact line.

    The tagline gets its own paragraph rather than riding in the contact
    string: the template sets it at 15pt against the contact row's 9.75pt
    (.header-tagline vs .contact-row), and one joined line cannot express
    two sizes.
    """
    # --- Header ---
    docx_theme.name_heading(doc, resume_data.get("NAME", ""))

    tagline = resume_data.get("TAGLINE", "")
    if tagline:
        paragraph = doc.add_paragraph()
        docx_theme.space(paragraph, after=2)
        # The tagline's own pipes are grey in the template too, and the
        # data string carries them literally.
        docx_theme.pipe_join(
            paragraph,
            [part.strip() for part in str(tagline).split("|")],
            size_pt=docx_theme.TAGLINE_PT,
        )

    contact_parts = [
        p
        for p in (
            resume_data.get("PHONE", ""),
            resume_data.get("EMAIL", ""),
            resume_data.get("LINKEDIN_DISPLAY", ""),
            resume_data.get("LOCATION", ""),
        )
        if p
    ]
    if contact_parts:
        paragraph = doc.add_paragraph()
        docx_theme.space(paragraph, after=8)
        docx_theme.pipe_join(paragraph, contact_parts, size_pt=docx_theme.CONTACT_PT)


def _write_summary(doc, resume_data: dict) -> None:
    """Writes the Professional Summary section, if there is one."""
    # --- Summary ---
    summary_text = resume_data.get("SUMMARY_TEXT", "")
    if summary_text:
        docx_theme.section_heading(
            doc, resume_data.get("SECTION_SUMMARY", "Professional Summary")
        )
        p = doc.add_paragraph()
        _add_bold_first_sentence(p, summary_text)


def _write_skills(doc, resume_data: dict) -> None:
    """Writes the Skills section, if there is one."""
    # --- Skills ---
    skills = resume_data.get("SKILLS", [])
    if skills:
        docx_theme.section_heading(doc, resume_data.get("SECTION_SKILLS", "Skills"))
        for skill in skills:
            p = doc.add_paragraph()
            # .skills-grid is a 1px-gap column, not ordinary paragraphs.
            docx_theme.space(p, after=0)
            _add_bold_markdown_runs(p, skill)


def _write_experience(doc, resume_data: dict) -> None:
    """Writes the Work Experience section, if there is one."""
    # --- Experience ---
    experience = resume_data.get("EXPERIENCE", [])
    if experience:
        docx_theme.section_heading(
            doc, resume_data.get("SECTION_EXPERIENCE", "Work Experience")
        )
        for index, job in enumerate(experience):
            title_p = doc.add_paragraph()
            # .job + .job .job-title: breathing room above every role but
            # the first, which the section heading already spaces.
            docx_theme.space(title_p, before=4 if index else 0, after=0)
            docx_theme.style_run(title_p.add_run(job.get("title", "")), bold=True)

            company = job.get("company", "")
            if job.get("size_revenue"):
                company = f"{company} ({job['size_revenue']})"
            meta_parts = [
                p
                for p in (company, job.get("location", ""), job.get("period", ""))
                if p
            ]
            if meta_parts:
                meta_p = doc.add_paragraph()
                docx_theme.space(meta_p, after=2)
                docx_theme.pipe_join(meta_p, meta_parts, bold=True)
                # .job-meta's thin rule, separating company info from the
                # bullets below it.
                docx_theme.add_bottom_rule(meta_p)

            if job.get("clients"):
                p = doc.add_paragraph()
                docx_theme.style_run(p.add_run("Clients: "), bold=True)
                docx_theme.style_run(p.add_run(job["clients"]))

            for label, bullets in normalize_resume.grouped_achievements(job):
                if label:
                    label_p = doc.add_paragraph()
                    docx_theme.space(label_p, before=3, after=0)
                    docx_theme.style_run(
                        label_p.add_run(f"{label}:"), bold=True, italic=True
                    )
                for achievement in bullets:
                    p = doc.add_paragraph(style="List Bullet")
                    # No bold inside bullets, per the design system -- the
                    # run is written here rather than passed to
                    # add_paragraph() so it carries the sheet's font.
                    docx_theme.style_run(p.add_run(achievement))

            if job.get("career_note"):
                p = doc.add_paragraph()
                docx_theme.style_run(p.add_run("Career Note: "), bold=True)
                # .career-note is italic; its label is not.
                docx_theme.style_run(p.add_run(job["career_note"]), italic=True)


def _write_certifications(doc, resume_data: dict) -> None:
    """Writes the Training & Certifications section, if there is one."""
    # --- Certifications ---
    certifications = resume_data.get("CERTIFICATIONS", [])
    if certifications:
        docx_theme.section_heading(
            doc,
            resume_data.get("SECTION_CERTIFICATIONS", "Training & Certifications"),
        )
        for cert in certifications:
            paragraph = doc.add_paragraph()
            docx_theme.space(paragraph, after=1)
            # .cert-title is 800-weight; .cert-org/.cert-year are not.
            title = cert.get("title", "")
            rest = [p for p in (cert.get("org", ""), cert.get("year", "")) if p]
            if title:
                docx_theme.style_run(paragraph.add_run(title), bold=True)
            elif rest:
                # A cert with no title still has to start with content, not
                # with a separator.
                docx_theme.style_run(paragraph.add_run(str(rest.pop(0))))
            for part in rest:
                docx_theme.style_run(
                    paragraph.add_run(" | "), color=docx_theme.RULE_COLOR
                )
                docx_theme.style_run(paragraph.add_run(str(part)))


def _write_education(doc, resume_data: dict) -> None:
    """Writes the Education section, if there is one."""
    # --- Education ---
    education = resume_data.get("EDUCATION", [])
    if education:
        docx_theme.section_heading(
            doc, resume_data.get("SECTION_EDUCATION", "Education")
        )
        for edu in education:
            meta_parts = [
                m
                for m in (
                    edu.get("institution", ""),
                    edu.get("location", ""),
                    edu.get("year", ""),
                )
                if m
            ]
            p = doc.add_paragraph()
            docx_theme.space(p, after=2)
            degree = edu.get("degree", "")
            # .edu-title and .edu-meta-text are both 800-weight; the header
            # carries the same grey rule .job-meta does.
            docx_theme.pipe_join(
                p, ([degree] if degree else []) + meta_parts, bold=True
            )
            docx_theme.add_bottom_rule(p)
            if edu.get("description"):
                docx_theme.body_paragraph(doc, edu["description"])
            for bullet in edu.get("bullets", []):
                bullet_p = doc.add_paragraph(style="List Bullet")
                docx_theme.style_run(bullet_p.add_run(bullet))


def _write_why(doc, resume_data: dict) -> None:
    """Writes the optional 'Additional Relevant Experience' section."""
    # --- Why (optional) ---
    why_text = resume_data.get("WHY_TEXT", "")
    if not _is_blank_or_null(why_text):
        section_why = resume_data.get("SECTION_WHY", "")
        heading = (
            section_why
            if not _is_blank_or_null(section_why)
            else "Additional Relevant Experience"
        )
        docx_theme.section_heading(doc, heading)
        # WHY_TEXT contains literal <p>/<em> tags (see render_html.py's
        # build_why_html() comment) -- split into paragraphs on </p> and
        # strip the tags, rather than collapsing everything into one run.
        raw_paragraphs = [rp for rp in why_text.split("</p>") if rp.strip()]
        for raw_p in raw_paragraphs:
            clean = re.sub(r"</?p>|</?em>", "", raw_p).strip()
            if clean:
                docx_theme.body_paragraph(doc, clean)


def render_resume_docx(resume_data: dict, output_path: str) -> str:
    """
    Builds an ATS-optimized .docx from resume_data and writes it to
    output_path. Returns output_path on success.
    """
    doc = Document()
    # Before any content: apply_document_theme() rewrites the shared Normal
    # / Title / Heading 1 / List Bullet styles and the page margins, so the
    # export matches cv-template.html rather than Word's factory look.
    docx_theme.apply_document_theme(doc)

    _write_header(doc, resume_data)
    _write_summary(doc, resume_data)
    _write_skills(doc, resume_data)
    _write_experience(doc, resume_data)
    _write_certifications(doc, resume_data)
    _write_education(doc, resume_data)
    _write_why(doc, resume_data)

    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    doc.save(output_path)
    return output_path


def main():
    parser = argparse.ArgumentParser(description="Render a resume JSON file to .docx")
    parser.add_argument("input_json")
    parser.add_argument("output_docx")
    args = parser.parse_args()
    with open(args.input_json, "r", encoding="utf-8") as f:
        resume_data = json.load(f)
    render_resume_docx(resume_data, args.output_docx)
    print(f"Resume DOCX rendered -> {args.output_docx}")


if __name__ == "__main__":
    main()
