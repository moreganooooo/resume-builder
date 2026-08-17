# 🧠 UX Deep-Dive: Designing for "Dom" (The ADHD Persona)

This document maps a professional, high-fidelity UX and product design critique of the `resume-builder` platform. It evaluates the user journey specifically through the lens of **"Dom" (the hyper-focused, tech-savvy job seeker who refuses to read READMEs and demands immediate value/dopamine feedback loops)**.

---

## 🗺️ 1. Dom's Friction Points & In-App Explanations

For a new user with zero context, standard developer jargon is a massive cognitive barrier. If Dom gets confused, he gets bored; if he gets bored, he closes the terminal.

We analyzed where Dom gets lost and how the system now speaks his language directly inside the interface:

| Term / concept | Where Dom Gets Confused | What We Did (In-App Fixes & Explanations) |
| :--- | :--- | :--- |
| **"Bullet Bank"** | Expects to edit a `.pdf` or Word document directly. Has no idea what a "bank" is or why he is triaging bullets. | Created a highly visible TUI Tip: *"Think of your Bullet Bank as an active, living inventory of all your achievements. Rather than editing files directly, you curate bullets, and the AI automatically selects and fits the best ones to match each job description!"* |
| **"Express Setup (Auto-pilot)"** | Doesn't know what files to provide or where they go. Fears a complex, 10-step setup. | Placed an onboarding-focused Tip explaining: *"Need to import your career history? Just drop your existing resume (.pdf, .docx) or LinkedIn text export directly into source_documents/ — our Express Auto-pilot will parse it automatically!"* |
| **"AI Voice Cloning"** | Assumes the AI will write dry, generic, robotic text that doesn't sound like him. | Created a dedicated explanation tip: *"Want the AI to sound like you? Feed your past cover letters, personal bios, or emails into source_documents/ — our parser automatically clones your authentic tone and writing style!"* |
| **Customizing Job Search** | Doesn't know how the app decides what JDs to scan or how to tweak them without editing source code. | Standardized the explanation: *"Customize your active search titles and board filters directly inside profiles/<name>/search_queries.json in your editor or in-app."* |

---

## 🚪 2. What Does Dom Have to Leave the App to Do?

To ensure zero friction, we must explicitly map out what actions require leaving the TUI, how the app mitigates this, and where further bridging is needed:

1. **Gemini API Keys & Env Config**
   * *The Friction:* Grabbing an API key from Google AI Studio.
   * *Mitigation:* The **Self-Healing Doctor** automatically detects a missing key, prompts the user interactively inside the terminal, and writes/appends it directly to their profile's private `.env` file—meaning Dom never has to open an editor.
2. **LinkedIn & JobRight Cookies**
   * *The Friction:* Getting session cookies can be a nightmare (opening DevTools, copying raw header strings).
   * *Mitigation:* The system includes automatic browser scanner modules. If Dom logs into LinkedIn or JobRight in Google Chrome, macOS handles the cookie extraction automatically. We added a Tip to reassure him: *"No manual copy-pasting required! Just log into LinkedIn or JobRight in Chrome, and our scanner pulls the active session cookie directly."*
3. **Reviewing the PDF Layout**
   * *The Friction:* Generating a resume and having to dig through directories to find and open the output PDF.
   * *Mitigation:* We injected a contextual `↗ View Generated PDF` option directly into the **Next Steps** screen. When Dom tailors a document, a single keystroke automatically launches his system's default PDF viewer (Acrobat, Preview, etc.) to show him his gorgeous new resume instantly.
4. **Submitting the Application**
   * *The Friction:* Submitting the tailored resume to the job board.
   * *The Reality:* Fully automated "one-click applying" is extremely brittle and easily flagged by ATS platforms. Dom must upload the PDF himself on the hiring site.
   * *Bridging:* The application tracker logs the URL, letting him jump straight to the submission portal.

---

## 🎨 3. Fixed: Alt-Screen Threshold & Hidden Footers

> **The Issue:** The footer commands (navigation keys, exit shortcuts) and menu options were getting hidden or scrolled off-screen on standard laptop windows.

### The Diagnostic Finding
We discovered that alternate screen (fullscreen) mode was gated behind a strict terminal height check:
```python
# Old threshold
return rows >= 35
```
A standard terminal window or split panel (like the VS Code terminal) is often **24 to 30 rows tall**. If the height was under 35, the app fell back to scrolling inline mode, pushing the gorgeous banners and footers into the terminal scrollback buffer where they became invisible.

### The Implementation
1. **Lowered the Threshold:** We updated `_should_use_alt_screen` to `rows >= 24`. At 24 rows, the entire menu, banner, and footer fit perfectly on-screen. Alt-screen fullscreen mode is now activated by default on almost all terminal configurations.
2. **Clean-Slate Transitions:** We updated `offer_next_steps()` to clear the terminal screen (`\x1b[2J\x1b[H`) and print a clean compact header and the footer commands. This completely wipes away the clutter of build logs, rendering a pristine, stable viewport for the user to make their next selection.
3. **Scoping Bug Fixed:** We removed local, redundant `import sys` statements inside the view handler to eliminate an `UnboundLocalError` scoping bug that was caught by the unit tests.

---

## ⚡ 4. Keeping Dom Motivated: The Dopamine Engine

Job hunting is exhausting and demoralizing. To give Dom the high-energy boost he needs, we built a **Celebratory Dopamine Engine** that fires whenever he hits a key milestone:

```
🌟 ACHIEVEMENT UNLOCKED 🌟
🎉 ✦ ─── HECK YEAH! ─── ✦ 🎉

RESUME CUSTOMIZED & POLISHED!

All your achievement bullets have been dynamically rewritten and adapted for this specific role.

💡 Remember: Every tailored resume brings you one step closer to your dream gig!
Go crush this application! 🚀
```

Whenever Dom finishes an auto-pilot setup, tailors a resume, or completes a cover letter, this high-fidelity double-bordered card flashes on his screen alongside the option to instantly view his newly minted PDF. It transforms a standard CLI utility into a gamified career dashboard.

---

## 🎯 5. Product Strategy: Does This Cover Everything?

Apart from cold-emailing hiring managers on LinkedIn, **this application is remarkably complete**. It covers:
* 📡 **Discovery:** Board crawling and keyword-focused scanning.
* 📊 **Triage:** Scoring and multi-dimensional fit evaluations.
* ✍️ **Generation:** Dynamic Bullet Bank assembly, ATS keyword matching, and PDF compilation.
* 📂 **Tracking:** Funnel status and post-tailoring status sweeps.

### What Could Make It Complete? (Future Roadmap)
To make this the *ultimate* self-contained job search weapon, we could expand into these two high-dopamine modules:
1. **Networking Outreach Drafts:** An option to automatically draft custom LinkedIn cold-outreach templates or email follow-ups for the specific job description and hiring manager.
2. **AI Mock Interview Simulator:** A mode that takes the tailored resume and the job description, drafts 3 highly targeted interview questions, and lets the user practice their answers directly in the terminal!

---

> [!TIP]
> **Actionable Tip for Dom:** Don't waste time formatting! Use the *Express Setup* with your LinkedIn profile, let the auto-pilot build your Bullet Bank, and then run *Job Search Scanner* to let the crawl do the work. Just look for the 🎉 success cards!
