# 💎 RESUME-BUILDER
### The job-search pipeline that actually reads the room. ✨

[![CI Multi-Version Matrix](https://github.com/moreganooooo/resume-builder/actions/workflows/pylint.yml/badge.svg)](https://github.com/moreganooooo/resume-builder/actions/workflows/pylint.yml)
[![Tests](https://img.shields.io/badge/tests-2%2C418%20passing-success.svg)](file:///Users/morganescott/resume-builder/tests)
[![Python 3.10 | 3.11 | 3.12](https://img.shields.io/badge/python-3.10%20%7C%203.11%20%7C%203.12-blue.svg)](https://www.python.org/)
[![Go 1.25](https://img.shields.io/badge/go-1.25-00ADD8.svg)](https://golang.org/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![WCAG 2.1 AA & PDF/UA](https://img.shields.io/badge/accessibility-WCAG%202.1%20AA%20%7C%20PDF%2FUA-green.svg)](https://www.w3.org/WAI/standards-guidelines/wcag/)

Not a "type in your job title, get a generic ChatGPT resume" toy. This is an ultra-premium, full-stack career operations pipeline built because I was tired of every AI resume tool doing exactly one of those steps badly and calling it a product.

This system **scans** real postings, **verifies** they're still active, **scores** your actual fit and ATS odds against a 10-dimensional rubric, **tailors** a resume and cover letter in your own distinct writing voice, **renders** a punishingly ATS-clean vector PDF, and **tracks** your applications.

Designed to be gorgeous, sparkling, and modular, it runs as a high-fidelity Terminal User Interface (TUI) on both your **Desktop computer** and **Android Linux Mobile (Google Pixel 10)**.

---

```
   scan            liveness          evaluate           tailor / render          track
┌─────────┐     ┌───────────┐     ┌───────────┐     ┌──────────────────┐     ┌──────────┐
│ JobRight│ ──▶ │  is this  │ ──▶ │ score fit │ ──▶ │  write it in     │ ──▶ │  log the │
│ LinkedIn│     │ posting   │     │ & ATS     │     │  YOUR voice from │     │  build,  │
│ Wellfnd │     │ still     │     │ odds      │     │  a verified bank,│     │  link the│
│ Otta/YC │     │ live?     │     │           │     │  render clean PDF│     │  posting │
└─────────┘     └───────────┘     └───────────┘     └──────────────────┘     └──────────┘
```

---

## 🏛️ The 7 Core Architectural Pillars

### 1. 🌐 Multi-Board Ingestion & Anti-Bot Infrastructure
* **Comprehensive Provider Ecosystem & Batch Scanner:** Native ingestion for Greenhouse, Lever, Workable, SmartRecruiters, Recruitee, Workday, LinkedIn, JobRight, Wellfound, Otta, Y Combinator (Work at a Startup), Levels.fyi, and curated remote indexes with high-performance concurrent single-process batch execution (`board-scanners/run_provider.mjs --batch`).
* **Role Discovery & O*NET SOC Taxonomy:** Built-in title normalization and query alias expansion (`data/modern_title_aliases.yml` and `scripts/role_discovery.py`) mapping modern roles to formal O*NET Standard Occupational Classification codes.
* **Commercial Anti-Bot Fallbacks:** Automatic Scrape.do proxy gateway routing on Cloudflare / 403 blocks with per-site token-bucket rate limiting and millisecond randomized jitter.
* **Deduplication Hashing & Blacklists:** SHA-256 canonical posting deduplication and crowdsourced employer blacklists.
* **Local & Commute-Aware Search:** Offline geocoding (bundled GeoNames centroids, no API key, no network) scores every posting's real distance from your configured origin, with a 5–25 mile radius and a remote / hybrid / on-site filter you can combine. Handles the location strings postings actually use — exclusion fencing ("US Remote, excluding CA"), multi-hub roles scored by their *nearest* office, metro shorthand, and international rejection.
* **Full-Text Sources vs. Discovery Sources:** Indeed (via JobSpy) and USAJOBS return complete descriptions; aggregators like Jooble and Adzuna serve truncated teasers by design and are flagged as such rather than silently tailored against. `resume discover-employers` mines the employers those aggregators surface near you and tracks the ones with real ATS boards, so their full postings get scraped directly.

### 2. 📊 Split-Agent Dual-Metric Intelligence
* **Capability Fit vs. Recruiter Friction:** Isolates functional engineering depth from bureaucratic recruiter friction to eliminate LLM cognitive saturation.
* **Piecewise Empirical Odds Engine:** Standardized conversion curves ($>4.5 \rightarrow 35\%$ callback rate) based on empirical tech hiring data.
* **Pre-Flight Capability Gating & Ghost Job Scorer:** Instant zero-cost heuristic screening and mathematical ghost job risk scoring ($0.0–1.0$).
* **Batch Skill-Gap Radar Matrix:** Aggregates missing skills across all pending postings to pinpoint the highest-leverage technologies to learn.

### 3. 🛡️ Audited Compounding Truth Engine
* **Zero-Hallucination Receipt Grounding:** Every bullet and metric originates from an audited keeper repository (`bullet-bank-keepers-audited.csv`). The AI can select and rephrase—**it cannot invent**.
* **STAR / Google XYZ Syntactic Quality Grader:** Enforces active past-tense verbs, quantifiable results, and causal connectors.
* **RFC 6902 JSON Patch Surgical Bullet Repair:** Precise JSON Patch engine (`scripts/patch_engine.py`) fixing failing bullets without regenerating entire documents.
* **Anti-Cliché Linter:** Eliminates banned AI idioms (*delve into, seamlessly, testament to, spearhead*) and preserves human authenticity.

### 4. 🗣️ Authenticity, Voice Cloning & ATS Science
* **Statistical Cadence & Voice Anchoring:** Enforces natural sentence length variance ($\sigma \ge 4.5$), burstiness spans ($\ge 12$), and type-token lexical diversity ($TTR \ge 0.46$).
* **Seniority & Company Scale Calibration:** Dynamically tunes word budgets and executive tone based on detected role scope (Startup vs Enterprise, IC vs Staff/VP).
* **Golden Ratio Cover Letters:** Strict 250–350 word budgets, 4-paragraph frameworks (*Hook -> Value Prop -> Proof/Culture -> CTA*), and front-loaded ATS keywords.

### 5. 📄 Multi-Format Vector & Typesetting Pipeline
* **Sub-Second Native Typst Vector Engine:** Blazing fast vector PDF generation across Standard, Executive, Compact 1-Page, and Modern Tech templates.
* **Playwright Headless Chromium Engine:** HTML/CSS to PDF with WCAG 2.1 AA & PDF/UA accessibility tagging and document outline trees.
* **Single-Column ATS DOCX Auto-Router:** Automatically emits single-column Microsoft Word `.docx` documents for 97%+ Workday/Taleo parseability.
* **Plain ASCII & JSONResume Exporters:** Clean text-box formatters and standard JSON Resume schema exports.

### 6. 💾 Career Operations CRM & Telemetry
* **Embedded ACID SQLite Database (`data.db`):** High-performance indexed storage for jobs, contacts, stages, and metrics with strict test-write isolation.
* **Automated IMAP / Email Sync Daemon & Write-Back:** Scans incoming recruiter messages, classifies intent (interview, offer, rejection), and updates stage transitions in `data.db` (`application_log`) via `--apply`.
* **Silence Detector & Chase List:** Evaluates application aging tiers (0–7d, 8–21d, 22+d) and drafts polite, tailored follow-up emails via `--chase`.
* **Recruiter & Hiring Manager Lead Enrichment:** Generates search dorks and CRM contact entries for direct outreach.
* **Bullet-Tag-to-Outcome Correlation:** Mathematical tracking correlating specific bullet categories and tags with real interview offers.

### 7. ⚡ Terminal Craft & Offline Multi-LLM Sovereignty
* **Charm TUI Cockpit (Bubble Tea v2 & Lip Gloss v2):** Instantaneous startup, Catppuccin themes, Harmonica spring physics animations, responsive 80x24 reflow, and interactive Knowledge Base Explorer.
* **Accessibility & Customization:** First-class support for `RESUME_BUILDER_MOTION=reduced`, `RESUME_BUILDER_ICONS=unicode`, and `RESUME_BUILDER_THEME=dark|light`.
* **Local Offline Tier (Ollama / vLLM):** Zero-cloud, local offline generation targeting DeepSeek-R1 / Llama 3 with zero API key dependencies.
* **Multi-Key API Rotation & Context Caching:** Automatic key failover on HTTP 429 and explicit prompt prefix caching for 90% token cost savings.
* **Decentralized Mobile P2P Sync:** Lightweight Termux client on Android Linux synced peer-to-peer via Syncthing.

---

## 🗺️ Documentation Directory

* [**🚀 Unified Setup & Installation**](docs/program_docs/installation.md) — The 1-click installer for macOS, Linux, WSL, and Android Termux.
* [**⚙️ How It Works: Operations & Usage Guide**](docs/program_docs/operations.md) — Detailed specifications for each pipeline module, dual-metric scoring, compounding bullet banks, voice cloning, and TUI cockpit.
* [**🤝 Contributing Guidelines**](CONTRIBUTING.md) — Development setup, test execution, and code style.
* [**📜 Code of Conduct**](CODE_OF_CONDUCT.md) — Standards and community pledge.
* [**🔒 Security Policy**](SECURITY.md) — Vulnerability reporting and local data sovereignty disclosures.
* [**💬 FAQ & Troubleshooting**](docs/program_docs/faq.md) — Quick fixes for session cookies, Playwright, API keys, TUI customization, and synchronization.

---

## 🎯 Quick Start Commands

```bash
# Launch the main menu & TUI cockpit
resume

# Launch into a specific profile
resume --profile morgan

# Run self-healing health diagnostics across all checks
resume doctor

# Run a quick smoke-test against a sample job posting
resume sample

# Find local employers with public ATS boards and track them
resume discover-employers            # preview
resume discover-employers --apply    # write them

# Scan for new jobs on LinkedIn, Wellfound, or Otta
resume scan --source linkedin --query "Staff Software Engineer"

# View executive mission control cockpit in terminal
python scripts/mission_control.py

# Export data lake to Parquet, DuckDB, or Excel
python scripts/export_data.py
```

Let's go crush this job search! 🚀
