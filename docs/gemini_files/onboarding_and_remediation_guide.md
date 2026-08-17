# 🚀 Developer Onboarding & Master Remediation Guide: `resume-builder`
### Technical Implementation, Architecture Fixes & Step-by-Step Code Updates for All 35 Audit Findings

---

## 📌 Guide Overview & Architecture Intent

Welcome to the **Developer Onboarding & Master Remediation Guide** for `resume-builder`. This manual provides new and existing maintainers with precise, step-by-step engineering specifications, technical root cause analyses, code refactoring blueprints, and verification checklists to address all **35 audit issues** identified across the system.

---

## 🧭 Master Implementation Task Checklist

- [ ] **Phase 1: Architecture & Technical Debt (Issues 1–6)**
  - [ ] Task 1.1: Refactor Monolithic Scripts into Modular Sub-Packages (`orchestrator.py`, `menu.py`, `rewrite_bullets.py`, `audit_keepers.py`, `validate_resume.py`)
  - [ ] Task 1.2: Containerize & Standardize 4-Runtime Polyglot Toolchain (Docker / DevContainer)
  - [ ] Task 1.3: Eliminate Circular Import Workarounds via Client Dependency Injection
  - [ ] Task 1.4: Replace Hardcoded Python Binary Paths with Dynamic `sys.executable`
  - [ ] Task 1.5: Migrate Subprocess `which` Calls to Cross-Platform `shutil.which`
  - [ ] Task 1.6: Clean Repository Root Clutter and Archive Legacy Working Files

- [ ] **Phase 2: State Persistence, Storage & Syncthing (Issues 7–11)**
  - [ ] Task 2.1: Unify State Architecture Around SQLite (`data.db`) as Single Source of Truth
  - [ ] Task 2.2: Refactor Go TUI Handlers (`career.go`) to Query SQLite Directly
  - [ ] Task 2.3: Expand SQLite `CHECK` Constraint for All Pipeline Statuses in `db.py`
  - [ ] Task 2.4: Resolve Syncthing SQLite WAL Lock Contention & Ignore Conflict Files
  - [ ] Task 2.5: Implement Atomic File Locks (`fcntl.flock`) for CSV Tracker Log Writes

- [ ] **Phase 3: Security, Secrets Hygiene & Privacy (Issues 12–14)**
  - [ ] Task 3.1: Secure API Keys and LinkedIn Cookies in OS Keyring Vault
  - [ ] Task 3.2: Exclude Plaintext Credential Files (`.env`, `.linkedin_cookie`) from Syncthing Shares
  - [ ] Task 3.3: Implement Regex PII Scrubbing Filters in Terminal Loggers and Checkpoints

- [ ] **Phase 4: Scrapers, Liveness & Third-Party Reliability (Issues 15–17)**
  - [ ] Task 4.1: Isolate Node.js Scraper Process Failures with Structured JSON Response Contracts
  - [ ] Task 4.2: Implement Graceful Cookie Prompts for LinkedIn Scraper Keychain Failures
  - [ ] Task 4.3: Classify Anti-Bot 403/429 Challenges as "Unknown/Deferred" in Liveness Sweep

- [ ] **Phase 5: Resume Tailoring, Google XYZ & Recruiter Impact (Issues 18–22)**
  - [ ] Task 5.1: Relax `validate_resume.py` to Support Qualitative Achievements Alongside XYZ
  - [ ] Task 5.2: Enforce Fact-Grounding Assertions against Raw Source Bullets During Rewrites
  - [ ] Task 5.3: Filter Scraping Marketing Buzzwords in Company Research Prompts
  - [ ] Task 5.4: Implement CSS `page-break-inside: avoid` and Dynamic Line-Budgeting for PDFs
  - [ ] Task 5.5: Add Full Typst Special Character Escaping (`[`, `]`, `_`, `#`, `$`, `@`)

- [ ] **Phase 6: UI/UX, TUI Ergonomics & Design Systems (Issues 23–25)**
  - [ ] Task 6.1: Unify UI Color Tokens and Spacing Components across Go and Python TUIs
  - [ ] Task 6.2: Replace Fixed 80-Column ASCII Art Banners with Responsive `rich` Console Panels
  - [ ] Task 6.3: Auto-Detect Font Glyph Capabilities and Fall Back Gracefully for Non-Nerd Fonts

