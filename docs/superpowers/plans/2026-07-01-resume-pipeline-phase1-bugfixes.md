# Resume Pipeline Phase 1: Bug Fixes Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix five independent, low-risk bugs in the resume-tailoring pipeline
that are actively violating `ResumeDesignSystem.md` on every run: a silently-empty
keyword-extraction prompt, two schema-required sections that don't exist in the
spec, a wrong section-header fallback, a wrong PDF margin, and a discarded
page-count signal.

**Architecture:** Each fix is scoped to the smallest set of files that must
change together, with a unit test proving the bug existed and now doesn't.
No architectural changes — this phase is pure bug-fixing ahead of the bigger
Phase 3 validation-layer project (see
`docs/superpowers/specs/2026-07-01-resume-spec-enforcement-design.md`).

**Tech Stack:** Python 3.10+, stdlib `unittest` (no pytest installed), Pydantic,
Node/Playwright for PDF generation (no JS test runner configured — verify
`generate-pdf.mjs` changes via a Python test that reads its source).

## Global Constraints

- Run all Python tests from the project root:
  `python3 -m unittest tests.<module> -v` (per `CLAUDE.md`; stdlib unittest,
  not pytest).
- Use `/usr/local/bin/python3.13` or an equivalent venv — bare `python3` may
  resolve to an unrelated stray venv on this machine (per `.claude.local.md`).
- Never touch `resume-engine/knowledge_base/` source-of-truth files (`cv.md`,
  `profile.yml`, bullet bank archives) — out of scope for this plan.
- Follow existing test conventions in `tests/test_orchestrator_build_checkpoint.py`:
  patch `orchestrator.subprocess.run`, `orchestrator.render_html`,
  `orchestrator.GeminiClient.generate` (never make real API/subprocess calls
  in tests).
- Every task must end with a passing test run and a commit. Commit messages
  end with `Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>`.

---

### Task 1: Fix silent fallback for missing prompt files, finalize extract_keywords.md

**Files:**
- Modify: `scripts/orchestrator.py:657-663` (`ResumeEngine.load_prompt`)
- Rename: `resume-engine/prompts/extract_keywords.DRAFT.md` →
  `resume-engine/prompts/extract_keywords.md`
- Test: Create `tests/test_orchestrator_load_prompt.py`

**Interfaces:**
- Consumes: `orchestrator.ResumeEngine()` (existing constructor, no args).
- Produces: `ResumeEngine.load_prompt(filename: str) -> str` now raises
  `FileNotFoundError` instead of returning the placeholder string
  `"Process the text."` on a missing file. No other task depends on this
  signature changing.

- [ ] **Step 1: Write the failing test**

```python
import os
import sys
import unittest

SCRIPTS_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts")
sys.path.insert(0, SCRIPTS_DIR)

import orchestrator  # noqa: E402


class TestLoadPromptFailsLoudly(unittest.TestCase):

    def setUp(self):
        self.engine = orchestrator.ResumeEngine()

    def test_missing_prompt_file_raises_instead_of_silent_fallback(self):
        with self.assertRaises(FileNotFoundError):
            self.engine.load_prompt("this_file_does_not_exist.md")

    def test_extract_keywords_prompt_file_exists_and_loads_real_content(self):
        content = self.engine.load_prompt("extract_keywords.md")
        self.assertNotEqual(content.strip(), "Process the text.")
        self.assertIn("tools", content)
        self.assertIn("hard_skills", content)
        self.assertIn("core_functions", content)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m unittest tests.test_orchestrator_load_prompt -v`
Expected: FAIL — `test_missing_prompt_file_raises_instead_of_silent_fallback`
fails because no exception is raised (current code returns the placeholder
string); `test_extract_keywords_prompt_file_exists_and_loads_real_content`
fails because `extract_keywords.md` doesn't exist yet, so `load_prompt`
returns `"Process the text."`, which fails the `assertNotEqual`.

- [ ] **Step 3: Rename the draft prompt file**

```bash
git mv resume-engine/prompts/extract_keywords.DRAFT.md resume-engine/prompts/extract_keywords.md
```

