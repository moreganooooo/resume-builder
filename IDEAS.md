# Ideas & Future Features

A running backlog of things worth building eventually. Nothing here is scheduled --
pull an item into a real plan (see `docs/superpowers/plans/`) when it's time to build it.

Organized by difficulty/scope, easiest first, so it's easy to see what's a
quick win vs. what needs its own planning session before touching code.

- **Easy** -- small, mechanical, no open design questions.
- **Medium** -- real engineering work across a few files, but the design
  questions are answerable/scoped, not open-ended.
- **Hard** -- has at least one genuine open design question (not just
  engineering) that needs a brainstorming pass before building.
- **Very Hard / Long-term** -- big, cross-cutting, multi-session efforts;
  no design work has started on any of these yet.

**This file only tracks open items.** For full build history, past
incidents, and detail on everything already shipped, see
[`IDEAS_ARCHIVE.md`](IDEAS_ARCHIVE.md).

## Suggested build order

A cross-cutting priority pass over the backlog, ordered by dependency (not
a replacement for the difficulty tiers below -- this is *which order*, the
tiers are still *how hard*). Numbering carries over from the original
2026-07-04 roadmap; items 1-3, 6, and the liveness half of 10 are done and
have been moved to the archive, so the sequence below starts at 4.

| # | Item | Difficulty | Notes |
|---|------|-----------|-------|
| 4 | Engine/profile rules audit + split | Medium-Hard | **Done 2026-07-17, including the `orchestrator.py` gap found in that day's final review (archived).** See `IDEAS_ARCHIVE.md`'s "Engine/profile split: orchestrator.py Morgan-specific constants closed" entry, and Multi-user support below. |
| 5 | Evidence bank extension | -- | Phase 1 shipped 2026-07-07 (archived). Everything past Phase 1 decoupled from the merge/career-ops entirely 2026-07-21 -- see "Strengthen evidence-guide.csv for cover letters" (Medium) and "Evidence bank: interview stories, negotiation talking points, full multi-type generalization" (Very Hard / Long-term) below. |
| 7 | Per-user secrets (`.env` per profile) | Easy | **Done 2026-07-17 (archived)** -- every script now loads `profiles/<name>/.env` instead of one shared root file; Morgan's real `.env` migrated. Bootstrap's own wizard walks a new profile through entering `GEMINI_API_KEY`/`JOBRIGHT_COOKIE_STRING` (or deferring to a file edit later) before Phase 0's first API call. See `IDEAS_ARCHIVE.md`. |
| 8 | Dominick's onboarding | Hard | Onboarding wizard shipped 2026-07-12/13; `profiles/<name>/` isolation shipped 2026-07-17; #4's `orchestrator.py` gap and #7 (per-user secrets) both closed same week. **No remaining blockers** on the engineering side -- next step is Dom's actual first session. See Multi-user support below. |
| 9 | Scheduler + notifications | Hard | Unblocked -- `scan` and `evaluate` stages both exist. Not started. See the Long-term merge section below. |
| 10 | Mongo migration | Medium | The liveness-check half of this item is done (archived). Migration itself still undone -- tied to the long-term three-way merge. |
| 11 | Multi-select "Specific JD" pickers (space-bar toggle) | -- | **Done 2026-07-21 (archived)**, folded into the "Browse & Manage Jobs" build alongside #15 and multi-job comparison -- see `IDEAS_ARCHIVE.md`. |
| 12 | Help command in the interactive menu | -- | **Done 2026-07-20 (archived).** See `IDEAS_ARCHIVE.md`. |
| 13 | "Doctor" script (dependency/asset checks + test run) | -- | **Done 2026-07-22 (archived)**, built together with #14's Maintenance submenu -- see `IDEAS_ARCHIVE.md`. |
| 14 | Bullet-bank reintegration menu option + eventual "Maintenance" submenu | -- | **Done.** Bullet-bank menu done 2026-07-15 (archived). The top-level "Maintenance" submenu shipped 2026-07-22 as the general home for admin tasks (doctor checks today) -- deliberately kept separate from "Manage Bullet Bank"'s own already-working maintenance section rather than merging them. See `IDEAS_ARCHIVE.md`. |
| 15 | "List Jobs" / "View Pipeline" browsing command | -- | **Done 2026-07-21 (archived)** as "Browse & Manage Jobs" -- browse, drill-in, Archive, and bulk actions across every evaluated JD, pending or completed. Retired the old "View Application Tracker" entry entirely. See `IDEAS_ARCHIVE.md`. |
| 16 | Skip recently-checked JDs in liveness (like evaluate's skip-by-default) | -- | **Done 2026-07-21 (archived).** See `IDEAS_ARCHIVE.md`. |

**Deliberately left off this pass:** an `interview-prep` pipeline stage
(porting career-ops's `modes/interview-prep.md`) -- Morgan's call, not
essential right now, revisit later if it turns out to be needed. Still a
real capability worth having eventually, just not part of this ordering.

## Easy

### Rename the `resume` CLI alias

"Resume" is ambiguous in a way that's mildly confusing in context --
`resume tailor`, `resume run`, etc. read fine on their own, but the name
overloads with "resume [a paused process]" (e.g. "This process is
paused. Would you like to resume?"). The shell wrapper
(`scripts/resume-cli.sh`, sourced from `~/.zshrc`/`~/.bashrc`) and every
reference to it in `README.md`/`CLAUDE.md` would need updating to the new
name. Mechanically small -- the only open question is picking the actual
name. Candidates floated 2026-07-16: `rb` (short for resume-builder),
`rbuild`, `jobkit`. Pull this into a real change the moment a name is
chosen.

## Medium

### Prettier, more informative live progress for liveness / evaluate

Raised 2026-07-17 (Morgan's memory of this being worked on before is
half-right): a real console-polish pass happened 2026-07-07
(`docs/superpowers/specs/2026-07-07-console-polish-design.md`, archived)
but it was scoped to the resume-*build* pipeline specifically (Step 1-7
headers, the PDF trim loop, banner colors) -- `scan.py`, `liveness.py`,
and `batch_evaluate.py` were never part of that pass. **`scan.py`'s piece
is now done** (`[i/total]` + explicit skip-reason per job, shipped
2026-07-17 alongside the evaluate-rationale/voice-anchor work -- see
`IDEAS_ARCHIVE.md`). **`batch_evaluate.py`'s piece is now done too**
(`───` separator added between entries, 2026-07-21, matching the
audit-loop/bootstrap-polish standard). Still open:
- `liveness.py` is architecturally different from the other two: it
  shells out to `check-liveness.mjs` once for the *entire* batch via
  `subprocess.run(..., capture_output=True)`, so there's no per-JD
  progress signal available *during* the check today -- results only
  print after the whole subprocess returns. Adding real incremental
  progress here means the Node side streaming partial results (e.g.
  JSON-lines to stdout as each URL resolves) rather than a single
  captured blob, which is a real architecture change, not just a print
  statement -- scope this one separately from the other two rather than
  bundling all three into one pass.

### Rotate across multiple API keys on rate-limit errors

Raised 2026-07-17: `GeminiClient` already does model-fallback (flash-lite
<-> gemma) on sustained failure (`gemini_client.py`'s `MODEL_FALLBACKS`),
but has no concept of multiple *keys* for the same model -- one
`GEMINI_API_KEY` in `.env`, full stop. The ask: support a list of keys
(e.g. `GEMINI_API_KEYS=key1,key2,key3` alongside or instead of the
singular var) and rotate to the next one specifically on a 429/rate-limit
response, the same way `MODEL_FALLBACKS` already rotates models on
sustained failure -- likely the same retry/backoff machinery
(`RETRYABLE`/`HIGH_DEMAND_STATUS` in `gemini_client.py`) extended with a
key index instead of (or alongside) a model swap. Real, but scoped --
mostly touches `GeminiClient.generate()`'s retry loop; the main design
question is whether key rotation and model-fallback rotation compose
cleanly (try every key on the current model before swapping models, or
interleave) rather than needing a genuinely new mechanism.

### Turn the bootstrap flow into a persistent, resumable submenu

Raised 2026-07-17: today "New User? Start Here!" is a single linear
subprocess run (`bootstrap_bullet_bank.py`, per Phase 0 -> 0.5 -> 1-6) --
if you back out partway (or it's a multi-session onboarding), there's no
menu entry to see where you left off short of re-running the whole thing
and relying on each phase's own internal checkpoint files. The ask:
a dedicated menu entry (mirroring "Manage Bullet Bank"'s existing status-
table-across-stages design, `scripts/bullet_bank_menu.py`) that shows
this profile's own progress -- documents ingested, profile.yml/cv.md/
background-guide drafted or not, which of the six real pipeline stages
have run -- and lets you jump back in at whichever step, rather than
always starting from `bootstrap_bullet_bank.main()`'s top. Most of the
underlying state already exists (Phase 0's `checkpoint.json`, Phase 0.5's
now-existing `cv_draft_checkpoint.json`, the six pipeline stages' own
per-stage outputs) -- this is primarily a UI/menu-wiring exercise over
already-persisted state, not new tracking logic, closely related to (and
possibly sharing menu real estate with) the "Maintenance" submenu idea
below.

### Strengthen evidence-guide.csv for cover letters

Split off from the evidence-bank/merge discussion 2026-07-21, decoupled
from career-ops entirely -- Morgan has additional source material in other
places she can supply whenever this gets picked up, no dependency on the
merge or on career-ops's files specifically. `evidence-guide.csv` (78
rows: Evidence Cluster / Finding / Source File(s) / Best Detail-Quote /
Best Metric / What This Proves / Where to Use It / Confidence / Source
URL) is comparatively thin next to the resume bullet bank's 1,400+ rows,
and it's the one piece of a broader evidence-bank expansion with real,
immediate payoff -- it already has a live consumer (cover-letter
generation already reads this file), so filling it out directly
strengthens cover letters without needing any new pipeline stage or
schema. No open design question -- same extraction pattern already proven
on the existing 78 rows (read source material, fill in the existing
columns, verify attribution before adding a row). Non-essential, no
deadline -- whenever Morgan wants to supply more material.

## Hard

### Application pattern analysis

Found during the 2026-07-21 sibling-repo audit: career-ops's
`modes/patterns.md` + `analyze-patterns.mjs` mine historical
evaluations/applications/outcomes for what's actually converting (by
archetype, etc.), not just a rejection log. Independently reinforced --
job_automater's own README lists an "Analytics Dashboard" under its own
Future Enhancements wishlist, so this is a capability both sibling
projects separately wanted. Not tracked anywhere in resume-builder yet.
**Difficulty: Hard.** Checked career-ops directly -- `analyze-patterns.mjs`
is 692 lines, the largest backing script found across all four modes
surfaced in this audit, doing real historical mining across
evaluations/outcomes. Genuine analytical logic to port or rebuild (not
prompt adaptation) -- closest in spirit to a small analytics engine, not
a quick feature add.

### Repo reorganization / cleanup pass

As the project's grown, the highest-traffic folders (`scripts/`,
`resume-engine/knowledge_base/`) have gotten harder to scan -- worth a
real subfolder pass plus archiving/deleting whatever's actually outdated
or unused. **Why this is Hard, not Easy/Medium:** files here are
referenced by path from many different scripts (constants scattered
across `rewrite_bullets.py`, `orchestrator.py`, `bullet_bank_menu.py`,
`audit_keepers.py`, etc.), so moving anything without first tracing
every reference risks silently breaking an import or a runtime file
lookup -- and "what's actually outdated vs. still load-bearing" isn't
safe to guess at; it needs a real audit (grep every file for
cross-references, check git log recency, check what the test suite
actually exercises) before anything gets moved or deleted. Deleting/
moving is also much harder to walk back than most changes in this repo,
which argues for a proposed structure + audit findings reviewed before
executing, not folding straight into implementation.

## Very Hard / Long-term

### Multi-computer sync for a profile's data

Raised 2026-07-17, genuinely open brainstorm (not scoped, no direction
chosen yet): using this on more than one machine (e.g. a laptop and a
desktop) means `profiles/<name>/` -- knowledge_base, bullet bank,
checkpoints, and now each profile's own `.env` -- only lives on whichever
one you last touched. job_automater's prior art here was MongoDB (a real
remote datastore, but a genuinely different architecture from this
repo's flat-file-per-profile design -- adopting it would mean either
migrating every script that reads/writes these files directly, or
running Mongo as a sync layer underneath the same file-based interface,
which is its own design problem). Three lighter-weight options Morgan
raised, none evaluated yet against this repo's actual constraints
(git-ignored secrets in `.env`, binary-ish files like `.npy` embeddings
mixed with text/CSV, checkpoint files that assume they're the only
writer at a time):
- **Syncthing** -- continuous, no-cloud-server file sync between
  specific machines/paths. Closest to "just works" for a flat-file
  layout like this one, but needs care around files that get read
  *and* written mid-run (checkpoints, cluster maps) if two machines
  could ever be active at once -- probably fine for "one person, two
  machines, never simultaneously," worth confirming that's the actual
  use case before assuming it.
- **Cloud-folder symlinks** (Dropbox/Google Drive/OneDrive +
  `ln -s`/`mklink /J`) -- simplest to set up, but inherits whatever
  conflict-resolution behavior the cloud provider has for files that
  change on two machines close together (typically a "conflicted copy"
  duplicate file, not a merge) -- probably fine for the same
  never-simultaneous use case, riskier if that assumption doesn't hold.
- **Version control** (git) for the text-based state specifically --
  already partially true (profile.yml-adjacent content could be
  committed to a private repo/branch), but explicitly wrong for
  `.env` (secrets, must stay gitignored) and awkward for large/binary
  knowledge-base files (embeddings, audited CSVs) that don't diff
  meaningfully.
**Not evaluated yet, worth doing before committing to one:** what
actually needs to sync (is `output/`/PDF history worth syncing, or just
the knowledge base + bullet bank + profile.yml?), whether "two machines,
never simultaneous" is a safe assumption to design around, and whether
`.env`/secrets need to be explicitly excluded from whichever mechanism
gets chosen (almost certainly yes, regardless of approach).

### Evidence bank: interview stories, negotiation talking points, full multi-type generalization

Split off from the evidence-bank/merge discussion 2026-07-21, **deliberately
decoupled from career-ops and from the merge** -- not blocked by, or
blocking, anything in the three-repo merge punchlist. Morgan has this kind
of source material (interview stories, negotiation talking points, company
proof points) in places outside career-ops too, and can supply it whenever
she wants to dig in -- no urgency, no deadline, no dependency on the merge
happening first. Two real things bundled here, worth separating whenever
this gets picked up: (1) sourcing/curating the raw material itself (dedup,
verify real attribution before anything goes in a bank whose whole premise
is "never fabricate, everything traceable"), and (2) the actual engineering
-- today nothing in the pipeline can consume an evidence type beyond resume
bullets; even `evaluate_fit()`'s cover-letter path only reads
`evidence-guide.csv` directly, there's no general "different renderers pull
from the same audited pool, filtered by evidence type" mechanism yet (the
architecture the Long-term merge section below originally sketched this
under). Interview-story evidence specifically has no consumer at all --
the `interview-prep` pipeline stage doesn't exist and is separately
deferred (Morgan's call, see the merge section below) -- so curating that
material before that stage exists would sit unused. Non-essential,
someday, no target date.

### Long-term: merge with career-ops and job_automater

**Punchlist:** `docs/superpowers/plans/2026-07-16-three-repo-merge-punchlist.md`
turns the narrative below into an ordered, actionable list (with
dependencies/blockers noted) -- this section stays the "why," that file is
the "what's next."

**Scope note:** the biggest item on this list. Spans three separate
codebases (this project plus two mature sibling projects). A brainstorming
pass happened 2026-07-04 and landed on an agreed direction below, but
**no implementation has started and nothing is scheduled yet**; this is
reference material for when that build actually begins, not a plan with a
start date. Full incident history (career-ops's June 2026 auto-update
overwriting Morgan's customizations, job_automater's file-loss repair, the
leaked-cookie finding now tracked separately under Easy above) lives in
`IDEAS_ARCHIVE.md`.

The eventual goal is a single system, with resume-builder replacing the
resume-generation features of both `/Users/morganescott/career-ops` and
`/Users/morganescott/job_automater`.

- **From career-ops** ("the glue"): the dashboard, application tracker
  (markdown/YAML, treated as the source of truth), and the multi-agent
  "mode" pipeline (job-board scanning via `providers/`, JD-fit evaluation,
  tracker updates). Its `providers/` cover direct-to-ATS job-board
  scanning (Ashby, Greenhouse, Lever, Workable, SmartRecruiters,
  Recruitee, plus a generic local-parser fallback, ~26 providers total) --
  a different, complementary source type from job_automater's scrapers
  below (LinkedIn + JobRight), not a redundant one; the merged system
  likely wants both rather than picking one. Worth naming which 1-2
  providers Morgan actually uses before picking what to port first.
- **From job_automater**: the CLI shape (`cli.py`, Click-based
  `job-agent`-style command group: `fetch-jobs`, `list-jobs`,
  `generate-docs`, `apply`, `status`, `setup`, `validate-config`/`config`,
  `config-info`, `interactive`) and its "doctor" pattern (see the Doctor
  script item above). Its document-generation backends (LaTeX/reportlab)
  and ATS auto-apply engine were both explicitly decided against carrying
  forward -- see `IDEAS_ARCHIVE.md` for why.
- **Persistence-layer mismatch, worth deciding up front -- not yet
  decided.** job_automater stores everything in MongoDB (run via a local
  Docker container, `local-mongo` / image `mongo:latest`, port 27017),
  career-ops treats flat markdown/YAML files as the source of truth
  (`data/applications.md`, `data/pipeline.md`), and resume-builder uses
  CSV files + JSON checkpoints. Three different persistence philosophies
  across the three projects -- the merge needs one, not an integration
  layer across all three.

  **Pros/cons discussed 2026-07-06, not yet decided:**
  - *CSV + JSON (resume-builder today):* zero infrastructure, human-
    inspectable, already proven at real scale (209+ JDs). Cons: no real
    query/indexing (dedup is hand-rolled Python, not a query), weak
    concurrent-write safety, schema changes mean touching every read/
    write site by hand.
  - *Markdown/YAML (career-ops):* maximally human-readable/editable, fits
    the "human eyes on every application" philosophy best, diffs read
    like prose. Cons: same lack of querying as CSV, and more fragile to
    parse back into structured data reliably; career-ops's own file-based
    system/data boundary already failed once in practice (see the
    archive's incident history) -- not a persistence-format bug
    specifically, but a reminder that "just files" isn't automatically
    safe.
  - *MongoDB (job_automater):* real queries/filtering/sorting, genuine
    multi-writer concurrency safety, flexible schema, already proven with
    83 real records. Cons: the only option needing a background service
    (Docker) running at all times; not human-inspectable without separate
    tooling (mongosh/Compass), cutting against this project's consistent
    inspectable-by-default pattern.
  - *SQLite (not one of the three above, floated as a possible fourth
    path):* real transactional safety and queries without a daemon/
    Docker -- a single portable file, `sqlite3` is in Python's stdlib.
    Solves the scheduler's concurrent-write concern reasonably well (WAL
    mode lets readers and a writer coexist, though it's still
    single-writer-at-a-time, not true multi-writer concurrency). Cons:
    loses inspectability too (a `.db` file needs the `sqlite3` CLI or a
    GUI tool, not a text editor); not git-diffable (less of a loss here
    since these trackers are already gitignored for PII); real
    schema/migration discipline instead of freeform files; a new
    SQL-query paradigm in a codebase that's been 100% pandas/CSV/JSON
    manipulation so far; and it may be solving a concurrency problem that
    doesn't fully exist yet -- the benefit mainly kicks in once the
    scheduler (below) is actually running unattended, not at today's
    scale.
  - **Leaning:** keep the human-facing tracker as markdown/YAML (or CSV)
    for inspectability; revisit SQLite specifically for the scheduler's
    concurrent-write needs when that build actually starts, rather than
    adopting it preemptively. Still not decided -- reference material for
    when this choice actually gets made.

**Agreed direction (brainstormed 2026-07-04, not yet a build plan):**

- **One codebase, one CLI.** resume-builder stays the surviving identity
  (a rename is a someday-detail, not a now-decision). Python throughout --
  career-ops's `.mjs` pipeline logic gets ported during the merge; its
  markdown/YAML tracker *format* carries over as-is, since that's just
  data.
- **The evidence bank ("the brain") -- the piece Morgan was most decisive
  about ("that's what I've been working toward... that is the brain, and
  a must").** Not a rebuild -- an extension of what already exists and
  already works: `bullet_feedback.py`, `triage_needs_review.py`, the
  verified-bullet CSV schema, the truthfulness/critique prompts. New
  evidence *types* get added alongside resume bullets -- STAR+R interview
  stories, cover-letter proof points, negotiation talking points,
  company-fact notes -- each keeping the same verification metadata
  (believability score, source, keep/retire status) that already governs
  resume bullets today. Different renderers (resume-bullet, interview-story,
  cover-letter-paragraph) pull from the same audited pool, filtered by
  which evidence rows are tagged applicable to that output type. This is
  also the piece that directly informs Dominick's onboarding -- see
  Multi-user support below. (Phase 1 of this is done -- see
  `IDEAS_ARCHIVE.md` for the full research/build writeup. **Decoupled from
  career-ops specifically, 2026-07-21** -- source material for new evidence
  types doesn't need to come from career-ops's files; Morgan has this
  material in other places too and can supply it whenever this gets picked
  up. See the Medium and Very-Hard/Long-term tiers below for the two pieces
  this split into.)
- **Pipeline + CLI.** Each stage (`scan`, `evaluate`, `tailor`, `render`,
  `track`, `interview-prep`) is a Python module with a defined in/out
  contract, runnable standalone or chained. The CLI itself gets
  job_automater's `cli.py`/`cli_art.py` polish (rich/click, the banner,
  interactive mode) as its skin, made "a tiny bit smoother/prettier" per
  Morgan's note. `scan` runs both career-ops's board-providers
  (Ashby/Greenhouse/Lever/etc.) and job_automater's scrapers
  (LinkedIn/JobRight) as parallel source plugins feeding one output shape.
  `evaluate` ports career-ops's fit-scoring. `tailor`+`render` are
  resume-builder's existing, already-proven pipeline, untouched. `track`
  adopts career-ops's markdown/YAML tracker.
- **Scheduler + notifications -- the other piece Morgan was decisive
  about** ("a system that runs continuously and brings things to me").
  Saved searches run on a schedule via **local launchd jobs** (her choice
  over cloud scheduling -- no dependency on Claude Code being open), each
  invoking `resume scan --saved-search <name>` headlessly. There's a
  single scored list, not two separately-maintained tiers: matches
  scoring **>=90 land on a review list**; matches scoring **>=95
  ("all-star") additionally auto-trigger `tailor`+`render`**, so a truly
  exceptional hit has a ready PDF sitting in a folder before Morgan has
  even looked at it. Every run ends with **both** a macOS local
  notification (quick heads-up count) and an email digest (the readable
  summary, with pre-generated PDFs attached/linked for all-stars).
  Nothing here ever applies or submits anything -- the entire scheduler's
  output is "things placed in front of Morgan to approve." Confirmed
  2026-07-06: the email digest sends via `smtplib` + a Gmail app password
  in `.env`, consistent with this repo's existing patterns. Still fully
  unresolved: the exact launchd job layout (one job per saved search vs.
  one dispatcher job iterating all of them).
- **Explicitly deferred, not decided against:** a career-ops-style
  dashboard/TUI (Morgan's call: "later nice-to-have," not blocking the
  core pipeline). **Decided against, not deferred:** ATS auto-apply/
  auto-submit and LaTeX rendering.

No implementation has started; this is scope-awareness plus an agreed
direction for when that build actually begins, not a plan with a start
date.

### Multi-user support -- let other people (starting with Dominick) use this

**Update 2026-07-16: the "harder problem" below (raw material -> first-draft
bullets) is genuinely solved -- but shipped a materially different shape
than the 2026-07-04 brainstorm decided on.** `bootstrap_extractors.py`/
`bootstrap_timeline.py`/`bootstrap_profile.py`, built 2026-07-12/13, extract
achievements from arbitrary uploaded documents into
`bullet-bank-clean.csv` and draft `cv.md`/`user-background-guide.md`,
reachable self-serve via a "New User? Start Here!" menu entry
(`bootstrap_bullet_bank.py`). What's different from the brainstormed
sequence below: it asks guess-confirm-or-edit questions immediately after
ingestion rather than surfacing gaps only after a first thin resume, has no
lenient onboarding-specific quality bar or top-2-3-gap cap, and never
generates an actual resume -- so the "watch it come alive" garnish Morgan
was most specific about didn't make it in. Full comparison in
`IDEAS_ARCHIVE.md`'s daily build log. Worth a conscious call on whether the
shipped version is good enough as-is before Dom's actual onboarding
session.

**Update 2026-07-17: point 1 (engine/profile split) is now built, and
three same-day follow-up passes closed every Morgan-specific gap found so
far -- archived.** `profiles/<name>/`, `scripts/profile_paths.py`, every
script's path constants, every remaining Morgan-specific constant in
`orchestrator.py` (mining floors, persona framing, deep-evidence gating,
filename prefix), a separately-hardcoded education achievement-bullet
system, and a third-pass sweep that found and closed 7 more gaps outside
`orchestrator.py`'s builder-schema path (`normalize_resume.py`'s career-note
trigger, cv.md section-excerpt keywords, two hardcoded trim-step
instructions, LLM-facing "Morgan's career" guardrail text,
`validate_coverletter.py`'s third-person-name/pronoun check, and
`scan_linkedin.py`'s saved searches) -- are all done. Full technical
writeup in `IDEAS_ARCHIVE.md`'s "Engine/profile split: orchestrator.py
Morgan-specific constants closed" entry.

**Update 2026-07-17 (a fourth pass, same day): the tag taxonomy is now
per-profile, and `rewrite_bullets.py` -- wrongly reported as dead code in
the third pass above -- turned out to be live in Dom's actual onboarding
wizard and got the same fixes as `orchestrator.py`.** A new `profile.yml`
`tags:` field, generated during bootstrap from the candidate's own target
roles + real achievement text (`bootstrap_extractors.generate_tag_taxonomy()`),
replaces three separately-hardcoded, already-drifted copies of Morgan's
marketing-specific `[email]`/`[ops]`/etc. taxonomy
(`orchestrator.py`'s `TAG_CONTEXT`+`CLAIM_TAG_KEYWORDS`, `tag_bullet_bank.py`'s
`TAG_KEYWORDS`) -- `tag_bullet_bank.py` is what actually auto-tags a new
profile's bullets during bootstrap ingestion. `rewrite_bullets.py` is
imported by `bootstrap_profile.py` for the CV-drafting step (`_polish_bullet()`),
`audit_keepers.py`, and `bullet_feedback.py`, and carried the exact same
hardcoded Morgan persona/Treering-evidence/"Morgan's career" content
`orchestrator.py` had before this pass -- meaning every bullet polished
during a new profile's onboarding was getting Morgan's identity injected
into the prompt. Now fixed identically. A second, unrelated bug from the
third pass was also caught here: `BACKGROUND_IDENTITY`/`BACKGROUND_TAGS`
were moved to `fixed_content.py` without adding empty defaults to the
bootstrap scaffold, so a fresh profile's first real build would have hit a
hard crash, not a graceful degradation -- now fixed with a regression test
that exercises the real consuming functions, not just checks for attribute
names. Full writeup (including the grep-command mistake that caused the
"dead code" misreport) in the same `IDEAS_ARCHIVE.md` entry, "Update... a
fourth pass" section.

Net effect: a second profile's actual resume build, bootstrap onboarding
(including bullet polishing and auto-tagging), cover-letter validation,
and LinkedIn scan all now read their own data from
`profile.yml`/`fixed_content.py`, with zero remaining Morgan-specific
fallback found across four full sweeps. Only remaining blocker before
Dom's first real build is #7 (per-user `.env` secrets).

**Other follow-ups noted in the same review, lower priority:**
- `scripts/liveness.py:19`'s temp file (`LIVENESS_INPUT_PATH`) writes to
  top-level `output/`, not `output/<profile>/` -- two profiles running
  liveness checks at the same moment could collide on it. Minor,
  transient file, not real data.
- Morgan's own existing operational data (`jds/`, `output/checkpoints/`,
  `data/applications.md`) sits at the old top-level paths from before
  the split -- a one-time manual move into `jds/morgan/`, `output/morgan/`,
  `data/morgan/` is needed the next time these are touched, or the
  pipeline will look for pending JDs/checkpoints and quietly find none.
