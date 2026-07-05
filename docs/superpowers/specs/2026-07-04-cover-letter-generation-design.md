# Cover Letter Generation (no company research yet) — Design

## Problem

`resume-engine/templates/coverletter-template.html` is a fully built template
(`{{DATE}}`, `{{RECIPIENT_BLOCK}}`, `{{GREETING}}`, `{{BODY_PARAGRAPHS}}`,
`{{SIGN_OFF}}`, `{{TYPED_NAME}}`, `{{TYPED_CONTACT}}`) with nothing wired to
it — no prompt fills it, nothing in `orchestrator.py` calls it. Morgan wants a
matching cover letter alongside the resume, generated from the same JD input.

Company research (career-ops's WebFetch/WebSearch-driven company research,
used for the "Company Connection" paragraph and tone-matching) is explicitly
**out of scope for this pass** — sequenced as a second, later pass per
Morgan's own call (2026-07-04): ship the letter working on JD + background
context alone first, layer research in afterward. IDEAS.md's "architecture
mismatch" note (career-ops assumes a live agent with tool-use; this pipeline
is a headless Gemini-API script) applies to that second pass, not this one.

## Goals

1. `resume coverletter <jd_file>` produces a rendered PDF cover letter for a
   single JD, independent of whether a resume has been tailored for that JD.
2. First-person throughout (inverted from the resume's pronoun-free-except-Why
   rule), 2-3 body paragraphs tying specific JD facts to Morgan's real
   background — no fabricated company research, no fake flattery.
3. A lightweight, dedicated validator: forbidden phrases (reusing
   `style_rules.yaml`), paragraph count, and stray third-person self-reference
   detection. One automatic retry with violations fed back on failure.
4. Reuse everything that already exists: the background-context helpers
   already on `ResumeEngine`, `style_rules.yaml`'s forbidden-phrases list, the
   render-template-fill pattern from `render_html.py`, and
   `generate-pdf.mjs` unchanged.

## Non-Goals

- Company research / "Company Connection" paragraph (next pass).
- Company-values tone-mirroring in the resume itself (IDEAS.md item #6,
  blocked on the same research step — not this pass).
- Page-fit trimming loop, per-role bullet allocation, skills-line-wrap
  validation, opening-verb uniqueness — none of these apply to a cover
  letter; the resume pipeline's heavier validator is not reused wholesale.
- Wiring into `jd_tracker_log.csv` / `data/applications.md` — a cover letter
  is a companion artifact to an already-tracked resume, not its own tracked
  event, for this pass.
- The signature image (`docs/MorganEscottSignature2025.png`) — doesn't exist
  yet; Morgan will provide it separately. The template keeps its `<img>` tag
  as-is; rendering will show a broken image until the file exists, which does
  not block anything else in this design.

## Architecture

```
JD file → ResumeEngine.build_tailored_coverletter(jd_path)
  → reuses existing background-context helpers (persona_context,
    get_verified_claims_text, build_background_summary) -- no new
    bullet-retrieval logic
  → one Gemini call: tailor_coverletter.md (new prompt) + JD text +
    background context → structured CoverLetterSchema output
  → validate_coverletter.py checks the result
      violations found → ONE automatic retry, violations fed back to the
      model (same pattern as the resume pipeline's fix loop, capped at 1
      attempt instead of 4 -- much smaller failure surface)
      still has violations after retry → proceed anyway, print them as
      warnings (this pass doesn't block on them)
  → render_coverletter.py fills coverletter-template.html (DATE, TYPED_NAME,
    TYPED_CONTACT, and header contact fields come from fixed_content.py /
    Python -- not model-generated)
  → node generate-pdf.mjs <html> <pdf> --format=letter (unchanged, already
    generic)
```

## Components

- **`resume-engine/prompts/tailor_coverletter.md`** (new) — system prompt:
  first-person, a greeting, 2-3 body paragraphs using JD text + background
  context (no live research), a sign-off. References the same archetype
  framing `tailor_resume.md` uses, but as an independent prompt file (no
  shared code between the two prompts).

- **`CoverLetterSchema`** (new Pydantic model, added alongside the existing
  schemas in `orchestrator.py`):
  ```python
  class CoverLetterSchema(BaseModel):
      company_name:    str
      greeting:        str
      body_paragraphs: List[str]   # 2-3 items
      sign_off:        str
  ```

- **`ResumeEngine.build_tailored_coverletter(jd_path, job_key=None) -> dict`**
  (new method on the existing class) — mirrors `build_tailored_resume`'s
  shape but much shorter: no checkpointing (one cheap call + at most one
  retry, not a multi-step pipeline worth resuming mid-way). Returns the
  filled `CoverLetterSchema` dict plus `_output_paths` (json/html/pdf), or
  `{}` on failure.

