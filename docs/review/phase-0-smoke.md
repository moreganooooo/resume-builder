# Phase 0 — Cold-boot smoke run

Model: Sonnet 5. Date: 2026-08-05. Profile used throughout: `morgan` (real,
fully-configured profile — 1144 pending JDs, 628-bullet bank, 0 resumes
customized this session prior to the `resume sample` run below).

Per the plan: no source read for diagnosis. Each entry is what I did, what
happened, what should have happened. No fixes applied.

---

## 1. `resume doctor`

**Did:** ran `resume doctor` cold.

**Happened:**
- Before any doctor output appears, every single `resume` invocation (this
  one included) prints `resume:1: command not found: _resume_ensure_profile`
  to stderr. Reproduced on every subsequent invocation all session (doctor,
  dashboard, menu — dozens of runs, 100% reproducible).
- Doctor's own checks passed (Python 3.13.14, `.venv/` ready, all pip
  packages installed, Node found, Chromium found, Go found, `GEMINI_API_KEY`
  set, fonts present, signature image found, KB allowlist files present),
  test suite: 1091 tests, OK.
- One flagged problem: "Playwright npm package: `node_modules/playwright`
  not found" — even though "Playwright Chromium browser" was found on the
  same run, and `resume sample` (below) rendered two PDFs successfully via
  that same Playwright/Chromium path minutes later in the same environment.

**Should have happened:** No shell error before the tool has done anything.
And if PDF generation actually works end-to-end without `node_modules/
playwright` present, the doctor check is flagging a false problem (or isn't
checking the thing that actually matters for PDF generation to work).

**Severity:** minor (shell error, cosmetic/trust issue) + minor (misleading
doctor signal). **Goal:** 1 (runs clean).

> **CORRECTED by Phases 1 and 4, ratified in `phase-9-backlog.md` §C2–C3.**
> Both claims in this section are wrong, and a later reader should not act on
> them as written:
>
> - **`_resume_ensure_profile: command not found` is not a product defect.** It
>   is a Claude Code shell-snapshot artifact — the snapshot captures `resume ()`
>   but filters out underscore-prefixed functions, so the review harness had the
>   caller without the callee. A real terminal sourcing `~/.zshrc` has both.
>   (`phase-1-onboarding.md`, "Corrections to Phase 0".)
> - **The Playwright doctor warning is not a false positive.** `node_modules/`
>   does not exist in this repo at all; rendering works only because Node
>   resolution walks up to a stray `~/node_modules` install (at version 1.60.0,
>   which does not satisfy the declared `^1.61.1`). Doctor was correct and, if
>   anything, understates the problem. (`phase-4-reliability.md` Finding 1 —
>   now backlog item **B15**, a blocker.)

---

## 2. `resume sample`

**Did:** ran `resume sample` end-to-end (fixture JD → resume + cover letter
PDF).

**Happened:** Completed successfully, exit clean, both PDFs generated
(2 pages / 58.4 KB resume, 1 page / 76.3 KB cover letter). Along the way:

- **a.** A raw, unlabeled library warning appeared mid-stream, interleaved
  with the validator's own output text with no surrounding blank line or
  attribution: `Could not get FontBBox from font descriptor because None
  cannot be parsed as 4 floats` (printed twice in a row).
- **b.** During "Step 5.5: Applying actionable recommendations one at a
  time," every one of the 3 recommendation-application attempts (including
  the one that was ultimately skipped) printed two warnings before
  proceeding: `WARNING: unrecognized KU achievement key '', falling back to
  first option.` and `WARNING: unrecognized KCKCC achievement key '',
  falling back to first option.` — an empty-string key, every time,
  regardless of which recommendation was being applied.
- **c.** The validator needed 2 of its 4 allowed attempts to get the JSON
  content past its own checks (forbidden phrase "proven track record,"
  duplicate opening verb "built," 3 skills-line width violations on attempt
  1; a bullet-length violation and 2 more skills-line width violations on
  attempt 2). The log jumps straight from attempt 2's issue list to "Step 5:
  Running holistic resume critique" with no "0 issues, passed" message in
  between — whether attempt 2's remaining issues were actually fixed, or the
  pipeline just moved on after using its budget, isn't visible from the
  output.
- **d.** After PDF generation, the pipeline's own post-render text-layer
  check flagged 5 mismatches — content the validator had approved in the
  JSON that then could not be found "intact" in the actual rendered PDF's
  text layer (1 bullet, 4 skills lines). The pipeline reported this and
  shipped the PDF anyway ("Pipeline complete!").

**Should have happened:** (a) a labeled/attributed warning, not a bare
library string interleaved with unrelated output. (b) an achievement key
that resolves correctly, or at minimum doesn't warn on every single
application regardless of which recommendation is being applied. (c) an
explicit "validator passed" or "validator gave up after N attempts, shipping
with remaining issues" message — not silence. (d) unclear what should happen
here without diagnosis, but a pipeline that self-detects likely ATS-parsing
mismatches and ships anyway without a decision (accept, flag prominently, or
retry) is worth Phase 3/4's attention — this is exactly what goal 2's
fabrication/accuracy question and the PDF text-layer check exist to catch.