- `CLAUDE.md` still documents `jds/`, `output/checkpoints/`, and
  `jds/jd_tracker_log.csv` at top level -- stale, worth a quick pass
  once the above settles.
- `build_role_rules_block()` (`orchestrator.py`) uses direct dict-key
  access on `roles:`/`fixed_credentials:` entries -- degrades
  gracefully when a section is missing entirely, but a hand-edited
  `profile.yml` with a *partially*-filled-in role/credential row would
  raise `KeyError` instead of degrading. Only matters once someone's
  hand-editing `profile.yml` directly rather than through bootstrap.

**Scope note:** roughly tied with the merge as the biggest item here --
and this has a real name and real deadline pressure attached rather than
being purely speculative: Morgan has promised Dominick ("Dom") that he'll
get to try this, and he's actively excited about it. That doesn't change
the scope, but it does mean this shouldn't sit indefinitely once the
merge's evidence-bank work is underway -- Dom's onboarding is the first
real test of it.

Splits into a mechanical (if broad) half -- separating engine from
per-user profile data -- and a genuinely unsolved half: designing an
onboarding flow that gets a brand-new user to a usable, trustworthy bullet
bank fast. That second half is a process/UX design problem, not an
engineering one.

Right now the whole pipeline is Morgan-specific, not just in data but in
structure: `scripts/fixed_content.py` is literally her contact info/company
facts/certifications/education as Python constants, and
`resume-engine/prompts/tailor_resume.md` + `resume-engine/rules/*.yaml` are
written assuming her specific companies, roles, and voice.

