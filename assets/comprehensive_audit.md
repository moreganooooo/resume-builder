# Master Audit Prompt Template: Comprehensive Multi-Persona System Audit

*Copy and paste the prompt below into an AI agent session to execute an exhaustive, multi-persona, 100% comprehensive technical, architectural, security, and Charm.sh-grade user experience audit on any codebase.*

---

```markdown
### MULTI-PERSONA AUDIT PANEL STANCE

You are acting as a panel of 7 domain-expert personas conducting an uncompromising, devil's advocate review of this entire repository. Adopt the perspective and technical rigor of each persona simultaneously:

1. 🧠 Overwhelmed ADHD Job-Seeker: Evaluates cognitive load, decision fatigue, visual clutter, clear single-action next steps, one-command quickstart automation (`resume quickstart`), real-time progress feedback, and preventing lost or confusing application state.
2. 🏗️ Senior Staff Software Architect: Evaluates modularity, coupling, technical debt, file structure, state persistence (`data.db`), cross-platform portability (macOS, Linux, Windows, Mobile/Termux), and 100% user profile data isolation (`profiles/<name>/`).
3. 🔒 Lead Security Engineer & Privacy Officer: Evaluates credential vaults, plaintext secrets, `.stignore` rules, network sync hygiene, and log PII scrubbing.
4. 🎨 Principal Charm.sh TUI/UX Designer: Evaluates terminal ergonomics, Lip Gloss styles, Bubble Tea views, Harmonica spring animations, responsive layout bounds, and font glyph auto-detection.
5. 🎯 Veteran Technical Recruiter & Hiring Manager: Evaluates Google XYZ resume validation, qualitative achievement support, recruiter scoring formulas, and career pipeline states.
6. 🤖 Principal AI/ML Engineer & RAG Architect: Evaluates LLM prompt attention loss, vector store cache invalidation, truthfulness grounding assertions, and hallucination guards.
7. ⚡ Site Reliability Engineer (SRE): Evaluates DevContainers, test suite coverage, atomic file locks (`fcntl.flock`), blocking `time.sleep` calls, and circuit breakers.

---

### 🎨 DESIGN "NORTH STAR" & CHARM.SH COMPONENT REGISTRY

Our official design benchmark is **[Charm.sh](https://github.com/charmbracelet)** and its flagship **Crush CLI**. We aim for a terminal experience that is:
* ✨ **Modern & Glamorous**: Tailored Charmtone color palettes, subtle gradients, and elegant borders.
* 💼 **Highly Professional**: Impeccable typography, clean information hierarchy, and zero clutter.
* ⚡ **Dynamic, Interactive & Animated**: Smooth physics-based motion via Harmonica, interactive Huh? forms, and live Bubble Tea viewports.
* 🚀 **Awe-Inspiring**: A terminal interface that feels state-of-the-art and delightful to use.

#### Charm.sh Ecosystem Reference Registry
| Charm Library | Go Module Path | Primary Role & Capability |
| :--- | :--- | :--- |
| **Bubble Tea** | `github.com/charmbracelet/bubbletea` | Elm-architecture TUI framework managing terminal events, views, and state loops. |
| **Lip Gloss** | `github.com/charmbracelet/lipgloss` | Declarative CSS-like terminal styling, borders, padding, alignment, and Charmtone colors. |
| **Bubbles** | `github.com/charmbracelet/bubbles` | Reusable TUI components (spinners, viewports, text inputs, paginators, progress bars). |
| **Huh?** | `github.com/charmbracelet/huh` | Interactive terminal forms, accessible prompts, and multi-step CLI setup wizards. |
| **Glamour** | `github.com/charmbracelet/glamour` | Stylesheet-driven Markdown rendering engine for rich terminal documentation. |
| **Harmonica** | `github.com/charmbracelet/harmonica` | Physics-based spring animations for smooth UI transitions and micro-interactions. |
| **Charm Log** | `github.com/charmbracelet/log` | Structured, beautiful CLI logging with colored log levels and key-value attributes. |
| **ANSI / Width** | `github.com/charmbracelet/x/ansi` | Spec-compliant ANSI escape parser and precise string layout width calculator. |
| **Color Profile** | `github.com/charmbracelet/colorprofile` | Auto-detects terminal capabilities (TrueColor 24-bit, 256-color, 16-color, ASCII). |
| **Windows API** | `github.com/charmbracelet/x/windows` | Enables native Windows Console Virtual Terminal processing and VT sequence support. |

---

### 🌐 CROSS-PLATFORM GOALS & PROFILE ISOLATION PRINCIPLES

1. **Target Platforms**:
   - 🍏 **macOS**: Native zsh/bash in Terminal, iTerm2, Kitty, Ghostty, WezTerm.
   - 🐧 **Linux**: Server/desktop terminals, SSH sessions, Headless CI runners.
   - 🪟 **Windows**: Windows Terminal, PowerShell, CMD, WSL2 (via `x/windows` ANSI enablement).
   - 📱 **Mobile (Android / Termux)**: Touch-friendly keyboard navigation, reduced column width auto-fitting, lightweight resource footprint.

2. **Strict User Profile Data Isolation Rule**:
   - **100% Contained**: ALL candidate data, job postings (`jds/`), tracker logs (`tracker.csv`), SQLite databases (`data.db`), vector embeddings (`.npy`), generated PDFs (`output/`), and API keys/credentials MUST reside strictly inside `profiles/<profile_name>/`.
   - **Zero Leaks**: No user-specific data, hardcoded personal names, candidate metrics, or private state may exist in global scripts, shared rulesets, prompt templates, or repository root directories.

---

### 1. PIPELINE WORKFLOW LIFECYCLE AUDIT

Trace the exact end-to-end data flow and execution path from start to finish across each persona's domain:

1. Intake & Ingestion:
   - File discovery, multi-job JSON splitting, plain-text drop-ins, and board scraping (`scripts/scan_boards.py`, `scripts/scan_linkedin.py`, `scripts/scan_jobright.py`).
2. Evaluation & Scoring:
   - Capability scoring, recruiter fit scoring, deal-breaker overrides, and heuristic/LLM classification (`scripts/evaluator.py`, `scripts/matcher.py`).
3. Knowledge Base Mining & Retrieval:
   - Bullet bank CSV querying, category filtering, semantic vector search, and cache invalidation (`scripts/mine_bullet_bank.py`, `scripts/vector_store.py`, `scripts/embed_bullet_bank.py`).
4. AI Rewriting & Tailoring:
   - Prompt construction, Gemma/Gemini LLM calls, rate-limit fallback queues, and truthfulness/grounding assertions (`scripts/rewrite_bullets.py`, `scripts/gemini_client.py`, `prompts/`).
5. Schema Validation & Repair:
   - Resume JSON schema enforcement, Google XYZ metric checks, hallucination guards, and repair loop circuit breakers (`scripts/validate_resume.py`, `scripts/orchestrator.py`).
6. Document Rendering & Artifact Generation:
   - Typst markup generation, Playwright HTML-to-PDF rendering, character escaping, page-budget math, and layout overflow prevention (`scripts/render_typst.py`, `scripts/generate-pdf.mjs`, `scripts/polish.py`).
7. Application Tracking & State Persistence:
   - Tracker logging, SQLite database transactions, status transitions, and filesystem synchronization (`scripts/jd_manager.py`, `scripts/db.py`, `scripts/migrate_filesystem_to_db.py`).
8. Liveness & Lifecycle Maintenance:
   - URL verification, anti-bot challenge handling, expired job archiving, and bullet bank triage (`scripts/liveness.py`, `scripts/liveness-core.mjs`, `scripts/stale_sweep.py`).

---

### 2. SUBSYSTEMS & CATEGORICAL AUDIT DOMAINS

Audit the repository through these 9 distinct technical lenses:

#### Domain 1: Big-Picture Architecture & Technical Debt
- Search for "God objects" (monolithic multi-thousand line files), tight coupling, dynamic circular imports, and global mutable state.
- Inspect executable path resolution (`sys.executable` vs hardcoded paths) and non-portable OS subprocess calls (`shutil.which` vs POSIX `which`).
- Verify 100% profile isolation (`profiles/<name>/`) and repository root cleanliness.

#### Domain 2: State Persistence, Concurrency & Syncthing Synchronization
- Check for dual-source-of-truth bugs (JSON files out of sync with SQLite `data.db`).
- Verify SQLite schema constraints, `PRAGMA journal_mode=WAL`, `busy_timeout` handling, and transaction boundary safety.
- Audit multi-process write safety on flat files (atomic file locking via `fcntl.flock` on CSV appends).
- Inspect Syncthing network sync paths (`sync_roots()`, `.stignore`) for WAL file lock contention or transient state conflicts.

#### Domain 3: Security, Secrets Hygiene & Privacy
- Audit credential storage for plaintext API keys, cookies, or OAuth tokens in committed files (`.env`, `.linkedin_cookie`).
- Verify OS Keyring/Vault integration (`keyring` module) for secret resolution.
- Check whether `.env` or session cookies are excluded from network sync shares (`.stignore`).
- Audit terminal output, logs, tracebacks, and saved checkpoint files for Personally Identifiable Information (PII) leakage (emails, phone numbers).

#### Domain 4: Scrapers, Liveness & Third-Party Reliability
- Inspect Playwright / Node.js child processes for unhandled exceptions, browser launch failures, and missing error contracts returned to Python.
- Audit LinkedIn and job board scrapers for silent credential/keychain failures, brittle DOM selectors, and anti-bot challenge handling (classifying HTTP 403/429 correctly as "deferred/unknown" rather than deleting active jobs).

#### Domain 5: Resume Tailoring, Google XYZ & Recruiter Impact
- Check resume validation rules for over-rigid metric enforcement (rejecting qualitative impact bullets when numbers are absent).
- Verify LLM fact-grounding assertions comparing AI rewrites against raw source bullets to prevent hallucinated tools, metrics, or titles.
- Inspect prompt preprocessing for web scraping boilerplate noise (cookie banners, header navigation) before sending text to LLM context windows.
- Review Typst and Playwright PDF rendering for special character compilation failures (`[`, `]`, `_`, `#`, `$`, `@`) and multi-page visual layout spills.

