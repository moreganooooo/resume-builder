# ⚠️ DEVIL'S ADVOCATE CRITICAL AUDIT: `resume-builder` (Master Edition)

An exhaustive, unsparing, stone-unturned evaluation of `resume-builder` across architecture, security, state management, TUI/UX, scoring algorithms, liveness checks, job board scrapers, data integrity, PDF rendering, installers, script workflows, testing, and documentation compared to professional career software (Teal, Jobscan, Rezi, Huntr, Reactive Resume).

---

## Executive Summary

`resume-builder` is an ambitious, feature-packed career automation pipeline. However, beneath its polished terminal aesthetic and marketing vocabulary ("ultra-premium", "punishingly ATS-clean", "Bayesian converter", "compounding brain"), the codebase relies on **fragile polyglot wrappers, naive file-based database hacks, pseudo-mathematical heuristics, unmitigated scraping risks, and context-stuffed LLM prompts**.

While impressive as a custom personal script, it exhibits significant technical friction, architectural fragility, security vulnerabilities, and UX barriers when evaluated against standard professional engineering practices and commercial job-search products.

---

## 1. Big-Picture Architecture & Tech Stack Fragility

### 1.1 Excessively Complex Polyglot Runtime Stack
* **The Mess:** The system requires **Python 3.10+** (core orchestrator), **Go 1.20+** (Bubble Tea TUI precompiled binaries), **Node.js + Playwright** (Chromium PDF rendering & liveness), **Shell scripts** (`resume-cli.sh`), **HTML/Jinja2 CSS templates**, and **Syncthing** (P2P folder sync).
* **The Flaw:** To execute a simple command, Python spawns a Go binary, which shells out to a Node.js process, which launches a headless Chromium browser. This creates severe inter-process communication (IPC) overhead, brittle environment requirements, and multi-runtime error handling nightmares.
* **Professional Contrast:** Production tools use a single unified backend (e.g., Node/Go/Python API) serving a responsive web UI, or leverage lightweight PDF generators (like Typst, WeasyPrint, or headless browser pools) rather than shelling out across three runtime environments on a local desktop machine.