- [ ] **Phase 7: Algorithms, Vector RAG & Prompt Design (Issues 26–28)**
  - [ ] Task 7.1: Re-Label "Bayesian Probability Converter" Documentation to "Piecewise Scale"
  - [ ] Task 7.2: Auto-Trigger Background Vector Re-Embedding on Bullet CSV Hash Updates
  - [ ] Task 7.3: Decompose Dense System Prompts (`tailor_resume.md`) into Sequential LLM Passes

- [ ] **Phase 8: Test Suite, SRE Resilience & Error Recovery (Issues 29–31)**
  - [ ] Task 8.1: Create Real End-to-End Integration Test Suite Executing Full Pipeline and Go TUI
  - [ ] Task 8.2: Replace Blocking 65-Second Thread Sleep in Gemma Fallback with Async Worker Queues
  - [ ] Task 8.3: Enforce Hard Circuit Breaker in `orchestrator.py` Stopping Repair Loops after 2 Passes

- [ ] **Phase 9: Onboarding & ADHD Cognitive Experience (Issues 32–35)**
  - [ ] Task 9.1: Build 1-Command Quickstart Mode (`resume quickstart`) Pre-Loaded with Demo Data
  - [ ] Task 9.2: Add Step-by-Step Progress Bars with Elapsed and Estimated Time Indicators
  - [ ] Task 9.3: Add Automated Go Toolchain Installation Guidance in `doctor.py`
  - [ ] Task 9.4: Centralize Single Source of Truth for Version Numbers in `pyproject.toml`

---

## 🛠️ Detailed Implementation Plans for All 35 Issues

### 🏛️ Phase 1: Architecture & Technical Debt (Issues 1–6)

