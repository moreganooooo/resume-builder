# ⚙️ Operations & Deep-Dive Systems Guide

Welcome to the ultimate operational manual for `resume-builder`. This guide goes far beyond basic commands—it is an in-depth breakdown of the proprietary, cutting-edge sub-systems that make this program a state-of-the-art career operations engine.

---

## 🧭 1. The Interactive Charm TUI Dashboard & Knowledge Base Explorer

To launch your central visual mission control, simply type:
```bash
resume
```
Or launch into a specific profile:
```bash
resume --profile morgan
```
This loads our high-fidelity, Charmbracelet-based terminal dashboard (Bubble Tea v2, Lip Gloss v2, Glamour, Harmonica physics), styled in an adaptive Catppuccin color scheme.

### Dashboard Screens & Core Keyboard Controls:
1. **Pipeline Checkpoints (`1`):** Track where every single job posting sits in your queue—from *Newly Scanned* to *Evaluated*, *Tailored*, *Applied*, and *Followed Up*.
2. **Real-Time Progress Tracking (`2`):** Dynamic Bubbles progress bars with color gradients and percentage metrics for active batch scans or tailoring jobs, monitoring your conversion funnel (e.g., Application-to-Interview ratios).
3. **Report Viewer (`3`):** Read full job/company research reports and evaluation write-ups in the Glamour markdown viewport.
4. **Interactive Jobs Triage (`4`):** Browse jobs in an accordion view and move them through stages visually using arrow keys (`h/j/k/l` or `←/↓/↑/→`).
5. **Interactive Knowledge Base Explorer (`5`):**
   * Instantaneously search, inspect, and preview all personal intelligence documents across **All**, **Tools & Skills**, **Verified Metrics**, **Core Facts**, and **Historical Projects**.
   * Switch categories using `Tab` / `Shift+Tab` or `[` / `]`.
   * Live filter entries by keyword using `/` or standard typing.
   * Press `Enter` to open an item in the **Glamour Markdown Viewport**, rendering styled markdown with scrollable viewport navigation (`j/k`, `PageUp/PageDown`, `Esc` to return).
6. **Harmonica Physics & Responsive Reflow:** Fluid spring-eased view transitions, automatic screen-resize reflow, and proactive 80x24 minimum viewport warning cards.
7. **Accessibility & Preferences:**
   * `RESUME_BUILDER_MOTION=reduced`: Disables spring animations for users with vestibular or motion sensitivities.
   * `RESUME_BUILDER_ICONS=unicode`: Uses standard Unicode symbols instead of Nerd Fonts.
   * `RESUME_BUILDER_THEME=dark|light`: Overrides automatic terminal background detection.
8. **Gamification & Achievement Loops:** Milestones (like submitting your 10th tailored resume) unlock high-energy celebration cards complete with twinkling terminal animations (`display_success_celebration`) to keep your momentum and career dopamine high!
9. **Global Charmbracelet Prompts:** Confirmations, select menus, checkboxes, and free-text input across the entire CLI are globally routed through Charm's prompt system (`Go/huh`), which compiles dynamically on its first launch into `dashboard/bin/prompt` for lightning-fast, sub-millisecond keyboard reactions.

---

## 🔍 2. Job Board Aggregation, Scraping & Staleness Sweeps

Our aggregator is designed to sweep multiple public and private channels simultaneously to curate your pipeline with fresh postings.

### Board Scrapers & Aggregation Setup:
* **LinkedIn Scanner:** Uses a visual, secure browser login helper (`scripts/linkedin_login.mjs`) to capture your cookie, then scrapes matching postings in the background.
* **JobRight Scanner:** Scrapes highly targeted job feeds using persistent cookie-token headers.
* **Custom RSS Feeds:** Parses arbitrary custom RSS feeds (e.g., Y Combinator, corporate careers RSS) directly in Python.
* **Customizing Search Queries:** In-program forms let you add, edit, or delete job board configurations, custom search queries, and keywords without opening a text editor.

### 🟢 Liveness Checks & The Staleness Sweep:
Job boards are notorious for keeping filled or dead listings active to inflate their numbers.
* To verify a posting's status, run **`resume liveness`**.
* The program executes non-blocking background HTTP requests directly to the listing's target URL.
* Any listing that fails (returning a 404, redirecting to a generic search home, or closing registration) is automatically archived to your profile's `expired/` directory, sweeping out stale entries and keeping your active queue 100% actionable.

---

## 📊 3. Re-Engineered Dual-Metric Scoring (Split-Agent Architecture)

Most platforms offer a basic single "Match" percentage. We pioneered a **rigorous split-agent dual evaluation** that isolates career capacity from recruiter friction to eliminate model cognitive saturation:

