# DOCX Exporter Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add automatic, ATS-optimized `.docx` export for both resumes and cover letters, generated alongside the existing JSON/HTML/PDF artifacts on every build.

**Architecture:** Two new sibling renderer modules (`render_resume_docx.py`, `render_coverletter_docx.py`) build `.docx` files directly with `python-docx`, consuming the exact same `resume_data`/`cover_letter_data` dicts the existing HTML renderers already consume — no new schema, no template file. `orchestrator.py` calls each one right after its corresponding PDF succeeds (cover letter) or after the whole trim-retry loop settles (resume — `resume_data` mutates across that loop, so DOCX must use the final data, not the first pass).

**Tech Stack:** Python 3.10+, `python-docx` 1.2.0 (already a pinned dependency, used today only for reading — this is its first write usage), stdlib `unittest`.

**Spec:** `docs/superpowers/specs/2026-08-17-docx-exporter-design.md`

## Global Constraints

- `python-docx` is already in `requirements.txt` — no dependency changes needed.
- ATS-optimized fidelity: single column, Word's built-in `Title`/`Heading 1`/`Normal`/`List Bullet` styles only. No colors, borders, tables, multi-column layout, or embedded images.
- Both renderer functions are pure: `(data: dict, output_path: str) -> str`, returning `output_path`. No side effects beyond writing the file (each self-creates its output directory via `os.makedirs(os.path.dirname(output_path), exist_ok=True)`, matching `render_coverletter.py`'s existing convention).
- DOCX generation is always-on (no CLI flag) and blocks the build on failure — a JD is not marked complete unless JSON, HTML, PDF, and DOCX all exist, matching the existing PDF-failure early-return shape (`return {}`).
- Run the full suite (`python -m unittest discover -s tests -v`) after each task, not just the new test file — this codebase's regression history (see `docs/superpowers/plans/2026-08-17-cover-letter-blueprint-roadmap.md`'s Group A/B gotchas) shows shared fixtures break in non-obvious ways.

---

## Task 1: `render_coverletter_docx.py`

**Files:**
- Create: `scripts/render_coverletter_docx.py`
- Test: `tests/test_render_coverletter_docx.py`

**Interfaces:**
- Consumes: `profile_paths.fixed_content_module().CONTACT_INFO` (dict with uppercase keys `NAME`, `PHONE`, `EMAIL`, `LINKEDIN_DISPLAY`, `LOCATION` — same source `render_coverletter.py:78` already reads).
- Produces: `render_coverletter_docx(cover_letter_data: dict, output_path: str) -> str`, importable as `from render_coverletter_docx import render_coverletter_docx`. Used by Task 3.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_render_coverletter_docx.py`:

```python
import os
import sys
import unittest

SCRIPTS_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts")
sys.path.insert(0, SCRIPTS_DIR)

from docx import Document  # noqa: E402

from render_coverletter_docx import render_coverletter_docx  # noqa: E402


def _minimal_letter_data(**overrides):
    data = {
        "company_name": "Acme Corp",
        "tagline": "PRODUCT MANAGER | GROWTH",
        "greeting": "Dear Acme Corp Hiring Team,",
        "body_paragraphs": [
            "I'm excited to apply for this role at Acme Corp.",
            "My background lines up well with what you need.",
        ],
        "sign_off": "Sincerely,",
    }
    data.update(overrides)
    return data


class TestRenderCoverletterDocx(unittest.TestCase):

    def setUp(self):
        self.out_path = os.path.join(os.path.dirname(__file__), "_tmp_coverletter_docx_test.docx")

    def tearDown(self):
        if os.path.exists(self.out_path):
            os.remove(self.out_path)

    def _paragraph_texts(self, doc):
        return [p.text for p in doc.paragraphs]

    def test_header_contains_senders_name_and_contact_from_fixed_content(self):
        # This repo's tests read real profile data via fixed_content_module()
        # rather than mocking it (see test_render_coverletter.py's
        # test_contact_info_comes_from_fixed_content) -- the active profile's
        # own contact info is asserted directly.
        render_coverletter_docx(_minimal_letter_data(), self.out_path)
        doc = Document(self.out_path)
        texts = self._paragraph_texts(doc)
        self.assertIn("Morgan Escott", texts)
        contact_line = next(t for t in texts if "escott.morgan@gmail.com" in t)
        self.assertIn("PRODUCT MANAGER | GROWTH", contact_line)

    def test_recipient_block_uses_hiring_team_when_no_contact_name(self):
        render_coverletter_docx(_minimal_letter_data(), self.out_path)
        doc = Document(self.out_path)
        texts = self._paragraph_texts(doc)
        self.assertIn("Acme Corp Hiring Team", texts)
        self.assertIn("Acme Corp", texts)

    def test_recipient_block_uses_attn_line_when_contact_name_present(self):
        render_coverletter_docx(
            _minimal_letter_data(contact_name="Maggie Smith", contact_title="HR Manager"),
            self.out_path,
        )
        doc = Document(self.out_path)
        texts = self._paragraph_texts(doc)
        self.assertIn("Attn: Maggie Smith, HR Manager", texts)

    def test_recipient_block_includes_location_when_present(self):
        render_coverletter_docx(_minimal_letter_data(company_location="Austin, TX"), self.out_path)
        doc = Document(self.out_path)
        texts = self._paragraph_texts(doc)
        self.assertIn("Austin, TX", texts)

    def test_body_paragraphs_each_render_as_their_own_paragraph(self):
        render_coverletter_docx(_minimal_letter_data(), self.out_path)
        doc = Document(self.out_path)
        texts = self._paragraph_texts(doc)
        self.assertIn("I'm excited to apply for this role at Acme Corp.", texts)
        self.assertIn("My background lines up well with what you need.", texts)

    def test_sign_off_and_typed_name_render_with_no_embedded_image(self):
        render_coverletter_docx(_minimal_letter_data(), self.out_path)
        doc = Document(self.out_path)
        texts = self._paragraph_texts(doc)
        self.assertIn("Sincerely,", texts)
        self.assertIn("Morgan Escott", texts)
        # Confirms the ATS-optimized "no signature image" design decision
        # (spec: docs/superpowers/specs/2026-08-17-docx-exporter-design.md) --
        # a real signature-image build would add an inline_shapes entry.
        self.assertEqual(len(doc.inline_shapes), 0)

    def test_returns_output_path(self):
        result = render_coverletter_docx(_minimal_letter_data(), self.out_path)
        self.assertEqual(result, self.out_path)

    def test_creates_parent_directory_if_missing(self):
        nested_path = os.path.join(os.path.dirname(__file__), "_tmp_docx_subdir", "letter.docx")
        try:
            render_coverletter_docx(_minimal_letter_data(), nested_path)
            self.assertTrue(os.path.exists(nested_path))
        finally:
            if os.path.exists(nested_path):
                os.remove(nested_path)
            subdir = os.path.dirname(nested_path)
            if os.path.isdir(subdir):
                os.rmdir(subdir)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `source .venv/bin/activate && python -m unittest tests.test_render_coverletter_docx -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'render_coverletter_docx'`

