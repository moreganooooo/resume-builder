# ⚙️ Operations & Deep-Dive Systems Guide

Welcome to the ultimate operational manual for `resume-builder`. This guide goes far beyond basic commands—it is an in-depth breakdown of the proprietary, cutting-edge sub-systems that make this program a state-of-the-art career operations engine.

---

## 🧭 1. The Interactive Go TUI Dashboard

To launch your central visual mission control, simply type:
```bash
resume
```
This loads our high-fidelity, Bubble Tea-based terminal dashboard, styled in a sleek Catppuccin color scheme. 

### Dashboard Sections & Features:
1. **Pipeline Checkpoints:** Track where every single job posting sits in your queue—from *Newly Scanned* to *Evaluated*, *Tailored*, *Applied*, and *Followed Up*.
2. **Interactive Triage:** Move jobs through stages visually using arrow keys instead of editing database entries manually.
3. **Live Metrics View:** Monitor your conversion funnel (e.g., Application-to-Interview ratios) with live ASCII bar charts.
4. **Gamification & Achievement Loops:** Milestones (like submitting your 10th tailored resume) unlock high-energy celebration cards complete with twinkling terminal animations (`display_success_celebration`) to keep your momentum and career dopamine high!
5. **Global Charmbracelet Prompts:** Confirmations, select menus, and checkboxes across the entire CLI are globally routed through Charm's state-of-the-art terminal prompt system (`Go/huh`), which compiles dynamically on its first launch into `dashboard/bin/prompt` for lightning-fast, sub-millisecond keyboard reactions.

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

## 📊 3. Dual-Metric Scoring: Fit Score vs. Odds Score

Most platforms give you a single "Match" percentage. We pioneered a **dual-metric analysis** that evaluates job postings from two completely different dimensions:

```
┌─────────────────────────────────────────────────────────────┐
│ 📊 DUAL-METRIC PROFILE AUDIT                                 │
├─────────────────────────────────────────────────────────────┤
│  🎯 FIT SCORE: 85%  ──▶  How well you actually fit the role │
│                          (10-dimensional weighted rubric)   │
│                                                             │
│  🎲 ODDS SCORE: 92% ──▶  Your mathematical probability of   │
│                          clearing the initial ATS screening │
└─────────────────────────────────────────────────────────────┘
```

1. **The Fit Score (Your Perspective):**
   Evaluates your actual professional capability against the role's text using a **10-dimensional weighted rubric** (e.g., core tech stack depth, leadership scale, domain context, communication expectations). It asks: *Is this a job you would actually excel at and enjoy?*
2. **The Odds Score (The ATS/Screener Perspective):**
   A rare, highly unique metric that models the **probabilistic likelihood of your resume passing the initial automated screening, HR filter, and keyword keyword ATS bots**. It checks for keyword density, structural page-count boundaries, and formatting gates. It asks: *Will an automated system let your resume through to a human?*

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
* **The Summary Paradox (Structural Archetypes):** Generates target-specific resume summaries based on business archetypes—**Scale-First/Growth** (process/enterprise optimization) vs. **Zero-to-One/Builder** (startup/launch scale)—validated programmatically with custom metrics/specificity linter checks.
* **Metrics Verification:** Verifies all numerical values against `verified_metrics.json`—**it cannot fabricate or invent metrics**.
* **ATS Keyword & Ligature Verification:** Once compiled, the program reads the final PDF's rendered text layer to programmatically assert that all target keywords survived Chromium-to-PDF layout conversion without ligature corruption (e.g. `fi`, `fl`, `ff` combining into single symbols), bad line-breaks, or truncations.

### Cover Letter Tailoring:
* **Hook-First Openings:** Strictly bans flat, passive, or clichéd introductory sentences (*"My name is..."*, *"I am writing to apply..."*) in favor of an engaging, research-grounded narrative hook.
* **Linter Validation Retries:** Automatically runs a regex validator loop over the output cover letter. If a clichéd opener is detected, it triggers a corrective prompt cycle to rewrite and heal the opening paragraph.
* **"Why Us" Alignment:** Integrates background company research to write an authentic, deep, and convincing opening and closing.
* **Signature Block:** Automatically appends your absolute path signature image (`signature.png`) with clean, vector-perfect HTML margins.