- [ ] **Step 4: Remove the silent fallback in `load_prompt`**

In `scripts/orchestrator.py`, replace:

```python
    def load_prompt(self, filename):
        path = os.path.join(self.prompts_dir, filename)
        try:
            with open(path, "r") as f:
                return f.read()
        except FileNotFoundError:
            return "Process the text."
```

with:

```python
    def load_prompt(self, filename):
        path = os.path.join(self.prompts_dir, filename)
        with open(path, "r") as f:
            return f.read()
```

- [ ] **Step 5: Run test to verify it passes**

Run: `python3 -m unittest tests.test_orchestrator_load_prompt -v`
Expected: PASS (2 tests)

- [ ] **Step 6: Run the full existing suite to confirm nothing else relied on the silent fallback**

Run:
```bash
python3 -m unittest tests.test_jd_manager tests.test_orchestrator_audit_resume tests.test_orchestrator_build_checkpoint tests.test_orchestrator_main_batch tests.test_orchestrator_load_prompt -v
```
Expected: all PASS. (Confirmed safe ahead of time: `critique_bullet.md`,
`tailor_resume.md`, and `critique_resume.md` — the other three files loaded
via `load_prompt` — all already exist on disk, so removing the fallback
cannot break those call sites.)

- [ ] **Step 7: Commit**

```bash
git add scripts/orchestrator.py tests/test_orchestrator_load_prompt.py
git add resume-engine/prompts/extract_keywords.md
git rm resume-engine/prompts/extract_keywords.DRAFT.md 2>/dev/null; git add -u resume-engine/prompts/
git commit -m "$(cat <<'EOF'
Fix silent fallback on missing prompt files; finalize extract_keywords.md

load_prompt() was swallowing FileNotFoundError and returning the placeholder
"Process the text.", so the JD keyword-extraction step ran with no real
instructions on every single resume (it asked for extract_keywords.md, which
never existed — only extract_keywords.DRAFT.md did). Renamed the draft into
place and made load_prompt() fail loudly so this class of bug can't recur
silently.

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
EOF
)"
```

---

### Task 2: Delete PROJECTS and COMPETENCIES sections entirely

**Files:**
- Modify: `scripts/orchestrator.py:550-629` (`TemplateSchema`)
- Modify: `scripts/render_html.py` (remove `build_competencies_html`,
  `build_projects_html`, their call sites, and their scalar defaults)
- Modify: `resume-engine/templates/cv-template.html` (remove Core Competencies
  and Projects CSS blocks and section markup)
- Modify: `resume-engine/prompts/tailor_resume.md` (remove
  `SECTION_COMPETENCIES`/`COMPETENCIES`/`SECTION_PROJECTS`/`PROJECTS`
  references from the output schema section)
- Test: Create `tests/test_render_html.py`

**Interfaces:**
- Consumes: `orchestrator.TemplateSchema` (Pydantic model), `render_html.render_html(resume_data: dict, output_path: str) -> str`.
- Produces: `TemplateSchema` no longer has `COMPETENCIES`, `SECTION_COMPETENCIES`,
  `PROJECTS`, or `SECTION_PROJECTS` fields. `render_html()` output never
  contains a Competencies or Projects section regardless of what's in
  `resume_data`. Task 3 (below) builds on the same `render_html.py` and adds
  to the same new test file.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_render_html.py`:

```python
import os
import sys
import unittest

SCRIPTS_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts")
sys.path.insert(0, SCRIPTS_DIR)

import orchestrator  # noqa: E402
from render_html import render_html  # noqa: E402


def _minimal_resume_data(**overrides):
    data = {
        "NAME": "Test Candidate",
        "TAGLINE": "TEST TAGLINE",
        "SUMMARY_TEXT": "<strong>Test summary.</strong>",
        "SKILLS": [],
        "EXPERIENCE": [],
        "EDUCATION": [],
        "CERTIFICATIONS": [],
    }
    data.update(overrides)
    return data


