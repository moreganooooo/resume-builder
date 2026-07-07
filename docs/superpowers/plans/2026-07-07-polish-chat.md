# Polish Chat Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add `resume polish [FILE]` — an interactive terminal chat that edits an already-generated resume or cover letter's JSON one instruction at a time, showing a diff before saving, and regenerating HTML+PDF on every accepted turn.

**Architecture:** A new `scripts/polish.py` module holds the whole feature: doc-type detection, a Gemini call reusing the builder's existing schemas (`TemplateSchema`/`CoverLetterSchema`) and `normalize_resume`/`validate_resume`/`validate_coverletter`, a field-level diff renderer, and the interactive accept/reject loop. `cli.py` and `menu.py` each get one new entry point that calls into it. No new persistence, no new schemas, no chat-history plumbing — the on-disk JSON already encodes every previously-accepted turn.

**Tech Stack:** Python 3.10+, `questionary` (interactive prompts, already a dependency), `click` (CLI), the existing `GeminiClient`/`orchestrator` schema+model constants, `unittest` (stdlib, project's only test framework).

## Global Constraints

- Python 3.10+ syntax (`str | None`, etc.) — matches the rest of `scripts/`.
- Reuse `GeminiClient.generate(model=BUILDER_MODEL, response_schema=..., temperature=0.0)` — the exact call shape `orchestrator.py` already uses for the builder and for recommendation-apply turns. Do not introduce a second Gemini client path or real multi-turn chat history.
- Every accepted turn must go through `normalize_resume.normalize()` (resume only) before saving — it's idempotent and already the established way non-builder-generated resume JSON gets its fixed fields/formatting reapplied.
- A diff must be shown and explicitly accepted before any file on disk changes. No auto-apply.
- Doc type is determined only by filename suffix: `_Resume.json` → resume, `_CoverLetter.json` → cover letter. Anything else is an error, not a guess.
- Tests: stdlib `unittest`, `tests/test_*.py` naming (auto-discovered — see project `CLAUDE.md`), `sys.path.insert(0, SCRIPTS_DIR)` + plain `import <module>` (the pattern every existing test file in `tests/` uses), mocks via `unittest.mock.patch("<module>.<name>")` targeting the name where it's *used*, not where it's defined.
- Run the suite with `python -m unittest discover -s tests -v` from the project root with `.venv/` activated (or `resume test -v`).

---

## Prep (already done)

The two prompt files this plan's Task 3 depends on already exist and don't need their own task:
- `resume-engine/prompts/polish_resume.md`
- `resume-engine/prompts/polish_coverletter.md`

Both instruct Gemini: apply only the requested change, preserve every other field verbatim, don't re-optimize/re-tailor, don't ask clarifying questions back, and (cover letter only) never touch `company_name`. Confirm they exist before starting Task 3; if for any reason they don't, recreate them with that content before proceeding.

---

### Task 1: Doc-type detection + output stem helper

**Files:**
- Create: `scripts/polish.py`
- Create: `tests/test_polish.py`

**Interfaces:**
- Produces: `polish.RESUME_SUFFIX: str = "_Resume.json"`, `polish.COVERLETTER_SUFFIX: str = "_CoverLetter.json"`, `polish.detect_doc_type(path: str) -> str | None` (returns `"resume"`, `"coverletter"`, or `None`), `polish.stem_from_json_path(path: str, doc_type: str) -> str`.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_polish.py`:

```python
import os
import sys
import unittest

SCRIPTS_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts")
sys.path.insert(0, SCRIPTS_DIR)

import polish  # noqa: E402


class TestDetectDocType(unittest.TestCase):

    def test_resume_suffix(self):
        self.assertEqual(polish.detect_doc_type("output/json/Foo_Bar_Resume.json"), "resume")

    def test_coverletter_suffix(self):
        self.assertEqual(polish.detect_doc_type("output/json/Foo_Bar_CoverLetter.json"), "coverletter")

    def test_unrecognized_suffix_returns_none(self):
        self.assertIsNone(polish.detect_doc_type("output/json/Foo_Bar.json"))


class TestStemFromJsonPath(unittest.TestCase):

    def test_resume_stem(self):
        stem = polish.stem_from_json_path(
            "output/json/MorganEscott_Title_Company_Resume.json", "resume",
        )
        self.assertEqual(stem, "MorganEscott_Title_Company")

    def test_coverletter_stem(self):
        stem = polish.stem_from_json_path(
            "output/json/MorganEscott_Title_Company_CoverLetter.json", "coverletter",
        )
        self.assertEqual(stem, "MorganEscott_Title_Company")


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python -m unittest tests.test_polish -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'polish'` (the file doesn't exist yet).

- [ ] **Step 3: Create `scripts/polish.py` with the minimal implementation**

```python
"""
polish.py -- interactive chat loop for polishing an already-generated
resume or cover letter's JSON. Each turn sends the current document plus
one plain-English instruction to Gemini (schema-constrained, same
schema/model the builder already uses) and gets back the complete
updated document; a diff of exactly what changed is shown before
anything is saved. Accepting a turn re-renders HTML and regenerates the
PDF immediately, same as the main tailoring pipeline.
"""

import os

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(SCRIPT_DIR)
OUTPUT_JSON_DIR = os.path.join(PROJECT_ROOT, "output", "json")
OUTPUT_HTML_DIR = os.path.join(PROJECT_ROOT, "output", "html")
OUTPUT_PDF_DIR = os.path.join(PROJECT_ROOT, "output", "pdf")

RESUME_SUFFIX = "_Resume.json"
COVERLETTER_SUFFIX = "_CoverLetter.json"


def detect_doc_type(path: str) -> str | None:
    """Returns "resume", "coverletter", or None if the filename doesn't
    end in a recognized suffix."""
    name = os.path.basename(path)
    if name.endswith(RESUME_SUFFIX):
        return "resume"
    if name.endswith(COVERLETTER_SUFFIX):
        return "coverletter"
    return None


def stem_from_json_path(path: str, doc_type: str) -> str:
    """Strips the doc_type's known suffix, returning the shared stem used
    to derive matching html/pdf output paths."""
    name = os.path.basename(path)
    suffix = RESUME_SUFFIX if doc_type == "resume" else COVERLETTER_SUFFIX
    return name[: -len(suffix)]
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `python -m unittest tests.test_polish -v`
Expected: PASS (5 tests).

- [ ] **Step 5: Commit**

```bash
git add scripts/polish.py tests/test_polish.py
git commit -m "feat: add polish.py doc-type detection and output stem helper"
```

---

### Task 2: Field-level diff renderer

**Files:**
- Modify: `scripts/polish.py`
- Modify: `tests/test_polish.py`

**Interfaces:**
- Consumes: nothing from Task 1 (pure functions, no new imports needed).
- Produces: `polish.diff_documents(old: dict, new: dict, keys: list[str]) -> list[str]` — one human-readable line (or set of lines) per changed field, restricted to `keys`. `EXPERIENCE` gets per-job, per-field, per-achievement-index treatment; other list fields (e.g. `body_paragraphs`) get index-wise comparison; everything else is a plain scalar comparison. Later tasks call this with `keys=polish.RESUME_FIELDS` or `polish.COVERLETTER_FIELDS` (defined in Task 3).

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_polish.py`:

```python
class TestDiffDocuments(unittest.TestCase):

    def test_identical_documents_produce_no_diff(self):
        doc = {"TAGLINE": "SAME", "SKILLS": ["Python"]}
        self.assertEqual(polish.diff_documents(doc, dict(doc), ["TAGLINE", "SKILLS"]), [])

    def test_scalar_field_change_is_reported(self):
        old = {"TAGLINE": "OLD"}
        new = {"TAGLINE": "NEW"}
        lines = polish.diff_documents(old, new, ["TAGLINE"])
        self.assertEqual(len(lines), 1)
        self.assertIn("TAGLINE", lines[0])
        self.assertIn("OLD", lines[0])
        self.assertIn("NEW", lines[0])

    def test_field_outside_keys_is_never_reported(self):
        old = {"TAGLINE": "OLD", "NAME": "Morgan Escott"}
        new = {"TAGLINE": "OLD", "NAME": "Someone Else"}
        lines = polish.diff_documents(old, new, ["TAGLINE"])
        self.assertEqual(lines, [])

    def test_plain_list_field_reports_only_changed_indices(self):
        old = {"SKILLS": ["Python", "SQL", "Excel"]}
        new = {"SKILLS": ["Python", "Postgres", "Excel"]}
        lines = polish.diff_documents(old, new, ["SKILLS"])
        self.assertEqual(len(lines), 1)
        self.assertIn("SKILLS[1]", lines[0])
        self.assertIn("SQL", lines[0])
        self.assertIn("Postgres", lines[0])

    def test_experience_reports_changed_scalar_field_by_index(self):
        old = {"EXPERIENCE": [{"title": "Old Title", "achievements": ["A"]}]}
        new = {"EXPERIENCE": [{"title": "New Title", "achievements": ["A"]}]}
        lines = polish.diff_documents(old, new, ["EXPERIENCE"])
        self.assertEqual(len(lines), 1)
        self.assertIn("EXPERIENCE[0].title", lines[0])

    def test_experience_reports_changed_achievement_by_index(self):
        old = {"EXPERIENCE": [{"title": "Same", "achievements": ["A", "B"]}]}
        new = {"EXPERIENCE": [{"title": "Same", "achievements": ["A", "B changed"]}]}
        lines = polish.diff_documents(old, new, ["EXPERIENCE"])
        self.assertEqual(len(lines), 1)
        self.assertIn("EXPERIENCE[0].achievements[1]", lines[0])

    def test_unchanged_experience_job_produces_no_lines(self):
        old = {"EXPERIENCE": [{"title": "Same", "achievements": ["A"]}]}
        new = {"EXPERIENCE": [{"title": "Same", "achievements": ["A"]}]}
        self.assertEqual(polish.diff_documents(old, new, ["EXPERIENCE"]), [])
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python -m unittest tests.test_polish -v`
Expected: FAIL — `AttributeError: module 'polish' has no attribute 'diff_documents'`.

- [ ] **Step 3: Add the diff functions to `scripts/polish.py`**

Append to `scripts/polish.py`:

```python
def _diff_list(label: str, old_list: list, new_list: list) -> list[str]:
    lines = []
    for i in range(max(len(old_list), len(new_list))):
        old_item = old_list[i] if i < len(old_list) else None
        new_item = new_list[i] if i < len(new_list) else None
        if old_item != new_item:
            lines.append(f"{label}[{i}]:\n  - {old_item!r}\n  + {new_item!r}")
    return lines


def _diff_experience(old_jobs: list, new_jobs: list) -> list[str]:
    lines = []
    scalar_fields = ("title", "company", "period", "location", "career_note")
    for i in range(max(len(old_jobs), len(new_jobs))):
        old_job = old_jobs[i] if i < len(old_jobs) else {}
        new_job = new_jobs[i] if i < len(new_jobs) else {}
        if old_job == new_job:
            continue
        for field in scalar_fields:
            if old_job.get(field) != new_job.get(field):
                lines.append(
                    f"EXPERIENCE[{i}].{field}:\n  - {old_job.get(field)!r}\n  + {new_job.get(field)!r}"
                )
        lines.extend(_diff_list(
            f"EXPERIENCE[{i}].achievements",
            old_job.get("achievements", []),
            new_job.get("achievements", []),
        ))
    return lines


def diff_documents(old: dict, new: dict, keys: list[str]) -> list[str]:
    """Field-by-field diff restricted to `keys` (a schema's own field
    list -- contact info/certifications/education/_recommendation_actions
    are never in `keys`, so they never surface here, since a polish turn
    can't touch them anyway). EXPERIENCE gets element-and-field-level
    treatment via _diff_experience; other list fields (e.g.
    body_paragraphs) via _diff_list; everything else is a plain scalar
    comparison."""
    lines = []
    for key in keys:
        old_val = old.get(key)
        new_val = new.get(key)
        if old_val == new_val:
            continue
        if key == "EXPERIENCE" and isinstance(old_val, list) and isinstance(new_val, list):
            lines.extend(_diff_experience(old_val, new_val))
        elif isinstance(old_val, list) and isinstance(new_val, list):
            lines.extend(_diff_list(key, old_val, new_val))
        else:
            lines.append(f"{key}:\n  - {old_val!r}\n  + {new_val!r}")
    return lines
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `python -m unittest tests.test_polish -v`
Expected: PASS (12 tests).

- [ ] **Step 5: Commit**

```bash
git add scripts/polish.py tests/test_polish.py
git commit -m "feat: add field-level diff renderer to polish.py"
```

---

### Task 3: `generate_candidate()` — the Gemini call

**Files:**
- Modify: `scripts/polish.py`
- Modify: `tests/test_polish.py`

**Interfaces:**
- Consumes: `orchestrator.TemplateSchema`, `orchestrator.CoverLetterSchema`, `orchestrator.BUILDER_MODEL`, `orchestrator.ResumeEngine` (for `.load_prompt(filename)` and `.load_yaml(dir, filename)`), `gemini_client.GeminiClient.generate(...)` / `.parse_json(text)`, `normalize_resume.normalize(dict) -> dict`, `validate_resume.validate(dict, dict) -> list[str]`, `validate_coverletter.validate(dict, dict) -> list[str]`, `cli_art.console`/`cli_art.WARNING` — all pre-existing, no changes needed to any of them.
- Produces: `polish.RESUME_FIELDS: list[str]`, `polish.COVERLETTER_FIELDS: list[str]`, `polish.generate_candidate(doc: dict, instruction: str, doc_type: str, engine) -> dict | None`. Task 6's main loop calls this with a real `orchestrator.ResumeEngine()` instance.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_polish.py` (add `import json` and `from unittest.mock import patch` to the file's existing imports, and `import orchestrator` alongside the existing `import polish`):

