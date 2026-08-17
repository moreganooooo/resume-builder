# One-Command Application Pipeline Design

**Status**: Proposed, awaiting review  
**Part of**: Group E, `docs/superpowers/plans/2026-08-17-cover-letter-blueprint-roadmap.md` (Feature #19)  
**Author**: Antigravity & Claude (pair programming), aligned with Morgan 2026-08-17  

---

## 1. Why

Applying for a job posting currently requires several fragmented, manual steps across different CLI commands or interactive menu options:
1. `resume liveness` (to check if the posting URL is still active).
2. `resume evaluate <jd>` (to score role fit, interview odds, and check for hard blockers).
3. `resume tailor <jd>` (to build the tailored resume PDF/DOCX and log to the database).
4. `resume coverletter <jd>` (to generate the tailored cover letter PDF/DOCX with voice and keyword alignment).
5. Inspecting disparate artifact folders to locate all 4 final output files (Resume PDF, Resume DOCX, Cover Letter PDF, Cover Letter DOCX).

### Operational Problems
- **Wasted Gemini API Quota**: When a user runs `resume tailor` or `resume coverletter` without evaluating first, expensive multi-step generation runs on roles that would have scored a `"Skip"` recommendation or contained hard deal-breakers.
- **Dead-Link Tailoring**: Building application materials for expired job postings because liveness checks were forgotten.
- **Desynchronization**: Generating a tailored resume but forgetting to generate the matching cover letter (or vice versa).
- **High Cognitive Friction**: For an active job search, running 3–4 commands per JD creates unnecessary decision fatigue.

### Goal
Provide a unified, fail-fast, one-command application pipeline (`resume package [JD]`) and interactive menu action that chains the entire end-to-end lifecycle—from liveness verification to fit gating, company research, resume generation, cover letter generation, database checkpointing, and a terminal HUD summary—into a single, cohesive workflow.

---

## 2. Scope

1. **One-Command Orchestration**: Build `run_application_package()` in `scripts/orchestrator.py` chaining:
   - **Stage 1 (Liveness Check)**: Verify posting status via Playwright if a `source_url` is present. Fail-fast on expired links.
   - **Stage 2 (Fit & Capability Gate)**: Check existing score or run `evaluate_fit()`. Fail-fast on `"Skip"` recommendations unless explicitly forced.
   - **Stage 3 (Company Research)**: Extract tone, values, and company intelligence (Tier 1 site / Tier 2 search / Tier 3 JD text) for downstream prompts.
   - **Stage 4 (Tailored Resume Build)**: Generate tailored resume JSON, HTML, PDF, and ATS-optimized DOCX.
   - **Stage 5 (Tailored Cover Letter Build)**: Generate tailored cover letter JSON, HTML, PDF, and ATS-optimized DOCX with Group B keyword front-loading and Group D voice metrics.
   - **Stage 6 (Tracking & Database Logging)**: Record completion in `JDTracker`, move JD to `jds/completed/`, append row to SQLite applications table, and checkpoint database.
   - **Stage 7 (Terminal Application HUD)**: Display a Rich summary panel with fit scores, ATS tier, and paths to all generated artifacts.
2. **CLI Ergonomics (`scripts/cli.py`)**:
   - Add `resume package [JD_FILE]` command (with alias `resume build [JD_FILE]`).
   - Flags: `--referral`, `--force` (bypass "Skip" fit gate), `--skip-liveness`, `--skip-fit`, `--pick` (interactive multi-select), `--yes` (skip confirmation in batch).
3. **Interactive Menu (`scripts/menu.py`)**:
   - Add primary top-level menu action: `"🚀 Full Application Package (Liveness + Fit + Resume + Cover Letter)"`.
4. **Pure Orchestration (No Net-New Prompts or Subsystems)**:
   - Reuses all existing, thoroughly-tested components (`liveness.py`, `batch_evaluate.py`, `render_html.py`, `render_resume_docx.py`, `render_coverletter.py`, `render_coverletter_docx.py`, `validate_resume.py`, `validate_coverletter.py`, `voice_metrics.py`, `jd_manager.py`, `db.py`).

---

## 3. Architecture & Execution Flow

```
                         ┌─────────────────────────────┐
                         │   `resume package [JD]`     │
                         │   or Interactive Menu Flow  │
                         └──────────────┬──────────────┘
                                        │
                                        ▼
                         ┌─────────────────────────────┐
                         │   Stage 1: Liveness Gate    │
                         │   (Playwright URL check)    │
                         └──────────────┬──────────────┘
                               /                 \
                    [Expired] /                   \ [Active / Uncertain / No URL]
                             ▼                     ▼
                 ┌───────────────────────┐ ┌─────────────────────────────┐
                 │ Move to jds/expired/  │ │  Stage 2: Fit Gate          │
                 │ Abort & Report        │ │  (Dual-metric scoring)      │
                 └───────────────────────┘ └──────────────┬──────────────┘
                                                 /                 \
                                      [Skip]    /                   \ [Pursue / Strong / --force]
                                               ▼                     ▼
                                   ┌───────────────────────┐ ┌─────────────────────────────┐
                                   │ Move to jds/archived/ │ │  Stage 3: Company Research  │
                                   │ Abort & Report        │ │  (Site scrape / Search)     │
                                   └───────────────────────┘ └──────────────┬──────────────┘
                                                                            │
                                                                            ▼
                                                             ┌─────────────────────────────┐
                                                             │  Stage 4: Build Resume      │
                                                             │  (JSON, HTML, PDF, DOCX)    │
                                                             └──────────────┬──────────────┘
                                                                            │
                                                                            ▼
                                                             ┌─────────────────────────────┐
                                                             │  Stage 5: Build Cover Letter│
                                                             │  (JSON, HTML, PDF, DOCX)    │
                                                             └──────────────┬──────────────┘
                                                                            │
                                                                            ▼
                                                             ┌─────────────────────────────┐
                                                             │  Stage 6: Database & State  │
                                                             │  (Tracker, Move, DB Sync)   │
                                                             └──────────────┬──────────────┘
                                                                            │
                                                                            ▼
                                                             ┌─────────────────────────────┐
                                                             │  Stage 7: Rich Package HUD  │
                                                             └─────────────────────────────┘
```

---

## 4. Pipeline Stages Specification

### Stage 1: Liveness Gate
- **Condition**: Executed when `jd_path` contains a valid `source_url` and `--skip-liveness` is false.
- **Execution**: Calls `liveness.verify_jd_paths([jd_path])`.
- **Outcome**:
  - `expired`: Moves JD to `jds/expired/` via `jd_manager.move_jd_to()`, prints expired notice with HTTP status/reason, and aborts pipeline early without calling Gemini.
  - `active` / `likely_active` / `uncertain`: Proceeds to Stage 2.
  - Network timeouts or Playwright failures are treated as `uncertain` to prevent transient network hiccups from blocking the user.

### Stage 2: Fit & Capability Gate
- **Condition**: Executed unless `--skip-fit` is true.
- **Execution**:
  - Checks if JD already has a persisted evaluation via `jd_manager.read_evaluation(jd_path)`.
  - If not evaluated, calls `engine.evaluate_fit(jd_path)` and saves via `jd_manager.save_evaluation(jd_path, eval_result)`.
- **Outcome**:
  - If `recommendation == "Skip"` and `--force` is false:
    - Displays fit subscores (Fit, Interview Odds, Practical Pursue) and hard blockers.
    - Moves JD to `jds/archived/` via `jd_manager.archive_jd(jd_path)`.
    - Aborts pipeline cleanly, saving further token spend.
  - If `recommendation in ("Pursue", "Strong Pursue", "Consider")` (or `--force` is passed):
    - Displays fit summary badge and proceeds to Stage 3.

### Stage 3: Company Research
- **Execution**: Calls `engine.research_company(jd_data, jd_text)`.
- **Outcome**:
  - Populates company voice, mission, and strategic priorities.
  - Result is passed directly into cover letter generation prompt context.

### Stage 4: Tailored Resume Generation
- **Execution**: Calls `engine.build_tailored_resume(jd_path, master_resume=..., output_filename=..., job_key=job_key)`.
- **Artifacts Generated**:
  - `output/<profile>/json/<stem>.json`
  - `output/<profile>/html/<stem>.html`
  - `output/<profile>/pdf/<stem>.pdf`
  - `output/<profile>/docx/<stem>.docx`
- **Validation**:
  - Strict semantic skills guardrail, duplicate verb checks, widow prevention, PDF text extraction verification.

### Stage 5: Tailored Cover Letter Generation
- **Execution**: Calls `engine.build_tailored_coverletter(jd_path, job_key=job_key)`.
- **Artifacts Generated**:
  - `output/<profile>/json/<stem>_CoverLetter.json`
  - `output/<profile>/html/<stem>_CoverLetter.html`
  - `output/<profile>/pdf/<stem>_CoverLetter.pdf`
  - `output/<profile>/docx/<stem>_CoverLetter.docx`
- **Validation**:
  - Word count validator (300–450 words), KB traceability, cliché phrase blocklist, ATS keyword front-loading (Group B), and stylometric voice variance (Group D).

### Stage 6: Database Logging & State Persistence
- **Execution**:
  - Moves JD to `jds/completed/` via `shutil.move(jd_path, dest)`.
  - Updates `JDTracker().mark_completed(...)`.
  - Appends application row with PDF/DOCX status, source URL, and fit evaluation via `jd_manager.append_application_row(...)`.
  - Runs `db.checkpoint()`.

### Stage 7: Application Package Summary HUD
- **Execution**: Renders a formatted Rich panel in the terminal:
  ```
  ╭────────────────────── Application Package Complete ──────────────────────╮
  │ Role:       Senior Content Strategist                                    │
  │ Company:    Spotify (Enterprise / Workday ATS)                           │
  │ Fit Score:  4.4 / 5.0 (Strong Pursue)                                    │
  │                                                                          │
  │ Resume:                                                                  │
  │   • PDF:  output/morgan/pdf/MorganEscott_Spotify_SeniorContentStrategist.pdf
  │   • DOCX: output/morgan/docx/MorganEscott_Spotify_SeniorContentStrategist.docx
  │                                                                          │
  │ Cover Letter:                                                            │
  │   • PDF:  output/morgan/pdf/MorganEscott_Spotify_CoverLetter.pdf         │
  │   • DOCX: output/morgan/docx/MorganEscott_Spotify_CoverLetter.docx       │
  │                                                                          │
  │ Status: Logged to SQLite database and marked complete.                   │
  ╰──────────────────────────────────────────────────────────────────────────╯
  ```

---

## 5. CLI & User Interface Specifications

### CLI Command (`scripts/cli.py`)
```bash
# Single JD package build (with automatic liveness + fit check + full artifacts)
python scripts/cli.py package jds/Spotify_SeniorContentStrategist.json

# Aliases
python scripts/cli.py build jds/Spotify_SeniorContentStrategist.json

# With referral contact
python scripts/cli.py package jds/Spotify.json --referral "Sarah Connor, VP Engineering"

# Bypass fit 'Skip' gate if the user wants to apply anyway
python scripts/cli.py package jds/Spotify.json --force

# Fast build (skipping liveness browser check)
python scripts/cli.py package jds/Spotify.json --skip-liveness

# Interactive multi-JD picker
python scripts/cli.py package --pick

# Batch mode for all pending JDs
python scripts/cli.py package
```

### Interactive Menu (`scripts/menu.py`)
Add top-level choice in `menu.py`:
```python
"🚀  Build Full Application Package (Liveness → Fit → Resume → Cover Letter → DOCX/PDF)"
```
When selected:
1. Prompts user to select from pending JDs (or all pending).
2. Prompts for optional referral contact if not already set.
3. Executes `run_application_package()` with live Rich step indicators.
4. Shows completion HUD with offer of next steps.

---

## 6. Resilience, Idempotency & Error Handling

1. **Sustained API Failure**: Catches `SustainedFailureError` from `gemini_client.py`. Immediately halts batch runs with human-readable quota instructions rather than cycling through pending JDs.
2. **Partial Failures**: If resume generation succeeds but cover letter generation fails, the resume artifacts and progress are preserved; the JD remains in an inspectable state with clear error reporting.
3. **Checkpoints & Metadata**: If `jd_keywords` or evaluation already exist in metadata/checkpoints, they are reused to avoid redundant LLM invocations.
4. **Collision Protection**: Uses `jd_manager.move_jd_to()` with collision suffixing when moving files to `expired/`, `archived/`, or `completed/`.

---

## 7. Verification & Testing Strategy

1. **Unit Tests (`tests/test_application_package.py`)**:
   - `test_liveness_expired_aborts_early_and_moves_to_expired`: Verifies expired URL stops pipeline before calling LLM.
   - `test_fit_skip_aborts_early_and_moves_to_archived`: Verifies "Skip" recommendation halts tailoring and moves file.
   - `test_fit_skip_with_force_proceeds_to_build`: Verifies `--force` overrides the "Skip" gate.
   - `test_full_package_generates_all_four_artifacts`: Verifies resume PDF/DOCX and cover letter PDF/DOCX are all created and tracked.
   - `test_batch_package_processing`: Verifies multi-JD batch execution and summary counts.
2. **CLI & Menu Tests (`tests/test_cli_package.py`, `tests/test_menu_package.py`)**:
   - Test Click CLI arguments, `--skip-liveness`, `--referral`, `--pick`, and `--force` flags.
   - Test menu flow dispatching to package runner.
3. **Full Suite Regression**:
   - Run complete test suite (`python -m unittest discover -s tests -v`) verifying all 1,648+ tests pass.
