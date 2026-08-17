# 💎 RESUME-BUILDER: COMPREHENSIVE DEVIL'S ADVOCATE AUDIT REPORT

> **Project:** `resume-builder`
> **Evaluation Date:** August 16, 2026
> **Scope:** Full-codebase deep-dive across all 20 operational dimensions, evaluated through four distinct persona lenses (**Senior Enterprise Architect**, **High-End UI/UX Designer**, **Cranky HR Manager/Recruiter**, and **ADHD Job-Seeker**).
> **Methodology:** Static code inspection, schema validation, dependency tree analysis, database model verification, and complete execution of the 1,515 automated unit test suite (`Ran 1515 tests in 112.058s — OK`).

---

## 🎭 EXECUTIVE MULTI-PERSONA AUDIT MATRIX

| Persona | Status | Primary Finding & Strategic Impact |
| :--- | :---: | :--- |
| **Senior Enterprise Architect** | 🔴 **CRITICAL DEBT** | **"Ghost Database" Anti-Pattern:** [`db.py`](file:///Users/morganescott/resume-builder/scripts/db.py) defines an ACID SQLite schema (`data.db`), but live execution in [`orchestrator.py`](file:///Users/morganescott/resume-builder/scripts/orchestrator.py), [`jd_manager.py`](file:///Users/morganescott/resume-builder/scripts/jd_manager.py), and [`menu.py`](file:///Users/morganescott/resume-builder/scripts/menu.py) operates exclusively on flat JSON files, CSV logs, and folder moves. Storing state in two parallel, un-synced representations creates severe data drift. |
| **High-End UI/UX Designer** | 🟠 **HIGH FRAGMENTATION** | **Dual TUI Engine Disconnect:** The visual experience is split between a Go + Bubble Tea dashboard (`dashboard/main.go`) and Python Questionary/Rich prompts (`scripts/menu.py`). Hardcoded dark hex color tokens (`#1e1e2e`, `#313244`) fail on Light Mode terminal backgrounds, and Nerd Font icons render as missing character "tofu" boxes without explicit overrides. |
| **Cranky Recruiter / HR Manager** | 🟢 **ELITE ATS QUALITY** | **Industry-Leading PDF Output:** Vector PDF generation via Typst and Chromium exhibits 100% text-layer fidelity and ATS parseability with explicit ligature disabling. However, when 3-pass LLM bullet trimming fails to bring a resume under 1 page, the system saves multi-page PDFs with orphan lines, violating strict 1-page HR expectations. |
| **ADHD Job-Seeker** | 🔴 **HIGH FRICTION** | **8-Stage Onboarding Blockers:** The bootstrap wizard exposes an overwhelming 8-stage setup pipeline before a user can tailor a single resume. If `data/<profile>/source_docs` is empty, the program halts entirely rather than offering an interactive interview wizard for users starting without a pre-existing resume document. |

---

## 🏛️ PERSONA 1: SENIOR DEVELOPER / ENTERPRISE ARCHITECT AUDIT

### 1. The "Ghost Database" & State Synchronization Drift
* **Code Reference:** [`scripts/db.py`](file:///Users/morganescott/resume-builder/scripts/db.py), [`scripts/jd_manager.py`](file:///Users/morganescott/resume-builder/scripts/jd_manager.py), [`scripts/orchestrator.py`](file:///Users/morganescott/resume-builder/scripts/orchestrator.py).
* **The Vulnerability:** [`README.md`](file:///Users/morganescott/resume-builder/README.md#L67-L71) advertises an *"Embedded ACID SQLite Database (`data.db`) ... Say goodbye to fragile flat-file JSON and CSV synchronization bugs."* However, `db.upsert_job()` is called **only** inside [`migrate_filesystem_to_db.py`](file:///Users/morganescott/resume-builder/scripts/migrate_filesystem_to_db.py#L47). Live orchestration, scanning, liveness checks, and evaluation write exclusively to:
  1. Flat JSON files in `jds/<profile>/` with underscore-prefixed metadata (`_evaluation`, `_liveness`, `_application`, `_research`, `_coverage`).
  2. Folder moves (`jds/<profile>/pending/`, `completed/`, `expired/`, `archived/`).
  3. CSV logs (`bullet-bank-keepers-audited.csv`, `jd_tracker_log.csv`).
* **Architectural Risk:** Running `migrate_filesystem_to_db.py` creates a snapshot in `data.db` that immediately drifts stale the moment `orchestrator.py` processes another job description. A true enterprise architecture must use SQLite as the single authoritative source of truth or enforce automatic real-time bi-directional synchronization.

### 2. Subprocess Coupling & Inter-Process Failure Modes
* **Code Reference:** [`scripts/liveness.py`](file:///Users/morganescott/resume-builder/scripts/liveness.py#L170-L240), [`scripts/generate-pdf.mjs`](file:///Users/morganescott/resume-builder/scripts/generate-pdf.mjs), [`scripts/scan_linkedin.py`](file:///Users/morganescott/resume-builder/scripts/scan_linkedin.py#L153-L180).
* **The Vulnerability:** Python executes Node.js, Go, and Playwright via `subprocess.Popen` or `subprocess.run`. Data transfer occurs via temporary JSON files ([`LIVENESS_INPUT_PATH`](file:///Users/morganescott/resume-builder/scripts/liveness.py#L64)) or standard I/O pipes.
* **Architectural Risk:** If Node or Playwright encounters an unhandled exception or segment fault, the Python parent receives corrupted stdout/stderr streams. While [`liveness.py`](file:///Users/morganescott/resume-builder/scripts/liveness.py#L218-L227) properly kills orphaned Node processes on `KeyboardInterrupt`, other subprocess calls lack explicit process-group cleanup handlers.

### 3. Heavy Dependency Footprint & Version Lock-In
* **Code Reference:** [`pyproject.toml`](file:///Users/morganescott/resume-builder/pyproject.toml), [`package.json`](file:///Users/morganescott/resume-builder/package.json#L19).
* **The Vulnerability:** 22 top-level Python dependencies are required, including `pandas`, `numpy`, `selenium`, `linkedin-jobs-scraper`, `beautifulsoup4`, `browser_cookie3`, `pdfminer.six`, `pypdf`, `odfpy`, and `openpyxl`.
* **Architectural Risk:** `pandas` and `numpy` are imported in [`cluster_bullet_bank.py`](file:///Users/morganescott/resume-builder/scripts/cluster_bullet_bank.py) for basic clustering that could be performed with zero-dependency Python stdlib algorithms. Playwright is pinned to exact `1.61.1` in `package.json` due to macOS 12 Chromium compatibility, preventing security updates on newer OS environments.

---

## 🎨 PERSONA 2: HIGH-END UI/UX DESIGNER AUDIT

### 1. Dual-Engine TUI Disconnect & Experience Splitting
* **Code Reference:** [`dashboard/main.go`](file:///Users/morganescott/resume-builder/dashboard/main.go), [`scripts/menu.py`](file:///Users/morganescott/resume-builder/scripts/menu.py), [`scripts/cli_art.py`](file:///Users/morganescott/resume-builder/scripts/cli_art.py).
* **The Vulnerability:** The user experience is fragmented across two completely different terminal UI frameworks:
  - **Go Bubble Tea Dashboard:** Catppuccin Macchiato theme, Vim-style navigation (`j`/`k`/`Tab`/`Esc`), Lip Gloss bordered panels.
  - **Python Menu System:** Questionary dropdowns, Rich console tables, standard Arrow key navigation.
* **UX Impact:** Keyboard shortcuts and panel focus models shift abruptly when moving from `resume dashboard` to `resume menu`.

### 2. Hardcoded Hex Colors & Light Mode Illiteracy
* **Code Reference:** [`scripts/theme.py`](file:///Users/morganescott/resume-builder/scripts/theme.py), [`DESIGN.md`](file:///Users/morganescott/resume-builder/DESIGN.md#L58-L82).
* **The Vulnerability:** Theme tokens (`#1e1e2e` Midnight base, `#313244` Surface, `#cdd6f4` Text) are hardcoded into Rich console styles and ANSI escape strings.
* **UX Impact:** When launched in a terminal with a light background (Apple Terminal Light, Solarized Light, PowerShell Light), `#cdd6f4` (light lavender) text renders against a white background, creating zero contrast and complete text illegibility.

### 3. Glyph Tofu Rendering & Font Fallback Missing
* **Code Reference:** [`scripts/cli_art.py`](file:///Users/morganescott/resume-builder/scripts/cli_art.py), [`scripts/theme.py`](file:///Users/morganescott/resume-builder/scripts/theme.py#L253-L274).
* **The Vulnerability:** Navigation icons default to Nerd Font glyphs (`ICONS_NERD`).
* **UX Impact:** If the user's terminal emulator lacks a Nerd Font patch (standard default on macOS/Windows/Linux), icons render as missing character boxes (`` or `[?]`). While `RESUME_BUILDER_ICONS=unicode` exists as an override, the system does not automatically detect glyph rendering capabilities on launch.

---

## 👔 PERSONA 3: CRANKY RECRUITER / HR MANAGER AUDIT

### 1. STAR / XYZ Formula Over-Strictness & Template Fatigue
* **Code Reference:** [`scripts/validate_resume.py`](file:///Users/morganescott/resume-builder/scripts/validate_resume.py#L180-L240).
* **Recruiter Impact:** Programmatic validation enforces Google's XYZ formula (*Accomplished [X], as measured by [Y], by doing [Z]*). While metrics are critical, over-enforcing numeric metrics across every bullet causes resumes to sound artificial. Bullets like *"Engineered 14 microservices achieving 34% throughput boost by implementing gRPC"* read as manufactured when all 20 experience bullets follow the exact same metric structure.

### 2. Trim Pass Failures Outputting Multi-Page Resumes
* **Code Reference:** [`scripts/orchestrator.py`](file:///Users/morganescott/resume-builder/scripts/orchestrator.py#L820-L890).
* **Recruiter Impact:** When a tailored resume exceeds 1 page, `orchestrator.py` runs up to 3 LLM trim passes. If after 3 attempts the PDF is still 1 page + 3 lines on page 2, the system logs a warning (`✗ PDF still 2 pages after 3 trim attempts`) and **saves the multi-page PDF anyway.** Resumes with short orphan lines on page 2 appear unpolished and careless during 6-second recruiter scans.

### 3. Vocabulary Substitution Distortions
* **Code Reference:** [`scripts/company_research.py`](file:///Users/morganescott/resume-builder/scripts/company_research.py#L120-L160).
* **Recruiter Impact:** Corporate register vocabulary substitutions (e.g., replacing "customers" with "guests" or "clients" with "patients") are injected into LLM rewrite prompts. Global replacements can distort technical terminology—turning *"Developed client-side caching module"* into *"Developed patient-side caching module"*, instantly exposing AI-generated text.

---

## ⚡ PERSONA 4: ADHD JOB-SEEKER AUDIT

### 1. High-Friction 8-Stage Onboarding Gate
* **Code Reference:** [`scripts/bootstrap_menu.py`](file:///Users/morganescott/resume-builder/scripts/bootstrap_menu.py#L280-L325).
* **UX Impact:** The onboarding wizard presents an 8-stage progress table (Phase 0 Ingestion, Phase 0.5 Profile, Stage 1 Audit, Stage 2 Cluster, Stage 3 Rewrite, Stage 4 Audit Keepers, Stage 5 Score Gems, Stage 6 Embed) before allowing a user to tailor a single resume. This creates substantial cognitive fatigue and setup friction.

### 2. Zero-Document Onboarding Dead End
* **Code Reference:** [`scripts/bootstrap_menu.py`](file:///Users/morganescott/resume-builder/scripts/bootstrap_menu.py#L83-L89).
* **UX Impact:** If `data/<profile>/source_docs` contains no files, Step 0 halts completely and prints instructions telling the user to manually copy files into the folder. A job seeker without a pre-existing resume PDF/DOCX (e.g., recent graduate or career switcher) is completely blocked, as there is no interactive step-by-step interview wizard to generate a baseline profile from scratch.

### 3. Liveness False-Positives Silently Moving Active Jobs
* **Code Reference:** [`scripts/liveness-core.mjs`](file:///Users/morganescott/resume-builder/scripts/liveness-core.mjs#L19-L22), [`scripts/liveness.py`](file:///Users/morganescott/resume-builder/scripts/liveness.py#L272).
* **UX Impact:** `liveness-core.mjs` uses regex patterns like `/d+\s+jobs?\s+found/i` to identify search result pages. If an active job description contains a sidebar displaying "12 jobs found in Engineering", `classifyLiveness()` incorrectly classifies the posting as `expired` and automatically moves the file to `jds/<profile>/expired/`. Active opportunities vanish from the pending queue without user notification.

---

## 🔍 FULL 20-DIMENSION OPERATIONAL MATRIX

| # | Dimension | Status | Key Codebase Location | Root Cause / Critical Flaw |
|---| :--- | :---: | :--- | :--- |
| **1** | **TUI / UX** | 🟠 | [`scripts/menu.py`](file:///Users/morganescott/resume-builder/scripts/menu.py), [`dashboard/main.go`](file:///Users/morganescott/resume-builder/dashboard/main.go) | Disconnect between Go Bubble Tea and Python Questionary/Rich; hardcoded dark hex colors fail on Light Mode terminals. |
| **2** | **Onboarding Flow** | 🔴 | [`scripts/bootstrap_menu.py`](file:///Users/morganescott/resume-builder/scripts/bootstrap_menu.py) | Overwhelming 8-stage setup gate; halts completely if `source_docs` is empty instead of offering a zero-document interview wizard. |
| **3** | **Liveness System** | 🔴 | [`scripts/liveness-core.mjs`](file:///Users/morganescott/resume-builder/scripts/liveness-core.mjs) | Regex false-positives (`/d+ jobs found/i`) incorrectly classify active postings as `expired` and move them to `jds/expired/`. |
| **4** | **Scoring & Evaluation** | 🟠 | [`scripts/batch_evaluate.py`](file:///Users/morganescott/resume-builder/scripts/batch_evaluate.py#L19) | Forced `4.5s` sleep between Gemini API calls delays batch processing; deal-breaker rules aggressively zero out flexible roles. |
| **5** | **Job Board Scans** | 🔴 | [`scripts/scan_linkedin.py`](file:///Users/morganescott/resume-builder/scripts/scan_linkedin.py) | Requires Chrome via `browser_cookie3`; triggers Keychain prompts; Selenium fails on Android ARM (Termux). 5s extra sleep per job. |
| **6** | **Pipeline Management** | 🟠 | [`scripts/jd_manager.py`](file:///Users/morganescott/resume-builder/scripts/jd_manager.py) | Funnel state updates (`applied`, `interviewing`, `offer`) are completely manual and disconnected from real ATS portals. |
| **7** | **Company Research** | 🟠 | [`scripts/company_research.py`](file:///Users/morganescott/resume-builder/scripts/company_research.py) | Web scraping failures fall back to LLM grounding; global vocabulary replacements risk altering technical engineering terms. |
| **8** | **Resume Tailoring** | 🟠 | [`scripts/orchestrator.py`](file:///Users/morganescott/resume-builder/scripts/orchestrator.py) | Two-pass bullet selection prevents metric collisions, but failed 3-pass trim loops produce multi-page PDFs with orphan lines. |
| **9** | **Overall Architecture** | 🔴 | [`scripts/db.py`](file:///Users/morganescott/resume-builder/scripts/db.py) vs [`orchestrator.py`](file:///Users/morganescott/resume-builder/scripts/orchestrator.py) | "Ghost Database": `data.db` exists but live operations rely entirely on flat JSON files, CSV logs, and filesystem directory moves. |
| **10** | **Bullet Bank Engine** | 🟠 | [`scripts/cluster_bullet_bank.py`](file:///Users/morganescott/resume-builder/scripts/cluster_bullet_bank.py) | Unnecessary heavy dependency footprint (`pandas`, `numpy`) for bullet clustering that stdlib could execute. |
| **11** | **Writing Voice Adoption** | 🟢 | [`scripts/build_voice_anchors.py`](file:///Users/morganescott/resume-builder/scripts/build_voice_anchors.py) | Effective prompt anchoring via `voice-anchors.md`, backed by post-hoc holistic critique passes. |
| **12** | **Knowledge Base** | 🟠 | [`scripts/orchestrator.py`](file:///Users/morganescott/resume-builder/scripts/orchestrator.py#L276) | `KB_ALLOWLIST` explicitly filters files in `data/`, silently ignoring unlisted files added by the user. |
| **13** | **Dependencies** | 🟠 | [`pyproject.toml`](file:///Users/morganescott/resume-builder/pyproject.toml), [`package.json`](file:///Users/morganescott/resume-builder/package.json) | 22 Python packages; Playwright pinned to exact `1.61.1` due to legacy macOS 12 compatibility. |
| **14** | **Test Suite** | 🟢 | [`tests/`](file:///Users/morganescott/resume-builder/tests/) | Excellent coverage (1,515 unit tests pass in 112s), but lacks automated visual regression checks for compiled PDFs. |
| **15** | **Doctor Script** | 🟢 | [`scripts/doctor.py`](file:///Users/morganescott/resume-builder/scripts/doctor.py) | Comprehensive health check for environment dependencies, but lacks database sync checks and Termux driver validation. |
| **16** | **Documentation** | 🟠 | [`README.md`](file:///Users/morganescott/resume-builder/README.md), [`CLAUDE.md`](file:///Users/morganescott/resume-builder/CLAUDE.md) | High quality documentation, but overstates SQLite integration and Termux out-of-the-box compatibility. |
| **17** | **Mobile Compatibility** | 🔴 | [`scripts/install.sh`](file:///Users/morganescott/resume-builder/scripts/install.sh) | Playwright Chromium and Selenium ChromeDriver binaries fail on Android ARM (Termux); UI wraps poorly on small screens. |
| **18** | **Cross-Platform** | 🟠 | [`scripts/resume-cli.sh`](file:///Users/morganescott/resume-builder/scripts/resume-cli.sh) | Shell scripts assume POSIX/zsh/bash, failing natively on Windows CMD/PowerShell without WSL. |
| **19** | **Multi-Machine Sync** | 🟠 | [`scripts/profile_paths.py`](file:///Users/morganescott/resume-builder/scripts/profile_paths.py) | Syncthing syncs `profiles/<profile>/`, risking SQLite database lock corruption if `data.db-wal` is synced during active writes. |
| **20** | **Storage & Sync** | 🔴 | [`scripts/db.py`](file:///Users/morganescott/resume-builder/scripts/db.py) | Triple state representation across JSON files, CSV logs, and SQLite `data.db` without automated synchronization triggers. |
