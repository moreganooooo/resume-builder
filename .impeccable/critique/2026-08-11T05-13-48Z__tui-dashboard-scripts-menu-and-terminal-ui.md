---
target: "TUI: dashboard/ + scripts/ menu and terminal UI"
total_score: 26
max_score: 40
na_heuristics:
p0_count: 1
p1_count: 6
timestamp: 2026-08-11T05-13-48Z
slug: tui-dashboard-scripts-menu-and-terminal-ui
---
Method: dual-agent (Assessment A: design review · Assessment B: detector + consistency audit)

# TUI Critique: resume-builder

Two independent, isolated passes: Assessment A did unanchored design/heuristic/persona review; Assessment B ran the mechanical detector (which turned out not to apply — see below) and then did its own grep/tool-based consistency audit as evidence. Findings below are synthesized, not concatenated.

## Detector note
`detect.mjs` returned 0 findings on both `dashboard/` and `scripts/`, exit 0. That's not a clean bill of health — the detector only has modes for HTML/CSS/JSX/TSX and browser-rendered URLs; there are zero such files in either directory (33 `.go`, 60 `.py`). The "clean scan" is "no eligible files," not "no anti-patterns." Real Assessment-B evidence came from a manual grep/tool audit instead, including running this repo's own purpose-built `dashboard/tools/lint_colors.go` (which *does* apply, and passed).

---

## Part 1 — Main Menu + Submenus