**1. Generalizing the engine.** Splitting "engine" (generic pipeline logic)
from "profile" (a per-user directory holding their own fixed-content
equivalent, bullet bank, and knowledge base) so a second person's data
doesn't live inside Morgan's files. Mechanical but broad -- touches most of
`scripts/` and `resume-engine/`.

**A real-world cautionary tale for this exact split, not a hypothetical:**
career-ops has almost this same engine/profile split on paper
(`DATA_CONTRACT.md`'s System Layer vs. User Layer) and it still failed in
practice in June 2026 -- an auto-update silently overwrote Morgan's
personalization because the tool's own docs invited hand-editing "system"
files directly, so real customization ended up there anyway (full account
in `IDEAS_ARCHIVE.md`, and in memory `project_career_ops_update_risk`).
The lesson for this split: the engine/profile boundary needs to be
structurally enforced (e.g. profile data physically can't live in
engine-owned files/paths) rather than just documented as a convention, or
the same failure mode will eventually repeat here too.

**2. The harder problem: how does a new user build their own bullet bank
in the first place**, when they don't have 100+ audited variations sitting
around already? Options raised: a guided interview/Q&A process, a profile
file/form to fill out, a LinkedIn data export, or sharing project
write-ups directly.

- **Already built and reusable:** the audit/critique/scoring machinery
  (`resume-engine/prompts/critique_bullet.md`, `rules/truthfulness_rules.yaml`,
  `rules/language_quality.yaml`, `rules/verb_taxonomy.yaml`, etc.) already
  takes a rough, self-written bullet and scores it for credibility, banned
  language, vague verbs, and believability, then proposes a rewrite. That's
  exactly the "polish a new user's rough draft into a verified bullet" step
  -- and it's the same machinery already battle-tested on Morgan's own
  material.
- **Not built yet, a real gap:** nothing today turns raw source material --
  a LinkedIn export, an old resume, project write-ups, or an interview
  transcript -- into first-*draft* bullets in the first place.
  `extract_evidence.md` (despite the name) deconstructs an *existing*
  bullet to check its credibility; it doesn't generate new ones from raw
  material. That initial extraction step is the thing to actually design/
  build.
- **The genuinely hard part isn't mechanical.** This whole system's identity
  is "never fabricate, everything traceable to real verified history."
  Morgan's bullet bank got that grounding from years of lived history plus
  a lot of manual auditing across many CSV iterations. A new user's
  onboarding flow has to front-load that same rigor in far less time --
  that's a process/UX design question (how much interview depth is
  enough?) more than an engineering one.