```
┌─────────────────────────────────────────────────────────────┐
┌ 📊 SPLIT-AGENT PIPELINE AUDIT                               │
├─────────────────────────────────────────────────────────────┤
│  🎯 CAPABILITY FIT (Stage 1) ──▶  Direct functional fit     │
│                                   & CoBlack Capability Gaps │
│                                                             │
│  🎲 HIRING ODDS (Stage 2)    ──▶  Chronological gap risk    │
│                                   & Bayesian absolute odds  │
└─────────────────────────────────────────────────────────────┘
```

1.  **Capability Fit (Stage 1 - Technical & Functional):**
    Evaluates your actual professional career experience against the role's operations (including functional depth, target role overlap, and tools/process overlap) and outputs a structured **Capability Gaps list**. This identifies precisely where your resume text requires strategic adjustment.
2.  **Hiring Odds (Stage 2 - Recruiter & Practical Filters):**
    Predicts automated gating, recruiter friction, title continuity, domain credibility, and **Chronological Resume Gap Risk**. To support career transitions, the engine evaluates gap-periods based on company profile rigidity—penalizing traditional corporates while maintaining strong scores for modern, empathetic, or mission-driven organizations.

### 📈 Advanced Scoring Engine Features:
* **Piecewise Probability Scale**: Translates qualitative 1-5 interview odds scores into an empirical **Absolute Interview Probability Percentage** using piecewise linear interpolation against an industry baseline ($2.0\%$), reflecting up to a $20\text{x}$ response multiplier for elite fits.
* **Prestige-Tier Volume Calibration**: Classifies companies into volume risk categories. Tier-1 giants (extreme competition) have their funnel friction scores capped in Python, while Tier-3 boutiques receive positive boosts to reward your application.
* **Heuristic Ghost Job Probability**: Evaluates explicit red flags (placeholder boilerplate, evergreen phrasing, posting age) to compute a deterministic risk percentage of fake or inactive listings.
* **Dynamic Profile Overrides**: An automated Python check scans your `profile.yml` deal-breakers list. If `remote_required` is `True` and the LLM scores `remote_quality < 5` (hybrid/onsite signals detected) or returns matched hard blockers, Python forces the composite score to `0.00` and automatically archives the JD as a `"Skip"`.


---

## 🧠 4. Personalized Knowledge System (Your Compounding AI Mind)

This program gets smarter about you the more you use it. It is designed as a secure, local knowledge base that grows organically.

```
┌──────────────────────────────────────────────────────────────┐
│ 🧠 DYNAMIC KNOWLEDGE BASE                                    │
├──────────────────────────────────────────────────────────────┤
│  📄 verified_metrics.json  ──▶ Structured metric validations │
│  📄 historical_resumes/   ──▶ Core career history inputs    │
│  📄 portfolio_texts/      ──▶ Tone, style & portfolio files  │
│                                                              │
│  🔄 Synced via Syncthing to Mobile for On-The-Go Learning!  │
└──────────────────────────────────────────────────────────────┘
```

* **Uploading Knowledge Documents:** Over time, you can drop new documents into your profile's `data/` directory—such as historic resumes, portfolio copy, cover letters, transcripts, or project briefs. The AI reads and Indexes these to build a deep, contextual map of your capabilities.
* **The Compounding Bullet Bank:**
  * Every bullet point lives in your audited bank (`bullet-bank-keepers-audited.csv`).
  * If the AI suggests a beautiful, high-impact phrasing during a tailoring run and you approve it, that customized line is automatically queued back into your profile's "Keepers" database as an approved achievement.
  * Your bullet bank is a living, breathing asset that automatically compounds, refines, and expands with every single build!
* **Interactive Profile Skills CLI Dashboard (`verified_tools.json`):**
  * Under `Settings & Upkeep -> View & Manage Profile Skills`, a custom CLI dashboard displays your verified skills/tools grouped elegantly by category with confidence rating meters.
  * Supports full, atomic-write CLI CRUD operations (Add, Edit, Delete, View Detail) ensuring data consistency under `verified_tools.json` so your skills profile stays instantly updated as you learn new technologies.

---

## 🎭 5. Deep Company Research & Writing Voice Cloning

### 🔍 Behind-The-Scenes Company Research:
When you process a job description, if the scraper extracts a company URL, a background research agent immediately sweeps their About Us, Mission, Values, and Product pages.
* It extracts their core business register and corporate culture.
* It dynamically injects this context into your Resume Summary and Cover Letter's "Why this company" sections.
* **Semantic Vocabulary Translation:** Preferred vocabulary substitutions (e.g. `customers -> guests`) are injected directly into the LLM bullet rewrite context during Step 3, replacing old post-hoc regex matches with semantic, grammatically perfect sentence layouts in the model's native translation step.
* **The result:** A warm, values-driven tone-match for non-profit and mission-driven orgs, and a highly polished, crisp, metrics-focused tone-match for sharp B2B SaaS companies.