```python
import json
from unittest.mock import patch

import orchestrator  # noqa: E402


class TestGenerateCandidate(unittest.TestCase):

    def setUp(self):
        self.engine = orchestrator.ResumeEngine()

    @patch("polish.GeminiClient.generate")
    def test_unparseable_response_returns_none(self, mock_generate):
        mock_generate.return_value = ("not valid json", {})
        result = polish.generate_candidate(
            {"TAGLINE": "OLD"}, "make it punchier", "resume", self.engine,
        )
        self.assertIsNone(result)

    @patch("polish.GeminiClient.generate")
    def test_resume_path_normalizes_and_reattaches_recommendation_actions(self, mock_generate):
        gemini_json = json.dumps({
            "TAGLINE": "new tagline",
            "SECTION_SUMMARY": "Professional Summary",
            "SUMMARY_TEXT": "<strong>Summary.</strong>",
            "SECTION_EXPERIENCE": "Work Experience",
            "EXPERIENCE": [],
            "KU_ACHIEVEMENT_KEY": "content_generalist",
            "KCKCC_ACHIEVEMENT_KEY": "generalist",
            "SECTION_SKILLS": "Skills",
            "SKILLS": ["Python"],
            "SECTION_WHY": "",
            "WHY_TEXT": "",
        })
        mock_generate.return_value = (gemini_json, {})

        original_doc = {
            "TAGLINE": "OLD TAGLINE",
            "_recommendation_actions": {"applied": ["x"], "skipped": []},
        }
        candidate = polish.generate_candidate(
            original_doc, "punch up the tagline", "resume", self.engine,
        )

        self.assertIsNotNone(candidate)
        # normalize_resume.normalize() upper-cases TAGLINE
        self.assertEqual(candidate["TAGLINE"], "NEW TAGLINE")
        # non-schema tracking key must survive the round trip unchanged
        self.assertEqual(candidate["_recommendation_actions"], {"applied": ["x"], "skipped": []})
        # normalize() injects fixed_content.CONTACT_INFO
        self.assertEqual(candidate["NAME"], "Morgan Escott")

    @patch("polish.GeminiClient.generate")
    def test_resume_path_with_no_recommendation_actions_does_not_add_one(self, mock_generate):
        gemini_json = json.dumps({
            "TAGLINE": "TAG", "SECTION_SUMMARY": "Professional Summary",
            "SUMMARY_TEXT": "s", "SECTION_EXPERIENCE": "Work Experience",
            "EXPERIENCE": [], "KU_ACHIEVEMENT_KEY": "content_generalist",
            "KCKCC_ACHIEVEMENT_KEY": "generalist", "SECTION_SKILLS": "Skills",
            "SKILLS": [], "SECTION_WHY": "", "WHY_TEXT": "",
        })
        mock_generate.return_value = (gemini_json, {})
        candidate = polish.generate_candidate({"TAGLINE": "TAG"}, "noop", "resume", self.engine)
        self.assertNotIn("_recommendation_actions", candidate)

    @patch("polish.GeminiClient.generate")
    def test_coverletter_path_does_not_run_resume_normalization(self, mock_generate):
        gemini_json = json.dumps({
            "company_name": "Acme",
            "greeting": "Dear Hiring Team,",
            "body_paragraphs": ["Paragraph one.", "Paragraph two."],
            "sign_off": "Sincerely,",
        })
        mock_generate.return_value = (gemini_json, {})

        candidate = polish.generate_candidate(
            {"company_name": "Acme", "greeting": "Hi,", "body_paragraphs": [], "sign_off": ""},
            "make the greeting more formal", "coverletter", self.engine,
        )
        self.assertEqual(candidate["greeting"], "Dear Hiring Team,")
        self.assertNotIn("NAME", candidate)
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python -m unittest tests.test_polish -v`
Expected: FAIL — `AttributeError: module 'polish' has no attribute 'GeminiClient'` (or `generate_candidate` missing).