**Refined onboarding idea (2026-07-03): light seed + grow-as-you-go, not a
big upfront audit.** Morgan's proposal: a new user doesn't need 1,000+
pre-audited bullets -- just one existing resume, a filled-out profile/a few
Q&A answers, maybe a LinkedIn PDF export and a couple project docs, as a
*seed*. The bullet bank then grows naturally over real usage, as the builder
rewrites/expands that seed material differently per JD.

This is sound, but it changes *where* the truthfulness verification happens:
- Today, verification is front-loaded -- the bullet bank is pre-audited once,
  and the per-JD builder is bounded to rephrasing/selecting from an
  already-trusted pool (never fabricate is enforceable because the pool
  itself was vetted first).
- In the light-seed model, verification has to move to *per-run human
  review* instead -- the user reviews/approves each newly generated resume
  (as they naturally would anyway), and that approval is what confirms a
  newly expanded or reworded bullet didn't drift into embellishment. That's
  a perfectly reasonable trade (arguably closer to how a human resume writer
  actually works with a new client), just a different mechanism than what
  this codebase currently has -- the "never invent a metric that wasn't in
  the source material" guardrails need to hold during that expansion step,
  not just during selection.
- **The harvest-back loop already exists** for Morgan's own bank:
  `scripts/bullet_feedback.py`, wired into `orchestrator.py`'s bullet-audit
  step, already queues any accepted bullet rewrite that clears the bank's
  real "KEEP" bar (`decide_action() == KEEP` and `manager_test == PASS`)
  into `needs-review.csv` automatically, during every resume build.
  `scripts/triage_needs_review.py` then routes those queued rows: PASS +
  believability >=80 -> `bullet-bank-keepers.csv` (permanent); FAIL with
  attempts left -> `rewrite-queue.csv`; FAIL, out of attempts ->
  `retired-bullets.csv`. So "grows over time" is already real for Morgan's
  own bank today -- the multi-user version of this is "make this per-user
  scoped" (each user's own needs-review/keepers/retired CSVs), not "invent
  it from scratch." Also worth noting: promotion into the permanent
  keeper bank isn't fully automatic -- `triage_needs_review.py` is a
  separate run, which is itself a nice built-in curation checkpoint, and
  maps well onto the "verification moves to human review" idea above.
