# Fix-pass execution plan

Companion to `phase-9-backlog.md` (the source of truth for what each `B<n>`
item is and why). This file sequences the *remaining* items into batched
sessions and marks where to `/clear` between them.

**Why sessions are scoped this way:** each cluster groups items that touch
the same file(s) or the same call site, so the work happens in one pass
instead of re-opening a file across separate sessions. Between clusters,
nothing from the prior session's conversation is needed to do the next one
correctly — the fix description already lives in `phase-9-backlog.md`, and
each session's own completion writeup (same changelog style already used for
B13–B19) is what carries the "what actually happened" forward, not
conversation memory. **Clear before starting a new session in this list.**

**Tool-usage policy for every session** (carried over so it doesn't need
re-explaining each time): fix inline in the main chat, no separate plan doc
or subagent by default — the test suite is the spec and the review. Haiku
only for pure mechanical repetition across many files with an obvious
low-risk pattern. Opus only if actually stuck on a hard architectural call,
not preemptively. Run the test suite after each item; commit at the end of
each session; append a completion note to `phase-9-backlog.md`'s §3 in the
existing style before clearing.

---

## Session 1 — Critique/rubric core — ✅ DONE 2026-08-06

**Items, in order:** B24 (warm-up, trivial) → B49 → B50 → B51 → B52 → B53 →
B54 → B18.

**Outcome:** all 8 done. B52 turned out to already be resolved on inspection
(no code change needed — verified, not assumed). Everything else landed and
was verified live via a real `resume sample` run except B54, which touches
`resume polish`'s interactive path and has no existing test harness to
exercise it — reviewed and syntax-checked, not run end-to-end. Full detail
and the exact verification evidence is in `phase-9-backlog.md`'s
2026-08-06 changelog entry. Test suite: 1182 → 1187, all passing.

**Why batched:** B49→B50→B51 is a strict dependency chain in one region of
`orchestrator.py` (the critique call site) — B50 needs B49's attach point,
B51 needs B50's schema fields. B52–B54 are small edits to the same
`resume-engine/scoring/`/`rules/` files already open for B49. B18 sits right
next to the rubric plumbing this session builds, so it's cheaper to do while
that's the active context.

**Files:** `orchestrator.py` (critique/step-5 region), `resume-engine/scoring/*.yaml`,
`resume-engine/rules/style_rules.yaml`, `cv-template.html` +
`coverletter-template.html` (B24 only).

**Clear after this session.**

---

## Session 2 — Voice/summary quality + bullet-bank integrity

**Items, in order:** B28 → B29 → B30 → B20.

**Why batched:** B29's fix is "pass voice-anchors to the critique/apply
calls" — same orchestrator region Session 1 left off in, but a fresh session
can pick it up fine since the backlog doc already states the fix. B28 is a
two-line addition to `validate_resume.py`, the file B29 already touches. B30
follows directly from B29 (`build_voice_anchors.py` feeds the same voice
pipeline). B20 is unrelated by file but same goal (2) and similar size —
bundled here rather than given its own session.

**Files:** `validate_resume.py`, `orchestrator.py` (Step 5/5.5),
`build_voice_anchors.py`, `cluster_bullet_bank.py`, `embed_bullet_bank.py`.

**Clear after this session.**

---

## Session 3 — Board-scanner hygiene — ✅ DONE 2026-08-06

**Items, in order:** B26 → B27 → B36.

**Why batched:** all three fixes land inside the same provider-request loop.
B27's error-envelope and B36's missing-description fix are natural additions
once `_http.mjs` is open for B26's backoff/retry logic.

**Outcome:** all 3 done. B36 turned out bigger than "small" — two of its six
providers (SmartRecruiters, Workday) need a bounded per-posting detail fetch,
not just a field mapping; asked Morgan, she chose the full fix over deferring
it. That pulled `scripts/scan_ats.py` into scope too (not in the file list
below) since it's the only caller that actually reaches `websearch.mjs`
sequentially and the four ATS-only providers, and it already imports/reuses
`scan_boards.py`'s helpers by convention. Full detail, the per-provider
verification method, and exact test counts are in `phase-9-backlog.md`'s
2026-08-06 Session 3 changelog entry. Test suite: 1218 → 1231 (Python), plus
40 new `node:test` cases (this repo had none outside `workday.test.mjs`
before this session) — not verified against a live scan (no credentials/
tracked-company data in this checkout to exercise safely).

**Files:** `board-scanners/_http.mjs`, ~8 provider `.mjs` files,
`scan_boards.py` — plus `scan_ats.py` and `cli_art.py` (see Outcome above).

**Clear after this session.**

---

## Session 4 — Subprocess & scan sweep

**Items, in order:** B34 → B35 → B21 → B42 → B41.

**Why batched:** B34/B35 live inside `run_scan()` (cap/confirm gate and
in-memory dedup index are adjacent edits to the same loop). B21/B42 are both
in `liveness.py`'s subprocess handling. B41 (credential/env allowlist) is
last because it depends on both the board-scanner (Session 3) and liveness
subprocess call sites already being settled.

**Files:** `scan.py`, `jd_manager.py`, `liveness.py`.

**Clear after this session.**

---

## Session 5 — Stranger path + TUI polish

**Items, in order:** B31 → B32 → B33 → B22 → B23.

**Why batched:** B31–B33 are one coherent "what does a stranger see first"
pass (goal 3) across different files, cheaper to review together than
separately. B22/B23 are the same Rich table/palette code (goal 4) — bundled
into the same session since it's the last remaining polish tier.

**Files:** `cli.py`, `doctor.py`, `theme.py`, `bootstrap_menu.py`, `menu.py`,
Go theme file (`dashboard/internal/theme/resumebuilder.go`).

**Clear after this session.**

---

## Session 6 — Cleanup

**Items:** B40 (root-cause investigation, isolated) → B46 (modernization
grab-bag, mostly trivial independent edits).

**Files:** `bootstrap_profile.py` (B40), `gemini_client.py` call sites,
`theme.py` colorizers, `rewrite_bullets.py` docstring (B46).

No clear needed after — this is the last session in the backlog as it
stands today.

---

## If new items get added

Follow the same rule used throughout `phase-9-backlog.md`: check whether a
new item shares files with an existing cluster before giving it its own
session. Append it to this file in the matching session, or add a new
session at the end if it doesn't fit anywhere.
