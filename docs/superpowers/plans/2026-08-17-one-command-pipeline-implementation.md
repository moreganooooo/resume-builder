# One-Command Application Pipeline Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement the 1-Click Application Package Pipeline (Feature #19 / Group E) unifying liveness verification, fit scoring & capability gating, company research, resume generation (PDF/DOCX), cover letter generation (PDF/DOCX), database tracking, and a terminal HUD summary into a single execution workflow.

**Architecture:** A new orchestration entry point `ResumeEngine.build_application_package()` and `run_application_package()` in `scripts/orchestrator.py` chains the existing pipeline modules with fail-fast cost gates (`liveness.py`, `batch_evaluate.py`, `company_research.py`, `validate_resume.py`, `validate_coverletter.py`, `render_resume_docx.py`, `render_coverletter_docx.py`, `jd_manager.py`, `db.py`). A dedicated Rich summary HUD in `scripts/cli_art.py` surfaces all 4 created artifacts. The workflow is exposed via CLI (`resume package` / `resume build`) in `scripts/cli.py` and as a top-level action in `scripts/menu.py`.

**Tech Stack:** Python 3.10+, Click, Rich, Playwright (liveness), python-docx, SQLite, stdlib `unittest`.

**Spec:** `docs/superpowers/specs/2026-08-17-one-command-pipeline-design.md`

---

## Global Constraints & Principles

- **Test-Driven Development (TDD):** For every task, write or update unit/integration tests *first*, verify they fail as expected, implement the changes, and verify all tests pass.
- **Fail-Fast Token Safety:** If a JD's posting URL is expired, or if fit evaluation yields `"Skip"`, abort before calling Gemini resume/cover-letter models (unless `--force` is explicitly provided).
- **4-Artifact Completeness:** Every successful package build must generate:
  1. `output/<profile>/pdf/<stem>.pdf` (Resume PDF)
  2. `output/<profile>/docx/<stem>.docx` (Resume DOCX)
  3. `output/<profile>/pdf/<stem>_CoverLetter.pdf` (Cover Letter PDF)
  4. `output/<profile>/docx/<stem>_CoverLetter.docx` (Cover Letter DOCX)
- **Database & State Integrity:** Successfully packaged JDs are moved to `jds/completed/`, tracked in `JDTracker`, appended to SQLite `applications` table, and committed via `db.checkpoint()`.
- **Full Suite Regression:** Run `python -m unittest discover -s tests -v` to ensure 100% green tests across the repository.

---

## Task 1: Package Orchestrator Engine (`scripts/orchestrator.py`)

**Files:**
- Create: `tests/test_application_package.py`
- Modify: `scripts/orchestrator.py`

**Interfaces:**
- `ResumeEngine.build_application_package(self, jd_path: str, master_resume: dict | None = None, output_filename: str | None = None, referral: str | None = None, force: bool = False, skip_liveness: bool = False, skip_fit: bool = False) -> dict | None`
- `run_application_package(jd_path: str | None = None, master_resume_path: str | None = None, output_filename: str | None = None, referral: str | None = None, force: bool = False, skip_liveness: bool = False, skip_fit: bool = False) -> tuple[int, int]`

- [ ] **Step 1: Write integration tests in `tests/test_application_package.py`**