class TestNoProjectsOrCompetencies(unittest.TestCase):

    def setUp(self):
        self.out_path = os.path.join(os.path.dirname(__file__), "_tmp_no_projects.html")

    def tearDown(self):
        if os.path.exists(self.out_path):
            os.remove(self.out_path)

    def test_template_schema_has_no_competencies_or_projects_fields(self):
        fields = orchestrator.TemplateSchema.model_fields
        self.assertNotIn("COMPETENCIES", fields)
        self.assertNotIn("SECTION_COMPETENCIES", fields)
        self.assertNotIn("PROJECTS", fields)
        self.assertNotIn("SECTION_PROJECTS", fields)

    def test_rendered_html_has_no_competencies_or_projects_markup(self):
        render_html(_minimal_resume_data(), self.out_path)
        with open(self.out_path, "r", encoding="utf-8") as f:
            html = f.read()
        self.assertNotIn("Core Competencies", html)
        self.assertNotIn("competency-tag", html)
        self.assertNotIn("Selected Projects", html)
        self.assertNotIn("project-title", html)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m unittest tests.test_render_html -v`
Expected: FAIL — both tests fail (`COMPETENCIES`/`PROJECTS` fields still
present in `TemplateSchema`; `"Core Competencies"` and `"Selected Projects"`
still render).

- [ ] **Step 3: Remove COMPETENCIES and PROJECTS from `TemplateSchema`**

In `scripts/orchestrator.py`, in the `TemplateSchema` class docstring, replace:

```python
    """
    Flattened schema for the builder call.
    EXPERIENCE/PROJECTS/EDUCATION/CERTIFICATIONS are List[dict] to avoid
    deeply-nested $defs in responseSchema that caused the builder 400.
    """
```

with:

```python
    """
    Flattened schema for the builder call.
    EXPERIENCE/EDUCATION/CERTIFICATIONS are List[dict] to avoid
    deeply-nested $defs in responseSchema that caused the builder 400.
    """
```

Then remove these two lines entirely:

```python
    SECTION_COMPETENCIES:   str       = Field(default="Core Competencies")
    COMPETENCIES:           List[str] = Field(min_length=6, max_length=8, description="6-8 exact keywords extracted from JD requirements.")
```

Then remove this whole block entirely:

```python
    SECTION_PROJECTS:       str       = Field(default="Projects")
    PROJECTS:               List[dict] = Field(
        min_length=3, max_length=4,
        description=(
            "Top 3-4 most relevant projects. Each dict must contain: "
            "title (str), badge (str, leave blank if none), "
            "description (str, 1-2 sentence impact summary), "
            "tech (str, comma-separated tech stack, leave blank if not applicable)."
        )
    )
```

- [ ] **Step 4: Remove COMPETENCIES/PROJECTS rendering from `render_html.py`**

Delete the `build_competencies_html` function entirely:

```python
def build_competencies_html(competencies: list[str]) -> str:
    """Renders core competencies as .competency-tag spans."""
    return "".join(f'<span class="competency-tag">{escape(c)}</span>' for c in competencies)
```

Delete the `build_projects_html` function entirely:

```python
def build_projects_html(projects: list[dict]) -> str:
    """Renders the projects section."""
    html = []
    for p in projects:
        badge = f'<span class="project-badge">{escape(p["badge"])}</span>' if p.get("badge") else ""
        tech  = f'<div class="project-tech">{escape(p["tech"])}</div>'     if p.get("tech")  else ""
        html.append(f"""
        <div class="project">
          <div class="project-title">{escape(p.get("title",""))}{badge}</div>
          <div class="project-desc">{escape(p.get("description",""))}</div>
          {tech}
        </div>""")
    return "\n".join(html)
```

In `render_html()`, remove these two lines from the `scalars` dict:

```python
        "SECTION_COMPETENCIES":   resume_data.get("SECTION_COMPETENCIES",   "Core Competencies"),
        "SECTION_PROJECTS":       resume_data.get("SECTION_PROJECTS",       "Selected Projects"),
```

And remove these two `html.replace` calls:

```python
    html = html.replace("{{COMPETENCIES}}",   build_competencies_html(resume_data.get("COMPETENCIES", [])))
    html = html.replace("{{PROJECTS}}",       build_projects_html(resume_data.get("PROJECTS", [])))
