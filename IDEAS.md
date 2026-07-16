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

## Suggested build order (2026-07-04 roadmap)

A cross-cutting priority pass over the backlog below, not a replacement for
the difficulty tiers -- this is *which order*, the tiers below are still
*how hard*. Ordered by dependency, with Morgan's explicit call that the CLI
goes first; item 1 is broken into sub-steps reflecting "fastest payoff
first, biggest lift last" within that phase. **Update 2026-07-04: all of
1.1-1.4 are now built** (see the per-row notes below). **Update
2026-07-05: items 2 (situational role-swap), 3 (cover letter generation),
6 (company-values/tone-mirroring), and 10 (liveness check, Mongo migration
still undone) are also done.** **Update 2026-07-07: item 5 (evidence bank
extension) Phase 1 is done** -- see its row below; the full multi-type
generalization remains unscheduled. Items 4, 7, 8 are still unscheduled/
not started; item 9 (scheduler) is unblocked but not started. **Update
2026-07-07 (later the same day): two off-backlog quality-of-life items
also shipped, surfaced by live usage rather than originally planned --
console output polish (theme-safe blue/green colors replacing
theme-dependent `cyan`, bordered panels for the title banner and "What's
next?" prompt, a collapsed trim-loop PDF block, a one-line
keyword-extraction summary, Step-header dividers; spec:
`docs/superpowers/specs/2026-07-07-console-polish-design.md`) and an
evaluated-only, scored, sorted resume picker ("Customize Resume for a
Specific JD" now only lists JDs someone has actually run "Evaluate"
against first, persisted into each JD's own JSON so re-displaying a score
never costs another Gemini call; spec:
`docs/superpowers/specs/2026-07-07-evaluated-resume-picker-design.md`).
See the README's "Interactive menu" and "Evaluating fit" sections for the
user-facing behavior. **Update 2026-07-07 (evening):** a live scan run
surfaced a real crash (`scan.py`'s `_write_jd_file()` called a
never-defined `jd_manager._sanitize_for_filename` instead of the real
`sanitize_for_filename` -- present since the scan stage was first built
2026-07-04, only triggered once a scan actually had a genuinely new job
to write; fixed, and `tests/test_scan.py` now exists to cover the gap
that let it slip through untested). Also added: batch-evaluate call
pacing (15 RPM Gemini tier limit was being hit instantly on a fresh
batch), a `[i/N]` progress counter for batch evaluate, a "please wait"
notice for liveness checks, 2-decimal score formatting and tier-colored
scores in the resume picklist, a corrected confirmation message on
"Customize Resume for ALL Pending JDs" (it never actually evaluates
anything, despite previously saying "About to evaluate..."), and a
JobRight/LinkedIn/Both source picker for the menu's "Scan for New
Postings" (the CLI's `--source` flag already supported this; the menu
just hardcoded both with no prompt). **Next-day follow-up:** "Evaluate
ALL Pending JDs"/`resume evaluate` now skip any JD that's already been
evaluated by default (a real Gemini call was being re-spent re-scoring
already-scored JDs every run) -- `resume evaluate --refresh` forces a
full re-evaluation when actually wanted. `resume run --pick`/`resume
coverletter --pick` deliberately keep their own always-fresh-evaluate
behavior (their whole point is a complete, current checkbox list, not
one silently missing anything already scored) -- caught and fixed a real
near-miss where `pick_and_process()` would have quietly inherited the
new skip-by-default instead. Also fixed a related inconsistency:
`resume evaluate <jd_file>` (the single-file CLI path) never persisted
its score at all, unlike the interactive menu's "Evaluate a Specific
JD" -- both now save consistently. `tests/test_cli_evaluate.py` is new
(zero coverage existed on the `evaluate` CLI command before this).
**Same-day follow-up:** the skip filter itself worked, but the
confirmation prompt shown *before* it ran still said "About to evaluate
302 pending JD(s)..." (the raw, unfiltered pending count) rather than the
56 actually about to get a real Gemini call -- easily read as "it's not
skipping anything." New `batch_evaluate.split_evaluated()` lets both
`menu._handle_evaluate_all()` and `cli.py`'s `evaluate` command filter
*before* confirming, so the number shown now matches the real work about
to happen, with an explicit "(N already-evaluated JD(s) will be
skipped.)" line. Also: a manual dry-run test against real pending JDs
while debugging this (mocking the Gemini call but not the file write)
briefly wrote fake placeholder scores into 56 real JD files -- caught
immediately and fully reverted, but a reminder to mock `save_evaluation`
too next time, not just the API call, when testing against real files.
**Separate follow-up the same day:** Morgan spotted real duplicates
still showing up in the resume picklist after asking scanning to dedupe
better -- traced to a genuinely different case than the one already
fixed (JobRight assigning two IDs to the same posting). This one is the
same real job cross-posted on *two entirely different platforms* (e.g.
the company's own ATS/Workday/Rippling listing via JobRight, and a
separate LinkedIn scrape of the same opening) -- no source_job_id or
source_url in common at all between the two, so neither existing check
could catch it. Confirmed against 4 real duplicate pairs already sitting
in `jds/` before fixing. `job_key_known()` now also matches on an exact
normalized (lowercase, alphanumeric-only) company name + job title --
deliberately no confirmation step, per Morgan's call, since a company
posting two genuinely distinct open roles under the identical title is
rare enough not to warrant one.