- [ ] **Step 3: Write the implementation**

Create `scripts/render_coverletter_docx.py`:

```python
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

from docx import Document

import profile_paths


def _build_recipient_lines(company_name: str, contact_name: str = "", contact_title: str = "",
                            location: str = "") -> list[str]:
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


def render_coverletter_docx(cover_letter_data: dict, output_path: str) -> str:
    """
    Builds an ATS-optimized .docx from cover_letter_data and writes it to
    output_path. Returns output_path on success.
    """
    contact = profile_paths.fixed_content_module().CONTACT_INFO
    doc = Document()

    # --- Header ---
    doc.add_heading(contact["NAME"], level=0)
    header_parts = [
        p for p in (
            cover_letter_data.get("tagline", ""),
            contact.get("PHONE", ""),
            contact.get("EMAIL", ""),
            contact.get("LINKEDIN_DISPLAY", ""),
            contact.get("LOCATION", ""),
        ) if p
    ]
    if header_parts:
        doc.add_paragraph(" | ".join(header_parts))

    # --- Date ---
    doc.add_paragraph(datetime.date.today().strftime("%B %-d, %Y"))

    # --- Recipient block ---
    for line in _build_recipient_lines(
        cover_letter_data.get("company_name", ""),
        cover_letter_data.get("contact_name", ""),
        cover_letter_data.get("contact_title", ""),
        cover_letter_data.get("company_location", ""),
    ):
        doc.add_paragraph(line)

    # --- Greeting ---
    greeting = cover_letter_data.get("greeting", "")
    if greeting:
        doc.add_paragraph(greeting)

    # --- Body ---
    for paragraph in cover_letter_data.get("body_paragraphs", []):
        doc.add_paragraph(paragraph)

    # --- Sign-off (typed name only -- no embedded signature image) ---
    sign_off = cover_letter_data.get("sign_off", "")
    if sign_off:
        doc.add_paragraph(sign_off)
    doc.add_paragraph(contact["NAME"])
    doc.add_paragraph(f"{contact['EMAIL']} | {contact['PHONE']}")

    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    doc.save(output_path)
    return output_path


def main():
    parser = argparse.ArgumentParser(description="Render a cover letter JSON file to .docx")
    parser.add_argument("input_json")
    parser.add_argument("output_docx")
    args = parser.parse_args()
    with open(args.input_json, "r", encoding="utf-8") as f:
        cover_letter_data = json.load(f)
    render_coverletter_docx(cover_letter_data, args.output_docx)
    print(f"Cover letter DOCX rendered -> {args.output_docx}")


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `source .venv/bin/activate && python -m unittest tests.test_render_coverletter_docx -v`
Expected: PASS (8 tests)

- [ ] **Step 5: Commit**

```bash
git add scripts/render_coverletter_docx.py tests/test_render_coverletter_docx.py
git commit -m "feat(coverletter): add ATS-optimized DOCX renderer (Group C, part 1/4)"
```

---

## Task 2: `render_resume_docx.py`

**Files:**
- Create: `scripts/render_resume_docx.py`
- Test: `tests/test_render_resume_docx.py`

**Interfaces:**
- Consumes: nothing beyond its `resume_data` argument (no external module calls).
- Produces: `render_resume_docx(resume_data: dict, output_path: str) -> str`, importable as `from render_resume_docx import render_resume_docx`. Used by Task 4.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_render_resume_docx.py`:

