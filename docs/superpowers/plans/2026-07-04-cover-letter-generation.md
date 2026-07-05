# Cover Letter Generation (No Company Research) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a standalone `resume coverletter <jd_file>` command that generates and renders a first-person cover letter PDF from a JD, using existing background context (no live company research yet — that's a later pass).

**Architecture:** One new Gemini call (JD text + `ResumeEngine.build_audit_static_prefix()`'s background context → structured `CoverLetterSchema`), checked by a new lightweight validator (reuses `style_rules.yaml`'s `forbidden_phrases` list plus two new checks), with one automatic retry on violations, rendered through a new template-fill script into the existing `generate-pdf.mjs` pipeline (unchanged).

**Tech Stack:** Python 3.10+, Pydantic, the existing `GeminiClient` (raw REST), Click (CLI), string-replace HTML templating (matching `render_html.py`'s pattern), Playwright/Node for PDF via `generate-pdf.mjs`.

## Global Constraints

- First-person throughout the letter body — inverted from the resume's pronoun-free-except-Why rule.
- No fabricated company research or facts outside the knowledge base — reuse `build_audit_static_prefix()`'s verified-facts-only content, nothing else.
- No new output folders — reuse `output/json/`, `output/html/`, `output/pdf/` with a `_coverletter` filename suffix.
- Do not wire into `jd_tracker_log.csv` / `data/applications.md` this pass — a cover letter is a side artifact, not a tracked pipeline completion event.
- Do not touch the signature `<img>` path in the template — Morgan is providing `docs/MorganEscottSignature2025.png` separately; rendering without it is expected and non-blocking.
- Reuse `style_rules.yaml`'s existing `forbidden_phrases` list verbatim — do not create a second phrase list.
- No page-fit trim loop, no per-role bullet allocation, no skills-line-wrap validation — none of these apply to a cover letter.
- Spec: `docs/superpowers/specs/2026-07-04-cover-letter-generation-design.md`.

---

### Task 1: Cover letter validator

**Files:**
- Create: `scripts/validate_coverletter.py`
- Test: `tests/test_validate_coverletter.py`

**Interfaces:**
- Consumes: nothing from other tasks (pure function, no dependencies beyond a plain dict + a plain dict of style rules).
- Produces: `validate_coverletter.validate(cover_letter_data: dict, style_rules: dict) -> list[str]` — a flat list of violation strings, `[]` if clean. `cover_letter_data` has keys `company_name`, `greeting`, `body_paragraphs` (list of str), `sign_off`. `style_rules` has key `forbidden_phrases` (list of str) — same shape as `style_rules.yaml`. Task 3 calls this exact function with this exact shape.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_validate_coverletter.py`:

```python
import os
import sys
import unittest

SCRIPTS_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts")
sys.path.insert(0, SCRIPTS_DIR)

import validate_coverletter  # noqa: E402

STYLE_RULES = {
    "forbidden_phrases": ["results-driven", "passionate", "synergy", "best-in-class"],
}


def _valid_letter():
    return {
        "company_name": "Acme Corp",
        "greeting": "Dear Hiring Team,",
        "body_paragraphs": [
            "I was excited to see the Content Strategist opening at Acme Corp, since it "
            "lines up directly with my background in campaign messaging and content "
            "operations.",
            "In my most recent role, I built lifecycle email campaigns that grew "
            "engagement by double digits, which maps closely to the JD's focus on "
            "activation-ready content.",
        ],
        "sign_off": "Sincerely,",
    }


class TestValidateCoverLetter(unittest.TestCase):

    def test_valid_letter_has_no_violations(self):
        violations = validate_coverletter.validate(_valid_letter(), STYLE_RULES)
        self.assertEqual(violations, [])

    def test_flags_forbidden_phrase(self):
        letter = _valid_letter()
        letter["body_paragraphs"][0] += " I'm a results-driven professional."
        violations = validate_coverletter.validate(letter, STYLE_RULES)
        self.assertTrue(any("results-driven" in v for v in violations))

    def test_flags_too_few_paragraphs(self):
        letter = _valid_letter()
        letter["body_paragraphs"] = ["Only one paragraph here."]
        violations = validate_coverletter.validate(letter, STYLE_RULES)
        self.assertTrue(any("Expected 2-3 body paragraphs" in v for v in violations))

    def test_flags_too_many_paragraphs(self):
        letter = _valid_letter()
        letter["body_paragraphs"] = ["One.", "Two.", "Three.", "Four."]
        violations = validate_coverletter.validate(letter, STYLE_RULES)
        self.assertTrue(any("Expected 2-3 body paragraphs" in v for v in violations))

    def test_flags_third_person_slip(self):
        letter = _valid_letter()
        letter["body_paragraphs"][0] = "Morgan has years of experience in content strategy."
        violations = validate_coverletter.validate(letter, STYLE_RULES)
        self.assertTrue(any("Third-person self-reference" in v for v in violations))

    def test_allows_legitimate_third_party_pronoun(self):
        # Known trade-off, not a bug: "her"/"she" is a blunt heuristic (see
        # validate_coverletter.py's docstring). This test just documents the
        # limitation exists rather than asserting a specific behavior for it.
        pass
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /Users/morganescott/resume-builder && source .venv/bin/activate && python -m unittest tests.test_validate_coverletter -v`
Expected: `ModuleNotFoundError: No module named 'validate_coverletter'` (file doesn't exist yet).

- [ ] **Step 3: Write the implementation**

Create `scripts/validate_coverletter.py`:

```python
"""
validate_coverletter.py — Deterministic Python checks for cover letter
output, run after every Gemini call in
ResumeEngine.build_tailored_coverletter().

Mirrors validate_resume.py's conventions (word-boundary forbidden-phrase
matching, a flat list of violation strings) but scoped to what actually
applies to a cover letter -- no bullet/skills/tagline checks exist here,
since a cover letter has none of those structures.
"""

import re


def _check_forbidden_phrases(cover_letter_data: dict, style_rules: dict) -> list[str]:
    violations = []
    phrases = [p.lower() for p in style_rules.get("forbidden_phrases", [])]
    haystacks = (
        [cover_letter_data.get("greeting", "")]
        + cover_letter_data.get("body_paragraphs", [])
        + [cover_letter_data.get("sign_off", "")]
    )
    for text in haystacks:
        lowered = text.lower()
        for phrase in phrases:
            if re.search(rf"\b{re.escape(phrase)}\b", lowered):
                violations.append(f"Forbidden phrase '{phrase}' found in: {text!r}")
    return violations


def _check_paragraph_count(cover_letter_data: dict) -> list[str]:
    count = len(cover_letter_data.get("body_paragraphs", []))
    if count < 2 or count > 3:
        return [f"Expected 2-3 body paragraphs, got {count}"]
    return []


# Blunt heuristic, not a perfect one: a first-person letter addressed
# generically to "Hiring Team" shouldn't ever need to reference a third
# party by name/pronoun, so this is a reasonable v1 check -- but it would
# false-positive on a legitimate sentence naming someone else (e.g. "I
# worked with the hiring manager and her team"). Not a concern for this
# pass since letters don't name third parties without company research.
_THIRD_PERSON_PATTERN = re.compile(r"\b(Morgan Escott|Morgan|she|her|hers)\b", re.IGNORECASE)


def _check_third_person_slip(cover_letter_data: dict) -> list[str]:
    violations = []
    haystacks = (
        [("greeting", cover_letter_data.get("greeting", ""))]
        + [(f"body_paragraphs[{i}]", p) for i, p in enumerate(cover_letter_data.get("body_paragraphs", []))]
        + [("sign_off", cover_letter_data.get("sign_off", ""))]
    )
    for field_name, text in haystacks:
        if _THIRD_PERSON_PATTERN.search(text):
            violations.append(f"Third-person self-reference found in {field_name}: {text!r}")
    return violations


def validate(cover_letter_data: dict, style_rules: dict) -> list[str]:
    violations = []
    violations.extend(_check_forbidden_phrases(cover_letter_data, style_rules))
    violations.extend(_check_paragraph_count(cover_letter_data))
    violations.extend(_check_third_person_slip(cover_letter_data))
    return violations
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd /Users/morganescott/resume-builder && source .venv/bin/activate && python -m unittest tests.test_validate_coverletter -v`
Expected: all 6 tests pass (5 real assertions + 1 documentation no-op).

- [ ] **Step 5: Run the full suite to confirm no regressions**

Run: `source .venv/bin/activate && python -m unittest discover -s tests`
Expected: `OK`, test count increased by 6 from the prior total.

- [ ] **Step 6: Commit**

```bash
git add scripts/validate_coverletter.py tests/test_validate_coverletter.py
git commit -m "$(cat <<'EOF'
Add cover letter validator (forbidden phrases, paragraph count, third-person slip)

Part of cover letter generation (see docs/superpowers/specs/2026-07-04-cover-letter-generation-design.md).

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
EOF
)"
```

---

### Task 2: Cover letter renderer + template CSS

**Files:**
- Create: `scripts/render_coverletter.py`
- Modify: `resume-engine/templates/coverletter-template.html:114` (add `.letter-recipient` CSS rule after `.letter-date`)
- Test: `tests/test_render_coverletter.py`

**Interfaces:**
- Consumes: `fixed_content.CONTACT_INFO` dict (keys `NAME`, `PHONE`, `EMAIL`, `LINKEDIN_DISPLAY`, `LOCATION` — already exists, `scripts/fixed_content.py:21`).
- Produces: `render_coverletter.render_coverletter(cover_letter_data: dict, output_path: str) -> str` — fills the template, writes to `output_path`, returns `output_path`. `cover_letter_data` has the same shape as Task 1 (`company_name`, `greeting`, `body_paragraphs`, `sign_off`). Task 3 calls this exact function with this exact shape.

- [ ] **Step 1: Add the missing CSS rule to the template**

In `resume-engine/templates/coverletter-template.html`, find this block (around line 109-115):

```css
  .letter-date {
    margin-top: 28px;
    font-size: 10.5pt;
    font-weight: 400;
    line-height: 1.4;
  }