```

- [ ] **Step 5: Remove Competencies/Projects markup and CSS from `cv-template.html`**

Remove this entire CSS block from the `<style>` section:

```css
  /* === CORE COMPETENCIES === */
  .competencies-grid {
    display: flex;
    flex-wrap: wrap;
    gap: 4px 0;
  }

  .competency-tag {
    font-family: 'DM Sans', sans-serif;
    font-size: 9.75pt;
    font-weight: 400;
    color: #000000;
  }

  .competency-tag::after {
    content: ' | ';
    color: #9aa3af;
    padding: 0 4px;
  }

  .competency-tag:last-child::after {
    content: '';
  }
```

Remove this entire CSS block from the `<style>` section:

```css
  /* === PROJECTS ===
     Rendered by render_pdf using ProjectItem: title, badge, description, tech */
  .project {
    margin-bottom: 10px;
    break-inside: avoid;
    page-break-inside: avoid;
  }

  .project-title {
    font-family: 'DM Sans', sans-serif;
    font-size: 10.5pt;
    font-weight: 600;
    color: #000000;
    margin-bottom: 2px;
  }

  .project-badge {
    display: inline-block;
    font-size: 8pt;
    font-weight: 600;
    color: hsl(187, 74%, 32%);
    border: 1px solid hsl(187, 74%, 32%);
    border-radius: 3px;
    padding: 0 5px;
    margin-left: 6px;
    vertical-align: middle;
    line-height: 1.6;
    letter-spacing: 0.04em;
    text-transform: uppercase;
  }

  .project-desc {
    font-size: 10.5pt;
    color: #000000;
    line-height: 1.55;
  }

  .project-tech {
    font-size: 9.75pt;
    color: #555555;
    margin-top: 2px;
    font-style: italic;
  }
```

Remove this markup block:

```html
  <!-- CORE COMPETENCIES -->
  <div class="section avoid-break">
    <div class="section-title">{{SECTION_COMPETENCIES}}</div>
    <div class="competencies-grid">
      {{COMPETENCIES}}
    </div>
  </div>
```

Remove this markup block:

```html
  <!-- PROJECTS -->
  <div class="section">
    <div class="section-title">{{SECTION_PROJECTS}}</div>
    {{PROJECTS}}
  </div>
```

- [ ] **Step 6: Remove COMPETENCIES/PROJECTS from `tailor_resume.md`'s output schema**

In `resume-engine/prompts/tailor_resume.md`, remove the lines:

```
- SECTION_COMPETENCIES = "Core Competencies"
```
```
- SECTION_PROJECTS = "Projects"
```

Remove this entire subsection:

````
## COMPETENCIES (array of 6–8 strings)
Each string is one exact JD keyword. Example:
```json
["Lifecycle Marketing", "CRM Strategy", "A/B Testing", "Salesforce", "Pipeline Generation", "Content Governance"]
```
````

Remove this entire subsection:

````
## PROJECTS (array of objects)
Each object has these exact keys:
```json
{
  "title": "Project Name",
  "badge": "Featured",
  "description": "1-2 sentence impact summary.",
  "tech": "Tool A, Tool B"
}
```
- `badge`: short type label — e.g. `"Open Source"`, `"Featured"`, `"AI"`. Use `""` if none.
- `tech`: comma-separated stack. Use `""` if not applicable.
- Include 3–4 projects. Choose the most relevant to the JD archetype.
````

- [ ] **Step 7: Run test to verify it passes**

Run: `python3 -m unittest tests.test_render_html -v`
Expected: PASS (2 tests)

- [ ] **Step 8: Run the full suite**

Run:
```bash
python3 -m unittest tests.test_jd_manager tests.test_orchestrator_audit_resume tests.test_orchestrator_build_checkpoint tests.test_orchestrator_main_batch tests.test_orchestrator_load_prompt tests.test_render_html -v
```
Expected: all PASS.

- [ ] **Step 9: Commit**

```bash
git add scripts/orchestrator.py scripts/render_html.py resume-engine/templates/cv-template.html resume-engine/prompts/tailor_resume.md tests/test_render_html.py
git commit -m "$(cat <<'EOF'
Delete PROJECTS and COMPETENCIES sections from the resume pipeline