- [ ] **Step 3: Add the imports and `generate_candidate()` to `scripts/polish.py`**

Add these imports at the top of `scripts/polish.py`, just below the existing `import os`:

```python
import json

import cli_art
import normalize_resume
import validate_coverletter
import validate_resume
from gemini_client import GeminiClient
from orchestrator import BUILDER_MODEL, CoverLetterSchema, ResumeEngine, TemplateSchema
```

Append to `scripts/polish.py`:

```python
RESUME_FIELDS = list(TemplateSchema.model_fields.keys())
COVERLETTER_FIELDS = list(CoverLetterSchema.model_fields.keys())


def generate_candidate(doc: dict, instruction: str, doc_type: str, engine: ResumeEngine) -> dict | None:
    """Sends the current document's schema-relevant fields plus one
    instruction to Gemini and returns the complete updated document, or
    None if the response was unparseable. Resume responses are re-run
    through normalize_resume.normalize() (idempotent -- reapplies fixed
    contact/cert/education fields and formatting rules) and have
    _recommendation_actions (not part of TemplateSchema) reattached
    unchanged if the original had it."""
    if doc_type == "resume":
        schema = TemplateSchema
        prompt_file = "polish_resume.md"
        fields = RESUME_FIELDS
    else:
        schema = CoverLetterSchema
        prompt_file = "polish_coverletter.md"
        fields = COVERLETTER_FIELDS

    sendable = {k: doc.get(k) for k in fields}
    system_instruction = engine.load_prompt(prompt_file)
    contents = (
        f"=== CURRENT DOCUMENT JSON ===\n{json.dumps(sendable, indent=2)}\n\n"
        f"=== REQUESTED EDIT ===\n{instruction}"
    )

    text, _usage = GeminiClient.generate(
        model=BUILDER_MODEL,
        system_instruction=system_instruction,
        contents=contents,
        response_schema=schema,
        temperature=0.0,
    )
    result = GeminiClient.parse_json(text or "")
    if not result:
        return None

    style_rules = engine.load_yaml(engine.rules_dir, "style_rules.yaml")
    if doc_type == "resume":
        candidate = normalize_resume.normalize(result)
        if "_recommendation_actions" in doc:
            candidate["_recommendation_actions"] = doc["_recommendation_actions"]
        violations = validate_resume.validate(candidate, style_rules)
    else:
        candidate = result
        violations = validate_coverletter.validate(candidate, style_rules)

    if violations:
        cli_art.console.print(f"{cli_art.WARNING} Validator found {len(violations)} issue(s) in this edit:")
        for v in violations:
            cli_art.console.print(f"  - {v}")

    return candidate
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `python -m unittest tests.test_polish -v`
Expected: PASS (16 tests).

- [ ] **Step 5: Commit**

```bash
git add scripts/polish.py tests/test_polish.py
git commit -m "feat: add generate_candidate() Gemini call to polish.py"
```

---

### Task 4: `save_and_render()` — write JSON, re-render HTML+PDF

**Files:**
- Modify: `scripts/polish.py`
- Modify: `tests/test_polish.py`

**Interfaces:**
- Consumes: `polish.stem_from_json_path` (Task 1), `render_html.render_html(dict, str) -> str`, `render_coverletter.render_coverletter(dict, str) -> str` (both pre-existing, imported directly).
- Produces: `polish.save_and_render(doc: dict, doc_type: str, json_path: str) -> dict` returning `{"json": str, "html": str, "pdf": str | None}` (`"pdf"` is `None` on a failed `generate-pdf.mjs` run; `"json"`/`"html"` are still written in that case).

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_polish.py` (add `from unittest.mock import MagicMock, patch` — extend the existing `unittest.mock` import to include `MagicMock`):

