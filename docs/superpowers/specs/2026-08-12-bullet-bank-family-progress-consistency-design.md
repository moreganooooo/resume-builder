# Bullet-Bank Family Themed Output + Markup-Safety Fix

## Problem

Twelve bullet-bank maintenance scripts (`audit_bullet_bank.py`,
`cluster_bullet_bank.py`, `tag_bullet_bank.py`, `score_keeper_gems.py`,
`audit_keepers.py`, `retire_rewrite_queue.py`, `detect_blank_scores.py`,
`detect_hidden_gems.py`, `embed_bullet_bank.py`, `trim_detective_findings.py`,
`bullet_bank_menu.py`, plus `triage_needs_review.py`) print almost
everything through `cli_art.console.print(..., markup=False, soft_wrap=True)`
— 103 call sites across 11 of the 12 files (`bullet_bank_menu.py` has none;
it's already fine, questionary-driven like `menu.py`). Every one of those
lines is flat, colorless text: no icons, no color, no visual hierarchy,
despite already routing through the shared themed `console` object.

`markup=False` there is not neglect — it is almost certainly a deliberate,
correct safety measure. Verified directly against Rich's actual parser:
content in `[brackets]` that doesn't resolve to a real style name is not
rendered literally and does not raise — it is **silently dropped**:

```
console.print('  Loaded [workday] 42 bullets')       -> "  Loaded  42 bullets"
console.print('[this looks like a style tag]')        -> ""
```

These scripts interpolate real dynamic content — provider IDs, bullet
text, company names — directly into bracketed formatting (e.g.
`audit_keepers.py`'s `f"[{src:<20}]"` column). Turning markup on naively
would silently corrupt exactly that data on some fraction of real inputs.

This same risk already exists, live, in code that predates and postdates
this session: `audit_keepers.py:733` calls `cli_art.cli_warning(f"[{d['map_status']}]
{...}")`, and `scan_linkedin.py:251` calls `cli_art.cli_error(f"[LinkedIn
ON_ERROR] {error}")` — both interpolate dynamic bracketed content into
markup-enabled helpers today. And the `ScanActivity.step()` component
built earlier this session (`docs/superpowers/specs/2026-08-12-scan-verify-progress-consistency-design.md`)
has the identical latent bug: `message`/`source` are dynamic and
markup-enabled. No existing call site anywhere in the codebase relies on
real Rich markup tags *inside* a `cli_info`/`cli_success`/`cli_warning`/
`cli_error` message (verified by grep) — so fixing this at that boundary
changes nothing for any caller that isn't already broken.

## Design

### 1. Foundational fix: escape dynamic text at the helper boundary

`cli_art.cli_info`, `cli_success`, `cli_warning`, `cli_error`,
`display_error`, `display_success` each escape their `message` argument
via `rich.markup.escape()` before building the final markup string —
static surrounding markup (icons, bold) stays real; the caller-supplied
text can never be misinterpreted as a tag. `ScanActivity.step()`
(`cli_art.py`, from the scan+verify work) gets the same treatment for its
`source`/`message` params.

This one change fixes both live bugs above and the `ScanActivity` latent
risk, with zero behavior change for every other existing call site.

### 2. The sweep: `console.print(markup=False)` → themed helpers

Across the 11 files, each `console.print(f"...", markup=False,
soft_wrap=True)` call becomes a call to the now-safe `cli_art.cli_info`/
`cli_success`/`cli_warning`/`cli_error` (matched to what the line actually
communicates — a plain status update, a success/completion line, a
skip/degraded-data warning, or a real failure), or `cli_art.detail(...,
level=cli_art.VERBOSE)` for lines that are genuinely implementation detail
(cache hits, per-batch counters) rather than something an ordinary user
needs to see by default. Per-file call-site counts, smallest to largest:
`audit_bullet_bank.py` (1), `trim_detective_findings.py` (1),
`score_keeper_gems.py` (2), `detect_blank_scores.py` (5),
`retire_rewrite_queue.py` (5), `embed_bullet_bank.py` (6),
`tag_bullet_bank.py` (6), `detect_hidden_gems.py` (10),
`triage_needs_review.py` (14), `cluster_bullet_bank.py` (23),
`audit_keepers.py` (30).

`triage_needs_review.py`'s final routing summary (KEEP/REWRITE/RETIRE/
DUPLICATE/Leftover counts, currently five flat `console.print` lines)
becomes one small themed table via `cli_art`, matching the visual
language of `render_bullet_bank_status()`/`render_scan_report()` rather
than a restyled version of the same flat list.

### 3. Exception: `audit_keepers.py`'s columnar rows stay tabular

Its per-item progress rows are aligned columns, not sentences, e.g.:

```
f"      #{int(row['queue_rank']):>3}  [{src:<20}]  cmp={cmp:>5.0f}  mgr={mgr:<4}  {bp}..."
```

Forcing these into `cli_info`'s icon-plus-sentence shape would lose the
alignment that makes them scannable. These render through a themed table
(new `cli_art` table renderer, following the existing
`render_polish_table`/`render_comparison_table` pattern) instead of
`cli_info` calls. The four-stage section headers already narrated
elsewhere in `audit_keepers.py` (`"Stage 4 complete → KEEP: {n_keep} |
MANUAL: {n_manual}"`-style lines) follow rule 2 (become `cli_info`/
`cli_success`), since those are genuinely sentence-shaped status lines,
not tabular data.

## Files touched

- `scripts/cli_art.py` — `rich.markup.escape()` added to `cli_info`,
  `cli_success`, `cli_warning`, `cli_error`, `display_error`,
  `display_success`, and `ScanActivity.step()`; one new table renderer
  for `audit_keepers.py`'s columnar rows.
- `scripts/audit_bullet_bank.py`, `cluster_bullet_bank.py`,
  `tag_bullet_bank.py`, `score_keeper_gems.py`, `audit_keepers.py`,
  `retire_rewrite_queue.py`, `detect_blank_scores.py`,
  `detect_hidden_gems.py`, `embed_bullet_bank.py`,
  `trim_detective_findings.py`, `triage_needs_review.py` — every
  `console.print(..., markup=False)` call site replaced per the rules in
  §2/§3 above.
- No changes to `bullet_bank_menu.py` (already has zero `markup=False`
  calls) or to any file's return values, persisted-data shape, or CSV
  schema — this is purely how already-computed results are displayed.

## Explicitly out of scope

- Any change to the underlying logic, scoring, or data written by these
  scripts — only their terminal output changes.
- Concurrency/parallelism in any of these scripts (all currently
  sequential; no design here changes that).
- The other under-styled areas already identified but not part of this
  family (`orchestrator.py`/`rewrite_bullets.py` polish pass, the
  bootstrap/new-user flow) — tracked as separate, later work.
- Retrofitting `rich.markup.escape()` everywhere a dynamic string reaches
  `console.print` directly (outside the `cli_art` helper functions named
  above) — callers that build their own markup strings by hand keep doing
  so; only the shared helper functions get the automatic safety net,
  since that's where the sweep in §2 routes everything.