### 🗣️ Capturing Your Unique Writing Style:
Most resume builders write in generic "AI-beige" jargon. We hate that.
* Our system utilizes **Voice Cloning & Writing Style Profiles** to extract your unique sentence structures, vocabulary choices, and syntactic patterns.
* It maps your writing style onto a multi-dimensional matrix.
* After every build, a **Holistic Critique Pass** reviews the output. It explicitly categorizes lines into *Distinctive Sections* (sentences that sound unmistakably like you) and *Flat Sections* (competent but generic).
* The AI optimizer is **strictly forbidden** from touching your Distinctive Sections, ensuring that the final resume maintains your authentic, human personality!

---

## 📝 6. Personalized Document Tailoring

Our tailoring engine treats your professional resume and cover letter as a unified, cohesive narrative, enforced by premium validation checkers:

### Resume Tailoring:
* **The Compounding Selector:** Selects the absolute highest-impact achievements from your audited bullet bank matching the job's core technical requirements.
* **CV-Context Auditing:** Feeds previously completed bullets (both role-specific and other roles in the CV) into the LLM context to prevent macro-redundancy, verb repetition, or metric duplication across the resume.
* **Typst Vector PDF Engine (`render_typst.py`):** Generates structured `.typ` document markup and compiles sub-second vector PDFs with native ATS typography and zero browser memory overhead.
* **The Summary Paradox (Structural Archetypes):** Generates target-specific resume summaries based on business archetypes—**Scale-First/Growth** (process/enterprise optimization) vs. **Zero-to-One/Builder** (startup/launch scale)—validated programmatically with custom metrics/specificity linter checks.
* **Metrics Verification:** Verifies all numerical values against `verified_metrics.json`—**it cannot fabricate or invent metrics**.
* **ATS Keyword & Ligature Verification:** Once compiled, the program reads the final PDF's rendered text layer to programmatically assert that all target keywords survived layout conversion without ligature corruption (e.g. `fi`, `fl`, `ff` combining into single symbols), bad line-breaks, or truncations.

### Cover Letter Tailoring:
* **Hook-First Openings:** Strictly bans flat, passive, or clichéd introductory sentences (*"My name is..."*, *"I am writing to apply..."*) in favor of an engaging, research-grounded narrative hook.
* **Linter Validation Retries:** Automatically runs a regex validator loop over the output cover letter. If a clichéd opener is detected, it triggers a corrective prompt cycle to rewrite and heal the opening paragraph.
* **"Why Us" Alignment:** Integrates background company research to write an authentic, deep, and convincing opening and closing.
* **Signature Block:** Automatically appends your absolute path signature image (`signature.png`) with clean, vector-perfect HTML margins.

---

## 🔬 7. Programmatic Resume-Writing Upgrade Suite & Storage Engine

We implemented an advanced, multi-dimensional technical upgrade to guarantee that every tailored resume meets an elite professional writing standard:

1. **Embedded ACID SQLite Storage (`data.db`):** Replaced legacy flat-file syncing with embedded SQLite database storage at `profiles/<profile>/data.db` managed by `scripts/db.py`. Stores job descriptions, application funnel states, and bullet bank achievements with ACID transaction safety and indexed query speed.
2. **Typst Vector PDF Compilation (`scripts/render_typst.py`):** Integrated Typst vector document compilation for sub-second, 100% ATS-compliant PDF generation without headless browser dependencies.
3. **STAR/XYZ Syntactic Quality Grader:** Programmatic parser in `scripts/validate_resume.py` that evaluates every experience achievement bullet against Google's XYZ formula (*Accomplished [X], as measured by [Y], by doing [Z]*). Deducts points for missing active verbs, numerical metrics, or causal outcome connectors, feeding weak bullets back into the validator's repair loop.
4. **Authenticity & Voice Calibration Metric:** Linter that scans for generic AI clichés (*proven track record, results-driven professional, passion for innovation*) and cross-references stylistic tone against `voice-anchors.md` to ensure a bold, systems-driven, authentic human voice.
5. **Proud Career Break Calibrator:** Automated timeline gap engine in `scripts/normalize_resume.py` that detects employment gaps >3 months and programmatically constructs a proud, active **Career Break — Professional Development & Retraining** entry using standard `MM/YYYY` dating to eliminate ATS timeline continuity flags.
6. **Transferable Skills Translation Matrix:** Direct reframing matrix embedded in `tailor_resume.md` that guides the LLM to translate raw historical tasks (e.g. blog posts, classroom tutoring, administrative tracking) into sophisticated archetype vocabulary without ever fabricating or exaggerating raw metrics.
7. **Single-Column Layout & ATS Ligature Safeguards:** Enforces clean, semantic single-column rendering with static DM Sans fonts and explicit zero-ligature flags (`font-variant-ligatures: none`), guaranteeing 100% text extraction accuracy across Workday, Greenhouse, and Lever parsers.
