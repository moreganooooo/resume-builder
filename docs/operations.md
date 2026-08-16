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

---

## 🎭 5. Deep Company Research & Writing Voice Cloning

### 🔍 Behind-The-Scenes Company Research:
When you process a job description, if the scraper extracts a company URL, a background research agent immediately sweeps their About Us, Mission, Values, and Product pages. 
* It extracts their core business register and corporate culture.
* It dynamically injects this context into your Resume Summary and Cover Letter's "Why this company" sections. 
* **The result:** A warm, values-driven tone-match for non-profit and mission-driven orgs, and a highly polished, crisp, metrics-focused tone-match for sharp B2B SaaS companies.

### 🗣️ Capturing Your Unique Writing Style:
Most resume builders write in generic "AI-beige" jargon. We hate that.
* Our system utilizes **Voice Cloning & Writing Style Profiles** to extract your unique sentence structures, vocabulary choices, and syntactic patterns.
* It maps your writing style onto a multi-dimensional matrix.
* After every build, a **Holistic Critique Pass** reviews the output. It explicitly categorizes lines into *Distinctive Sections* (sentences that sound unmistakably like you) and *Flat Sections* (competent but generic).
* The AI optimizer is **strictly forbidden** from touching your Distinctive Sections, ensuring that the final resume maintains your authentic, human personality!

---

## 📝 6. Personalized Document Tailoring

Our tailoring engine treats your professional resume and cover letter as a unified, cohesive narrative:

### Resume Tailoring:
* Selects the absolute highest-impact achievements from your audited bullet bank matching the job's core technical requirements.
* Verifies all numerical values against `verified_metrics.json`—**it cannot fabricate or invent metrics**.
* Adjusts chronological emphasis, surfacing relevant historical roles only when a job posting contains highly relevant keyword gates.

### Cover Letter Tailoring:
* Drafts a compelling, high-fidelity cover letter in your active writing voice.
* Integrates the backend company research to write an authentic, deep, and convincing "Why us" opening paragraph.
* Structures the body copy to map your compounding achievements directly to the job's hardest problems.
* Automatically appends your absolute path signature image (`signature.png`) with clean, vector-perfect HTML margins.