**Severity:** (a) minor, (b) minor, (c) minor (no diagnosis, just an
information gap), (d) major (goes to output quality / ATS-parseability, the
thing goal 2 cares about most). **Goal:** 1 and 2.

---

## 3. Interactive menu — all 15 top-level branches

**Did:** drove `resume` (the real interactive menu, `scripts/menu.py`) via
piped keystrokes, entering all 15 top-level items one at a time (profile
selector defaults to `morgan`), capturing the first screen of each, then
backing out before confirming any destructive/paid action.

**Happened, no defects (branches behaved correctly):**
- New User? Start Here! → shows a real onboarding-stage progress table for
  the already-set-up `morgan` profile (stages 0–6, mostly "Up to date," one
  "In progress").
- Curate Bullet Bank → same-style progress table + a full "Bullet Bank
  Management" submenu (Audit / Cluster / Rewrite / Re-Audit / Score Hidden
  Gems / Embed, plus an "Ongoing Maintenance" section).
- Scan for New Jobs → correctly stops at a "Which source(s)?" picker (All /
  JobRight / LinkedIn / public boards / direct-to-ATS) before doing
  anything — never fired a real scan.
- Evaluate Pending Roles → correctly gated behind `About to evaluate 1
  pending JD(s) -- one real Gemini call each. Continue? [y/N]:` before
  spending anything.
- Customize Resume for Specific Role(s) / Batch → both correctly show the
  paginated JD picker (batch) or go straight to a `Continue? [y/N]` gate
  quoting the real count (1144) before any Gemini call.
- Write Cover Letter for Specific Role(s) → correctly reports `Nothing to
  browse -- no Completed JDs yet` (accurate: 0 resumes customized for real
  roles this session) rather than erroring.
- Polish a Resume or Cover Letter with Gemini → correctly lists the 2 real
  documents `resume sample` had just generated, with a working "Back to Main
  Menu" option in the same list.
- Browse & Manage Jobs → correctly loads and paginates the real 1144-JD
  queue with live scores ("Page 1/23 -- rows 1-50 of 1143 evaluated JD(s)").
- Career Dashboard (in-menu) and `resume dashboard` (the separate Go
  binary) both independently show the same correct, well-formatted empty
  state (`No applications logged yet for this profile ... log at least one
  application status via "Browse & Manage Jobs" first`) — consistent
  between the two entry points.
- Maintenance → submenu (Run Doctor Checks / Generate Sample QA / Check for
  GitHub Updates / Back) renders correctly; selecting **Back** returns
  cleanly to the main menu (only back-navigation path tested).
- Help, Exit → both render correctly; Exit prints `No actions taken this
  session.`

**Happened, real defects:**

- **Drop New Knowledge** immediately says: `This profile hasn't been set up
  yet -- use "New User? Start Here!" first.` This is the `morgan` profile —
  the same profile that, one menu item earlier, showed a fully-populated
  onboarding progress table and a 628-bullet bank, and that has 1144 tracked
  JDs. **Should have happened:** an already-set-up profile should not be
  told it isn't set up. **Severity: major** (a working feature is fully
  inaccessible to an existing real user). **Goal:** 1, 3.

- **Browse & Manage Jobs**, when the JD picker is confirmed with 0 items
  selected (pressing Enter immediately without selecting anything), silently
  returns straight to the main menu with **no feedback at all** — no
  "nothing selected," no confirmation of what (if anything) happened.
  **Should have happened:** some acknowledgment that the empty confirm was
  received and nothing was done. **Severity: minor.** **Goal:** 3.

- The animated ASCII-art banner + rotating tip box takes roughly **20–25+
  seconds** of wall-clock time to reach the interactive main menu when run
  in a real terminal (verified via a real PTY) — versus reaching the same
  screen in under 8 seconds when stdin isn't a TTY (the animation appears to
  be skipped in that case). A real user pays the ~20s cost on every single
  launch. **Should have happened:** unclear without diagnosis whether this
  is intentional branding or an unaddressed cost; flagged as a data point.
  **Severity: minor-to-major depending on intent** (Phase 1/2 territory —
  see Handoffs). **Goal:** 3.

