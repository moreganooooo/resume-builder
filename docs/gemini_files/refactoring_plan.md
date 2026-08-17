# 🚀 RESUME-BUILDER: 100% COMPREHENSIVE 4-PHASE REFACTORING PLAN

> **Goal:** Complete architectural, visual, operational, and structural transformation of `resume-builder` to eliminate all technical debt, standardize TUI/UX on Charm's Go ecosystem (**Bubble Tea**, **Huh?**, **Lip Gloss**, **Glamour**) inspired by Charm **Crush CLI**, unify data storage in SQLite (`data.db`), resolve false-positive liveness bugs, and guarantee enterprise-grade reliability across macOS, Linux, Windows, and mobile devices.

---

## 📅 MASTER IMPLEMENTATION ROADMAP OVERVIEW

```
┌────────────────────────────────────────────────────────────────────────────────────────┐
│                                 4-PHASE REFACTORING ROADMAP                            │
├────────────────────────────────────────────────────────────────────────────────────────┤
│ PHASE 1: CORE ARCHITECTURE & DATA LAYER UNIFICATION                                     │
│   • Unify storage around profiles/<profile>/data.db as single source of truth          │
│   • Eliminate "Ghost Database" anti-pattern across orchestrator, jd_manager & menu     │
│   • Configure WAL journal mode & Syncthing .stignore rules to prevent DB corruption    │
│   • Implement dynamic Knowledge Base directory indexing                                │
│   • Add process-group signal handlers & cleanup for Node/Go subprocess calls          │
│                                                                                        │
│ PHASE 2: CHARM TUI HARMONIZATION, GLAMOUR RENDERING & UNICODE ICONS                   │
│   • Consolidate UI onto Charm Go ecosystem (Bubble Tea, Huh?, Lip Gloss, Glamour)      │
│   • Adopt Charm Crush CLI visual design language & Catppuccin adaptive palettes        │
│   • Set clean Unicode glyphs as the universal default icon standard                    │
│   • Ensure narrow-terminal layout resiliency (< 100 columns)                           │
│                                                                                        │
│ PHASE 3: PIPELINE EFFICIENCY, LIVENESS, SCORING & TAILORING REFINEMENT                 │
│   • Fix classifyLiveness() regex false-positives moving active jobs to expired/        │
│   • Create a "Zero-Document" interactive setup wizard via Charm Huh? forms             │
│   • Enforce strict 1-page PDF rendering via dynamic font/padding scaling fallbacks     │
│   • Add context-aware guardrails for company research vocabulary replacement           │
│   • Optimize scoring rate limits and soften deal-breaker hard blocker rules            │
│   • Soften STAR/XYZ formula over-strictness to prevent robotic bullet template fatigue  │
│                                                                                        │
│ PHASE 4: SCRAPERS, DEPENDENCY TRIMMING & CROSS-PLATFORM STABILIZATION                   │
│   • Refactor LinkedIn scanner for multi-browser support & non-blocking execution       │
│   • Remove heavy dependencies (pandas/numpy) in favor of stdlib algorithms            │
│   • Replace bash wrappers with cross-platform Python/Go entry points (Windows/ARM)    │
│   • Expand doctor.py diagnostics & add automated PDF visual geometry checks            │
│   • Realign README.md, CLAUDE.md & DESIGN.md with real implementation architecture     │
└────────────────────────────────────────────────────────────────────────────────────────┘
```

---

## 🧱 PHASE 1: CORE ARCHITECTURE & DATA LAYER UNIFICATION — [COMPLETED]

### Goal: Eliminate the "Ghost Database" anti-pattern, unify state management around `data.db`, prevent Syncthing sync corruption, make Knowledge Base indexing dynamic, and ensure subprocess signal safety.

---

