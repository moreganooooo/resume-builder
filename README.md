# 💎 RESUME-BUILDER
### The job-search pipeline that actually reads the room. ✨

Not a "type in your job title, get a generic ChatGPT resume" toy. This is an ultra-premium, full-stack career operations pipeline built because I was tired of every AI resume tool doing exactly one of those steps badly and calling it a product. 

This system **scans** real postings, **verifies** they're still active, **scores** your actual fit and ATS odds against a 10-dimensional rubric, **tailors** a resume and cover letter in your own distinct writing voice, **renders** a punishingly ATS-clean vector PDF, and **tracks** your applications. 

Designed to be gorgeous, sparkling, and modular, it runs as a high-fidelity Terminal User Interface (TUI) on both your **Desktop computer** and **Android Linux Mobile (Google Pixel 10)**.

---

```
   scan            liveness          evaluate           tailor / render          track
┌─────────┐     ┌───────────┐     ┌───────────┐     ┌──────────────────┐     ┌──────────┐
│ JobRight│ ──▶ │  is this  │ ──▶ │ score fit │ ──▶ │  write it in     │ ──▶ │  log the │
│ LinkedIn│     │ posting   │     │ & ATS     │     │  YOUR voice from │     │  build,  │
│         │     │ still     │     │ odds      │     │  a verified bank,│     │  link the│
│         │     │ live?     │     │           │     │  render clean PDF│     │  posting │
└─────────┘     └───────────┘     └───────────┘     └──────────────────┘     └──────────┘
```

---

## ✨ Core Sub-Systems & Unique Selling Points

### 📊 Re-Engineered Dual-Metric Scoring (Split-Agent Architecture)
Most platforms offer a basic single "Match" percentage. We pioneered a **rigorous split-agent dual evaluation** that isolates career capacity from recruiter friction to eliminate model cognitive saturation:
*   **Capability Fit (Stage 1):** Evaluates functional depth, target role overlap, and tools/process overlap to output a structured **CoBlack-Style Capability Gaps list** highlighting precisely where your resume text requires strategic adjustment.
*   **Hiring Odds (Stage 2):** Predicts automated gating, recruiter friction, title continuity, domain credibility, and **Chronological Resume Gap Risk** (empathy-aware criteria calibrated dynamically by company profile rigidity).
*   **Bayesian Probability Converter**: Translates qualitative 1-5 interview odds scores into an empirical **Absolute Interview Probability Percentage** (reflecting up to an $20\text{x}$ response multiplier for elite fits).
*   **Dynamic Profile Overrides**: An automated Python check scans your `profile.yml` deal-breakers list. If `remote_required` is `True` and `remote_quality < 5` (hybrid/onsite signals detected) or matched hard blockers trigger, Python forces the composite score to `0.00` and automatically archives the JD as a `"Skip"`.
*   **Prestige-Tier Calibration & Ghost Job Probability**: Applies mathematical caps to funnel friction for high-volume Tier-1 giants and calculates a deterministic risk percentage of fake or inactive listings based on explicit red flags.


### 🧠 Dynamic Knowledge System (Compounding Brain)
This program gets smarter about you the more you use it. It is designed as a secure, local knowledge base that grows organically.
* **Knowledge Document Feeding:** Drop historical resumes, portfolio copies, cover letters, transcripts, or project briefs into your `data/` directory. The AI indexes these files to build a deep, contextual map of your capabilities.
* **The Compounding Bullet Bank:** Every achievement lives in your audited bank (`bullet-bank-keepers-audited.csv`). If the AI suggests a beautiful, high-impact phrasing during a tailoring run and you approve it, that customized line is automatically queued back into your profile's "Keepers" database as an approved achievement. Your bullet bank organically compounds, refines, and expands with every build!

### 🗣️ Writing Voice Cloning & Protection
Most resume builders write in generic "AI-beige" jargon. We hate that.
* Our system utilizes **Voice Cloning & Writing Style Profiles** to extract your unique sentence structures, vocabulary choices, and syntactic patterns.
* After every build, a **Holistic Critique Pass** reviews the output, explicitly categorizing lines into *Distinctive Sections* (sentences that sound unmistakably like you) and *Flat Sections* (competent but generic).
* The AI optimizer is **strictly forbidden** from touching your Distinctive Sections, ensuring that the final resume maintains your authentic, human personality!

### 📝 Programmatic Resume-Writing Upgrade Suite
* **STAR/XYZ Syntactic Quality Grader:** Programmatic parser in `scripts/validate_resume.py` that evaluates every experience achievement bullet against Google's XYZ formula (*Accomplished [X], as measured by [Y], by doing [Z]*), enforcing active verbs, metrics, and causal connectors.
* **Authenticity & Voice Calibration Linter:** Linter that eliminates generic AI clichés (*proven track record, results-driven professional*) and matches style against `voice-anchors.md`.
* **Proud Career Break Calibrator:** Automatically detects employment gaps >3 months and inserts a proud, active **Career Break — Professional Development & Retraining** entry using standard `MM/YYYY` dating to eliminate ATS timeline continuity red flags.
* **Transferable Skills Translation Matrix:** Guidance matrix in `tailor_resume.md` that translates raw tasks (blog posts, tutoring, spreadsheets) into sophisticated marketing archetype vocabulary without metric exaggeration.


