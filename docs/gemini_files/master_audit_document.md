# 💎 MASTER AUDIT DOCUMENT: `resume-builder`
### Comprehensive Architectural, Security, UX, Recruiter & Algorithmic Quality Report

---

## 📌 Executive Summary

This document synthesizes every flaw, vulnerability, architectural inconsistency, and usability barrier identified across all evaluation passes of `resume-builder`. The audit evaluates the codebase from four distinct professional perspectives:

1. **Senior Enterprise Software Architect**: Infrastructure, polyglot sprawl, database state management, and maintenance debt.
2. **High-End UI/UX & Systems Designer**: Terminal ergonomics, visual identity cohesion, responsive layout, and typography.
3. **HR Hiring Manager & Recruiter**: Bullet writing authenticity, Google XYZ formula rigidity, ATS parsing, and company research quality.
4. **ADHD Job-Seeker**: Onboarding friction, execution feedback loops, and pipeline cognitive load.

---

## 🏛️ Section 1: Architecture, Codebase Design & Technical Debt

### 1.1 Monolithic Script Antipatterns
* **File Size Bloat**: Core system responsibilities are concentrated in a small number of oversized files:
  * [`scripts/orchestrator.py`](file:///Users/morganescott/resume-builder/scripts/orchestrator.py): **229 KB** (~3,500+ lines). Handles CLI parsing, API client configuration, prompt generation, state checkpointing, error logging, and retry loops within a single module.
  * [`scripts/menu.py`](file:///Users/morganescott/resume-builder/scripts/menu.py): **95 KB**.
  * [`scripts/rewrite_bullets.py`](file:///Users/morganescott/resume-builder/scripts/rewrite_bullets.py): **78 KB**.
  * [`scripts/audit_keepers.py`](file:///Users/morganescott/resume-builder/scripts/audit_keepers.py): **59 KB**.
  * [`scripts/validate_resume.py`](file:///Users/morganescott/resume-builder/scripts/validate_resume.py): **52.6 KB**.
* **Impact**: Monolithic files increase cognitive load, complicate refactoring, and make merge conflicts frequent.

### 1.2 Polyglot Stack Sprawl
* **4-Runtime Environment Requirement**:
  Running `resume-builder` requires **Python 3.10+**, **Node.js + Playwright**, **Go toolchain** (for Bubble Tea TUI binaries), **Shell scripts** (`install.sh`, `resume-cli.sh`), **Typst**, and **HTML/CSS**.
* **Impact**: Environment setup is fragile across different operating systems. CI/CD pipelines require managing four separate toolchains.

### 1.3 Circular Import Workarounds
* **Module Splitting Hacks**: [`scripts/gemini_client.py`](file:///Users/morganescott/resume-builder/scripts/gemini_client.py#L4) explicitly notes it was extracted to break a circular import between `orchestrator.py` and `rewrite_bullets.py`.
* **Impact**: Tight coupling between business logic and API client instantiation remains.

### 1.4 Hardcoded OS & Path Assumptions
* **POSIX Assumptions**: [`scripts/install.sh`](file:///Users/morganescott/resume-builder/scripts/install.sh) and [`scripts/resume-cli.sh`](file:///Users/morganescott/resume-builder/scripts/resume-cli.sh) assume `zsh`/`bash` environments and POSIX symlinks. Windows PowerShell and CMD environments are unsupported without WSL.
* **Hardcoded Python Binary Fallbacks**: [`scripts/doctor.py`](file:///Users/morganescott/resume-builder/scripts/doctor.py#L70) includes hardcoded paths like `/usr/local/bin/python3.13`, failing on machines where Python lives under `/usr/bin/python3` or Homebrew paths.
* **Non-Portable Subprocess `which` Calls**: [`scripts/render_typst.py`](file:///Users/morganescott/resume-builder/scripts/render_typst.py#L127) calls `subprocess.run(["which", "typst"])` instead of Python's cross-platform `shutil.which("typst")`, breaking binary detection on Windows.

### 1.5 Repository Root Clutter
* **Legacy Artifact Accumulation**:
  The repository root contains unorganized working files:
  * `ImprovementConcepts/` (Directory with design proposals)
  * `IDEAS_ARCHIVE.md` (**124 KB** historical markdown archive)
  * `IDEAS.md` (**41.5 KB** idea list)
  * `scratch/` (Temporary testing directory)
  * `resume-builder-conversations-perplexity/` (Raw LLM chat logs)

---

## 💾 Section 2: Data Persistence, Storage Fragmentation & Sync Risks

### 2.1 The 5-Way Data Storage Fragmentation
Job applications and evaluation states do not exist in one database; they are simultaneously written across **five incompatible data formats**:

```
                       5-WAY DATA STORAGE FRAGMENTATION
┌─────────────────────────────────────────────────────────────────────────────┐
│ 1. `data.db`                     ──▶ Embedded SQLite database               │
│ 2. `jds/<profile>/*.json`        ──▶ Individual JD files with `_` keys      │
│ 3. `jd_tracker_log.csv`          ──▶ CSV tracking log file                  │
│ 4. `data/applications.md`        ──▶ Markdown table parsed by Go TUI        │
│ 5. `dashboard_jobs_*.json`       ──▶ Ephemeral JSON snapshot generated      │
└─────────────────────────────────────────────────────────────────────────────┘
```

### 2.2 The "Embedded ACID SQLite" Illusion
* **Unqueried Side-Car Database**: [`README.md`](file:///Users/morganescott/resume-builder/README.md#L67) advertises: *"Every profile maintains an ACID-compliant embedded database (`data.db`)"*.
* **Code Reality**:
  * [`orchestrator.py`](file:///Users/morganescott/resume-builder/scripts/orchestrator.py#L2383) loads bullet points exclusively from `bullet-bank-keepers-audited.csv`.
  * [`picker.py`](file:///Users/morganescott/resume-builder/scripts/picker.py) and [`rewrite_bullets.py`](file:///Users/morganescott/resume-builder/scripts/rewrite_bullets.py) operate directly on CSVs.
  * Job discovery and status updates move JSON files between `jds/<profile>/`, `completed/`, and `expired/`.
  * `data.db` is updated via [`scripts/db.py`](file:///Users/morganescott/resume-builder/scripts/db.py) as a side effect, but its tables are rarely queried by core pipeline modules.
* **SQLite CHECK Constraint Incompatibility**: [`scripts/db.py`](file:///Users/morganescott/resume-builder/scripts/db.py#L44) defines `CHECK(status IN ('pending', 'evaluating', 'completed', 'applied', 'expired', 'archived'))`. Passing pipeline statuses like `'interview'`, `'offer'`, `'rejected'`, or `'discarded'` directly causes SQLite `IntegrityError` exceptions.

### 2.3 Go Dashboard Vendoring Drift
* **Legacy Schema Expectations**: [`dashboard/internal/data/career.go`](file:///Users/morganescott/resume-builder/dashboard/internal/data/career.go#L52) was vendored from a sibling project (`career-ops`). It expects `applications.md`, `batch-input.tsv`, and `scan-history.tsv`.
* **Impact**: The Go dashboard does not read `data.db` or `jd_tracker_log.csv`. Python exports temporary JSON snapshots (`dashboard_jobs_*.json`) at runtime to bridge the schema gap.

### 2.4 Syncthing Multi-Device Sync Hazards
* **SQLite WAL Lock Corruption**: [`scripts/db.py`](file:///Users/morganescott/resume-builder/scripts/db.py#L26) executes `PRAGMA journal_mode=WAL;`. Syncing `data.db` via Syncthing while SQLite connections are open on desktop and mobile causes database lock contention, corrupted pages, and `.sync-conflict-*` database copies.
* **Allowlist Failures**: [`scripts/doctor.py`](file:///Users/morganescott/resume-builder/scripts/doctor.py#L303) flags `.sync-conflict-*` files because Syncthing collisions create invalid files inside profile directories.

### 2.5 Non-Atomic CSV Appends
* **Unsafe File Access**: [`scripts/jd_manager.py`](file:///Users/morganescott/resume-builder/scripts/jd_manager.py#L140) appends rows directly to `jd_tracker_log.csv` using standard file writes (`open(path, "a")`) without file locking (`fcntl.flock`).
* **Impact**: Concurrent writes during background scans risk interleaving lines and corrupting CSV formatting.

---

## 🔐 Section 3: Security, Secrets Hygiene & Privacy

### 3.1 Plain-Text Credential Storage
* **API Keys**: [`scripts/gemini_client.py`](file:///Users/morganescott/resume-builder/scripts/gemini_client.py#L34) loads API keys from plain-text `profiles/<profile>/.env` files.
* **LinkedIn Session Tokens**: [`scripts/scan_linkedin.py`](file:///Users/morganescott/resume-builder/scripts/scan_linkedin.py) saves captured `li_at` session tokens as unencrypted text inside `profiles/<profile>/.linkedin_cookie`.

### 3.2 P2P Network Credential Sync
* **Unencrypted Sync Hazards**: [`CLAUDE.md`](file:///Users/morganescott/resume-builder/CLAUDE.md#L62-L66) specifies that `.env` files are deliberately *not* excluded from Syncthing sync.
* **Impact**: Plain-text API keys and session tokens are transmitted across local network devices via P2P sync, exposing credentials if any peer device is unencrypted.

### 3.3 Lack of PII Scrubbing in Tracebacks
* **Unredacted Logs**: Error tracebacks printed to terminal logs or stored in checkpoint files include full resume text, candidate names, addresses, phone numbers, and email addresses.

---

## 🌐 Section 4: Scrapers, Liveness Engine & Third-Party Fragility

### 4.1 Subprocess Shell-Out Cascades
* **Multi-Runtime Ingestion**: Python invokes [`scripts/scan_boards.py`](file:///Users/morganescott/resume-builder/scripts/scan_boards.py), which spawns Node.js to execute [`board-scanners/run_provider.mjs`](file:///Users/morganescott/resume-builder/board-scanners/run_provider.mjs), which calls provider ES modules in [`board-scanners/providers/`](file:///Users/morganescott/resume-builder/board-scanners/providers).
* **Impact**: An unhandled rejection in a JavaScript provider script crashes the Node subprocess with exit code `1`, dropping the entire Python batch scan.

### 4.2 DOM Selector Fragility & Cookie Dependencies
* **Brittle Scraper Hooks**: [`scripts/scan_linkedin.py`](file:///Users/morganescott/resume-builder/scripts/scan_linkedin.py) relies on `linkedin-jobs-scraper` and `browser_cookie3`. `browser_cookie3` frequently fails on modern macOS/Windows due to OS keychain encryption changes (Chrome DPAPI/Keychain restrictions).

### 4.3 Anti-Bot False Positive Expirations
* **Liveness Misclassification**: [`scripts/liveness.py`](file:///Users/morganescott/resume-builder/scripts/liveness.py) spawns [`scripts/check-liveness.mjs`](file:///Users/morganescott/resume-builder/scripts/check-liveness.mjs) to check job posting URLs. When Greenhouse, Lever, or LinkedIn return HTTP `403 Forbidden`, `429 Too Many Requests`, or Cloudflare CAPTCHA challenges, the engine misinterprets anti-bot responses as dead listings, automatically moving valid JDs into `expired/`.

---

## 📄 Section 5: Resume Tailoring, Google XYZ Formula & Recruiter Impact

### 5.1 The Google XYZ Formula Paradox
* **Robotic "AI-Beige" Output**: [`scripts/validate_resume.py`](file:///Users/morganescott/resume-builder/scripts/validate_resume.py) programmatically enforces Google's XYZ formula (*Accomplished [X], measured by [Y], by doing [Z]*) on every bullet point.
* **Recruiter Impression**:
  Forcing metrics onto every single entry produces artificial, hyper-quantified claims:
  > *"Optimized internal documentation readability, increasing developer reading velocity by 34.2% through 14 structured Markdown edits."*
  Recruiters recognize formulaic AI bullets. When every bullet contains a metric, core achievements lose impact.

### 5.2 "Zero Lie" Claim vs. LLM Semantic Drift
* **The "Cannot Lie" Myth**: [`README.md`](file:///Users/morganescott/resume-builder/README.md#L65) states: *"It cannot lie about you... The AI can rephrase and select—it cannot invent."*
* **Code Reality**: In [`scripts/rewrite_bullets.py`](file:///Users/morganescott/resume-builder/scripts/rewrite_bullets.py), selected bullets are sent to Gemini to weave in JD keywords and company vocabulary substitutions (`customers -> guests`). During rewriting, LLMs introduce subtle semantic drift—claiming proficiency in sub-frameworks or tools that were absent from the original bullet.

### 5.3 Corporate Research Fluff
* **Superficial Tone Matching**: [`scripts/company_research.py`](file:///Users/morganescott/resume-builder/scripts/company_research.py) scrapes corporate homepages to inject mission values into Summaries and Cover Letters. When scraping returns generic marketing copy ("driving synergistic paradigm shifts"), cover letters sound like automated sales pitches.

### 5.4 Single-Page Budget Overflows & Typst Special Character Escaping
* **Orphan Headers in PDF Output**:
  The HTML template ([`resume-engine/templates/resume_template.html`](file:///Users/morganescott/resume-builder/resume-engine/templates/resume_template.html)) uses strict CSS margins. When candidate history includes multiple roles with long bullets, Playwright's Chromium renderer forces multi-page spills with orphan section headers or dangling single-line bullets.
* **Typst Markup Syntax Breaks**: In [`scripts/render_typst.py`](file:///Users/morganescott/resume-builder/scripts/render_typst.py#L29), character escaping omits square brackets `[` `]` and underscores `_`. Raw text containing brackets or underscores produces syntax errors during Typst compilation.

---

## 🎨 Section 6: UI/UX, TUI Ergonomics & Design Systems

### 6.1 Multi-Paradigm UI Fragmentation
The user interface switches across four distinct visual paradigms:
1. **Go Bubble Tea TUI** ([`dashboard/`](file:///Users/morganescott/resume-builder/dashboard/)): Catppuccin Macchiato palette with Lip Gloss borders.
2. **Python Questionary CLI** ([`scripts/menu.py`](file:///Users/morganescott/resume-builder/scripts/menu.py)): Plain terminal text menus.
3. **Rich / ANSI Art Banners** ([`scripts/cli_art.py`](file:///Users/morganescott/resume-builder/scripts/cli_art.py)): 80+ column ASCII art headers.
4. **PDF Output**: Monochrome print layout using `DM Serif Display` and `DM Sans`.

### 6.2 Terminal Layout Breakdowns on Narrow Screens
* **Wrapped ASCII Art**: [`scripts/cli_art.py`](file:///Users/morganescott/resume-builder/scripts/cli_art.py) and [`scripts/menu.py`](file:///Users/morganescott/resume-builder/scripts/menu.py) hardcode fixed line-length banners. On terminal widths under 80 columns (e.g. mobile Termux or vertical IDE splits), headers wrap into unreadable ASCII clutter.

### 6.3 Nerd Font Glyph Dependencies
* **Missing Icon Glyph Boxes**: Terminal icons rely on Nerd Font glyphs (`\uE0B0`, `\uF00c`). If a terminal lacks a Nerd Font, icons render as missing glyph boxes ("tofu") unless `RESUME_BUILDER_ICONS=unicode` is set manually in the shell environment.

---

## 🧮 Section 7: Algorithms, Vector RAG & Mathematical Claims

### 7.1 Mathematical Buzzword Marketing
* **Documentation Claim**: [`README.md`](file:///Users/morganescott/resume-builder/README.md#L30) advertises a *"Bayesian Probability Converter"*.
* **Code Reality**: A codebase search reveals **zero** implementation of Bayes' Theorem. The score calculation uses simple **piecewise linear interpolation**:
  ```python
  if score >= 4.5:
      odds = 0.02 * 14.5  # 29%
  elif score >= 4.0:
      odds = 0.02 * 7.25  # 14.5%
  ```

### 7.2 Fragile Vector Store Cache Invalidation
* **Silent RAG Degradation**: [`scripts/vector_store.py`](file:///Users/morganescott/resume-builder/scripts/vector_store.py#L62-L64) checks the SHA-256 hash of `bullet-bank-keepers-audited.csv` against `bullet_vectors_ge2_d768.meta`. When a user edits a bullet, the SHA hash updates. `vector_store.py` returns an empty list `[]` for semantic RAG searches until the user manually executes `python scripts/embed_bullet_bank.py`. The system falls back to keyword matching without notifying the user.

### 7.3 Instruction Drop-Off in Dense System Prompts
* **Prompt Over-Saturation**: [`resume-engine/prompts/tailor_resume.md`](file:///Users/morganescott/resume-builder/resume-engine/prompts/tailor_resume.md) contains over 15 distinct prompt directives (XYZ formula, company vocabulary substitutions, voice constraints, skills matrix grounding, character budgets). Standard LLMs exhibit instruction drop-off when presented with overly dense prompt instruction sets.

---

## 🧪 Section 8: Test Suite Hygiene, SRE Resilience & Failure Recovery

### 8.1 Over-Mocking in Unit Tests
* **Integration Blindspots**:
  * The repository contains **106 test modules** in [`tests/`](file:///Users/morganescott/resume-builder/tests).
  * Almost every test relies heavily on `unittest.mock.patch` (mocking `gemini_client.generate`, `requests.post`, `subprocess.run`).
  * **Zero End-to-End Tests:** No automated test launches Playwright Chromium to verify real HTML-to-PDF rendering end-to-end, and no test compiles and runs the Go binary.

### 8.2 API Rate-Limit Stalls (Gemma Pacing)
* **65-Second Execution Freezes**: In [`scripts/gemini_client.py`](file:///Users/morganescott/resume-builder/scripts/gemini_client.py#L196), falling back to `gemma-4-31b-it` enforces a mandatory **65-second sleep** between calls to respect the 16k TPM limit. In a batch run processing 10 jobs, falling back to Gemma forces the CLI to sleep for over **10 minutes**, appearing frozen to the user.

### 8.3 Infinite Validation Repair Loops
* **Quota Exhaustion**: When [`scripts/validate_resume.py`](file:///Users/morganescott/resume-builder/scripts/validate_resume.py) fails a generated resume, `orchestrator.py` triggers a 4-pass repair loop. If the model deletes a bullet to fix a metric collision, it breaks role minimums, burning API quota without converging.

---

## ⚡ Section 9: Onboarding & ADHD Cognitive Load

### 9.1 High Initial Setup Barrier
Before generating a single tailored resume, new users must:
1. Install Python 3.10+, Node.js, npm, npx, Playwright Chromium binaries, and the Go toolchain.
2. Configure a Gemini API Key in `profiles/<name>/.env`.
3. Run an 8-stage interactive wizard in [`scripts/bootstrap_profile.py`](file:///Users/morganescott/resume-builder/scripts/bootstrap_profile.py).
4. Supply historical resumes and build a bullet bank.
5. Extract career history and run audit scripts.

### 9.2 Opaque Execution Spinners
Running `resume run` executes a sequential pipeline:
`Company Research ──▶ Liveness Check ──▶ Split-Agent Evaluation ──▶ Bullet Mining ──▶ LLM Rewrite ──▶ Validation Retry Loop ──▶ Playwright PDF Rendering`

If Gemini rate-limits or Playwright takes long to launch, the terminal displays generic spinners without progress percentages, leaving the user unable to tell if execution is progressing or hung.

---

## 🛠️ Section 10: Master Remediation Matrix (35 Explicit Verified Findings)

| # | Subsystem / Category | Specific Flaw / Finding | Severity | Exact Actionable Remediation |
| :--- | :--- | :--- | :--- | :--- |
| **1** | Architecture | Monolithic files (`orchestrator.py` 229KB, `menu.py` 95KB). | 🔴 **High** | Refactor into modular sub-packages (`engine/tailor.py`, `ui/menu/`). |
| **2** | Architecture | 4-runtime polyglot stack sprawl (Python, Node, Go, Shell). | 🔴 **High** | Standardize dependencies and provide automated Docker/DevContainer specs. |
| **3** | Architecture | Inline hacks breaking circular imports (`gemini_client.py`). | 🟡 **Medium** | Re-architect dependency tree to inject API client via dependency injection. |
| **4** | Architecture | Hardcoded `/usr/local/bin/python3.13` paths in `doctor.py`. | 🟡 **Medium** | Replace with dynamic `sys.executable` and cross-platform resolution. |
| **5** | Architecture | Subprocess `which typst` call in `render_typst.py` breaks Windows. | 🟡 **Medium** | Replace `subprocess.run(["which"...])` with `shutil.which("typst")`. |
| **6** | Architecture | Repository root clutter (`ImprovementConcepts/`, archives). | 🟢 **Low** | Relocate legacy working files into `/docs/archive/`. |
| **7** | Persistence | 5-way state fragmentation (`data.db`, JSON, CSV, `.md`). | 🔴 **High** | Unify state around `profiles/<profile>/data.db` as single source of truth. |
| **8** | Persistence | Go TUI vendoring drift reading legacy `applications.md`. | 🔴 **High** | Refactor `dashboard/` Go handlers to query `data.db` SQLite directly. |
| **9** | Persistence | SQLite `CHECK` constraint fails on `'interview'` / `'offer'` statuses. | 🔴 **High** | Update `db.py` schema `CHECK` constraint to include all pipeline statuses. |
| **10** | Persistence | SQLite WAL mode lock contention and `.sync-conflict-*` files. | 🔴 **High** | Configure SQLite busy timeouts and exclude WAL/shm files in Syncthing. |
| **11** | Persistence | Non-atomic appends on `jd_tracker_log.csv` without file locking. | 🔴 **High** | Implement `fcntl.flock` file locks in `atomic_write.py` or route via SQLite. |
| **12** | Security | Plaintext API keys (`.env`) & cookies (`.linkedin_cookie`). | 🔴 **High** | Secure credentials using OS keyring (`keyring` module) or local encryption. |
| **13** | Security | Unencrypted P2P Syncthing sync of `.env` files. | 🔴 **High** | Exclude `.env` and cookie files from Syncthing folder sync definitions. |
| **14** | Privacy | Unredacted PII (phone, address) printed in tracebacks/logs. | 🟡 **Medium** | Add regex PII scrubbing filters in `cli_art.py` and checkpoint loggers. |
| **15** | Ingestion | Node.js provider script unhandled rejections drop Python scans. | 🟡 **Medium** | Wrap Node subprocess outputs in strict JSON response contracts with try/catch. |
| **16** | Ingestion | Brittle LinkedIn scraper and `browser_cookie3` keychain crashes. | 🟡 **Medium** | Provide graceful manual cookie export fallbacks when keychain reads fail. |
| **17** | Liveness | Anti-bot 403/429 responses trigger false job expirations. | 🟡 **Medium** | Treat 403/429/CAPTCHA responses as "Unknown/Deferred" instead of "Expired". |
| **18** | Recruiter | Forced Google XYZ formula creates robotic, artificial bullets. | 🟡 **Medium** | Relax `validate_resume.py` to allow qualitative impact bullets alongside XYZ. |
| **19** | Recruiter | LLM semantic drift introducing unverified tech stacks in rewrites. | 🟡 **Medium** | Add strict fact-grounding assertions comparing rewritten bullets to raw source. |
| **20** | Recruiter | Superficial company research scraping creating fluff cover letters. | 🟢 **Low** | Filter out marketing buzzwords before injecting research context into prompts. |
| **21** | Layout | Single-page PDF spills with orphan section headers. | 🟡 **Medium** | Apply CSS `page-break-inside: avoid` and dynamic character-budget checks. |
| **22** | Layout | Incomplete Typst special symbol escaping (`[`, `]`, `_`) in `render_typst.py`. | 🟡 **Medium** | Add full Typst syntax character escaping for brackets and underscores. |
| **23** | UI/UX | Multi-paradigm UI fragmentation (Bubble Tea, Questionary, ANSI). | 🟡 **Medium** | Unify UI components, spacing, and color tokens across Python and Go. |
| **24** | UI/UX | Fixed 80-column ASCII art wrapping on narrow terminals. | 🟡 **Medium** | Replace static banners with responsive `rich` console panels. |
| **25** | UI/UX | Missing icon glyph boxes ("tofu") on non-Nerd-Font terminals. | 🟢 **Low** | Auto-detect font glyph support and fall back to standard Unicode/ASCII icons. |
| **26** | Algorithms | Piecewise interpolation marketed as "Bayesian Converter". | 🟡 **Medium** | Update documentation to accurately describe "Piecewise Scoring Scale". |
| **27** | Algorithms | CSV hash changes silently disable vector RAG search. | 🟡 **Medium** | Trigger automatic background vector re-embedding when bullet CSV is edited. |
| **28** | Algorithms | Dense multi-constraint system prompts (`tailor_resume.md`). | 🟡 **Medium** | Split system prompts into sequential, single-responsibility LLM passes. |
| **29** | Testing | 106 unit tests rely on heavy mocking without E2E tests. | 🟡 **Medium** | Add real end-to-end integration tests executing full pipeline and Go TUI. |
| **30** | SRE | Gemma fallback enforces 65-second CLI thread sleeps. | 🟡 **Medium** | Replace blocking sleeps with asynchronous background job scheduling. |
| **31** | SRE | Infinite validation repair loops burning Gemini API quota. | 🟡 **Medium** | Enforce circuit breaker in `orchestrator.py` halting repair loops after 2 attempts. |
| **32** | Onboarding | 8-stage setup wizard creates high initial user friction. | 🟡 **Medium** | Provide a 1-command quickstart mode (`resume quickstart`) with sample data. |
| **33** | UX / ADHD | Opaque execution spinners during long multi-step LLM runs. | 🟡 **Medium** | Implement step-by-step progress bars with elapsed/estimated time indicators. |
| **34** | Doctor | `doctor.py` fails to report missing Go tools as fixable in non-Go environments. | 🟢 **Low** | Add automatic installation hints for Go toolchain in `doctor.py`. |
| **35** | Maintenance | Inconsistent version flags across scripts and CLI commands. | 🟢 **Low** | Centralize single source of truth for version number in `pyproject.toml`. |
