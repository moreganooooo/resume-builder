# Kickoff brief: orchestrator.py / rewrite_bullets.py polish pass

**For a fresh thread.** This is a handoff brief, not a design spec — read this,
then invoke `superpowers:brainstorming` to scope the work before writing an
actual spec/plan. Branch: `feature/tui-dashboard` (already checked out, work
in place, no worktree needed).

## Where this fits

Part of the ongoing "Crush IDE"-level terminal polish initiative across the
resume-builder CLI. Four areas were identified; this is the one still
remaining after the other three:

1. **Job scan scripts** — DONE (scan.py + all scan_*.py sources unified on
   `cli_art`/`ScanActivity`).
2. **Bullet-bank family + other workflows** — DONE (11 scripts routed through
   themed helpers, plus a `rich.markup.escape()` safety fix at the
   `cli_art.py` message-helper boundary — see
   `docs/superpowers/specs/2026-08-12-bullet-bank-family-progress-consistency-design.md`
   and its paired plan for the established pattern).
3. **Bootstrap/new-user flow** — separate brief, see
   `2026-08-13-bootstrap-new-user-flow-brief.md`.
4. **orchestrator.py / rewrite_bullets.py polish** — **this brief.**

This area was explicitly assessed early on as the most mature surface in the
repo — "close to shine already — likely need polish, not a rebuild," not a
redesign. Treat it as an audit/sweep pass using the pattern already proven on
the bullet-bank family, not a new design problem.

## Current state (measured 2026-08-13)

| File | Lines | `cli_art.*` refs | `console.print` calls | of which `markup=False` |
|---|---|---|---|---|
| `scripts/orchestrator.py` | 3946 | 237 | 183 | 111 |
| `scripts/rewrite_bullets.py` | 1584 | 66 | 65 | 11 |

Both already use themed Gemini-call spinners:
`cli_art.console.status("Calling Gemini...", spinner="dots")` — 3 call sites
in `orchestrator.py` (~lines 2902, 3090, 3332). That pattern is good and
should be preserved, not replaced.

Sample `markup=False` sites to ground scoping (not exhaustive):

- `orchestrator.py` ~699-717: divider lines and an "-- skipping 5.5" status
  line via raw `console.print`.
- `orchestrator.py` ~1877-2089: a repeated audit-loop-preview block
  (`[i/total] {bullet_preview}...`, `Tags: ... | Company: ...`) — structurally
  identical to the per-bullet preview loops already fixed in
  `audit_bullet_bank.py`/`tag_bullet_bank.py` during the bullet-bank pass.
  Likely a direct application of the same fix, not new design work.
- `rewrite_bullets.py` ~1344: a "DRY RUN PROMPT" block that dumps the full
  Gemini prompt between `====` dividers — worth deciding whether this stays a
  raw dump (developer-facing debug output) or gets a themed treatment; it's
  not user-facing narration like the rest.
- `rewrite_bullets.py` ~1527-1580: an end-of-run summary block (`KEEP:`,
  `MANUAL:`, output file paths) — a candidate for the same
  "columnar data → themed table, not icon+sentence" rule used for
  `audit_keepers.py`'s Top-10 preview and `triage_needs_review.py`'s summary
  table in the bullet-bank pass.

## Known complication

`orchestrator.py` is the single largest file in the project (3946 lines,
111 raw call sites). The bullet-bank plan enumerated every call site by exact
line number across 11 smaller files; doing the same for one file this size in
one shot may not be the right shape. Worth deciding during brainstorming
whether to section the plan by pipeline stage (e.g. JD ingest, tailoring loop,
audit loop, rewrite loop, final render) rather than one flat task list.

## Suggested first step in the fresh thread

Invoke `superpowers:brainstorming`, using this brief plus a fresh
`grep -n "markup=False" scripts/orchestrator.py scripts/rewrite_bullets.py`
to re-confirm current line numbers (this brief's line numbers may drift if
other work lands first). Reuse the bullet-bank family's line-classification
rule verbatim as the starting proposal (success/info/warning/error/detail/
rule/table) rather than re-deriving it — it's already validated across 11
files. Then: design spec → implementation plan → execute inline, git commits
at each task, same as the completed areas.

## Loose end from earlier phases

The `finishing-a-development-branch` skill was invoked once after area 1
completed and presented its merge/PR/keep-as-is menu, but the user never
explicitly picked an option — default assumption has been "keep as-is"
(option 3, keep working on `feature/tui-dashboard`) until told otherwise.
Worth resolving once all four areas are complete, not necessarily now.
