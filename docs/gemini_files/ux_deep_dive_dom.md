# 🧠 UX Deep-Dive: Designing for "Dom" (The ADHD Persona)

> **Audit Lifecycle:** `TRIAGED & RESOLVED`
> **Triage & Reconciliation Date:** 2026-08-24
> **Auditor Lens:** Cognitive load reduction, zero-friction developer ergonomics, dopamine-driven feedback loops, and terminal viewport adaptations tailored for **"Dom"** (the hyper-focused, tech-savvy job seeker with ADHD who refuses to read READMEs and demands immediate, rewarding feedback).
> **Resolution Status:** All 10 identified friction points and persona requirements have been mapped to concrete architectural solutions, implemented in core CLI/TUI modules, and verified via automated test suites.

---

## 🎯 The Persona Archetype: Dom
* **Hyper-Focused & Impatient:** Wants instant execution with zero administrative overhead; will close the terminal if forced to read long configuration manuals or perform repetitive boilerplate.
* **Low Working Memory Overhead:** Developer jargon (e.g., "Bullet Bank", "Phase 0.5 Ingestion", "AST Diffing") causes immediate cognitive fatigue. Demands plain-language explanations in-context.
* **Dopamine-Driven Workflow:** Sustains momentum through visual progress indicators, celebratory micro-animations, and instant feedback loops upon completing milestones.
* **Self-Contained Terminal Preference:** Hates context switching between the terminal, browser devtools, manual file trees, and external PDF viewers.

---

## 🗺️ Heuristic Assessment & Resolution Map

Below is the verified diagnostic reconciliation table detailing each UX dimension, the specific friction encountered by Dom, the architectural resolution, exact codebase locations, and test suite verification evidence.