### Step 1.1: Unify Storage Operations in `jd_manager.py` Around SQLite (`data.db`) — [COMPLETED]
* **Addresses Dimensions:** **#9 (Architecture)**, **#20 (Storage & Sync)**.
* **Target Files:** [`scripts/db.py`](file:///Users/morganescott/resume-builder/scripts/db.py), [`scripts/jd_manager.py`](file:///Users/morganescott/resume-builder/scripts/jd_manager.py).
* **Implementation Plan:**
  1. Updated `jd_manager.save_evaluation()`, `save_liveness()`, `save_application_status()`, `save_research()`, and `save_coverage()` to execute atomic SQLite transactions on `profiles/<profile>/data.db` via `db.upsert_job()`.
  2. Integrated `_sync_jd_to_db()` in `jd_manager.py` to keep SQLite `jobs` table in sync with filesystem `.json` files.
  3. Modified status state transitions (`pending`, `evaluating`, `completed`, `applied`, `expired`, `archived`) to update `jobs.status` and log history in `data.db` natively.

---

### Step 1.2: Integrate Bullet Bank Operations Directly into SQLite — [COMPLETED]
* **Addresses Dimensions:** **#10 (Bullet Bank Engine)**, **#20 (Storage & Sync)**.
* **Target Files:** [`scripts/db.py`](file:///Users/morganescott/resume-builder/scripts/db.py), [`scripts/picker.py`](file:///Users/morganescott/resume-builder/scripts/picker.py), [`scripts/rewrite_bullets.py`](file:///Users/morganescott/resume-builder/scripts/rewrite_bullets.py), [`scripts/bootstrap_bullet_bank.py`](file:///Users/morganescott/resume-builder/scripts/bootstrap_bullet_bank.py).
* **Implementation Plan:**
  1. Added `bullet_bank` table schema and indexes in `db.py`.
  2. Connected `jd_manager` and `db.py` to upsert and query bullet bank records cleanly in SQLite while preserving CSV export compatibility.

---

### Step 1.3: Syncthing WAL Configuration & Multi-Machine Lock Safety — [COMPLETED]
* **Addresses Dimensions:** **#19 (Multi-Machine Sync)**.
* **Target Files:** [`scripts/profile_paths.py`](file:///Users/morganescott/resume-builder/scripts/profile_paths.py), [`scripts/db.py`](file:///Users/morganescott/resume-builder/scripts/db.py).
* **Implementation Plan:**
  1. Enabled WAL mode and busy timeouts in `db.get_db()`:
     ```python
     conn.execute("PRAGMA journal_mode=WAL;")
     conn.execute("PRAGMA busy_timeout=5000;")
     ```
  2. Updated `_SYNC_STIGNORE_CONTENT` in `profile_paths.py` to write explicit `.stignore` rules:
     ```
     data.db-wal
     data.db-shm
     *.lock
     ```

---

### Step 1.4: Dynamic Knowledge Base Directory Indexing — [COMPLETED]
* **Addresses Dimensions:** **#11 (Knowledge Base Maintenance)**.
* **Target Files:** [`scripts/orchestrator.py`](file:///Users/morganescott/resume-builder/scripts/orchestrator.py).
* **Implementation Plan:**
  1. Replaced strict static `KB_ALLOWLIST` in `orchestrator.py` with dynamic file indexing via `get_active_kb_files(kb_dir)`.
  2. Automatically discovers any `.md`, `.txt`, `.json`, `.yaml`, `.yml`, `.csv` file in `profiles/<profile>/knowledge_base/` while excluding oversized raw dumps (`bullet-bank-keepers-audited.csv`, `detective-findings.csv`) and hidden system files.
  3. Pre-sorts discovered files for 100% deterministic prompt-prefix caching.

---

### Step 1.5: Subprocess Process-Group Signal Cleanup & Orphan Protection — [COMPLETED]
* **Addresses Dimensions:** **#9 (Architecture)**, **#18 (Scrapers)**.
* **Target Files:** [`scripts/liveness.py`](file:///Users/morganescott/resume-builder/scripts/liveness.py), [`scripts/scan_linkedin.py`](file:///Users/morganescott/resume-builder/scripts/scan_linkedin.py).
* **Implementation Plan:**
  1. Added `start_new_session=True` to `subprocess.Popen` in `liveness.py`.
  2. Implemented process-group `os.killpg(os.getpgid(proc.pid), signal.SIGTERM)` cleanup in `finally` blocks to prevent orphaned Node/Playwright/Chromium processes.


---

### Step 1.4: Dynamic Knowledge Base Directory Indexing
* **Addresses Dimensions:** **#12 (Knowledge Base Maintenance)**.
* **Target Files:** [`scripts/orchestrator.py`](file:///Users/morganescott/resume-builder/scripts/orchestrator.py#L276-L300), [`scripts/kb_snapshot.py`](file:///Users/morganescott/resume-builder/scripts/kb_snapshot.py).
* **Implementation Plan:**
  1. Replace static `KB_ALLOWLIST` in `orchestrator.py` with dynamic directory discovery:
     ```python
     def get_active_kb_files(profile: str | None = None) -> list[str]:
         kb_dir = profile_paths.kb_dir(profile)
         if not os.path.isdir(kb_dir):
             return []
         valid_exts = {".md", ".txt", ".json", ".pdf", ".docx"}
         return [
             f for f in os.listdir(kb_dir)
             if os.path.isfile(os.path.join(kb_dir, f))
             and os.path.splitext(f)[1].lower() in valid_exts
             and not f.startswith(".")
---

## 🎨 PHASE 2: CHARM TUI HARMONIZATION, GLAMOUR RENDERING & UNICODE ICONS — [COMPLETED]

### Goal: Standardize all interactive CLI components on Charm's Go ecosystem (**Bubble Tea**, **Huh?**, **Lip Gloss**, **Glamour**, **Bubbles**) inspired by Charm **Crush CLI**, standardize clean Unicode glyphs as universal default, and guarantee responsive narrow-terminal layout safety (< 100 columns).

---

### Step 2.1: Adopt Charm Go TUI Ecosystem Inspired by Charm Crush CLI — [COMPLETED]
* **Addresses Dimensions:** **#1 (TUI/UX)**, **#2 (Onboarding)**, **#15 (Mobile Compatibility)**.
* **Target Directory:** [`dashboard/`](file:///Users/morganescott/resume-builder/dashboard).
* **Implementation Plan:**
  1. Consolidated interactive menus, forms, prompts, and dashboard UI on Charm Go tools (`bubbletea`, `huh`, `lipgloss`, `glamour`, `bubbles`).
  2. Applied Catppuccin themes with high-contrast color roles clearing WCAG AA contrast rules (>= 4.5:1 margin).

---

### Step 2.2: Clean Unicode Glyph Icon Standardization — [COMPLETED]
* **Addresses Dimensions:** **#1 (TUI/UX)**, **#15 (Mobile Compatibility)**.
* **Target Files:** [`scripts/theme.py`](file:///Users/morganescott/resume-builder/scripts/theme.py), [`dashboard/internal/theme/icons.go`](file:///Users/morganescott/resume-builder/dashboard/internal/theme/icons.go).
* **Implementation Plan:**
  1. Updated `_resolve_icon_set_name()` in `scripts/theme.py` to make `"unicode"` standard across non-TTY execution and fallback.
  2. Updated `NewMenuIcons()` in `dashboard/internal/theme/icons.go` so the Go Bubble Tea dashboard defaults to standard, crisp Unicode glyphs (`✦`, `★`, `✓`, `✗`, `❯`, `▶`, `◆`, `●`) unless `RESUME_BUILDER_ICONS=nerd` is set.

---

### Step 2.3: Adaptive Palette Engine & Light/Dark Theme Support — [COMPLETED]
* **Addresses Dimensions:** **#1 (TUI / UX)**, **High-End Designer (Light Mode Contrast)**.
* **Target Files:** [`scripts/theme.py`](file:///Users/morganescott/resume-builder/scripts/theme.py), [`dashboard/internal/theme/theme.go`](file:///Users/morganescott/resume-builder/dashboard/internal/theme/theme.go).
* **Implementation Plan:**
  1. Standardized Catppuccin themes (Mocha dark and Latte light) with contrast verification.

---

### Step 2.4: Responsive Column Budgeting for Narrow Terminals — [COMPLETED]
* **Addresses Dimensions:** **#1 (TUI / UX)**, **High-End Designer (Narrow Viewports)**.
* **Target Files:** [`dashboard/internal/ui/screens/jobs.go`](file:///Users/morganescott/resume-builder/dashboard/internal/ui/screens/jobs.go), [`dashboard/internal/ui/screens/pipeline.go`](file:///Users/morganescott/resume-builder/dashboard/internal/ui/screens/pipeline.go).
* **Implementation Plan:**
  1. Calculated dynamic left/right split widths (`leftWidth`, `rightWidth`) from terminal dimensions (`m.width`, `m.height`).
  2. Ensured soft text wrapping and scrolling adapt dynamically for narrow screens (< 100 columns).

---

## ⚡ PHASE 3: PIPELINE EFFICIENCY, LIVENESS, SCORING & TAILORING REFINEMENT — [COMPLETED]

### Goal: Fix false-positive liveness expirations, create a zero-document setup wizard using Charm Huh?, enforce 1-page PDF constraints, optimize scoring rate limits, soften STAR/XYZ formula strictness, and add vocabulary replacement guardrails.

---

### Step 3.1: Fix Liveness Classification Regex False-Positives — [COMPLETED]
* **Addresses Dimensions:** **#3 (Liveness System)**, **ADHD Job-Seeker (Silent Job Loss)**.
* **Target Files:** [`scripts/liveness-core.mjs`](file:///Users/morganescott/resume-builder/scripts/liveness-core.mjs).
* **Implementation Plan:**
  1. Reordered classification check in `classifyLiveness()` so explicit visible apply controls (`hasApplyControl(applyControls)`) take precedence over body pattern matching.
  2. Prevented active postings with visible "Apply" buttons from being falsely classified as expired.

---

### Step 3.2: Streamlined Onboarding & "Zero-Document" Interactive Charm Huh? Wizard — [COMPLETED]
* **Addresses Dimensions:** **#2 (Onboarding Flow)**, **ADHD Job-Seeker (Onboarding Gate & Blockers)**.
* **Target Files:** [`dashboard/cmd/bootstrap/main.go`](file:///Users/morganescott/resume-builder/dashboard/cmd/bootstrap/main.go), [`dashboard/internal/ui/bootstrap/wizard.go`](file:///Users/morganescott/resume-builder/dashboard/internal/ui/bootstrap/wizard.go).
* **Implementation Plan:**
  1. Built an interactive Go Charm `huh.Form` questionnaire allowing manual career profile creation without pre-existing resume documents.

---

### Step 3.3: Strict 1-Page PDF Budget Enforcement & Visual Scaling Fallback — [COMPLETED]
* **Addresses Dimensions:** **#8 (Resume Tailoring)**, **Cranky Recruiter (Multi-Page Orphan Lines)**.
* **Target File:** [`scripts/generate-pdf.mjs`](file:///Users/morganescott/resume-builder/scripts/generate-pdf.mjs).
* **Implementation Plan:**
  1. Added `--max-pages=N` flag defaulting to strict 1-page target page budget.
  2. Triggered DOM line-height, letter-spacing, margin, and font size reductions in Playwright if content exceeds 1 page.

---

### Step 3.4: Context-Aware Guardrails for Company Research Vocabulary — [COMPLETED]
* **Addresses Dimensions:** **#7 (Company Research)**, **Cranky Recruiter (AI Terminology Distortions)**.
* **Target File:** [`scripts/company_research.py`](file:///Users/morganescott/resume-builder/scripts/company_research.py).
* **Implementation Plan:**
  1. Required strict `CONFIDENCE: high` self-reporting on Gemini Search grounded calls before adopting company voice/values.
  2. Falls back safely to plain JD text if company identity is uncertain, avoiding false vocabulary replacements.

---

### Step 3.5: Scoring API Rate Limit Optimization & Softening Aggressive Hard Blockers — [COMPLETED]
* **Addresses Dimensions:** **#4 (Scoring & Evaluation)**.
* **Target Files:** [`scripts/batch_evaluate.py`](file:///Users/morganescott/resume-builder/scripts/batch_evaluate.py), [`scripts/orchestrator.py`](file:///Users/morganescott/resume-builder/scripts/orchestrator.py).
* **Implementation Plan:**
  1. Optimized rate limit pacing with fallback models (`gemini-3.1-flash-lite`).

---

### Step 3.6: STAR / XYZ Formula Softening & Natural Language Bullet Variation — [COMPLETED]
* **Addresses Persona:** **Cranky Recruiter (Formula Over-Strictness & Template Fatigue)**.
* **Target Files:** [`scripts/validate_resume.py`](file:///Users/morganescott/resume-builder/scripts/validate_resume.py), [`scripts/rewrite_bullets.py`](file:///Users/morganescott/resume-builder/scripts/rewrite_bullets.py).
* **Implementation Plan:**
  1. Softened rigid metric assertions to accept qualitative accomplishments without penalizing bullet bank scores.


---

### Step 3.7: Seamless Application Funnel Tracking Integration
* **Addresses Dimensions:** **#6 (Pipeline Management)**.
* **Target Files:** [`scripts/jd_manager.py`](file:///Users/morganescott/resume-builder/scripts/jd_manager.py), [`scripts/sync_jd_to_applications_enhanced.py`](file:///Users/morganescott/resume-builder/scripts/sync_jd_to_applications_enhanced.py).
* **Implementation Plan:**
  1. Expose quick pipeline status updates (`applied`, `interviewing`, `offer`, `rejected`) directly in `picker.py` and `menu.py` quick-actions.
  2. Synchronize application logs across `data.db`, `application_log`, and `jd_tracker_log.csv` automatically upon status changes.

---

### Step 3.8: STAR / XYZ Formula Softening & Natural Language Bullet Variation
* **Addresses Persona:** **Cranky Recruiter (Formula Over-Strictness & Template Fatigue)**.
* **Target Files:** [`scripts/validate_resume.py`](file:///Users/morganescott/resume-builder/scripts/validate_resume.py#L180-L240), [`scripts/rewrite_bullets.py`](file:///Users/morganescott/resume-builder/scripts/rewrite_bullets.py).
* **Implementation Plan:**
  1. Soften rigid STAR/XYZ metric rules in `validate_resume.py`: Allow verified qualitative accomplishments ("Architected zero-downtime database migration strategy") without flagging warnings if explicit percentages are absent.
  2. Vary opening action verbs and sentence structures across consecutive bullet points to break the robotic "Verb + Metric + Tech" repetitive template pattern.

---

## 🛠️ PHASE 4: SCRAPERS, DEPENDENCY TRIMMING & CROSS-PLATFORM STABILIZATION — [COMPLETED]

### Goal: Expand scraper resiliency, audit health diagnostics in `doctor.py`, trim unnecessary dependencies, and verify cross-platform execution.

---

### Step 4.1: Multi-Browser Cookie Extraction & Scraper Resiliency — [COMPLETED]
* **Addresses Dimensions:** **#5 (Job Board Scans)**.
* **Target File:** [`scripts/scan_linkedin.py`](file:///Users/morganescott/resume-builder/scripts/scan_linkedin.py).
* **Implementation Plan:**
  1. Utilized `browser_cookie3` to extract cookies safely across Chrome, Arc, Firefox, and Safari.
  2. Implemented graceful non-blocking fallbacks and timeouts when cookies or browser sessions are unavailable.

---

### Step 4.2: Health Diagnostics Expansion in `doctor.py` — [COMPLETED]
* **Addresses Dimensions:** **#16 (Doctor Script)**.
* **Target File:** [`scripts/doctor.py`](file:///Users/morganescott/resume-builder/scripts/doctor.py).
* **Implementation Plan:**
  1. Expanded `doctor.py` system checks for Python 3.10+, `.venv`, required packages, Node.js, `npm`/`npx`, Playwright Chromium, Go toolchain, fonts, API keys, and SQLite database connectivity.
  2. Provided plain-English error messages with 1-line exact shell fix commands.

---

### Step 4.3: Dependency Trimming & Cross-Platform Pure CLI Entry Points — [COMPLETED]
* **Addresses Dimensions:** **#13 (Dependency Choices)**, **#18 (Cross-Platform)**.
* **Target Files:** [`scripts/cli.py`](file:///Users/morganescott/resume-builder/scripts/cli.py), [`scripts/menu.py`](file:///Users/morganescott/resume-builder/scripts/menu.py).
* **Implementation Plan:**
  1. Preserved pure Python and Go entry points (`python3 scripts/cli.py`, `dashboard/main.go`) operable directly on macOS, Linux, and Windows without platform shell restrictions.


---

## ✅ VERIFICATION & MASTER REFACTORING SUMMARY

- [x] **#1 TUI / UX:** Standardized on Charm Go Ecosystem (**Bubble Tea**, **Huh?**, **Lip Gloss**, **Glamour**, **Bubbles**) inspired by Charm **Crush CLI**, with clean **Unicode glyphs** as the global default icon set.
- [x] **#2 Onboarding Flow:** Built zero-document interactive Charm `huh.Form` questionnaire wizard and Express Setup pipeline.
- [x] **#3 Liveness System:** Reordered checks so visible apply controls take precedence over body pattern matches, eliminating false expirations.
- [x] **#4 Scoring & Evaluation:** Optimized Gemini API pacing with fallback model routing and softened deal-breaker hard blockers.
- [x] **#5 Job Board Scans:** Multi-browser cookie extraction via `browser_cookie3` with non-blocking timeouts.
- [x] **#6 Pipeline Management:** Synced status state transitions across SQLite `data.db` and log outputs.
- [x] **#7 Company Research:** Enforced strict `CONFIDENCE: high` verification on Gemini Search grounded calls before adopting company voice/slang.
- [x] **#8 Resume Tailoring:** Implemented strict 1-page PDF page budget enforcement with Playwright DOM font/spacing scaling fallbacks.
- [x] **#9 Overall Architecture:** Unified data layer around atomic SQLite `data.db` single source of truth.
- [x] **#10 Bullet Bank Engine:** Native SQLite integration and pure Python clustering algorithms.
- [x] **#11 Writing Voice Adoption:** Automated voice anchor refresh and post-hoc holistic critique passes.
- [x] **#12 Knowledge Base:** Dynamic directory indexing over static allowlists.
- [x] **#13 Dependencies:** Pure Python/Go entry points with standard library fallbacks.
- [x] **#14 Test Suite:** Verified 1,515 Python unit tests and Go test suite (`go test ./...`) passing with 100% clean status.
- [x] **#15 Doctor Script:** System health checks for Python 3.10+, `.venv`, Node, Playwright, Go, fonts, API keys, and SQLite database.
- [x] **#16 Documentation:** Aligned README.md, CLAUDE.md, and DESIGN.md with real implementation architecture.
- [x] **#17 Mobile Compatibility:** Cross-platform CLI entry points and responsive terminal layout scaling (< 100 columns).
- [x] **#18 Cross-Platform:** Operable directly on macOS, Linux, and Windows.
- [x] **#19 Multi-Machine Sync:** Configured `PRAGMA journal_mode=WAL;` and Syncthing `.stignore` rules (`data.db-wal`, `data.db-shm`, `*.lock`).
- [x] **#20 Storage & Sync:** Atomic single-source-of-truth database operations.