Neither section exists anywhere in ResumeDesignSystem.md's canonical section
list (Professional Summary, Skills, Work Experience, Training &
Certifications, Education, Why). TemplateSchema made both Pydantic-required
(6-8 competencies, 3-4 projects), forcing the builder to fabricate content
for both on every single resume. Removed from the schema, the HTML template,
render_html.py's rendering functions, and tailor_resume.md's output spec.

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
EOF
)"
```

---

### Task 3: Fix "Core Skills" fallback default to "Skills"

**Files:**
- Modify: `scripts/render_html.py:193`
- Test: Modify `tests/test_render_html.py` (add one test to the class from Task 2)

**Interfaces:**
- Consumes: `render_html.render_html(resume_data: dict, output_path: str) -> str` (unchanged signature).
- Produces: no new interface; purely a default-value fix.

- [ ] **Step 1: Write the failing test**

Add to `tests/test_render_html.py`'s `TestNoProjectsOrCompetencies` class (reuses
`_minimal_resume_data` and the class's `setUp`/`tearDown`):

```python
    def test_missing_section_skills_key_falls_back_to_skills_not_core_skills(self):
        data = _minimal_resume_data()
        data.pop("SECTION_SKILLS", None)  # confirm it's absent
        render_html(data, self.out_path)
        with open(self.out_path, "r", encoding="utf-8") as f:
            html = f.read()
        self.assertIn(">Skills<", html)
        self.assertNotIn("Core Skills", html)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m unittest tests.test_render_html -v`
Expected: FAIL — `test_missing_section_skills_key_falls_back_to_skills_not_core_skills`
fails because the rendered HTML contains `"Core Skills"`, not `"Skills"`.

- [ ] **Step 3: Fix the default**

In `scripts/render_html.py`, replace:

```python
        "SECTION_SKILLS":         resume_data.get("SECTION_SKILLS",         "Core Skills"),
```

with:

```python
        "SECTION_SKILLS":         resume_data.get("SECTION_SKILLS",         "Skills"),
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m unittest tests.test_render_html -v`
Expected: PASS (3 tests)

- [ ] **Step 5: Commit**

```bash
git add scripts/render_html.py tests/test_render_html.py
git commit -m "$(cat <<'EOF'
Fix Skills section header fallback default: "Core Skills" to "Skills"

ResumeDesignSystem.md requires the header to read exactly "Skills";
render_html.py's fallback (used only if the builder ever omits
SECTION_SKILLS) defaulted to the wrong string.

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
EOF
)"
```

---

### Task 4: Fix PDF margin: 0.6in to 0.5in

**Files:**
- Modify: `scripts/generate-pdf.mjs`
- Test: Create `tests/test_generate_pdf_margins.py`

**Interfaces:**
- Consumes: none (standalone Node script invoked via subprocess elsewhere).
- Produces: no interface change — this is a literal-value fix. No JS test
  runner is configured in this repo (`package.json`'s `test` script is a
  stub), so this is verified with a Python test that reads the script's
  source text directly rather than executing Playwright.

- [ ] **Step 1: Write the failing test**

Create `tests/test_generate_pdf_margins.py`:

```python
import os
import re
import unittest

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PDF_SCRIPT = os.path.join(PROJECT_ROOT, "scripts", "generate-pdf.mjs")


class TestPdfMargins(unittest.TestCase):

    def test_pdf_margins_are_half_inch_per_design_spec(self):
        with open(PDF_SCRIPT, "r", encoding="utf-8") as f:
            source = f.read()
        margin_block_match = re.search(r"margin:\s*\{([^}]+)\}", source)
        self.assertIsNotNone(margin_block_match, "Could not find margin: {...} block in generate-pdf.mjs")
        margin_block = margin_block_match.group(1)
        self.assertNotIn("0.6in", margin_block)
        for side in ("top", "right", "bottom", "left"):
            self.assertIn(f"{side}: '0.5in'", margin_block)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m unittest tests.test_generate_pdf_margins -v`
Expected: FAIL — current margins are `'0.6in'`, not `'0.5in'`.

- [ ] **Step 3: Fix the margins**

In `scripts/generate-pdf.mjs`, replace:

```javascript
      margin: {
        top: '0.6in',
        right: '0.6in',
        bottom: '0.6in',
        left: '0.6in',
      },