### Design Health Score
| # | Heuristic | Score | Key Issue |
|---|---|---|---|
| 1 | Visibility of System Status | 3 | Strong stage-status tables in bootstrap; no "starting…" indicator before the Go dashboard's cold-start subprocess launch |
| 2 | Match System / Real World | 3 | "Phase 0"/"0.5" dev-sequencing numbering leaks into user copy (`bootstrap_menu.py:139-147`) |
| 3 | User Control and Freedom | 3 | Back/Exit consistent; Ctrl-C is a documented past bug class, now fixed but handled via 3 different mechanisms across the 3 Go menu surfaces (list.go key-switch, huh's ErrUserAborted, main.go global catch) |
| 4 | Consistency and Standards | 2 | CLI menu (15 items) and Go dashboard menu (5 items) share almost no vocabulary or scope |
| 5 | Error Prevention | 3 | Cost-gated Gemini actions confirm; `archive_jd()` doesn't (`menu.py:638-641`) |
| 6 | Recognition Rather Than Recall | 2 | 15 flat/grouped top-level choices exceed working-memory limits; no per-submenu key legend |
| 7 | Flexibility and Efficiency | 3 | `--pick`/`--yes` flags, paginated pickers, chained "what's next" |
| 8 | Aesthetic and Minimalist Design | 2 | Gradient banner + stats + tip + breadcrumb stacked on every launch |
| 9 | Error Recovery | 2 | "Bootstrap wizard failed" gives no detail or fix (`menu.py:322-324`) |
| 10 | Help and Documentation | 3 | `resume help` cheat sheet is thorough and single-sourced |
| **Total** | | **26/40** | **Acceptable** |

### Design Specificity Verdict
Authored, not boilerplate — the icon+color pairing, resumable onboarding status table, and guest-mode gating are real product thinking. But the 15-item flat top-level menu reads as organically grown rather than intentionally scoped, and the CLI/dashboard menu split has no shared vocabulary explaining why.

Deterministic evidence: no hardcoded ANSI/hex color bypass, no raw `input()`/`fmt.Scan` calls remaining in this file set (the `65b78e5f`/`2da53e4c` fixes hold here), icon struct fields match 1:1 between `icons.go` and `theme.go`. One duplication found: `style=cli_art.QUESTIONARY_STYLE` is repeated at 18 call sites across 4 files with no shared wrapper — low risk (the constant itself is centralized) but real duplication.

### Overall Impression
The menu system has real craft in its details (icon pairing, resumable bootstrap) but hasn't been edited down as it grew — 15 top-level choices and duplicate "what's next" logic are signs of accretion, not a designed information architecture.

### What's Working
- `menu.py:151-217` — shared-computer safety net that explicitly documents and fixes a prior Ctrl-C-fallthrough bug class.
- `bootstrap_menu.py:27-67` — per-stage resumable status turns an 8-step onboarding pipeline into transparent, restartable progress.
- Icon+color pairing (`menu.py:43-46`, `theme.questionary_icon_tuple`) is consistent across every single choice.

### Priority Issues
- **[P1] 15-item flat main menu exceeds recognition limits** (`menu.py:59-91`). Why it matters: pushes a non-technical job seeker past the ~7-item working-memory ceiling on the very first screen they see. Fix: collapse into 5-7 categories (Find Jobs / Build Documents / Bullet Bank / Track & Follow Up / Setup). Suggested command: `/impeccable layout`
- **[P1] CLI and dashboard menus share no vocabulary** (`menu.py:59-91` vs `dashboard/internal/ui/menu/list.go:29-35`). Why it matters: a user who learns one surface has zero transfer to the other; "Career Dashboard" doesn't signal it's a narrower, review-only scope. Fix: either mirror a CLI subset in the dashboard menu, or explicitly label the scope drop. Suggested command: `/impeccable clarify`
- **[P2] Bootstrap wizard demands a typed absolute filesystem path with no autocomplete/picker** (`wizard.go:63-92`). Fix: prefill common locations or add a huh file-picker. Suggested command: `/impeccable onboard`
- **[P2] Two independent "what's next" mechanisms with different vocabularies** (`menu.py`'s `_CHAIN`/`_run_with_chain` vs. `cli.py:49-79`'s `_offer_next_steps`). Fix: unify into one shared function. Suggested command: `/impeccable distill`
- **[P3] `archive_jd()` fires with zero confirmation** (`menu.py:638-641`), inconsistent with this menu's own cost-gated-confirm pattern elsewhere. Suggested command: `/impeccable harden`

### Persona Red Flags
**Jordan (first-timer)**: 15-item menu carrying "Phase 0/0.5" internal-sequencing jargon (`bootstrap_menu.py:139-147`); the wizard's "Absolute path on your machine" field (`wizard.go:64-67`) assumes filesystem fluency.
**Riley (stress-tester)**: Ctrl-C is handled by 3 different mechanisms across `list.go`, `prompt.go`/`wizard.go` (via `huh.ErrUserAborted`), and `main.go`'s global catch — functionally fine today (verified, not broken) but a fragile spot given it's already broken once (`2da53e4c`).

### Minor Observations
- `_flourish_line()` (`menu.py:94-120`) is a lot of engineering for a decorative separator relative to how flat the menu underneath it is.
- `style=cli_art.QUESTIONARY_STYLE` duplicated at 18 call sites, no shared `select()`/`confirm()` wrapper in `cli_art.py`.
- `bullet_bank_menu.py`'s `↳`-prefixed nested follow-up choices (lines 366-374) are good progressive disclosure — worth reusing in the main menu's own restructuring.

---

## Part 2 — User-Facing Scripts / Terminal Output

### Design Health Score
| # | Heuristic | Score | Key Issue |
|---|---|---|---|
| 1 | Visibility of System Status | 4 | Genuinely excellent — progress bars, spinners, checkpoint-resume messaging |
| 2 | Match System / Real World | 2 | `orchestrator.py` prints cache/tier/token internals on ordinary runs |
| 3 | User Control and Freedom | 3 | Confirm-gates present; `polish.py`'s accept-loop has no undo once saved |
| 4 | Consistency and Standards | 2 | `audit_bullet_bank.py`/`build_sample.py`/`git_update.py` bypass the shared `cli_art`/`theme` system the rest of the codebase follows |
| 5 | Error Prevention | 3 | `should_proceed()`/`_confirm()` gates consistent and well-worded |
| 6 | Recognition Rather Than Recall | 3 | Good tables/legends; `polish.py`'s raw-repr diff needs schema recall |
| 7 | Flexibility and Efficiency | 3 | Checkpointing, `--refresh`/`--yes`, pagination throughout |
| 8 | Aesthetic and Minimalist Design | 2 | `orchestrator.py`'s verbose internals contradict `scan.py`'s own documented "don't spam" philosophy |
| 9 | Error Recovery | 2 | Raw exception text reaches the terminal unmediated in several scripts |
| 10 | Help and Documentation | 3 | `doctor.py`'s check+detail+fix convention is excellent where used |
| **Total** | | **27/40** | **Acceptable** (top of band) |

### Design Specificity Verdict
The shared system (`theme.py`/`cli_art.py`) is genuinely well-built and specific to this product — documented WCAG contrast math, a single icon pipeline, a shared recommendation-color vocabulary. Adoption is inconsistent: several scripts bypass it with hand-rolled prints, and `orchestrator.py` — the core engine, run on every job — leaks deep implementation detail by default.

Deterministic evidence: only 3 bare `print()` calls exist anywhere in `scripts/*.py`, all in `dashboard_actions.py`, and all **deliberate and correct** — that file's own docstring explains `jobs.go` captures its stderr verbatim into a themed Go panel, so Rich markup would leak in as garbage if it used `cli_art`. Verified false positive, not a bug. 21 of 60 scripts import neither `cli_art` nor `theme`; all 21 checked out as pure library modules with no `print()` calls of their own — correct layering, not a gap.

The real finding: **the "harden silent-failure paths" commit (`2da53e4c`) was partial, not exhaustive.** 7 `except Exception` blocks across 6 files still silently swallow errors with no log/print/re-raise:
- `audit_keepers.py:489` — same file, same commit fixed 3 sibling blocks (lines 292/310/337) with warnings; this 4th block was missed.
- `bootstrap_bullet_bank.py:289` — silently treats a corrupted bullet-bank CSV as "0 rows."
- `score_keeper_gems.py:98`, `rewrite_bullets.py:256`, `theme.py:145`, `orchestrator.py:678` — silent fallbacks, no log.
- `gemini_client.py:370` — silent `return None, {}`, inconsistent with sibling branches in the *same function* that do log a warning first.
(`company_research.py:118`'s silent `return None` is explicitly contractual per its own docstring — not a bug.)

### Overall Impression
The status-visibility and confirm-gate patterns here are the strongest UX work in the whole program — but two things undercut it: `orchestrator.py` breaks its own house style by defaulting to engineer-facing verbosity, and the error-hardening pass that clearly started (and did good work in `audit_keepers.py`, `scan_linkedin.py`, `picker.py`) didn't finish.

### What's Working
- `doctor.py:49-338` — every failed check carries a concrete one-line fix; the model every other error path should follow.
- `scan.py`'s `run_scan`/`render_scan_report` — explicitly documents and avoids per-item noise, collapsing hundreds of lines into one grouped summary.
- `picker.py:86-234` — one shared, scroll-bounded pagination engine reused everywhere instead of four bespoke ones.

### Priority Issues
- **[P0] `orchestrator.py` prints engineering telemetry by default** — cache hit/miss, per-tier character counts, model internals, rule-file names (`orchestrator.py:1338-1719, 1743-1894`) — on every ordinary tailoring run, for every user. Why it matters: this is the single biggest violation of the "non-dev-fluent user" design goal, and it's the core engine every user runs constantly. Fix: gate behind `--verbose`/a debug env var; default to the step-labeled summary `dashboard_actions.py` already parses. Suggested command: `/impeccable clarify`
- **[P1] Silent-failure hardening is incomplete** — 7 `except Exception` blocks across `audit_keepers.py:489`, `bootstrap_bullet_bank.py:289`, `score_keeper_gems.py:98`, `rewrite_bullets.py:256`, `gemini_client.py:370`, `theme.py:145`, `orchestrator.py:678` still swallow errors with zero user-visible signal. Why it matters: users see stale/wrong state (e.g. "0 existing rows") with no idea it came from a parse failure, not reality. Fix: route each through the existing `cli_art.cli_warning()` pattern already used on the 3 sibling blocks that *were* fixed in `audit_keepers.py` — same file proves the fix pattern already exists. Suggested command: `/impeccable harden`
- **[P1] `polish.py`'s diff view renders raw Python `repr()`** with ALL-CAPS schema keys and no +/- coloring (`polish.py:63-114`), at the exact moment a user reviews edits to their own resume. Fix: color old/new with `theme.ERROR`/`theme.SUCCESS`; map schema keys via `cli_art.py`'s existing `_FIT_DIMENSION_GROUPS`. Suggested command: `/impeccable typeset`
- **[P2] Raw exception text leaks unmediated** elsewhere too: `audit_bullet_bank.py:111`, `bootstrap_bullet_bank.py:390,394`, and git stderr surfaced raw via `menu.py:856`. Fix: a `friendly_error()` helper classifying common cases, matching `doctor.py`'s own convention. Suggested command: `/impeccable clarify`
- **[P3] `liveness.py:224` identifies results by raw file path** instead of company/title, unlike every other list view. Fix: resolve via `jd_manager.extract_job_meta()`. Suggested command: `/impeccable clarify`

### Persona Red Flags
**Jordan (first-timer)**: hits `orchestrator.py`'s cache/tier jargon on their very first build, plus raw exception text in `bootstrap_bullet_bank.py:390,394` during the new-user flow itself.
**Sam (color-only signaling)**: `cli_art.py:313-326`'s `_posting_age_cell` encodes posting freshness purely by text color (green/amber/red) — the one place in `cli_art.py` that doesn't pair color with an icon the way `colorize_icon()` does everywhere else.

### Minor Observations
- `build_sample.py` hand-rolls `'─'*60` dividers instead of `cli_art.display_banner()`/`Panel` — a visible style break.
- `audit_bullet_bank.py:116` prints a "Checkpoint saved" line after every single bullet (spam); line 124 misuses red error-styling for a benign zero-count summary.

---

## Part 3 — Dashboard Screens/Chrome

### Design Health Score
| # | Heuristic | Score | Key Issue |
|---|---|---|---|
| 1 | Visibility of System Status | 3 | Real progress bar for tailor action; liveness/status spinners have no fallback if stuck |
| 2 | Match System / Real World | 2 | `formatSubscores` (`jobs.go:544-558`) prints raw snake_case schema keys |
| 3 | User Control and Freedom | 3 | Esc/Quit consistent, in-flight actions cancellable |
| 4 | Consistency and Standards | 2 | 5-item Main Menu doesn't reflect the CLI's real breadth |
| 5 | Error Prevention | 3 | Status changes commit immediately with no confirm (`jobs.go:360-369`) |
| 6 | Recognition Rather Than Recall | 2 | 12-14 single-letter chords per screen, no help overlay |
| 7 | Flexibility and Efficiency | 3 | Sort/filter/search/tabs, vim-style nav, half-page scroll |
| 8 | Aesthetic and Minimalist Design | 3 | Strongest realization of "Command Center Editor" of the three parts |
| 9 | Error Recovery | 2 | Raw error text surfaces directly in the viewer and action panels |
| 10 | Help and Documentation | 2 | No in-app help screen; only the bottom key-bar |
| **Total** | | **25/40** | **Acceptable** |

### Design Specificity Verdict
The most rigorously-authored surface of the three. Code comments repeatedly cite real WCAG contrast measurements and fixes, narrow-terminal truncation guards are deliberate, and shared helpers (`bars.go`) prevent Jobs/Pipeline drift. This is genuinely crafted TUI work.

Deterministic evidence corroborates this strongly: `dashboard/tools/lint_colors.go` — a purpose-built internal linter this codebase already has, specifically written after two prior contrast bugs it documents in its own comments — runs clean (`go run ./tools/lint_colors.go` → "Color linting passed," exit 0), independently confirmed by a zero-hit grep for hardcoded hex. The narrow-terminal fix from `078f8d6d` was checked for unfixed siblings and found complete — all 6 `fitBar()` call sites consistently pass the background param, and no parallel unbounded-bar pattern exists outside `progress.go`.

One real cross-cutting discrepancy, found independently by both assessments: **DESIGN.md's stated success/warning/error hex values (`#4caf50`/`#f5c542`/`#c96a6a`) don't match what's actually implemented** (`#12C78F`/`#F5EF34`/`#FF7B99` in `theme.py` → `resumebuilder.go`). `theme.py`'s own comments explain these were deliberately substituted for AA-contrast reasons — the implementation is right, DESIGN.md is stale.

### Overall Impression
The best-crafted of the three surfaces on contrast/layout discipline, undercut by two omissions: no help overlay for a dense, chord-heavy interface, and a data-label regression where the Go side shows raw schema keys the Python side already solved.

### What's Working
- Extensive, code-documented WCAG contrast discipline (`theme.go:78-93`, `pipeline.go:1116-1137`) — measured, not eyeballed, and enforced by a real internal linter that passes clean.
- `bars.go:1-193` — shared `fitBar`/`renderSidebarRow`/`detailPaneStyles` keep Jobs and Pipeline visually identical and share narrow-terminal guards.
- `pipeline.go:1126-1137`'s `statusColorMap` — real semantic differentiation per status instead of one reused accent.

### Priority Issues
- **[P1] `formatSubscores` prints raw schema keys** (`jobs.go:544-558`) while `cli_art.py:508-524` already maps every one of these exact keys to a human label. Why it matters: this is an avoidable regression, not a missing capability — the fix already exists on the other side of the codebase. Fix: port the label map into Go, or generate it the way `sync_dashboard_theme.py` already generates the Go theme from `theme.py`. Suggested command: `/impeccable clarify`
- **[P1] No in-app help overlay** for 12-14 keybindings per screen living only in a dense bottom bar. Fix: add a `?` key opening a categorized key panel, matching the CLI's own dedicated Help entry. Suggested command: `/impeccable onboard`
- **[P2] Application-status changes commit immediately on Enter**, no confirm/undo (`jobs.go:360-369`, `pipeline.go:520-533`) — mirrors the same gap found independently in Part 1's `archive_jd()`. Fix: add a lightweight confirm, matching the CLI's cost-gated pattern. Suggested command: `/impeccable harden`
- **[P2] Raw error text passes through by design in two places** — `viewer.go:39` embeds a raw `os.ReadFile` error; `jobs.go:663-670` deliberately forwards `dashboard_actions.py`'s raw stderr per that module's own docstring. Two individually-reasonable choices compound into unfiltered technical errors reaching the least technical part of the product. Fix: have `dashboard_actions.py` emit one final plain-language line on failure that `jobs.go` prefers when present. Suggested command: `/impeccable clarify`
- **[P3] Pipeline's 8-tab bar silently truncates on narrow terminals** (`pipeline.go:992-1004`) with no "(more)" affordance — tabs become invisible even though cycle keys still reach them. Suggested command: `/impeccable adapt`

### Persona Red Flags
**Sam (color-only signaling)**: `bars.go:82-93`'s `scoreStyle` encodes composite-score tier purely by color banding, no icon/shape redundancy.
**Alex (power-user)**: Pipeline has live `/` search (`pipeline.go:319-322`); Jobs — the screen most likely to hold hundreds of postings — has none, only scroll + a 3-way filter cycle.

### Minor Observations
- `main.go:399` explicitly defaults to the `resume-builder` theme (not `auto`) — good, but see the DESIGN.md/implementation mismatch above for what that theme actually contains.
- The harmonica-spring screen-transition (`main.go:85-108`) is properly gated behind `RESUME_BUILDER_MOTION=reduced` — a real vestibular accommodation.

---

## Combined Program Score

| # | Heuristic | Menu | Scripts | Screens | Avg | Program Key Issue |
|---|---|---|---|---|---|---|
| 1 | Visibility of System Status | 3 | 4 | 3 | 3.3 | Strongest heuristic program-wide; only gap is cold-starts/stuck-spinners |
| 2 | Match System / Real World | 3 | 2 | 2 | 2.3 | Internal jargon/schema keys leak to users in 2 of 3 surfaces |
| 3 | User Control and Freedom | 3 | 3 | 3 | 3.0 | Consistently solid |
| 4 | Consistency and Standards | 2 | 2 | 2 | 2.0 | Weakest heuristic program-wide — CLI/dashboard menu scope mismatch is the root cause |
| 5 | Error Prevention | 3 | 3 | 3 | 3.0 | Good, but same one blind spot (destructive-but-free actions) recurs independently in both Menu and Screens |
| 6 | Recognition Rather Than Recall | 2 | 3 | 2 | 2.3 | No help legend/overlay anywhere in the TUI stack |
| 7 | Flexibility and Efficiency | 3 | 3 | 3 | 3.0 | Consistently solid |
| 8 | Aesthetic and Minimalist Design | 2 | 2 | 3 | 2.3 | Screens realize the brand best; Menu/Scripts add decoration where content should carry it |
| 9 | Error Recovery | 2 | 2 | 2 | 2.0 | Weakest tied with #4 — raw errors surface in all three surfaces |
| 10 | Help and Documentation | 3 | 3 | 2 | 2.7 | Good in CLI (`resume help`), absent in the dashboard |
| **Total** | | **26/40** | **27/40** | **25/40** | **26/40** | **Acceptable** |

*(Combined total is the three parts' actual point totals averaged — 78 ÷ 3 — not a re-sum of the rounded Avg column above, which will read a point or two off due to rounding.)*

Program-wide, the same two failure modes appear independently in all three surfaces, which is more informative than any single score: **(1) internal implementation detail (schema keys, cache internals, dev-phase numbering, raw stderr) leaks to a self-described non-technical audience**, and **(2) destructive-but-free actions get no confirmation** even where costly actions do. Neither looks like a one-off bug — both are a missing house rule, which is why fixing them once (a shared `friendly_error()` helper; a shared confirm-gate policy) would move all three scores at once rather than requiring three separate fixes.

## Program-Wide Priority Issues (ranked)
1. **[P0]** `orchestrator.py`'s default engineering-telemetry output (Part 2) — highest-frequency exposure of the "leaks internals" pattern; every user hits this on every run.
2. **[P1]** Silent-failure hardening left incomplete across 6 files (Part 2) — users see wrong state with zero signal.
3. **[P1]** `formatSubscores` raw schema keys in the dashboard (Part 3) — a regression against work already done on the CLI side.
4. **[P1]** 15-item flat main menu (Part 1) + no dashboard help overlay (Part 3) — the program's two "recognition rather than recall" failures, same root cause (no information architecture pass), different surfaces.
5. **[P1]** CLI/dashboard menu vocabulary mismatch (Part 1, corroborated by Cross-Part evidence) — undermines the "one coherent product" feel across the two halves of the stack.

## Questions to Consider
- If `orchestrator.py`'s telemetry exists because you still need it while iterating on prompts, does a `--verbose` flag actually cost you anything, or is defaulting it off pure upside?
- The CLI's 15 items and the dashboard's 5 both feel individually reasonable — is the real fix restructuring the CLI, expanding the dashboard, or explicitly documenting that they're different tools for different moments (triage vs. deep work)?
- Now that `audit_keepers.py` proves the hardening fix pattern is cheap (a one-line `cli_art.cli_warning()` per block), is there a reason the other 6 blocks weren't included in `2da53e4c`, or was it just scope-cut?