#### Issue 1: Monolithic Script Antipatterns
* **Target Files**: [`scripts/orchestrator.py`](file:///Users/morganescott/resume-builder/scripts/orchestrator.py) (229KB), [`scripts/menu.py`](file:///Users/morganescott/resume-builder/scripts/menu.py) (95KB), [`scripts/rewrite_bullets.py`](file:///Users/morganescott/resume-builder/scripts/rewrite_bullets.py) (78KB), [`scripts/audit_keepers.py`](file:///Users/morganescott/resume-builder/scripts/audit_keepers.py) (59KB), [`scripts/validate_resume.py`](file:///Users/morganescott/resume-builder/scripts/validate_resume.py) (52.6KB).
* **Root Cause**: Business logic, API orchestration, prompt compilation, CLI menus, and formatting are tightly coupled in monolithic scripts.
* **Fix Specification**:
  1. Create package structure: `scripts/engine/` (`ingest.py`, `eval.py`, `tailor.py`, `render.py`), `scripts/ui/` (`menu/`, `components/`).
  2. Move LLM prompt generation from `orchestrator.py` to `scripts/engine/tailor.py`.
  3. Extract checkpoint state saving from `orchestrator.py` to `scripts/engine/checkpoint.py`.
* **Verification**: Run `python -m unittest discover -s tests` to ensure imports resolve and tests pass cleanly.

#### Issue 2: Polyglot Stack Sprawl
* **Target Files**: [`pyproject.toml`](file:///Users/morganescott/resume-builder/pyproject.toml), [`package.json`](file:///Users/morganescott/resume-builder/package.json), [`scripts/install.sh`](file:///Users/morganescott/resume-builder/scripts/install.sh).
* **Root Cause**: Four distinct runtimes (Python, Node.js, Go, Shell) require manual multi-step environment provisioning.
* **Fix Specification**:
  1. Create a root `.devcontainer/devcontainer.json` and `Dockerfile` declaring Python 3.11, Node 20, Go 1.22, and Typst.
  2. Update `install.sh` to perform automated dependency verification and install missing binary dependencies idempotently.
* **Verification**: Execute `./scripts/install.sh` inside a fresh container to verify complete provisioning.

#### Issue 3: Circular Import Hacks
* **Target Files**: [`scripts/gemini_client.py`](file:///Users/morganescott/resume-builder/scripts/gemini_client.py), [`scripts/orchestrator.py`](file:///Users/morganescott/resume-builder/scripts/orchestrator.py).
* **Root Cause**: Direct inter-module references between orchestrator and bullet rewriter required extracting `gemini_client.py` as a top-level workaround.
* **Fix Specification**:
  1. Implement client instantiation using dependency injection: pass an initialized `GeminiClient` instance to functions in `rewrite_bullets.py` and `orchestrator.py`.
* **Verification**: Run `python -c "import scripts.orchestrator; import scripts.rewrite_bullets"` with no circular import errors.

#### Issue 4: Hardcoded Python Binary Paths in `doctor.py`
* **Target Files**: [`scripts/doctor.py`](file:///Users/morganescott/resume-builder/scripts/doctor.py#L70).
* **Root Cause**: Fix suggestions hardcode `/usr/local/bin/python3.13`.
* **Fix Specification**:
  1. Replace hardcoded strings in `doctor.py` with `sys.executable`:
     ```python
     # Replace:
     # "/usr/local/bin/python3.13 -m venv .venv"
     # With:
     f"{sys.executable} -m venv .venv"
     ```
* **Verification**: Run `python scripts/doctor.py` on macOS and Linux; assert path reflects active python interpreter.

#### Issue 5: Non-Portable Subprocess `which` Calls
* **Target Files**: [`scripts/render_typst.py`](file:///Users/morganescott/resume-builder/scripts/render_typst.py#L127).
* **Root Cause**: Executing `subprocess.run(["which", "typst"])` fails on Windows where `which` is not a native command.
* **Fix Specification**:
  1. Replace `subprocess.run(["which", ...])` with standard library `shutil.which("typst")`:
     ```python
     if shutil.which("typst") is not None:
         # execute typst compile
     ```
* **Verification**: Run `python scripts/render_typst.py` on Windows PowerShell; confirm clean binary detection.

#### Issue 6: Repository Root Clutter
* **Target Files**: Root directory folders (`ImprovementConcepts/`, `IDEAS_ARCHIVE.md`, `scratch/`).
* **Root Cause**: Working notes and historical logs accumulate in the root workspace.
* **Fix Specification**:
  1. Create `/docs/archive/`.
  2. Move `IDEAS_ARCHIVE.md`, `ImprovementConcepts/`, and `scratch/` into `/docs/archive/`.
* **Verification**: Verify `ls -la` in repository root is clean and contains only core source directories and manifests.

---

### 💾 Phase 2: State Persistence, Storage & Syncthing (Issues 7–11)

#### Issue 7: 5-Way State Storage Fragmentation
* **Target Files**: [`scripts/db.py`](file:///Users/morganescott/resume-builder/scripts/db.py), [`scripts/picker.py`](file:///Users/morganescott/resume-builder/scripts/picker.py), [`scripts/jd_manager.py`](file:///Users/morganescott/resume-builder/scripts/jd_manager.py).
* **Root Cause**: Job state is stored concurrently in `data.db`, JSON files, CSV logs, markdown tables, and temporary snapshots.
* **Fix Specification**:
  1. Establish `profiles/<profile>/data.db` as the canonical primary datastore.
  2. Update `picker.py` and `jd_manager.py` to query `data.db` directly.
  3. Generate flat CSV and JSON files strictly as read-only exports for backwards compatibility.
* **Verification**: Update job status in CLI; verify change reflects instantly across SQLite and exported views.

#### Issue 8: Go Dashboard Vendoring Drift
* **Target Files**: [`dashboard/internal/data/career.go`](file:///Users/morganescott/resume-builder/dashboard/internal/data/career.go#L52).
* **Root Cause**: Vendored Go dashboard reads legacy `applications.md` tables instead of querying `data.db`.
* **Fix Specification**:
  1. Add `mattn/go-sqlite3` or `modernc.org/sqlite` import to `dashboard/go.mod`.
  2. Update `career.go` to query `jobs` and `application_log` tables in `data.db` directly.
* **Verification**: Launch `resume dashboard` without an `applications.md` file present; confirm TUI populates correctly from `data.db`.

#### Issue 9: SQLite `CHECK` Constraint Incompatibility
* **Target Files**: [`scripts/db.py`](file:///Users/morganescott/resume-builder/scripts/db.py#L44).
* **Root Cause**: Table schema restricts status to `('pending', 'evaluating', 'completed', 'applied', 'expired', 'archived')`, throwing exceptions on pipeline statuses like `'interview'` or `'offer'`.
* **Fix Specification**:
  1. Update schema migration in `db.py`:
     ```sql
     CHECK(status IN ('pending', 'evaluating', 'completed', 'applied', 'interview', 'offer', 'responded', 'rejected', 'discarded', 'expired', 'archived', 'skip'))
     ```
* **Verification**: Execute `db.update_job_status("job_123", "interview")`; assert update succeeds without `IntegrityError`.

#### Issue 10: Syncthing SQLite WAL Lock Contention
* **Target Files**: [`scripts/db.py`](file:///Users/morganescott/resume-builder/scripts/db.py#L26), `.stignore`.
* **Root Cause**: Active WAL journal files (`data.db-wal`, `data.db-shm`) synced via Syncthing cause multi-device database corruption.
* **Fix Specification**:
  1. Increase SQLite busy timeout in `db.py` to `15000` ms.
  2. Add `.stignore` rules to profile directories:
     ```
     (?d)*.db-wal
     (?d)*.db-shm
     (?d).sync-conflict-*
     ```
* **Verification**: Verify Syncthing sync ignores WAL sidecar files while syncing main `data.db`.

#### Issue 11: Non-Atomic CSV Tracker Writes
* **Target Files**: [`scripts/jd_manager.py`](file:///Users/morganescott/resume-builder/scripts/jd_manager.py#L140), [`scripts/atomic_write.py`](file:///Users/morganescott/resume-builder/scripts/atomic_write.py).
* **Root Cause**: Unlocked direct appends to `jd_tracker_log.csv` risk line interleaving during concurrent background scans.
* **Fix Specification**:
  1. Wrap all file appends in `jd_manager.py` with `fcntl.flock(f, fcntl.LOCK_EX)` (or Windows file lock equivalent).
* **Verification**: Trigger concurrent background scan and manual status update; assert CSV structure remains valid.

---

### 🔐 Phase 3: Security, Secrets Hygiene & Privacy (Issues 12–14)

#### Issue 12: Plaintext Credential Storage
* **Target Files**: [`scripts/gemini_client.py`](file:///Users/morganescott/resume-builder/scripts/gemini_client.py#L34), [`scripts/scan_linkedin.py`](file:///Users/morganescott/resume-builder/scripts/scan_linkedin.py).
* **Root Cause**: API keys and LinkedIn session cookies are saved as unencrypted plain text in `.env` and `.linkedin_cookie`.
* **Fix Specification**:
  1. Integrate the `keyring` Python library.
  2. Store `GEMINI_API_KEY` and LinkedIn cookies in OS Keyring (macOS Keychain, Windows Credential Manager, Linux Secret Service).
  3. Fall back to local `.env` only if keyring is unavailable.
* **Verification**: Run `resume bootstrap`; assert API key is stored securely in system keyring.

#### Issue 13: Unencrypted P2P Credential Sync Exposure
* **Target Files**: [`CLAUDE.md`](file:///Users/morganescott/resume-builder/CLAUDE.md#L62-L66), `.stignore`.
* **Root Cause**: Syncthing shares sync `.env` files across local network devices.
* **Fix Specification**:
  1. Add `.env` and `.linkedin_cookie` to default `.stignore` rules.
  2. Update documentation to advise entering API keys per device using keyring.
* **Verification**: Verify Syncthing status excludes `.env` files from cross-device synchronization.

#### Issue 14: Unredacted PII in Tracebacks and Log Files
* **Target Files**: [`scripts/cli_art.py`](file:///Users/morganescott/resume-builder/scripts/cli_art.py), [`scripts/orchestrator.py`](file:///Users/morganescott/resume-builder/scripts/orchestrator.py).
* **Root Cause**: Full candidate phone numbers, emails, and street addresses are printed in unhandled error tracebacks.
* **Fix Specification**:
  1. Add a PII scrubbing utility in `cli_art.py`:
     ```python
     def scrub_pii(text: str) -> str:
         text = re.sub(r'[\w\.-]+@[\w\.-]+\.\w+', '[REDACTED_EMAIL]', text)
         text = re.sub(r'\b\d{3}[-.\s]?\d{3}[-.\s]?\d{4}\b', '[REDACTED_PHONE]', text)
         return text
     ```
  2. Filter exception messages through `scrub_pii()` before logging to terminal or disk.
* **Verification**: Raise a simulated exception containing candidate contact info; verify logged output displays `[REDACTED_EMAIL]`.

---

### 🌐 Phase 4: Scrapers, Liveness & Third-Party Reliability (Issues 15–17)

#### Issue 15: Node.js Provider Script Subprocess Crashes
* **Target Files**: [`board-scanners/run_provider.mjs`](file:///Users/morganescott/resume-builder/board-scanners/run_provider.mjs), [`scripts/scan_boards.py`](file:///Users/morganescott/resume-builder/scripts/scan_boards.py).
* **Root Cause**: Unhandled promise rejections in Node.js provider plugins exit with code `1`, causing Python batch scans to fail.
* **Fix Specification**:
  1. Wrap entry point execution in `run_provider.mjs` with top-level `try/catch`.
  2. Catch errors and output a valid JSON error payload to stdout:
     `{"status": "error", "message": err.message}` with exit code `0`.
* **Verification**: Pass an invalid URL to a board scanner; verify Python receives structured JSON error instead of crashing.

#### Issue 16: Brittle LinkedIn Scraper & Cookie Keychain Crashes
* **Target Files**: [`scripts/scan_linkedin.py`](file:///Users/morganescott/resume-builder/scripts/scan_linkedin.py).
* **Root Cause**: `browser_cookie3` crashes on modern OS versions due to keychain encryption changes.
* **Fix Specification**:
  1. Catch `browser_cookie3` exceptions gracefully.
  2. Prompt user with a fallback terminal input to paste raw `li_at` cookie string if automatic browser cookie extraction fails.
* **Verification**: Simulate `browser_cookie3.BrowserCookieError`; verify CLI presents fallback manual prompt.

#### Issue 17: Anti-Bot False Positive Job Expirations
* **Target Files**: [`scripts/liveness.py`](file:///Users/morganescott/resume-builder/scripts/liveness.py), [`scripts/check-liveness.mjs`](file:///Users/morganescott/resume-builder/scripts/check-liveness.mjs).
* **Root Cause**: HTTP `403 Forbidden` and `429 Too Many Requests` responses are misclassified as dead listings and moved to `expired/`.
* **Fix Specification**:
  1. Update status classification in `liveness.py`:
     * HTTP 200: `Active`
     * HTTP 404, 410: `Expired`
     * HTTP 403, 429, 503, CAPTCHA: `Unknown / Rate-Limited` (Do NOT move to `expired/`).
* **Verification**: Mock HTTP 429 response on a job link; verify job status remains active in pending queue.

---

### 📄 Phase 5: Resume Tailoring, Google XYZ & Recruiter Impact (Issues 18–22)

#### Issue 18: Forced Google XYZ Formula Rigidity
* **Target Files**: [`scripts/validate_resume.py`](file:///Users/morganescott/resume-builder/scripts/validate_resume.py).
* **Root Cause**: Programmatically deducting points for bullets lacking numeric metrics forces artificial claims onto qualitative experience.
* **Fix Specification**:
  1. Update `validate_resume.py` to allow qualitative impact categories (e.g. strategic leadership, architecture design, process transformation) without requiring numeric percentages.
* **Verification**: Pass a qualitative bullet ("Architected core auth service using OAuth2 and OpenID Connect"); assert validation score passes.

#### Issue 19: LLM Semantic Drift in Bullet Rewrites
* **Target Files**: [`scripts/rewrite_bullets.py`](file:///Users/morganescott/resume-builder/scripts/rewrite_bullets.py).
* **Root Cause**: Rewriting prompts allow Gemini to introduce unverified technical frameworks or metrics during keyword injection.
* **Fix Specification**:
  1. Implement a post-rewrite fact-checking assertion: verify all technical nouns and numeric figures in the rewritten bullet exist in the candidate's verified knowledge base (`verified_tools.json` / `verified_metrics.json`).
* **Verification**: Attempt to rewrite a Python bullet into a Rust bullet; verify fact-checking assertion flags unverified framework.

#### Issue 20: Superficial Company Research Scraping Fluff
* **Target Files**: [`scripts/company_research.py`](file:///Users/morganescott/resume-builder/scripts/company_research.py).
* **Root Cause**: Raw corporate website scraping extracts marketing buzzwords ("synergistic paradigm shifts") that pollute cover letter tone.
* **Fix Specification**:
  1. Add a buzzword exclusion filter to `company_research.py` that strips low-value corporate slogans before passing context to LLM prompts.
* **Verification**: Process a company homepage containing generic marketing copy; verify extracted context isolates products, tools, and mission statements.

#### Issue 21: Single-Page PDF Spills & Orphan Headers
* **Target Files**: [`resume-engine/templates/resume_template.html`](file:///Users/morganescott/resume-builder/resume-engine/templates/resume_template.html), [`scripts/render_html.py`](file:///Users/morganescott/resume-builder/scripts/render_html.py).
* **Root Cause**: Multi-role candidate histories overflow single-page margins, creating orphan headers.
* **Fix Specification**:
  1. Add CSS rules to `resume_template.html`:
     ```css
     .job-entry { page-break-inside: avoid; }
     h2, h3 { page-break-after: avoid; }
     ```
  2. Implement dynamic font size and padding scaling (e.g. reducing font size from 9.5pt to 9.0pt when total character count exceeds threshold).
* **Verification**: Compile a long candidate profile; verify PDF fits cleanly on target page budget without orphan headings.

#### Issue 22: Incomplete Typst Special Character Escaping
* **Target Files**: [`scripts/render_typst.py`](file:///Users/morganescott/resume-builder/scripts/render_typst.py#L29).
* **Root Cause**: Character escaping omits brackets `[` `]` and underscores `_`, causing Typst compilation syntax errors.
* **Fix Specification**:
  1. Update `_escape_typst()`:
     ```python
     def _escape_typst(text: str) -> str:
         if not text: return ""
         for char in ["#", "$", "@", "_", "[", "]", "*"]:
             text = text.replace(char, f"\\{char}")
         return text
     ```
* **Verification**: Pass resume text containing `[Senior_Engineer]` to `render_typst.py`; verify PDF compiles cleanly.

---

### 🎨 Phase 6: UI/UX, TUI Ergonomics & Design Systems (Issues 23–25)

#### Issue 23: Multi-Paradigm UI Fragmentation
* **Target Files**: [`dashboard/internal/theme/resumebuilder.go`](file:///Users/morganescott/resume-builder/dashboard/internal/theme/resumebuilder.go), [`scripts/theme.py`](file:///Users/morganescott/resume-builder/scripts/theme.py), [`scripts/cli_art.py`](file:///Users/morganescott/resume-builder/scripts/cli_art.py).
* **Root Cause**: Independent color definitions across Python, Go, and HTML templates create inconsistent visual aesthetics.
* **Fix Specification**:
  1. Maintain master design tokens in `DESIGN.md` / `theme.py`.
  2. Ensure `scripts/sync_dashboard_theme.py` generates Go theme tokens automatically during build steps.
* **Verification**: Run `python scripts/sync_dashboard_theme.py`; assert Go theme source matches Python theme tokens exactly.

#### Issue 24: Fixed 80-Column ASCII Art Layout Wrapping
* **Target Files**: [`scripts/cli_art.py`](file:///Users/morganescott/resume-builder/scripts/cli_art.py).
* **Root Cause**: Banners hardcode fixed 80+ column line lengths, wrapping on narrow mobile or split-pane terminals.
* **Fix Specification**:
  1. Replace static string banners with dynamic `rich.panel.Panel` and `rich.text.Text` components that query `shutil.get_terminal_size().columns` and auto-fit header content.
* **Verification**: Resize terminal window to 60 columns and run `resume`; verify banners adjust dynamically without wrapping.

#### Issue 25: Missing Icon Glyph Boxes ("Tofu")
* **Target Files**: [`scripts/theme.py`](file:///Users/morganescott/resume-builder/scripts/theme.py), [`scripts/ui_config.py`](file:///Users/morganescott/resume-builder/scripts/ui_config.py).
* **Root Cause**: Icons rely on Nerd Font glyphs that render as missing glyph boxes on default system fonts.
* **Fix Specification**:
  1. Implement automated font capability detection in `ui_config.py`.
  2. Default to standard Unicode/ASCII fallback icons unless `RESUME_BUILDER_ICONS=nerdfont` is explicitly set.
* **Verification**: Unset `RESUME_BUILDER_ICONS` and run CLI in standard terminal; verify clean Unicode icons render without missing glyph boxes.

---

### 🧮 Phase 7: Algorithms, Vector RAG & Prompt Design (Issues 26–28)

#### Issue 26: Pseudo-Scientific "Bayesian" Marketing Claims
* **Target Files**: [`README.md`](file:///Users/morganescott/resume-builder/README.md), [`docs/faq.md`](file:///Users/morganescott/resume-builder/docs/faq.md), [`docs/operations.md`](file:///Users/morganescott/resume-builder/docs/operations.md).
* **Root Cause**: Documentation labels piecewise linear interpolation as a "Bayesian Probability Converter".
* **Fix Specification**:
  1. Update documentation and CLI text to accurately describe scoring as a "Piecewise Linear Probability Scale".
* **Verification**: Search codebase for `Bayesian`; verify marketing terms are replaced with accurate technical terminology.

#### Issue 27: Silent Vector RAG Cache Invalidation
* **Target Files**: [`scripts/vector_store.py`](file:///Users/morganescott/resume-builder/scripts/vector_store.py#L62-L64).
* **Root Cause**: Editing `bullet-bank-keepers-audited.csv` changes the SHA hash, causing `vector_store.py` to return an empty list `[]` without notifying the user.
* **Fix Specification**:
  1. Add auto-reembedding logic: when SHA hash mismatch is detected, display a notice and trigger `embed_bullet_bank.py` in the background before returning search results.
* **Verification**: Modify a bullet point in CSV and execute vector search; verify background re-embedding triggers automatically.

#### Issue 28: Dense Multi-Constraint System Prompt Saturation
* **Target Files**: [`resume-engine/prompts/tailor_resume.md`](file:///Users/morganescott/resume-builder/resume-engine/prompts/tailor_resume.md).
* **Root Cause**: Combining 15+ constraints in a single prompt causes instruction drop-off in LLM outputs.
* **Fix Specification**:
  1. Decompose tailoring into two sequential passes:
     * **Pass 1 (Content Selection):** Pick matching bullets from bank and align technical skills.
     * **Pass 2 (Stylistic Polish):** Apply vocabulary substitutions, character budgets, and formatting constraints.
* **Verification**: Compare output resumes from single-pass vs. two-pass pipelines; verify two-pass pipeline adheres to 100% of formatting constraints.

---

### 🧪 Phase 8: Test Suite, SRE Resilience & Error Recovery (Issues 29–31)

#### Issue 29: Over-Mocking in Unit Tests
* **Target Files**: [`tests/`](file:///Users/morganescott/resume-builder/tests) (106 test modules).
* **Root Cause**: Tests rely exclusively on `unittest.mock.patch`, leaving real integration paths unverified.
* **Fix Specification**:
  1. Create an integration test suite under `tests/integration/`:
     * `test_pdf_rendering_e2e.py`: Compiles a real HTML/Typst resume to PDF using Playwright and asserts text extraction.
     * `test_dashboard_binary_e2e.py`: Launches compiled Go binary against sample data and asserts return code `0`.
* **Verification**: Run `python -m unittest discover -s tests/integration`; verify real integration tests pass.

#### Issue 30: Gemma Fallback 65-Second Thread Sleeps
* **Target Files**: [`scripts/gemini_client.py`](file:///Users/morganescott/resume-builder/scripts/gemini_client.py#L196).
* **Root Cause**: Falling back to `gemma-4-31b-it` enforces blocking `time.sleep(65)` calls that freeze the main CLI thread.
* **Fix Specification**:
  1. Replace blocking sleeps with an asynchronous job queue worker or present an interactive countdown timer with option to switch API keys or cancel.
* **Verification**: Simulate Gemma rate limit; verify CLI displays interactive countdown timer instead of freezing.

#### Issue 31: Infinite Validation Repair Loops
* **Target Files**: [`scripts/orchestrator.py`](file:///Users/morganescott/resume-builder/scripts/orchestrator.py).
* **Root Cause**: Failing validation triggers a 4-pass repair loop that can burn API quota without converging.
* **Fix Specification**:
  1. Enforce a strict circuit breaker: limit validation repair attempts to **2 passes**.
  2. If validation fails after 2 passes, present user with manual edit options or accept best-effort output.
* **Verification**: Mock recurring validation failure; verify orchestrator halts after pass 2 and prompts user.

---

### ⚡ Phase 9: Onboarding & ADHD Cognitive Experience (Issues 32–35)

#### Issue 32: High Initial Onboarding Setup Barrier
* **Target Files**: [`scripts/bootstrap_profile.py`](file:///Users/morganescott/resume-builder/scripts/bootstrap_profile.py), [`scripts/cli.py`](file:///Users/morganescott/resume-builder/scripts/cli.py).
* **Root Cause**: Requiring an 8-stage wizard before generating any resume causes high user drop-off.
* **Fix Specification**:
  1. Implement a `resume quickstart` command pre-loaded with sample candidate data (`fixtures/sample_profile/`).
  2. Allow users to generate a sample tailored PDF immediately to experience the product before configuring their own profile.
* **Verification**: Run `resume quickstart` in a clean environment; verify sample PDF renders in under 10 seconds.

#### Issue 33: Opaque Execution Spinners During LLM Pipeline Runs
* **Target Files**: [`scripts/cli_art.py`](file:///Users/morganescott/resume-builder/scripts/cli_art.py), [`scripts/orchestrator.py`](file:///Users/morganescott/resume-builder/scripts/orchestrator.py).
* **Root Cause**: Generic spinners give no indication of pipeline progress or remaining time during 60+ second builds.
* **Fix Specification**:
  1. Replace static spinners with multi-step `rich.progress.Progress` bars displaying current step (e.g. `[3/6] Rewriting Bullets...`), elapsed time, and estimated time remaining.
* **Verification**: Run `resume run`; verify terminal displays clear step-by-step progress bar.

#### Issue 34: `doctor.py` Missing Go Toolchain Installation Guidance
* **Target Files**: [`scripts/doctor.py`](file:///Users/morganescott/resume-builder/scripts/doctor.py#L140).
* **Root Cause**: `doctor.py` checks for `go` binary but does not provide direct OS installation commands when missing.
* **Fix Specification**:
  1. Update `check_go()` in `doctor.py` to provide exact OS installation commands (`brew install go` for macOS, `sudo apt install golang` for Ubuntu/Debian, `winget install GoLang.Go` for Windows).
* **Verification**: Run `doctor.py` without Go installed; verify actionable installation commands are displayed.

#### Issue 35: Inconsistent Version Flags Across Commands and Manifests
* **Target Files**: [`pyproject.toml`](file:///Users/morganescott/resume-builder/pyproject.toml), [`scripts/cli_art.py`](file:///Users/morganescott/resume-builder/scripts/cli_art.py), [`dashboard/main.go`](file:///Users/morganescott/resume-builder/dashboard/main.go).
* **Root Cause**: Version strings are hardcoded independently across files.
* **Fix Specification**:
  1. Centralize single source of truth for version number in `pyproject.toml`.
  2. Parse version dynamically in Python via `importlib.metadata.version("resume-builder")` and pass to Go build flags (`-ldflags "-X main.Version=..."`).
* **Verification**: Run `resume --version` and `dashboard --version`; verify matching version output.