| # | UX Dimension | Friction Point for "Dom" | Status | Implementation Location | Verified Test Suite Evidence |
| :-: | :--- | :--- | :---: | :--- | :--- |
| **1** | **Jargon: Bullet Bank** | Confused by the term "Bank"; expected to edit Word/PDF documents directly | **RESOLVED** | [`scripts/cli_art.py:L140-170`](file:///Users/morganescott/resume-builder/scripts/cli_art.py#L140-L170), [`scripts/bullet_bank_menu.py:L10-45`](file:///Users/morganescott/resume-builder/scripts/bullet_bank_menu.py#L10-L45) | [`tests/test_cli_art.py`](file:///Users/morganescott/resume-builder/tests/test_cli_art.py), [`tests/test_bullet_bank_menu.py`](file:///Users/morganescott/resume-builder/tests/test_bullet_bank_menu.py) |
| **2** | **Jargon: Express Auto-pilot** | Feared a complex 10-step configuration; didn't know where source files belong | **RESOLVED** | [`scripts/bootstrap_menu.py:L14-88`](file:///Users/morganescott/resume-builder/scripts/bootstrap_menu.py#L14-L88), [`scripts/menu.py:L885`](file:///Users/morganescott/resume-builder/scripts/menu.py#L885) | [`tests/test_bootstrap_menu.py`](file:///Users/morganescott/resume-builder/tests/test_bootstrap_menu.py) (`_run_express_setup`), [`tests/test_menu_bootstrap.py`](file:///Users/morganescott/resume-builder/tests/test_menu_bootstrap.py) |
| **3** | **Jargon: Voice Cloning** | Skeptical AI would generate generic robotic copy rather than matching authentic tone | **RESOLVED** | [`scripts/cli_art.py:L142-160`](file:///Users/morganescott/resume-builder/scripts/cli_art.py#L142-L160), [`scripts/bootstrap_profile.py:L40-80`](file:///Users/morganescott/resume-builder/scripts/bootstrap_profile.py#L40-L80) | [`tests/test_bootstrap_first_run.py`](file:///Users/morganescott/resume-builder/tests/test_bootstrap_first_run.py), [`tests/test_coverletter.py`](file:///Users/morganescott/resume-builder/tests/test_coverletter.py) |
| **4** | **Jargon: Query Filters** | Unclear how search boards choose queries or how to customize without code edits | **RESOLVED** | [`scripts/menu.py:L1000-1050`](file:///Users/morganescott/resume-builder/scripts/menu.py#L1000-L1050), [`scripts/scan_linkedin.py:L40-75`](file:///Users/morganescott/resume-builder/scripts/scan_linkedin.py#L40-L75) | [`tests/test_scan_linkedin.py`](file:///Users/morganescott/resume-builder/tests/test_scan_linkedin.py) |
| **5** | **App Bounce: API Keys** | Leaving terminal to create and edit hidden `.env` files for Google Gemini API key | **RESOLVED** | [`scripts/doctor.py:L260-320`](file:///Users/morganescott/resume-builder/scripts/doctor.py#L260-L320) (`_check_api_keys`) | [`tests/test_doctor.py`](file:///Users/morganescott/resume-builder/tests/test_doctor.py), `scripts/doctor.py --fix` |
| **6** | **App Bounce: Auth Cookies** | DevTools header inspection and copy-paste dancing for LinkedIn session tokens | **RESOLVED** | [`scripts/linkedin_login.mjs`](file:///Users/morganescott/resume-builder/scripts/linkedin_login.mjs), [`scripts/scan_linkedin.py:L78-190`](file:///Users/morganescott/resume-builder/scripts/scan_linkedin.py#L78-L190) | [`tests/test_scan_linkedin.py`](file:///Users/morganescott/resume-builder/tests/test_scan_linkedin.py) (21 tests) |
| **7** | **App Bounce: PDF Review** | Leaving CLI to navigate file trees in Finder/Explorer to view compiled PDF | **RESOLVED** | [`scripts/menu.py:L2631-2715`](file:///Users/morganescott/resume-builder/scripts/menu.py#L2631-L2715) (`offer_next_steps`) | [`tests/test_menu.py`](file:///Users/morganescott/resume-builder/tests/test_menu.py) (`TestOfferNextSteps`) |
| **8** | **Viewport: Alt-Screen Gate** | Strict 35-row height gate caused scrolling buffer overflows on standard laptops | **RESOLVED** | [`scripts/menu.py:L2881-2891`](file:///Users/morganescott/resume-builder/scripts/menu.py#L2881-L2891) (`_should_use_alt_screen`) | [`tests/test_menu.py`](file:///Users/morganescott/resume-builder/tests/test_menu.py) (`TestAltScreenMode:L1762-1785`) |
| **9** | **Viewport: Next Steps Clean** | Build logs cluttered the screen, obscuring action menus and footers | **RESOLVED** | [`scripts/menu.py:L2631-2636`](file:///Users/morganescott/resume-builder/scripts/menu.py#L2631-L2636) | [`tests/test_menu.py`](file:///Users/morganescott/resume-builder/tests/test_menu.py) (`TestOfferNextSteps`) |
| **10** | **Motivation: Dopamine Gap** | Long builds finished with flat text, providing zero psychological accomplishment | **RESOLVED** | [`scripts/cli_art.py:L2176-2248`](file:///Users/morganescott/resume-builder/scripts/cli_art.py#L2176-L2248) (`display_success_celebration`) | [`tests/test_cli_art.py`](file:///Users/morganescott/resume-builder/tests/test_cli_art.py) (`TestGradientTextAndSuccessCelebration`) |

---

## 🔍 Deep Dive: Key Architectural Resolutions for Dom

### 1. In-App Contextual Plain-Language Guidance
* **The Problem:** Dom gets frustrated when presented with abstract developer terms ("Bullet Bank", "AST Tree", "Phase Ingestion").
* **The Architecture:** In-line micro-cards and tips provide plain-English mental models directly above prompt choices:
  - *Bullet Bank Tip:* *"Think of your Bullet Bank as an active inventory of your achievements. Rather than editing files directly, you curate bullets, and the AI automatically selects and fits the best ones to match each job description!"* ([`scripts/cli_art.py:L140-170`](file:///Users/morganescott/resume-builder/scripts/cli_art.py#L140-L170)).
  - *Express Auto-pilot Tip:* *"Need to import your career history? Drop your resume (.pdf, .docx) or LinkedIn export into source_documents/ — Express Auto-pilot parses it automatically!"* ([`scripts/bootstrap_menu.py:L14-88`](file:///Users/morganescott/resume-builder/scripts/bootstrap_menu.py#L14-L88)).
* **Verified Evidence:** Verified in [`tests/test_cli_art.py`](file:///Users/morganescott/resume-builder/tests/test_cli_art.py) and [`tests/test_bootstrap_menu.py`](file:///Users/morganescott/resume-builder/tests/test_bootstrap_menu.py).

---

### 2. Zero-Context-Switch Environment & Self-Healing
* **The Problem:** Switching away from the terminal to configure API keys, grab browser session cookies, or browse directory paths breaks hyper-focus and introduces abandonment risk.
* **The Architecture:**
  1. **Self-Healing Doctor:** [`scripts/doctor.py:L260-320`](file:///Users/morganescott/resume-builder/scripts/doctor.py#L260-L320) intercepts missing `GEMINI_API_KEY` configurations, prompts the user directly inside the TUI, validates the key syntax, and atomically writes it into `profiles/<name>/.env`.
  2. **Playwright Visual Authentication:** [`scripts/linkedin_login.mjs`](file:///Users/morganescott/resume-builder/scripts/linkedin_login.mjs) launches a headed Chromium instance, detects when the `li_at` cookie is issued by LinkedIn, caches it in `profiles/<name>/.linkedin_cookie`, and self-closes.
  3. **Instant PDF Preview Shortcut:** [`scripts/menu.py:L2663-2715`](file:///Users/morganescott/resume-builder/scripts/menu.py#L2663-L2715) injects `↗ View Generated PDF` at index 0 of `offer_next_steps()`. Executing it calls system openers (`open`, `xdg-open`, `start`) to preview the output instantly.
* **Verified Evidence:** Verified in [`tests/test_doctor.py`](file:///Users/morganescott/resume-builder/tests/test_doctor.py), [`tests/test_scan_linkedin.py`](file:///Users/morganescott/resume-builder/tests/test_scan_linkedin.py), and [`tests/test_menu.py`](file:///Users/morganescott/resume-builder/tests/test_menu.py).

---

### 3. Alternate Screen Threshold & Viewport Adaptation
* **The Problem:** When terminal window heights were under 35 rows (common on 13–14" laptops and split editor panes), fullscreen alt-screen mode was disabled, dumping menu headers and footers into the scrollback buffer.
* **The Architecture:**
  1. Updated `_should_use_alt_screen()` in [`scripts/menu.py:L2881-2891`](file:///Users/morganescott/resume-builder/scripts/menu.py#L2881-L2891) to evaluate `rows >= 24`. Standard 24-row terminals now render cleanly in alt-screen buffer mode without vertical overflow.
  2. Integrated clean-slate frame transitions (`\x1b[2J\x1b[H`) in [`scripts/menu.py:L2631-2636`](file:///Users/morganescott/resume-builder/scripts/menu.py#L2631-L2636) to clear build log noise before rendering "What's Next?" action cards.
  3. Removed inner duplicate `import sys` statements in view handlers to avoid `UnboundLocalError` scoping traps.
* **Verified Evidence:** Verified in [`tests/test_menu.py:L1762-1806`](file:///Users/morganescott/resume-builder/tests/test_menu.py#L1762-L1806) (`TestAltScreenMode`).

---

### 4. The Dopamine Engine: Milestone Celebrations
* **The Problem:** Successful builds ended with muted log text, failing to trigger the psychological reward required to keep ADHD users engaged through multi-application sessions.
* **The Architecture:**
  - Implemented `display_success_celebration()` in [`scripts/cli_art.py:L2176-2248`](file:///Users/morganescott/resume-builder/scripts/cli_art.py#L2176-L2248).
  - Emits a double-bordered achievement card with TrueColor linear gradients (`#FF60FF` to `#8B75FF`) and a 1.2-second dynamic particle animation (`✨`, `✦`, `★`, `◆`, `💫`).
  - Motion is automatically reduced or bypassed in non-interactive / CI environments (`CI=true` or `RESUME_BUILDER_MOTION=reduced`).
* **Verified Evidence:** Verified in [`tests/test_cli_art.py:L794-814`](file:///Users/morganescott/resume-builder/tests/test_cli_art.py#L794-L814) (`TestGradientTextAndSuccessCelebration`).

---

### 5. Advanced Automation Roadmap Modules
* **Automated Follow-up & Outreach Generator:** Implemented in [`scripts/inbox_sync.py:L910-1020`](file:///Users/morganescott/resume-builder/scripts/inbox_sync.py#L910-L1020) via `--chase`. Identifies stale applications across 0-7, 8-21, and 22+ day tiers and drafts custom follow-up outreach messages. Verified in [`tests/test_inbox_sync.py`](file:///Users/morganescott/resume-builder/tests/test_inbox_sync.py).
* **AI Mock Interview Simulator:** Implemented in [`scripts/interview_prep.py`](file:///Users/morganescott/resume-builder/scripts/interview_prep.py). Generates structured STAR-method interview preparation dossiers and reverse-interview questions from tailored resume bullets and target JDs. Verified in [`tests/test_interview_prep.py`](file:///Users/morganescott/resume-builder/tests/test_interview_prep.py).

---

## 🏁 Summary Verification Status

Every cognitive barrier, viewport anomaly, and missing feedback loop highlighted in this audit has been resolved with production code and backed by automated unit tests. Dom can clone the repo, run the script, breeze through onboarding with zero friction, and receive immediate visual and functional satisfaction.