```

Add immediately after it:

```css

  .letter-recipient {
    margin-top: 20px;
    font-size: 10.5pt;
    font-weight: 400;
    line-height: 1.4;
  }
```

- [ ] **Step 2: Write the failing tests**

Create `tests/test_render_coverletter.py`:

```python
import os
import sys
import unittest

SCRIPTS_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts")
sys.path.insert(0, SCRIPTS_DIR)

from render_coverletter import render_coverletter  # noqa: E402


def _minimal_letter_data(**overrides):
    data = {
        "company_name": "Acme Corp",
        "greeting": "Dear Hiring Team,",
        "body_paragraphs": [
            "First paragraph, tying a JD requirement to real experience.",
            "Second paragraph, with another concrete example.",
        ],
        "sign_off": "Sincerely,",
    }
    data.update(overrides)
    return data


class TestRenderCoverLetter(unittest.TestCase):

    def setUp(self):
        self.out_path = os.path.join(os.path.dirname(__file__), "_tmp_coverletter.html")

    def tearDown(self):
        if os.path.exists(self.out_path):
            os.remove(self.out_path)

    def test_no_unfilled_tokens_remain(self):
        render_coverletter(_minimal_letter_data(), self.out_path)
        with open(self.out_path, "r", encoding="utf-8") as f:
            html = f.read()
        self.assertNotIn("{{", html)
        self.assertNotIn("}}", html)

    def test_recipient_block_contains_company_name(self):
        render_coverletter(_minimal_letter_data(company_name="Widget Co"), self.out_path)
        with open(self.out_path, "r", encoding="utf-8") as f:
            html = f.read()
        self.assertIn("Widget Co", html)
        self.assertIn('class="letter-recipient"', html)

    def test_body_paragraphs_each_wrapped_in_p_tag(self):
        render_coverletter(_minimal_letter_data(), self.out_path)
        with open(self.out_path, "r", encoding="utf-8") as f:
            html = f.read()
        self.assertIn("<p>First paragraph, tying a JD requirement to real experience.</p>", html)
        self.assertIn("<p>Second paragraph, with another concrete example.</p>", html)

    def test_contact_info_comes_from_fixed_content(self):
        render_coverletter(_minimal_letter_data(), self.out_path)
        with open(self.out_path, "r", encoding="utf-8") as f:
            html = f.read()
        self.assertIn("Morgan Escott", html)
        self.assertIn("escott.morgan@gmail.com", html)
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `cd /Users/morganescott/resume-builder && source .venv/bin/activate && python -m unittest tests.test_render_coverletter -v`
Expected: `ModuleNotFoundError: No module named 'render_coverletter'` (file doesn't exist yet).

- [ ] **Step 4: Write the implementation**

Create `scripts/render_coverletter.py`:

```python
"""
render_coverletter.py — Fills coverletter-template.html with
ResumeEngine.build_tailored_coverletter()'s output.

Usage (standalone):
    python scripts/render_coverletter.py output/json/my_letter_coverletter.json output/html/my_letter_coverletter.html

Called programmatically by orchestrator.py's build_tailored_coverletter().
"""

import argparse
import datetime
import json
import os
from html import escape

import fixed_content

SCRIPT_DIR    = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT  = os.path.dirname(SCRIPT_DIR)
TEMPLATE_PATH = os.path.join(PROJECT_ROOT, "resume-engine", "templates", "coverletter-template.html")


def build_recipient_block_html(company_name: str) -> str:
    return f'<div class="letter-recipient">{escape(company_name)}</div>'


def build_body_paragraphs_html(paragraphs: list) -> str:
    return "\n".join(f"<p>{escape(p)}</p>" for p in paragraphs)


def render_coverletter(cover_letter_data: dict, output_path: str) -> str:
    """
    Fill coverletter-template.html with cover_letter_data and write to
    output_path. Returns output_path on success.
    """
    with open(TEMPLATE_PATH, "r", encoding="utf-8") as f:
        html = f.read()

    company_name = cover_letter_data.get("company_name", "")
    contact = fixed_content.CONTACT_INFO
    title = f"{company_name} Cover Letter - Morgan Escott" if company_name else "Cover Letter - Morgan Escott"

    scalars = {
        "LANG":             "en",
        "DOCUMENT_TITLE":   escape(title),
        "NAME":             escape(contact["NAME"]),
        "TAGLINE":          "",
        "PHONE":            escape(contact["PHONE"]),
        "EMAIL":            escape(contact["EMAIL"]),
        "LINKEDIN_DISPLAY": escape(contact["LINKEDIN_DISPLAY"]),
        "LOCATION":         escape(contact["LOCATION"]),
        "PAGE_WIDTH":       "8.5in",
        "DATE":             datetime.date.today().strftime("%B %-d, %Y"),
        "GREETING":         escape(cover_letter_data.get("greeting", "")),
        "SIGN_OFF":         escape(cover_letter_data.get("sign_off", "")),
        "TYPED_NAME":       escape(contact["NAME"]),
        "TYPED_CONTACT":    escape(f"{contact['EMAIL']} | {contact['PHONE']}"),
    }
    for token, value in scalars.items():
        html = html.replace(f"{{{{{token}}}}}", value)

    html = html.replace("{{RECIPIENT_BLOCK}}", build_recipient_block_html(company_name))
    html = html.replace("{{BODY_PARAGRAPHS}}", build_body_paragraphs_html(cover_letter_data.get("body_paragraphs", [])))

    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(html)

    print(f"  ✅ Cover letter HTML rendered → {output_path}")
    return output_path


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Render a cover letter JSON into HTML")
    parser.add_argument("input_json")
    parser.add_argument("output_html")
    args = parser.parse_args()
    with open(args.input_json, "r", encoding="utf-8") as f:
        data = json.load(f)
    render_coverletter(data, args.output_html)
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd /Users/morganescott/resume-builder && source .venv/bin/activate && python -m unittest tests.test_render_coverletter -v`
Expected: all 4 tests pass.

- [ ] **Step 6: Run the full suite to confirm no regressions**

Run: `source .venv/bin/activate && python -m unittest discover -s tests`
Expected: `OK`, test count increased by 4 more from Task 1's total.

- [ ] **Step 7: Commit**

```bash
git add scripts/render_coverletter.py tests/test_render_coverletter.py resume-engine/templates/coverletter-template.html
git commit -m "$(cat <<'EOF'
Add cover letter renderer, add missing .letter-recipient CSS rule

Part of cover letter generation (see docs/superpowers/specs/2026-07-04-cover-letter-generation-design.md).

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
EOF
)"
```

---

### Task 3: Cover letter prompt, schema, and `build_tailored_coverletter()`

**Files:**
- Create: `resume-engine/prompts/tailor_coverletter.md`
- Modify: `scripts/orchestrator.py:31` (add `import validate_coverletter` next to `import validate_resume`)
- Modify: `scripts/orchestrator.py:29` (add `from render_coverletter import render_coverletter` next to the existing `render_html` import)
- Modify: `scripts/orchestrator.py:623` (add `CoverLetterSchema` class, immediately before `class CritiqueSchema`)
- Modify: `scripts/orchestrator.py:1447` (add `build_tailored_coverletter` method to `ResumeEngine`, between `evaluate_fit` and `build_tailored_resume`)

**Interfaces:**
- Consumes: `validate_coverletter.validate(dict, dict) -> list[str]` (Task 1), `render_coverletter.render_coverletter(dict, str) -> str` (Task 2), `self.build_audit_static_prefix() -> str` (existing, `orchestrator.py:819`), `self.load_prompt(filename) -> str` (existing, `orchestrator.py:794`), `self.load_yaml(dir, filename) -> dict` (existing, `orchestrator.py:788`), `GeminiClient.generate(...)` / `GeminiClient.parse_json(...)` (existing), module-level `BUILDER_MODEL`, `SCRIPT_DIR`, `PROJECT_ROOT` constants (existing).
- Produces: `ResumeEngine.build_tailored_coverletter(jd_path: str) -> dict` — returns the filled cover letter dict plus `_output_paths` (`{"json": ..., "html": ..., "pdf": ...}`), or `{}` on failure. Task 4 calls this exact method.

There is no meaningful unit test for this task without mocking the Gemini API, and this codebase's existing convention (see `dummy_jd.txt`, kept specifically for real-API smoke tests) is to verify LLM-calling code with a real, small live call rather than mocks — Step 6 below is that verification, not a unit test.

- [ ] **Step 1: Write the prompt**

Create `resume-engine/prompts/tailor_coverletter.md`:

```markdown
# Tailor Cover Letter

# Role

You are writing a first-person cover letter for Morgan Escott, tailored to a specific job description. This is NOT a resume -- no bullet points, no page-fit trimming, no third-person framing anywhere.

# Task

Using the job description and the background context provided, write:
1. A **greeting** -- "Dear Hiring Team," unless the JD names a specific hiring manager (rare; use their name if given).
2. **2-3 body paragraphs**, first-person throughout ("I..."), each tying a specific fact from the job description to a specific, real piece of Morgan's background from the context provided. Do not invent facts, metrics, or experience not present in the background context. Do not flatter the company with generic praise ("I've always admired your innovative culture") -- every sentence should be grounded in a real JD requirement or a real fact about Morgan.
3. A **sign-off** -- "Sincerely," or an equally standard, professional close.
4. The hiring company's name, exactly as it appears in the job description (for `company_name`).

# Rules

- First person ("I") throughout every paragraph. Never refer to Morgan in the third person ("Morgan has...", "she brings...").
- No forbidden buzzwords/phrases (results-driven, passionate, synergy, thought leader, etc. -- the same list the resume pipeline forbids).
- Ground every claim in the background context provided -- never invent a metric, tool, or achievement not present there.
- No company research beyond what's in the job description itself -- do not claim to know anything about the company's culture, mission, or values that isn't stated in the JD text. (A later pass will add real company research; this version deliberately doesn't fake it.)
- Keep each paragraph to 3-5 sentences -- a cover letter, not an essay.

# Output

Respond with the structured cover letter JSON only: `company_name`, `greeting`, `body_paragraphs` (a list of 2-3 strings, one per paragraph), `sign_off`.
```

- [ ] **Step 2: Add the imports**

In `scripts/orchestrator.py`, find line 29:

```python
from render_html import render_html
```

Change to:

```python
from render_html import render_html
from render_coverletter import render_coverletter
```

Find line 31:

```python
import validate_resume
```

Change to:

```python
import validate_resume
import validate_coverletter
```

- [ ] **Step 3: Add the schema**

In `scripts/orchestrator.py`, find:

```python
class CritiqueSchema(BaseModel):
```

Insert immediately before it:

```python
class CoverLetterSchema(BaseModel):
    company_name:    str       = Field(description="The hiring company's name, exactly as it appears in the job description.")
    greeting:        str       = Field(description="e.g. 'Dear Hiring Team,' or a named hiring manager if the JD provides one.")
    body_paragraphs: List[str] = Field(description="2-3 first-person paragraphs, each grounded in a real JD requirement and a real fact from the background context.")
    sign_off:        str       = Field(description="e.g. 'Sincerely,'")

```

- [ ] **Step 4: Add the method**

In `scripts/orchestrator.py`, find the blank line between `evaluate_fit`'s `return evaluation` and `def build_tailored_resume(`. Insert:

```python
    def build_tailored_coverletter(self, jd_path: str) -> dict:
        """
        Standalone cover letter generation -- independent of
        build_tailored_resume (no checkpoint, no resume required to exist
        first, no page-fit trim loop -- a cover letter has none of the
        resume's page-count constraints). One Gemini call, validated by
        validate_coverletter.py, with one automatic retry on violations.
        Company research is out of scope for this pass (see
        docs/superpowers/specs/2026-07-04-cover-letter-generation-design.md).
        Returns the filled cover letter dict plus _output_paths
        (json/html/pdf), or {} on failure.
        """
        try:
            with open(jd_path, "r", encoding="utf-8") as f:
                jd_text = f.read()
        except FileNotFoundError:
            print(f"  ERROR: JD file not found: {jd_path}")
            return {}

        coverletter_prompt = self.load_prompt("tailor_coverletter.md")
        background_context = self.build_audit_static_prefix()
        system_instruction = f"{coverletter_prompt}\n\n{background_context}"

        letter_text, _ = GeminiClient.generate(
            model=BUILDER_MODEL,
            system_instruction=system_instruction,
            contents=f"=== JOB DESCRIPTION ===\n{jd_text}",
            response_schema=CoverLetterSchema,
            temperature=0.0,
        )
        letter_data = GeminiClient.parse_json(letter_text or "")
        if not letter_data:
            print("  ERROR: Cover letter generation returned no parseable result.")
            return {}

        style_rules = self.load_yaml(self.rules_dir, "style_rules.yaml")
        violations = validate_coverletter.validate(letter_data, style_rules)

        if violations:
            print(f"  Validator found {len(violations)} issue(s), retrying once:")
            for v in violations:
                print(f"    - {v}")
            fix_contents = (
                f"=== ORIGINAL COVER LETTER JSON ===\n{json.dumps(letter_data, indent=2)}\n\n"
                f"=== ISSUES TO FIX (change nothing else) ===\n" + "\n".join(f"- {v}" for v in violations)
            )
            fix_text, _ = GeminiClient.generate(
                model=BUILDER_MODEL,
                system_instruction=system_instruction,
                contents=fix_contents,
                response_schema=CoverLetterSchema,
                temperature=0.0,
            )
            fixed_data = GeminiClient.parse_json(fix_text or "")
            if fixed_data:
                letter_data = fixed_data
                violations = validate_coverletter.validate(letter_data, style_rules)
            if violations:
                print(f"  WARNING: {len(violations)} issue(s) remain after retry, proceeding anyway:")
                for v in violations:
                    print(f"    - {v}")

        jd_stem  = Path(jd_path).stem
        json_out = os.path.join(self.output_json_dir, f"{jd_stem}_coverletter.json")
        html_out = os.path.join(PROJECT_ROOT, "output", "html", f"{jd_stem}_coverletter.html")
        pdf_out  = os.path.join(PROJECT_ROOT, "output", "pdf",  f"{jd_stem}_coverletter.pdf")

        os.makedirs(os.path.dirname(json_out), exist_ok=True)
        with open(json_out, "w", encoding="utf-8") as f:
            json.dump(letter_data, f, indent=2, ensure_ascii=False)
        print(f"  Cover letter saved to: {json_out}")

        render_coverletter(letter_data, html_out)

        pdf_script = os.path.join(SCRIPT_DIR, "generate-pdf.mjs")
        pdf_result = subprocess.run(
            ["node", pdf_script, html_out, pdf_out, "--format=letter"],
            capture_output=True, text=True
        )
        if pdf_result.returncode != 0:
            print(f"  ⚠️  PDF generation failed:\n{pdf_result.stderr}")
            return {}
        print(pdf_result.stdout)

        letter_data["_output_paths"] = {"json": json_out, "html": html_out, "pdf": pdf_out}
        print(f"  🎉 Cover letter complete! PDF → {pdf_out}")
        return letter_data

```

- [ ] **Step 5: Run the full test suite to confirm no import/syntax regressions**

Run: `source .venv/bin/activate && python -m unittest discover -s tests`
Expected: `OK`, same test count as after Task 2 (this task added no new automated tests, per the note above).

- [ ] **Step 6: Live verification (real Gemini call, real PDF — this is the actual test for this task)**

```bash
cp jds/completed/dummy_jd.txt jds/smoketest_coverletter.json
source .venv/bin/activate
python3 -c "
import sys
sys.path.insert(0, 'scripts')
import orchestrator
engine = orchestrator.ResumeEngine()
result = engine.build_tailored_coverletter('jds/smoketest_coverletter.json')
print('company_name:', result.get('company_name'))
print('greeting:', result.get('greeting'))
print('num paragraphs:', len(result.get('body_paragraphs', [])))
print('sign_off:', result.get('sign_off'))
print('output paths:', result.get('_output_paths'))
"
```

Expected: prints a real company name (matching the Abnormal AI JD in the fixture), a greeting, 2-3 paragraphs, a sign-off, and three real file paths under `_output_paths`. Confirm the PDF actually exists:

```bash
ls -la output/pdf/smoketest_coverletter_coverletter.pdf
```

Then clean up the test artifacts (this was a verification run, not a real application):

```bash
rm -f jds/smoketest_coverletter.json output/json/smoketest_coverletter_coverletter.json output/html/smoketest_coverletter_coverletter.html output/pdf/smoketest_coverletter_coverletter.pdf
```

- [ ] **Step 7: Commit**

```bash
git add resume-engine/prompts/tailor_coverletter.md scripts/orchestrator.py
git commit -m "$(cat <<'EOF'
Add cover letter prompt, schema, and build_tailored_coverletter()

Live-verified against a real JD: produces a grounded, first-person letter
with a real PDF output. Part of cover letter generation (see
docs/superpowers/specs/2026-07-04-cover-letter-generation-design.md).

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
EOF
)"
```

---

### Task 4: CLI wiring (`resume coverletter <jd_file>`)

**Files:**
- Modify: `scripts/cli.py` (add `coverletter` command)
- Modify: `scripts/resume-cli.sh` (add `coverletter` case + help text, matching the existing `evaluate`/`scan` pattern)

**Interfaces:**
- Consumes: `orchestrator.ResumeEngine.build_tailored_coverletter(jd_path: str) -> dict` (Task 3), `cli_art.display_banner(subtitle: str) -> None` (existing).
- Produces: the `resume coverletter <jd_file>` command, usable both via `python scripts/cli.py coverletter <jd_file>` and the `resume coverletter <jd_file>` shell shortcut.

- [ ] **Step 1: Add the CLI command**

In `scripts/cli.py`, find:

```python
@cli.command()
@click.argument("jd_file", type=click.Path(exists=True))
def evaluate(jd_file):
```

Insert immediately before it:

```python
@cli.command()
@click.argument("jd_file", type=click.Path(exists=True))
def coverletter(jd_file):
    """Generate + render a cover letter for a single JD file."""
    cli_art.display_banner(f"Cover letter: {jd_file}")
    engine = orchestrator.ResumeEngine()
    result = engine.build_tailored_coverletter(jd_file)
    if not result:
        raise SystemExit(1)


```

- [ ] **Step 2: Verify the command registers**

Run: `source .venv/bin/activate && python scripts/cli.py coverletter --help`
Expected:
```
Usage: cli.py coverletter [OPTIONS] JD_FILE

  Generate + render a cover letter for a single JD file.

Options:
  --help  Show this message and exit.
```

- [ ] **Step 3: Wire the shell shortcut**

In `scripts/resume-cli.sh`, find:

```bash
    evaluate)
      ( cd "$_RESUME_BUILDER_DIR" && source .venv/bin/activate && python scripts/cli.py evaluate "$@" )
      ;;
```

Insert immediately before it:

```bash
    coverletter)
      ( cd "$_RESUME_BUILDER_DIR" && source .venv/bin/activate && python scripts/cli.py coverletter "$@" )
      ;;
```

In the same file, find:

```bash
      echo "  resume evaluate jds/x.txt   score a JD's fit (go/no-go) without building a resume"
```

Insert immediately after it:

```bash
      echo "  resume coverletter jds/x.txt   generate + render a cover letter for one JD"
```

- [ ] **Step 4: Verify the shortcut works**

Run: `source scripts/resume-cli.sh && resume coverletter --help`
Expected: same help text as Step 2.

- [ ] **Step 5: Run the full test suite one more time**

Run: `source .venv/bin/activate && python -m unittest discover -s tests`
Expected: `OK`, same test count as after Task 3 (this task adds no new automated tests — it's pure wiring, already verified live in Task 3 and via `--help` above).

- [ ] **Step 6: Commit**

```bash
git add scripts/cli.py scripts/resume-cli.sh
git commit -m "$(cat <<'EOF'
Wire resume coverletter <jd_file> into the CLI and shell shortcut

Completes cover letter generation (see
docs/superpowers/specs/2026-07-04-cover-letter-generation-design.md).
Company research is a deliberately separate, later pass.

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
EOF
)"
```
