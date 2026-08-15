# Cover Letter Header/Address Enrichment Implementation Plan

> **For agentic workers:** Execute task-by-task with `- [ ]` checkboxes.
> No subagent dispatch for this plan (explicit user preference — Pro plan
> usage budget) — execute inline in this session.

**Goal:** Cover letters pull the matching resume's title line, show a
company address block (contact/company/location), and open with a
grounded, impressive company fact — all from data this pipeline already
gathers, no new Gemini calls.

**Architecture:** Two Pydantic schemas (`CompanyResearchSchema`,
`CoverLetterSchema`) each gain 1-2 optional fields, riding calls that
already happen. Three new deterministic Python helpers in `orchestrator.py`
resolve location/contact/tagline without any model involvement. A
`render_coverletter.py` template function grows from a single company-name
line into a 3-line address block.

**Tech Stack:** Python 3.10+, Pydantic (`BaseModel`/`Field`), stdlib
`unittest`.

## Global Constraints
- Spec: `docs/superpowers/specs/2026-08-12-coverletter-header-enrichment-design.md`
- No new Gemini calls — every addition rides an existing call or is
  resolved deterministically in Python.
- No web search for a named contact — JD text + already-scraped
  `find_jd_contacts()` only.
- Company location is shown whenever known, regardless of remote/on-site
  status — no filtering.
- Every new company-research field must be grounded in source text, never
  invented (same discipline as existing `company_facts`).
- Run from repo root with `.venv/` activated:
  `python -m unittest discover -s tests -v`.

---

### Task 1: `CompanyResearchSchema` gains `company_hq_location` + `notable_highlights`

**Files:**
- Modify: `scripts/orchestrator.py:943-953` (`CompanyResearchSchema`), `scripts/orchestrator.py:1028-1053` (`format_company_research_block`)
- Modify: `resume-engine/prompts/research_company.md`
- Test: `tests/test_orchestrator_research_block.py`

**Interfaces:**
- Produces: `CompanyResearchSchema.company_hq_location: str` (default `""`), `CompanyResearchSchema.notable_highlights: List[str]` (default `[]`). `format_company_research_block(research: dict) -> str` now also renders a "Notable highlights" line when `research.get("notable_highlights")` is non-empty.

- [ ] **Step 1: Write failing tests**

Add to `tests/test_orchestrator_research_block.py` (inside `TestFormatCompanyResearchBlock`):

```python
    def test_includes_notable_highlights_when_present(self):
        block = orchestrator.format_company_research_block(dict(
            self.BASE, notable_highlights=["Named to Forbes Cloud 100 five years running."]))
        self.assertIn("Notable highlights", block)
        self.assertIn("Forbes Cloud 100", block)

    def test_omits_notable_highlights_line_when_absent(self):
        block = orchestrator.format_company_research_block(dict(self.BASE))
        self.assertNotIn("Notable highlights", block)

    def test_omits_notable_highlights_line_when_empty_list(self):
        block = orchestrator.format_company_research_block(dict(self.BASE, notable_highlights=[]))
        self.assertNotIn("Notable highlights", block)
```

Add a new class at the end of the same file (before `if __name__ ==`):

```python
class TestCompanyResearchSchemaNewFields(unittest.TestCase):

    def test_new_fields_default_to_empty(self):
        model = orchestrator.CompanyResearchSchema(
            overall_tone_adjective="warm", tone_register="conversational",
            pronoun_framing="we-centric", sentence_style="short and punchy",
            jargon_density="low", recurring_keywords=[], company_facts=[],
            vocabulary_substitutions=[],
        )
        self.assertEqual(model.company_hq_location, "")
        self.assertEqual(model.notable_highlights, [])
```

- [ ] **Step 2: Run tests, verify they fail**