```python
import os
import sys
import unittest

SCRIPTS_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts")
sys.path.insert(0, SCRIPTS_DIR)

from docx import Document  # noqa: E402

from render_resume_docx import render_resume_docx  # noqa: E402


def _minimal_resume_data(**overrides):
    data = {
        "NAME": "Jane Doe",
        "TAGLINE": "PRODUCT MANAGER | GROWTH",
        "PHONE": "555-123-4567",
        "EMAIL": "jane@example.com",
        "LINKEDIN_DISPLAY": "linkedin.com/in/janedoe",
        "LOCATION": "Austin, TX",
        "SUMMARY_TEXT": "<strong>Product leader with 10 years experience.</strong> Focused on growth.",
        "SKILLS": ["**Product:** Roadmapping, A/B Testing", "SQL"],
        "EXPERIENCE": [{
            "title": "Senior PM",
            "company": "Acme Corp",
            "location": "Remote",
            "period": "2020-Present",
            "achievements": ["Shipped a feature used by 1M users."],
        }],
        "CERTIFICATIONS": [{"title": "PMP", "org": "PMI", "year": "2019"}],
        "EDUCATION": [{"degree": "B.S. Computer Science", "institution": "State University", "year": "2015"}],
    }
    data.update(overrides)
    return data


class TestRenderResumeDocx(unittest.TestCase):

    def setUp(self):
        self.out_path = os.path.join(os.path.dirname(__file__), "_tmp_resume_docx_test.docx")

    def tearDown(self):
        if os.path.exists(self.out_path):
            os.remove(self.out_path)

    def _paragraph_texts(self, doc):
        return [p.text for p in doc.paragraphs]

    def test_header_contains_name_and_contact_line(self):
        render_resume_docx(_minimal_resume_data(), self.out_path)
        doc = Document(self.out_path)
        texts = self._paragraph_texts(doc)
        self.assertIn("Jane Doe", texts)
        contact_line = next(t for t in texts if "555-123-4567" in t)
        self.assertIn("PRODUCT MANAGER | GROWTH", contact_line)
        self.assertIn("jane@example.com", contact_line)
        self.assertIn("Austin, TX", contact_line)

    def test_summary_first_sentence_is_bold_and_strong_tags_are_stripped(self):
        render_resume_docx(_minimal_resume_data(), self.out_path)
        doc = Document(self.out_path)
        summary_para = next(p for p in doc.paragraphs if "Product leader" in p.text)
        self.assertNotIn("<strong>", summary_para.text)
        self.assertNotIn("</strong>", summary_para.text)
        self.assertTrue(summary_para.runs[0].bold)
        self.assertIn("Product leader with 10 years experience.", summary_para.runs[0].text)
        self.assertFalse(summary_para.runs[-1].bold)

    def test_skills_markdown_bold_is_converted_to_a_bold_run(self):
        render_resume_docx(_minimal_resume_data(), self.out_path)
        doc = Document(self.out_path)
        skill_para = next(p for p in doc.paragraphs if "Roadmapping" in p.text)
        self.assertNotIn("**", skill_para.text)
        bold_run = next(r for r in skill_para.runs if r.text == "Product:")
        self.assertTrue(bold_run.bold)

    def test_experience_renders_title_meta_and_bulleted_achievements(self):
        render_resume_docx(_minimal_resume_data(), self.out_path)
        doc = Document(self.out_path)
        texts = self._paragraph_texts(doc)
        self.assertIn("Senior PM", texts)
        meta_line = next(t for t in texts if "Acme Corp" in t)
        self.assertIn("Remote", meta_line)
        self.assertIn("2020-Present", meta_line)
        bullet_para = next(p for p in doc.paragraphs if "Shipped a feature" in p.text)
        self.assertEqual(bullet_para.style.name, "List Bullet")

    def test_size_revenue_is_appended_to_company_in_parentheses(self):
        data = _minimal_resume_data()
        data["EXPERIENCE"][0]["size_revenue"] = "500 employees"
        render_resume_docx(data, self.out_path)
        doc = Document(self.out_path)
        meta_line = next(p.text for p in doc.paragraphs if "Acme Corp" in p.text)
        self.assertIn("Acme Corp (500 employees)", meta_line)

    def test_clients_and_career_note_render_as_labeled_lines(self):
        data = _minimal_resume_data()
        data["EXPERIENCE"][0]["clients"] = "Fortune 500 retailers"
        data["EXPERIENCE"][0]["career_note"] = "Took a planned career break in 2019."
        render_resume_docx(data, self.out_path)
        doc = Document(self.out_path)
        texts = self._paragraph_texts(doc)
        clients_line = next(t for t in texts if "Fortune 500 retailers" in t)
        self.assertIn("Clients:", clients_line)
        note_line = next(t for t in texts if "planned career break" in t)
        self.assertIn("Career Note:", note_line)

    def test_certifications_render_as_pipe_separated_line(self):
        render_resume_docx(_minimal_resume_data(), self.out_path)
        doc = Document(self.out_path)
        texts = self._paragraph_texts(doc)
        self.assertIn("PMP | PMI | 2019", texts)

    def test_education_renders_degree_meta_description_and_bullets(self):
        data = _minimal_resume_data()
        data["EDUCATION"][0]["description"] = "Focus in distributed systems."
        data["EDUCATION"][0]["bullets"] = ["Dean's List, all semesters."]
        render_resume_docx(data, self.out_path)
        doc = Document(self.out_path)
        texts = self._paragraph_texts(doc)
        degree_line = next(t for t in texts if "B.S. Computer Science" in t)
        self.assertIn("State University", degree_line)
        self.assertIn("2015", degree_line)
        self.assertIn("Focus in distributed systems.", texts)
        bullet_para = next(p for p in doc.paragraphs if "Dean's List" in p.text)
        self.assertEqual(bullet_para.style.name, "List Bullet")

    def test_why_section_is_omitted_entirely_when_blank(self):
        render_resume_docx(_minimal_resume_data(WHY_TEXT="", SECTION_WHY=""), self.out_path)
        doc = Document(self.out_path)
        headings = [p.text for p in doc.paragraphs if p.style.name.startswith("Heading")]
        self.assertNotIn("Additional Relevant Experience", headings)

    def test_why_section_is_omitted_when_literal_null_string(self):
        render_resume_docx(_minimal_resume_data(WHY_TEXT="null", SECTION_WHY="null"), self.out_path)
        doc = Document(self.out_path)
        texts = self._paragraph_texts(doc)
        self.assertNotIn("null", [t.strip().lower() for t in texts])

    def test_why_section_renders_with_default_heading_and_strips_html_tags(self):
        data = _minimal_resume_data(
            WHY_TEXT="<p><em>I've long admired</em> this company's mission.</p><p>I'd love to contribute.</p>",
            SECTION_WHY="",
        )
        render_resume_docx(data, self.out_path)
        doc = Document(self.out_path)
        texts = self._paragraph_texts(doc)
        self.assertIn("Additional Relevant Experience", texts)
        self.assertIn("I've long admired this company's mission.", texts)
        self.assertIn("I'd love to contribute.", texts)
        joined = "\n".join(texts)
        self.assertNotIn("<p>", joined)
        self.assertNotIn("<em>", joined)

    def test_why_section_uses_custom_heading_when_provided(self):
        data = _minimal_resume_data(WHY_TEXT="I'm a great fit.", SECTION_WHY="Why Acme Corp?")
        render_resume_docx(data, self.out_path)
        doc = Document(self.out_path)
        texts = self._paragraph_texts(doc)
        self.assertIn("Why Acme Corp?", texts)

    def test_returns_output_path(self):
        result = render_resume_docx(_minimal_resume_data(), self.out_path)
        self.assertEqual(result, self.out_path)

    def test_creates_parent_directory_if_missing(self):
        nested_path = os.path.join(os.path.dirname(__file__), "_tmp_docx_subdir", "resume.docx")
        try:
            render_resume_docx(_minimal_resume_data(), nested_path)
            self.assertTrue(os.path.exists(nested_path))
        finally:
            if os.path.exists(nested_path):
                os.remove(nested_path)
            subdir = os.path.dirname(nested_path)
            if os.path.isdir(subdir):
                os.rmdir(subdir)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `source .venv/bin/activate && python -m unittest tests.test_render_resume_docx -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'render_resume_docx'`

- [ ] **Step 3: Write the implementation**

Create `scripts/render_resume_docx.py`:

```python
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