```

with:

```javascript
      margin: {
        top: '0.5in',
        right: '0.5in',
        bottom: '0.5in',
        left: '0.5in',
      },
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m unittest tests.test_generate_pdf_margins -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add scripts/generate-pdf.mjs tests/test_generate_pdf_margins.py
git commit -m "$(cat <<'EOF'
Fix PDF margins: 0.6in to 0.5in per design spec

ResumeDesignSystem.md requires 0.5in margins on all sides; the Playwright
page.pdf() call hardcoded 0.6in, shrinking the usable content width on every
generated resume.

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
EOF
)"
```

---

### Task 5: Capture real PDF page count instead of discarding it

**Files:**
- Modify: `scripts/orchestrator.py:1399-1424` (`build_tailored_resume`, Step 7)
- Test: Modify `tests/test_orchestrator_build_checkpoint.py`

**Interfaces:**
- Consumes: `subprocess.run(["node", pdf_script, ...], capture_output=True, text=True)`
  (existing call; `pdf_result.stdout` now gets parsed, not just checked for
  return code).
- Produces: `build_tailored_resume()`'s returned `resume_data` dict now
  includes a `"_page_count"` key: `int` if `generate-pdf.mjs`'s
  `📊 Pages: N` line was found in stdout, else `None`. This is a read-only
  signal for this task — Phase 3's validator/retry-loop design is what
  consumes `_page_count` to actually enforce the 2-page rule; this task only
  stops silently discarding it and logs a warning when it's already over 2.

- [ ] **Step 1: Write the failing test**

Add to `tests/test_orchestrator_build_checkpoint.py` (reuses the existing
`TestBuildCheckpointResume` class, `_pass_critique_json`, and fixture setup):

```python
    @patch("orchestrator.subprocess.run")
    @patch("orchestrator.render_html")
    @patch("orchestrator.GeminiClient.generate")
    @patch("orchestrator.time.sleep", lambda *a, **kw: None)
    def test_captures_page_count_from_pdf_stdout(
        self, mock_generate, mock_render_html, mock_subprocess_run
    ):
        jd_manager.save_checkpoint(self.job_key, {
            "jd_keywords": {"hard_skills": ["python"]},
            "bullet_tuples": [["Shipped a widget platform used by 10k users.", "Acme", "eng"]],
        })

        def generate_side_effect(*args, **kwargs):
            schema = kwargs.get("response_schema")
            if schema is orchestrator.CritiqueSchema:
                return (_pass_critique_json(), {})
            if schema is orchestrator.TemplateSchema:
                return (json.dumps({"SUMMARY": "Test summary."}), {})
            if schema is orchestrator.ResumeCritiqueSchema:
                return (json.dumps({
                    "summary_alignment_score": 90, "skills_relevance_score": 90,
                    "overall_fit_score": 90, "flags": [], "recommendations": [],
                }), {})
            raise AssertionError(f"Unexpected response_schema in test: {schema}")

        mock_generate.side_effect = generate_side_effect
        mock_subprocess_run.return_value = MagicMock(
            returncode=0,
            stdout="📄 Input:  x\n📁 Output: y\n📏 Format: LETTER\n✅ PDF generated: y\n📊 Pages: 3\n📦 Size: 42.0 KB\n",
            stderr="",
        )

        with patch.object(self.engine, "mine_bullet_bank"):
            result = self.engine.build_tailored_resume(
                jd_path=self.jd_path,
                master_resume={},
                output_filename=self.output_filename,
                job_key=self.job_key,
            )

        self.assertEqual(result.get("_page_count"), 3)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m unittest tests.test_orchestrator_build_checkpoint -v`
Expected: FAIL — `test_captures_page_count_from_pdf_stdout` fails with a
`KeyError`/`None` mismatch because `_page_count` doesn't exist on the
returned dict yet.

- [ ] **Step 3: Parse and store the page count**

In `scripts/orchestrator.py`, in `build_tailored_resume`'s Step 7, replace:

```python
        pdf_result = subprocess.run(
            ["node", pdf_script, html_out, pdf_out, "--format=letter"],
            capture_output=True, text=True
        )
        if pdf_result.returncode != 0:
            print(f"  ⚠️  PDF generation failed:\n{pdf_result.stderr}")
            return {}

        print(pdf_result.stdout)
        print(f"  🎉 Pipeline complete! PDF → {pdf_out}")
        jd_manager.delete_checkpoint(job_key)
        resume_data["_output_paths"] = {"json": output_path, "html": html_out, "pdf": pdf_out}

        return resume_data