```python
class TestSaveAndRender(unittest.TestCase):

    def setUp(self):
        self.tmp_dir = os.path.join(os.path.dirname(__file__), "_tmp_polish_save")
        os.makedirs(self.tmp_dir, exist_ok=True)
        self.resume_json_path = os.path.join(self.tmp_dir, "MorganEscott_Title_Company_Resume.json")
        self.coverletter_json_path = os.path.join(self.tmp_dir, "MorganEscott_Title_Company_CoverLetter.json")

        self._real_html_dir = polish.OUTPUT_HTML_DIR
        self._real_pdf_dir = polish.OUTPUT_PDF_DIR
        polish.OUTPUT_HTML_DIR = os.path.join(self.tmp_dir, "html")
        polish.OUTPUT_PDF_DIR = os.path.join(self.tmp_dir, "pdf")

    def tearDown(self):
        polish.OUTPUT_HTML_DIR = self._real_html_dir
        polish.OUTPUT_PDF_DIR = self._real_pdf_dir
        for root, dirs, files in os.walk(self.tmp_dir, topdown=False):
            for name in files:
                os.remove(os.path.join(root, name))
            for name in dirs:
                os.rmdir(os.path.join(root, name))
        os.rmdir(self.tmp_dir)

    @patch("polish.subprocess.run")
    @patch("polish.render_html")
    def test_resume_paths_and_success(self, mock_render, mock_run):
        mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")

        result = polish.save_and_render({"TAGLINE": "X"}, "resume", self.resume_json_path)

        self.assertTrue(os.path.exists(self.resume_json_path))
        expected_html = os.path.join(polish.OUTPUT_HTML_DIR, "MorganEscott_Title_Company_Resume.html")
        expected_pdf = os.path.join(polish.OUTPUT_PDF_DIR, "MorganEscott_Title_Company_Resume.pdf")
        self.assertEqual(result, {"json": self.resume_json_path, "html": expected_html, "pdf": expected_pdf})
        mock_render.assert_called_once_with({"TAGLINE": "X"}, expected_html)

    @patch("polish.subprocess.run")
    @patch("polish.render_html")
    def test_pdf_failure_returns_none_pdf_but_keeps_json_and_html(self, mock_render, mock_run):
        mock_run.return_value = MagicMock(returncode=1, stdout="", stderr="boom")

        result = polish.save_and_render({"TAGLINE": "X"}, "resume", self.resume_json_path)

        self.assertTrue(os.path.exists(self.resume_json_path))
        self.assertIsNone(result["pdf"])

    @patch("polish.subprocess.run")
    @patch("polish.render_coverletter")
    def test_coverletter_uses_coverletter_renderer(self, mock_render, mock_run):
        mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")

        result = polish.save_and_render(
            {"greeting": "Hi,"}, "coverletter", self.coverletter_json_path,
        )

        expected_html = os.path.join(polish.OUTPUT_HTML_DIR, "MorganEscott_Title_Company_CoverLetter.html")
        mock_render.assert_called_once_with({"greeting": "Hi,"}, expected_html)
        self.assertEqual(result["html"], expected_html)
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python -m unittest tests.test_polish -v`
Expected: FAIL — `AttributeError: module 'polish' has no attribute 'save_and_render'`.

