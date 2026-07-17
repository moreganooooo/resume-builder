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
| 4 | Engine/profile rules audit + split | Medium-Hard | Unblocks all multi-user work. See Multi-user support below. |
| 5 | Evidence bank extension (Tier 2) | Hard | Phase 1 shipped 2026-07-07 (archived). Tier 2 -- raw "Treering Sequences" archive curation, `BestCopySamples`/`Master Cover Letters` skim -- still unscheduled. |
| 7 | Per-user secrets (`.env` per profile) | Easy | Quick prerequisite right before Dom's onboarding. |
| 8 | Dominick's onboarding | Hard | The onboarding wizard's own logic (extraction + profile personalization) shipped 2026-07-12/13 -- see the Multi-user support section below. Still blocked on #4 (no `profiles/<name>/` isolation yet -- a second user would overwrite Morgan's files today) and #7. |
| 9 | Scheduler + notifications | Hard | Unblocked -- `scan` and `evaluate` stages both exist. Not started. See the Long-term merge section below. |
| 10 | Mongo migration | Medium | The liveness-check half of this item is done (archived). Migration itself still undone -- tied to the long-term three-way merge. |
| 11 | Multi-select "Specific JD" pickers (space-bar toggle) | Medium-Hard | Real open design question: how it coexists with `resume run --pick`'s existing evaluate-then-checkbox flow. See below. |
| 12 | Help command in the interactive menu | Easy | `resume help` already exists as a shell shortcut; just needs a menu entry. See below. |
| 13 | "Doctor" script (dependency/asset checks + test run) | Medium | See below. |
| 14 | Bullet-bank reintegration menu option + eventual "Maintenance" submenu | Hard | Bullet-bank menu done 2026-07-15, including a real maintenance section inside it. Still open: a top-level, cross-feature "Maintenance" submenu (would also house #13's doctor script). See below. |
| 15 | "List Jobs" / "View Pipeline" browsing command | Hard | A real first step already exists ("View Application Tracker," 2026-07-08) and `Score`/`Report` are now wired to the real `evaluate` stage (2026-07-16). Still covers a narrower slice -- no drill-in or Skip/Archive action. See below. |
| 16 | Skip recently-checked JDs in liveness (like evaluate's skip-by-default) | Medium | Close parallel to the evaluate skip-by-default feature (archived) -- same pattern, plus a time-window twist. See below. |

**Deliberately left off this pass:** an `interview-prep` pipeline stage
(porting career-ops's `modes/interview-prep.md`) -- Morgan's call, not
essential right now, revisit later if it turns out to be needed. Still a
real capability worth having eventually, just not part of this ordering.

## Easy

### Rotate the leaked LinkedIn `li_at` cookie

Found during the 2026-07-04 merge research, still unresolved: a local
script in the job_automater working copy
(`scrapers/recommended_scraper.py`, not part of the actual upstream
project) has a LinkedIn `li_at` session cookie hardcoded in plaintext.
It's a live credential still sitting on disk. Rotate it, and don't carry
that file forward into any future merge work. Full context in
`IDEAS_ARCHIVE.md`'s "Long-term merge: incident history" section.

### The Johnson County Community College education line wraps

It currently wraps to a 2nd line at the real printed page width (KU/KCKCC
don't anymore, after shortening their degree names) -- low priority, not
something Morgan has flagged as a problem.

### Help command in the interactive menu

`resume help` already exists -- but only as a shell shortcut
(`scripts/resume-cli.sh`'s `help)` case, a hardcoded list of `echo` lines
describing every command). It isn't reachable from inside the interactive
menu itself, and Click's own auto-generated `--help` flag on
`scripts/cli.py` is a separate, third copy of similar information. Adding
a "Help" entry to `menu.py`'s `_CHOICES` that prints an equivalent summary
closes that gap. Mechanical, no open design question -- the only minor
wrinkle is that the content would then live in two (arguably three)
places unless something shares a single source of truth between the
shell script's static text and whatever the menu option prints.

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

### Modernize emojis in rewrite_bullets.py / orchestrator.py

The interactive menu's icons went through a real design pass
(`theme.py`'s `ICONS` dict, Nerd Font default + plain-Unicode fallback
via `RESUME_BUILDER_ICONS=unicode`), but `rewrite_bullets.py` and
`orchestrator.py`'s print statements still use the older, ad-hoc emoji
set (📥📋✅⚠️📌🔥📦🖊️💫💯✏️🔧 etc.) picked before that system existed. No
open design question -- swap each emoji for its `theme.ICONS` equivalent
where one exists, framework-consistent print styling otherwise -- but
real volume: two large files, dozens of print statements each, worth
its own focused pass rather than folding into an unrelated change.

## Medium

### Liveness skip-by-recency (persist a check date, skip if checked recently)

A close parallel to the evaluate skip-by-default feature built
2026-07-08 (`batch_evaluate.split_evaluated()`/`save_evaluation()`) --
same shape, applied to `liveness.py` instead. Today,
`run_liveness_check()` persists nothing for `active`/`likely_active`/
`uncertain` results (only `expired` triggers a real action, moving the
file to `jds/expired/`) -- every result is printed once and forgotten, so
re-running liveness re-checks every pending JD's URL every time, even one
confirmed `active` five minutes ago. The ask: persist a `_liveness` block
(result, reason, `checked_at`) into each JD's own JSON, matching
`_evaluation`'s existing pattern, and skip re-checking any JD whose
`_liveness.checked_at` is within some recency window (Morgan suggested 24
hours) by default.

**The one real twist vs. evaluate's skip logic:** evaluate's skip is
permanent (a JD either has been evaluated or hasn't -- no expiry), while
this needs an actual time comparison (`checked_at` newer than N hours ago
-> skip; older -> re-check). Otherwise the same shape applies: a
`--refresh`-style escape hatch to force-recheck everything, and the
confirmation-prompt-accuracy lesson from the evaluate fix (show the real
count of JDs *about to be checked* after the skip filter, not the raw
pending count, learned the hard way on 2026-07-08). Also needs
`jd_manager.read_jd_text()`'s same underscore-key-stripping treatment if
liveness's checker ever reads JD content directly rather than just the
`source_url` field it already extracts today.

### Multi-select pickers for "Specific JD" actions

Today, `picker.pick_one_pending_jd()` and `picker.pick_one_evaluated_jd()`
(used by "Evaluate a Specific JD," "Write cover letter for a Specific
JD," and "Customize Resume for a Specific JD") are single-select
(`questionary.select()`) -- pick exactly one JD, act on it, done. The
ask: let these toggle multiple selections via the space bar (like
`questionary.checkbox()`, which `pick_and_process()` -- the
evaluate-then-checkbox flow behind `resume run --pick`/`resume
coverletter --pick` -- already uses) and act on every checked JD in one go.

**The open design question:** this would functionally overlap with what
`--pick` already does, just without `--pick`'s fresh full-batch
evaluation step first. Worth deciding explicitly: does the "Specific JD"
picker become multi-select and subsume single-select (space to check one
or many, enter confirms), or does it stay single-select with a separate,
new multi-select entry point alongside it? The former is probably the
more natural fit for how these are actually used, but changes an existing
interaction pattern people already have muscle memory for. Whichever
direction, the mechanics themselves are well-understood
(`questionary.checkbox()` is already proven in this codebase) -- the
three menu handlers (`_handle_evaluate_one`, `_handle_coverletter_one`,
`_handle_tailor_one`) would need to loop over a list of paths instead of
handling exactly one, and their "one" naming would need revisiting.

### "Doctor" script -- dependency/asset checks + test run

job_automater has real prior art for this exact pattern (full detail in
`IDEAS_ARCHIVE.md`'s incident history): `system_checker.py` (Python
version, MongoDB, pdflatex, pip) plus `config_validator.py` (API keys,
contact fields, etc.) together form its "doctor" equivalent, run via its
`setup`/`validate-config` commands. resume-builder's own version would
check things specific to this pipeline instead: Python 3.10+, `.venv/`
exists with `requirements.txt` installed, Node + Playwright's Chromium
browser installed, `GEMINI_API_KEY` (and `JOBRIGHT_COOKIE_STRING` if scan
is used) present in `.env`, the static DM Sans font files exist at
`resume-engine/fonts/`, `docs/MorganEscottSignature2025.png` exists (the
README already documents this one degrading gracefully if missing, but a
doctor script could flag it proactively instead), and the `KB_ALLOWLIST`
files `orchestrator.py` references are all actually present on disk.
Ending with a real test-suite run
(`python -m unittest discover -s tests`) and a plain-English summary of
what passed/failed/is missing, with a one-line suggested fix per problem
found, completes the picture. No genuinely open design question here --
it's broad (touches the Python env, Node env, filesystem, API keys, and
tests) but every individual check is a simple, well-understood
existence/version check.

## Hard

### "List Jobs" / "View Pipeline" browsing command

**A real first step already exists.** "View Application Tracker" (built
2026-07-08) renders `data/applications.md` as a Rich-Markdown table in the
terminal, satisfying the "browse a list" half in miniature, and its
`Score`/`Report` columns are now wired to the real `evaluate` stage
(done 2026-07-16, see `IDEAS_ARCHIVE.md`). It's still a narrower feature,
not an early version of this one: it only lists JDs that reached a
completed/tailored build (this idea wants *every evaluated job*, pending
or completed), and there's no drill-in or Skip/Archive action at all --
just a flat printed table. Everything below (archive state, richer
eval-notes persistence, the browse/detail/act UI pattern) is still fully
open.

A menu option listing every evaluated job at once (score, recommendation,
last liveness check date if the liveness skip-by-recency item above
exists, Completed/Pending status), with a "View More Details" drill-in
(full JD text + the evaluation's reasoning) and a manual Skip/Archive
action per role. Genuinely more than a picker -- it's a new interaction
shape (browse a list -> drill into one item -> take an action on it) that
nothing in `menu.py` does today; every existing picker is a single
pick-and-immediately-act flow, not a browse-then-decide one.

**Several real open questions, not just engineering:**
- **Archive as a new state.** Skipping/archiving a role needs somewhere
  to live that isn't "pending" (would keep resurfacing) or "completed"
  (no resume was built) or "expired" (liveness didn't decide this, a
  person did). A new `jds/archived/` folder mirroring the existing
  `completed/`/`expired/` pattern is the obvious shape, but worth
  confirming rather than assuming -- e.g. should an archived JD ever be
  un-archived, and does `get_pending_jds()` need to explicitly exclude it
  (the way it already excludes `completed/`)?
- **Eval "notes" may need richer persistence than exists today.**
  `save_evaluation()` currently only persists `composite_score`,
  `recommendation`, `hard_blockers`, and `evaluated_at` -- not the
  model's per-dimension reasoning from `evaluate_fit()`'s full
  `FitEvaluationSchema` result (`dimension_scores`, `archetype`, etc.).
  "Read eval rating notes" implies persisting more of that structure,
  which is a real (if modest) schema change to `_evaluation`, not free.
- **Last liveness check date** depends on the liveness skip-by-recency
  item above existing first -- there's nothing to show here until that's
  built.
- **The browse/detail/act UI pattern itself** needs its own design pass:
  paginated vs. scrollable for 300+ pending JDs, how "View More Details"
  composes with questionary's existing single-screen-per-prompt model
  (probably a sub-menu loop: list -> select one -> action menu -> back to
  list), and whether this subsumes or complements the existing evaluated
  picker (the multi-select pickers idea above is closely related --
  worth designing these together rather than separately, since both are
  about browsing/acting on the same underlying pending-JD pile).

### Bullet-bank reintegration menu option (+ eventual "Maintenance" submenu) -- menu done 2026-07-15

Built (`docs/superpowers/specs/2026-07-15-bullet-bank-management-design.md`,
archived): a "Manage Bullet Bank" entry in the main interactive menu
(`scripts/bullet_bank_menu.py`), surfacing a status table across all 6
pipeline stages plus the `triage_needs_review.py`/`retire_rewrite_queue.py`
maintenance scripts. The open pipeline-order question this section used to
flag (whether `triage_needs_review.py` -> `score_keeper_gems.py` ->
`embed_bullet_bank.py` was the real, correct chain) got resolved as a side
effect of the same build, alongside the `cluster_bullet_bank.py` ->
`bullet-bank-clustered.csv` naming mismatch -- see `IDEAS_ARCHIVE.md`'s
daily build log and Evidence bank Phase 1 section for full detail.

**Still open, not part of that build:** the broader "Maintenance" submenu
idea below (grouping this alongside a future doctor script and anything
else administrative) -- today maintenance only exists nested inside
"Manage Bullet Bank," scoped to the bullet bank specifically, not as its
own general category one level up in the main menu.

**The "Maintenance" submenu idea:** rather than bolting bullet-bank
triage directly onto the main menu list, Morgan's suggestion is a
dedicated "Maintenance" entry leading to its own submenu of
background/administrative tasks (this bullet-bank reintegration flow,
and eventually the doctor script above, maybe others later) -- each
showing something like "Last run: 2026-07-07, 3 days ago." That needs a
small persisted "when did this last run" marker per task (a gitignored
JSON/text file per task, following this project's existing tracker-file
conventions, is probably the simplest option) -- not itself hard, but
worth designing once there's more than one maintenance task to actually
house in it.

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
  stories (from career-ops's story bank), cover-letter proof points,
  negotiation talking points, company-fact notes -- each keeping the same
  verification metadata (believability score, source, keep/retire status)
  that already governs resume bullets today. Different renderers
  (resume-bullet, interview-story, cover-letter-paragraph) pull from the
  same audited pool, filtered by which evidence rows are tagged applicable
  to that output type. This is also the piece that directly informs
  Dominick's onboarding -- see Multi-user support below. (Phase 1 of this
  is done -- see the Evidence bank extension row in the build-order table
  above and `IDEAS_ARCHIVE.md` for the full research/build writeup.)
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
session. **Still true regardless:** point 1 below (engine/profile split) is
unbuilt -- bootstrap writes into Morgan's own single-user file layout, so
Dom can't actually use this today without either overwriting her live
files or #4/#7 landing first.

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