Run: `python -m unittest tests.test_orchestrator_research_block -v`
Expected: FAIL — `AttributeError`/`AssertionError` (fields/behavior don't exist yet).

- [ ] **Step 3: Extend the schema**

In `scripts/orchestrator.py`, replace the `CompanyResearchSchema` class (lines 943-953) with:

```python
class CompanyResearchSchema(BaseModel):
    overall_tone_adjective: str       = Field(description="One short phrase describing the company's overall voice.")
    tone_register:          Literal["formal", "conversational", "mixed"]
    pronoun_framing:        Literal["we-centric", "you-centric", "mixed"]
    sentence_style:         Literal["short and punchy", "long and flowing", "mixed"]
    jargon_density:         Literal["high", "moderate", "low"]
    recurring_keywords:     List[str] = Field(description="1-3 brand words/phrases that genuinely repeat in the source text.")
    company_facts:          List[str] = Field(description="2-3 short, factual statements traceable directly to the source text.")
    company_hq_location:    str       = Field(default="", description="The company's headquarters city/state (e.g. 'New York, NY'), only if stated in the source text -- empty string otherwise.")
    notable_highlights:     List[str] = Field(default_factory=list, description="0-3 short, factual, impressive statements -- awards, funding, recognition, charitable/community work, notable stats, or recent/upcoming launches -- each traceable directly to the source text. Empty list if none genuinely qualify.")
    vocabulary_substitutions: List[VocabularySubstitution] = Field(
        description="0-3 generic-term/company-term pairs where the source text clearly and repeatedly prefers its own word over the common one. Empty list if none genuinely qualify."
    )
```

- [ ] **Step 4: Extend `format_company_research_block()`**

In `scripts/orchestrator.py`, in `format_company_research_block` (lines 1028-1053), insert a new highlights section between the `company_facts` block and the `vocabulary_substitutions` block:

```python
    highlights = research.get("notable_highlights") or []
    if highlights:
        block += (
            "\n\nNotable highlights (use at most 1-2, ideal for an opening hook, never fabricate beyond these):\n"
            + "\n".join(f"- {h}" for h in highlights)
        )

    pairs = [
```
(the existing `pairs = [...]` line and everything after it stays unchanged)

- [ ] **Step 5: Run tests, verify they pass**

Run: `python -m unittest tests.test_orchestrator_research_block -v`
Expected: PASS

- [ ] **Step 6: Update the research prompt**

In `resume-engine/prompts/research_company.md`, add two new numbered items after item 8 (`vocabulary_substitutions`) in the Task section:

```markdown
9. **company_hq_location** -- the company's headquarters city and state (e.g. "New York, NY"), only if the provided text states it. Leave as an empty string if not stated -- never guess or infer from context.
10. **notable_highlights** -- 0-3 short, factual, impressive statements about the company: awards, industry rankings, funding milestones, notable stats (e.g. customer count), charitable or community initiatives, or recent/upcoming product launches. Each must be traceable directly to the provided text. Return an empty list when nothing genuinely qualifies; never invent one to fill this field.
```

Update the Rules section's first bullet and the Output section to also cover the two new fields:

```markdown
- Every `company_facts` and `notable_highlights` entry must be grounded in the provided text -- if the text doesn't clearly support a fact, leave it out rather than guessing.
```

```markdown
Respond with the structured company research JSON only: `overall_tone_adjective`, `tone_register`, `pronoun_framing`, `sentence_style`, `jargon_density`, `recurring_keywords` (list), `company_facts` (list of 2-3), `company_hq_location` (string, empty if unknown), `notable_highlights` (list of 0-3), `vocabulary_substitutions` (list of 0-3 `{generic_term, company_term}` objects).
```

- [ ] **Step 7: Commit**

```bash
git add scripts/orchestrator.py resume-engine/prompts/research_company.md tests/test_orchestrator_research_block.py
git commit -m "feat(company-research): add HQ location + notable highlights fields"
```

---

### Task 2: `CoverLetterSchema` gains `contact_name` + `contact_title`; prompt updates

**Files:**
- Modify: `scripts/orchestrator.py:933-937` (`CoverLetterSchema`)
- Modify: `resume-engine/prompts/tailor_coverletter.md`
- Test: `tests/test_orchestrator_coverletter_enrichment.py` (new)

**Interfaces:**
- Produces: `CoverLetterSchema.contact_name: str` (default `""`), `CoverLetterSchema.contact_title: str` (default `""`).

- [ ] **Step 1: Write failing test**

Create `tests/test_orchestrator_coverletter_enrichment.py`:

```python
import json
import os
import sys
import unittest
from unittest.mock import MagicMock, patch

SCRIPTS_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts")
sys.path.insert(0, SCRIPTS_DIR)

import orchestrator  # noqa: E402
import profile_paths  # noqa: E402


class TestCoverLetterSchemaNewFields(unittest.TestCase):

    def test_contact_fields_default_to_empty_string(self):
        model = orchestrator.CoverLetterSchema(
            company_name="Acme", greeting="Dear Acme Corp Hiring Team,",
            body_paragraphs=["p1", "p2"], sign_off="Sincerely,",
        )
        self.assertEqual(model.contact_name, "")
        self.assertEqual(model.contact_title, "")


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run test, verify it fails**

Run: `python -m unittest tests.test_orchestrator_coverletter_enrichment -v`
Expected: FAIL — `TypeError` (unexpected keyword arguments accepted is fine, but the attributes don't exist without the fields, so `AttributeError`).

- [ ] **Step 3: Extend the schema**

In `scripts/orchestrator.py`, replace `CoverLetterSchema` (lines 933-937) with:

```python
class CoverLetterSchema(BaseModel):
    company_name:    str       = Field(description="The hiring company's name, exactly as it appears in the job description.")
    greeting:        str       = Field(description="e.g. 'Dear {Company} Hiring Team,' or a named hiring manager if the JD provides one.")
    contact_name:    str       = Field(default="", description="The specific hiring contact's name, only if the job description names one -- empty string otherwise.")
    contact_title:   str       = Field(default="", description="That contact's job title, only if the job description states one -- empty string otherwise.")
    body_paragraphs: List[str] = Field(description="2-3 first-person paragraphs, each grounded in a real JD requirement and a real fact from the background context.")
    sign_off:        str       = Field(description="e.g. 'Sincerely,'")
```

- [ ] **Step 4: Run test, verify it passes**

Run: `python -m unittest tests.test_orchestrator_coverletter_enrichment -v`
Expected: PASS

- [ ] **Step 5: Update the cover letter prompt**

In `resume-engine/prompts/tailor_coverletter.md`, replace Task item 1 with:

```markdown
1. A **greeting** -- "Dear {Company Name} Hiring Team," (using the real company name) unless the JD names a specific hiring manager, in which case greet them by name (e.g. "Dear Maggie Smith," or "Dear Ms. Smith," if only a last name/title is given).
```

Add a new Task item after the current item 4 (company_name):

```markdown
5. The hiring **contact's name and title**, only if the job description itself names a specific person to contact (for `contact_name`/`contact_title`) -- this is the same JD read used for the greeting above, just captured as structured fields too. Leave both as empty strings if the JD doesn't name anyone. Never invent a contact.
```

In the Rules section, add a bullet right after the existing company-research bullet about the Company Connection:

```markdown
- If `notable_highlights` are present in the `=== COMPANY RESEARCH ===` block, consider opening the first paragraph with one of them as a hook (e.g. leading with a notable award, ranking, funding milestone, or stat) rather than saving all company connection for later in the letter. Use at most 1-2, and never fabricate beyond what's given.
```

Update the Output section:

```markdown
Respond with the structured cover letter JSON only: `company_name`, `greeting`, `contact_name`, `contact_title`, `body_paragraphs` (a list of 2-3 strings, one per paragraph), `sign_off`.
```

- [ ] **Step 6: Commit**

```bash
git add scripts/orchestrator.py resume-engine/prompts/tailor_coverletter.md tests/test_orchestrator_coverletter_enrichment.py
git commit -m "feat(coverletter): add structured contact_name/contact_title fields"
```

---

### Task 3: Deterministic resolver helpers (location, contact fallback, tagline)

**Files:**
- Modify: `scripts/orchestrator.py` (add three module-level functions near `find_jd_contacts`/`_build_output_stem`, roughly line 1007-1026)
- Test: `tests/test_orchestrator_coverletter_enrichment.py`, `tests/test_orchestrator_contacts.py`

**Interfaces:**
- Consumes: `find_jd_contacts(jd_data: dict) -> list` (existing, `orchestrator.py:966`).
- Produces: `_resolve_company_location(research: dict | None, jd_data: dict) -> str`, `_resolve_contact_fallback(letter_data: dict, jd_data: dict) -> None` (mutates in place), `_read_matching_resume_tagline(stem: str) -> str`.

- [ ] **Step 1: Write failing tests**

Add to `tests/test_orchestrator_coverletter_enrichment.py`:

```python
class TestResolveCompanyLocation(unittest.TestCase):

    def test_prefers_research_hq_location(self):
        result = orchestrator._resolve_company_location(
            {"company_hq_location": "Austin, TX"}, {"location": "Remote"})
        self.assertEqual(result, "Austin, TX")

    def test_falls_back_to_jd_location_when_research_has_none(self):
        result = orchestrator._resolve_company_location({"company_hq_location": ""}, {"location": "Remote"})
        self.assertEqual(result, "Remote")

    def test_falls_back_to_jd_location_when_research_is_none(self):
        result = orchestrator._resolve_company_location(None, {"location": "Buffalo, NY"})
        self.assertEqual(result, "Buffalo, NY")

    def test_returns_empty_string_when_nothing_known(self):
        self.assertEqual(orchestrator._resolve_company_location(None, {}), "")

    def test_returns_jd_location_even_for_a_remote_role(self):
        # No filtering by remote/on-site -- shown whenever known.
        result = orchestrator._resolve_company_location(None, {"location": "Remote"})
        self.assertEqual(result, "Remote")


class TestReadMatchingResumeTagline(unittest.TestCase):

    def setUp(self):
        self.resume_dir = os.path.join(profile_paths.output_dir(), "json")
        os.makedirs(self.resume_dir, exist_ok=True)
        self.resume_path = os.path.join(self.resume_dir, "_tmp_enrichment_stem_Resume.json")

    def tearDown(self):
        if os.path.exists(self.resume_path):
            os.remove(self.resume_path)

    def test_returns_empty_string_when_no_matching_resume_exists(self):
        self.assertEqual(orchestrator._read_matching_resume_tagline("_tmp_enrichment_stem"), "")

    def test_returns_tagline_from_matching_resume_json(self):
        with open(self.resume_path, "w", encoding="utf-8") as f:
            json.dump({"TAGLINE": "CONTENT STRATEGIST | SEO"}, f)
        self.assertEqual(
            orchestrator._read_matching_resume_tagline("_tmp_enrichment_stem"),
            "CONTENT STRATEGIST | SEO",
        )

    def test_returns_empty_string_on_malformed_json(self):
        with open(self.resume_path, "w", encoding="utf-8") as f:
            f.write("{not valid json")
        self.assertEqual(orchestrator._read_matching_resume_tagline("_tmp_enrichment_stem"), "")
```

Add to `tests/test_orchestrator_contacts.py` (new class, alongside `TestFindJdContacts`):

```python
class TestResolveContactFallback(unittest.TestCase):

    def test_no_op_when_model_already_found_a_contact(self):
        letter_data = {"contact_name": "Maggie Smith", "contact_title": "HR Manager"}
        orchestrator._resolve_contact_fallback(letter_data, {"social_connections": [
            {"fullName": "Someone Else", "jobTitle": "Recruiter"},
        ]})
        self.assertEqual(letter_data["contact_name"], "Maggie Smith")

    def test_fills_from_scraped_contact_with_hr_title(self):
        letter_data = {"contact_name": "", "contact_title": ""}
        jd_data = {"social_connections": [
            {"fullName": "Jen Dudik", "jobTitle": "Director of Engineering"},
            {"fullName": "Maggie Smith", "jobTitle": "HR Manager"},
        ]}
        orchestrator._resolve_contact_fallback(letter_data, jd_data)
        self.assertEqual(letter_data["contact_name"], "Maggie Smith")
        self.assertEqual(letter_data["contact_title"], "HR Manager")

    def test_falls_back_to_first_contact_when_no_hr_title_matches(self):
        letter_data = {"contact_name": "", "contact_title": ""}
        jd_data = {"social_connections": [{"fullName": "Jen Dudik", "jobTitle": "Director of Engineering"}]}
        orchestrator._resolve_contact_fallback(letter_data, jd_data)
        self.assertEqual(letter_data["contact_name"], "Jen Dudik")

    def test_leaves_fields_empty_when_no_contacts_exist(self):
        letter_data = {"contact_name": "", "contact_title": ""}
        orchestrator._resolve_contact_fallback(letter_data, {})
        self.assertEqual(letter_data["contact_name"], "")
        self.assertEqual(letter_data["contact_title"], "")
```

- [ ] **Step 2: Run tests, verify they fail**

Run: `python -m unittest tests.test_orchestrator_coverletter_enrichment tests.test_orchestrator_contacts -v`
Expected: FAIL — `AttributeError: module 'orchestrator' has no attribute '_resolve_company_location'` (etc.)

- [ ] **Step 3: Implement the three helpers**

In `scripts/orchestrator.py`, add immediately after `find_jd_contacts()` (after line 1007, before `_build_output_stem`):

```python
_CONTACT_TITLE_KEYWORDS = ("hr", "recruit", "talent", "people")


def _resolve_contact_fallback(letter_data: dict, jd_data: dict) -> None:
    """Fills contact_name/contact_title from already-scraped, real JD
    contacts (find_jd_contacts()) when the model found no named contact
    in the JD text itself. Mutates letter_data in place. Never invents a
    person -- prefers a contact whose title reads as HR/recruiting/talent,
    else the first scraped contact; no-op if none exist."""
    if letter_data.get("contact_name"):
        return
    contacts = find_jd_contacts(jd_data)
    if not contacts:
        return
    chosen = next(
        (c for c in contacts if any(k in (c.get("title") or "").lower() for k in _CONTACT_TITLE_KEYWORDS)),
        contacts[0],
    )
    letter_data["contact_name"] = chosen.get("name", "")
    letter_data["contact_title"] = chosen.get("title", "")


def _resolve_company_location(research: dict | None, jd_data: dict) -> str:
    """Prefers company_hq_location from company research (traceable to
    real source text); falls back to the JD's own posted location.
    Shown regardless of remote/on-site status -- the candidate wants the
    address line for professionalism even on remote roles."""
    if research and research.get("company_hq_location"):
        return research["company_hq_location"]
    return jd_data.get("location") or ""


def _read_matching_resume_tagline(stem: str) -> str:
    """Best-effort read of a resume TAGLINE already built for the same
    JD -- '{stem}_Resume.json' in this profile's output/json dir, the
    exact filename build_tailored_resume() writes (see _build_output_stem,
    the shared stem builder). Returns "" if no resume has been built yet
    for this JD, or if its JSON can't be parsed -- a cover letter can
    always be generated standalone."""
    resume_path = os.path.join(profile_paths.output_dir(), "json", f"{stem}_Resume.json")
    if not os.path.exists(resume_path):
        return ""
    try:
        with open(resume_path, "r", encoding="utf-8") as f:
            resume_data = json.load(f)
    except (json.JSONDecodeError, UnicodeDecodeError, OSError):
        return ""
    return resume_data.get("TAGLINE", "") if isinstance(resume_data, dict) else ""
```

- [ ] **Step 4: Run tests, verify they pass**

Run: `python -m unittest tests.test_orchestrator_coverletter_enrichment tests.test_orchestrator_contacts -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add scripts/orchestrator.py tests/test_orchestrator_coverletter_enrichment.py tests/test_orchestrator_contacts.py
git commit -m "feat(coverletter): add deterministic location/contact/tagline resolvers"
```

---

### Task 4: `render_coverletter.py` — 3-line recipient block + tagline threading

**Files:**
- Modify: `scripts/render_coverletter.py`
- Test: `tests/test_render_coverletter.py`

**Interfaces:**
- Consumes: `cover_letter_data.get("contact_name")`, `.get("contact_title")`, `.get("company_location")`, `.get("tagline")` (all optional, default `""` — the keys `build_tailored_coverletter()` will populate in Task 5).
- Produces: `build_recipient_block_html(company_name: str, contact_name: str = "", contact_title: str = "", location: str = "") -> str` (signature change from today's single-arg version).

- [ ] **Step 1: Write failing tests**

Add to `tests/test_render_coverletter.py`, inside `TestRenderCoverLetter`:

```python
    def test_recipient_block_shows_attn_line_when_contact_known(self):
        render_coverletter(_minimal_letter_data(contact_name="Maggie Smith", contact_title="HR Manager"), self.out_path)
        with open(self.out_path, "r", encoding="utf-8") as f:
            html = f.read()
        self.assertIn("Attn: Maggie Smith, HR Manager", html)

    def test_recipient_block_falls_back_to_hiring_team_line_without_contact(self):
        render_coverletter(_minimal_letter_data(company_name="Widget Co"), self.out_path)
        with open(self.out_path, "r", encoding="utf-8") as f:
            html = f.read()
        self.assertIn("Widget Co Hiring Team", html)

    def test_recipient_block_includes_location_when_present(self):
        render_coverletter(_minimal_letter_data(company_location="Austin, TX"), self.out_path)
        with open(self.out_path, "r", encoding="utf-8") as f:
            html = f.read()
        self.assertIn("Austin, TX", html)

    def test_tagline_rendered_in_header_when_present(self):
        render_coverletter(_minimal_letter_data(tagline="CONTENT STRATEGIST | SEO"), self.out_path)
        with open(self.out_path, "r", encoding="utf-8") as f:
            html = f.read()
        self.assertIn("CONTENT STRATEGIST | SEO", html)
```

Add a new class at the end of the file (before `class TestBuildSignatureBlockHtml` or after it):

```python
class TestBuildRecipientBlockHtml(unittest.TestCase):

    def test_no_contact_no_location(self):
        html = render_coverletter_module.build_recipient_block_html("Acme Corp")
        self.assertEqual(html, '<div class="letter-address">Acme Corp Hiring Team<br>Acme Corp</div>')

    def test_with_contact_and_location(self):
        html = render_coverletter_module.build_recipient_block_html(
            "Acme Corp", contact_name="Maggie Smith", contact_title="HR Manager", location="Austin, TX")
        self.assertEqual(
            html,
            '<div class="letter-address">Attn: Maggie Smith, HR Manager<br>Acme Corp<br>Austin, TX</div>',
        )

    def test_contact_without_title(self):
        html = render_coverletter_module.build_recipient_block_html("Acme Corp", contact_name="Maggie Smith")
        self.assertIn("Attn: Maggie Smith<br>", html)
        self.assertNotIn("Attn: Maggie Smith,", html)

    def test_escapes_html_in_all_lines(self):
        html = render_coverletter_module.build_recipient_block_html(
            "A&B Corp", contact_name="Pat <b>Lee</b>", location="NY & NJ")
        self.assertIn("A&amp;B Corp", html)
        self.assertIn("Pat &lt;b&gt;Lee&lt;/b&gt;", html)
        self.assertIn("NY &amp; NJ", html)
```

- [ ] **Step 2: Run tests, verify they fail**

Run: `python -m unittest tests.test_render_coverletter -v`
Expected: FAIL — `TypeError: build_recipient_block_html() got an unexpected keyword argument` (etc.)

- [ ] **Step 3: Implement**

In `scripts/render_coverletter.py`, replace `build_recipient_block_html()` (lines 26-30) with:

```python
def build_recipient_block_html(company_name: str, contact_name: str = "", contact_title: str = "", location: str = "") -> str:
    # Up to 3 lines in one .letter-address div (line-height 1.3, single
    # margin-top before the whole block) so it reads as a tight address
    # block rather than 3 separately-spaced paragraphs.
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
    return f'<div class="letter-address">{"<br>".join(escape(line) for line in lines)}</div>'
```

In `render_coverletter()`, update the `TAGLINE` scalar (currently hardcoded `""`, around line 73):

```python
        "TAGLINE":          escape(cover_letter_data.get("tagline", "")),
```

And update the recipient block call site (around line 88):

```python
    html = html.replace("{{RECIPIENT_BLOCK}}", build_recipient_block_html(
        company_name,
        cover_letter_data.get("contact_name", ""),
        cover_letter_data.get("contact_title", ""),
        cover_letter_data.get("company_location", ""),
    ))
```

- [ ] **Step 4: Run tests, verify they pass**

Run: `python -m unittest tests.test_render_coverletter -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add scripts/render_coverletter.py tests/test_render_coverletter.py
git commit -m "feat(coverletter): render 3-line address block and tagline in header"
```

---

### Task 5: Wire it all into `build_tailored_coverletter()` + end-to-end tests

**Files:**
- Modify: `scripts/orchestrator.py:2675-2784` (`build_tailored_coverletter`)
- Test: `tests/test_orchestrator_coverletter_enrichment.py`

**Interfaces:**
- Consumes everything from Tasks 1-4: `_resolve_contact_fallback`, `_resolve_company_location`, `_read_matching_resume_tagline`, the extended schemas.
- Produces: `letter_data` (as saved to `{stem}_CoverLetter.json` and passed to `render_coverletter()`) now always carries `tagline`, `company_location`, and (when known) `contact_name`/`contact_title`.

- [ ] **Step 1: Write failing tests**

Add to `tests/test_orchestrator_coverletter_enrichment.py`:

```python
class TestCoverLetterEnrichmentWiring(unittest.TestCase):
    """Confirms build_tailored_coverletter() merges tagline, resolved
    company_location, and contact fallback into the saved letter_data."""

    def setUp(self):
        self.engine = orchestrator.ResumeEngine()
        self.jd_path = os.path.join(os.path.dirname(__file__), "_tmp_jd_enrichment.json")
        self.jd_json = {
            "job_title": "Content Strategist",
            "company_name": "Acme Corp",
            "location": "Remote",
            "description": "We are hiring a Content Strategist.",
        }
        with open(self.jd_path, "w", encoding="utf-8") as f:
            json.dump(self.jd_json, f)

        self.stem = orchestrator._build_output_stem(self.jd_path)
        self.resume_json_path = os.path.join(self.engine.output_json_dir, f"{self.stem}_Resume.json")
        os.makedirs(self.engine.output_json_dir, exist_ok=True)
        with open(self.resume_json_path, "w", encoding="utf-8") as f:
            json.dump({"TAGLINE": "CONTENT STRATEGIST | SEO | LIFECYCLE MARKETING"}, f)

        self.json_out = os.path.join(self.engine.output_json_dir, f"{self.stem}_CoverLetter.json")
        self.html_out = os.path.join(self.engine.output_html_dir, f"{self.stem}_CoverLetter.html")

    def tearDown(self):
        for path in (self.jd_path, self.resume_json_path, self.json_out, self.html_out):
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

    def _run_build(self):
        with patch("orchestrator.subprocess.run", return_value=MagicMock(returncode=0, stdout="", stderr="")), \
             patch("orchestrator.render_coverletter"), \
             patch("orchestrator.validate_pdf_text.validate_coverletter_pdf_text", return_value=[]):
            return self.engine.build_tailored_coverletter(self.jd_path)

    @patch.object(orchestrator.ResumeEngine, "research_company",
                   return_value={"company_hq_location": "Austin, TX", "company_facts": [], "notable_highlights": []})
    @patch("orchestrator.GeminiClient.generate")
    def test_tagline_and_research_location_land_in_saved_letter(self, mock_generate, mock_research):
        mock_generate.return_value = (self._clean_letter_json(), {})
        result = self._run_build()
        self.assertEqual(result["tagline"], "CONTENT STRATEGIST | SEO | LIFECYCLE MARKETING")
        self.assertEqual(result["company_location"], "Austin, TX")

    @patch.object(orchestrator.ResumeEngine, "research_company", return_value=None)
    @patch("orchestrator.GeminiClient.generate")
    def test_falls_back_to_jd_location_when_research_has_none(self, mock_generate, mock_research):
        mock_generate.return_value = (self._clean_letter_json(), {})
        result = self._run_build()
        self.assertEqual(result["company_location"], "Remote")

    @patch.object(orchestrator.ResumeEngine, "research_company", return_value=None)
    @patch("orchestrator.GeminiClient.generate")
    def test_contact_fallback_fills_from_scraped_jd_contacts(self, mock_generate, mock_research):
        self.jd_json["social_connections"] = [
            {"fullName": "Maggie Smith", "jobTitle": "HR Manager", "companyName": "Acme Corp"},
        ]
        with open(self.jd_path, "w", encoding="utf-8") as f:
            json.dump(self.jd_json, f)
        mock_generate.return_value = (self._clean_letter_json(), {})
        result = self._run_build()
        self.assertEqual(result["contact_name"], "Maggie Smith")
        self.assertEqual(result["contact_title"], "HR Manager")


if __name__ == "__main__":
    unittest.main()
```

(Remove the now-duplicate trailing `if __name__ == "__main__": unittest.main()` left over from Task 2's file creation, keeping only one at the true end of the file.)

- [ ] **Step 2: Run tests, verify they fail**

Run: `python -m unittest tests.test_orchestrator_coverletter_enrichment -v`
Expected: FAIL — `KeyError: 'tagline'` / `'company_location'` (not merged into `letter_data` yet).

- [ ] **Step 3: Wire the resolvers into `build_tailored_coverletter()`**

In `scripts/orchestrator.py`, in `build_tailored_coverletter()`, right after the existing validate/retry block ends (immediately before the current `stem     = _build_output_stem(jd_path)` line, around line 2745), insert:

```python
        _resolve_contact_fallback(letter_data, jd_data)
        letter_data["company_location"] = _resolve_company_location(research, jd_data)

        stem     = _build_output_stem(jd_path)
        letter_data["tagline"] = _read_matching_resume_tagline(stem)
        json_out = os.path.join(self.output_json_dir, f"{stem}_CoverLetter.json")
```

(the two lines after `stem = ...` — `json_out = ...` and everything below — stay exactly as they are today; `letter_data["tagline"]` is set right after `stem` is computed since `_read_matching_resume_tagline` needs it, and before `json_out`/`html_out` so the enriched dict is what gets both saved to JSON and passed to `render_coverletter()`.)

- [ ] **Step 4: Run tests, verify they pass**

Run: `python -m unittest tests.test_orchestrator_coverletter_enrichment -v`
Expected: PASS

- [ ] **Step 5: Run the full test suite**

Run: `python -m unittest discover -s tests -v`
Expected: PASS, no regressions (in particular `tests/test_orchestrator_coverletter_injection.py`'s B14 regression suite, `tests/test_render_coverletter.py`, `tests/test_orchestrator_research_block.py`, `tests/test_orchestrator_contacts.py`, `tests/test_validate_coverletter.py`).

- [ ] **Step 6: Commit and push**

```bash
git add scripts/orchestrator.py tests/test_orchestrator_coverletter_enrichment.py
git commit -m "feat(coverletter): wire tagline/location/contact resolution into build_tailored_coverletter"
git push
```