### 1.2 Operating System & Dependency Lock-in
* **The Mess:** Playwright is strictly pinned to `1.61.1` in [`CLAUDE.md`](file:///Users/morganescott/resume-builder/CLAUDE.md#L25-L30) because the development machine runs **macOS 12 Monterey** (released in 2021). Newer Playwright versions (1.62+) dropped macOS 12 support.
* **The Flaw:** The entire codebase is locked to legacy dependency versions due to host OS constraints. Upgrading any Node package risks breaking the Playwright browser runner.
* **Professional Contrast:** Enterprise software containerizes environments (Docker) or uses OS-agnostic APIs to prevent host machine OS versions from freezing project dependencies.

### 1.3 Primitive File-System "Database" Architecture
* **The Mess:** There is no database (SQLite, PostgreSQL, or IndexedDB). Application state is tracked by **physically moving `.json` files across directories** on disk (`jds/pending/`, `jds/completed/`, `jds/expired/`).
* **The Flaw:** Metadata is stored directly inside job JSON files under underscore-prefixed keys (`_evaluation`, `_liveness`, `_application`). Directory file moves are non-atomic across file systems and prone to partial writes.
* **Syncthing Collision Hazard:** Background P2P folder sync via Syncthing while the orchestrator moves files creates `.sync-conflict-*` files, duplicate state entries, and directory race conditions.

---

## 2. Security, Credentials & Privacy Vulnerabilities

### 2.1 PII Stored in Executable Python Source Files
* **The Mess:** Candidate contact details (full name, phone number, personal email address, physical location) are written directly into executable Python source files ([`profiles/<name>/fixed_content.py`](file:///Users/morganescott/resume-builder/profiles/morgan/fixed_content.py)).
* **The Vulnerability:** Executable code files containing raw PII invite accidental git commits, code leaks, and static analysis exposure.

### 2.2 Unencrypted Plaintext Secrets & P2P Sync Exposure
* **The Mess:** Secret API keys (`GEMINI_API_KEY`, `BRAVE_API_KEY`, `JOBRIGHT_COOKIE_STRING`) live in plaintext `.env` files in profile directories.
* **The Flaw:** Syncthing synchronizes these profile folders across mobile phones and desktop devices. While Syncthing encrypts data in transit via TLS, any unencrypted local storage device holds unencrypted API keys, session cookies, and candidate PII.

### 2.3 Stale Auth Header Cache on Profile Switching
* **The Bug:** [`gemini_client.py`](file:///Users/morganescott/resume-builder/scripts/gemini_client.py#L40) computes `AUTH_HEADERS = {"x-goog-api-key": API_KEY}` once at module import time.
* **The Vulnerability:** When switching profiles mid-session via `profile_paths.set_active_profile()`, `gemini_client.py` is **omitted from `_RELOAD_ON_PROFILE_SWITCH`**. Subsequent LLM API requests silently continue using the previous profile's API key.

---

## 3. TUI / UX (Interface, Dashboard, Layout, & Accessibility)

### 3.1 Fragmented UI Prompts & Visual Inconsistency
* **The Mess:** The interface jumps between Go Bubble Tea TUI screens ([`dashboard/`](file:///Users/morganescott/resume-builder/dashboard)), Python `Rich` terminal tables ([`cli_art.py`](file:///Users/morganescott/resume-builder/scripts/cli_art.py)), Questionary selection prompts, and pre-compiled Go `huh` prompts ([`charm_prompt.py`](file:///Users/morganescott/resume-builder/scripts/charm_prompt.py)).
* **The Flaw:** Input behavior, hotkeys, and color rendering shift depending on which subsystem handles the current step.

### 3.2 Glyph Corruption ("Tofu Boxes") & Terminal Window Instability
* **The Mess:** Icon rendering defaults to Nerd Font glyphs. Terminals without Nerd Fonts display corrupted rectangle symbols ("tofu").
* **The Flaw:** The fallback mechanism (`RESUME_BUILDER_ICONS=unicode`) requires manually setting shell environment variables. On narrow terminal windows (<80 columns) or mobile Termux screens, Rich tables wrap awkwardly and Bubble Tea views clip or throw layout errors.

### 3.3 Zero Accessibility & Rigid Modal Workflows
* **The Mess:** The terminal interface offers no support for screen readers, keyboard-only tab navigation parity, or high-contrast theme overrides.
* **The Flaw:** The user cannot inspect their resume side-by-side with a job description. Every iteration requires executing a terminal command, waiting for LLM generation, opening an external PDF reader, and returning to the terminal to adjust inputs.

---

## 4. Onboarding & Knowledge Base ("Compounding Brain")

### 4.1 Extreme Setup Friction
* **The Mess:** Onboarding requires manually dropping raw documents into `data/`, running `bootstrap_menu.py`, interactive CLI prompts, and hand-editing `profile.yml`, `bullet-bank-keepers-audited.csv`, and `verified_tools.json`.
* **Professional Contrast:** Modern platforms (Teal, Rezi, Huntr) offer 1-click LinkedIn profile imports, structured onboarding wizards, and visual drag-and-drop resume parsers.

### 4.2 Context-Window Stuffing Masquerading as a "Dynamic Knowledge Base"
* **The Mess:** The README claims a "Dynamic Knowledge System (Compounding Brain)". In reality, there is **no vector database, no embeddings index, and no RAG pipeline** (Chroma, FAISS, Qdrant) for knowledge base retrieval.
* **The Flaw:** [`orchestrator.py`](file:///Users/morganescott/resume-builder/scripts/orchestrator.py) simply concatenates raw allowlisted text files from `data/` directly into the Gemini system prompt context window (`KB_ALLOWLIST`).
* **The Consequence:** Context window stuffing explodes token costs, increases LLM generation latency, and leads to prompt attention degradation ("lost in the middle").

---

## 5. Scoring, Evaluation & "Bayesian" Marketing Hyperbole

### 5.1 Pseudo-Mathematical "Bayesian Converter"
* **The Mess:** The README advertises a *"Bayesian Probability Converter"* translating 1–5 scores into *"empirical Absolute Interview Probability Percentages"*.
* **The Code Reality:** In [`orchestrator.py` lines 2701–2719](file:///Users/morganescott/resume-builder/scripts/orchestrator.py#L2701-L2719):
```python
x = interview_odds_score
points = [(1.0, 0.1), (2.0, 1.0), (3.0, 2.5), (4.0, 8.0), (5.0, 20.0)]
# Piecewise linear interpolation on arbitrary log-odds baseline (2%)
```
* **The Verdict:** This is standard piecewise linear interpolation between five arbitrarily hardcoded numbers mapped to a static 2% baseline multiplier. There are no priors, no likelihood distributions, no posterior updates, and no empirical data calibration. Presenting this as "Bayesian" statistics is pure marketing exaggeration.

### 5.2 Split-Agent Over-Engineering & Synchronous Bottlenecks
* **The Mess:** Evaluating fit requires two separate LLM calls (`evaluate_capability.md` and `evaluate_recruiter.md`) for every single job description, executed synchronously via `requests.post` with hardcoded `time.sleep(4.5)` delays ([`batch_evaluate.py`](file:///Users/morganescott/resume-builder/scripts/batch_evaluate.py#L19)).
* **The Flaw:** Batch-evaluating 50 pending JDs takes over 4 minutes of blocking I/O while doubling API costs.

---

## 6. Liveness Checks & Job Board Scanning

### 6.1 Naive Liveness Regexes Fail on Modern SPAs
* **The Mess:** Liveness checking in [`liveness-core.mjs`](file:///Users/morganescott/resume-builder/scripts/liveness-core.mjs) searches inner page text for simple string patterns (`/job no longer available/i`, `/position has been filled/i`).
* **The Flaw:** Modern ATS platforms (Workday, Taleo, iCIMS, Greenhouse) use Single Page Applications (SPAs). Closed roles frequently return `HTTP 200 OK` while displaying dynamic modal overlays, or redirect to generic career search portals without matching static regexes. Furthermore, Cloudflare and Akamai bot protections block headless Playwright instances, returning false "uncertain" or false "active" statuses.

### 6.2 High-Risk Cookie Scraping & Fragile Session Tokens
* **The Mess:** [`scan_linkedin.py`](file:///Users/morganescott/resume-builder/scripts/scan_linkedin.py) uses `browser_cookie3` to extract the user's live `li_at` cookie directly from their local Chrome browser.
* **The Risks:**
  1. Modern macOS Keychain encryption blocks `browser_cookie3` from reading Chrome cookies without password prompts or native decryption permissions.
  2. Scraping LinkedIn using personal authenticated session cookies violates LinkedIn Terms of Service and carries an **immediate risk of permanent account termination**.
  3. JobRight scanning ([`scan_jobright.py`](file:///Users/morganescott/resume-builder/scripts/scan_jobright.py)) requires pasting temporary HTTP cookie strings into `.env`, which expire within hours.

---

## 7. Bullet Bank & Writing Voice Adoption

### 7.1 Unstructured CSV Data Storage & Partial-Write Hazards
* **The Mess:** Core achievement bullets are stored in a raw CSV file ([`bullet-bank-keepers-audited.csv`](file:///Users/morganescott/resume-builder/profiles/morgan/bullet-bank-keepers-audited.csv)).
* **The Flaw:** CSV files lack relational keys, schema validation, and type safety. Multi-line bullet text, unescaped commas, or quote character collisions cause parsing errors during automated updates.
* **Interruption Vulnerability:** In [`bootstrap_bullet_bank.py`](file:///Users/morganescott/resume-builder/scripts/bootstrap_bullet_bank.py), pipeline stages run as subprocess calls. An API timeout or network drop mid-run leaves intermediate CSV files partially written and out of sync with `checkpoint.json`.

### 7.2 Strict Uniqueness Enforcers Restrict Quality
* **The Mess:** [`mine_bullet_bank()`](file:///Users/morganescott/resume-builder/scripts/mine_bullet_bank.py) enforces two-pass selection rules to prevent duplicate opening verbs and repeated metric numbers across the CV.
* **The Flaw:** In smaller bullet banks, strict uniqueness rules starve the selection algorithm, forcing the builder to pick weak or irrelevant achievements simply because top-tier bullets share common action verbs (e.g., "Led", "Built", "Managed") or common metrics (e.g., "$1M", "30%").

---

## 8. Resume Building, PDF Rendering, & ATS Verification

### 8.1 Chromium PDF Rendering Overhead
* **The Mess:** PDF generation ([`generate-pdf.mjs`](file:///Users/morganescott/resume-builder/scripts/generate-pdf.mjs)) renders Jinja-generated HTML via headless Chromium in Playwright.
* **The Flaw:** Launching a full Chromium browser process for every single resume PDF build incurs high CPU/memory overhead compared to native vector PDF compilation engines (like Typst, LaTeX, or Rust-based printers).

### 8.2 ATS Text Normalization Risks
* **The Mess:** [`normalizeTextForATS()`](file:///Users/morganescott/resume-builder/scripts/generate-pdf.mjs#L54-L109) replaces non-ASCII characters (`→` to ` to `, `—` to `-`, and `•` / `·` to ` | `).
* **The Risk:** Replacing standard list bullet characters (`•`) with vertical pipe characters (` | `) can break ATS document structural parsers that rely on standard bullet characters to delineate list items in work experience sections.

---

## 9. Application Tracking & Pipeline Management

### 9.1 In-Place CSV Logging Without File Locking
* **The Mess:** Pipeline history is logged to [`jd_tracker_log.csv`](file:///Users/morganescott/resume-builder/jds/morgan/jd_tracker_log.csv).
* **The Flaw:** Appending to a flat CSV file without thread or process file locking invites data corruption during concurrent script executions or interrupted pipeline runs.

### 9.2 Lack of Visual Pipeline Boards & Integrations
* **Professional Contrast:** Platforms like Huntr, Teal, and Jobscan feature interactive Kanban boards (Wishlist → Applied → Interviewing → Offer), automated email response parsing (Gmail/Outlook sync), calendar sync for interviews, and contacts/recruiter CRM mapping. `resume-builder` relies on text-based terminal lists and manual directory migrations.

---

## 10. Testing & Environment Doctor Script

### 10.1 Over-Reliance on Mocks & Lack of E2E ATS Integration Tests
* **The Mess:** The repository contains 105 test files in [`tests/`](file:///Users/morganescott/resume-builder/tests).
* **The Flaw:** Nearly all tests heavily mock external systems (`unittest.mock.patch` for Gemini API, Playwright, shell calls, and scrapers). There are zero end-to-end integration tests that pass generated PDFs through real ATS parsers (e.g., Workday, Lever, Greenhouse) to verify parse rates empirically.

### 10.2 Standalone Doctor Script Execution Failure
* **The Bug:** Running `.venv/bin/python scripts/doctor.py` directly from the terminal outputs **nothing** and silently exits with code 0.
* **The Cause:** [`doctor.py`](file:///Users/morganescott/resume-builder/scripts/doctor.py) contains no `if __name__ == "__main__":` entry point; display logic is tightly coupled to `cli_art.render_doctor_report()`.

---

## 11. Script-by-Script & Installer Audits

### 11.1 Installation Script Failures (`scripts/install.sh`)
* **Shell Variable Detection Failure:** Line 124 checks `[ -n "$ZSH_VERSION" ]`. When the user runs `bash install.sh`, `$ZSH_VERSION` is always empty, causing script detection to fall back blindly to checking `~/.zshrc`.
* **Global Alias Pollution:** The installer appends `source .../scripts/resume-cli.sh` directly onto the user's shell rc file (`.zshrc` / `.bashrc`), polluting the user's global shell namespace with aliases (`resume`, `resume-doctor`, `resume-test`, `resume-activate`) without providing an uninstaller or removal command.

### 11.2 Heavy Pandas Dependency & Data Type Corruption
* **Massive Overhead for Simple CSVs:** `pandas` is imported across multiple scripts (`audit_keepers.py`, `rewrite_bullets.py`, `cluster_bullet_bank.py`, `score_keeper_gems.py`, `orchestrator.py`) solely for reading and writing 2D CSV tables.
* **Silent Type Conversion Bugs:** `pandas.read_csv()` and `pandas.to_csv()` automatically convert integer IDs (e.g. `1001`) into floating-point numbers (`1001.0`), strip leading zeros, and mangle nullable string columns (`audit_status`, `manager_test`). This forced the addition of a hand-rolled `ensure_writable_dtypes()` workaround in `rewrite_bullets.py`.

### 11.3 Interactive Terminal Prompt Duplication & Unhandled Cancellations
* **Unhandled Cancellation States:** In [`skills_menu.py`](file:///Users/morganescott/resume-builder/scripts/skills_menu.py), pressing `Ctrl+C` or `Esc` during a `questionary` prompt returns `None`. `_add_skill()` skips validation on optional fields, appending incomplete skill objects (e.g. `evidence_count = 1` with empty names or broken references) to `verified_tools.json`.

### 11.4 Subshell Pre-compilation Overhead & Hidden Failures
* **On-the-Fly Precompilation Delays:** [`scripts/dashboard.py`](file:///Users/morganescott/resume-builder/scripts/dashboard.py) and [`scripts/charm_prompt.py`](file:///Users/morganescott/resume-builder/scripts/charm_prompt.py) attempt to compile Go binaries (`dashboard/bin/dashboard` and `dashboard/bin/prompt`) on-the-fly during execution. If the Go toolchain is missing, compilation silently fails and falls back to running `go run` or raw Questionary prompts, defeating the sub-millisecond launch speed claim.

### 11.5 Flawed Stale Sweep & Archive Rules
* **Naive File Age Archive Logic:** In [`scripts/stale_sweep.py`](file:///Users/morganescott/resume-builder/scripts/stale_sweep.py), job postings in `jds/morgan/` are checked against file creation time or posting dates. Unread JDs that haven't been evaluated are archived automatically if they pass a static threshold (e.g., >30 days old), even if the job posting remains active on the employer's official site.

---

## 12. Documentation & Marketing vs. Reality Gap

| Feature Claim in README | Technical Implementation Reality |
| :--- | :--- |
| **"Bayesian Probability Converter"** | Hardcoded 5-point piecewise linear interpolation on log-odds (`points = [(1.0, 0.1)...]`). No Bayesian priors or posterior calculations. |
| **"Compounding Brain / Dynamic Knowledge Base"** | Raw string concatenation dumping allowlisted text files directly into the LLM system prompt context window. No vector database or RAG. |
| **"Liveness Sweep"** | Basic Playwright page inner-text regex matching (`HARD_EXPIRED_PATTERNS`). Easily bypassed by SPAs and Cloudflare bot protection. |
| **"Punishingly ATS-Clean Vector PDF"** | Headless Chromium HTML-to-PDF print rendering. Text normalization replaces bullet points (`•`) with pipes (` \| `), risking list parsing issues. |
| **"Decentralized Mobile Sync"** | Manual setup instructions pairing desktop and Termux on Android via Syncthing P2P folder sync. Subject to file move sync conflicts. |

---

## Structural Roadmap for Technical Modernization

1. **Unify the Tech Stack:** Replace the hybrid Python/Go/Node stack with a single cohesive language framework (e.g., Python FastAPI backend with a React/Next.js frontend, or a pure Rust CLI).
2. **Adopt a Real Embedded Database:** Migrate away from filesystem `.json` directory moves and flat CSV logs to **SQLite / DuckDB** with ACID transactions, proper indexing, and relational schemas.
3. **Implement True Vector RAG:** Replace full-file context dumping with an embedded vector store (e.g., `chromadb` or `sqlite-vec`) for semantic chunk retrieval from historical documents and bullet banks.
4. **Replace Cookie Scraping with Safe APIs:** Remove `browser_cookie3` Chrome cookie extraction and unauthenticated LinkedIn scraping to prevent user account bans. Use official job board APIs, RSS feeds, or SerpAPI/JSearch integrations.
5. **Secure Candidate Credentials & PII:** Move contact information out of executable `.py` files and into encrypted environment stores or keychains.
6. **Decouple Presentation from Core Logic:** Ensure utility scripts like `doctor.py` can be executed independently from CLI UI modules.
7. **Eliminate Pandas Dependency for CSVs:** Replace Pandas imports across lightweight scripts with Python's built-in `csv` module or standard `dataclasses` to eliminate ~100MB+ memory overhead and integer-to-float column corruption bugs.