**Same-day, unrelated but important finding: a real test-isolation bug had
been silently corrupting `data/applications.md` on every test-suite run.**
Morgan asked for a posting-link feature ("where would I go to review the
job post and start an application?"), and checking the tracker file to
plan it surfaced something worse -- 63 fresh "unknown/unknown" rows had
already accumulated in the 2 days since the file was fully reset
2026-07-07, despite `jds/completed/` being empty and `jd_tracker_log.csv`
not even existing (i.e. zero real resume builds had happened in that
window). Root cause: `tests/test_orchestrator_main_batch.py` calls the
real `orchestrator.main()` with `COMPLETED_DIR` safely redirected to a
temp dir, but never redirected `APPLICATIONS_MD` or mocked
`append_application_row()` -- so every real test-suite run (and this
session ran the full suite dozens of times today alone, verifying each
fix) silently appended a fake row using the fake `good.txt`/`bad.txt`
fixture paths' empty company/title. **This means the 2026-07-07
"unknown/unknown" investigation's conclusion was wrong** -- those weren't
historical `dummy_jd.txt`/smoketest-fixture leftovers as assumed at the
time, they were this same leak, already active before it was ever found.
Fixed by redirecting `APPLICATIONS_MD` to a temp path in that test's
`setUp`/`tearDown`, matching the existing `COMPLETED_DIR` pattern; the
real file was reset again afterward. Built alongside: `data/applications.md`
now has a `Link` column (`[Apply](source_url)`) so there's actually
somewhere to click through to the real posting once a resume's done --
new `jd_manager.extract_source_url()`, extracted before the JD file
moves to `jds/completed/` (extracting after the move would read a path
that no longer exists). `tests/test_applications_md.py` is new (zero
coverage existed on `append_application_row()` before this). **Also
added the same day:** a "View Application Tracker" menu option
(`cli_art.display_applications_tracker()`) that renders
`data/applications.md` directly in the terminal via Rich's built-in
Markdown renderer -- table and clickable links included, no custom
parsing needed since the file is already valid GFM markdown.

| # | Item | Difficulty | Notes |
|---|------|-----------|-------|
| 1.1 | **CLI skin over existing tailor+render** -- **done 2026-07-04** | Easy-Medium | Built: `scripts/cli.py` (Click, `tailor <jd_file>`/`run`) + `scripts/cli_art.py` (rich banner), calling `orchestrator.run_pipeline()` (extracted from `main()`, behavior-preserving -- all 162 tests still pass). `resume run` shell shortcut now routes through it too. `click`/`rich` added to `requirements.txt`. |
| 1.2 | **`track` stage** -- **done 2026-07-04** | Medium | Built: `jd_manager.append_application_row()` appends to `data/applications.md` (career-ops's markdown format, gitignored like the CSV tracker) from `orchestrator.py`'s completion step, alongside the existing `jd_tracker_log.csv` (not replacing it). `Score`/`Report` are placeholders (`NA`/`—`) until 1.3/1.4 exist. No dedup/merge logic ported (single writer today). |
| 1.3 | **`evaluate` stage** -- **done 2026-07-04** | Hard | Built: `resume-engine/prompts/evaluate_fit.md` (career-ops's 10-dimension weighted matrix, verbatim reuse) + `ResumeEngine.evaluate_fit()` (same headless Gemini plumbing as the rest of the pipeline) + `resume evaluate <jd_file>` CLI command. Composite score computed in Python from the model's per-dimension scores, not trusted from the LLM's own math. Deliberately standalone -- no wiring into `run_pipeline()`/`applications.md` yet (no job_key to match a row against, and no `scan` stage feeding it results yet); that integration is a `1.4`-adjacent follow-up, not part of this pass. Smoke-tested live against a real JD (`jds/completed/dummy_jd.txt`): correctly scored a strong remote content-strategy match 4.8/5, "Strong pursue," with sane per-dimension reasoning. |
| 1.4 | **`scan` stage** -- **done 2026-07-04** | Hard-Very Hard | Scope decided 2026-07-04: LinkedIn + JobRight only (no career-ops `.mjs` providers this pass), writing straight into `jds/` (no Mongo, no new storage layer -- `jd_manager.job_key_known()` dedupes against `jd_tracker_log.csv` and `jds/` itself). Built: `scripts/scan_jobright.py` (ported from job_automater's `jobright_scraper.py`, zero new deps, plain `requests`) + `scripts/scan_linkedin.py` (ported from `linkedin_scraper.py`; needs `selenium`/`webdriver-manager`/`linkedin-jobs-scraper`/`beautifulsoup4`, added to `requirements.txt`) + `scripts/scan.py` (writes/dedupes into `jds/`) + `resume scan --source jobright\|linkedin` CLI command. **Real fix along the way, not in the original port:** Morgan's `li_at` cookie kept going stale under her old manual copy-paste workflow -- turned out to be LinkedIn's bot-detection invalidating sessions it suspects are automated, not the cookie being inherently short-lived (confirmed: it's set to expire in ~2027 once genuinely live). Fixed with `browser_cookie3`, reading the live cookie straight from her already-logged-in Chrome on every scan call -- automates her exact manual step, cookie never touches disk. Also caught and fixed a real bug during the live test: the port was silently falling back to `linkedin_jobs_scraper`'s deprecated `AnonymousStrategy` because job_automater's `LinkedInConfig.LI_AT_COOKIE` global-config wiring (`config.py` lines 153-157) hadn't been carried over -- added it, confirmed the log now shows `AuthenticatedStrategy`. Live-tested: JobRight twice (209 real JD files now in `jds/`, zero duplicate `source_job_id`s across both runs) and LinkedIn once at a small limit (6 real jobs fetched, `is_top_applicant` detection working) via direct fetch call (not yet run through the full `resume scan --source linkedin` write path, to avoid growing the pending-JD pile further without asking first). **Operational note:** `jds/` holds 209 real pending JDs from the JobRight test runs -- running `resume run` as-is would trigger 209 real Gemini-tailored builds. Triage with `resume evaluate <file>` (1.3) or thin the pile before batch-running. |

**Lean scope for 1.1-1.4 (2026-07-04) -- token/effort efficiency matters
to Morgan, so these are deliberately reuse-first, not rewrite-first.
Sanity-checked against the real code in job_automater/career-ops on
2026-07-04 -- corrections below folded in from that pass:**
- **1.1:** new `scripts/cli.py`, Click-based, reusing job_automater's
  `cli_art.py` banner/table style as-is. Commands (`tailor <jd_file>`,
  `run`) just call the existing `orchestrator.py` -- no internals rewrite.
  Skip a `status` command until 1.2 exists. Confirmed job_automater's
  `cli.py`/`cli_art.py` really are structured this way (Click group,
  separate banner module). One real gap: `click` isn't in this repo's
  `requirements.txt` yet -- needs adding.
- **1.2:** **correction -- this isn't a from-scratch "new capability."**
  resume-builder already has a working completion tracker:
  `jd_manager.JDTracker`, CSV-backed at `jds/jd_tracker_log.csv`
  (`job_key, job_title, company_name, source_file, status, date_processed,
  output_json, output_pdf, error_message`), already wired into
  `orchestrator.py`'s completion loop via `mark_completed`/`mark_failed`.
  So 1.2 is really "extend/reshape an existing tracker toward career-ops's
  `applications.md` format" (which adds `Score`/`Status`/`PDF`/`Report`/
  `Notes` columns career-ops's `merge-tracker.mjs`/`dedup-tracker.mjs`
  dedupe against), not building tracking from nothing -- likely smaller
  than originally scoped. Also: career-ops's `data/pipeline.md` isn't a
  second tracker table -- it's a plain checklist of pending URLs to
  scan/triage, so it's actually 1.4 (`scan`) territory, not 1.2.
- **1.3:** new `resume-engine/prompts/evaluate_fit.md`. **Correction --
  it's not an A-F letter-grade rubric.** career-ops's "A-F" refers to
  output *section* labels (Block A, B, C... plus a G legitimacy block in
  `modes/offer.md`), not a grade -- the actual score is numeric out of 5
  (e.g. `4.7/5`, matching the `Score` column above). The "10 weighted
  dimensions" claim is accurate and the real weights (from
  `modes/offer.md`) are: CV/profile match 25%, North Star alignment 20%,
  Remote quality 15%, Level fit 15%, Comp 10%, Growth 5%, Time-to-offer
  5%, Tech/tool 3%, Company reputation 1%, Cultural signals 1%. Port the
  numeric weighted rubric, not a letter-grade one. Runs through the same
  headless Gemini-API plumbing `orchestrator.py` already has
  (`gemini_client.GeminiClient`, raw REST). Don't build all 10 dimensions
  on day one if that's overkill -- start with whatever subset actually
  drives the go/no-go decision.
- **1.4:** don't port everything at once. job_automater's scrapers are
  already Python -- copy directly (confirmed: JobRight is plain REST via
  `requests`, no browser automation; LinkedIn goes through the
  `linkedin_jobs_scraper` package, which is Selenium-backed). career-ops's
  `providers/*.mjs` are Node -- shell out to them as subprocesses and
  parse JSON output rather than rewriting them in Python. **Correction --
  there are ~26 providers in `providers/`, not the 7 originally named**
  (Ashby/Greenhouse/Lever/Workable/SmartRecruiters/Recruitee/local-parser
  are real, but so are adzuna, remoteok, themuse, usajobs,
  weworkremotely, workday, and many more) -- worth naming which 1-2
  Morgan actually uses before picking what to port first, since the real
  menu is much bigger than assumed.

| 2 | Situational role-swap logic | Medium | **Done 2026-07-05.** See the Situational/optional work history entries section below. |
| 3 | Cover letter generation | Medium | **Done 2026-07-04.** See the Cover letter generation section below. |
| 4 | Engine/profile rules audit + split | Medium-Hard | Unblocks all multi-user work |
| 5 | Evidence bank extension | Hard | **Phase 1 done 2026-07-07** (voice-anchors.md, trimmed detective-findings, evidence-guide.csv for cover letters, style guide distillation). Full multi-type generalization + career-ops data reconciliation still unscheduled -- see the Long-term merge section below. |
| 6 | Company-values/tone-mirroring | Medium-Hard | **Done 2026-07-05.** The company-research architecture question is resolved; see the Company-values/terminology mirroring section below. |
| 7 | Per-user secrets (`.env` per profile) | Easy | Quick prerequisite right before Dom's onboarding |
| 8 | Dominick's onboarding | Hard | Depends on #4 and #7 existing first |
| 9 | Scheduler + notifications | Hard | **Unblocked 2026-07-04** -- 1.4's `scan` and 1.3's `evaluate` both exist now. Scheduler itself not started. |
| 10 | ~~Mongo migration~~ + liveness check | Medium | **Liveness check done 2026-07-05, decoupled from Mongo.** Investigation found career-ops's actual liveness checker (`liveness-core.mjs`/`liveness-browser.mjs`) needs zero MongoDB -- pure Playwright + deterministic classification, no LLM calls. Built: ported verbatim (`scripts/liveness-core.mjs`, `scripts/liveness-browser.mjs`) + adapted `scripts/check-liveness.mjs` (new `--json-file` batch mode) + `scripts/liveness.py` (gathers pending JDs' `source_url`, moves confirmed-`expired` ones to `jds/expired/`) + `resume liveness` CLI command. Live-verified against all 208 real pending JDs: 166 active, 7 likely active, 35 uncertain, 0 expired, zero crashes. Spec: `docs/superpowers/specs/2026-07-05-liveness-checker-design.md`. **Mongo migration itself remains undone** -- a separate, much bigger question tied to the long-term three-way merge, not needed for anything built so far. |
| 11 | Multi-select "Specific JD" pickers (space-bar toggle) | Medium-Hard | Real open design question: how it coexists with `resume run --pick`'s existing evaluate-then-checkbox flow. See the Multi-select pickers section below. |
| 12 | Help command in the interactive menu | Easy | `resume help` already exists as a shell shortcut; just needs a menu entry. See the Help command section below. |
| 13 | "Doctor" script (dependency/asset checks + test run) | Medium | job_automater already has prior art for this exact pattern (see the Long-term merge section's job_automater notes). See the Doctor script section below. |
| 14 | Bullet-bank reintegration menu option + eventual "Maintenance" submenu | Hard | None of the bullet-bank curation pipeline is wired into the menu today, and the pipeline itself has at least one already-discovered, unresolved inconsistency. See the Bullet-bank reintegration section below. |
| 15 | "List Jobs" / "View Pipeline" browsing command | Hard | Several genuinely open questions (archive as a new state, whether eval notes need richer persistence, a new multi-level browse/detail/act UI pattern). See the List Jobs / View Pipeline section below. |
| 16 | Skip recently-checked JDs in liveness (like evaluate's skip-by-default) | Medium | Close parallel to the evaluate skip-by-default feature already built 2026-07-08 -- same pattern, plus a time-window twist. See the Liveness skip-by-recency section below. |

**Deliberately left off this pass:** an `interview-prep` pipeline stage
(porting career-ops's `modes/interview-prep.md`) -- Morgan's call, not
essential right now, revisit later if it turns out to be needed. Still a
real capability worth having eventually, just not part of this ordering.

## Easy

### Minor/nice-to-have

- The Johnson County Community College education line currently wraps to a
  2nd line at the real printed page width (KU/KCKCC don't anymore, after
  shortening their degree names) -- low priority, not something Morgan has
  flagged as a problem.

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
(`scripts/resume-cli.sh`, sourced from `~/.zshrc`) and every reference to
it in `README.md`/`CLAUDE.md` would need updating to the new name.
Mechanically small -- the only open question is picking the actual
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

job_automater already has real prior art for this exact pattern (see the
Long-term merge section below): `system_checker.py` (Python version,
MongoDB, pdflatex, pip) plus `config_validator.py` (API keys, contact
fields, etc.) together form its "doctor" equivalent, run via its `setup`/
`validate-config` commands. resume-builder's own version would check
things specific to this pipeline instead: Python 3.10+, `.venv/` exists
with `requirements.txt` installed, Node + Playwright's Chromium browser
installed, `GEMINI_API_KEY` (and `JOBRIGHT_COOKIE_STRING` if scan is used)
present in `.env`, the static DM Sans font files exist at
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

### Cover letter generation -- done 2026-07-04

Built in two passes, per the sequencing decided at the time: first the
letter itself (no company research), then company research layered in as
a second pass (2026-07-05, see below). `resume coverletter <jd_file>` is
a fully separate, opt-in command -- never auto-triggered by `tailor`/`run`,
since plenty of real postings don't accept a cover letter at all.

Built: `resume-engine/prompts/tailor_coverletter.md`, `CoverLetterSchema`,
`ResumeEngine.build_tailored_coverletter()`, `scripts/validate_coverletter.py`
(forbidden phrases, paragraph count, third-person-slip checks, one
automatic retry on violations), `scripts/render_coverletter.py`, and the
CLI/shell-shortcut wiring. Specs:
`docs/superpowers/specs/2026-07-04-cover-letter-generation-design.md` and
`docs/superpowers/specs/2026-07-04-company-research-design.md`.

**Scope note (historical):** the template already existed fully built;
this was mostly "build the missing plumbing" (a prompt, a render function,
an orchestrator hook) rather than open design work. The one piece that
pushed toward the harder end was the company-research step (see below) --
done as a second pass, per plan.

Generate a matching cover letter alongside the resume, using the same JD input.

**Why it should be simpler than the resume pipeline:** no page-fit trimming loop,
no per-role bullet allocation, no skills-line-wrap validation, no opening-verb
uniqueness constraint. Mostly: a personalized greeting, 2-3 body paragraphs
tying specific JD/company facts to Morgan's background, and a sign-off.

**What exists already:**
- `resume-engine/templates/coverletter-template.html` -- a full template with
  `{{DATE}}`, `{{RECIPIENT_BLOCK}}`, `{{GREETING}}`, `{{BODY_PARAGRAPHS}}`,
  `{{SIGN_OFF}}`, `{{TYPED_NAME}}`, `{{TYPED_CONTACT}}` placeholders -- but it's
  not wired to anything yet (no script fills it, nothing in `orchestrator.py`
  calls it).
- The existing "Why [Company]?" section in `tailor_resume.md` is first-person,
  company-specific narrative writing -- structurally close to what a cover
  letter body needs, and a reasonable seed/reference for its prompt rules.

**What it would take:**
- A prompt (`resume-engine/prompts/tailor_coverletter.md` or similar) --
  probably reusing JD-derived archetype detection from the resume prompt.
- A render function (new script, or an addition to `render_html.py`) to fill
  `coverletter-template.html` from that output.
- Wiring into `orchestrator.py` -- likely opt-in per JD run rather than
  always-on.
- A lighter validator, if any -- note pronoun rules invert here (cover
  letters are first-person throughout, unlike the resume).
- Confirm `docs/MorganEscottSignature2025.png` (referenced by the template)
  exists and is current.
- A company-research step feeding the prompt (see below) -- this specific
  piece is closer to Hard than Medium; see the architecture-mismatch note.

**Company research -- what career-ops (`/Users/morganescott/career-ops`) does,
and an important architecture mismatch:**

career-ops has no separate "research a company" script/API call. Company
research is done entirely by a live Claude Code agent using its `WebFetch`/
`WebSearch` tools, directed by plain-markdown instructions:
- `career-ops/modes/coverletter.md`, Phase 2 ("Research Before Writing",
  ~lines 53-86): "Do not write a single sentence until the company and role
  have been researched" -- WebFetch the About/mission/values/careers pages,
  cross-reference against `_profile.md`.
- `career-ops/modes/pdf.md`'s "Company Research Rule" (~lines 502-528) does
  the same for resumes: WebFetch `/about`, `/mission`, `/values`, `/careers`,
  etc., falling back to `WebSearch("[company] mission values culture")` if
  those pages are thin.
- `career-ops/modes/deep.md` is a different, standalone mode -- it doesn't
  research anything itself, it *generates a research prompt* meant to be
  pasted into Perplexity/ChatGPT/another assistant. Not really the thing to
  port for automatic per-JD research.

**The mismatch:** all of this assumes an interactive agent session with live
web-browsing tools available mid-conversation. resume-builder's pipeline is
the opposite shape -- `orchestrator.py` calls the Gemini API directly as a
headless script (no tool-use loop, no live web access). So the mode files
aren't directly portable as-is; either (a) add an actual web-fetch step in
Python (`requests`/`BeautifulSoup` against the company's About/careers page)
before building the prompt, feeding the scraped text in as context, or (b)
run this specific step through an agentic session instead of the Gemini-API
script. Worth deciding which before building.

**Cover letter's tone-matching rule** (career-ops `modes/coverletter.md`,
"Rule 4 -- Match the company's register," ~lines 173-198) is a good, already-
written blueprint either way: "mission-driven org -> warmer, more resonant;
playful startup -> sharper, slightly more personality; conventional B2B SaaS
-> measured, crisp, lightly distinctive." Plus a "Company Connection"
paragraph that ties one specific researched fact to Morgan's history,
explicitly guarding against fake flattery.

### Company-values/terminology mirroring in the resume itself -- done 2026-07-05

Built alongside company research (see
`docs/superpowers/specs/2026-07-04-company-research-design.md`): a real
gap was found and fixed along the way -- `tailor_resume.md` already had
instructions assuming company research existed (Summary Rules' tone-mirror
line, the Why section's "specific company research details" line), with
nothing ever having fed them. Both now source real data from a
`=== COMPANY RESEARCH ===` context block when available (via
`scripts/company_research.py`'s plain requests/BeautifulSoup scraper +
`ResumeEngine.research_company()`), and explicitly skip rather than
fabricate when it isn't -- no `company_website` known, pages unreachable,
or content too thin all fall back to pre-feature behavior with a printed
notice, never a guess.

**Scope note (historical):** depended on the cover letter's company-research
step existing first (same architecture-mismatch question applied here
too). Once that was solved, this part itself was close to Easy -- career-ops
already had a working, narrowly-scoped blueprint, ported almost as-is.

Once cover-letter company research exists, reuse it to also tone-match the
resume's Summary and (when present) Why section to the target company's
voice -- not just the JD's literal keywords, which the pipeline already
mirrors.

career-ops already does exactly this in `modes/pdf.md` (~lines 502-528),
scoped narrowly on purpose: "tone mirroring applies ONLY to Summary (tone
and word choice, not facts) and the Why section (framing and register).
Never to job titles, dates, bullet achievements, or skills." It maps signals
like formal-vs-conversational register, "we" vs "you" framing, and 1-2
recurring brand words, to be echoed "naturally... where genuinely
applicable" -- explicitly never copying phrases verbatim. That scoping (and
the "never touches facts" boundary) is worth carrying over as-is; it's a
good, already-tested guardrail against tone-matching sliding into
misrepresentation.

## Hard

### "List Jobs" / "View Pipeline" browsing command

A menu option listing every evaluated job at once (score, recommendation,
last liveness check date if #16 above exists, Completed/Pending status),
with a "View More Details" drill-in (full JD text + the evaluation's
reasoning) and a manual Skip/Archive action per role. Genuinely more than
a picker -- it's a new interaction shape (browse a list -> drill into one
item -> take an action on it) that nothing in `menu.py` does today; every
existing picker is a single pick-and-immediately-act flow, not a
browse-then-decide one.

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
- **Last liveness check date** depends on #16 (Liveness skip-by-recency)
  existing first -- there's nothing to show here until that's built.
- **The browse/detail/act UI pattern itself** needs its own design pass:
  paginated vs. scrollable for 300+ pending JDs, how "View More Details"
  composes with questionary's existing single-screen-per-prompt model
  (probably a sub-menu loop: list -> select one -> action menu -> back to
  list), and whether this subsumes or complements the existing evaluated
  picker (#11's multi-select idea above is closely related -- worth
  designing these together rather than separately, since both are about
  browsing/acting on the same underlying pending-JD pile).

### Bullet-bank reintegration menu option (+ eventual "Maintenance" submenu)

The bullet-bank feedback loop (README's "Bullet bank feedback loop"
section) already queues rewrites automatically during every build into
`needs-review.csv`, and `scripts/triage_needs_review.py` already routes
those queued rows into `bullet-bank-keepers.csv` (permanent),
`rewrite-queue.csv`, or `retired-bullets.csv` -- but it's a separate,
manual script today, unreachable from the interactive menu, and
(confirmed while scoping this idea) not the *complete* path back into the
live pipeline. Step 2 of a real resume build reads **only**
`bullet-bank-keepers-audited.csv` plus its precomputed embeddings
(`bullet_vectors_ge2_d768.npy`, built by `embed_bullet_bank.py`) --
neither of which `triage_needs_review.py` touches (it writes
`bullet-bank-keepers.csv`, not the `-audited` file, and doesn't call
`score_keeper_gems.py` or `embed_bullet_bank.py` itself). So a genuinely
complete "work newly-reviewed bullets back into the live bank" flow needs
at least `triage_needs_review.py` -> `score_keeper_gems.py` ->
`embed_bullet_bank.py`, run in that order -- and **that chain isn't fully
verified yet**: `score_keeper_gems.py`'s own default `--input` points at
`bullet-bank-keepers-audited.csv` (the stage's *output*, per the naming),
not `bullet-bank-keepers.csv` (what `triage_needs_review.py` actually
writes) -- meaning either there's an already-existing manual step between
the two that hasn't been found yet, or the real data flow here isn't what
the file names imply. This needs actually tracing through before wiring
anything, the same way the `cluster_bullet_bank.py` ->
`bullet-bank-clustered.csv` mismatch was flagged earlier rather than
assumed (see the wiring/gap research pass above). That open question --
what the real, correct script order and arguments are -- is exactly why
this is Hard, not Medium: the menu wiring itself (one new option,
shelling out to a script or three) would be easy once the actual pipeline
is confirmed.

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

### Situational/optional work history entries -- done 2026-07-05

Built exactly per the bump-priority design resolved 2026-07-04, no
re-brainstorming needed. `scripts/situational_roles.py` (deterministic
keyword gate, TDD-tested), `fixed_content.py` entries for the 6 companies,
`mine_bullet_bank()` extended with `extra_company_minimums` to guarantee 2
real bullets per cleared candidate, `build_tailored_resume()` folds
candidates into the builder's context, `tailor_resume.md` gets the
shrink-not-replace + floor-of-2-exception section, and an audit log line
fires whenever a situational role survives into the final resume.

**Real finding during build:** `bullet-bank-keepers-audited.csv` tags KU
Payroll Office and DeJoy, Knauff & Blood more tersely ("Payroll", "DeJoy")
than their proper resume display names -- `situational_roles.py`'s
`bank_tag` field bridges this. Also caught and fixed a real bug live:
`normalize_resume.py` assumed every `COMPANY_META` entry has both
`size_revenue` and `location`, crashing on the new entries that only have
`location` (no real size/revenue data exists for a 3-month internship).

**Live-verified both directions:** a deliberately animal-welfare-flavored
test JD correctly cleared the Humane Society keyword gate and
guaranteed-mined real bullets, but the LLM judged the entry wasn't worth
including here -- instead reframing existing strong content (Hill's Pet
Nutrition) to speak to the JD's angle. That's the "essentially never"
guardrail working as intended, not a failure. A second run on an ordinary
JD showed zero situational-role activity, confirming no regression.

**Scope note (historical):** the wiring itself (new `fixed_content.py`
entries, a new prompt section) was Easy -- mechanically identical to the
existing six roles. The bump-priority design question below was
brainstormed and resolved 2026-07-04.

Let the builder swap in one of Morgan's other real roles when a JD is
specifically relevant to it, instead of always using the same fixed six
(Mercor, Treering, Inside Sales Team, Element 8/Strategy LLC, VML, Callahan
Creek). Examples raised: Humane Society of Greater Kansas City (animal
welfare roles), Unisource Document Products (print production), Kansas
Colloquies/The Chieftain (journalism), KU Payroll Office and DeJoy Knauff &
Blood (payroll/tax/clerical/sensitive-info roles), USitek (clerical +
graphic design blend). Rare, deliberate use only -- not a default behavior.

**Good news:** verified bullet content for all of these already exists in
`resume-engine/knowledge_base/bullet-bank-clean.csv` (worth double-checking
completeness/dates per company before building, but this isn't a
from-scratch content-gathering project).

**What it would take -- the wiring is straightforward, the judgment calls are not:**
- `fixed_content.py` needs `COMPANY_META` / `COMPANY_TITLE_DESCRIPTOR` (etc.)
  entries for each optional company -- mechanically identical to the existing
  six.
- `tailor_resume.md` needs a new section spelling out each optional role, its
  trigger condition (what makes a JD relevant to it), and explicit guardrails
  ("only when clearly helpful, essentially never for most JDs").

**Bump-priority design, resolved 2026-07-04:**

- **Trigger -- hybrid gate.** `orchestrator.py` runs a deterministic keyword
  pre-check per optional company against the JD text (e.g. Humane Society
  of Greater Kansas City -> "animal welfare"/"shelter"/"animal rescue").
  Only companies clearing this gate are even presented to the builder;
  the LLM then makes the actual go/no-go call among those candidates,
  using the same archetype-detection reasoning it already applies
  everywhere else. Nothing reaches the LLM's judgment unless the keyword
  gate opened first -- keeps this rare *by construction*, not just by
  instruction in the prompt.
- **Shrink-not-replace, not a swap.** Explicitly *not* "situational role
  replaces one of the six" -- nobody disappears from the resume. Every one
  of the six temporarily gives up one bullet-count notch to make room for
  a small, tightly-bounded situational entry (2 bullets -- a supporting
  signal, not a fully weighted role).
- **A new floor table, inverted from today's default trim order for this
  scenario specifically.** `tailor_resume.md`'s existing trim order (line
  ~174) protects Element 8/VML/Callahan Creek down to a floor of 3 and
  treats Treering/Inside Sales Team as flexible-first-to-trim -- tuned for
  the common case where big-name brand/client signal matters most. Morgan's
  call flips this specifically when a situational role is active: Mercor,
  Treering, and Inside Sales Team (her most recent experience) must
  **never** be the ones that shrink to make room, full stop -- so the
  absorbing has to come from Element 8/VML/Callahan Creek instead, even
  though those three are the *protected* trio everywhere else. Needs to be
  written down explicitly as its own rule ("floor of 3 normally; floor of 2
  specifically when a situational role is active") rather than left as an
  implicit exception to the existing line -- it directly contradicts the
  existing "never below 3" wording if not called out as a distinct case.
- **Auditability, not a numeric rarity threshold.** The double-gate
  (keyword match + LLM judgment) already makes this naturally rare by
  construction, so no extra score threshold was judged necessary. The one
  thing worth adding: a log line in `orchestrator.py` whenever a situational
  role actually fires, so "rare" stays a checkable fact across real runs
  instead of an assumption.

Implementation complete as of 2026-07-05 (see above).

## Very Hard / Long-term

### Long-term: merge with career-ops and job_automater

**Scope note:** the biggest item on this list. Spans three separate
codebases (this project plus two mature sibling projects). Both siblings
had real incidents surfaced and fixed on 2026-07-04 (job_automater's
missing files restored; career-ops recovered from a bad auto-update) --
see below for what that revealed about each project's shape. A first
brainstorming pass happened the same day (2026-07-04) and landed on an
agreed direction -- see "Agreed direction" below -- but **no implementation
has started and nothing is scheduled yet**; this is still reference
material for when that build actually begins, not a plan with a start date.

The eventual goal is a single system, with resume-builder replacing the
resume-generation features of both `/Users/morganescott/career-ops` and
`/Users/morganescott/job_automater`. Rough shape as of 2026-07-04:

- **From career-ops** ("the glue"): the dashboard, application tracker
  (markdown/YAML, treated as the source of truth), and the multi-agent
  "mode" pipeline (job-board scanning via `providers/`, JD-fit evaluation,
  tracker updates) -- see the cover-letter section above for what it does
  for company research/tone-matching specifically. Its `providers/` cover
  direct-to-ATS job-board scanning (Ashby, Greenhouse, Lever, Workable,
  SmartRecruiters, Recruitee, plus a generic local-parser fallback) --
  a different, complementary source type from job_automater's scrapers
  below (LinkedIn + JobRight), not a redundant one; the merged system
  likely wants both rather than picking one.

  **A real incident here is directly relevant to the eventual merge design,
  not just a one-off bug (2026-07-04):** career-ops is a fork of
  `santifer/career-ops` and has an `update-system.mjs` (confirmed
  2026-07-04: no git remote is actually named `upstream` -- only `origin`
  points at her fork; `update-system.mjs` sources the original repo some
  other way, worth checking before relying on `git fetch upstream` for
  any future audit) that auto-pulls changes into what its own
  `DATA_CONTRACT.md`
  calls "System Layer" files (all `modes/*.md`, `*.mjs` scripts,
  `dashboard/*`, `templates/*`), on the theory that personalization only
  ever lives in `config/profile.yml`/`modes/_profile.md`/`cv.md`. In
  practice a June 2026 auto-update (v1.9.0) silently overwrote Morgan's
  actual customizations in `modes/_shared.md`, `modes/apply.md`, the
  scan/provider scripts, and the CV templates -- because the contract's
  own README explicitly invites hand-editing those "system" files directly
  ("just ask Claude to change them"), so real personalization had ended up
  there despite the documented rule. Recovered by diffing the update
  commit against its parent and reverting only the files nothing had
  touched since (full account in memory: `project_career_ops_update_risk`).
  **Why this matters for the merge:** whatever "engine vs. profile"
  separation the merged system ends up with (see Multi-user support below)
  needs to actually be *enforced*, not just documented -- career-ops had
  exactly this separation written down and it still failed in practice.
- **From job_automater**: the pieces Morgan wants to keep, plus a few
  cross-cutting findings from the 2026-07-04 repair that surfaced real
  decisions the merge will need to make (concrete file paths throughout so
  none of this needs re-researching later):
  - **CLI** -- `cli.py`, a Click-based `job-agent`-style command group:
    `fetch-jobs`, `list-jobs`, `generate-docs`, `apply`, `status`, `setup`,
    `validate-config`/`config`, `config-info`, `interactive`.
  - **"Doctor" script** -- there's no single file literally named "doctor";
    it's really two complementary pieces: `system_checker.py`
    (checks *system* dependencies -- Python version, MongoDB, pdflatex, pip
    -- run via the `setup` command through `setup_wizard.py`) and
    `config_validator.py` (checks *config values* -- API keys, contact
    fields, address, LinkedIn URL, work-auth fields -- exposed via
    `validate-config`/`config`). Together those two are the real doctor
    equivalent. (`check-all.py`/`check-db.py` are separate, thinner,
    Mongo-only checkers, present in the working copy but not the fresh ZIP --
    likely local-only scripts Morgan added herself.)
  - **Three separate document-generation backends, decided (2026-07-04):
    dropped.** `document_generator/` contains `generator.py`/`generator_v2.py`
    (reportlab) plus `resume_latex_match.py`/`resume_perfect_latex.py`/
    `resume_reportlab.py`/`cover_letter_reportlab.py` -- all LaTeX/reportlab.
    Morgan's call: LaTeX output can have real ATS-parsing issues, whereas
    resume-builder's existing Playwright/HTML->PDF approach (already
    battle-tested -- the DM Sans static-font-instance fix for the PDF
    text-scrambling bug, the skills-line-wrap validator, etc.) performs
    cleanly. None of job_automater's rendering code carries forward into
    the merge; Playwright/HTML is the one true renderer.
  - **The ATS auto-apply engine, decided (2026-07-04): cut entirely.**
    `job_automator/automator_main.py` + `ats_fillers/` (Selenium-based, with
    dedicated Greenhouse/Workday fillers) actually navigates to a job
    posting, fills out the form, and submits it. Morgan's call: she wants
    human eyes on every application before the final submit button, full
    stop -- this inherits career-ops's existing Human-in-the-Loop stance
    ("the system never submits an application -- you always have the final
    call") rather than job_automater's auto-submit behavior. None of the
    ATS-filling/submission code carries forward into the merge; manual
    intervention isn't a fallback mode, it's the only mode.
  - **Persistence-layer mismatch, worth deciding up front:** job_automater
    stores everything in MongoDB (run via a local Docker container,
    `local-mongo` / image `mongo:latest`, port 27017 -- confirmed holding
    83 real scraped job records as of 2026-07-04), career-ops treats flat
    markdown/YAML files as the source of truth (`data/applications.md`,
    `data/pipeline.md`), and resume-builder uses CSV files + JSON
    checkpoints. Three different persistence philosophies across the three
    projects -- the merge needs one, not an integration layer across all
    three.

    **Pros/cons discussed 2026-07-06, not yet decided:**
    - *CSV + JSON (resume-builder today):* zero infrastructure, human-
      inspectable, already proven at real scale (209+ JDs). Cons: no real
      query/indexing (dedup is hand-rolled Python, not a query), weak
      concurrent-write safety, schema changes mean touching every read/
      write site by hand.
    - *Markdown/YAML (career-ops):* maximally human-readable/editable,
      fits the "human eyes on every application" philosophy best, diffs
      read like prose. Cons: same lack of querying as CSV, and more
      fragile to parse back into structured data reliably; career-ops's
      own file-based system/data boundary already failed once in
      practice (the auto-update incident) -- not a persistence-format
      bug specifically, but a reminder that "just files" isn't
      automatically safe.
    - *MongoDB (job_automater):* real queries/filtering/sorting, genuine
      multi-writer concurrency safety, flexible schema, already proven
      with 83 real records. Cons: the only option needing a background
      service (Docker) running at all times; not human-inspectable
      without separate tooling (mongosh/Compass), cutting against this
      project's consistent inspectable-by-default pattern.
    - *SQLite (not one of the three above, floated as a possible
      fourth path):* real transactional safety and queries without a
      daemon/Docker -- a single portable file, `sqlite3` is in Python's
      stdlib. Solves the scheduler's concurrent-write concern
      reasonably well (WAL mode lets readers and a writer coexist,
      though it's still single-writer-at-a-time, not true multi-writer
      concurrency). Cons: loses inspectability too (a `.db` file needs
      the `sqlite3` CLI or a GUI tool, not a text editor); not
      git-diffable (less of a loss here since these trackers are
      already gitignored for PII); real schema/migration discipline
      instead of freeform files; a new SQL-query paradigm in a codebase
      that's been 100% pandas/CSV/JSON manipulation so far; and it may
      be solving a concurrency problem that doesn't fully exist yet --
      the benefit mainly kicks in once the scheduler (#9) is actually
      running unattended, not at today's scale.
    - **Leaning:** keep the human-facing tracker as markdown/YAML (or
      CSV) for inspectability; revisit SQLite specifically for the
      scheduler's concurrent-write needs when that build actually
      starts, rather than adopting it preemptively. Still not decided --
      reference material for when this choice actually gets made.
  - **Interview setup** -- confirmed again against the fresh ZIP: **doesn't
    exist in job_automater**, not even a partial version. The likely source
    of the mix-up: `RESEARCH_FINDINGS_COMPETITORS.md` (a competitive-analysis
    doc in the repo) lists "Interview scheduler" as a low-priority,
    not-yet-built roadmap idea and notes competitors having "mock interview
    prep" -- that's probably what got remembered as an existing feature.
    career-ops's `modes/interview-prep.md` (Glassdoor-query-based interview
    intel) is the thing that's actually built and worth porting instead.
  - **Jobright scraping** -- `scrapers/jobright_scraper.py`. Plain REST API
    calls (no browser automation) against a configurable base URL,
    cookie-authenticated, paginated, filters out anything below a 70 match
    score, writes to MongoDB + a JSON backup file.
  - **LinkedIn scraping** -- `scrapers/linkedin_scraper.py`. Browser
    automation via the `linkedin_jobs_scraper` package (Selenium under the
    hood) using hardcoded search queries, plus a supplementary authenticated
    `requests`/BeautifulSoup pass to detect "Top Applicant" badges. Same
    Mongo + JSON-backup output pattern as Jobright.

  **Security flag, found during this research -- still not fixed:**
  `scrapers/recommended_scraper.py` (present in the working copy) has a
  **LinkedIn `li_at` session cookie hardcoded in plaintext**. Checked the
  fresh ZIP re-download: this file **isn't part of the actual open-source
  project at all** -- the real repo's `scrapers/` only has `__init__.py`,
  `jobright_scraper.py`, and `linkedin_scraper.py` (which correctly sources
  its cookie from `config`, not hardcoded). So this is a local, ad-hoc script
  Morgan or something added to her working copy and never upstream. The
  2026-07-04 repair (below) only restored *missing* files and deliberately
  left every existing file untouched, so this one is exactly as it was --
  that cookie is still a live credential sitting on disk; still needs
  rotating, and don't carry the file forward into any merge.

  **Working-copy repaired, 2026-07-04:** the file loss described above
  (`config.py`, `main.py`, `job-agent`/`job-agent-clean`, plus -- discovered
  during the actual repair -- the entire `document_generator/` package and
  the whole `job_automator/` automation engine, ~55 files total) has been
  fixed: restored from the fresh ZIP via `rsync --ignore-existing` (so
  Morgan's customized scrapers/tailor files were left alone), verified
  `cli.py`/`main.py` run end-to-end against the real Mongo data, and
  committed to git (these files had existed on disk and run before but had
  never actually been `git add`ed, which is how they were silently lost in
  the first place -- they're tracked now, so this specific failure mode
  shouldn't recur). job_automater is no longer a blocker for merge planning.

**Agreed direction (brainstormed 2026-07-04, not yet a build plan):**
five candidate approaches were floated, ranging from a conservative
strangler-fig port to genuinely out-there ideas (a standing background
daemon; one shared "evidence bank" underlying every output). Morgan's
reaction converged on a combination rather than picking just one:

- **One codebase, one CLI.** resume-builder stays the surviving identity
  (a rename is a someday-detail, not a now-decision). Python throughout --
  career-ops's `.mjs` pipeline logic gets ported during the merge; its
  markdown/YAML tracker *format* carries over as-is, since that's just data.
- **The evidence bank ("the brain") -- the piece Morgan was most decisive
  about ("that's what I've been working toward... that is the brain, and a
  must").** Not a rebuild -- an extension of what already exists and
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
  Dominick's onboarding -- see the Multi-user support section below.

**2026-07-07 -- Sparkle critique signals + evidence bank scoping
conversation.** Two threads, connected:

1. **Sparkle critique signals -- built 2026-07-07.** an external
   brainstorm doc (`SparkleConcept.docx`) proposed scoring resumes for
   warmth/memorability/distinctiveness. Investigation found this project
   already does much of this piecemeal (`forbidden_phrases` in
   `style_rules.yaml`, `hidden_gem_score`/`hidden_gem_flag` in the
   bullet-bank scripts, mandatory first-person warmth in `WHY_TEXT`).
   Scoped down from the doc's full multi-stage-pipeline vision to a small,
   zero-new-API-call extension of the *existing* critique/recommendation-
   apply loop: `ResumeCritiqueSchema` gains `distinctive_moments`/
   `flat_sections`, and the recommendation-apply loop protects
   `distinctive_moments` verbatim + routes reflective-question
   recommendations it can't ground in real context to a new
   `needs_personal_input` bucket (surfaced as "try `resume polish` for
   these" rather than fabricated). Spec:
   `docs/superpowers/specs/2026-07-07-sparkle-critique-signals-design.md`.
2. **This surfaced item 5 (evidence bank extension) as a real dependency**
   -- `distinctive_moments` are currently rediscovered fresh on every
   resume build; a real evidence bank would let that signal persist and
   feed back into curation instead. Investigating scope turned up more
   complexity than expected:
   - Of the ~18 CSVs in `resume-engine/knowledge_base/`, **only one or two
     are actually wired into the live resume/cover-letter pipeline today**
     -- most of the rest are different stages/snapshots of the *same*
     bullet-bank pipeline (`needs-review` -> `triage_needs_review.py` ->
     `bullet-bank-keepers.csv`/`rewrite-queue.csv`/retired), not
     independent systems. The other, non-bullet-bank CSVs
     (`evidence-guide.csv`, `detective-findings.csv`, `verified-claims.csv`,
     `summaries-and-skills-clean.csv`, etc.) are each their own thing and
     may or may not be wired into anything live -- unconfirmed as of this
     writing.
   - `career-ops/data/` shares several filenames with resume-builder's
     `knowledge_base/` (`bullet-bank-clean.csv`, `evidence-guide.csv`,
     `detective-findings.csv`, `verified-claims.csv`,
     `summaries-and-skills-clean.csv`) -- these look like a one-time copy
     that's since diverged, since resume-builder built real pipeline logic
     (clustering, auditing, hidden-gem scoring) on top of its copies that
     career-ops's versions never received.
   - `career-ops` also has evidence-relevant material **resume-builder has
     none of at all**: `interview-prep/story-bank.md` (STAR+R interview
     stories) and `writing-samples/` (Master Cover Letters, Application
     Answers, LinkedIn Tone & Style Examples) -- real past writing samples,
     currently untouched by any tooling, that could ground voice/tone work
     directly.
   - **Decision:** reconciling two diverged data directories across repos
     plus adding new evidence types is genuinely "Very Hard/Long-term"
     scope, not a single-session spec. Next concrete step (in progress):
     a research pass (no code changes) to map (a) what's actually wired
     into the live resume/cover-letter pipeline today, (b) what exists in
     `knowledge_base/` but isn't wired into anything, and (c) what's in
     career-ops that resume-builder doesn't have -- before deciding what,
     if anything, to build.

**2026-07-07 -- Wiring/gap research pass (findings, verified against real
code, not assumed):**

- **What's actually live-wired into resume building today (all confirmed
  by tracing `orchestrator.py`, not guessed):**
  - Step 2 (mine bullet bank): reads **only** `bullet-bank-keepers-audited.csv`
    + its precomputed embeddings (`bullet_vectors_ge2_d768.npy`, built by
    `embed_bullet_bank.py`) -- confirms Morgan's instinct that only one or
    two bullet-bank CSVs are truly live-wired; everything else in the
    `bullet-bank-*` family is an earlier curation stage feeding toward that
    one file (`bullet-bank-clean` -> `audit_bullet_bank.py` ->
    `bullet-bank-audited` -> `cluster_bullet_bank.py` -> cluster map ->
    `triage_needs_review.py` -> `bullet-bank-keepers.csv` ->
    `score_keeper_gems.py` -> `bullet-bank-keepers-audited.csv`).
  - Step 3 (audit bullets) **and** cover-letter generation both use
    `build_audit_static_prefix()` -- a slim ~5-10k-token context of
    `profile.yml` (trimmed) + `verified_facts.json` + `verified_tools.json`
    + `verified_projects.json` only.
  - Step 4 (build resume, fresh builds only) additionally pulls in the full
    ~457k-token `KB_ALLOWLIST` (`load_knowledge_base()`):
    `article-digest.md`, `bullet-bank.md`, `cv.md`, `evidence-guide.csv`,
    `evidence_graph.json`, `extracted-screenshot-metrics.csv`,
    `morgan-background-guide.md`, `portals.yml`, `profile.yml`,
    `recruiter_memory_patterns.json`, `summaries-and-skills-clean.csv`,
    `treering-archive-readme.md`, `verified-claims.csv`,
    `verified_metrics.json`, plus the three verified_*.json above.
  - **Real finding:** cover letters get the slim Tier-1 context ONLY --
    none of the Step-4-only KB_ALLOWLIST files (`evidence-guide.csv`,
    `verified-claims.csv`, `bullet-bank.md`, `summaries-and-skills-clean.csv`,
    `recruiter_memory_patterns.json`, etc.) ever reach cover-letter
    generation today.
- **Confirmed genuinely orphaned within resume-builder's own codebase**
  (zero references anywhere in `scripts/*.py`, verified by exact-filename
  grep, not substring-matched): `active-inventory.csv` (444KB),
  `bullet-bank-deduplicated.csv` (478KB), `bullet-bank-gems-report.csv`
  (191KB), `coverage-tracker.csv` (699KB), `detective-findings.csv`
  (232KB), `screenshot-review-log.csv`, and `treering-archive-readme.csv`
  (only the `.md` twin is wired; the `.csv` version of the same content
  isn't referenced anywhere).
- **A real pipeline mismatch, found by accident:** `cluster_bullet_bank.py`
  is currently configured to write `bullet-bank-clustered.csv`, but no
  such file exists anywhere in `knowledge_base/` -- only
  `bullet-bank-cluster-map.csv`/`-cluster-map-updated.csv` exist (which
  `audit_keepers.py`/`rewrite_bullets.py` do read). Either those cluster-map
  files came from an earlier version of the script before a rename, or
  running `cluster_bullet_bank.py` today would silently produce a file
  nothing downstream reads. Not investigated further; flagged for whoever
  picks up bullet-bank pipeline work next.
- **What's in career-ops that resume-builder has none of:**
  - `interview-prep/story-bank.md` -- turned out to be an **empty
    template** (26 lines, all placeholder comments, zero actual stories
    filled in yet). Nothing to port content-wise; only the STAR+R format
    is worth reusing conceptually, later.
  - `writing-samples/` (291 files) -- **real, substantial, mostly
    untapped.** Actual past cover letters (PDF/docx), "BestCopySamples"
    (newsletter samples, an IT sequence, headline copy), ~20 LinkedIn
    tone/style screenshots, and **`MorganWritingStyleGuide.txt`** (246
    lines, saved as RTF) -- which opens with *"Morgan Escott writes with
    what can only be described as **strategic sparkle**"* and goes on to
    define tone/energy, sentence rhythm, word choice, and power words in
    real detail. This directly predates and validates the Sparkle work
    above -- it's Morgan's own pre-existing voice rubric, currently wired
    into nothing at all in resume-builder (not in `KB_ALLOWLIST`, not
    referenced by any prompt). Most other writing-samples files are
    binary (PDF/docx/PNG) and would need conversion (same `textutil`
    approach already used for `SparkleConcept.docx`) to be machine-usable.

**2026-07-07 -- Deeper dig + spec (Phase 1 scoped and written).** Follow-up
investigation confirmed: `coverage-tracker.csv` (802 rows), `detective-
findings.csv`'s sibling process-tracking file `screenshot-review-log.csv`,
and the `.csv` twin of `treering-archive-readme` are audit-*process*
tracking artifacts (file review status, completion tracking), not evidence
content themselves -- not worth wiring in. `detective-findings.csv` itself
*is* real evidence content (its own README calls it a companion file) but
was missing from `KB_ALLOWLIST`, apparently by oversight. Also dug into
career-ops's `writing-samples/Application Answers/` -- a small (14-row),
already-curated index with themes and "Quote Worth Pulling" lines, real
value, nothing else covering it. The raw "Treering Sequences" archive
(140+ files, heavy duplication, some not even Morgan's own authorship --
files literally prefixed "ERIKA_") is genuine but needs its own curation
pass before it's usable, same as the original bullet bank did -- **filed
here as a future follow-up, not part of Phase 1.**

**Phase 1 -- built 2026-07-07**, scoped around Morgan's hard constraint (a
real past incident: including `bullet-bank-keepers-audited.csv` in
`KB_ALLOWLIST` once blew a run past the free tier's 250k-tokens/minute cap)
-- nothing got wired in without being measured first:
- Distilled `MorganWritingStyleGuide.txt` directly into `style_rules.yaml`/
  prompts (zero runtime cost, one-time content migration).
- New curated `voice-anchors.md` from `Application_Answers_Index.csv`
  (measured: ~1,011 tokens -- trivially safe everywhere).
- New `detective-findings-trimmed.csv` (5 of 14 columns kept -- measured:
  ~57,850 -> ~29,983 tokens, 48.2% smaller) added to `KB_ALLOWLIST` in
  place of the raw file.
- `build_audit_static_prefix(include_evidence_guide=False)` parameterized
  so cover letters now get `evidence-guide.csv` (~17,329 tokens) without
  that cost multiplying across Step 3's per-bullet audit loop, which
  reuses the same function.

Spec: `docs/superpowers/specs/2026-07-07-evidence-bank-phase1-design.md`.
Plan (combined with Sparkle critique signals, built together for
coordination): `docs/superpowers/plans/2026-07-07-sparkle-and-evidence-bank-phase1.md`.
Tier 2 (raw "Treering Sequences" archive curation, `BestCopySamples`/
`Master Cover Letters` skim) remains unscheduled, tracked above.

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
  invoking `resume scan --saved-search <name>` headlessly. There's a single
  scored list, not two separately-maintained tiers: matches scoring **>=90
  land on a review list**; matches scoring **>=95 ("all-star") additionally
  auto-trigger `tailor`+`render`**, so a truly exceptional hit has a ready
  PDF sitting in a folder before Morgan has even looked at it. Every run
  ends with **both** a macOS local notification (quick heads-up count) and
  an email digest (the readable summary, with pre-generated PDFs
  attached/linked for all-stars). Nothing here ever applies or submits
  anything -- the entire scheduler's output is "things placed in front of
  Morgan to approve."
- **Explicitly deferred, not decided against:** a career-ops-style
  dashboard/TUI (Morgan's call: "later nice-to-have," not blocking the core
  pipeline). **Decided against, not deferred:** ATS auto-apply/auto-submit
  and LaTeX rendering (see above).

**Confirmed 2026-07-06:** the email digest sends via `smtplib` + a Gmail
app password in `.env`, consistent with this repo's existing patterns.

Still fully unresolved and *not* covered by the brainstorm above: the
exact launchd job layout (one job per saved search vs. one dispatcher job
iterating all of them).

No implementation has started; this is scope-awareness plus an agreed
direction for when that build actually begins, not a plan with a start
date.

### Multi-user support -- let other people (starting with Dominick) use this

**Scope note:** roughly tied with the merge as the biggest item here --
and, as of 2026-07-04, this has a real name and a real deadline pressure
attached rather than being purely speculative: Morgan has promised
Dominick ("Dom") that he'll get to try this, and he's actively excited
about it. That doesn't change the scope, but it does mean this shouldn't
sit indefinitely once the merge's evidence-bank work (above) is underway --
Dom's onboarding is the first real test of it.

Splits into a mechanical (if broad) half -- separating engine from
per-user profile data -- and a genuinely unsolved half: designing an
onboarding flow that gets a brand-new user to a usable, trustworthy bullet
bank fast. That second half is a process/UX design problem, not an
engineering one, and needs its own brainstorming pass.

Right now the whole pipeline is Morgan-specific, not just in data but in
structure: `scripts/fixed_content.py` is literally her contact info/company
facts/certifications/education as Python constants, and
`resume-engine/prompts/tailor_resume.md` + `resume-engine/rules/*.yaml` are
written assuming her specific companies, roles, and voice. Making this
usable by someone else is really two separate problems:

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
above, under the career-ops merge notes, and in memory
`project_career_ops_update_risk`). The lesson for this split: the
engine/profile boundary needs to be structurally enforced (e.g. profile
data physically can't live in engine-owned files/paths) rather than just
documented as a convention, or the same failure mode will eventually repeat
here too.

**2. The harder problem Morgan actually asked about: how does a new user
build their own bullet bank in the first place**, when they don't have
100+ audited variations sitting around already? Options raised: a guided
interview/Q&A process, a profile file/form to fill out, a LinkedIn data
export, or sharing project write-ups directly.

Checked what's already reusable vs. what's a real gap:
- **Already built and reusable:** the audit/critique/scoring machinery
  (`resume-engine/prompts/critique_bullet.md`, `rules/truthfulness_rules.yaml`,
  `rules/language_quality.yaml`, `rules/verb_taxonomy.yaml`, etc.) already
  takes a rough, self-written bullet and scores it for credibility, banned
  language, vague verbs, and believability, then proposes a rewrite. That's
  exactly the "polish a new user's rough draft into a verified bullet" step
  -- and it's the same machinery already battle-tested on Morgan's own
  material (`bullet-bank-audited.csv` etc. show a lot of iteration through
  it).
- **Not built yet, a real gap:** nothing today turns raw source material --
  a LinkedIn export, an old resume, project write-ups, or an interview
  transcript -- into first-*draft* bullets in the first place.
  `extract_evidence.md` (despite the name) deconstructs an *existing*
  bullet to check its credibility; it doesn't generate new ones from raw
  material. That initial extraction step is the thing to actually design/build.
- **The genuinely hard part isn't mechanical.** This whole system's identity
  is "never fabricate, everything traceable to real verified history."
  Morgan's bullet bank got that grounding from years of lived history plus a
  lot of manual auditing across many CSV iterations. A new user's onboarding
  flow has to front-load that same rigor in far less time -- that's a
  process/UX design question (how much interview depth is enough?) more than
  an engineering one, and probably deserves its own brainstorming pass
  before building anything.

**Refined onboarding idea (2026-07-03): light seed + grow-as-you-go, not a
big upfront audit.** Morgan's proposal: a new user doesn't need 1,000+
pre-audited bullets -- just one existing resume, a filled-out profile/a few
Q&A answers, maybe a LinkedIn PDF export and a couple project docs, as a
*seed*. The bullet bank then grows naturally over real usage, as the builder
rewrites/expands that seed material differently per JD.

This is sound, but it changes *where* the truthfulness verification happens,
which is worth being explicit about rather than assuming it's free:
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
- **Correction (2026-07-03):** the harvest-back loop already exists --
  I'd said it didn't and Morgan caught it. `scripts/bullet_feedback.py`,
  wired into `orchestrator.py`'s bullet-audit step (~line 1206), already
  queues any accepted bullet rewrite that clears the bank's real "KEEP" bar
  (`decide_action() == KEEP` and `manager_test == PASS`) into
  `needs-review.csv` automatically, during every resume build. A separate
  pass, `scripts/triage_needs_review.py`, then routes those queued rows: PASS
  + believability >=80 -> `bullet-bank-keepers.csv` (permanent); FAIL with
  attempts left -> `rewrite-queue.csv`; FAIL, out of attempts ->
  `retired-bullets.csv`. So "grows over time" is already real for Morgan's
  own bank today -- the multi-user version of this is "make this per-user
  scoped" (each user's own needs-review/keepers/retired CSVs), not "invent it
  from scratch." Also worth noting: promotion into the permanent keeper bank
  isn't fully automatic -- `triage_needs_review.py` is a separate run, which
  is itself a nice built-in curation checkpoint, and maps well onto the
  "verification moves to human review" idea above.
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
  convention -- the career-ops cautionary tale above is no longer abstract
  once a second real person's data is in the repo.
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
    same way Morgan's own bank already grows today (`bullet_feedback.py` /
    `triage_needs_review.py`) -- not through a formal onboarding gate.
    **Flagged refinement for later, not a prerequisite:** the cap itself
    could loosen slightly in later sessions if Dom's engaged, borrowing a
    light touch of the adaptive idea without building its full machinery
    up front.
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

No design work has started on any of this; these are brainstormed
directions, not a plan.