```

with:

```python
        pdf_result = subprocess.run(
            ["node", pdf_script, html_out, pdf_out, "--format=letter"],
            capture_output=True, text=True
        )
        if pdf_result.returncode != 0:
            print(f"  ⚠️  PDF generation failed:\n{pdf_result.stderr}")
            return {}

        print(pdf_result.stdout)

        page_count_match = re.search(r"Pages:\s*(\d+)", pdf_result.stdout)
        page_count = int(page_count_match.group(1)) if page_count_match else None
        if page_count is not None and page_count > 2:
            print(f"  ⚠️  WARNING: PDF is {page_count} pages — spec requires exactly 2. "
                  f"(Automatic trim-and-retry is not implemented yet; see Phase 3.)")

        print(f"  🎉 Pipeline complete! PDF → {pdf_out}")
        jd_manager.delete_checkpoint(job_key)
        resume_data["_output_paths"] = {"json": output_path, "html": html_out, "pdf": pdf_out}
        resume_data["_page_count"] = page_count

        return resume_data
```

`re` is already imported at the top of `scripts/orchestrator.py` (line 5) —
no new import needed.

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m unittest tests.test_orchestrator_build_checkpoint -v`
Expected: PASS (3 tests in this file)

- [ ] **Step 5: Run the full suite**

Run:
```bash
python3 -m unittest tests.test_jd_manager tests.test_orchestrator_audit_resume tests.test_orchestrator_build_checkpoint tests.test_orchestrator_main_batch tests.test_orchestrator_load_prompt tests.test_render_html tests.test_generate_pdf_margins -v
```
Expected: all PASS.

- [ ] **Step 6: Commit**

```bash
git add scripts/orchestrator.py tests/test_orchestrator_build_checkpoint.py
git commit -m "$(cat <<'EOF'
Capture real PDF page count instead of discarding it

generate-pdf.mjs already computes and prints an actual page count, but
build_tailored_resume() only checked the subprocess return code and threw
that number away -- the "exactly 2 pages" rule was never checked anywhere.
Now parsed from stdout, stored on the returned resume_data as _page_count,
and a warning is logged when it's already over 2. Enforcement (automatic
trim-and-retry) is Phase 3's job, not this bugfix pass.

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
EOF
)"
```

---

## Self-Review Notes

- **Spec coverage:** All 5 items are load-bearing findings from the audit in
  `docs/superpowers/specs/2026-07-01-resume-spec-enforcement-design.md`'s
  "Silent/broken wiring" list. The remaining audit findings (verb-rule
  contradictions, banned-phrase unification, formatting_rules.yaml/ats_rules.yaml
  retirement, summary scoring metric, orphaned files) are explicitly Phase
  2/3 work per that doc's sequencing and are covered in the separate Phase 2
  and Phase 3 plans, not duplicated here.
- **Placeholder scan:** no TBD/TODO; every step shows literal before/after
  code.
- **Type consistency:** `load_prompt` signature (`filename: str -> str`)
  unchanged across tasks; `render_html(resume_data: dict, output_path: str) -> str`
  unchanged; `_page_count` is a new dict key, not a new function signature,
  so no cross-task type drift.
- **Ordering:** Tasks 2 and 3 both touch `render_html.py` and
  `tests/test_render_html.py` — Task 3 explicitly builds on the file Task 2
  creates. Do not run Task 3 before Task 2 lands.
