# Implementation Plan: Resume-Writing Upgrade Suite

We will implement a premium upgrade suite that transforms the resume-writing and tailoring mechanisms from a simple instruction-based system into a **programmatically validated, self-correcting, and highly authentic pipeline.** This plan addresses all four core improvement vectors plus visual layout parsing security.

---

## 🛠️ Step-by-Step Task Breakdown

### 🎯 Task 1: The STAR/XYZ Syntactic Quality Grader
We will build a deterministic semantic parser in `scripts/validate_resume.py` that parses each achievement bullet to check for three critical components:
1.  **Strong Active Verb:** Confirms the bullet starts with a pre-approved, past-tense action verb (using a compiled local registry of ~250 high-impact active verbs).
2.  **Quantified Metric/Evidence:** Verifies the presence of percentages (`%`), currency (`$`), or numerical scales.
3.  **Result/Causal Connector:** Scans for outcome-indicating transition words (e.g., *resulting in, driving, to increase, to optimize, boosting, reducing, capturing*).

*   **Programmatic STAR Score Formula:**
    $$\text{Score} = 100 - (30 \text{ if no Verb}) - (40 \text{ if no Metric}) - (30 \text{ if no Result})$$
*   **Integration:** Add `check_bullet_star_quality()` to `validate_resume.validate()`. If any tailored bullet scores below $70$, it raises a blocking violation. The orchestrator's Hill-Climbing repair loop will automatically re-prompt the LLM to rewrite the bullet to be structurally flawless and impact-driven.

---

### 🎨 Task 2: Authenticity & Voice Calibration Metric
To eliminate sterile "AI voice" boilerplate and generic text, we will implement an authenticity linter in `scripts/validate_resume.py`:
1.  **Strict Boilerplate Check:** Raise violations for any phrase from an expanded "AI Cliché Checklist" (e.g., *results-oriented professional, passion for innovation, proven track record of, collaborating with cross-functional teams to drive*).
2.  **Verbatim Anchor Overlap:** Match stylistic traits against `voice-anchors.md` to flag overly corporate or passive phrasing.
3.  **Pronoun Enforcement:** Reinforce the strict no-pronouns-outside-Why-section constraint with clear actionable error messages.

---

### 📅 Task 3: The Proud Career Break Calibrator
Instead of relying on static KB entries or attempting to cover up employment gaps (which are red flags to ATS and human recruiters), we will build an automated timeline synthesizer in `scripts/orchestrator.py`:
1.  **Gap Analysis Engine:** Parse the candidate's historical work dates and identify any gap periods greater than 3 months using standard `MM/YYYY` formats.
2.  **Proud Entry Injection:** If a gap is identified (such as the 2024–2025 transition period), the orchestrator programmatically constructs a proud, active **"Career Break — Professional Development & Retraining"** entry in standard reverse-chronological order.
3.  **Active Skill Synthesis:** Populate the break's achievements with Morgan's actual upskilling milestones:
    *   *Completed comprehensive certifications in Google Data Analytics and Advanced Lifecycle Marketing Automation.*
    *   *Designed and deployed personal database operations and campaign flow automation projects using Python and SQL.*
    *   *Managed household operational budgets and timeline logistics with high efficiency.*
4.  **Standard Dates:** Format the dates as standard, ATS-optimized strings (e.g., `08/2024 - 02/2025`) to bypass parsing hurdles.

---

### 🔄 Task 4: Transferable Skills Translation Matrix
We will enhance `resume-engine/prompts/tailor_resume.md` with a structured **Transferable Skills Translation Matrix**. This provides the LLM with direct reframing rules to map past historical roles to the exact, sophisticated vocabulary of target marketing archetypes:
*   *Blog/article copy* $\rightarrow$ *Campaign narrative design & conversion copy*
*   *Classroom instruction* $\rightarrow$ *Cross-functional content enablement & training infrastructure*
*   *Administrative tracking* $\rightarrow$ *Process design, CRM hygiene, & funnel optimization*

This ensures high-impact description of past experiences without ever exaggerating or fabricating raw metrics.

---

### 🖥️ Task 5: Single-Column Layout & Rendering Audit
We will audit `scripts/render_html.py` and styling assets:
1.  **Zero-Table Enforcement:** Verify that the rendered HTML does not use complex CSS grids, flexboxes with severe nested offsets, or raw HTML tables for core text columns, keeping Workday and Greenhouse parser accuracy at $95\% - 98\%$.
2.  **Typography Normalization:** Enforce clean, system-standard, easily extractable typefaces (e.g., DM Sans, Arial, Calibri, Times New Roman).
3.  **ATS Validator:** Create a script/check inside `scripts/validate_pdf_text.py` that does a mock parse of the output PDF to verify that the extracted text flow is perfectly sequential and free of fragmentation.

---

## 📈 Verification & Robustness Plan

To ensure our upgraded system is 100% stable, backwards-compatible, and mathematically correct, we will write **comprehensive unit tests** under `tests/`:
1.  `tests/test_star_quality_grader.py`: Validates that bullets with varying STAR structures are graded accurately and weak bullets are correctly caught.
2.  `tests/test_career_break_calibrator.py`: Asserts that timelines with gaps are programmatically enriched with confident Career Break entries while continuous timelines are left untouched.
3.  `tests/test_voice_calibration.py`: Verifies that AI clichés are successfully detected and blocked.

---

## 🚀 Execution Order

We will execute this plan sequentially to maintain 100% green tests at every milestone:
1.  **Phase 1:** Implement the pre-approved action verb database and STAR quality grading functions in `scripts/validate_resume.py`.
2.  **Phase 2:** Integrate voice authenticity checks and AI cliché filters.
3.  **Phase 3:** Write the automated timeline gap detector and proud Career Break injector in `scripts/orchestrator.py`.
4.  **Phase 4:** Update the `tailor_resume.md` prompt context with the Transferable Skills Translation Matrix.
5.  **Phase 5:** Audit and solidify the rendering and PDF text parser pipelines, and run the complete test suite.