- **`scripts/validate_coverletter.py`** (new) — mirrors `validate_resume.py`
  conventions:
  - `_check_forbidden_phrases` — reuses `style_rules.yaml`'s existing
    `forbidden_phrases` list verbatim (same word-boundary regex approach),
    checked across greeting/body_paragraphs/sign_off.
  - `_check_paragraph_count` — 2-3 body paragraphs.
  - `_check_third_person_slip` — flags stray self-referential third-person
    ("Morgan Escott", "Morgan", standalone "she"/"her") anywhere in the
    letter; this is the *inverse* of `_check_pronouns_outside_why` (which
    enforces pronoun-free everywhere but the Why section on the resume) —
    here the letter should be first-person ("I") throughout.
  - `validate(cover_letter_data, style_rules) -> list[str]` — same shape as
    `validate_resume.py`'s top-level `validate()`, returns a flat list of
    violation strings.

- **`scripts/render_coverletter.py`** (new) — mirrors `render_html.py`'s
  fill-template pattern (read template, scalar-token replace, block-token
  replace for `RECIPIENT_BLOCK`). `RECIPIENT_BLOCK` is built in Python from
  `company_name`, never raw HTML from the model:
  `<div class="letter-recipient">{company_name}</div>`. The template has no
  `.letter-recipient` CSS rule yet — this design includes adding one
  (matching `.letter-date`'s existing margin/spacing, so it doesn't need new
  visual design work, just a small CSS addition to
  `coverletter-template.html`).

- **`cli.py`**: new `resume coverletter <jd_file>` command (standalone,
  opt-in — not part of `tailor`/`run`), calling
  `ResumeEngine.build_tailored_coverletter` then the render/PDF steps.

## Data Flow

```
resume coverletter jds/some_jd.json
  → load JD text (jd_manager, same as tailor)
  → engine.build_tailored_coverletter(jd_path)
      → background context via existing ResumeEngine helpers
      → Gemini call #1 → CoverLetterSchema
      → validate_coverletter.validate(...)
          if violations: Gemini call #2 (retry, violations in prompt)
          re-validate once more, log any remaining violations as warnings
      → render_coverletter.render(...) → HTML
      → subprocess: node generate-pdf.mjs → PDF
  → print output paths (json/html/pdf), same style as `resume tailor`
```

## Output Layout

Reuses the existing `output/json/`, `output/html/`, `output/pdf/` folders
with a `_coverletter` suffix, not new folders:

```
output/json/<jd_stem>_coverletter.json
output/html/<jd_stem>_coverletter.html
output/pdf/<jd_stem>_coverletter.pdf
```

No changes to `jds/` intake, completion-moving, or tracker/`applications.md`
behavior — `resume coverletter` doesn't move the JD file or write tracker
rows; it's a side artifact, not a pipeline completion event.

## Error Handling

- JD file not found / unreadable → same pattern as `build_tailored_resume`:
  print an error, return `{}`, CLI exits nonzero.
- Gemini call fails to parse (`GeminiClient.parse_json` returns `{}`) on both
  the initial attempt and the retry → print an error, return `{}`.
- PDF generation subprocess failure → print stderr, return `{}` (matches
  `build_tailored_resume`'s existing handling of `generate-pdf.mjs` failures).
- Validator violations that persist after the one retry are non-fatal:
  logged as warnings, the PDF still gets built. (Explicit scope choice —
  see Goals/Non-Goals: this pass doesn't block on validator output.)

## Testing

- Unit tests (no real Gemini calls, fixtures/mocked model output):
  - `validate_coverletter.validate()`: forbidden-phrase hit, paragraph count
    outside 2-3, a third-person slip ("Morgan has experience..." instead of
    "I have experience...") — each should produce exactly the expected
    violation string; a clean, first-person 2-3-paragraph letter should
    produce `[]`.
  - `render_coverletter`: given a fixed `CoverLetterSchema`-shaped dict,
    confirm every `{{TOKEN}}` in the template gets replaced (no literal
    `{{...}}` left in the output HTML) and `RECIPIENT_BLOCK` contains the
    given company name.
- Manual end-to-end check (real Gemini + real PDF, like the recent
  `resume tailor` smoke test): run `resume coverletter` against the same
  `dummy_jd.txt`-derived fixture, confirm a PDF is produced, confirm it reads
  first-person throughout, confirm the validator ran (check console output
  for either "no violations" or a warning list).
