# 💬 FAQ & Troubleshooting Guide

Here are answers to the most common questions, edge cases, and environment troubleshooting tips for the `resume-builder` system.

---

## 📊 1. The Re-Engineered Dual Scoring System (Fit vs. Interview Odds)

### Q: What is the difference between my Capability Fit and my Interview/Hiring Odds?
A: To prevent cognitive model saturation and score compression, our system utilizes a state-of-the-art **Split-Agent Pipeline** evaluating job postings across two dedicated, isolated LLM stages:
1.  **Capability & Functional Fit (Stage 1)**: Measures your actual career experience alignment, target role overlap, and tools/process overlap against the JD. It returns a structured **CoBlack-Style Capability Gaps list** highlighting precisely where your narrative or experience falls short of the JD's core needs.
2.  **Recruiter Perception & Hiring Odds (Stage 2)**: Models the psychological friction an automated filter or a human recruiter will face. It checks title continuity, domain credibility, and **Chronological Resume Gaps** (using empathy-aware criteria based on company profile rigidity), and extracts explicit **Ghost Job Red Flags**.

### Q: What is the Piecewise Interview Probability Scale?
A: It is a mathematical converter that translates your qualitative 1-5 `interview_odds_score` into a literal **Absolute Interview Probability Percentage** using baseline response rates ($P_{\text{baseline}} = 2.0\%$) and piecewise-interpolated Odds Ratios:
*   An elite score ($4.5+$) calculates as a **$20\text{x}$ response rate multiplier** (translating to a $\sim 29.0\%$ absolute response rate).
*   A strong score ($4.0+$) calculates as an **$8\text{x}$ multiplier** (translating to $\sim 14.5\%$).
*   This removes abstract scoring bias and grounds your job-hunt pipeline in empirical, statistics-based probability.

### Q: How do Profile-Driven Overrides and Deal-Breakers work?
A: If you enable `location.remote_required` in your profile configuration (`profile.yml`), any job description evaluated with onsite or hybrid language (resulting in `remote_quality < 5` or triggered `hard_blockers`) is immediately caught by a Python post-processor. 
*   The system overrides the composite score to a flat **`0.00`** and recommendation to **`Skip`**.
*   The job is **automatically archived** out of your pending queue, keeping your search hyper-focused. This framework is fully generic and works for any user's profile deal-breakers!


---

## 🧠 2. Feeding the Compounding Knowledge System

### Q: How do I feed the program more custom Knowledge Docs, and what formats are supported?
A: Drop your historic files (old resumes, cover letters, portfolios, course transcripts, project briefs, or recommendation letters) directly into your active profile's data folder:
`profiles/<profile_name>/data/` or `data/<profile_name>/`.
* **Supported Formats:** `.txt`, `.pdf`, `.docx`, `.md`, and `.csv`.
* **How it processes:** The program automatically parses, clean-extracts, and indexes these documents during your next build. This builds a rich, contextual semantic map of your career milestones, giving the LLM a deeper reservoir of true, verified facts to draw from.

### Q: How does the Bullet Bank compound over time?
A: Whenever you run a tailoring build, the AI will suggest polished, high-impact phrasings of your achievements to align with the job posting. 
* If you approve a build, the program takes those polished, tailored sentences and writes them directly back to your "Keepers" database (`profiles/<profile>/bullet-bank-keepers-audited.csv`) as approved, reusable achievements.
* Your bullet bank is never static—it compounds and grows sharper with every single application!

---

## 🗣️ 3. Writing Voice Cloning & Company Research

### Q: How does the AI capture and clone my writing voice?
A: When you bootstrap a profile, the system reads your raw historical resume and extracts your unique sentence structures, vocabulary density, and syntax. It maps this on a style matrix to create your **Active Voice Profile**.
* **Voice Protection:** After every tailoring build, a **Holistic Critique Pass** audits the output. It categorizes sentences into *Distinctive Sections* (sound unmistakably like you) and *Flat Sections* (competent but generic).
* The AI optimizer is **explicitly forbidden** from editing your Distinctive Sections, ensuring that your authentic human personality is never sanded away into generic AI-beige text.

### Q: How does the background Company Research work?
A: If a job description contains a corporate homepage URL, a background web scraper immediately sweeps their primary About, Mission, Values, and Product pages. 
* It extracts their exact corporate culture and registers.
* It dynamically adjusts your Resume Summary and Cover Letter opening paragraphs to match their tone (e.g., warmer and values-driven for mission-centric teams; sharper, technical, and metrics-focused for fast-paced B2B software companies).

---

## 🧹 4. Liveness & Staleness sweeps

