# Product

<!-- impeccable:product-schema 1 -->

## Platform

web

## Stack

- TUI / Dashboard: Go (Bubble Tea framework)
- Core Engine & Orchestrator: Python 3.10+
- AI Models: Gemini / Gemma LLMs
- PDF Rendering: Node.js + Playwright 1.61.1 (pinned for macOS 12 compatibility)
- Resume Templates: HTML / Vanilla CSS rendered via Playwright Chromium headless
- Sync & Data: Syncthing (multi-device profile data sync)

## Users

Job seekers applying across any field or industry (e.g., marketing, sales, accounting, clerical, tech) since the system is entirely field-agnostic and fully customized to the user's preferences upon setup. They need to:
1. Search and aggregate job descriptions from multiple sources in one place.
2. Accurately score role alignment based on actual chance at an interview (beyond simple keyword matching).
3. Easily tailor resumes and cover letters using a bullet bank system that improves with every application.
4. Track full application lifecycle and progress seamlessly.

## Product Purpose

An end-to-end, LLM-powered job application management system built out of frustration with predatory, subscription-based web resume builders that squeeze job seekers for "premium" features, use opaque scoring, and generate subpar copy requiring heavy manual editing. It eliminates tedious manual resume customization by providing a free-to-operate, intelligent system that aggregates job leads, evaluates realistic interview odds, tailors resumes/cover letters to exact job specs, and tracks application pipelines. The ultimate goal is to instantly produce elite, zero-edit resumes that capture the tiny nuances required to turn a "thrown together" application into one of the best resumes a company receives.

## Positioning

Unlike traditional SaaS resume builders or basic ATS keyword matchers, `resume-builder` is a self-improving, LLM-driven engine that stands against the paid-SaaS category. It operates without subscription costs and dramatically outperforms competitors in quality. Instead of merely matching keywords or assessing general "fit", it scores by true interview likelihood, draws from a personal bullet bank to write in the user's authentic voice, and enforces strict PDF layout rules. It delivers an aesthetically gorgeous, state-of-the-art terminal/TUI experience that saves hours of manual labor while maintaining the highest personal standards.

## Operating Context

- Primary interactive workflow occurs in the terminal/TUI dashboard (`resume dashboard` / `resume run`).
- Multi-profile management (`profiles/<name>/`) supporting profile-specific JDs, bullet banks, credentials, and configuration.
- Local command-line execution and Syncthing peer-to-peer data synchronization across machines.
- Output artifacts generated as HTML and compiled to clean single- or multi-page PDFs in `output/<profile>/`.

## Capabilities and Constraints

### Capabilities
- Multi-source job description ingestion and tracker log management.
- Multi-dimensional role scoring assessing realistic interview probability.
- LLM-powered bullet selection, rewriting, and cover letter tailoring.
- Automated HTML-to-PDF rendering with strict page-budget enforcement.
- Rich TUI dashboard featuring interactive job management, live progress indicators, filtering, and reporting.

### Technical & Design Constraints
- PDF rendering uses Playwright pinned strictly to `1.61.1` (macOS 12 constraint).
- Existing HTML/CSS resume template structure and Playwright rendering pipeline must be strictly preserved.
- Profile-scoped data syncs via Syncthing (`profiles/`, `jds/`, `output/`, `data/`); repository code syncs via Git.
- Terminal/TUI interfaces must adhere to high-end TUI craft: gorgeous aesthetics, fluid animations, clear visual hierarchy, interactive dashboards, keyboard navigation, and clear status reporting.

## Brand Commitments

- CLI & TUI identity: Modern, powerful developer-grade tool aesthetic. Supports Nerd Fonts glyphs with fallbacks to standard Unicode symbols via `RESUME_BUILDER_ICONS`.
- Clean typography and professional styling in generated PDF resume artifacts.

## Evidence on Hand

- Core Python engine, Jinja HTML templates, and Playwright rendering scripts in codebase (`scripts/`, `resume-engine/`).
- Vendored Go Bubble Tea TUI dashboard (`dashboard/`).
- Permanent test fixture (`fixtures/sample_jd.txt`) for pipeline smoke testing (`resume sample`).

## Product Principles

1. **System That Learns & Grows**: Every tailored resume, bullet edit, and score refines the bullet bank and engine over time.
2. **Realistic Fit Scoring**: Evaluate true interview probability rather than superficial keyword density or general "role fit".
3. **Radically High-Quality Output**: Generate resumes that sound authentic, capturing the tiny nuances that elicit a "wow" response from recruiters and eliminating the need for manual post-editing.
4. **Free & Sovereign**: Built for job seekers who shouldn't be squeezed for subscription fees; the system operates locally and freely.
5. **Impeccable TUI Ergonomics**: Treat terminal interfaces with equal design rigor as modern web dashboards—stunning visuals, responsive navigation, micro-animations, and rich data views.
6. **Uncompromised PDF Quality**: Guarantee pixel-perfect, beautifully typeset PDFs adhering to strict page budgets.

## Accessibility & Inclusion

- TUI dashboard must support standard Unicode fallback mode (`RESUME_BUILDER_ICONS=unicode`) for terminals without Nerd Fonts.
- Rendered PDFs must be screen-reader accessible with structured semantic tags and high-contrast text layout.