### 🏢 Behind-The-Scenes Company Research
When you process a job description, if the scraper extracts a company URL, a background research agent immediately sweeps their About Us, Mission, Values, and Product pages. 
* It extracts their core business register and corporate culture.
* It dynamically injects this context into your Resume Summary and Cover Letter's "Why this company" sections. 
* **The result:** A warm, values-driven tone-match for non-profit and mission-driven orgs, and a highly polished, crisp, metrics-focused tone-match for B2B SaaS companies.

### 🧹 Liveness Checks & The Staleness Sweep
Job boards are notorious for keeping filled or dead listings active to inflate their traffic. 
* Running **`resume liveness`** triggers non-blocking background HTTP requests directly to the listing's target URL. 
* Any listing that fails (returning a 404, redirecting to a generic search home, or closing registration) is automatically archived to your profile's `expired/` directory, sweeping out stale entries and keeping your active queue 100% actionable.

### 🚫 It Cannot Lie About You
Every bullet point the builder is allowed to use lives in an audited bank (`bullet-bank-keepers-audited.csv`) that’s already been checked for truthfulness, banned language, and vague verbs *before* a single job description ever sees it. The AI can rephrase and select—**it cannot invent**. Numbers are verified against structured metrics; if you don't have the receipts, it doesn't make the cut.

### 🔬 Premium Features & AI Orchestration Advancements
We have taken our tailoring, validation, and CLI experience to a world-class level:
* **ATS Keyword & Ligature Verification:** The renderer runs real-time programmatic verification checks on the output PDFs to guarantee that target keywords survive the Chromium-to-PDF rendering text layer without ligature corruption (e.g. `fi`/`fl` merging into Unicode equivalents like `ﬁ`), bad line breaks, or text truncation.
* **LLM-Based Semantic Vocabulary Translation:** Gone are the days of fragile, post-hoc regex word replacements. Preferred terms scraped during company research are injected directly into the Gemini rewrite instructions, allowing the model to naturally craft grammatically flawless, pluralization-safe sentences natively.
* **CV-Context Bullet Auditing:** During tailoring, the system feeds completed bullets (both role-specific and other CV roles) into the rewrite prompt context. This completely prevents verb repetition, metric duplication, or phrasing redundancy across your document.
* **The Summary Paradox (Structural Archetypes):** Codified narrative summary templates mapped directly to your targeted business stages—**Scale-First/Growth** (enterprise scale, process optimization) vs. **Zero-to-One/Builder** (startups, product launches), verified programmatically via custom linter specificity checkers.
* **Cover Letter Hook-First Introductions:** Upgraded cover letter generators ban flat, passive openings (*"My name is..."*, *"I am writing to apply..."*) in favor of high-impact narrative hooks, enforced via automatic regex-linter retries.
* **Interactive Skills CRUD Dashboard:** A dedicated CLI sub-screen (Settings -> View & Manage Profile Skills) allowing you to view, add, edit, and delete tools or categories stored atomically in your `verified_tools.json` file.
* **Global Go-Precompiled Charmbracelet Prompts:** The entire CLI's selections, checkbox menus, and confirmations have been upgraded to Charm's state-of-the-art terminal prompt system (`Go/huh`), with automatic on-the-fly pre-compilation for instant, sub-millisecond launches!

### ⚡ Go-Based TUI Dashboard
Our visual command dashboard is written in Go utilizing the gorgeous **Charmbracelet (Bubble Tea)** terminal ecosystem. To give you instant career dopamine, we compiled this into a native binary that loads in **10 milliseconds** and is styled with a gorgeous Catppuccin Macchiato color palette, complete with gamified success celebrations and twinkling terminal animations.

### 📱 Decentralized Mobile Sync
Run your job search from the subway! Our automated wizard installs a highly distilled **Mobile-Lite client (~15MB)** inside Termux on your phone. Using peer-to-peer **Syncthing**, your profile, JDs, and state files sync directly between your desktop and phone. Tailor on the go; your desktop compiles the heavy PDFs and syncs them back to your phone instantly!

---

## 🗺️ Documentation Directory

We have organized our setup guides and operational manuals into clean, bite-sized reference files:

* [**🚀 Unified Setup & Installation**](docs/installation.md) — The 1-click installer for macOS, Linux, WSL, and Android Termux.
* [**⚙️ How It Works: Operations & Usage Guide**](docs/operations.md) — Detailed specifications for each pipeline module, dual-metric scoring, compounding bullet banks, and voice cloning.
* [**💬 FAQ & Troubleshooting**](docs/faq.md) — Quick fixes for session cookies, Playwright, API keys, and synchronization.

---

## 🎯 Quick Start Commands

If you already have your environment set up and sourced:

```bash
# Launch the gorgeous main menu & dashboard
resume

# Run a self-healing health check on your environment
resume doctor

# Run a quick QA smoke-test against a sample job posting
resume sample

# Scan for new jobs on LinkedIn
resume scan --source linkedin --query "Staff Software Engineer"
```

Let's go crush this job search! 🚀