from docx import Document


def _add_bold_first_sentence(paragraph, text: str) -> None:
    """SUMMARY_TEXT wraps its first sentence in a literal <strong> tag
    (an HTML-rendering convention -- see render_html.py's own comment on
    SUMMARY_TEXT). Strip the tag and apply run-level bold instead, since
    docx has no inline-markup story."""
    match = re.match(r"<strong>(.*?)</strong>(.*)", text, re.DOTALL)
    if match:
        bold_part, rest = match.groups()
        run = paragraph.add_run(bold_part)
        run.bold = True
        if rest:
            paragraph.add_run(rest)
    else:
        paragraph.add_run(text)


def _add_bold_markdown_runs(paragraph, text: str) -> None:
    """SKILLS entries use "**Category:** Item, Item" markdown-style bold
    (the same convention render_html.py's build_skills_html() converts to
    <strong>) -- split on **...** and alternate bold/plain runs."""
    parts = re.split(r"\*\*(.+?)\*\*", text)
    for i, part in enumerate(parts):
        if not part:
            continue
        run = paragraph.add_run(part)
        run.bold = (i % 2 == 1)


def _is_blank_or_null(value: str) -> bool:
    return not value or value.strip().lower() == "null"


def render_resume_docx(resume_data: dict, output_path: str) -> str:
    """
    Builds an ATS-optimized .docx from resume_data and writes it to
    output_path. Returns output_path on success.
    """
    doc = Document()

    # --- Header ---
    doc.add_heading(resume_data.get("NAME", ""), level=0)
    contact_parts = [
        p for p in (
            resume_data.get("TAGLINE", ""),
            resume_data.get("PHONE", ""),
            resume_data.get("EMAIL", ""),
            resume_data.get("LINKEDIN_DISPLAY", ""),
            resume_data.get("LOCATION", ""),
        ) if p
    ]
    if contact_parts:
        doc.add_paragraph(" | ".join(contact_parts))

    # --- Summary ---
    summary_text = resume_data.get("SUMMARY_TEXT", "")
    if summary_text:
        doc.add_heading(resume_data.get("SECTION_SUMMARY", "Professional Summary"), level=1)
        p = doc.add_paragraph()
        _add_bold_first_sentence(p, summary_text)

    # --- Skills ---
    skills = resume_data.get("SKILLS", [])
    if skills:
        doc.add_heading(resume_data.get("SECTION_SKILLS", "Skills"), level=1)
        for skill in skills:
            p = doc.add_paragraph()
            _add_bold_markdown_runs(p, skill)

    # --- Experience ---
    experience = resume_data.get("EXPERIENCE", [])
    if experience:
        doc.add_heading(resume_data.get("SECTION_EXPERIENCE", "Work Experience"), level=1)
        for job in experience:
            title_p = doc.add_paragraph()
            title_run = title_p.add_run(job.get("title", ""))
            title_run.bold = True

            company = job.get("company", "")
            if job.get("size_revenue"):
                company = f"{company} ({job['size_revenue']})"
            meta_parts = [p for p in (company, job.get("location", ""), job.get("period", "")) if p]
            if meta_parts:
                doc.add_paragraph(" | ".join(meta_parts))

            if job.get("clients"):
                p = doc.add_paragraph()
                run = p.add_run("Clients: ")
                run.bold = True
                p.add_run(job["clients"])

            for achievement in job.get("achievements", []):
                doc.add_paragraph(achievement, style="List Bullet")

            if job.get("career_note"):
                p = doc.add_paragraph()
                run = p.add_run("Career Note: ")
                run.bold = True
                p.add_run(job["career_note"])

    # --- Certifications ---
    certifications = resume_data.get("CERTIFICATIONS", [])
    if certifications:
        doc.add_heading(resume_data.get("SECTION_CERTIFICATIONS", "Training & Certifications"), level=1)
        for cert in certifications:
            cert_parts = [p for p in (cert.get("title", ""), cert.get("org", ""), cert.get("year", "")) if p]
            doc.add_paragraph(" | ".join(cert_parts))

    # --- Education ---
    education = resume_data.get("EDUCATION", [])
    if education:
        doc.add_heading(resume_data.get("SECTION_EDUCATION", "Education"), level=1)
        for edu in education:
            meta_parts = [m for m in (edu.get("institution", ""), edu.get("location", ""), edu.get("year", "")) if m]
            p = doc.add_paragraph()
            degree = edu.get("degree", "")
            if degree:
                run = p.add_run(degree)
                run.bold = True
            if meta_parts:
                meta_text = " | ".join(meta_parts)
                p.add_run(f" | {meta_text}" if degree else meta_text)
            if edu.get("description"):
                doc.add_paragraph(edu["description"])
            for bullet in edu.get("bullets", []):
                doc.add_paragraph(bullet, style="List Bullet")

    # --- Why (optional) ---
    why_text = resume_data.get("WHY_TEXT", "")
    if not _is_blank_or_null(why_text):
        section_why = resume_data.get("SECTION_WHY", "")
        heading = section_why if not _is_blank_or_null(section_why) else "Additional Relevant Experience"
        doc.add_heading(heading, level=1)
        # WHY_TEXT contains literal <p>/<em> tags (see render_html.py's
        # build_why_html() comment) -- split into paragraphs on </p> and
        # strip the tags, rather than collapsing everything into one run.
        raw_paragraphs = [rp for rp in why_text.split("</p>") if rp.strip()]
        for raw_p in raw_paragraphs:
            clean = re.sub(r"</?p>|</?em>", "", raw_p).strip()
            if clean:
                doc.add_paragraph(clean)

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
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `source .venv/bin/activate && python -m unittest tests.test_render_resume_docx -v`
Expected: PASS (14 tests)