- In the paginated Browse & Manage Jobs list, several company/role names
  are visibly cut off mid-word (e.g. "Manager, Customer Succe", "Encyclopaedia
  Britannica, Inc. | Marketing A"). **Caveat:** this capture ran without a
  real TTY width, so the app may have defaulted to an assumed column count
  rather than reflecting a real terminal's width — **not confirmed as a
  real bug**, flagged for Phase 2 to verify in an actual terminal window.

---

## 4. Edge cases

- **Back-navigation:** Maintenance → Back returns cleanly to the main menu,
  fully re-rendered, no defect observed (only this one back-path was
  tested; the plan's "every next-steps path" is broader than Phase 0's time
  budget covered — see Handoffs).

- **Empty input** (confirm a picker with 0 selections): see Browse & Manage
  Jobs finding above.

- **Ctrl-C mid-run:** interrupted `resume sample` ~20s in, mid-bullet-audit,
  via SIGINT to the process group. Clean exit, no traceback, no orphaned
  process, no corrupted state — confirmed no stray `orchestrator.py`
  process survived. Re-running `resume sample` afterward is safe (it always
  clears its checkpoint and does a full fresh build per its own design).
  **No defect.**

- **Invalid menu selection:** not meaningfully testable non-interactively —
  arrow-key list menus structurally prevent selecting an out-of-range
  option, so there's no equivalent of "type an invalid number" to trigger.
  No free-text prompt was reached in this session's coverage that would
  accept truly invalid input without risking a real, hard-to-reverse
  mutation (e.g., creating a stray new profile) — not tested, flagged as
  incomplete coverage.

- **Malformed JD file:** ran `python scripts/orchestrator.py <path>` in
  single-file mode against a file containing `this is not valid JSON or a
  real job description at all {{{ broken`. **Happened:** the pipeline did
  **not** reject or flag the content upfront — it proceeded directly into
  the full, real, paid bullet-bank audit pipeline (GEM-scoring and
  rewriting real bullets against the Gemini/Gemma APIs) exactly as it would
  for a legitimate JD. I stopped the run partway through (6 of 30 bullets
  audited) to avoid further unnecessary API spend once the point was
  clear — the run had not yet reached the JD-specific "Building resume"
  step, so whether *that* step would have failed on the garbage content
  wasn't observed. Process terminated cleanly, no orphan. **Should have
  happened:** unclear without diagnosis, but a JD file with no discernible
  job-description content committing real API cost before any content
  sanity check runs is worth Phase 4's attention. **Severity: major**
  (cost/reliability risk on a common real mistake — pointing the tool at
  the wrong file). **Goal:** 1.

---

## 5. `resume dashboard` (Go binary)

**Did:** ran `resume dashboard` (the Bubble Tea TUI) directly, and also via
`go run .` from inside `dashboard/` directly (bypassing the wrapper).

**Happened:**
- Via the wrapper (`resume dashboard`): resolves the `morgan` profile
  correctly, shows a clean bordered empty-state message when
  `data/morgan/applications.md` doesn't exist yet. No crash. (Also prints
  the same `_resume_ensure_profile` shell error noted in §1.)
- Run directly from `dashboard/` via `go run .` (no wrapper): fails with
  `Error: could not find applications.md in . or ./data/` and exits 1. This
  is expected given the wrapper is what supplies the correct profile-scoped
  path — not a defect in the product's real entry point, just confirms the
  wrapper is load-bearing for this to work at all.

**No defect** in the actual product entry point.

---

## Process-safety note (not a product defect, but worth recording)

While interrupting several menu branches during this session, one spawned
child process (`node .../scripts/check-liveness.mjs`, from entering "Check
Job Posting Liveness") was observed to **keep running as an orphan** after
its parent `resume` process was killed with SIGINT/SIGKILL sent to the
parent's own PID — it only stopped when explicitly killed by PID directly.
No data corruption resulted (it appears to have simply finished its own
work and then sat idle), but this means an interrupted "Check Job Posting
Liveness" run in real usage may keep making outbound network requests after
a user believes they've cancelled it.

## Handoffs

- **Phase 1:** "New User? Start Here!" and "Curate Bullet Bank" both render
  a fully-populated real-progress table for the already-onboarded `morgan`
  profile — worth checking what a genuinely brand-new profile's first-run
  experience looks like (this session never tested a true `I'm new here`
  path, to avoid creating a stray profile).
- **Phase 2:** verify the Browse & Manage Jobs column-truncation issue
  (§3) against a real terminal width — this session's capture had no real
  TTY and may be a capture artifact, not a real bug.
- **Phase 2/3:** the ~20–25s animated banner on every real-terminal launch
  (§3) — is this intentional brand polish or unaddressed cost? Worth a
  design judgment call.
- **Phase 3:** the PDF text-layer check flagging 5 real mismatches and
  shipping anyway (§2d) goes directly to goal 2 (ATS-parseable output) —
  highest-value item in this whole report for that phase to trace.
- **Phase 4:** the `_resume_ensure_profile` shell error on every invocation
  (§1); the Playwright doctor false-positive (§1); the empty-string
  achievement-key warning (§2b); the malformed-JD-file cost/reliability gap
  (§4); the orphaned child-process-on-interrupt behavior (process-safety
  note above). None of these were traced to file:line — Phase 0 read no
  source.
- **Phase 4 (bug, not just architecture):** "Drop New Knowledge" incorrectly
  gating an already-set-up profile (§3) is the single highest-severity
  finding in this report — a real feature that a real, fully-configured
  user cannot currently use at all.