### Q: How do I run a Liveness Sweep to clean out stale listings?
A: Run **`resume liveness`** from your terminal, or select the liveness option in the main TUI menu.
* **The Sweep:** The program runs non-blocking, asynchronous HTTP requests to check if each job post’s URL is still live.
* **Pruning:** If a link returns a `404 Not Found`, redirects to a generic expired page, or has been closed, the program automatically moves the listing to `jds/<profile>/expired/` and prunes it from your active triage lists, keeping your pipeline 100% active.

---

## 🎮 5. Gamification & Success Celebrations

### Q: What happens when the TUI detects a completed milestone?
A: To deliver an immediate hit of career dopamine and keep you motivated, completing major milestones (like scanning your 50th job or submitting your 10th application) triggers a visual **twinkling celebration sequence** inside your terminal.
* Custom double-buffered terminal ticks (`\x1b[2J\x1b[H`) render a dynamic frame-by-frame animation of twinkling stars, sparkles, and achievement graphics in vibrant TrueColor gradients.
* This sequence runs in a secure sandbox. Even if you cancel mid-animation (`CTRL+C`), a robust `finally` block instantly restores your cursor and terminal shell cleanly.

---

## 🍪 6. Session Cookies & Playwright Troubles

### Q: How do I handle LinkedIn & JobRight Session Cookies?
* **LinkedIn:** Automated! When running `resume scan --source linkedin`, if your session is expired, a secure visual browser opens for you to log in. Once authenticated, the script automatically captures the `li_at` session cookie, saves it to `profiles/<profile>/.linkedin_cookie`, and closes the browser.
* **JobRight:** If your JobRight scans fail with auth errors, copy your raw cookie header string from your browser's Developer Tools (Network tab -> Copy as cURL) and paste it into your `profiles/<profile>/.env` file under `JOBRIGHT_COOKIE_STRING`.

### Q: Playwright fails on macOS 12 (Monterey)
* **The Reason:** Playwright version `1.62.0` and above dropped support for macOS 12.
* **The Fix:** Our `package.json` pins Playwright strictly to version **`1.61.1`** (the final release supporting macOS 12, compiling Chromium revision `1228`). If your packages are corrupted, run a clean reinstall:
  ```bash
  rm -rf node_modules package-lock.json && npm install && npx playwright install chromium
  ```

---

## 💎 7. Premium AI Tailoring & Modern CLI Tools

### Q: How does the new Interactive Profile Skills Screen work?
A: It is accessible directly from your terminal under `Settings & Upkeep -> View & Manage Profile Skills`. It displays an elegant, categorised TUI dashboard of your verified skills stored in `verified_tools.json`. You can view comprehensive usage details, add new skills with autocomplete suggestions, edit confidence meters, and delete entries entirely from your keyboard without manual JSON edits.

### Q: What are Go-Precompiled Charmbracelet Prompts?
A: To provide an extremely responsive keyboard feel, confirmations, selections, and checkboxes are globally handled by a compiled Go binary from Charmbracelet's `huh` prompt ecosystem. The program automatically compiles this binary under `dashboard/bin/prompt` upon its first launch. Subsequent keyboard actions react instantly in **less than 1 millisecond** with premium styling and smooth animations.

### Q: Why does the system automatically rewrite Cover Letter openings?
A: Standard "AI-beige" cover letter templates often start with passive, flat phrases (*"My name is..."*, *"I am writing to express my interest in..."*). Our system strictly bans these clichéd openings in favor of captivating, values-grounded narrative hooks. A post-generation linter automatically scans the text; if a cliché is found, it triggers a self-corrective rewrite loop to produce a compelling 12/10 hook.

### Q: What is the "Ligature Trap" in PDF resume rendering?
A: When rendering HTML templates to PDFs, Chromium often combines characters like `fi`, `fl`, or `ff` into single Unicode ligature symbols (`ﬁ`, `ﬂ`). While this looks beautiful on paper, standard Applicant Tracking Systems (ATS) can fail to parse or index these ligatures correctly, filtering your resume out. Our system programmatically inspects the raw text layer of the final PDF output to assert that all targeted job keywords survived the rendering layer perfectly intact.

### Q: How does the embedded SQLite database (`data.db`) work?
A: Every active profile stores job descriptions, application pipeline states, and bullet bank achievements inside an embedded ACID SQLite database located at `profiles/<profile>/data.db`. Handled via `scripts/db.py`, SQLite eliminates flat-file synchronization locks and JSON corruption, allowing lightning-fast query filtering and transaction-safe concurrency across TUI sessions.

### Q: What is the Typst Vector PDF Renderer?
A: Typst is a modern, high-performance document markup and compilation system. Implemented in `scripts/render_typst.py`, the Typst renderer generates structured `.typ` document markup and compiles vector PDFs in sub-second time directly from CLI without invoking headless Chromium browsers. Both Typst and Chromium rendering engines are fully supported.
