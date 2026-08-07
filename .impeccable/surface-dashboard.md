# Surface Brief: TUI Dashboard

**1. Job and audience**

- **Audience:** Job seekers actively managing a pipeline of potential roles across multiple industries.
- **Context:** They are opening the CLI to decide what to do next—either importing/scoring new jobs, verifying existing job liveness, or sitting down to tailor a high-quality resume for a top-scoring role.
- **Mode:** **Operate**. The user is here to make decisions and execute tasks (filter, review, trigger generation).

**2. Outcome and proof**

- **Primary Action:** Fluidly navigate an aggregated list of jobs, instantly understand *why* a job is a good fit, and execute the resume tailoring engine.
- **Success:** The user feels confident and focused. They know exactly which job gives them the best chance of an interview and can trigger the generation without friction.
- **Proof:** Displaying true interview probability scores, explicit reasoning for the score, matched skills (confidence booster!), missing skills, application status, and date of posting/scan (as applying early is critical).

**3. Selected direction**

- **Visual Authority:** "The Command Center Editor" (established in `DESIGN.md`).
- **Thesis:** A vibrant, Charm-powered (Bubble Tea, Lip Gloss, Huh) split-pane layout. It uses deep terminal backgrounds against high-contrast, tactile neons to create a focused, premium workspace.
- **Sequence:** Land on the main dashboard $\rightarrow$ Filter/Search jobs on the left $\rightarrow$ Review rich details/scores on the right $\rightarrow$ Trigger actions (Liveness Check, Tailor Resume, Update Status).

**4. Scope and boundaries**

- **In Scope:** The main unified dashboard view, list filtering, detail pane rendering, and action triggers.
- **Out of Scope:** The backend scraping mechanisms, the actual PDF rendering logic, and any web-based GUI.
- **Anti-goals:** Avoid dense, overwhelming data tables. Do not present a "wall of text." Keep the UI breathable with clear visual hierarchy.

**5. States and ranges**

- **Content:** The job list may range from 1 to 100+ active roles.
- **States:**
  - *Selection States:* Focused vs. Unfocused panels.
  - *Job States:* Saved, Scored, Tailoring, Applied, Rejected, Dead/Inactive (via liveness check).
  - *Data States:* Missing score (needs processing), missing skills, perfect match.

**6. Interaction and layout**

- **Topology:** Split-pane. Left sidebar (approx. 30% width) for navigating the job list. Right main area (70% width) for the detailed breakdown and action menus.
- **Affordances:** Keyboard-first navigation. Active panes are highlighted with vibrant borders (e.g., Electric Sky `#4dabf7`).
- **Transitions:** Instant pane switching. Use Charm's `bubbles/spinner` or progress bars for async actions like "Checking Liveness" or "Tailoring...".

**7. Constraints and open decisions**

- **Constraints:** Must render cleanly within standard terminal emulators. Relies on standard CLI interaction (no mouse assumed, though bubbletea supports it).
- **Tooling:** Built strictly using Go, Bubble Tea, Bubbles, and Lip Gloss.
