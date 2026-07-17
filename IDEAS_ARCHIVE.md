# Ideas Archive -- Completed Work & Build History

Full detail on everything already shipped from `IDEAS.md`'s backlog, plus
historical incident narratives, moved here to keep `IDEAS.md` scannable as
an active backlog. Nothing in this file needs action -- it's reference
material for "how did we get here" / "what was already decided and why,"
not a to-do list. Organized by feature, each section stamped with its
done date; the daily build log at the top is chronological.

## Daily build log (2026-07-04 through 2026-07-16)

A cross-cutting priority pass over the backlog happened 2026-07-04, with
Morgan's explicit call that the CLI goes first; item 1 was broken into
sub-steps reflecting "fastest payoff first, biggest lift last" within that
phase. **Update 2026-07-04: all of 1.1-1.4 are now built** (see the
per-row notes below). **Update 2026-07-05: items 2 (situational
role-swap), 3 (cover letter generation), 6 (company-values/
tone-mirroring), and 10 (liveness check, Mongo migration still undone) are
also done.** **Update 2026-07-07: item 5 (evidence bank extension) Phase 1
is done** -- see its row below; the full multi-type generalization remains
unscheduled. **Update 2026-07-07 (later the same day):** two off-backlog
quality-of-life items also shipped, surfaced by live usage rather than
originally planned -- console output polish (theme-safe blue/green colors
replacing theme-dependent `cyan`, bordered panels for the title banner and
"What's next?" prompt, a collapsed trim-loop PDF block, a one-line
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

**2026-07-16 catch-up (documentation fell behind actual work for about a
week, 2026-07-08 -> 2026-07-16; backfilling here rather than pretending it
just happened):**

- **Bootstrap flow for new users -- built 2026-07-12 and 2026-07-13**
  (`docs/superpowers/specs/2026-07-12-bootstrap-bullet-bank-design.md` +
  `2026-07-13-bootstrap-profile-personalization-design.md`), resolving the
  core of the "harder problem" under Multi-user support in `IDEAS.md`: raw
  uploaded documents (PDF/images/`.docx`/`.pptx`/spreadsheets) -> Gemini-
  based classification/achievement extraction -> a real
  `bullet-bank-clean.csv` -> the existing 6-stage pipeline, guided end-to-
  end via a new "New User? Start Here!" entry point in the interactive menu
  (`bootstrap_bullet_bank.py`, `bootstrap_extractors.py`,
  `bootstrap_timeline.py`). A second pass (`bootstrap_profile.py`) then
  auto-derives `verified_metrics/tools/projects.json` from those extracted
  achievements, guesses/confirms `profile.yml`'s contact/target-role fields
  inline, and drafts `cv.md` + `user-background-guide.md` for
  accept/regenerate/skip review. **Important nuance -- this is the
  onboarding-UX/extraction half only, not full multi-user isolation:**
  confirmed there's still no `profiles/<name>/` directory split -- bootstrap
  writes into the same single-user file layout Morgan's own data lives in.
  Running it for a second real user today would still write over her live
  files. **Verified 2026-07-16 against the 2026-07-04 brainstorm's specific
  sequence, and the shipped flow's shape is materially different, not just
  unverified:**
  - **"Gaps surface after first resume, not before" -- not built.** The
    decision was: upload triggers silent extraction straight through to a
    rendered (expected-thin) resume with zero blocking questions, and
    follow-up questions drive a second pass after that. What's actually
    built instead (`bootstrap_profile.py`'s "Phase 0.5") asks guess-
    confirm-or-edit questions (name, email, phone, location, portfolio
    link, target roles) immediately after ingestion, before any resume
    exists -- and bootstrap never generates an actual tailored resume at
    all. Its final summary just points the user to run a real JD through
    the normal pipeline afterward, as a separate manual step.
  - **Lenient, onboarding-specific quality bar (vs. the production
    believability bar) -- not built.** No distinct threshold logic exists
    anywhere in the Phase 0.5 code or spec.
  - **Capped at the top 2-3 highest-impact gaps -- not built.** There's no
    gap-ranking/cap logic at all. Every extractable field gets its own
    guess-confirm-or-edit prompt unconditionally, rather than a filtered
    short list of the biggest gaps.
  - **The "visible-growth reveal" garnish -- not built as conceived.** What
    exists instead is an accept/regenerate/skip-and-edit-later preview for
    the synthesized `cv.md` and `user-background-guide.md` drafts -- a
    document-review step, not "watch a thin first resume visibly improve
    after adding more material," which was the specific moment Morgan
    wanted.
  - **Net assessment:** the shipped wizard is a reasonable, working
    onboarding flow and solves the hard "how does raw material become
    first-draft evidence" problem correctly -- but it took a different
    shape (guess-confirm Q&A up front + draft-preview-accept for two
    documents) than the specific sequence decided on 2026-07-04 (silent-
    extraction -> thin-resume -> top-3-gap-followups -> visible-growth
    reveal). Worth a conscious call on whether the shipped version is good
    enough as-is or whether the "watch it come alive" garnish specifically
    is still wanted before Dom's actual onboarding session -- that piece
    was the one Morgan was most specific about, and it's the one that
    didn't make it in. See `IDEAS.md`'s Multi-user support entry.
- **CLI visual redesign -- built 2026-07-14**
  (`docs/superpowers/specs/2026-07-14-cli-ux-redesign-design.md`):
  color/icon tokens fully consolidated onto `theme.py` (fixes the "defined
  three different ways across three files" problem the spec opens with), a
  diagonal-gradient splash with a progressive Rich `Live` reveal, live
  stats + rotating "did you know?" tips on the splash, spinners around
  long-running calls (`evaluate_fit()`, bootstrap,
  `orchestrator.run_pipeline`) so a multi-minute Gemini call no longer
  looks identical to a hang, a bordered fit-score table with a
  recommendation color-key legend, a grouped main menu with labeled
  separators + category icons, a compact breadcrumb replacing the
  full-banner loop-back, and a session-end summary tally. Supersedes/
  extends the narrower 2026-07-07 console-polish pass above.
- **Bullet Bank Management menu -- built 2026-07-15**
  (`docs/superpowers/specs/2026-07-15-bullet-bank-management-design.md`): a
  "Manage Bullet Bank" entry in the main interactive menu
  (`scripts/bullet_bank_menu.py`, wired via `menu.py`'s dispatch loop),
  distinct from "New User? Start Here!" (the full ingestion+profile+6-stage
  bootstrap flow, which a returning user doesn't need). It surfaces a
  mtime-based status table across all 6 pipeline stages
  (`audit_bullet_bank.py` -> `cluster_bullet_bank.py` -> `rewrite_bullets.py`
  -> `audit_keepers.py` -> `score_keeper_gems.py` -> `embed_bullet_bank.py`)
  plus two adjacent maintenance scripts (`triage_needs_review.py`,
  `retire_rewrite_queue.py`, surfaced as the submenu's own "maintenance"
  section with its own status line), including in-progress checkpoints, so
  someone mid-rebuild can see which stage they're on and whether a stage's
  output is stale relative to its input, instead of eyeballing file
  timestamps by hand. **Still open:** a top-level, cross-feature
  "Maintenance" submenu (grouping this alongside a future doctor script and
  anything else administrative) -- today maintenance only exists nested
  inside "Manage Bullet Bank," scoped to the bullet bank specifically, not
  as its own general category one level up in the main menu. See
  `IDEAS.md`'s Bullet-bank reintegration entry.
- **`resume polish` / Polish Chat -- built 2026-07-07**
  (`docs/superpowers/specs/2026-07-07-polish-chat-design.md`, same day as
  the Sparkle work above that references it): an interactive terminal chat
  against an already-generated resume/cover-letter JSON -- each turn is a
  free-form instruction answered by a single Gemini call returning the
  complete updated document, shown as a diff requiring explicit
  accept/reject before anything touches disk; accepting re-renders HTML and
  regenerates the PDF immediately. This is what the Sparkle critique-
  signals note above ("try `resume polish` for these") was already
  assuming existed.
- **Gemini-call reliability work -- built 2026-07-15/16.** `GeminiClient`
  gained a `SustainedFailureError` (distinguishing real quota exhaustion
  from a transient blip) and a `model_fallback` opt-out; `rewrite_bullets.py`/
  `audit_keepers.py`/`score_keeper_gems.py` now checkpoint incrementally
  and stop cleanly on sustained failure instead of burning full retry
  ladders per remaining bullet; a new Gemma-specific slim-context tier
  keeps `gemma-4-31b-it` usable under its new (2026-07-14) 16k-TPM cap
  instead of 429ing on nearly every call. `cluster_bullet_bank.py`'s
  embedding step now batches (`batchEmbedContents`) and checkpoints
  incrementally, matching the pattern `embed_bullet_bank.py` already used
  -- **this also resolves the `bullet-bank-clustered.csv` mismatch flagged
  in the Evidence bank Phase 1 section below** (see that section's updated
  note).

**Score/Report wiring -- done 2026-07-16.**
`jd_manager.append_application_row()` now takes an optional `evaluation`
dict (the same shape `read_evaluation()` already returns) and fills
`Score` as `"{composite_score:.2f}/5"` and `Report` as the recommendation
label (e.g. "Strong pursue") when one's present, falling back to the old
`"NA"`/`"—"` placeholders for a JD that was tailored without ever running
through `resume evaluate` first. `orchestrator.py`'s batch-completion loop
reads the pending JD's persisted `_evaluation`
(`jd_manager.read_evaluation(path)`, called alongside the existing
`extract_source_url(path)` call, before the file moves to
`jds/completed/`) and passes it straight through. Covered by new tests in
`tests/test_applications_md.py` (score/recommendation formatting, and the
no-evaluation fallback) and a new end-to-end
`tests/test_orchestrator_main_batch.py` case asserting a real persisted
`_evaluation` shows up correctly in the written row. Full suite (615
tests) passes. See `IDEAS.md`'s List Jobs / View Pipeline entry.

## CLI, track, evaluate, scan stages (items 1.1-1.4) -- done 2026-07-04

| # | Item | Difficulty | Notes |
|---|------|-----------|-------|
| 1.1 | **CLI skin over existing tailor+render** | Easy-Medium | Built: `scripts/cli.py` (Click, `tailor <jd_file>`/`run`) + `scripts/cli_art.py` (rich banner), calling `orchestrator.run_pipeline()` (extracted from `main()`, behavior-preserving -- all 162 tests still pass). `resume run` shell shortcut now routes through it too. `click`/`rich` added to `requirements.txt`. |
| 1.2 | **`track` stage** | Medium | Built: `jd_manager.append_application_row()` appends to `data/applications.md` (career-ops's markdown format, gitignored like the CSV tracker) from `orchestrator.py`'s completion step, alongside the existing `jd_tracker_log.csv` (not replacing it). `Score`/`Report` are placeholders (`NA`/`—`) until 1.3/1.4 exist. No dedup/merge logic ported (single writer today). |
| 1.3 | **`evaluate` stage** | Hard | Built: `resume-engine/prompts/evaluate_fit.md` (career-ops's 10-dimension weighted matrix, verbatim reuse) + `ResumeEngine.evaluate_fit()` (same headless Gemini plumbing as the rest of the pipeline) + `resume evaluate <jd_file>` CLI command. Composite score computed in Python from the model's per-dimension scores, not trusted from the LLM's own math. Deliberately standalone -- no wiring into `run_pipeline()`/`applications.md` yet (no job_key to match a row against, and no `scan` stage feeding it results yet); that integration was a `1.4`-adjacent follow-up. Smoke-tested live against a real JD (`jds/completed/dummy_jd.txt`): correctly scored a strong remote content-strategy match 4.8/5, "Strong pursue," with sane per-dimension reasoning. |
| 1.4 | **`scan` stage** | Hard-Very Hard | Scope decided 2026-07-04: LinkedIn + JobRight only (no career-ops `.mjs` providers this pass), writing straight into `jds/` (no Mongo, no new storage layer -- `jd_manager.job_key_known()` dedupes against `jd_tracker_log.csv` and `jds/` itself). Built: `scripts/scan_jobright.py` (ported from job_automater's `jobright_scraper.py`, zero new deps, plain `requests`) + `scripts/scan_linkedin.py` (ported from `linkedin_scraper.py`; needs `selenium`/`webdriver-manager`/`linkedin-jobs-scraper`/`beautifulsoup4`, added to `requirements.txt`) + `scripts/scan.py` (writes/dedupes into `jds/`) + `resume scan --source jobright\|linkedin` CLI command. **Real fix along the way, not in the original port:** Morgan's `li_at` cookie kept going stale under her old manual copy-paste workflow -- turned out to be LinkedIn's bot-detection invalidating sessions it suspects are automated, not the cookie being inherently short-lived (confirmed: it's set to expire in ~2027 once genuinely live). Fixed with `browser_cookie3`, reading the live cookie straight from her already-logged-in Chrome on every scan call -- automates her exact manual step, cookie never touches disk. Also caught and fixed a real bug during the live test: the port was silently falling back to `linkedin_jobs_scraper`'s deprecated `AnonymousStrategy` because job_automater's `LinkedInConfig.LI_AT_COOKIE` global-config wiring (`config.py` lines 153-157) hadn't been carried over -- added it, confirmed the log now shows `AuthenticatedStrategy`. Live-tested: JobRight twice (209 real JD files now in `jds/`, zero duplicate `source_job_id`s across both runs) and LinkedIn once at a small limit (6 real jobs fetched, `is_top_applicant` detection working) via direct fetch call (not yet run through the full `resume scan --source linkedin` write path, to avoid growing the pending-JD pile further without asking first). **Operational note:** `jds/` held 209 real pending JDs from the JobRight test runs at the time -- running `resume run` as-is would have triggered 209 real Gemini-tailored builds; triaged with `resume evaluate <file>` (1.3) before batch-running. |

**Lean scope for 1.1-1.4 (2026-07-04) -- token/effort efficiency mattered
to Morgan, so these were deliberately reuse-first, not rewrite-first.
Sanity-checked against the real code in job_automater/career-ops on
2026-07-04 -- corrections folded in from that pass:**
- **1.1:** `scripts/cli.py`, Click-based, reusing job_automater's
  `cli_art.py` banner/table style as-is. Commands (`tailor <jd_file>`,
  `run`) just call the existing `orchestrator.py` -- no internals rewrite.
  Skipped a `status` command until 1.2 existed. Confirmed job_automater's
  `cli.py`/`cli_art.py` really are structured this way (Click group,
  separate banner module). One real gap: `click` wasn't in this repo's
  `requirements.txt` yet -- added.
- **1.2:** **correction -- this wasn't a from-scratch "new capability."**
  resume-builder already had a working completion tracker:
  `jd_manager.JDTracker`, CSV-backed at `jds/jd_tracker_log.csv`
  (`job_key, job_title, company_name, source_file, status, date_processed,
  output_json, output_pdf, error_message`), already wired into
  `orchestrator.py`'s completion loop via `mark_completed`/`mark_failed`.
  So 1.2 was really "extend/reshape an existing tracker toward career-ops's
  `applications.md` format" (which adds `Score`/`Status`/`PDF`/`Report`/
  `Notes` columns career-ops's `merge-tracker.mjs`/`dedup-tracker.mjs`
  dedupe against), not building tracking from nothing -- smaller than
  originally scoped. Also: career-ops's `data/pipeline.md` isn't a
  second tracker table -- it's a plain checklist of pending URLs to
  scan/triage, so it was actually 1.4 (`scan`) territory, not 1.2.
- **1.3:** `resume-engine/prompts/evaluate_fit.md`. **Correction --
  it's not an A-F letter-grade rubric.** career-ops's "A-F" refers to
  output *section* labels (Block A, B, C... plus a G legitimacy block in
  `modes/offer.md`), not a grade -- the actual score is numeric out of 5
  (e.g. `4.7/5`, matching the `Score` column above). The "10 weighted
  dimensions" claim is accurate and the real weights (from
  `modes/offer.md`) are: CV/profile match 25%, North Star alignment 20%,
  Remote quality 15%, Level fit 15%, Comp 10%, Growth 5%, Time-to-offer
  5%, Tech/tool 3%, Company reputation 1%, Cultural signals 1%. Ported the
  numeric weighted rubric, not a letter-grade one. Runs through the same
  headless Gemini-API plumbing `orchestrator.py` already had
  (`gemini_client.GeminiClient`, raw REST).
- **1.4:** didn't port everything at once. job_automater's scrapers were
  already Python -- copied directly (confirmed: JobRight is plain REST via
  `requests`, no browser automation; LinkedIn goes through the
  `linkedin_jobs_scraper` package, which is Selenium-backed). career-ops's
  `providers/*.mjs` are Node -- shelling out to them as subprocesses and
  parsing JSON output remains the plan if/when ported, rather than
  rewriting them in Python. **Correction -- there are ~26 providers in
  `providers/`, not the 7 originally named** (Ashby/Greenhouse/Lever/
  Workable/SmartRecruiters/Recruitee/local-parser are real, but so are
  adzuna, remoteok, themuse, usajobs, weworkremotely, workday, and many
  more) -- worth naming which 1-2 Morgan actually uses before picking what
  to port first, since the real menu is much bigger than assumed.

**Deliberately left off this pass:** an `interview-prep` pipeline stage
(porting career-ops's `modes/interview-prep.md`) -- Morgan's call, not
essential right now, revisit later if it turns out to be needed. Still a
real capability worth having eventually, just not part of this ordering.
(Still true as of the last update to this archive -- not built.)

## Cover letter generation -- done 2026-07-04

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

**Why it was simpler than the resume pipeline:** no page-fit trimming loop,
no per-role bullet allocation, no skills-line-wrap validation, no opening-verb
uniqueness constraint. Mostly: a personalized greeting, 2-3 body paragraphs
tying specific JD/company facts to Morgan's background, and a sign-off.

**What existed already going in:**
- `resume-engine/templates/coverletter-template.html` -- a full template with
  `{{DATE}}`, `{{RECIPIENT_BLOCK}}`, `{{GREETING}}`, `{{BODY_PARAGRAPHS}}`,
  `{{SIGN_OFF}}`, `{{TYPED_NAME}}`, `{{TYPED_CONTACT}}` placeholders -- but
  wasn't wired to anything yet before this.
- The existing "Why [Company]?" section in `tailor_resume.md` is first-person,
  company-specific narrative writing -- structurally close to what a cover
  letter body needs, and was the seed/reference for its prompt rules.

**Company research -- what career-ops (`/Users/morganescott/career-ops`) did,
and the architecture mismatch that had to be resolved:**

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
  pasted into Perplexity/ChatGPT/another assistant. Not the thing ported for
  automatic per-JD research.

**The mismatch:** all of this assumed an interactive agent session with live
web-browsing tools available mid-conversation. resume-builder's pipeline is
the opposite shape -- `orchestrator.py` calls the Gemini API directly as a
headless script (no tool-use loop, no live web access). **Resolved by
building an actual web-fetch step in Python** (`scripts/company_research.py`,
plain `requests`/`BeautifulSoup` against the company's About/careers page)
before building the prompt, feeding the scraped text in as context.

**Cover letter's tone-matching rule** (career-ops `modes/coverletter.md`,
"Rule 4 -- Match the company's register," ~lines 173-198) was the blueprint
either way: "mission-driven org -> warmer, more resonant; playful startup ->
sharper, slightly more personality; conventional B2B SaaS -> measured,
crisp, lightly distinctive." Plus a "Company Connection" paragraph that ties
one specific researched fact to Morgan's history, explicitly guarding
against fake flattery.

## Company-values/terminology mirroring in the resume itself -- done 2026-07-05

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

career-ops already did exactly this in `modes/pdf.md` (~lines 502-528),
scoped narrowly on purpose: "tone mirroring applies ONLY to Summary (tone
and word choice, not facts) and the Why section (framing and register).
Never to job titles, dates, bullet achievements, or skills." It maps signals
like formal-vs-conversational register, "we" vs "you" framing, and 1-2
recurring brand words, to be echoed "naturally... where genuinely
applicable" -- explicitly never copying phrases verbatim. That scoping (and
the "never touches facts" boundary) was carried over as-is; it's a
good, already-tested guardrail against tone-matching sliding into
misrepresentation.

## Situational/optional work history entries -- done 2026-07-05

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

**What it did:** let the builder swap in one of Morgan's other real roles
when a JD is specifically relevant to it, instead of always using the same
fixed six (Mercor, Treering, Inside Sales Team, Element 8/Strategy LLC, VML,
Callahan Creek). Examples: Humane Society of Greater Kansas City (animal
welfare roles), Unisource Document Products (print production), Kansas
Colloquies/The Chieftain (journalism), KU Payroll Office and DeJoy Knauff &
Blood (payroll/tax/clerical/sensitive-info roles), USitek (clerical +
graphic design blend). Rare, deliberate use only -- not a default behavior.

Verified bullet content for all of these already existed in
`resume-engine/knowledge_base/bullet-bank-clean.csv` going in.

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
- **A new floor table, inverted from the default trim order for this
  scenario specifically.** `tailor_resume.md`'s existing trim order (line
  ~174) protects Element 8/VML/Callahan Creek down to a floor of 3 and
  treats Treering/Inside Sales Team as flexible-first-to-trim -- tuned for
  the common case where big-name brand/client signal matters most. Morgan's
  call flips this specifically when a situational role is active: Mercor,
  Treering, and Inside Sales Team (her most recent experience) must
  **never** be the ones that shrink to make room, full stop -- so the
  absorbing has to come from Element 8/VML/Callahan Creek instead, even
  though those three are the *protected* trio everywhere else. Written
  down explicitly as its own rule ("floor of 3 normally; floor of 2
  specifically when a situational role is active") rather than left as an
  implicit exception to the existing line.
- **Auditability, not a numeric rarity threshold.** The double-gate
  (keyword match + LLM judgment) already makes this naturally rare by
  construction, so no extra score threshold was judged necessary. One log
  line in `orchestrator.py` fires whenever a situational role actually
  fires, so "rare" stays a checkable fact across real runs instead of an
  assumption.

## Liveness checker -- done 2026-07-05 (Mongo migration still separate/undone)

Investigation found career-ops's actual liveness checker
(`liveness-core.mjs`/`liveness-browser.mjs`) needs zero MongoDB -- pure
Playwright + deterministic classification, no LLM calls. Built: ported
verbatim (`scripts/liveness-core.mjs`, `scripts/liveness-browser.mjs`) +
adapted `scripts/check-liveness.mjs` (new `--json-file` batch mode) +
`scripts/liveness.py` (gathers pending JDs' `source_url`, moves confirmed-
`expired` ones to `jds/expired/`) + `resume liveness` CLI command.
Live-verified against all 208 real pending JDs at the time: 166 active, 7
likely active, 35 uncertain, 0 expired, zero crashes. Spec:
`docs/superpowers/specs/2026-07-05-liveness-checker-design.md`.

**Mongo migration itself remains undone** -- a separate, much bigger
question tied to the long-term three-way merge (see below), not needed for
anything built so far. Tracked as still-open in `IDEAS.md`.

## Sparkle critique signals -- done 2026-07-07

An external brainstorm doc (`SparkleConcept.docx`) proposed scoring
resumes for warmth/memorability/distinctiveness. Investigation found this
project already did much of this piecemeal (`forbidden_phrases` in
`style_rules.yaml`, `hidden_gem_score`/`hidden_gem_flag` in the
bullet-bank scripts, mandatory first-person warmth in `WHY_TEXT`). Scoped
down from the doc's full multi-stage-pipeline vision to a small,
zero-new-API-call extension of the *existing* critique/recommendation-apply
loop: `ResumeCritiqueSchema` gained `distinctive_moments`/`flat_sections`,
and the recommendation-apply loop protects `distinctive_moments` verbatim
+ routes reflective-question recommendations it can't ground in real
context to a new `needs_personal_input` bucket (surfaced as "try `resume
polish` for these" rather than fabricated). Spec:
`docs/superpowers/specs/2026-07-07-sparkle-critique-signals-design.md`.

This surfaced evidence bank extension (below) as a real dependency --
`distinctive_moments` were being rediscovered fresh on every resume build;
a real evidence bank would let that signal persist and feed back into
curation instead.

## Evidence bank Phase 1 -- done 2026-07-07 (research pass + build)

**2026-07-07 -- wiring/gap research pass (findings, verified against real
code, not assumed):**

- **What's actually live-wired into resume building** (all confirmed by
  tracing `orchestrator.py`, not guessed):
  - Step 2 (mine bullet bank): reads **only**
    `bullet-bank-keepers-audited.csv` + its precomputed embeddings
    (`bullet_vectors_ge2_d768.npy`, built by `embed_bullet_bank.py`) --
    confirms only one or two bullet-bank CSVs are truly live-wired;
    everything else in the `bullet-bank-*` family is an earlier curation
    stage feeding toward that one file (`bullet-bank-clean` ->
    `audit_bullet_bank.py` -> `bullet-bank-audited` ->
    `cluster_bullet_bank.py` -> cluster map -> `triage_needs_review.py` ->
    `bullet-bank-keepers.csv` -> `score_keeper_gems.py` ->
    `bullet-bank-keepers-audited.csv`).
  - Step 3 (audit bullets) **and** cover-letter generation both use
    `build_audit_static_prefix()` -- a slim ~5-10k-token context of
    `profile.yml` (trimmed) + `verified_facts.json` + `verified_tools.json`
    + `verified_projects.json` only.
  - Step 4 (build resume, fresh builds only) additionally pulls in the
    full ~457k-token `KB_ALLOWLIST` (`load_knowledge_base()`):
    `article-digest.md`, `bullet-bank.md`, `cv.md`, `evidence-guide.csv`,
    `evidence_graph.json`, `extracted-screenshot-metrics.csv`,
    `morgan-background-guide.md`, `portals.yml`, `profile.yml`,
    `recruiter_memory_patterns.json`, `summaries-and-skills-clean.csv`,
    `treering-archive-readme.md`, `verified-claims.csv`,
    `verified_metrics.json`, plus the three verified_*.json above.
  - **Real finding:** cover letters get the slim Tier-1 context ONLY --
    none of the Step-4-only KB_ALLOWLIST files (`evidence-guide.csv`,
    `verified-claims.csv`, `bullet-bank.md`,
    `summaries-and-skills-clean.csv`, `recruiter_memory_patterns.json`,
    etc.) ever reached cover-letter generation before this.
- **Confirmed genuinely orphaned within resume-builder's own codebase**
  (zero references anywhere in `scripts/*.py`, verified by exact-filename
  grep, not substring-matched): `active-inventory.csv` (444KB),
  `bullet-bank-deduplicated.csv` (478KB), `bullet-bank-gems-report.csv`
  (191KB), `coverage-tracker.csv` (699KB), `detective-findings.csv`
  (232KB), `screenshot-review-log.csv`, and `treering-archive-readme.csv`
  (only the `.md` twin is wired; the `.csv` version of the same content
  isn't referenced anywhere).
- **A real pipeline mismatch, found by accident -- resolved 2026-07-16.**
  `cluster_bullet_bank.py` was configured to write
  `bullet-bank-clustered.csv`, but no such file existed anywhere in
  `knowledge_base/` -- only `bullet-bank-cluster-map.csv`/
  `-cluster-map-updated.csv` existed (which `audit_keepers.py`/
  `rewrite_bullets.py` actually read). Fixed alongside the Bullet Bank
  Management menu build: `cluster_bullet_bank.py` was reworked (commit
  `f46fd064`, "Rework bullet-bank clustering pipeline: audit-score joins,
  next_action classification, path/column-detection fixes") and its
  checkpoint/batching/rate-limit handling was brought in line with
  `embed_bullet_bank.py`'s proven pattern
  (`docs/superpowers/specs/2026-07-16-cluster-embedding-checkpoint-design.md`).
  See `IDEAS.md`'s Bullet-bank reintegration entry.
- **What's in career-ops that resume-builder had none of:**
  - `interview-prep/story-bank.md` -- turned out to be an **empty
    template** (26 lines, all placeholder comments, zero actual stories
    filled in). Nothing to port content-wise; only the STAR+R format is
    worth reusing conceptually, later.
  - `writing-samples/` (291 files) -- **real, substantial, mostly
    untapped.** Actual past cover letters (PDF/docx), "BestCopySamples"
    (newsletter samples, an IT sequence, headline copy), ~20 LinkedIn
    tone/style screenshots, and **`MorganWritingStyleGuide.txt`** (246
    lines, saved as RTF) -- which opens with *"Morgan Escott writes with
    what can only be described as **strategic sparkle**"* and defines
    tone/energy, sentence rhythm, word choice, and power words in real
    detail. This directly predates and validates the Sparkle work above --
    it was Morgan's own pre-existing voice rubric, wired into nothing at
    all in resume-builder before this (not in `KB_ALLOWLIST`, not
    referenced by any prompt). Most other writing-samples files are
    binary (PDF/docx/PNG) and would need conversion (same `textutil`
    approach already used for `SparkleConcept.docx`) to be machine-usable.

**2026-07-07 -- deeper dig.** Follow-up investigation confirmed:
`coverage-tracker.csv` (802 rows), `detective-findings.csv`'s sibling
process-tracking file `screenshot-review-log.csv`, and the `.csv` twin of
`treering-archive-readme` are audit-*process* tracking artifacts (file
review status, completion tracking), not evidence content themselves --
not worth wiring in. `detective-findings.csv` itself *is* real evidence
content (its own README calls it a companion file) but was missing from
`KB_ALLOWLIST`, apparently by oversight. Also dug into career-ops's
`writing-samples/Application Answers/` -- a small (14-row), already-curated
index with themes and "Quote Worth Pulling" lines, real value, nothing
else covering it. The raw "Treering Sequences" archive (140+ files, heavy
duplication, some not even Morgan's own authorship -- files literally
prefixed "ERIKA_") is genuine but needs its own curation pass before it's
usable, same as the original bullet bank did -- **filed as a Tier 2
follow-up, tracked as still-open in `IDEAS.md`.**

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
`Master Cover Letters` skim) remains unscheduled -- tracked as open in
`IDEAS.md`'s Evidence bank extension entry.

## Long-term merge: incident history

These are past incidents from the career-ops/job_automater merge research
-- already resolved/repaired, kept here for context since they directly
informed decisions the still-open merge item makes in `IDEAS.md`.

**career-ops auto-update incident (2026-07-04).** career-ops is a fork of
`santifer/career-ops` and has an `update-system.mjs` (confirmed 2026-07-04:
no git remote is actually named `upstream` -- only `origin` points at her
fork; `update-system.mjs` sources the original repo some other way, worth
checking before relying on `git fetch upstream` for any future audit) that
auto-pulls changes into what its own `DATA_CONTRACT.md` calls "System
Layer" files (all `modes/*.md`, `*.mjs` scripts, `dashboard/*`,
`templates/*`), on the theory that personalization only ever lives in
`config/profile.yml`/`modes/_profile.md`/`cv.md`. In practice a June 2026
auto-update (v1.9.0) silently overwrote Morgan's actual customizations in
`modes/_shared.md`, `modes/apply.md`, the scan/provider scripts, and the CV
templates -- because the contract's own README explicitly invites
hand-editing those "system" files directly ("just ask Claude to change
them"), so real personalization had ended up there despite the documented
rule. Recovered by diffing the update commit against its parent and
reverting only the files nothing had touched since (full account in memory:
`project_career_ops_update_risk`). **Why this matters for the merge:**
whatever "engine vs. profile" separation the merged system ends up with
needs to actually be *enforced*, not just documented -- career-ops had
exactly this separation written down and it still failed in practice.

**job_automater working-copy repair (2026-07-04).** File loss (`config.py`,
`main.py`, `job-agent`/`job-agent-clean`, plus -- discovered during the
actual repair -- the entire `document_generator/` package and the whole
`job_automator/` automation engine, ~55 files total) was fixed: restored
from a fresh ZIP via `rsync --ignore-existing` (so Morgan's customized
scrapers/tailor files were left alone), verified `cli.py`/`main.py` run
end-to-end against the real Mongo data, and committed to git (these files
had existed on disk and run before but had never actually been `git add`ed,
which is how they were silently lost in the first place -- they're tracked
now, so this specific failure mode shouldn't recur). job_automater is no
longer a blocker for merge planning.

**Security flag found during this research (2026-07-04) -- still open, see
`IDEAS.md`'s Easy tier.** `scrapers/recommended_scraper.py` (present in the
working copy) had a **LinkedIn `li_at` session cookie hardcoded in
plaintext**. Checked the fresh ZIP re-download: this file **isn't part of
the actual open-source project at all** -- the real repo's `scrapers/` only
has `__init__.py`, `jobright_scraper.py`, and `linkedin_scraper.py` (which
correctly sources its cookie from `config`, not hardcoded). So this is a
local, ad-hoc script Morgan or something added to her working copy and
never upstream. The 2026-07-04 repair above only restored *missing* files
and deliberately left every existing file untouched, so this one is
exactly as it was found -- **the cookie is a live credential still sitting
on disk and still needs rotating; don't carry the file forward into any
merge.**

**Interview setup -- confirmed doesn't exist in job_automater (2026-07-04),**
not even a partial version. The likely source of the mix-up:
`RESEARCH_FINDINGS_COMPETITORS.md` (a competitive-analysis doc in the repo)
lists "Interview scheduler" as a low-priority, not-yet-built roadmap idea
and notes competitors having "mock interview prep" -- that's probably what
got remembered as an existing feature. career-ops's `modes/interview-prep.md`
(Glassdoor-query-based interview intel) is the thing that's actually built
and worth porting instead, whenever the merge happens.

**Three separate document-generation backends, decided (2026-07-04):
dropped.** `document_generator/` contained `generator.py`/`generator_v2.py`
(reportlab) plus `resume_latex_match.py`/`resume_perfect_latex.py`/
`resume_reportlab.py`/`cover_letter_reportlab.py` -- all LaTeX/reportlab.
Morgan's call: LaTeX output can have real ATS-parsing issues, whereas
resume-builder's existing Playwright/HTML->PDF approach (already
battle-tested -- the DM Sans static-font-instance fix for the PDF
text-scrambling bug, the skills-line-wrap validator, etc.) performs
cleanly. None of job_automater's rendering code carries forward into any
merge; Playwright/HTML is the one true renderer.

**The ATS auto-apply engine, decided (2026-07-04): cut entirely.**
`job_automator/automator_main.py` + `ats_fillers/` (Selenium-based, with
dedicated Greenhouse/Workday fillers) actually navigated to a job posting,
filled out the form, and submitted it. Morgan's call: she wants human eyes
on every application before the final submit button, full stop -- this
inherits career-ops's existing Human-in-the-Loop stance ("the system never
submits an application -- you always have the final call") rather than
job_automater's auto-submit behavior. None of the ATS-filling/submission
code carries forward into any merge; manual intervention isn't a fallback
mode, it's the only mode.

**Jobright scraping (job_automater's original)** --
`scrapers/jobright_scraper.py`. Plain REST API calls (no browser
automation) against a configurable base URL, cookie-authenticated,
paginated, filters out anything below a 70 match score, wrote to MongoDB +
a JSON backup file. (Superseded by the ported `scripts/scan_jobright.py`,
see 1.4 above.)

**LinkedIn scraping (job_automater's original)** --
`scrapers/linkedin_scraper.py`. Browser automation via the
`linkedin_jobs_scraper` package (Selenium under the hood) using hardcoded
search queries, plus a supplementary authenticated `requests`/BeautifulSoup
pass to detect "Top Applicant" badges. Same Mongo + JSON-backup output
pattern as Jobright. (Superseded by the ported `scripts/scan_linkedin.py`,
see 1.4 above.)