- [ ] **Step 5: Commit**

```bash
git add scripts/render_resume_docx.py tests/test_render_resume_docx.py
git commit -m "feat(resume): add ATS-optimized DOCX renderer (Group C, part 2/4)"
```

---

## Task 3: Wire cover-letter DOCX export into `orchestrator.py`

**Files:**
- Modify: `scripts/orchestrator.py:38` (imports), `scripts/orchestrator.py:1168` (new `output_docx_dir`), `scripts/orchestrator.py:2853-2857` (hook point)
- Create: `tests/test_orchestrator_docx_export.py`

**Interfaces:**
- Consumes: `render_coverletter_docx` from Task 1.
- Produces: `self.output_docx_dir` on `ResumeEngine`, consumed by Task 4.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_orchestrator_docx_export.py`:

```python
import json
import os
import sys
import unittest
from unittest.mock import MagicMock, patch

SCRIPTS_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts")
sys.path.insert(0, SCRIPTS_DIR)

import orchestrator  # noqa: E402


class TestCoverLetterDocxExport(unittest.TestCase):
    """Group C: build_tailored_coverletter() must call
    render_coverletter_docx() after its PDF subprocess succeeds, and a
    DOCX-generation failure must block the build the same way a PDF
    failure does."""

    def setUp(self):
        self.engine = orchestrator.ResumeEngine()
        self.jd_path = os.path.join(os.path.dirname(__file__), "_tmp_jd_coverletter_docx_export.json")
        with open(self.jd_path, "w", encoding="utf-8") as f:
            json.dump({
                "job_title": "Content Strategist",
                "company_name": "Acme Corp",
                "description": "We are hiring a Content Strategist.",
            }, f)

        self.stem = orchestrator._build_output_stem(self.jd_path)
        self.json_out = os.path.join(self.engine.output_json_dir, f"{self.stem}_CoverLetter.json")
        self.html_out = os.path.join(self.engine.output_html_dir, f"{self.stem}_CoverLetter.html")

    def tearDown(self):
        for path in (self.jd_path, self.json_out, self.html_out):
            if os.path.exists(path):
                os.remove(path)

    def _clean_letter_json(self):
        return json.dumps({
            "company_name": "Acme Corp",
            "greeting": "Dear Acme Corp Hiring Team,",
            "contact_name": "",
            "contact_title": "",
            "body_paragraphs": [
                "I'm excited to apply for this role at Acme Corp.",
                "My background lines up well with what you need.",
            ],
            "sign_off": "Sincerely,",
        })

    @patch.object(orchestrator.ResumeEngine, "research_company", return_value=None)
    @patch("orchestrator.GeminiClient.generate")
    @patch("orchestrator.render_coverletter_docx")
    def test_docx_is_rendered_after_pdf_succeeds(self, mock_render_docx, mock_generate, mock_research):
        mock_generate.return_value = (self._clean_letter_json(), {})
        with patch("orchestrator.subprocess.run", return_value=MagicMock(returncode=0, stdout="", stderr="")), \
             patch("orchestrator.render_coverletter"), \
             patch("orchestrator.validate_pdf_text.validate_coverletter_pdf_text", return_value=[]):
            result = self.engine.build_tailored_coverletter(self.jd_path)

        self.assertTrue(result)
        mock_render_docx.assert_called_once()
        called_data, called_path = mock_render_docx.call_args[0]
        self.assertTrue(called_path.endswith(".docx"))
        self.assertIn(os.path.join(orchestrator.profile_paths.output_dir(), "docx"), called_path)
        self.assertEqual(called_data.get("company_name"), "Acme Corp")

    @patch.object(orchestrator.ResumeEngine, "research_company", return_value=None)
    @patch("orchestrator.GeminiClient.generate")
    @patch("orchestrator.render_coverletter_docx", side_effect=Exception("docx boom"))
    def test_docx_failure_blocks_the_build_like_a_pdf_failure_does(
        self, mock_render_docx, mock_generate, mock_research
    ):
        mock_generate.return_value = (self._clean_letter_json(), {})
        with patch("orchestrator.subprocess.run", return_value=MagicMock(returncode=0, stdout="", stderr="")), \
             patch("orchestrator.render_coverletter"), \
             patch("orchestrator.validate_pdf_text.validate_coverletter_pdf_text", return_value=[]):
            result = self.engine.build_tailored_coverletter(self.jd_path)

        self.assertEqual(result, {})


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `source .venv/bin/activate && python -m unittest tests.test_orchestrator_docx_export.TestCoverLetterDocxExport -v`
Expected: FAIL — `AttributeError: <module 'orchestrator' ...> does not have the attribute 'render_coverletter_docx'` (the `@patch("orchestrator.render_coverletter_docx")` target doesn't exist yet)

- [ ] **Step 3: Wire it into `orchestrator.py`**

In `scripts/orchestrator.py`, at line 38, change:

```python
from render_coverletter import render_coverletter
```

to:

```python
from render_coverletter import render_coverletter
from render_coverletter_docx import render_coverletter_docx
```

At line 1168, change:

```python
        self.output_pdf_dir  = os.path.join(profile_paths.output_dir(), "pdf")
```

to:

```python
        self.output_pdf_dir  = os.path.join(profile_paths.output_dir(), "pdf")
        self.output_docx_dir = os.path.join(profile_paths.output_dir(), "docx")
```

At line 2857 (right after `cli_art.print_subprocess_output(pdf_result.stdout)` in `build_tailored_coverletter()`), insert:

```python
        cli_art.print_subprocess_output(pdf_result.stdout)

        docx_out = os.path.join(self.output_docx_dir, f"{stem}_CoverLetter.docx")
        try:
            render_coverletter_docx(letter_data, docx_out)
        except Exception as e:
            cli_art.friendly_error(e, "creating the DOCX for this cover letter")
            return {}

        cl_text_warnings = validate_pdf_text.validate_coverletter_pdf_text(pdf_out, letter_data, jd_keywords=jd_keywords)
```

(This replaces the existing two-line sequence — `cli_art.print_subprocess_output(pdf_result.stdout)` immediately followed by the `cl_text_warnings = ...` line — with the same two lines plus the new DOCX block in between.)

- [ ] **Step 4: Run tests to verify they pass**

Run: `source .venv/bin/activate && python -m unittest tests.test_orchestrator_docx_export.TestCoverLetterDocxExport -v`
Expected: PASS (2 tests)

Then run the full cover-letter-related regression files to confirm no existing behavior broke:

Run: `source .venv/bin/activate && python -m unittest tests.test_orchestrator_coverletter_enrichment tests.test_orchestrator_coverletter_injection tests.test_cli_coverletter_pick -v`
Expected: PASS (all existing tests)

- [ ] **Step 5: Commit**

```bash
git add scripts/orchestrator.py tests/test_orchestrator_docx_export.py
git commit -m "feat(coverletter): wire DOCX export into build_tailored_coverletter() (Group C, part 3/4)"
```

---

## Task 4: Wire resume DOCX export into `orchestrator.py`

**Files:**
- Modify: `scripts/orchestrator.py:38` (imports), `scripts/orchestrator.py:3780` (hook point)
- Modify: `tests/test_orchestrator_docx_export.py` (add `TestResumeDocxExport`)

**Interfaces:**
- Consumes: `render_resume_docx` from Task 2, `self.output_docx_dir` from Task 3.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_orchestrator_docx_export.py` (add these imports to the top of the file alongside the existing ones, and this class at the bottom):

Add to the top imports:

```python
import contextlib
import io
import re
```

(full updated import block at the top of the file):

```python
import contextlib
import io
import json
import os
import re
import sys
import unittest
from unittest.mock import MagicMock, patch

SCRIPTS_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts")
sys.path.insert(0, SCRIPTS_DIR)

import orchestrator  # noqa: E402
import jd_manager  # noqa: E402
```

Append this class to the end of the file (before the `if __name__ == "__main__":` block, or after it — Python doesn't care, but keep `if __name__ == "__main__": unittest.main()` as the last thing in the file):

```python
def _pass_critique_json():
    return json.dumps({
        "manager_test": "PASS",
        "believability_score": 95,
        "hidden_gem_score": 10,
        "hidden_gem_flag": False,
        "hidden_gem_reason": "",
        "weaknesses": "",
    })


class TestResumeDocxExport(unittest.TestCase):
    """Group C: build_tailored_resume() must call render_resume_docx() with
    the FINAL (post-trim-loop) resume_data, after the PDF text-layer check
    passes -- not from inside the trim-retry loop, where resume_data is
    still mutating. A DOCX-generation failure must block the build the same
    way a PDF failure does."""

    def setUp(self):
        self._roster_patch = patch("orchestrator._required_role_roster", return_value=[])
        self._roster_patch.start()
        self.addCleanup(self._roster_patch.stop)

        def _regex_parse_pdf_result(stdout, pdf_path=None):
            m = re.search(r"Pages:\s*(\d+)", stdout)
            page_count = int(m.group(1)) if m else None
            sm = re.search(r"Size:\s*([\d.]+\s*\w+)", stdout)
            size_str = sm.group(1) if sm else "unknown size"
            return page_count, size_str

        self._parse_pdf_patch = patch("orchestrator._parse_pdf_result", side_effect=_regex_parse_pdf_result)
        self._parse_pdf_patch.start()
        self.addCleanup(self._parse_pdf_patch.stop)

        self._validate_pdf_text_patch = patch(
            "orchestrator.validate_pdf_text.validate_pdf_text", return_value=([], [])
        )
        self._validate_pdf_text_patch.start()
        self.addCleanup(self._validate_pdf_text_patch.stop)

        real_exists = os.path.exists

        def _fake_exists(path):
            if str(path).endswith(".pdf"):
                return True
            return real_exists(path)

        self._pdf_exists_patch = patch("orchestrator.os.path.exists", side_effect=_fake_exists)
        self._pdf_exists_patch.start()
        self.addCleanup(self._pdf_exists_patch.stop)

        self._research_patch = patch.object(
            orchestrator.ResumeEngine, "research_company", return_value=None
        )
        self._research_patch.start()
        self.addCleanup(self._research_patch.stop)

        self.engine = orchestrator.ResumeEngine()
        self.jd_path = os.path.join(os.path.dirname(__file__), "_tmp_jd_for_docx_export.txt")
        with open(self.jd_path, "w", encoding="utf-8") as f:
            f.write("We are hiring a Widget Engineer.")
        self.job_key = "test-docx-export-job"
        self.output_filename = "TESTONLY_docx_export_resume.json"
        self.output_path = os.path.join(self.engine.output_json_dir, self.output_filename)

        jd_manager.save_checkpoint(self.job_key, {
            "jd_keywords": {"hard_skills": ["python"]},
            "bullet_tuples": [["Shipped a widget platform used by 10k users.", "Acme", "eng"]],
        })

    def tearDown(self):
        if os.path.exists(self.jd_path):
            os.remove(self.jd_path)
        if os.path.exists(self.output_path):
            os.remove(self.output_path)
        jd_manager.delete_checkpoint(self.job_key)

    def _generate_side_effect(self, *args, **kwargs):
        schema = kwargs.get("response_schema")
        if schema is orchestrator.CritiqueSchema:
            return (_pass_critique_json(), {})
        if schema is orchestrator.TemplateSchema:
            return (json.dumps({"SUMMARY": "Test summary."}), {})
        if schema is orchestrator.ResumeCritiqueSchema:
            return (json.dumps({
                "summary_alignment_score": 90,
                "skills_relevance_score": 90,
                "overall_fit_score": 90,
                "flags": [],
                "recommendations": [],
            }), {})
        raise AssertionError(f"Unexpected response_schema in test: {schema}")

    @patch("orchestrator.subprocess.run")
    @patch("orchestrator.render_html")
    @patch("orchestrator.render_resume_docx")
    @patch("orchestrator.GeminiClient.generate")
    @patch("orchestrator.time.sleep", lambda *a, **kw: None)
    def test_docx_is_rendered_with_final_resume_data_after_a_successful_build(
        self, mock_generate, mock_render_docx, mock_render_html, mock_subprocess_run
    ):
        mock_generate.side_effect = self._generate_side_effect
        mock_subprocess_run.return_value = MagicMock(returncode=0, stdout="📊 Pages: 2\n", stderr="")

        stdout_buf = io.StringIO()
        with patch.object(self.engine, "mine_bullet_bank"), \
                contextlib.redirect_stdout(stdout_buf):
            result = self.engine.build_tailored_resume(
                jd_path=self.jd_path,
                master_resume={},
                output_filename=self.output_filename,
                job_key=self.job_key,
            )

        self.assertTrue(result)
        mock_render_docx.assert_called_once()
        called_data, called_path = mock_render_docx.call_args[0]
        self.assertTrue(called_path.endswith(".docx"))
        self.assertIn(os.path.join(orchestrator.profile_paths.output_dir(), "docx"), called_path)
        self.assertIsInstance(called_data, dict)
        # This fixture's PDF mock reports 2 pages on the first pass, so the
        # trim-retry loop exits immediately without mutating resume_data --
        # it doesn't exercise the "stale vs. final data" risk the spec
        # flagged (that risk is about code placement: the docx call must
        # sit after the loop, which is what this test's mock ordering
        # confirms). The loop's own mutation behavior across multiple trim
        # iterations already has dedicated coverage in
        # tests/test_orchestrator_build_checkpoint.py.
        self.assertEqual(mock_render_html.call_count, 1)

    @patch("orchestrator.subprocess.run")
    @patch("orchestrator.render_html")
    @patch("orchestrator.render_resume_docx", side_effect=Exception("docx boom"))
    @patch("orchestrator.GeminiClient.generate")
    @patch("orchestrator.time.sleep", lambda *a, **kw: None)
    def test_docx_failure_blocks_the_build_like_a_pdf_failure_does(
        self, mock_generate, mock_render_docx, mock_render_html, mock_subprocess_run
    ):
        mock_generate.side_effect = self._generate_side_effect
        mock_subprocess_run.return_value = MagicMock(returncode=0, stdout="📊 Pages: 2\n", stderr="")

        stdout_buf = io.StringIO()
        with patch.object(self.engine, "mine_bullet_bank"), \
                contextlib.redirect_stdout(stdout_buf):
            result = self.engine.build_tailored_resume(
                jd_path=self.jd_path,
                master_resume={},
                output_filename=self.output_filename,
                job_key=self.job_key,
            )

        self.assertFalse(result)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `source .venv/bin/activate && python -m unittest tests.test_orchestrator_docx_export.TestResumeDocxExport -v`
Expected: FAIL — `AttributeError: <module 'orchestrator' ...> does not have the attribute 'render_resume_docx'`

- [ ] **Step 3: Wire it into `orchestrator.py`**

At line 38 (now line 39 after Task 3's import addition), change:

```python
from render_coverletter_docx import render_coverletter_docx
```

to:

```python
from render_coverletter_docx import render_coverletter_docx
from render_resume_docx import render_resume_docx
```

In `build_tailored_resume()`, find the end of the PDF text-layer check block:

```python
        if pdf_text_warnings:
            cli_art.console.print(f"  {theme.colorize_icon('warning')} PDF text-layer check found {len(pdf_text_warnings)} potential issue(s) "
                  f"(what an ATS would actually parse from the file, not just the pre-render JSON):", soft_wrap=True)
            from rich.text import Text
            for w in pdf_text_warnings:
                msg = Text("    - ")
                msg.append(str(w))
                cli_art.console.print(msg)
        else:
            cli_art.console.print(f"  {theme.colorize_icon('success')} PDF text-layer check: 0 issues.", soft_wrap=True)
```

and insert immediately after the `else:` block closes (before the `# B18 (phase-9-backlog.md): reported before the pipeline claims` comment that follows it):

```python
        else:
            cli_art.console.print(f"  {theme.colorize_icon('success')} PDF text-layer check: 0 issues.", soft_wrap=True)

        docx_out = os.path.join(self.output_docx_dir, f"{stem}_Resume.docx")
        try:
            render_resume_docx(resume_data, docx_out)
        except Exception as e:
            cli_art.friendly_error(e, "creating the DOCX for this resume")
            return {}

        # B18 (phase-9-backlog.md): reported before the pipeline claims
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `source .venv/bin/activate && python -m unittest tests.test_orchestrator_docx_export -v`
Expected: PASS (4 tests total: `TestCoverLetterDocxExport` x2, `TestResumeDocxExport` x2)

Then run the full suite to confirm nothing regressed:

Run: `source .venv/bin/activate && python -m unittest discover -s tests -v 2>&1 | tail -20`
Expected: `OK`, no failures

- [ ] **Step 5: Commit**

```bash
git add scripts/orchestrator.py tests/test_orchestrator_docx_export.py
git commit -m "feat(resume): wire DOCX export into build_tailored_resume() (Group C, part 4/4)"
```

---

## Post-implementation

Update `docs/superpowers/plans/2026-08-17-cover-letter-blueprint-roadmap.md`'s Group C entry from "not started" to complete, following the same write-up style as the Group A/B entries (what shipped, any gotchas hit, final test count).
