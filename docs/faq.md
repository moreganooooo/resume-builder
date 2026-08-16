# 💬 FAQ & Troubleshooting Guide

Here are answers to the most common questions, edge cases, and environment troubleshooting tips for the `resume-builder` system.

---

## 📊 1. Scoring: Fit Score vs. ATS Odds Score

### Q: What is the difference between my Fit Score and my ATS Odds Score?
A: Our system evaluates job postings from two completely independent directions:
1. **The Fit Score:** Measures your actual professional alignment against the job's core technical requirements, leadership scope, and domain context. It uses a **10-dimensional weighted rubric** to ask: *Is this a role where you would genuinely excel and be happy?*
2. **The ATS Odds Score:** Models the **probabilistic likelihood of your resume passing initial automated screening and HR filters**. It checks for formatting traps, page-count boundary violations, and target keyword density. It asks: *Will an automated system let your resume through to a human?*

### Q: What does it mean if my Fit Score is high but my Odds Score is low (or vice versa)?
* **High Fit / Low Odds:** You are perfectly qualified for the job, but your current resume text lacks the dense, specific terminology or keywords that automated screeners search for. **Solution:** Run the `tailor` module to inject the correct keyword mapping while preserving your voice.
* **Low Fit / High Odds:** You have matched all the keyword patterns perfectly, but your underlying professional level or stack depth doesn't align with the role's actual expectations (e.g., applying for a Haskell role when your background is strictly Python). **Solution:** Focus on roles where both scores align!

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
