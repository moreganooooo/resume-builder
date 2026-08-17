# DOCX Exporter Design

**Status**: Approved, ready for implementation planning
**Part of**: Group C, `docs/superpowers/plans/2026-08-17-cover-letter-blueprint-roadmap.md` (Feature #3)
**Author**: Claude (brainstorming session), approved by Morgan 2026-08-17

## Why

Feature #3 of the cover-letter blueprint cites Taleo/Workday's ~97% DOCX parse
rate vs. PDF's less reliable text-layer extraction — the motivation is ATS
parsing reliability, not visual richness. No DOCX *write* path exists
anywhere in this repo today; `python-docx` (already a dependency, declared in
`requirements.txt`) is currently used only to *read* uploaded resumes
(`scripts/bootstrap_extractors.py::_extract_docx_text()`), a shallow
text-extraction call that has no bearing on how to *build* a document.

## Scope

Both resume and cover letter get a DOCX export, generated automatically on
every build (not behind a flag), alongside the existing JSON/HTML/PDF
artifacts. ATS-optimized fidelity — not a visual match to the PDF.

## Architecture

Two new sibling renderer modules, following the repo's existing
per-document-type-per-format convention (`render_html.py` = resume/HTML,
`render_coverletter.py` = cover letter/HTML, `render_typst.py` =
resume/Typst, currently dormant — see Note on Typst below):

- `scripts/render_resume_docx.py`
  `render_resume_docx(resume_data: dict, output_path: str) -> str`
- `scripts/render_coverletter_docx.py`
  `render_coverletter_docx(cover_letter_data: dict, output_path: str) -> str`

Both consume the *exact same* dicts the existing HTML renderers already
consume — no new schema, no extra LLM call, no template file. `python-docx`
builds the document programmatically (`doc.add_heading()`,
`doc.add_paragraph()`, `doc.add_paragraph(style="List Bullet")`) rather than
filling a template — docx has no HTML-style string-replace templating story,
and matching `render_html.py`'s token-substitution approach would mean
maintaining a `.docx` template file as a second source of truth for the same
content structure.

**Note on Typst**: `render_typst.py` exists and is fully tested
(`tests/test_render_typst.py`) but is not called from `orchestrator.py`
anywhere — greping the codebase for `render_typst` outside its own file and
tests turns up nothing. The actual production resume renderer is
`render_html.py` → `generate-pdf.mjs` (Playwright), same pipeline shape as
the cover letter. This spec treats `render_html.py`/`render_coverletter.py`
as the source-of-truth field schemas, not Typst — Typst integration is out
of scope here and untouched by this change.

## Data → content mapping

### Resume (`render_resume_docx.py`)

Reads the same uppercase-keyed `resume_data` dict as `render_html.py`
(`scripts/render_html.py:231-247` for the exact key list). Section order
mirrors the HTML template:

| Section | Source field(s) | DOCX treatment |
|---|---|---|
| Header | `NAME`, `TAGLINE`, `PHONE`, `EMAIL`, `LINKEDIN_DISPLAY`, `LOCATION` | Title-style heading + one contact line, pipe-separated |
| Summary | `SECTION_SUMMARY` (heading label), `SUMMARY_TEXT` | Heading 2 + one paragraph. `SUMMARY_TEXT` contains a literal `<strong>` around its first sentence (HTML convention) — strip the tag and apply `run.bold = True` to that sentence instead of leaving markup in the text |
| Skills | `SECTION_SKILLS`, `SKILLS` (list of strings, each `"**Category:** Item, Item"` markdown-bold) | Heading 2 + one paragraph per skill line; convert `**text**` to a bold run, matching `build_skills_html()`'s regex behavior |
| Experience | `SECTION_EXPERIENCE`, `EXPERIENCE` (list of dicts: `title`, `company`, `size_revenue`, `location`, `period`, `achievements`, `career_note`, `clients`) | Heading 2, then per job: bold job title paragraph, a meta line (company + optional size/revenue parenthetical, location, period — pipe-separated, matching `build_experience_html()`), optional "Clients:" line, bulleted achievements (`List Bullet` style), optional "Career Note:" line |
| Certifications | `SECTION_CERTIFICATIONS`, `CERTIFICATIONS` (list of dicts: `title`, `org`, `year`) | Heading 2 + one pipe-separated line per cert |
| Education | `SECTION_EDUCATION`, `EDUCATION` (list of dicts: `degree`, `institution`, `location`, `year`, `description`, `bullets`) | Heading 2, then per entry: degree + pipe-separated meta line, optional description paragraph, optional bulleted list |
| Why (optional) | `SECTION_WHY`, `WHY_TEXT` | Heading 2 + paragraph, **omitted entirely** when `WHY_TEXT` is blank or the literal string `"null"` (case/whitespace-insensitive) — same drop-the-whole-section rule as `build_why_html()` |

No signature/decorative elements — resume has none in the HTML version
either.

### Cover letter (`render_coverletter_docx.py`)

Reads the same lowercase-keyed `cover_letter_data` dict as
`render_coverletter.py` (`scripts/render_coverletter.py:81-96` for the exact
key list), plus `profile_paths.fixed_content_module().CONTACT_INFO` for the
sender's own contact block (same source `render_coverletter.py` uses).

| Section | Source field(s) | DOCX treatment |
|---|---|---|
| Header | `contact["NAME"]`, `PHONE`, `EMAIL`, `LINKEDIN_DISPLAY`, `LOCATION` | Same header treatment as the resume |
| Date | today's date, `%B %-d, %Y` | One paragraph |
| Recipient block | `company_name`, `contact_name`, `contact_title`, `company_location` | Up to 3 lines, same "Attn: X, title" / company / location logic as `build_recipient_block_html()`, one paragraph per line (no `<br>` — DOCX paragraphs are already line-separated) |
| Greeting | `greeting` | One paragraph |
| Body | `body_paragraphs` (list of strings) | One paragraph per list item |
| Sign-off | `sign_off`, `contact["NAME"]`, `contact["EMAIL"]`/`PHONE` | Sign-off line, then typed name, then contact line |

**No embedded signature image** — per the ATS-optimized fidelity call, the
signature is decorative and a raster image adds fragility (file-path
resolution, missing-signature handling) for zero ATS parsing benefit. Typed
name only, matching what `build_signature_block_html()` degrades to anyway
when a profile has no `signature.png`.

## Hook point in `orchestrator.py`

New `self.output_docx_dir = os.path.join(profile_paths.output_dir(), "docx")`
next to the existing `output_json_dir`/`output_html_dir`/`output_pdf_dir`
(`orchestrator.py:1166-1170`), created with the same `os.makedirs(...,
exist_ok=True)` pattern.

- **Resume**: `resume_data` mutates across `build_tailored_resume()`'s Step 7
  trim-retry `while True` loop (optional-client-roster drop, Why-section
  drop, LLM trim edits — `orchestrator.py:3643-3746`), which only exits once
  `is_final` is true or a fatal condition returns `{}` early. Generating the
  DOCX from the first successful PDF pass (inside the loop) would capture
  pre-trim content that no longer matches the final, possibly-shorter PDF.
  Call `render_resume_docx()` **after the loop and its post-loop
  `pdf_fatal`/`pdf_text_warnings` check both pass** (`orchestrator.py`
  ~line 3780, right before whatever currently follows to mark the build
  complete), using the final `resume_data` and `pdf_out` at that point.
  Output: `{stem}_Resume.docx`.
- **Cover letter**: called in `build_tailored_coverletter()`, immediately
  after its PDF subprocess succeeds (`orchestrator.py` ~line 2853-2857).
  Output: `{stem}_CoverLetter.docx`.

## Error handling

Blocks the build, same as an existing PDF failure: wrap the `python-docx`
call in `try/except`, on failure call
`cli_art.friendly_subprocess_error`-style messaging (or a comparable
`cli_art.console.print` warning if the failure isn't a subprocess — it's an
in-process library call, not a subprocess, so the exact error surface will
be a caught `Exception` rather than a `subprocess.CalledProcessError`) and
`return {}`, matching the existing "PDF generation timed out" /
"`pdf_result.returncode != 0`" early-return shape immediately above it. A JD
is not marked complete unless all four artifacts (JSON, HTML, PDF, DOCX)
exist.

## Testing

- `tests/test_render_resume_docx.py` — build a `resume_data` fixture
  covering every optional field (Why section present and absent, a job with
  `career_note`/`clients`, an education entry with/without `bullets`), call
  `render_resume_docx()`, then read the result back with `docx.Document()`
  and assert each section's text is present in the right order, and that
  Why is fully absent (no heading, no paragraph) when blank/`"null"`.
- `tests/test_render_coverletter_docx.py` — same read-back approach for the
  cover letter fixture (with/without `contact_name`, with/without
  `company_location`), and assert no embedded image part exists in the
  `.docx` (confirms the no-signature decision).
- Two new orchestrator integration tests (in the existing
  `test_orchestrator_*` files, following whatever pattern the current PDF
  success/failure tests use): a normal build produces a `.docx` file at the
  expected path, and a forced `render_*_docx()` exception blocks the build
  the same way a forced PDF failure does (`return {}`, no completion).

## Out of scope

- Typst integration (dormant, untouched).
- Visual/style parity with the PDF templates.
- A CLI flag to opt in/out of DOCX generation (always-on, per this design).
- Resume DOCX support for anything beyond the fields `render_html.py`
  already handles (no new resume content).
