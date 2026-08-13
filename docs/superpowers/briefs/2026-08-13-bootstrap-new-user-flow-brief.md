# Kickoff brief: bootstrap / new-user flow polish

**For a fresh thread.** This is a handoff brief, not a design spec — read this,
then invoke `superpowers:brainstorming` to scope the work before writing an
actual spec/plan. Branch: `feature/tui-dashboard` (already checked out, work
in place, no worktree needed).

## Where this fits

Part of the ongoing "Crush IDE"-level terminal polish initiative across the
resume-builder CLI. Four areas were identified; this is the one prioritized
third (moved up from originally-last because it was assessed as "already
decently invested," but first-impression stakes for a brand-new user are
high enough to warrant its own dedicated pass rather than being skipped):

1. **Job scan scripts** — DONE.
2. **Bullet-bank family + other workflows** — DONE (see
   `docs/superpowers/specs/2026-08-12-bullet-bank-family-progress-consistency-design.md`
   and its paired plan for the established pattern — line-classification
   rule + `rich.markup.escape()` safety fix, both directly reusable here).
3. **Bootstrap/new-user flow** — **this brief.**
4. **orchestrator.py / rewrite_bullets.py polish** — separate brief, see
   `2026-08-13-orchestrator-rewrite-bullets-polish-brief.md`.

## Current state (measured 2026-08-13)

| File | Lines | `cli_art.*` refs | `console.print` calls | of which `markup=False` |
|---|---|---|---|---|
| `scripts/bootstrap_profile.py` | 1074 | 69 | 53 | 47 |
| `scripts/bootstrap_menu.py` | 202 | 5 | 3 | 0 |

**Worth flagging:** the original cross-repo analysis characterized this area
as "decently invested (questionary + theme + cli_art throughout)." The actual
numbers for `bootstrap_profile.py` don't clearly support that — 47 of its 53
`console.print` calls are still raw `markup=False`, a higher raw ratio than
either `orchestrator.py` or the pre-fix bullet-bank scripts had. Re-verify
this assumption during brainstorming rather than trusting the earlier
high-level read; this file may need more work than originally scoped.

`bootstrap_menu.py` is small and mostly clean already (0 `markup=False`
hits) — likely because it's primarily a `questionary` prompt wrapper with
little raw console output of its own. Confirm during scoping whether it needs
any work at all, or whether this area is really just `bootstrap_profile.py`.

Sample `markup=False` sites in `bootstrap_profile.py` to ground scoping:

- ~174-182: a "[DRY RUN]" preview block dumping a guessed profile
  (`full_name`, `email`, `phone`, `location`, `linkedin_url`) — structurally
  a labeled-field preview, a candidate for a themed table or a
  `cli_info`/`detail` sequence rather than raw prints.
- ~379: a "Keeping profile.yml" confirmation-style line — straightforward
  `cli_success`/`cli_info` candidate.
- ~693-701: a per-bullet preview loop (`[i/total] {bullet[:60]}...`) —
  structurally identical to the exact pattern already fixed across the
  bullet-bank family (`audit_bullet_bank.py`, `tag_bullet_bank.py`, etc.).
  This is very likely a direct, low-risk application of that established
  fix rather than new design work.

## Design question worth raising in brainstorming

This file mixes two UI libraries: `questionary` (interactive prompts) and
`cli_art`/`rich` (styled console output). Worth deciding explicitly whether
questionary's own theming should be pulled toward the same color palette as
`cli_art`'s `theme.py`, or whether that seam is already consistent and just
needs the raw-print sweep. Check `theme.py` for whether it already configures
a `questionary.Style` — if not, that may be a real (small) gap distinct from
the raw-print issue.

## Suggested first step in the fresh thread

Invoke `superpowers:brainstorming`, using this brief plus a fresh
`grep -n "markup=False" scripts/bootstrap_profile.py scripts/bootstrap_menu.py`
to re-confirm current line numbers. Reuse the bullet-bank family's
line-classification rule verbatim as the starting proposal rather than
re-deriving it. Then: design spec → implementation plan → execute inline,
git commits at each task, same as the completed areas.

## Loose end from earlier phases

The `finishing-a-development-branch` skill was invoked once after area 1
completed and presented its merge/PR/keep-as-is menu, but the user never
explicitly picked an option — default assumption has been "keep as-is"
(option 3, keep working on `feature/tui-dashboard`) until told otherwise.
Worth resolving once all four areas are complete, not necessarily now.