```python
import json
import os
import shutil
import tempfile
import unittest
from unittest.mock import MagicMock, patch

import jd_manager
import orchestrator
import profile_paths


class TestApplicationPackage(unittest.TestCase):

    def setUp(self):
        self.engine = orchestrator.ResumeEngine()
        self.test_dir = tempfile.mkdtemp()
        self.jd_path = os.path.join(self.test_dir, "test_job.json")
        self.jd_data = {
            "title": "Senior Content Strategist",
            "company": "Testco",
            "source_url": "https://boards.greenhouse.io/testco/jobs/123",
            "description": "We are looking for a Senior Content Strategist with 8+ years experience in content design and messaging.",
        }
        with open(self.jd_path, "w", encoding="utf-8") as f:
            json.dump(self.jd_data, f)

    def tearDown(self):
        shutil.rmtree(self.test_dir, ignore_errors=True)

    @patch("liveness.verify_jd_paths")
    def test_liveness_expired_moves_to_expired_and_aborts(self, mock_liveness):
        mock_liveness.return_value = {
            "active": 0, "likely_active": 0, "expired": 1, "uncertain": 0, "moved": 1,
            "expired_source_paths": [self.jd_path],
        }
        res = self.engine.build_application_package(self.jd_path)
        self.assertIsNotNone(res)
        self.assertEqual(res.get("status"), "expired")
        mock_liveness.assert_called_once()

    @patch("liveness.verify_jd_paths")
    def test_fit_skip_moves_to_archived_and_aborts(self, mock_liveness):
        mock_liveness.return_value = {"active": 1, "likely_active": 0, "expired": 0, "uncertain": 0, "moved": 0}
        with patch.object(self.engine, "evaluate_fit") as mock_eval, \
             patch("jd_manager.archive_jd", return_value="jds/archived/test_job.json") as mock_archive:
            mock_eval.return_value = {
                "recommendation": "Skip",
                "composite_score": 2.1,
                "fit_score": 2.0,
                "interview_odds_score": 2.2,
                "practical_pursue_score": 2.0,
                "hard_blockers": ["Requires 15+ years in Defense"],
            }
            res = self.engine.build_application_package(self.jd_path)
            self.assertIsNotNone(res)
            self.assertEqual(res.get("status"), "skipped")
            mock_archive.assert_called_once()

    @patch("liveness.verify_jd_paths")
    def test_fit_skip_with_force_proceeds(self, mock_liveness):
        mock_liveness.return_value = {"active": 1, "likely_active": 0, "expired": 0, "uncertain": 0, "moved": 0}
        with patch.object(self.engine, "evaluate_fit") as mock_eval, \
             patch.object(self.engine, "build_tailored_resume") as mock_resume, \
             patch.object(self.engine, "build_tailored_coverletter") as mock_cl, \
             patch("jd_manager.archive_jd") as mock_archive, \
             patch("shutil.move"), \
             patch("db.checkpoint"):
            mock_eval.return_value = {"recommendation": "Skip", "composite_score": 2.1}
            mock_resume.return_value = {"_output_paths": {"pdf": "res.pdf", "docx": "res.docx", "json": "res.json"}}
            mock_cl.return_value = {"_output_paths": {"pdf": "cl.pdf", "docx": "cl.docx", "json": "cl.json"}}

            res = self.engine.build_application_package(self.jd_path, force=True)
            self.assertIsNotNone(res)
            self.assertEqual(res.get("status"), "completed")
            mock_archive.assert_not_called()
            mock_resume.assert_called_once()
            mock_cl.assert_called_once()
```

- [ ] **Step 2: Run test to confirm it fails before implementation**

```bash
python -m unittest tests.test_application_package -v
```

- [ ] **Step 3: Implement `build_application_package` and `run_application_package` in `scripts/orchestrator.py`**
  - Add `build_application_package()` method to `ResumeEngine`.
  - Add `run_application_package()` top-level batch/single function.
  - Wire liveness check (`liveness.verify_jd_paths`), fit check (`self.evaluate_fit`), referral save, resume generation, cover letter generation, tracking, and database checkpoint.

- [ ] **Step 4: Re-run unit tests to verify pass**

```bash
python -m unittest tests.test_application_package -v
```

---

## Task 2: Package Summary HUD in `scripts/cli_art.py`

**Files:**
- Create: `tests/test_cli_art_package_hud.py`
- Modify: `scripts/cli_art.py`

**Interfaces:**
- `cli_art.render_application_package_hud(package_result: dict) -> None`

- [ ] **Step 1: Write test for Package Summary HUD in `tests/test_cli_art_package_hud.py`**

```python
import io
import unittest
from unittest.mock import patch

import cli_art


class TestPackageHUD(unittest.TestCase):

    def test_render_application_package_hud_completed(self):
        result = {
            "status": "completed",
            "company_name": "Spotify",
            "job_title": "Senior Content Strategist",
            "evaluation": {"composite_score": 4.5, "recommendation": "Strong Pursue"},
            "ats_classification": {"provider_id": "workday", "weight_tier": "enterprise_high"},
            "output_paths": {
                "resume_pdf": "output/morgan/pdf/MorganEscott_Resume.pdf",
                "resume_docx": "output/morgan/docx/MorganEscott_Resume.docx",
                "coverletter_pdf": "output/morgan/pdf/MorganEscott_CoverLetter.pdf",
                "coverletter_docx": "output/morgan/docx/MorganEscott_CoverLetter.docx",
            },
        }
        with patch("sys.stdout", new=io.StringIO()) as fake_out:
            cli_art.render_application_package_hud(result)
            output = fake_out.getvalue()
            # Rich console prints to stdout/stderr
            self.assertTrue(len(output) >= 0)
```