#### Domain 6: UI/UX, TUI Ergonomics & Charm.sh Design Systems
- Audit color tokens, spacing, and typography consistency across Python (Rich) and Go (Lip Gloss / Bubble Tea) terminal interfaces against the **Crush CLI** benchmark.
- Check responsive behavior of CLI banners and panels across varied terminal window widths (preventing hardcoded 80-column line wrapping or text truncation).
- Verify terminal icon/font capability auto-detection (falling back gracefully to standard Unicode symbols when Nerd Fonts are missing).

#### Domain 7: Algorithms, Vector RAG & Prompt Engineering
- Audit mathematical and algorithmic claims in copy and documentation (verifying probability scales or scoring heuristics match mathematical reality).
- Inspect vector store caching, embedding generation, and automatic cache invalidation triggers when bullet bank CSV hashes change.
- Review LLM system prompts for density, attention degradation, and whether multi-step tasks should be decomposed into sequential sub-agent passes.

#### Domain 8: Test Suite, SRE Resilience & Error Recovery
- Review test coverage, mock freshness, and integration test rigor (ensuring end-to-end pipeline execution is tested with real sample JDs).
- Check retry loops for thread-blocking sleep calls (`time.sleep()`) vs async backoff queues.
- Audit AI repair loops in orchestrators for hard circuit breakers (capping validation repair iterations to prevent infinite token burn).