- Expect the first few resumes for a brand-new user to be thinner/less
  specific than what Morgan gets today, simply because there's less pool to
  draw from yet -- that's an inherent, expected bootstrapping curve, not a
  bug to fix.

**Onboarding flow, brainstormed 2026-07-04: upload-first wizard + a
visible-growth reveal.** Three shapes were floated -- a pure Q&A wizard
with no document parsing, an upload-first wizard that only asks follow-ups
for gaps, and a fully conversational Claude-Code-driven intake. Morgan
picked the upload-first wizard, plus a specific garnish:

- **Data location:** shared resume-builder repo, `profiles/dominick/`
  alongside `profiles/morgan/` -- not his own separate fork. Chosen so he
  stays on the same engine improvements as Morgan, but this raises the
  stakes on point 1 above: with two real users sharing one repo, the
  engine/profile boundary has to be *structurally* enforced (profile data
  physically can't live in engine-owned paths), not just a documented
  convention -- the career-ops cautionary tale is no longer abstract once
  a second real person's data is in the repo.
- **Self-serve, no live guidance from Morgan:** a `resume onboard`-style
  wizard, closer to job_automater's existing `setup_wizard.py` pattern than
  a guided session with her.
- **The flow itself:** Dom uploads whatever he already has (old resume
  file, LinkedIn PDF export) as a seed. This requires actually building the
  extraction step flagged as a real gap above -- turning raw source
  material into first-*draft* bullets, not just critiquing bullets that
  already exist. The wizard then only asks targeted follow-up questions for
  whatever the material didn't cover (a missing metric, an unclear "so
  what"), rather than making him answer a full Q&A from a blank page.

  **Extraction step's gap-detection depth, resolved 2026-07-04:**
  - **Gaps surface *after* the first resume, not before.** Upload triggers
    silent extraction straight through to a rendered first (expected-thin)
    resume, with zero blocking questions. Follow-up questions are what
    *drives* the second pass, not a separate checkpoint in front of it --
    this ties the extraction step directly into the garnish below rather
    than competing with it.
  - **A lenient, onboarding-specific quality bar, not the production
    believability bar.** Reusing the real per-type resume-bullet threshold
    (set for the evidence bank above) would flag nearly everything on a
    rough first upload -- deliberately looser here since early material is
    already expected to be thinner.
  - **Capped at the top 2-3 highest-impact gaps, not a full list of
    everything under the bar.** Chosen over both a fixed full-list batch and
    an adaptive-bar-that-tightens-over-time approach: a full list risks
    feeling like homework on a rough upload, and a tightening bar is more
    machinery than day one actually needs. Everything below the cap rides
    along as "thin for now" and improves through ordinary future runs, the
    same way Morgan's own bank already grows today -- not through a formal
    onboarding gate. **Flagged refinement for later, not a prerequisite:**
    the cap itself could loosen slightly in later sessions if Dom's
    engaged, borrowing a light touch of the adaptive idea without building
    its full machinery up front.
- **The garnish Morgan specifically wanted:** make the first session feel
  like watching the system come alive, not filling out a form. Generate a
  first (expected-thin, per above) resume early in the flow, then show him
  the visible improvement after he adds a bit more in a second pass --
  turning "the bank grows over time" from an invisible mechanism into
  something he actually watches happen, in his very first session.
- **Connects back to the merge's evidence-bank design** (see the Long-term
  merge section above): the extraction step being built here -- raw
  material into first-draft evidence -- is the same missing piece the
  evidence bank will eventually need for evidence types beyond resume
  bullets too (interview stories, cover-letter proof points). Worth
  designing it generally rather than resume-bullet-specific if that's not
  much extra work, so it isn't rebuilt twice.

No design work has started on the implementation of any of this; the
onboarding flow above is a brainstormed direction, not a plan.