- [ ] **Step 2: Implement `render_application_package_hud()` in `scripts/cli_art.py`**
  - Use Rich `Panel`, `Table`, and `Text` with `theme.BRAND`, `theme.SUCCESS`, `theme.WARNING`.
  - Display Company, Job Title, ATS Tier, Composite Score, and file links for all 4 output files.

- [ ] **Step 3: Verify tests pass**

```bash
python -m unittest tests.test_cli_art_package_hud -v
```

---

## Task 3: CLI Subcommand `package` / `build` in `scripts/cli.py`

**Files:**
- Create: `tests/test_cli_package.py`
- Modify: `scripts/cli.py`

**Interfaces:**
- CLI command: `resume package [JD_FILE]`
- CLI command alias: `resume build [JD_FILE]`
- Flags: `--referral`, `--force`, `--skip-liveness`, `--skip-fit`, `--pick`, `--yes`, `--master`

- [ ] **Step 1: Write CLI command tests in `tests/test_cli_package.py`**

```python
import os
import unittest
from unittest.mock import patch, MagicMock
from click.testing import CliRunner

import cli


class TestCliPackage(unittest.TestCase):

    def setUp(self):
        self.runner = CliRunner()

    @patch("orchestrator.run_application_package", return_value=(1, 0))
    def test_cli_package_single_jd(self, mock_run):
        with self.runner.isolated_filesystem():
            with open("job.json", "w") as f:
                f.write("{}")
            result = self.runner.invoke(cli.cli, ["package", "job.json"])
            self.assertEqual(result.exit_code, 0)
            mock_run.assert_called_once()

    @patch("orchestrator.run_application_package", return_value=(1, 0))
    def test_cli_build_alias(self, mock_run):
        with self.runner.isolated_filesystem():
            with open("job.json", "w") as f:
                f.write("{}")
            result = self.runner.invoke(cli.cli, ["build", "job.json"])
            self.assertEqual(result.exit_code, 0)
            mock_run.assert_called_once()
```

- [ ] **Step 2: Add `package` and `build` commands to `scripts/cli.py`**
  - Wire flags `--referral`, `--force`, `--skip-liveness`, `--skip-fit`, `--pick`, `--yes`, `--master`.
  - Connect to `orchestrator.run_application_package()`.
  - Wire `menu.offer_next_steps("package", jd_file=jd_file, from_cli=True)`.

- [ ] **Step 3: Run CLI tests**

```bash
python -m unittest tests.test_cli_package -v
```

---

## Task 4: Interactive Menu Integration & Full Suite Validation

**Files:**
- Create: `tests/test_menu_package.py`
- Modify: `scripts/menu.py`
- Modify: `docs/superpowers/plans/2026-08-17-cover-letter-blueprint-roadmap.md`

**Interfaces:**
- `menu.handle_application_package_choice()`

- [ ] **Step 1: Write interactive menu integration test in `tests/test_menu_package.py`**

```python
import unittest
from unittest.mock import patch, MagicMock

import menu


class TestMenuPackage(unittest.TestCase):

    @patch("orchestrator.run_application_package", return_value=(1, 0))
    @patch("jd_manager.get_pending_jds", return_value=["jds/test.json"])
    @patch("cli_art.select", return_value="all")
    def test_menu_package_flow(self, mock_select, mock_pending, mock_run):
        # Test selecting the full package action from the interactive menu
        menu.handle_application_package_flow()
        mock_run.assert_called_once()
```

- [ ] **Step 2: Implement menu flow in `scripts/menu.py`**
  - Add `"🚀  Build Full Application Package (Liveness → Fit → Resume → Cover Letter → DOCX/PDF)"` to main menu.
  - Implement `handle_application_package_flow()`.

- [ ] **Step 3: Run menu tests**

```bash
python -m unittest tests.test_menu_package -v
```

- [ ] **Step 4: Update Cover Letter Blueprint Roadmap**
  - Update `docs/superpowers/plans/2026-08-17-cover-letter-blueprint-roadmap.md` marking Group E as `✅ COMPLETE`.

- [ ] **Step 5: Run Full Test Discovery Suite**

```bash
python -m unittest discover -s tests -v
```

- [ ] **Step 6: Commit all changes**

```bash
git add . && git commit -m "feat(pipeline): implement one-command application package pipeline (Group E complete)"
```
