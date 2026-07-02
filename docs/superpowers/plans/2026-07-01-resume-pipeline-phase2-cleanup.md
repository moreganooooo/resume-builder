# Resume Pipeline Phase 2: Cleanup and Critique Consolidation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Delete the dead/orphaned prompts and scoring rubrics identified in the spec-enforcement audit, retire the two scoring rubrics that now score sections Phase 1 deleted (Projects/Competencies), fix `summary_score.yaml`'s wrong length metric, and fold the unique "first impression / top third of page one" evaluation from `hiring_manager_scan.md` + `top_third_score.yaml` into the live `critique_resume.md` critique instead of leaving it as a dead duplicate prompt.

**Architecture:** This phase only touches the advisory critique layer (`critique_resume.md`, `ResumeCritiqueSchema`, `resume-engine/scoring/*.yaml`) and dead prompt files. It does not touch the builder (`tailor_resume.md`, `TemplateSchema`'s generated fields) or add any enforcement/gating — that's Phase 3. Every YAML/prompt content edit that has a mechanically-checkable property gets a real regression test; pure prose/comment edits get a literal before/after diff and a grep-based verification step instead of a unit test.

**Tech Stack:** Python 3.10+, stdlib `unittest`, PyYAML (already a dependency, used via `orchestrator.py`'s existing `self.load_yaml()` pattern).

## Global Constraints

- Run all Python tests via `/usr/local/bin/python3.13 -m unittest tests.<module> -v` (stdlib unittest, not pytest).
- Never touch `resume-engine/knowledge_base/` source-of-truth files.
- Every task ends with a passing test run and its own commit.
- This phase does not touch `scripts/orchestrator.py`'s `TemplateSchema`, `tailor_resume.md`, or anything in the builder call path (Step 4 of `build_tailored_resume`) — only the Step 5 critique call and its supporting prompt/schema/scoring files.
- Do not implement any retry/gating/enforcement logic — this phase is content correctness only. Enforcement is Phase 3 (`docs/superpowers/specs/2026-07-01-resume-spec-enforcement-design.md`).

## Execution Strategy (token-budget optimization)

Dispatch as 2 batches, not 6 individual task dispatches, to cut subagent overhead:

- **Batch A — Tasks 1-4:** one Haiku implementer dispatch covering all four (each is small, independent, and fully specified with literal before/after content). One Haiku reviewer dispatch on the combined diff.
- **Batch B — Tasks 5-6:** one Haiku implementer dispatch (Task 6 depends on Task 5's output, so they must run in that order within the batch). One Sonnet reviewer dispatch — Task 5 touches the live Step 5 critique API call path, worth slightly more reviewer scrutiny than pure content edits.
- **Final whole-branch review:** one Sonnet dispatch (not Opus) covering the full phase diff.

Keep per-task TDD discipline intact within each batch (failing test before implementation, full suite before the batch's commit(s)) — the savings come from fewer dispatches and cheaper models, not from skipping verification. A batch may still produce one commit per task internally (each task's own commit message), or one combined commit per batch if that reads more cleanly — either is fine as long as the batch's own tests all pass before moving to the next batch.

---

### Task 1: Delete dead prompts and clean up Phase 1's leftover minor findings

**Files:**
- Delete: `resume-engine/prompts/diagnose_resume.md`
- Delete: `resume-engine/prompts/recruiter_scan.md`
- Delete: `resume-engine/prompts/rank_bullets.md`
- Modify: `scripts/orchestrator.py` (remove `ProjectItem` model; fix `ResumeCritiqueSchema.skills_relevance_score`'s description)
- Modify: `resume-engine/templates/cv-template.html` (fix stale `.project` comment)
- Modify: `resume-engine/scoring/recruiter_score.yaml` (fix stale reference to the just-deleted `recruiter_scan.md`)
- Test: Create `tests/test_orchestrator_schema_cleanup.py`

**Interfaces:**
- Consumes: `orchestrator.ResumeCritiqueSchema` (Pydantic model, unchanged shape — only a field description string changes).
- Produces: `orchestrator` module no longer exposes a `ProjectItem` class. No other task in this plan depends on this.

**Context:** `diagnose_resume.md` (14 lines, no rubric), `recruiter_scan.md` (17 lines, a "6-second recruiter pass" persona), and `rank_bullets.md` (14 lines, an LLM-based bullet-sorter) are never loaded anywhere in `scripts/orchestrator.py` — confirmed by grep during the audit. `diagnose_resume.md` and `recruiter_scan.md` have no unique content worth keeping (their ideas are already covered, more rigorously, by `hiring_manager_scan.md`'s Top-Third Test, which Task 5 below folds into the live critique). `rank_bullets.md`'s idea — sort bullets by `manager_test` pass/fail then a score — is a deterministic sort over data the pipeline already computes, which belongs in Phase 3's validator as plain Python, not as a separate LLM prompt; there is no current call site for it, so deleting the file loses nothing live. The final whole-branch review of Phase 1 flagged three small leftovers: `orchestrator.py`'s `ProjectItem` model (dead since Phase 1 deleted the `PROJECTS` schema field but never removed this now-unused Pydantic class), `ResumeCritiqueSchema.skills_relevance_score`'s description still saying "are Skills and Competencies JD-relevant?" (Competencies no longer exists), and `cv-template.html`'s page-break-control comment still listing `.project` among the classes that carry `break-inside: avoid` (the `.project` CSS rule itself was deleted in Phase 1).

- [ ] **Step 1: Write the failing tests**

Create `tests/test_orchestrator_schema_cleanup.py`:

```python
import os
import sys
import unittest

SCRIPTS_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts")
sys.path.insert(0, SCRIPTS_DIR)

import orchestrator  # noqa: E402


class TestSchemaCleanup(unittest.TestCase):

    def test_project_item_model_no_longer_exists(self):
        self.assertFalse(hasattr(orchestrator, "ProjectItem"))

    def test_skills_relevance_score_description_has_no_stale_competencies_reference(self):
        field = orchestrator.ResumeCritiqueSchema.model_fields["skills_relevance_score"]
        self.assertNotIn("Competencies", field.description)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `/usr/local/bin/python3.13 -m unittest tests.test_orchestrator_schema_cleanup -v`
Expected: FAIL — `ProjectItem` still exists; the description still contains `"Competencies"`.

- [ ] **Step 3: Delete the three dead prompt files**

```bash
git rm resume-engine/prompts/diagnose_resume.md resume-engine/prompts/recruiter_scan.md resume-engine/prompts/rank_bullets.md
```

- [ ] **Step 4: Remove `ProjectItem` and fix the stale schema description**

In `scripts/orchestrator.py`, remove this class entirely (it has zero references anywhere in the codebase — confirmed by grep):

```python
class ProjectItem(BaseModel):
    title:       str = Field(description="Project name.")
    badge:       str = Field(default="", description="Short type label, e.g. 'Open Source', 'Featured', 'AI'. Leave blank if none.")
    description: str = Field(description="1-2 sentence impact summary.")
    tech:        str = Field(default="", description="Comma-separated tech stack. Leave blank if not applicable.")
```

Then, in `ResumeCritiqueSchema`, replace:

```python
    skills_relevance_score:  int       = Field(description="0-100: are Skills and Competencies JD-relevant?")
```

with:

```python
    skills_relevance_score:  int       = Field(description="0-100: are Skills JD-relevant?")
```

- [ ] **Step 5: Fix the stale CSS comment**

In `resume-engine/templates/cv-template.html`, replace:

```css
  /* === PAGE BREAK CONTROL ===
     .job, .edu-item, .cert-item, .project each carry break-inside: avoid
     in their own rules above. .avoid-break is kept as a general utility
     class for header and small single-block sections. */
```

with:

```css
  /* === PAGE BREAK CONTROL ===
     .job, .edu-item, .cert-item each carry break-inside: avoid
     in their own rules above. .avoid-break is kept as a general utility
     class for header and small single-block sections. */
```

- [ ] **Step 6: Fix the stale `recruiter_scan.md` reference**

In `resume-engine/scoring/recruiter_score.yaml`, replace:

```yaml
# Was a generic 5-category weight stub disconnected from its stated purpose.
# Rewritten to match critique_resume.md's own description of this file --
# "Recruiter first-pass readability and signal clarity" -- and to mirror the
# 6-second-glance persona/criteria defined in recruiter_scan.md, as a scoring
# rubric rather than a standalone prompt persona.
```

with:

```yaml
# Was a generic 5-category weight stub disconnected from its stated purpose.
# Rewritten to match critique_resume.md's own description of this file --
# "Recruiter first-pass readability and signal clarity" -- as a mechanical
# 6-second-glance scannability rubric, independent of narrative quality.
```

- [ ] **Step 7: Run test to verify it passes**

Run: `/usr/local/bin/python3.13 -m unittest tests.test_orchestrator_schema_cleanup -v`
Expected: PASS (2 tests)

- [ ] **Step 8: Verify the comment fixes and deletions with grep (no test framework for prose)**

```bash
grep -rn "recruiter_scan\|rank_bullets\|diagnose_resume" resume-engine/ scripts/
```
Expected output: only `resume-engine/scoring/manager_test.yaml`'s line referencing `hiring_manager_scan.md` (untouched by this task — Task 5 handles that file), and no remaining references to the three deleted files anywhere else.

- [ ] **Step 9: Run the full existing suite**

Run:
```bash
/usr/local/bin/python3.13 -m unittest tests.test_jd_manager tests.test_orchestrator_audit_resume tests.test_orchestrator_build_checkpoint tests.test_orchestrator_main_batch tests.test_orchestrator_load_prompt tests.test_render_html tests.test_generate_pdf_margins tests.test_orchestrator_schema_cleanup -v
```
Expected: all PASS.

- [ ] **Step 10: Commit**

```bash
git add scripts/orchestrator.py resume-engine/templates/cv-template.html resume-engine/scoring/recruiter_score.yaml tests/test_orchestrator_schema_cleanup.py
git commit -m "$(cat <<'EOF'
Delete dead prompts and clean up Phase 1's leftover minor findings

diagnose_resume.md, recruiter_scan.md, and rank_bullets.md are never loaded
by orchestrator.py and duplicate logic that hiring_manager_scan.md (folded
into critique_resume.md in a later task) already covers more rigorously.
Also removes the orphaned ProjectItem model, the stale "Competencies"
reference in ResumeCritiqueSchema, and two stale comments left over from
Phase 1's Projects/Competencies deletion.

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
EOF
)"
```

---

### Task 2: Retire competencies_score.yaml; trim specificity.yaml to Education-only

**Files:**
- Delete: `resume-engine/scoring/competencies_score.yaml`
- Modify: `resume-engine/scoring/specificity.yaml`
- Modify: `resume-engine/prompts/critique_resume.md`
- Test: Create `tests/test_scoring_yaml_content.py`

**Interfaces:**
- Consumes: none (pure content files).
- Produces: `resume-engine/scoring/specificity.yaml` no longer contains any `project_*` criteria/penalties/bonuses. Task 6 (README rewrite) depends on this task and Task 3 having already run, since it documents the final file list.

**Context:** Phase 1 deleted the `PROJECTS` and `COMPETENCIES` sections from every generated resume — they don't exist anymore. `competencies_score.yaml` exists solely to score the now-nonexistent Competencies section (`required_rule: every_competency_must_be_supported_by_resume_evidence`), so it has nothing left to score. `specificity.yaml` scores both Projects (60 of its 100 points: `project_description_specificity` weight 40, `project_tech_specificity` weight 20) and Education (`education_description_specificity` weight 40) — the Projects half needs to go, the Education half stays (Education is still fully LLM-generated at this point in the plan; Phase 3 is what makes it deterministic).

- [ ] **Step 1: Write the failing test**

Create `tests/test_scoring_yaml_content.py`:

```python
import os
import unittest
import yaml

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCORING_DIR = os.path.join(PROJECT_ROOT, "resume-engine", "scoring")


def _load(filename):
    with open(os.path.join(SCORING_DIR, filename), "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


class TestSpecificityYamlIsEducationOnly(unittest.TestCase):

    def test_competencies_score_file_no_longer_exists(self):
        self.assertFalse(os.path.exists(os.path.join(SCORING_DIR, "competencies_score.yaml")))

    def test_specificity_yaml_has_no_project_criteria(self):
        data = _load("specificity.yaml")
        self.assertNotIn("project_description_specificity", data["criteria"])
        self.assertNotIn("project_tech_specificity", data["criteria"])
        self.assertIn("education_description_specificity", data["criteria"])

    def test_specificity_yaml_has_no_project_penalties_or_bonuses(self):
        data = _load("specificity.yaml")
        self.assertNotIn("generic_project_description", data["penalties"])
        self.assertNotIn("generic_project_tech", data["penalties"])
        self.assertNotIn("named_outcome", data.get("bonuses", {}))
        self.assertNotIn("named_system_or_stack", data.get("bonuses", {}))


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `/usr/local/bin/python3.13 -m unittest tests.test_scoring_yaml_content -v`
Expected: FAIL — `competencies_score.yaml` still exists; `specificity.yaml` still has the `project_*` keys.

- [ ] **Step 3: Delete competencies_score.yaml**

```bash
git rm resume-engine/scoring/competencies_score.yaml
```

- [ ] **Step 4: Trim specificity.yaml to Education-only**

Replace the full contents of `resume-engine/scoring/specificity.yaml` with:

```yaml
version: 3.0
# Was a generic positive/negative point stub, unreferenced by any prompt or
# script. Bullet-level specificity is already covered by believability.yaml's
# `specificity` criterion, and Summary-level specificity is already covered
# by summary_patterns.yaml. The remaining gap this file fills: specificity in
# the Education section, which nothing else scores.
#
# v3.0: Projects criteria removed -- the Projects section was deleted from
# the resume pipeline entirely (it never existed in ResumeDesignSystem.md).

max_score: 100

reject_if:
  score_below: 60

criteria:
  education_description_specificity:
    weight: 100
    description: >
      Does each education entry's description name a concrete honor, GPA,
      scholarship, or coursework focus, rather than a generic "graduated with
      honors" style claim with no specifics?
    examples:
      good: "3.56 GPA; Dean's List scholarship recipient"
      bad: "Graduated with distinction"

# Penalties
penalties:
  generic_education_description: -15 # no GPA, honor, or coursework specificity

# Bonuses
bonuses: {}
```

- [ ] **Step 5: Remove competencies_score.yaml from critique_resume.md's Load and Apply list**

In `resume-engine/prompts/critique_resume.md`, replace:

```
14. `certifications_score.yaml` — Certification relevance and canonical credential anchoring
15. `competencies_score.yaml` — Core competency presence and role alignment
16. `recruiter_score.yaml` — Recruiter first-pass readability and signal clarity
17. `specificity.yaml` — Projects and Education section specificity (bullet- and
    summary-level specificity are already covered by believability.yaml and
    summary_patterns.yaml respectively)
```

with:

```
14. `certifications_score.yaml` — Certification relevance and canonical credential anchoring
15. `recruiter_score.yaml` — Recruiter first-pass readability and signal clarity
16. `specificity.yaml` — Education section specificity (bullet- and
    summary-level specificity are already covered by believability.yaml and
    summary_patterns.yaml respectively)
```

- [ ] **Step 6: Update critique_resume.md's Step 7 evaluation sequence**

Replace:

```
### Step 7 — Evaluate Supporting Sections

Using `summary_patterns.yaml`, `certifications_score.yaml`,
`competencies_score.yaml`, `specificity.yaml`:
- Score summary quality and positioning clarity
- Confirm canonical certifications are present and correctly positioned
- Evaluate competency relevance
- Score Projects and Education section specificity
```

with:

```
### Step 7 — Evaluate Supporting Sections

Using `summary_patterns.yaml`, `certifications_score.yaml`, `specificity.yaml`:
- Score summary quality and positioning clarity
- Confirm canonical certifications are present and correctly positioned
- Score Education section specificity
```

- [ ] **Step 7: Run test to verify it passes**

Run: `/usr/local/bin/python3.13 -m unittest tests.test_scoring_yaml_content -v`
Expected: PASS (3 tests)

- [ ] **Step 8: Run the full suite**

Run:
```bash
/usr/local/bin/python3.13 -m unittest tests.test_jd_manager tests.test_orchestrator_audit_resume tests.test_orchestrator_build_checkpoint tests.test_orchestrator_main_batch tests.test_orchestrator_load_prompt tests.test_render_html tests.test_generate_pdf_margins tests.test_orchestrator_schema_cleanup tests.test_scoring_yaml_content -v
```
Expected: all PASS.

- [ ] **Step 9: Commit**

```bash
git add resume-engine/scoring/specificity.yaml resume-engine/prompts/critique_resume.md tests/test_scoring_yaml_content.py
git commit -m "$(cat <<'EOF'
Retire competencies_score.yaml; trim specificity.yaml to Education-only

Phase 1 deleted the Projects and Competencies sections from every generated
resume -- neither exists anymore, so competencies_score.yaml has nothing
left to score and specificity.yaml's Projects criteria (60 of its 100
points) were scoring a section that can't exist. Education is still fully
LLM-generated at this point in the project, so its specificity criterion
stays.

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
EOF
)"
```

---

### Task 3: Retire education_score.yaml

**Files:**
- Delete: `resume-engine/scoring/education_score.yaml`
- Test: extend `tests/test_scoring_yaml_content.py`

**Interfaces:**
- Consumes: none.
- Produces: none. `education_score.yaml` was never referenced in `critique_resume.md`'s Load and Apply list (confirmed during the audit) and is not loaded anywhere in `scripts/orchestrator.py` — this is a pure, isolated deletion.

**Context:** ResumeDesignSystem.md's Education rules are fully fixed (3 schools in a fixed order, fixed bullet counts, mostly-fixed content) — Phase 3 makes this deterministic in code rather than LLM-judged. An unwired, never-invoked LLM scoring rubric for a section that's about to become code-enforced isn't worth keeping around; delete it now rather than carrying it forward.

- [ ] **Step 1: Write the failing test**

Add to `tests/test_scoring_yaml_content.py`'s `TestSpecificityYamlIsEducationOnly` class:

```python
    def test_education_score_file_no_longer_exists(self):
        self.assertFalse(os.path.exists(os.path.join(SCORING_DIR, "education_score.yaml")))
```

- [ ] **Step 2: Run test to verify it fails**

Run: `/usr/local/bin/python3.13 -m unittest tests.test_scoring_yaml_content -v`
Expected: FAIL — `education_score.yaml` still exists.

- [ ] **Step 3: Delete the file**

```bash
git rm resume-engine/scoring/education_score.yaml
```

- [ ] **Step 4: Run test to verify it passes**

Run: `/usr/local/bin/python3.13 -m unittest tests.test_scoring_yaml_content -v`
Expected: PASS (4 tests)

- [ ] **Step 5: Commit**

```bash
git add tests/test_scoring_yaml_content.py
git commit -m "$(cat <<'EOF'
Retire education_score.yaml

Never referenced in critique_resume.md's Load and Apply list or anywhere in
orchestrator.py -- a fully orphaned rubric. ResumeDesignSystem.md's
Education rules are fully fixed (3 schools, fixed order, exact bullet
counts); Phase 3 makes this deterministic in code, leaving nothing for an
LLM rubric to judge.

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
EOF
)"
```

---

### Task 4: Fix summary_score.yaml's word-count bug (should be line-count)

**Files:**
- Modify: `resume-engine/scoring/summary_score.yaml`
- Test: Create `tests/test_summary_score_yaml.py`

**Interfaces:**
- Consumes: none.
- Produces: `summary_score.yaml`'s `readability` criterion no longer references word counts. Task 5 wires this file's real content into the live critique call and does not need to change this content further.

**Context:** `ResumeDesignSystem.md` caps the Summary at "Maximum 5 lines of text" — a layout/line-count measure. `summary_score.yaml`'s `readability` criterion currently scores `under_80_words` (excellent) / `over_120_words` (poor) — a word-count measure that has no relationship to the actual spec rule, and also disagrees with `summary_patterns.yaml`'s separate 40-80-word ideal (not touched by this task; `summary_patterns.yaml` is a different file already live in the critique and out of scope here). Fix: replace the word-count criteria with line-count criteria matching the spec's actual 5-line limit.

- [ ] **Step 1: Write the failing test**

Create `tests/test_summary_score_yaml.py`:

```python
import os
import unittest
import yaml

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCORING_DIR = os.path.join(PROJECT_ROOT, "resume-engine", "scoring")


class TestSummaryScoreYaml(unittest.TestCase):

    def setUp(self):
        with open(os.path.join(SCORING_DIR, "summary_score.yaml"), "r", encoding="utf-8") as f:
            self.data = yaml.safe_load(f)

    def test_readability_uses_line_count_not_word_count(self):
        readability = self.data["scoring_rules"]["readability"]
        excellent = readability["excellent"]
        poor = readability["poor"]
        self.assertNotIn("under_80_words", excellent)
        self.assertNotIn("over_120_words", poor)
        self.assertIn("within_5_line_limit", excellent)
        self.assertIn("exceeds_5_line_limit", poor)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `/usr/local/bin/python3.13 -m unittest tests.test_summary_score_yaml -v`
Expected: FAIL — the file still has `under_80_words` / `over_120_words`, not the line-count criteria.

- [ ] **Step 3: Fix the readability criterion**

In `resume-engine/scoring/summary_score.yaml`, replace:

```yaml
  readability:

    excellent:
      - under_80_words
      - concise_sentences
      - direct_language

    poor:
      - over_120_words
      - dense_paragraphs
      - filler_language
```

with:

```yaml
  readability:

    excellent:
      - within_5_line_limit
      - concise_sentences
      - direct_language

    poor:
      - exceeds_5_line_limit
      - dense_paragraphs
      - filler_language
```

- [ ] **Step 4: Run test to verify it passes**

Run: `/usr/local/bin/python3.13 -m unittest tests.test_summary_score_yaml -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add resume-engine/scoring/summary_score.yaml tests/test_summary_score_yaml.py
git commit -m "$(cat <<'EOF'
Fix summary_score.yaml: readability metric was word-count, spec is line-count

ResumeDesignSystem.md caps the Summary at 5 lines -- a layout measure.
summary_score.yaml's readability criterion scored under_80_words/
over_120_words instead, an unrelated metric never mentioned in the spec.

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
EOF
)"
```

---

### Task 5: Fold hiring_manager_scan.md + top_third_score.yaml into critique_resume.md; attach real scoring content to the critique call

**Files:**
- Modify: `scripts/orchestrator.py` (`ResumeCritiqueSchema`; the Step 5 critique call in `build_tailored_resume`)
- Modify: `resume-engine/prompts/critique_resume.md`
- Delete: `resume-engine/prompts/hiring_manager_scan.md`
- Modify: `resume-engine/scoring/manager_test.yaml` (drop the now-stale `hiring_manager_scan.md` consumer reference)
- Test: extend `tests/test_orchestrator_build_checkpoint.py`

**Interfaces:**
- Consumes: `orchestrator.ResumeEngine.load_yaml(dir_path, filename) -> dict` (existing method, unchanged signature, already used by `audit_and_refine_bullets` — this task reuses the identical pattern for the Step 5 critique call).
- Produces: `ResumeCritiqueSchema` gains one new field, `top_third_score: int`. `build_tailored_resume`'s Step 5 now actually loads `summary_score.yaml` and `top_third_score.yaml`'s real YAML content into the critique API call (previously only referenced by name in prose inside `critique_resume.md`, never attached — this closes that gap for these two specific files).

**Context:** `hiring_manager_scan.md` (never loaded by `orchestrator.py`) simulates a hiring manager's first 15-30 seconds of reading a resume, with a dedicated "Top-Third Test" step asking whether the strongest evidence is visible above the fold. `top_third_score.yaml` (also never wired in) is its matching scoring rubric. Both have real, unique content `critique_resume.md`'s current 3-score schema doesn't cover at all. Rather than reviving `hiring_manager_scan.md` as a second live prompt (doubling API calls per resume), fold its "Top-Third Test" concept into `critique_resume.md`'s existing single critique call as one new score.

- [ ] **Step 1: Write the failing test**

Add to `tests/test_orchestrator_build_checkpoint.py`'s `TestBuildCheckpointResume` class (reuses the existing `_pass_critique_json` helper and fixtures):

```python
    @patch("orchestrator.subprocess.run")
    @patch("orchestrator.render_html")
    @patch("orchestrator.GeminiClient.generate")
    @patch("orchestrator.time.sleep", lambda *a, **kw: None)
    def test_critique_call_attaches_summary_and_top_third_scoring_yaml(
        self, mock_generate, mock_render_html, mock_subprocess_run
    ):
        jd_manager.save_checkpoint(self.job_key, {
            "jd_keywords": {"hard_skills": ["python"]},
            "bullet_tuples": [["Shipped a widget platform used by 10k users.", "Acme", "eng"]],
        })
        seen_critique_system_instructions = []

        def generate_side_effect(*args, **kwargs):
            schema = kwargs.get("response_schema")
            if schema is orchestrator.CritiqueSchema:
                return (_pass_critique_json(), {})
            if schema is orchestrator.TemplateSchema:
                return (json.dumps({"SUMMARY": "Test summary."}), {})
            if schema is orchestrator.ResumeCritiqueSchema:
                seen_critique_system_instructions.append(kwargs.get("system_instruction", ""))
                return (json.dumps({
                    "summary_alignment_score": 90, "skills_relevance_score": 90,
                    "overall_fit_score": 90, "top_third_score": 85,
                    "flags": [], "recommendations": [],
                }), {})
            raise AssertionError(f"Unexpected response_schema in test: {schema}")

        mock_generate.side_effect = generate_side_effect
        mock_subprocess_run.return_value = MagicMock(returncode=0, stdout="📊 Pages: 2\n", stderr="")

        with patch.object(self.engine, "mine_bullet_bank"):
            result = self.engine.build_tailored_resume(
                jd_path=self.jd_path,
                master_resume={},
                output_filename=self.output_filename,
                job_key=self.job_key,
            )

        self.assertEqual(result["_critique"]["top_third_score"], 85)
        self.assertEqual(len(seen_critique_system_instructions), 1)
        system_instruction = seen_critique_system_instructions[0]
        self.assertIn("readability", system_instruction)          # from summary_score.yaml
        self.assertIn("recruiter_comprehension_speed", system_instruction)  # from top_third_score.yaml
```

- [ ] **Step 2: Run test to verify it fails**

Run: `/usr/local/bin/python3.13 -m unittest tests.test_orchestrator_build_checkpoint -v`
Expected: FAIL — `ResumeCritiqueSchema` has no `top_third_score` field yet, and the Step 5 call's `system_instruction` doesn't contain either YAML file's content.

- [ ] **Step 3: Add `top_third_score` to `ResumeCritiqueSchema`**

In `scripts/orchestrator.py`, replace:

```python
class ResumeCritiqueSchema(BaseModel):
    summary_alignment_score: int       = Field(description="0-100: does the Summary match the JD role and tone?")
    skills_relevance_score:  int       = Field(description="0-100: are Skills JD-relevant?")
    overall_fit_score:       int       = Field(description="0-100: holistic resume-to-JD fit")
    flags:                   List[str] = Field(description="Specific issues found")
    recommendations:         List[str] = Field(description="Actionable fixes, one per flag")
```

with:

```python
class ResumeCritiqueSchema(BaseModel):
    summary_alignment_score: int       = Field(description="0-100: does the Summary match the JD role and tone?")
    skills_relevance_score:  int       = Field(description="0-100: are Skills JD-relevant?")
    overall_fit_score:       int       = Field(description="0-100: holistic resume-to-JD fit")
    top_third_score:         int       = Field(description="0-100: does the top third of page one alone communicate fit within a 15-30 second first read (first-impression / above-the-fold test)?")
    flags:                   List[str] = Field(description="Specific issues found")
    recommendations:         List[str] = Field(description="Actionable fixes, one per flag")
```

- [ ] **Step 4: Attach summary_score.yaml and top_third_score.yaml's real content to the Step 5 critique call**

In `scripts/orchestrator.py`'s `build_tailored_resume`, replace:

```python
            critique_prompt = self.load_prompt("critique_resume.md")
            critique_contents = (
                f"=== JOB DESCRIPTION ===\n{jd_text}\n\n"
                f"=== RESUME JSON ===\n{json.dumps(resume_data, indent=2)}"
            )
            critique_text, _ = GeminiClient.generate(
                model=CRITIQUE_MODEL,
                system_instruction=critique_prompt,
                contents=critique_contents,
                response_schema=ResumeCritiqueSchema,
                temperature=0.0,
            )
```

with:

```python
            critique_prompt = self.load_prompt("critique_resume.md")
            summary_score_rules    = json.dumps(self.load_yaml(self.scoring_dir, "summary_score.yaml"))
            top_third_score_rules  = json.dumps(self.load_yaml(self.scoring_dir, "top_third_score.yaml"))
            critique_system = (
                f"{critique_prompt}"
                f"\n\nSUMMARY SCORING RUBRIC:\n{summary_score_rules}"
                f"\n\nTOP-THIRD-OF-PAGE-ONE SCORING RUBRIC:\n{top_third_score_rules}"
            )
            critique_contents = (
                f"=== JOB DESCRIPTION ===\n{jd_text}\n\n"
                f"=== RESUME JSON ===\n{json.dumps(resume_data, indent=2)}"
            )
            critique_text, _ = GeminiClient.generate(
                model=CRITIQUE_MODEL,
                system_instruction=critique_system,
                contents=critique_contents,
                response_schema=ResumeCritiqueSchema,
                temperature=0.0,
            )
```

Also update the print block immediately below it — replace:

```python
                print(f"  Holistic critique scores:")
                print(f"    summary_alignment : {critique_data.get('summary_alignment_score', '?')}")
                print(f"    skills_relevance  : {critique_data.get('skills_relevance_score',  '?')}")
                print(f"    overall_fit       : {critique_data.get('overall_fit_score',        '?')}")
```

with:

```python
                print(f"  Holistic critique scores:")
                print(f"    summary_alignment : {critique_data.get('summary_alignment_score', '?')}")
                print(f"    skills_relevance  : {critique_data.get('skills_relevance_score',  '?')}")
                print(f"    top_third         : {critique_data.get('top_third_score',         '?')}")
                print(f"    overall_fit       : {critique_data.get('overall_fit_score',        '?')}")
```

- [ ] **Step 5: Delete hiring_manager_scan.md and fix manager_test.yaml's stale reference**

```bash
git rm resume-engine/prompts/hiring_manager_scan.md
```

In `resume-engine/scoring/manager_test.yaml`, replace:

```yaml
# Active -- primary rubric for critique_resume.md and hiring_manager_scan.md.
```

with:

```yaml
# Active -- primary rubric for critique_resume.md.
```

- [ ] **Step 6: Add summary_score.yaml and top_third_score.yaml to critique_resume.md's Load and Apply list, and add a Top-Third evaluation step**

In `resume-engine/prompts/critique_resume.md`, replace:

```
14. `certifications_score.yaml` — Certification relevance and canonical credential anchoring
15. `recruiter_score.yaml` — Recruiter first-pass readability and signal clarity
16. `specificity.yaml` — Education section specificity (bullet- and
    summary-level specificity are already covered by believability.yaml and
    summary_patterns.yaml respectively)
```

with:

```
14. `certifications_score.yaml` — Certification relevance and canonical credential anchoring
15. `recruiter_score.yaml` — Recruiter first-pass readability and signal clarity
16. `specificity.yaml` — Education section specificity (bullet- and
    summary-level specificity are already covered by believability.yaml and
    summary_patterns.yaml respectively)
17. `summary_score.yaml` — Summary quality scoring by JD-relevance, specificity,
    alignment, credibility, and readability
18. `top_third_score.yaml` — Whether the top third of page one alone
    communicates fit within a 15-30 second first read
```

Then, after Step 8 in the Evaluation Sequence, add a new step:

```
### Step 9 — Evaluate Top-Third-of-Page-One Impact

Using `top_third_score.yaml`:
- Simulate a hiring manager's first 15-30 seconds of reading: is the single
  strongest accomplishment visible in the top third of page one, without
  scrolling?
- Score `role_clarity`, `specialization_visibility`,
  `strongest_evidence_visibility`, `recruiter_comprehension_speed`, and
  `differentiation` per the rubric's weights
- Flag `weak_top_section` if the strongest evidence is buried below the fold
```

Finally, add a line to the Output Format's `SECTION SCORES` block — replace:

```
  Recruiter Readability:    [x/100]
```

with:

```
  Recruiter Readability:    [x/100]
  Top-Third Impression:     [x/100]
```

- [ ] **Step 7: Run test to verify it passes**

Run: `/usr/local/bin/python3.13 -m unittest tests.test_orchestrator_build_checkpoint -v`
Expected: PASS

- [ ] **Step 8: Run the full suite**

Run:
```bash
/usr/local/bin/python3.13 -m unittest tests.test_jd_manager tests.test_orchestrator_audit_resume tests.test_orchestrator_build_checkpoint tests.test_orchestrator_main_batch tests.test_orchestrator_load_prompt tests.test_render_html tests.test_generate_pdf_margins tests.test_orchestrator_schema_cleanup tests.test_scoring_yaml_content tests.test_summary_score_yaml -v
```
Expected: all PASS.

- [ ] **Step 9: Commit**

```bash
git add scripts/orchestrator.py resume-engine/prompts/critique_resume.md resume-engine/scoring/manager_test.yaml tests/test_orchestrator_build_checkpoint.py
git commit -m "$(cat <<'EOF'
Fold hiring_manager_scan.md's top-third test into the live critique call

hiring_manager_scan.md and top_third_score.yaml had real, unique content
(first-impression / above-the-fold evaluation) that critique_resume.md's
3-score schema didn't cover, but neither was ever wired into the live
pipeline. Added a top_third_score field to ResumeCritiqueSchema and a new
evaluation step to critique_resume.md, and -- while touching this call --
actually attached summary_score.yaml and top_third_score.yaml's real YAML
content to the critique API call instead of leaving them as prose-only
references the model has to infer compliance with.

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
EOF
)"
```

---

### Task 6: Rewrite scoring/README.md to reflect the true final state

**Files:**
- Modify: `resume-engine/scoring/README.md`

**Interfaces:**
- Consumes: none. This task only updates documentation to match the state Tasks 1-5 produced.
- Produces: none.

**Context:** The README currently claims "All 17 files above exist and are populated" and that all are "consumed at runtime... for the document-level critique" — both false even before this plan (the audit found the Load-and-Apply list was prose-only for most files) and now additionally wrong about the file count (`competencies_score.yaml` and `education_score.yaml` are deleted; `summary_score.yaml` and `top_third_score.yaml` are now genuinely wired in).

- [ ] **Step 1: Replace the file table and status section**

Replace the full contents of `resume-engine/scoring/README.md` with:

```markdown
# resume-engine/scoring/

This folder holds YAML scoring rubrics used by `orchestrator.py`'s per-bullet
audit loop and the document-level critique driven by
`resume-engine/prompts/critique_resume.md`, plus `score_keeper_gems.py`.

## Files that belong here

| File | Used by | Purpose |
|---|---|---|
| `manager_test.yaml` | `orchestrator.py`, `critique_resume.md` | Pass/fail rules the Skeptical Editor uses to judge bullets |
| `believability.yaml` | `orchestrator.py`, `score_keeper_gems.py`, `critique_resume.md` | Rubric for bullet-level believability scoring (0-100) |
| `ai_risk.yaml` | `orchestrator.py`, `critique_resume.md` | Definitions of high-risk AI-sounding language patterns |
| `professional_identity_score.yaml` | `critique_resume.md` | Identity/archetype detection driving all downstream document-level scoring |
| `resume_cohesion_score.yaml` | `critique_resume.md` | Cross-section narrative alignment and identity consistency |
| `experience_structure_score.yaml` | `critique_resume.md` | Bullet structure, depth, and role-level formatting |
| `skills_scoring.yaml` | `critique_resume.md` | Skills grouping relevance, evidence support, archetype alignment; also the canonical skills-vocabulary bank |
| `role_dna.yaml` | `tailor_resume.md`, `critique_resume.md` | Archetype library (evidence signals + summary framing) shared between building and scoring |
| `ats_match.yaml` | `critique_resume.md` | ATS keyword-match weighting against the JD |
| `evidence_alignment.yaml` | `critique_resume.md` | Achievement-to-claim support -- traces every metric/tool/claim back to verified evidence |
| `summary_patterns.yaml` | `critique_resume.md` | Summary-level pattern scoring (opener style, specificity, length) |
| `summary_score.yaml` | `critique_resume.md`, actually attached to the Step 5 critique API call | Summary quality scoring by JD-relevance/specificity/alignment/credibility/readability (readability is line-count based, matching the spec's 5-line limit) |
| `certifications_score.yaml` | `critique_resume.md` | Certification relevance and canonical credential anchoring |
| `recruiter_score.yaml` | `critique_resume.md` | Recruiter first-pass scannability (distinct from `top_third_score.yaml`'s narrative-comprehension check) |
| `top_third_score.yaml` | `critique_resume.md`, actually attached to the Step 5 critique API call | Whether the top third of page one alone communicates fit within a 15-30 second first read |
| `specificity.yaml` | `critique_resume.md` | Education section specificity only (Projects criteria removed -- that section no longer exists; bullet- and summary-level specificity are covered separately by `believability.yaml` and `summary_patterns.yaml`) |

`competencies_score.yaml` and `education_score.yaml` have been retired:
Competencies no longer exists as a resume section, and Education's rules are
fully fixed content (see `docs/superpowers/specs/2026-07-01-resume-spec-enforcement-design.md`'s
Phase 3 design), leaving nothing for an LLM rubric to judge.

## Status

`critique_resume.md`'s "Load and Apply" list is the source of truth for
which files drive the document-level critique. As of this rewrite,
`summary_score.yaml` and `top_third_score.yaml` are both listed there AND
have their real YAML content attached to the Step 5 critique API call in
`orchestrator.py` (not just referenced by name) -- the remaining 12 files in
the Load and Apply list are still prose-only references the critique model
must infer compliance with; wiring their actual content into the call the
same way is future work, not required by this rewrite.

## Format reference

See any file in this folder for the convention: `version`, `max_score`,
`reject_if.score_below`, a `criteria` block with per-item `weight` +
`description` + `good`/`bad` examples, then `penalties` and `bonuses` blocks.
`resume-engine/rules/` uses a similar but not identical convention for
bullet-rewrite rules (as opposed to scoring rubrics).
```

- [ ] **Step 2: Verify no stale references remain**

```bash
grep -n "competencies_score\|education_score\|17 files" resume-engine/scoring/README.md
```
Expected: no output (all three phrases removed).

- [ ] **Step 3: Commit**

```bash
git add resume-engine/scoring/README.md
git commit -m "$(cat <<'EOF'
Rewrite scoring/README.md to reflect the true final state

The old README claimed all 17 files were consumed at runtime for the
document-level critique -- false before this plan, and now additionally
wrong on the file count after retiring competencies_score.yaml and
education_score.yaml and actually wiring summary_score.yaml and
top_third_score.yaml into the live critique call.

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
EOF
)"
```

---

## Self-Review Notes

- **Spec coverage:** All items from the resolved Phase 2 salvage plan (design doc, "Scope and sequencing" section) are covered: delete diagnose_resume.md/recruiter_scan.md (Task 1), retire rank_bullets.md as a prompt (Task 1), fold hiring_manager_scan.md/top_third_score.yaml into critique_resume.md (Task 5), fix summary_score.yaml's bug and attach it (Tasks 4 and 5), retire education_score.yaml (Task 3), rewrite scoring/README.md (Task 6). Task 2 (competencies_score.yaml/specificity.yaml) was discovered while re-reading the current post-Phase-1 state of critique_resume.md and is a direct, necessary consequence of Phase 1 already having shipped -- not in the original design doc text, but squarely in the same "content correctness" scope as the rest of this phase.
- **Placeholder scan:** no TBD/TODO; every step shows literal before/after content.
- **Type consistency:** `ResumeCritiqueSchema` gains exactly one new field (`top_third_score: int`) across Task 5 -- no other task touches this schema. `load_yaml(dir_path, filename) -> dict` signature is unchanged and reused as-is from its existing use in `audit_and_refine_bullets`.
- **Ordering:** Task 6 (README rewrite) must run last -- it documents the file list Tasks 1-5 produce. Task 5 depends on Task 4 having already fixed `summary_score.yaml`'s content (Task 5 attaches that file's content to the live call; if Task 4 hasn't run yet, the attached content would still carry the word-count bug). Run Tasks 1-4 in any order relative to each other, then Task 5, then Task 6.