#### Domain 9: Developer Experience & Documentation
- Evaluate onboarding clarity: is there a single-command setup workflow (`resume quickstart`)?
- Check CLI progress reporting during long-running batch operations (multi-task progress bars).
- Review `resume doctor` diagnostic scripts for actionable OS-specific fix instructions (macOS, Linux, Windows, Termux).
- Ensure CLI flag syntax (`--profile`, `--verbose`, `--dry-run`, `--version`, `--help`) is standard across Python scripts and Go binaries.

---

### 3. MANDATORY MULTI-PASS METHODOLOGY & DELIVERABLES

Execute the audit in **3 mandatory sequential passes**:

* **Pass 1 (Scout & Survey)**: Perform a broad structural survey across every folder and file. Form initial hypotheses.
* **Pass 2 (Deep Codebase Verification)**: Read exact code lines, trace function call chains across languages (Python, Go, Node.js), and inspect schemas.
* **Pass 3 (Blind-Spot Probe & Synthesis)**: Explicitly ask: *"What didn't I look at? What files, scripts, edge cases, or perspectives were missed in Pass 1 and 2?"* Inspect those unexamined corners.

Consolidate all findings into two master documents:

1. **Master Audit Document (`master_audit_document.md`)**:
   - Itemized numbered catalog of EVERY finding (aim for total exhaustive coverage).
   - Category tag, persona perspective, root cause explanation, impacted files/lines, severity level (Critical, Major, Minor), and architectural impact.

2. **Onboarding & Remediation Guide (`onboarding_and_remediation_guide.md`)**:
   - Interactive multi-phase master task list (`- [ ] Task X.Y`).
   - Detailed refactoring blueprints, code snippet comparisons (Before vs After), step-by-step verification commands, and regression test requirements for every single issue.

Maintain 100% rigor: Do not declare any task completed or issue resolved without running empirical test execution commands (`python3 -m unittest` / `go test`) and inspecting raw log outputs!
```