- [ ] **Step 3: Add the imports and `save_and_render()` to `scripts/polish.py`**

Add these imports at the top of `scripts/polish.py`, alongside the existing ones:

```python
import subprocess

from render_coverletter import render_coverletter
from render_html import render_html
```

Append to `scripts/polish.py`:

```python
def save_and_render(doc: dict, doc_type: str, json_path: str) -> dict:
    """Saves `doc` to json_path, re-renders its HTML, and regenerates its
    PDF via generate-pdf.mjs. Returns {"json": ..., "html": ..., "pdf":
    ...} -- "pdf" is None if PDF generation failed (JSON/HTML are still
    saved in that case; the caller decides what to tell the user)."""
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(doc, f, indent=2, ensure_ascii=False)

    stem = stem_from_json_path(json_path, doc_type)
    suffix = "_Resume" if doc_type == "resume" else "_CoverLetter"
    html_path = os.path.join(OUTPUT_HTML_DIR, f"{stem}{suffix}.html")
    pdf_path = os.path.join(OUTPUT_PDF_DIR, f"{stem}{suffix}.pdf")
    os.makedirs(os.path.dirname(html_path), exist_ok=True)
    os.makedirs(os.path.dirname(pdf_path), exist_ok=True)

    if doc_type == "resume":
        render_html(doc, html_path)
    else:
        render_coverletter(doc, html_path)

    pdf_script = os.path.join(SCRIPT_DIR, "generate-pdf.mjs")
    result = subprocess.run(
        ["node", pdf_script, html_path, pdf_path, "--format=letter"],
        capture_output=True, text=True,
    )
    if result.returncode != 0:
        cli_art.console.print(
            f"{cli_art.WARNING} PDF generation failed (JSON/HTML were still saved):\n{result.stderr}"
        )
        return {"json": json_path, "html": html_path, "pdf": None}

    return {"json": json_path, "html": html_path, "pdf": pdf_path}
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `python -m unittest tests.test_polish -v`
Expected: PASS (19 tests).

- [ ] **Step 5: Commit**

```bash
git add scripts/polish.py tests/test_polish.py
git commit -m "feat: add save_and_render() to polish.py"
```

---

### Task 5: `pick_polish_target()` — interactive file picker

**Files:**
- Modify: `scripts/polish.py`
- Modify: `tests/test_polish.py`

**Interfaces:**
- Consumes: `polish.detect_doc_type` (Task 1), `polish.OUTPUT_JSON_DIR` (Task 1), `cli_art.QUESTIONARY_STYLE` (pre-existing).
- Produces: `polish.pick_polish_target() -> str | None` — `None` if `output/json/` has no recognized files or the user cancels the picker.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_polish.py` (add `import time` to the file's existing imports):

```python
class TestPickPolishTarget(unittest.TestCase):

    def setUp(self):
        self.tmp_dir = os.path.join(os.path.dirname(__file__), "_tmp_polish_picker")
        os.makedirs(self.tmp_dir, exist_ok=True)
        self._real_json_dir = polish.OUTPUT_JSON_DIR
        polish.OUTPUT_JSON_DIR = self.tmp_dir

    def tearDown(self):
        polish.OUTPUT_JSON_DIR = self._real_json_dir
        for name in os.listdir(self.tmp_dir):
            os.remove(os.path.join(self.tmp_dir, name))
        os.rmdir(self.tmp_dir)

    def _touch(self, name, mtime_offset):
        path = os.path.join(self.tmp_dir, name)
        with open(path, "w") as f:
            f.write("{}")
        now = time.time()
        os.utime(path, (now + mtime_offset, now + mtime_offset))
        return path

    def test_empty_dir_returns_none(self):
        self.assertIsNone(polish.pick_polish_target())

    def test_unrecognized_files_are_excluded(self):
        self._touch("random.json", 0)
        self.assertIsNone(polish.pick_polish_target())

    @patch("polish.questionary.select")
    def test_newest_first_and_labeled(self, mock_select):
        older = self._touch("A_Resume.json", -10)
        newer = self._touch("B_CoverLetter.json", 0)
        mock_select.return_value.ask.return_value = newer

        result = polish.pick_polish_target()

        self.assertEqual(result, newer)
        choices = mock_select.call_args.kwargs["choices"]
        self.assertEqual(choices[0].value, newer)
        self.assertEqual(choices[0].title, "[Cover Letter] B_CoverLetter.json")
        self.assertEqual(choices[1].value, older)
        self.assertEqual(choices[1].title, "[Resume] A_Resume.json")
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python -m unittest tests.test_polish -v`
Expected: FAIL — `AttributeError: module 'polish' has no attribute 'pick_polish_target'`.

- [ ] **Step 3: Add the imports and `pick_polish_target()` to `scripts/polish.py`**

Add these imports at the top of `scripts/polish.py`, alongside the existing ones:

```python
import glob

import questionary
```

Append to `scripts/polish.py`:

```python
def pick_polish_target() -> str | None:
    """Interactive picker over every recognized output/json file, newest
    first. Returns None if there's nothing to pick (empty dir, or the
    user cancels)."""
    paths = sorted(
        glob.glob(os.path.join(OUTPUT_JSON_DIR, "*.json")),
        key=os.path.getmtime, reverse=True,
    )
    choices = []
    for p in paths:
        doc_type = detect_doc_type(p)
        if doc_type is None:
            continue
        label = "Resume" if doc_type == "resume" else "Cover Letter"
        choices.append(questionary.Choice(title=f"[{label}] {os.path.basename(p)}", value=p))
    if not choices:
        return None
    return questionary.select(
        "Which document do you want to polish?", choices=choices, style=cli_art.QUESTIONARY_STYLE,
    ).ask()
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `python -m unittest tests.test_polish -v`
Expected: PASS (22 tests).

- [ ] **Step 5: Commit**

```bash
git add scripts/polish.py tests/test_polish.py
git commit -m "feat: add pick_polish_target() interactive picker to polish.py"
```

---

### Task 6: The chat loop — `run_polish_session()` and `run()`

**Files:**
- Modify: `scripts/polish.py`
- Modify: `tests/test_polish.py`

**Interfaces:**
- Consumes: `polish.detect_doc_type`, `polish.RESUME_FIELDS`/`polish.COVERLETTER_FIELDS`, `polish.generate_candidate`, `polish.diff_documents`, `polish.save_and_render`, `polish.pick_polish_target`, `orchestrator.ResumeEngine`, `questionary.text`/`questionary.select`, `cli_art.console`/`cli_art.SUCCESS`/`cli_art.WARNING`/`cli_art.ERROR`/`cli_art.QUESTIONARY_STYLE` — all already defined by prior tasks or pre-existing.
- Produces: `polish.run_polish_session(json_path: str) -> None`, `polish.run(file: str | None = None) -> None`. Task 7's CLI/menu wiring calls `polish.run(file)`.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_polish.py`:

```python
class TestRunPolishSession(unittest.TestCase):

    def setUp(self):
        self.tmp_dir = os.path.join(os.path.dirname(__file__), "_tmp_polish_session")
        os.makedirs(self.tmp_dir, exist_ok=True)
        self.json_path = os.path.join(self.tmp_dir, "MorganEscott_Title_Company_Resume.json")
        with open(self.json_path, "w") as f:
            json.dump({"TAGLINE": "OLD"}, f)

    def tearDown(self):
        for name in os.listdir(self.tmp_dir):
            os.remove(os.path.join(self.tmp_dir, name))
        os.rmdir(self.tmp_dir)

    def test_unrecognized_suffix_does_not_enter_loop(self):
        bad_path = os.path.join(self.tmp_dir, "not_a_recognized_name.json")
        with open(bad_path, "w") as f:
            f.write("{}")
        with patch("polish.questionary.text") as mock_text:
            polish.run_polish_session(bad_path)
        mock_text.assert_not_called()

    def test_missing_file_does_not_enter_loop(self):
        with patch("polish.questionary.text") as mock_text:
            polish.run_polish_session(os.path.join(self.tmp_dir, "Nope_Resume.json"))
        mock_text.assert_not_called()

    @patch("polish.questionary.text")
    def test_exit_word_ends_loop_without_calling_gemini(self, mock_text):
        mock_text.return_value.ask.return_value = "done"
        with patch("polish.generate_candidate") as mock_generate:
            polish.run_polish_session(self.json_path)
        mock_generate.assert_not_called()

    @patch("polish.questionary.text")
    def test_none_from_ask_ends_loop_like_exit(self, mock_text):
        mock_text.return_value.ask.return_value = None
        with patch("polish.generate_candidate") as mock_generate:
            polish.run_polish_session(self.json_path)
        mock_generate.assert_not_called()

    @patch("polish.questionary.text")
    @patch("polish.generate_candidate")
    def test_unparseable_candidate_reprompts_without_saving(self, mock_generate, mock_text):
        mock_text.return_value.ask.side_effect = ["do a thing", "done"]
        mock_generate.return_value = None
        with patch("polish.save_and_render") as mock_save:
            polish.run_polish_session(self.json_path)
        mock_save.assert_not_called()

    @patch("polish.questionary.text")
    @patch("polish.generate_candidate")
    def test_no_diff_reprompts_without_saving(self, mock_generate, mock_text):
        mock_text.return_value.ask.side_effect = ["do a thing", "done"]
        mock_generate.return_value = {"TAGLINE": "OLD"}  # identical to what's on disk
        with patch("polish.save_and_render") as mock_save:
            polish.run_polish_session(self.json_path)
        mock_save.assert_not_called()

    @patch("polish.questionary.select")
    @patch("polish.questionary.text")
    @patch("polish.generate_candidate")
    def test_reject_keeps_state_and_does_not_save(self, mock_generate, mock_text, mock_select):
        mock_text.return_value.ask.side_effect = ["make it punchier", "done"]
        mock_generate.return_value = {"TAGLINE": "NEW"}
        mock_select.return_value.ask.return_value = "reject"
        with patch("polish.save_and_render") as mock_save:
            polish.run_polish_session(self.json_path)
        mock_save.assert_not_called()

    @patch("polish.questionary.select")
    @patch("polish.questionary.text")
    @patch("polish.generate_candidate")
    def test_accept_saves_the_candidate(self, mock_generate, mock_text, mock_select):
        mock_text.return_value.ask.side_effect = ["make it punchier", "done"]
        mock_generate.return_value = {"TAGLINE": "NEW"}
        mock_select.return_value.ask.return_value = "accept"
        with patch(
            "polish.save_and_render",
            return_value={"json": self.json_path, "html": "h", "pdf": "p"},
        ) as mock_save:
            polish.run_polish_session(self.json_path)
        mock_save.assert_called_once_with({"TAGLINE": "NEW"}, "resume", self.json_path)

    @patch("polish.questionary.select")
    @patch("polish.questionary.text")
    @patch("polish.generate_candidate")
    def test_quit_choice_ends_loop(self, mock_generate, mock_text, mock_select):
        mock_text.return_value.ask.return_value = "make it punchier"
        mock_generate.return_value = {"TAGLINE": "NEW"}
        mock_select.return_value.ask.return_value = "quit"
        with patch("polish.save_and_render") as mock_save:
            polish.run_polish_session(self.json_path)
        mock_save.assert_not_called()


class TestRun(unittest.TestCase):

    @patch("polish.run_polish_session")
    @patch("polish.pick_polish_target")
    def test_uses_given_file_without_picker(self, mock_pick, mock_session):
        polish.run("some/path_Resume.json")
        mock_pick.assert_not_called()
        mock_session.assert_called_once_with("some/path_Resume.json")

    @patch("polish.run_polish_session")
    @patch("polish.pick_polish_target")
    def test_uses_picker_when_no_file_given(self, mock_pick, mock_session):
        mock_pick.return_value = "picked_Resume.json"
        polish.run(None)
        mock_session.assert_called_once_with("picked_Resume.json")

    @patch("polish.run_polish_session")
    @patch("polish.pick_polish_target")
    def test_nothing_to_pick_does_not_enter_session(self, mock_pick, mock_session):
        mock_pick.return_value = None
        polish.run(None)
        mock_session.assert_not_called()
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python -m unittest tests.test_polish -v`
Expected: FAIL — `AttributeError: module 'polish' has no attribute 'run_polish_session'`.

- [ ] **Step 3: Add `run_polish_session()` and `run()` to `scripts/polish.py`**

Append to `scripts/polish.py`:

```python
_EXIT_WORDS = {"", "done", "exit", "quit"}


def run_polish_session(json_path: str) -> None:
    """Runs the interactive polish loop against json_path until the user
    exits. Each turn: prompt for an instruction, generate a candidate,
    show its diff, then accept (save + re-render) / reject (discard,
    keep chatting) / quit."""
    doc_type = detect_doc_type(json_path)
    if doc_type is None:
        cli_art.console.print(
            f"{cli_art.ERROR} {json_path} doesn't end in {RESUME_SUFFIX} or {COVERLETTER_SUFFIX} -- "
            "can't tell which schema to polish against."
        )
        return
    if not os.path.exists(json_path):
        cli_art.console.print(f"{cli_art.ERROR} File not found: {json_path}")
        return

    with open(json_path, "r", encoding="utf-8") as f:
        doc = json.load(f)

    engine = ResumeEngine()
    fields = RESUME_FIELDS if doc_type == "resume" else COVERLETTER_FIELDS

    cli_art.console.print(f"\nPolishing {os.path.basename(json_path)}. Type 'done' to finish.\n")

    while True:
        try:
            instruction = questionary.text("polish>", style=cli_art.QUESTIONARY_STYLE).ask()
        except (KeyboardInterrupt, EOFError):
            instruction = None

        if instruction is None or instruction.strip().lower() in _EXIT_WORDS:
            break

        candidate = generate_candidate(doc, instruction, doc_type, engine)
        if candidate is None:
            cli_art.console.print(f"{cli_art.WARNING} No parseable response -- try rephrasing.")
            continue

        diff_lines = diff_documents(doc, candidate, fields)
        if not diff_lines:
            cli_art.console.print("Nothing changed -- try rephrasing.")
            continue

        cli_art.console.print("\n".join(diff_lines))
        decision = questionary.select(
            "Apply this change?",
            choices=[
                questionary.Choice(title="Accept", value="accept"),
                questionary.Choice(title="Reject and rephrase", value="reject"),
                questionary.Choice(title="Quit", value="quit"),
            ],
            style=cli_art.QUESTIONARY_STYLE,
        ).ask()

        if decision == "quit" or decision is None:
            break
        if decision == "reject":
            continue

        doc = candidate
        paths = save_and_render(doc, doc_type, json_path)
        cli_art.console.print(f"{cli_art.SUCCESS} Saved -> {paths['json']}")
        if paths["pdf"]:
            cli_art.console.print(f"{cli_art.SUCCESS} PDF -> {paths['pdf']}")

    cli_art.console.print("\nDone polishing.\n")


def run(file: str | None = None) -> None:
    """Entry point wired from cli.py's `resume polish [FILE]` command and
    menu.py's interactive-menu entry. Uses `file` if given, otherwise
    launches the interactive picker."""
    json_path = file or pick_polish_target()
    if not json_path:
        cli_art.console.print("Nothing to polish -- no output/json files found.")
        return
    run_polish_session(json_path)
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `python -m unittest tests.test_polish -v`
Expected: PASS (34 tests).

- [ ] **Step 5: Commit**

```bash
git add scripts/polish.py tests/test_polish.py
git commit -m "feat: add polish chat loop (run_polish_session/run)"
```

---

### Task 7: Wire `resume polish` into the CLI, menu, and shell shortcut

**Files:**
- Modify: `scripts/cli.py`
- Modify: `scripts/menu.py`
- Modify: `scripts/resume-cli.sh`
- Create: `tests/test_cli_polish.py`

**Interfaces:**
- Consumes: `polish.run(file: str | None) -> None` (Task 6).
- Produces: `resume polish [FILE]` CLI command; a matching interactive-menu entry; a matching `resume-cli.sh` case + help line.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_cli_polish.py`:

```python
import os
import sys
import unittest
from unittest.mock import patch

SCRIPTS_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts")
sys.path.insert(0, SCRIPTS_DIR)

from click.testing import CliRunner  # noqa: E402
import cli  # noqa: E402


class TestPolishCommand(unittest.TestCase):

    def test_no_file_launches_picker_path(self):
        with patch("cli.polish_module.run") as mock_run:
            runner = CliRunner()
            result = runner.invoke(cli.cli, ["polish"])
        self.assertEqual(result.exit_code, 0)
        mock_run.assert_called_once_with(None)

    def test_file_argument_is_forwarded(self):
        with patch("cli.polish_module.run") as mock_run:
            runner = CliRunner()
            result = runner.invoke(cli.cli, ["polish", "README.md"])
        self.assertEqual(result.exit_code, 0)
        mock_run.assert_called_once_with("README.md")

    def test_nonexistent_file_argument_errors(self):
        runner = CliRunner()
        result = runner.invoke(cli.cli, ["polish", "definitely/does/not/exist.json"])
        self.assertNotEqual(result.exit_code, 0)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python -m unittest tests.test_cli_polish -v`
Expected: FAIL — `AttributeError: module 'cli' has no attribute 'polish_module'` (or `click.exceptions.UsageError: No such command 'polish'`).

- [ ] **Step 3: Wire the command into `scripts/cli.py`**

Add this import in `scripts/cli.py` alongside the existing `import scan as scan_module` / `import liveness as liveness_module` lines:

```python
import polish as polish_module
```

Add this command anywhere among the other `@cli.command()` definitions (e.g. right after the `liveness_cmd` command, before the `if __name__ == "__main__":` block):

```python
@cli.command()
@click.argument("file", required=False, type=click.Path(exists=True))
def polish(file):
    """Interactively polish an already-generated resume or cover letter."""
    polish_module.run(file)
```

- [ ] **Step 4: Run the CLI tests to verify they pass**

Run: `python -m unittest tests.test_cli_polish -v`
Expected: PASS (3 tests).

- [ ] **Step 5: Wire the menu entry into `scripts/menu.py`**

Add this import in `scripts/menu.py` alongside the existing `import liveness as liveness_module` line:

```python
import polish as polish_module
```

Add a new choice to `_CHOICES`, just before the `"Exit"` entry:

```python
    questionary.Choice(title="Polish a resume or cover letter", value="polish"),
```

Add a handler function alongside the other `_handle_*` functions:

```python
def _handle_polish():
    polish_module.run(None)
```

Add it to `_HANDLERS`, alongside the other entries:

```python
    "polish": _handle_polish,
```

- [ ] **Step 6: Wire the shell shortcut into `scripts/resume-cli.sh`**

Add a new case in the shell function's `case "$cmd" in` block, right after the existing `liveness)` case:

```bash
    polish)
      ( cd "$_RESUME_BUILDER_DIR" && source .venv/bin/activate && python scripts/cli.py polish "$@" )
      ;;
```

Add a new line to the `help)` case's output, right after the existing liveness help line:

```bash
      echo "  resume polish           interactively polish an already-generated resume/cover letter"
```

- [ ] **Step 7: Run the full test suite to verify nothing broke**

Run: `python -m unittest discover -s tests -v`
Expected: PASS (every test, including the new `test_polish.py` and `test_cli_polish.py`).

- [ ] **Step 8: Commit**

```bash
git add scripts/cli.py scripts/menu.py scripts/resume-cli.sh tests/test_cli_polish.py
git commit -m "feat: wire resume polish into cli, menu, and shell shortcut"
```

- [ ] **Step 9: Live verification**

Run `resume polish` (or `python scripts/cli.py polish`) against a real file in `output/json/`, make one real edit request (e.g. "make the tagline punchier"), confirm:
1. The diff shown actually matches what changed.
2. Accepting it writes the JSON, regenerates the HTML, and regenerates the PDF (check `output/pdf/<stem>.pdf`'s modified time and open it to confirm the change shows up).
3. Typing `done` exits cleanly back to the shell.

---

## Self-Review Notes

- **Spec coverage:** Entry point + file selection → Task 7 (picker → Task 5). Edit mechanism (schema reuse, normalize/validate, prompt files) → Task 3 (prompts already created in Prep). Diff & confirm → Tasks 2 and 6. Save/re-render → Task 4. Loop exit → Task 6. All five spec sections have a task.
- **Placeholder scan:** No TBD/TODO markers; every step has complete, runnable code.
- **Type consistency:** `generate_candidate(doc, instruction, doc_type, engine)` (Task 3) is called identically in Task 6. `save_and_render(doc, doc_type, json_path) -> dict` (Task 4) is called identically in Task 6, and its return shape (`{"json", "html", "pdf"}`) matches what Task 6 reads (`paths["json"]`, `paths["pdf"]`). `diff_documents(old, new, keys)` (Task 2) is called with `RESUME_FIELDS`/`COVERLETTER_FIELDS` (Task 3) in Task 6 — same names throughout.
