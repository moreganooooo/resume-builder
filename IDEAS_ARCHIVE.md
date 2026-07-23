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

## Engine/profile split: orchestrator.py Morgan-specific constants closed -- done 2026-07-17

The mechanical engine/profile split (`profiles/<name>/`, `scripts/profile_paths.py`,
15 tasks, `docs/superpowers/plans/2026-07-16-engine-profile-split.md`) shipped
2026-07-17 but that plan's own final review found `orchestrator.py` itself
still had several Morgan-specific constants never threaded through
`profile_paths` -- so a second profile's onboarding wizard would run
cleanly, but an actual resume *build* under it would silently pull in
Morgan's data anyway. Two passes, same day, closed all of it:

**Pass 1 -- the four constants the review found:**
- `COMPANY_MIN_BULLETS` deleted -- `mine_bullet_bank()` now builds its
  per-company minimums straight from `profile.yml`'s `roles:` (`min_bullets`),
  the same source `build_role_rules_block()` already read. One source of
  truth, not two -- a real run had previously mined 0 Mercor and 0 Callahan
  Creek bullets out of 30 precisely because this floor didn't generalize.
- `BACKGROUND_IDENTITY`/`BACKGROUND_TAGS` (the persona bio blocks fed into
  every bullet's rewrite context) moved to `profiles/morgan/fixed_content.py`,
  loaded via the same `profile_paths.fixed_content_module()` helper
  `CLIENTS` already used.
- `TREERING_KEYWORDS`/`is_treering_bullet()` replaced by a new
  `deep_evidence_keywords:` field in `profile.yml` and a generic
  `is_deep_evidence_bullet(company, keywords)` -- an empty list (the
  default for a fresh profile) just skips the deep-evidence file bundle
  (verified-claims.csv, screenshot metrics, etc.) entirely rather than
  needing Treering-shaped data. LLM-facing prompt text that used to
  hardcode "Treering" now interpolates the real company name.
- `MorganEscott_` output-filename prefix replaced by a new
  `profile_paths.full_name()` helper reading `candidate.full_name` from
  `profile.yml`, spaces stripped.

`tests/test_mine_bullet_bank.py`'s three tests (which patched the now-gone
`COMPANY_MIN_BULLETS` module dict) were updated to write a fake
`profile.yml` into the test's temp `kb_dir` instead.

**Pass 2 -- a fifth gap the review missed, caught by asking "were KU/KCKCC
handled too?":** the Education Achievement Bullet Selection system had its
own, separate hardcoding, spread across three files:
- `orchestrator.py`'s `TemplateSchema` (the Pydantic class defining
  Gemini's `responseSchema` for every builder/fix/trim call) had
  `KU_ACHIEVEMENT_KEY`/`KCKCC_ACHIEVEMENT_KEY` as *required*
  `Literal[...]`-typed fields with Morgan's exact enum values baked into
  the class definition itself.
- `resume-engine/prompts/tailor_resume.md` hardcoded the same two field
  names and their options as authoritative instructions -- inconsistent
  with the neighboring "Archetype Detection" section, which correctly
  treats its own examples as "illustrative only" and defers to `profile.yml`.
- `bootstrap_bullet_bank.py`'s new-profile scaffold literally wrote
  `KU_ACHIEVEMENT_OPTIONS = {}`/`KCKCC_ACHIEVEMENT_OPTIONS = {}` into every
  fresh profile's `fixed_content.py`, regardless of that profile's real
  schools.

This one was more invasive than pass 1's mechanical moves, because a plain
generic field wouldn't actually work: `GeminiClient.sanitize_schema()`
strips every field's `description` before the schema reaches Gemini (a
regression test in `test_orchestrator_schema_cleanup.py` already existed
to guard exactly this), so only a real JSON-schema `enum` constraint
reliably makes the model pick a valid key -- and the valid keys differ per
profile, unknowable at `TemplateSchema`'s class-definition time. The fix:
- `TemplateSchema` no longer declares any achievement-key fields at all.
- A new `ResumeEngine.build_education_achievement_schema_fields()` builds
  one enum-typed `EDU_ACHIEVEMENT_KEY_<n>` property per `profile.yml`
  education entry that offers a pre-approved achievement-bullet choice
  (new `achievement_options:` sub-field under `fixed_credentials.education`),
  numbered via a new shared `profile_paths.education_achievement_slots()`
  so the numbering can never drift between schema-building and
  response-parsing.
- `GeminiClient.generate()` gained `extra_schema_properties`/
  `extra_required` kwargs that merge into whatever `response_schema` was
  passed, before `resolve_refs`/`sanitize_schema` run -- deliberately
  *not* building a hand-assembled dict schema and passing it as
  `response_schema=` directly, because that would have broken every
  existing test's `response_schema is orchestrator.TemplateSchema` mock
  routing (18+ call sites across `test_orchestrator_build_checkpoint.py`).
  `response_schema=TemplateSchema` still gets passed at all 3 call sites
  in `build_tailored_resume()`, identity intact.
- `normalize_resume.py` maps `EDU_ACHIEVEMENT_KEY_<n>` answers back to
  institution names via the same `education_achievement_slots()` call,
  and `fixed_content.build_education()`'s signature changed from two
  positional strings to one `achievement_keys: dict` keyed by institution
  name (internal `KU_ACHIEVEMENT_OPTIONS`/`KCKCC_ACHIEVEMENT_OPTIONS` dict
  names inside Morgan's own `fixed_content.py` stayed as-is -- that file is
  already profile-internal Python, doesn't need generalizing itself).

JCCC needed no change -- it never had an achievement-key field to begin
with; its single fixed bullet was already handled generically.

Tests updated: `test_orchestrator_schema_cleanup.py` (regression test
rewritten against the new mechanism), `test_fixed_content.py`,
`test_normalize_resume.py`, `test_polish.py`, `test_orchestrator_build_checkpoint.py`
(key rename only, no schema-identity impact), plus two new tests in
`test_gemini_client.py` covering the extra-properties merge itself. Full
suite: 686 tests, all green.

Net effect: a second profile's actual resume build -- not just its
onboarding wizard -- now reads every one of its own mining floors, persona
framing, filename prefix, deep-evidence gating, and education
achievement-bullet options from its own `profile.yml`/`fixed_content.py`,
with zero remaining Morgan-specific fallback anywhere in `orchestrator.py`.
Only remaining blocker before Dom's first real build is `IDEAS.md`'s #7
(per-user `.env` secrets) -- see `IDEAS.md`'s Multi-user support section
for the "Other follow-ups, lower priority" list (still open: the
`jds`/`output`/`data` top-level-to-per-profile path move, stale `CLAUDE.md`
docs, and `build_role_rules_block()`'s ungraceful `KeyError` on a
partially-filled hand-edited `profile.yml`).

**Update 2026-07-17 (a third, broader pass, same day): a full codebase
sweep for anything the first two passes missed (asked directly: "were
KU/KCKCC/JCCC handled too?") found seven more real gaps, none caught by
the engine/profile split's own review since they sit outside
`orchestrator.py`'s builder-schema path -- all closed:**
- `normalize_resume.py`'s `if company == "Treering Yearbooks":`
  (triggering `CAREER_NOTE`) replaced by a new `CAREER_NOTE_COMPANY`
  constant in `fixed_content.py` (empty string default in the bootstrap
  scaffold -- no career note is a valid "nothing configured yet" state).
- `orchestrator.py`'s `CV_SECTION_KEYWORDS` (company-name -> cv.md
  `### heading` map, used by `extract_cv_section()`) moved into
  `fixed_content.py`, loaded via the existing `fixed_content_module()`
  pattern. Degraded gracefully before (fell back to the whole cv.md
  rather than crashing) but lost the per-company excerpt precision for
  any other profile.
- `orchestrator.py`'s `_widow_trim_instruction` no longer hardcodes
  `{"Treering Yearbooks", "Inside Sales Team"}` -- it now checks every
  company actually present in the resume being trimmed. The hardcoded
  version would have been a **complete no-op** for a profile whose
  companies don't happen to match those two literal strings.
- `orchestrator.py`'s 4th (last-resort) trim step, previously a fully
  hardcoded lambda naming Morgan's two highest-bullet-count companies and
  her exact protected-bullet phrasing, extracted into a new
  `_bullet_removal_trim_instruction(profile_data)` that derives both from
  `profile.yml`'s `roles:` (`flex_priority` ordering, `min_bullets`
  floors) and `protected_bullets:` -- the same data `build_role_rules_block()`
  already surfaces to the model elsewhere. **Real behavior nuance for
  Morgan herself:** this now trims Treering Yearbooks before Inside Sales
  Team (both share `flex_priority: 1`, tie broken by `roles:` list order)
  where the old hardcoded text did the reverse -- which also resolves a
  pre-existing self-contradiction, since the ROLE RULES block's own "Trim
  priority" line already told the model Treering-then-IST. Both roles
  stay bounded by their own `min_bullets` floor regardless of which goes
  first.
- Two LLM-facing guardrail strings in `build_audit_static_prefix()`/
  `_gemma()` said "facts about Morgan's career" -- unlike `TemplateSchema`'s
  `Field(description=...)` text (confirmed stripped by `sanitize_schema()`
  before reaching Gemini), these are plain content strings that really do
  reach the model on every call. Reworded to "this candidate's career."
- `validate_coverletter.py`'s `_THIRD_PERSON_PATTERN` hardcoded
  `"Morgan Escott|Morgan|she|her|hers"`. Replaced by a
  `_third_person_terms()` helper reading `candidate.full_name` (always
  available) plus an optional new `candidate.pronouns:` profile.yml field
  -- deliberately never guessed or defaulted for a profile that hasn't set
  it (a wrong pronoun guess is worse than no pronoun check at all), so
  such a profile just gets a name-only check instead of a full no-op or a
  bad guess.
- `scan_linkedin.py`'s `_build_queries()` hardcoded Morgan's 3 tuned
  LinkedIn boolean search strings. A new `linkedin_search_queries:` field
  holds Morgan's exact real searches (hand-tuned boolean queries can't be
  derived automatically); a profile without it falls back to one query
  per `target_roles.primary` entry rather than searching nothing.

**Also swept and found, but deliberately not touched:**
- `scripts/rewrite_bullets.py` is a complete duplicate of the pre-split
  Tier-2 logic (same `TREERING_KEYWORDS`/`BACKGROUND_IDENTITY`/etc.),
  confirmed **not imported anywhere** -- dead code superseded by
  `orchestrator.py`'s own copy, not a live gap. Candidate for deletion in
  the "Repo reorganization / cleanup pass" item, not fixed here.
- The `[email]`/`[ops]`/`[content]`/`[enablement]`/`[sales]`/`[brand]`/
  `[design]` tag taxonomy (`TAG_CONTEXT`, `CLAIM_TAG_KEYWORDS`,
  `tag_bullet_bank.py`'s `TAG_KEYWORDS` -- the last one **actively used**
  during Dom's bootstrap onboarding via `bootstrap_bullet_bank.py`) is
  marketing/sales-vocabulary, baked in throughout the rules engine too
  (`verb_taxonomy.yaml`, `language_quality.yaml`). Not a "leftover" --
  a real design question whose answer depends entirely on whether Dom's
  actual field is marketing-adjacent, which isn't known. Left open.
- `README.md` claims cover letters reference `docs/MorganEscottSignature2025.png`
  for a handwritten signature -- no code anywhere actually reads that
  file; either a removed feature or stale docs, unrelated to multi-user
  since there's no live behavior to fix.

Tests: `test_normalize_resume.py` unchanged (its Treering fixture matches
`CAREER_NOTE_COMPANY`'s real value); `test_trim_widow_bullets.py` gained
a regression test for the "any company, not a hardcoded pair" widow-check
fix and a new `TestBulletRemovalTrimInstruction` class; other fixes had no
existing test coverage to update. Full suite: 690 tests, all green.

**Update 2026-07-17 (a fourth pass, same day): `rewrite_bullets.py` was
NOT dead code -- a real correction after wrongly reporting it as such.**
The "deliberately not touched" list above claimed `rewrite_bullets.py` was
confirmed unimported and safe to delete via a grep that, in fact, silently
failed (an unrelated shell-glob error aborted it before it ran) --
un-verified "no output" got reported as "confirmed no matches." Real grep
shows it's imported by `bootstrap_profile.py` (`RulesBundle`,
`KnowledgeBase`, `build_system_prompts`, `process_bullet`, `RULES_DIR` --
used in `_polish_bullet()` during `write_cv_md()`, i.e. **live in Dom's
actual onboarding wizard**), `audit_keepers.py`, and `bullet_feedback.py`.
Its `KnowledgeBase` class carried the exact same hardcoded
`TAG_CONTEXT`/`BACKGROUND_IDENTITY`/`BACKGROUND_TAGS`/`CV_SECTION_KEYWORDS`/
`TREERING_KEYWORDS`/`is_treering_bullet()`/"Morgan's career" text as
`orchestrator.py`'s pre-fix copy -- meaning every bullet `bootstrap_profile.py`
polished while drafting a new profile's `cv.md` was getting Morgan's
persona identity and Treering-specific evidence injected into the prompt,
regardless of whose onboarding it was.

This surfaced while answering a direct question about whether the wizard
could determine an appropriate **tag taxonomy** from a candidate's own
target roles + ingested source documents, instead of Morgan's hardcoded
marketing-specific `[email]`/`[ops]`/`[content]`/etc. categories (the "real
design question" flagged as left-open above). The two turned out to be the
same underlying problem: `TAG_CONTEXT`/`CLAIM_TAG_KEYWORDS` (`orchestrator.py`)
and `TAG_KEYWORDS` (`tag_bullet_bank.py`) were three separately-hardcoded,
already-drifted copies of the same taxonomy (confirmed by diffing them --
`TAG_CONTEXT` had `[demand]`/`[product]`/`[general]` the other two didn't;
`CLAIM_TAG_KEYWORDS`/`TAG_KEYWORDS` had `[enablement]`/`[mgmt]`/`[writing]`
`TAG_CONTEXT` didn't -- `tag_bullet_bank.py`'s own docstring already
admitted these were "kept in sync by hand"). Fixed together:

- **New `profile.yml` field: `tags:`** -- one canonical list (`name`,
  `persona_description`, `keywords` per tag), generated once during
  bootstrap from that candidate's own target roles and real achievement
  text, replacing all three hardcoded copies. A new
  `profile_paths.tags()` is the one shared reader.
- **`bootstrap_extractors.py`** gained `generate_tag_taxonomy()`, following
  the exact pattern its sibling functions already use (`suggest_secondary_roles`,
  `draft_background_guide`): a `TagTaxonomy`/`TagDefinition` Pydantic
  schema, a prompt instructing the model to base the taxonomy entirely on
  the given roles/achievements (not assume marketing), and an always-included
  catch-all `"generalist"` tag with empty keywords (the established
  "empty keywords = matches everything" convention, preserved from the
  original hardcoded dicts).
- **`bootstrap_profile.py`** calls it right after the identity Q&A (roles
  known) using achievement text already gathered by Phase 0, and writes
  the result into `profile.yml` via a new `tags:` block in
  `_PROFILE_YML_TEMPLATE` -- ordered *before* `write_cv_md()` so
  `rewrite_bullets.py`'s `KnowledgeBase` has real tag data by the time it
  polishes the first bullet.
- **`orchestrator.py`, `tag_bullet_bank.py`, and `rewrite_bullets.py`**
  all now read `profile_paths.tags()` instead of their own hardcoded
  copies -- `_tag_context_map()`/`_claim_tag_keywords_map()` (added to
  both `orchestrator.py` and `rewrite_bullets.py`, identical) and
  `tag_bullet_bank.tag_keywords()`/`fallback_tag()`.
- **`rewrite_bullets.py` also got every other fix `orchestrator.py`
  already had:** `BACKGROUND_IDENTITY`/`BACKGROUND_TAGS`/`CV_SECTION_KEYWORDS`
  now come from `profile_paths.fixed_content_module()`;
  `TREERING_KEYWORDS`/`is_treering_bullet()` replaced by
  `is_deep_evidence_bullet()` reading `profile.yml`'s `deep_evidence_keywords:`
  (a new `self.deep_evidence_keywords` loaded in `KnowledgeBase.__init__`);
  the "Morgan's career" guardrail text genericized; `[Treering+claims]`
  log flag genericized to `[+claims]`.
- **Morgan's own `profile.yml`** got a real `tags:` list -- required, not
  optional: `profile_paths.tags()` returning `[]` for her profile would
  have silently degraded her own persona context to a generic fallback and
  her claims/metrics filtering to an unfiltered `head(max_rows)` on every
  build, a real regression caught before it shipped. The list consolidates
  the union of all three drifted sources into one (9 tags: email, ops,
  content, enablement, mgmt, writing, brand, design, generalist).

**A second real bug, found and fixed in the same pass:** the original
`BACKGROUND_IDENTITY`/`BACKGROUND_TAGS` fix (this entry's first update)
moved those constants out of `orchestrator.py` into `fixed_content.py`,
but never added empty defaults to `bootstrap_bullet_bank.py`'s new-profile
scaffold -- so a freshly-bootstrapped profile's very first real build
would have hit a hard `AttributeError` in `build_background_summary()` the
moment any bullet got audited, not a graceful degradation. Fixed by adding
`BACKGROUND_IDENTITY = ""` / `BACKGROUND_TAGS = {}` to the scaffold, with a
new regression test (`test_scaffold_has_every_attribute_orchestrator_actually_accesses`
in `test_bootstrap_new_profile.py`) that exercises the real consuming
functions against a freshly-scaffolded profile, not just checking that
attribute names exist as strings -- specifically so this class of bug (a
scaffold gap invisible until someone's actual first build) gets caught
here going forward.

Tests: new `TestBulletRemovalTrimInstruction`-style coverage in
`test_bootstrap_profile.py` (tag taxonomy written into `profile.yml`,
`generate_tag_taxonomy()` called and mocked in the writer-order test),
`test_bootstrap_new_profile.py` (the scaffold-completeness regression
above), `test_rewrite_bullets.py` (updated comment only -- its existing
13 tests kept passing unmodified since Morgan's real `profile.yml` now
carries equivalent tag data), and a new `test_tag_bullet_bank.py` (this
script had zero prior test coverage despite being live). Full suite: 696
tests, all green.

## Bootstrap wizard UX + per-profile secrets -- done 2026-07-17

A fifth same-day pass, from real UX feedback after watching the wizard
run: ordering, progress visibility, resumability, and per-profile
secrets/search config. All in `bootstrap_profile.py`/`bootstrap_bullet_bank.py`
unless noted.

- **Draft ordering fixed:** `write_cv_md()` (bullet-polishing) used to run
  *before* `write_background_guide()` in `run_profile_setup()` --
  `rewrite_bullets.KnowledgeBase.__init__` loads `user-background-guide.md`
  at construction time, so every bullet in the first draft was polished
  with that file not yet existing. Swapped. (`self.bg_raw` -- that loaded
  content -- is still not wired into any actual prompt; doing that
  properly means tag-filtering it into the Tier-2 segment bundle like
  `BACKGROUND_TAGS`, not dumping Morgan's real 15KB file into the
  always-included Tier-1 prefix, which would silently inflate every
  build's token cost. Left as a clearly-scoped follow-up, not bundled in
  here.)
- **Bullet-by-bullet visibility added:** `_assemble_cv_draft()`'s loop had
  zero separation between bullets and no success indicator, unlike
  `rewrite_bullets.py`'s real 6-stage pipeline and `orchestrator.py`'s
  audit loop, both of which already print a `───` separator, a
  `[i/total]` counter, and a status line per bullet. Bootstrap's loop now
  matches: separator + `[i/total]` + company line + `✅ KEEP` / `🔧 MANUAL`
  per bullet, plus an upfront total count.
- **Resumability added:** an interrupted `write_cv_md()` run (network
  blip, closed terminal, laptop sleep) used to lose every bullet already
  polished -- up to 3 API calls each, zero incremental persistence. Now
  checkpointed per bullet (keyed by company+text) to a new
  `bootstrap/cv_draft_checkpoint.json`, mirroring Phase 0's own
  `_load_checkpoint()`/`_save_checkpoint()` pattern -- a second call to
  `write_cv_md()` reuses cached results instead of re-polishing. The
  explicit "Regenerate" choice in the accept/regenerate/skip prompt clears
  the checkpoint first, since that's a real request to start over, not an
  interruption to resume from.
- **Per-profile `.env`:** every script's `load_dotenv()` (`orchestrator.py`,
  `gemini_client.py`, `audit_bullet_bank.py`, `cluster_bullet_bank.py`,
  `embed_bullet_bank.py`, `detect_hidden_gems.py`, `ingest.py`) now points
  at a new `profile_paths.env_path()` (`profiles/<name>/.env`) instead of
  one shared project-root file. Morgan's real `.env` migrated to
  `profiles/morgan/.env` (still correctly gitignored -- `*.env` matches at
  any depth). A new `bootstrap_profile.collect_secrets()` walks a profile
  through `GEMINI_API_KEY` and (optional) `JOBRIGHT_COOKIE_STRING`, each
  with real instructions and a genuine "enter it now" vs. "I'll add it
  later, here's the exact file and line" choice -- called from
  `bootstrap_bullet_bank.py`'s `main()` *before* `run_ingestion()`, since
  Phase 0 itself calls the Gemini API for document classification/
  extraction, not just Phase 0.5. Skips the prompt entirely (no
  re-asking) when a var is already set, since bootstrap is re-runnable on
  an existing profile to ingest more documents later.
- **LinkedIn search terms, made per-profile:** `linkedin_search_queries:`
  existed in `profile_paths.py`'s reader (see the third-pass entry above)
  but was never actually in the wizard-generated `profile.yml` template --
  a new profile would silently and permanently fall back to
  `target_roles.primary` with no visible way to set a real boolean query.
  A new `collect_linkedin_search_queries()` explains that LinkedIn
  scanning needs no cookie (live Chrome read, unlike JobRight) but does
  need search terms, shows what the fallback would search for, and offers
  to collect real boolean strings now or defer -- with the exact
  `profile.yml` field name and path if deferred. Wired into the template
  and `write_profile_yml()`.

**A close call during verification, worth remembering:** smoke-testing
`load_dotenv()` changes via `python -c "import audit_bullet_bank"`
triggered that script's *entire* real audit run (no `if __name__ ==
"__main__":` guard -- module-level code executes on import) against
Morgan's live `bullet-bank-audited.csv`. It happened to be a safe no-op
only because that file's checkpoint-resume logic found everything already
scored from a prior real run (confirmed via `git diff --stat` showing
zero byte change) -- not because the test method was actually safe.
Scripts without a main-guard need `ast.parse()` for a syntax check, not a
real `import`, when the only thing being verified is an unrelated
top-of-file change.

Tests: `test_bootstrap_profile.py` gained `TestCvDraftResumability` (3
tests), `TestCollectSecrets` (3 tests), `TestCollectLinkedinSearchQueries`
(3 tests); `test_bootstrap_bullet_bank_pipeline.py`'s four `main()` tests
updated to mock the new `collect_secrets()` call. Full suite: 705 tests,
all green.

## Signature image made per-profile and actually fixed -- done 2026-07-22

Closes the gap flagged in the Doctor-script archive entry above, and
corrects two earlier, incomplete findings about this same feature -- both
worth recording since they show how a `.py`-only grep can miss a real
bug living in a `.html` template.

**The earlier findings, corrected:**
- A pass during the multi-user work (see this archive's "third pass" note
  above) concluded "no code anywhere actually reads that file; either a
  removed feature or stale docs" -- true only because that grep never
  checked `.html` files. `resume-engine/templates/coverletter-template.html`
  had `<img src="./docs/MorganEscottSignature2025.png">` hardcoded the
  whole time.
- Yesterday's Doctor-script entry flagged this as "hardcoded, not
  profile-specific" -- accurate, but incomplete. The real, deeper bug,
  found today by actually tracing how `generate-pdf.mjs` loads the
  rendered HTML: it writes the HTML to a temp directory
  (`os.tmpdir()/resume-pdf-*/resume.html`) before navigating Chromium to
  it -- a real fix for a font-loading bug, per that file's own comment.
  A relative `./docs/...` path in the HTML resolves against *that temp
  directory*, not the real project. **This feature has never actually
  worked, for any profile, since the day that temp-file fix shipped** --
  independent of whether the PNG file ever existed on disk.

**Built:**
- `profile_paths.signature_path(profile=None) -> str | None` -- checks
  `profiles/<name>/signature.{png,jpg,jpeg}` in that order, returns the
  first that exists or `None`.
- `resume-engine/templates/coverletter-template.html`'s hardcoded `<img>`
  replaced with a `{{SIGNATURE_BLOCK}}` token, same pattern as the
  existing `{{RECIPIENT_BLOCK}}`/`{{BODY_PARAGRAPHS}}` tokens.
  `render_coverletter.build_signature_block_html()` renders either a real
  `<img>` tag or an empty string -- true graceful degradation (no
  element at all), not a broken reference.
- **Fixes the actual bug, not just the hardcoding:** the `<img>` tag now
  uses an *absolute* `file://` path
  (`file:///Users/.../profiles/morgan/signature.png`) built directly in
  Python, sidestepping the temp-dir problem entirely -- no relative path
  involved, so nothing for the temp-file move to break. Mirrors
  `generate-pdf.mjs`'s own already-proven fix for the exact same class of
  bug with font files (absolute `file://` paths to `resume-engine/fonts/`,
  a different directory than the temp HTML file, confirmed working) --
  same fix, applied on the Python side this time instead of needing a
  second rewrite pass in the Node script.
- `doctor.py`'s signature check now reports the active profile's real
  `signature_path()` result instead of a hardcoded, Morgan-only path.
- `.gitignore`: `profiles/*/signature.{png,jpg,jpeg}` -- a handwritten
  signature is personal, identifying content, same conservative posture
  this repo already takes on scanned-JD PII. Verified the pattern
  actually matches before relying on it.
- README's signature section rewritten to describe the new per-profile
  location instead of the old hardcoded one.

Full suite: 856 tests (12 new), all green. Smoke-tested end to end with a
real placeholder PNG before writing this up -- confirmed
`signature_path()` finds it and `build_signature_block_html()` emits the
correct absolute `file://` `<img>` tag.

## Doctor script + Maintenance submenu -- done 2026-07-22

Built together as scoped (the docs already flagged the Maintenance
submenu as the doctor script's intended home -- building doctor as a
standalone entry first, then relocating it, would've been throwaway
work).

**A real finding along the way, not a hypothetical:** while scoping the
Node/Playwright check, direct inspection of this actual checkout found
`node_modules/` doesn't exist at all right now -- `package.json` correctly
lists `playwright` as a dependency, but it's never been installed here, so
`generate-pdf.mjs`'s `import { chromium } from 'playwright'` would fail if
a real build ran. `resume doctor` catches exactly this and reports the fix
(`npm install`). Confirms the whole premise of the feature on its first
real run, not just in tests.

**Also found and flagged, not fixed (separate decision):** the cover-letter
template (`resume-engine/templates/coverletter-template.html`) hardcodes
`src="./docs/MorganEscottSignature2025.png"` -- confirmed via direct grep,
not parameterized by profile at all, a leftover gap the four multi-user
sweeps (2026-07-17) never caught since it's a template asset, not a Python
constant. Doctor's signature check reports this as informational-only
(matches the README's already-documented graceful degradation), and
explicitly does not try to fix the underlying gap -- making the signature
profile-configurable is a real, separate feature decision, not a doctor-
script concern.

**Built:**
- `scripts/doctor.py` -- 11 checks (Python version, `.venv/` active,
  every `requirements.txt` package actually importable via a real
  pip-name -> import-name map, Node on PATH, the `playwright` npm package,
  a Playwright Chromium install under `~/Library/Caches/ms-playwright/`,
  `GEMINI_API_KEY`, `JOBRIGHT_COOKIE_STRING` as optional/informational,
  DM Sans font files, the signature image as informational, and the
  active profile's `KB_ALLOWLIST` files) plus `run_test_suite()` (the
  real suite, real subprocess). Pure logic, no printing -- matches
  `liveness.py`/`scan.py`'s existing split between logic and
  `cli_art.py`-owned rendering.
- `cli_art.render_doctor_report()` -- a table plus a plain-English "N
  problem(s) found" summary with a one-line suggested fix per failure, per
  the original spec.
- `scripts/maintenance.py` -- `record_run()`/`get_last_run()`, one small
  gitignored JSON file per profile (`profile_paths.maintenance_log_path()`
  -- already covered by the existing `*_log.json` gitignore pattern, no
  gitignore change needed), keyed by task name so it generalizes to future
  maintenance tasks without a schema change.
- New top-level "Maintenance" menu entry -> a submenu currently housing
  "Run Doctor Checks" (shows "last run: <date>" / "never run"), and a
  `resume doctor` / `resume doctor --skip-tests` CLI command (added to
  `HELP_ENTRIES`). **Scope decision, not in the original ask:** deliberately
  did NOT relocate "Manage Bullet Bank"'s own already-working Ongoing
  Maintenance section (`triage_needs_review.py`/`retire_rewrite_queue.py`,
  built 2026-07-15) into this new submenu -- that stays exactly where it
  is, since it's real, working, bullet-bank-specific UI; duplicating or
  tearing it out for a second entry point would have been churn without a
  real payoff. The new Maintenance submenu is the general home for
  cross-cutting admin tasks that aren't specific to any one domain.

Full suite: 848 tests (40 new), all green.

## Follow-up cadence tracking + contact/outreach finder -- done 2026-07-22

Both found in the 2026-07-21 sibling-repo audit; both turned out to have
real complications only visible once the actual data was checked
directly, not from career-ops's file sizes alone.

**Follow-up cadence tracking (career-ops's `modes/followup.md`), tracking
half only:**
- **Real prerequisite found before building anything:** career-ops's
  cadence classification depends on an application's status progressing
  (Applied -> Responded -> Interview). Checked `jd_manager.append_application_row()`
  directly -- resume-builder's `applications.md` writes exactly one
  hardcoded status, `"Tailored"`, and nothing ever updates it. There was
  nothing to classify until that gap closed.
- Closed it using the existing per-JD-JSON metadata pattern
  (`_evaluation`/`_liveness`) rather than trying to rewrite markdown table
  rows in place: `jd_manager.save_application_status()`/
  `read_application_status()` persist an `_application` block
  (`status`, `applied_at` -- set once, never overwritten by a later
  status change -- `status_changed_at`, `follow_up_count`,
  `last_followup_at`) directly on the JD's own JSON.
- `followup.py` (new module): `compute_urgency()`, a straight port of
  `followup-cadence.mjs`'s date-math thresholds (7 days to first
  follow-up, 7 more between subsequent ones, cold after 2, 3 days for a
  "responded" reply, 1 day for a post-interview thank-you) -- pure
  function, no LLM call, no network.
- Surfaced in "Browse & Manage Jobs": a new "Follow-up" column on the
  pipeline table (status + colored urgency), plus two new single-JD
  actions for Completed-status rows -- "Update Application Status"
  (select from `jd_manager.APPLICATION_STATUSES`) and "Log a Follow-up
  Sent" (shown only once a status exists).
- **Deliberately not built:** the actual follow-up message drafting
  (career-ops's other half of this mode). Flagged in `IDEAS.md` as a
  small remaining piece now that `draft_outreach_message()` (below)
  exists as prior art for the same shape.

**Contact/outreach finder (career-ops's `modes/contact.md`):**
- **Real fabrication risk found before building anything:** the mode's
  actual job is surfacing real, named people at a company -- an
  ungrounded LLM call here risks hallucinated names/titles, a serious
  problem for a system whose whole identity is "never fabricate."
- **Then a much better answer than either grounding or role-archetypes-only
  was found by checking real scanned data:** `scan_jobright.py` already
  captures `social_connections`/`personal_social_connections` from
  JobRight's own API response into every JobRight-sourced JD file --
  confirmed on a real file on disk (an actual named person, title, and
  LinkedIn URL, already surfaced by JobRight itself, sitting unused).
  Zero fabrication risk this way: nothing is generated or guessed, only
  quoted from an already-real, already-scraped source.
- **LinkedIn-sourced JDs confirmed NOT to have this, and confirmed why,**
  via a live empirical test (not assumed): `scan_linkedin.py` hardcodes
  both fields to `None`. Tested LinkedIn's "People you can reach out to"
  panel directly against a real posting Morgan confirmed shows the panel
  on her screen -- an authenticated fetch of the exact same URL (same
  mechanism `_fetch_personalized_extras()` already uses successfully for
  "Top Applicant" detection) contained none of the panel's markers. The
  panel is rendered client-side after page load, not in the HTML a plain
  fetch can see, even authenticated. Real browser automation would be
  needed to capture it -- a materially bigger lift than anything else
  built this session, and deliberately not pursued. LinkedIn-sourced JDs
  get `[]` from `find_jd_contacts()`, not an error.
- Built: `orchestrator.find_jd_contacts(jd_data)` (module-level, pure
  data-shaping, no Gemini call) flattens both connection sources into
  `{name, title, company, linkedin_url, connection_type}` dicts, skipping
  any entry with no name. `ResumeEngine.draft_outreach_message(jd_path,
  contact)` (one Gemini call, `resume-engine/prompts/draft_outreach.md`)
  drafts a short, specific message to an already-real contact -- the
  prompt explicitly forbids fabricating any shared connection or prior
  interaction beyond what's given. New "Draft Outreach Message" action in
  "Browse & Manage Jobs" (available regardless of Pending/Completed
  status), prompting for which contact when more than one is found.

Full suite: 808 tests (41 new), all green.

## Follow-up message drafting -- done 2026-07-22

Closed the one piece deliberately left open above: career-ops's
`modes/followup.md` drafting half. `draft_outreach_message()` was
prior art for the shape (one Gemini call, real JD + real context, short
message) but not a drop-in -- a follow-up has different constraints an
outreach message doesn't:

- New `resume-engine/prompts/draft_followup.md`, mirroring career-ops's
  drafting rules (1st vs. 2nd follow-up structure/length, banned
  "just checking in"-style phrasing, exactly one real proof point from
  `cv.md` tied to something the JD actually asks for, contact-type-aware
  addressing, LinkedIn-note-length vs. email framing).
- `ResumeEngine.draft_followup_message(jd_path, follow_up_count,
  contact=None)`: grounds on `cv.md` alone rather than the full ~250k-token
  knowledge base -- a 2-4 sentence message doesn't need that much context,
  and `cv.md` is already the curated, traceable source the prompt draws
  its one proof point from. Doesn't re-derive urgency itself; callers gate
  on `followup.compute_urgency() == "overdue"` before calling it.
- Unlike `draft_outreach_message()`, `contact` is optional here --
  career-ops's own spec drafts a generically-addressed email
  ("the hiring team") when no contact is known rather than skipping the
  follow-up entirely, since a follow-up (unlike a cold outreach) doesn't
  need someone specific to address.
- New "Draft Follow-Up Message" action in "Browse & Manage Jobs", shown
  only when `followup.compute_urgency(row["application"]) == "overdue"`
  (never for "waiting" -- too soon -- or "cold" -- already two unanswered
  follow-ups, a different problem). Reuses `find_jd_contacts()` for the
  same real-contact-or-generic prompt as outreach. After the draft
  prints, asks "Did you send this?" and logs it via the existing
  `_handle_log_followup()` on confirmation -- closing the loop career-ops's
  own spec calls for (record a follow-up only after it's actually sent).

Full suite: 870 tests (14 new), all green.

## "Update My Knowledge" flow -- done 2026-07-21

Filed as Hard, on the assumption that the six-stage pipeline's
checkpointing needed new "append, don't rebuild" logic to be safe on a
second run. **Checked all six stages directly before writing any code --
turned out mostly already true, for free:**
- `audit_bullet_bank.py`, `rewrite_bullets.py`, `audit_keepers.py`,
  `score_keeper_gems.py` all checkpoint by **bullet-text content**, not
  row position -- re-running them on a regenerated `bullet-bank-clean.csv`
  (old bullets + new ones) already skips everything previously processed
  and only touches genuinely new bullets.
- `cluster_bullet_bank.py`/`embed_bullet_bank.py` checkpoint by **row
  index** instead -- riskier under a grown file. Decided not to bet on
  index-resume math staying valid across a rebuild; an update run just
  forces a full re-cluster/re-embed instead. Bounded cost at today's bank
  size (~1,400 rows), not a real scalability problem.
- `run_ingestion()`'s own draft outputs (`timeline.json`,
  `bullet-bank-clean.csv`) already **regenerate from the complete
  accumulated checkpoint** every run (old files skip re-extraction, but
  their stored results still feed the rebuild) -- so there was no real
  "append vs. rebuild" problem to solve there either; a full rebuild from
  complete accumulated data already produces the correct end state.
- `bootstrap_profile.collect_secrets()` already explicitly documented
  itself as safe to re-run on an already-configured profile -- confirmed,
  no changes needed.

**One real gap found and closed:** `write_profile_yml()` was the only
Phase-0.5 writer with no accept/regenerate/skip protection (unlike
`write_cv_md()`/`write_background_guide()`/`write_voice_anchors()`, all
of which already have a real preview loop) -- it would have silently
clobbered any hand-edited `profile.yml` on a second run. Now gated: if
`profile.yml` already exists, confirms before overwriting (declining
leaves the existing file untouched); no prompt at all on a first-time
cold start, since there's nothing to lose yet.

**Scope decision, asked directly rather than assumed:** should "Update My
Knowledge" also re-run Phase 0.5 (cv.md/profile.yml/background guide), or
stay scoped to just the bullet bank? Morgan's answer -- a genuine
third option, not either of the two offered: let the user choose per run,
via a checkbox ("Bullet Bank" / "Profile & Background Documents"),
defaulting both checked. Implemented as `bootstrap_bullet_bank.py`'s new
`--scope {bullets,profile,both}` CLI flag -- Phase 0 ingestion always
runs first regardless of scope (it's what actually processes new files),
`--scope` only gates what runs after it.

**Built:**
- `bootstrap_bullet_bank.py main()`: `--scope` flag, default `"both"`
  (preserves the original cold-start behavior exactly for every existing
  caller).
- `menu.py`: new "Update My Knowledge" entry (right under "New User?
  Start Here!"). Gated on `bootstrap_bullet_bank.CHECKPOINT_PATH` already
  existing (i.e. Phase 0 has run at least once for this profile) --
  otherwise points the user at "New User? Start Here!" instead. Checks
  `source_documents/` for new files (same proactive-instructions message
  bootstrap's own empty-folder case already uses), then the scope
  checkbox, then shells out to `bootstrap_bullet_bank.py --scope <value>`
  exactly like cold-start bootstrap already does.

Full suite: 767 tests (15 new), all green.

## "Browse & Manage Jobs": multi-select pickers + List Jobs + comparison mode unified -- done 2026-07-21

Three separately-tracked Hard/Medium-Hard items (#11 multi-select "Specific
JD" pickers, #15 "List Jobs"/"View Pipeline" browsing, and the sibling-repo
audit's "Multi-job comparison mode") turned out to be one feature, not
three -- all were really "browse/act on multiple already-evaluated JDs at
once." Two design decisions locked in before building (asked directly,
not assumed): the new view **replaces** the three old single-JD-by-name
pickers ("Evaluate/Tailor/Write Cover Letter for a Specific Role") rather
than sitting alongside them, and **absorbs** the old "View Application
Tracker" markdown-table entry entirely rather than keeping both.

**Data layer (`jd_manager.py`):**
- `save_evaluation()` now also persists `archetype`/`dimension_scores`
  (previously computed and discarded, same gap `why` used to have) --
  needed for the browse view's per-JD detail drill-in.
- New `ARCHIVED_DIR` (`jds/archived/`) and `archive_jd()` -- a JD's fourth
  terminal state, distinct from `completed/` (no resume necessarily
  built) and `expired/` (liveness decided it, not a person). One-way for
  now, no un-archive UI. Needs no exclusion logic in
  `get_pending_jds()`/`get_completed_jds()` -- both already only scan
  their own specific directory.

**Selection layer (`picker.py`):** `list_all_evaluated_jds()` combines
`get_pending_jds()`/`get_completed_jds()`, filters to JDs carrying a
persisted `_evaluation`, tags each with its status, sorts best-score-first
(same pattern the now-removed `pick_one_evaluated_jd()` used).
`browse_and_select_jds()` renders the overview table then a
`questionary.checkbox()` multi-select over the same rows, returning full
row dicts (not just paths) so downstream code never has to re-fetch.
**Removed as genuinely dead code** (zero remaining callers after the
menu restructure): `pick_one_pending_jd()`, `pick_one_evaluated_jd()`.

**Rendering (`cli_art.py`):** `render_pipeline_table()` (# / Score /
Recommendation / Company / Title / Status / Last Liveness -- the actual
"List Jobs" ask). `render_comparison_table()` (the "Multi-job comparison"
ask) -- one column per selected JD, one row per fit dimension plus
score/recommendation/archetype, so a strength/weakness pattern is visible
across jobs at a glance rather than holding several single-JD views in
your head.

**Menu (`menu.py`):** one new entry, "Browse & Manage Jobs," replaces
four old ones (`evaluate_one`, `tailor_one`, `coverletter_one`,
`view_applications`). Selecting exactly one JD opens a per-item action
menu (View More Details / Tailor -- Pending only / Write Cover Letter --
Completed only / Archive / Back); selecting 2+ opens a bulk menu (Compare
Selected / Tailor Resumes for Selected -- Completed rows silently
skipped, matching the old single-picker's same constraint / Write Cover
Letters for Selected -- shown only when every selected row is Completed /
Archive Selected / Back). `_CHAIN` updated: `evaluate_all` and
`tailor_all` now offer "Browse & Manage Jobs" as a next step in place of
the retired `coverletter_one` destination.

**One disclosed behavior change, not a bug:** there's no dedicated
"evaluate one specific not-yet-evaluated JD by name" flow anymore -- the
browse view's whole premise is *already-evaluated* JDs. "Evaluate ALL
Pending Roles" still covers this (it already skips already-scored JDs by
default, so re-running it after adding one new JD is cheap), just not via
a pick-by-name single-eval entry point.

Full suite: 752 tests, net +10 from real churn (retired pickers'/handlers'
tests removed, new data/selection/render/menu-layer tests added) -- all
green.

## Company-research fallback lookup: search-grounding spike + build -- done 2026-07-21

Closes the real design question left open in "Standardize company
research across JD sources" after its mechanical half (`scan_linkedin.py`
passing through `company_link`) shipped earlier the same day.

**The spike, run before writing any code:** tried a live test call to
`gemini-3.1-flash-lite` with `tools: [{"google_search": {}}]` via this
project's existing REST client to confirm grounding actually works on
this account/model combo. Got a real `429 RESOURCE_EXHAUSTED` both times
(not transient -- retried once) -- the account's Gemini quota was fully
exhausted at the time, so live verification couldn't complete. Rather
than block on that, designed around the one grounding constraint that's
been stable and well-documented regardless of live-test results: Google
Search grounding and structured JSON output (`response_schema`) can't be
combined in a single Gemini call. The build below never attempts to
combine them, so it doesn't depend on the blocked spike's answer -- worth
a real live smoke-test once quota resets, but not a blocker to shipping.

**Built:**
- `gemini_client.py`'s `GeminiClient.generate()` gained an optional
  `tools` parameter (reaches the request body as `body["tools"]` when
  set) plus an explicit `ValueError` if both `tools` and `response_schema`
  are passed together -- catches the incompatibility above at the call
  site instead of surfacing as a confusing API-level 400 far from the
  mistake.
- `company_research.py` gained `find_company_website(company_name)`: a
  separate, plain-text grounded call (no `response_schema`) that asks for
  just the official homepage URL, extracts it via regex from the
  response, and rejects matches on job-board/reference-site domains
  (`_REJECTED_DOMAINS`: linkedin.com, indeed.com, glassdoor.com,
  wikipedia.org, etc.) that grounding could plausibly surface instead of
  the real company site. Returns `None` (never raises) on any failure
  mode, matching `research_company()`'s existing "None means proceed as
  if this feature didn't exist" contract.
- `ResumeEngine.research_company()` now calls this fallback when
  `jd_data` has no `company_website` at all, before giving up -- if
  found, the existing scrape-then-extract flow (`fetch_company_pages()` +
  the structured `CompanyResearchSchema` call) proceeds completely
  unchanged. This is the piece that actually helps LinkedIn-sourced JDs
  specifically, since `scan_linkedin.py`'s `company_link` fallback
  (shipped the same day) is a LinkedIn URL that mostly fails
  `MIN_USEFUL_CHARS` -- this grounded lookup is the real fallback for
  those cases, not the LinkedIn-URL passthrough.

Full suite (742 tests, 13 new) green -- all new tests mock
`GeminiClient.generate`/`requests.post`, none depend on live API access,
so they're unaffected by the quota exhaustion that blocked the spike.

## Four highest-impact-per-effort backlog items -- done 2026-07-21

Picked via an explicit impact-vs-effort pass over the whole backlog
(highest daily-workflow impact for the least build complexity), then
built in that order. Full suite (729 tests, 9 new) green.

- **LinkedIn JDs never got company research, closed.** `scan_linkedin.py`
  hardcoded `"company_website": None` unconditionally, so every
  LinkedIn-sourced resume/cover letter silently skipped
  `ResumeEngine.research_company()` entirely, while JobRight-sourced ones
  got it. Now passes through `company_link` (LinkedIn's own
  `/company/<slug>` page -- the only company-related URL the
  `linkedin_jobs_scraper` library exposes) instead. Honest caveat kept in
  a code comment: this is a LinkedIn URL, not an external domain, and
  LinkedIn blocks unauthenticated scraping on most of its pages --
  `company_research.py`'s existing `MIN_USEFUL_CHARS` graceful
  degradation makes this low-risk but also probably low-yield, not a full
  fix. The real fallback-lookup design question (AI-searches-for-website)
  stays open in `IDEAS.md`.
- **Posting-legitimacy check, closed.** career-ops's original 6-block
  evaluation had a scam/ghost-posting legitimacy assessment that didn't
  survive the 2026-07-04 port -- confirmed missing via direct grep before
  building anything. Added `posting_legitimacy`
  ("High Confidence"/"Proceed with Caution"/"Suspicious") and
  `posting_legitimacy_notes` to `FitEvaluationSchema` and
  `evaluate_fit.md`'s prompt (condensed from career-ops's original Block
  G criteria: posting freshness, description quality, practical
  credibility), persisted via `save_evaluation()`, and surfaced two
  places: the single-JD evaluate view (`_handle_evaluate_one`, shown only
  when not "High Confidence" so the common case stays uncluttered) and an
  inline flag on the batch fit table's Recommendation column. Also fixed
  one leftover gendered pronoun ("her real experience" -> "the
  candidate's real experience") found while editing the same prompt file
  -- a genuine miss from the four full multi-user sweeps back on 2026-07-17.
- **Liveness skip-by-recency, closed.** `run_liveness_check()` used to
  re-check every pending JD's URL every run, even one confirmed `active`
  five minutes ago. New `jd_manager.save_liveness()`/`read_liveness()`
  (mirrors `save_evaluation()`/`read_evaluation()` exactly) persists a
  `_liveness` block (`result`, `reason`, `checked_at`); `RECENCY_HOURS = 24`
  and `liveness.split_recently_checked()` skip anything checked inside
  that window by default, with a `--refresh` CLI flag (`resume liveness
  --refresh`) to force a full re-check. **Also seeded at scan time:**
  `scan.py`'s `_write_jd_file()` now stamps a fresh `_liveness` block
  (`result: "active"`, reason `"confirmed to exist by scan"`) onto every
  newly-written JD, so a posting found 5 minutes ago is already inside
  its freshness window instead of triggering an immediate, redundant
  separate check -- directly resolves the 2026-07-17 real-world data point
  (104 JobRight results, 30 confusing `uncertain`s from same-minute
  re-verification of brand-new results). Doesn't fix the aggregator-DOM
  `uncertain` noise itself (still a separate, harder problem, noted as
  such in the original write-up). **Side fix along the way:**
  `jd_manager.read_jd_text()` generalized from hardcoded
  `_evaluation`-only stripping to stripping any underscore-prefixed
  metadata key, so `_liveness` (and anything persisted later) can never
  leak into a Gemini prompt as job-description content -- exactly the gap
  the original backlog item flagged as a risk if liveness ever read JD
  content directly.
- **`batch_evaluate.py`'s missing `───` separator, closed.** The smallest
  of the four -- one line, matching the same divider convention already
  used in `orchestrator.py`/`bootstrap_profile.py`'s progress loops. Left
  `liveness.py`'s half of this same backlog item open (a real streaming-
  architecture change, not a print statement -- `check-liveness.mjs`
  still returns one captured blob per batch, not incremental results).

## Interactive-menu Help entry + emoji modernization -- done 2026-07-20

Two Easy-tier items closed in one pass.

- **Help command in the interactive menu, closed.** `cli_art.HELP_ENTRIES`
  (a plain list of (command, description) tuples) plus `cli_art.display_help()`
  is now the single source of truth for the shortcuts cheat sheet --
  `scripts/cli.py` gained a `help` command that calls it, `menu.py`'s
  `_CHOICES` gained a "Help" entry (`theme.ICONS['hint']`) under the
  Utility section that calls the same function, and `scripts/resume-cli.sh`'s
  `help)` case now just shells out to `python scripts/cli.py help` instead
  of its own hardcoded `echo` lines -- closing the "content lives in two
  (arguably three) places" wrinkle the item originally flagged.
- **Modernize emojis in rewrite_bullets.py / orchestrator.py, closed.**
  Every ad-hoc emoji in both files' print statements (~95 occurrences
  across the two files) now resolves through `theme.ICONS` instead of a
  hardcoded glyph, following a 3-bucket mapping: success/done/loaded/
  accepted states -> `theme.ICONS['success']`; could-not-load/cache-miss/
  parse-error/fallback-triggered states -> `theme.ICONS['warning']`;
  everything else (progress announcements, config stats, informational
  one-liners with no existing theme concept) -> `theme.ICONS['hint']`, the
  same general-purpose FYI icon `cli_art.py`'s tip panel already uses --
  deliberately not stretching `discovery`/`evaluate`/`build`/`utility`/
  `bullet_bank` to cover unrelated meanings, since those are tied to
  specific menu-domain concepts elsewhere. Plain (non-f) print strings
  got an `f` prefix added where needed so the interpolation actually
  evaluates. Full suite (720 tests) green after both changes.
- **Follow-up, same day: bootstrap_profile.py and bootstrap_bullet_bank.py
  swept too, closing the gap flagged above.** `bootstrap_profile.py`'s own
  unconverted `✅`/`🔧` KEEP/MANUAL status pair (built 2026-07-17, after
  the menu's icon system already existed) now uses `theme.ICONS['success']`/
  `theme.ICONS['warning']`, plus one `📝`-prefixed progress line ->
  `theme.ICONS['hint']`. While in there, `bootstrap_bullet_bank.py`
  turned out to have the same drift -- its `_STAGE_HINTS` dict (6 entries)
  used a raw `\U0001F4A1` (💡) literal that happened to already be the
  *exact same glyph* as `theme.ICONS['hint']`'s Unicode fallback, just not
  wired through `theme` (so it wouldn't respect
  `RESUME_BUILDER_ICONS=unicode`/Nerd-Font switching); one closing
  `\U0001F389` ("All done!") -> `theme.ICONS['success']`. `bootstrap_extractors.py`
  checked and already clean, no emoji at all. Full suite (720 tests) green.

## Onboarding copy, evaluate rationale, voice-anchor drafting -- done 2026-07-17

A sixth same-day pass, closing three items straight off `IDEAS.md`'s Easy
and Medium tiers plus part of a fourth. Full suite (716 tests) green.

- **Proactive first-step onboarding copy (Easy tier item, closed).**
  `menu.py`'s `_handle_bootstrap()` used to only mention the
  `source_documents/` folder reactively, once someone had already picked
  "New User? Start Here!" and the folder turned up empty. Now prints
  Morgan's proposed copy (hyperlinked real path, document-type examples --
  resume, LinkedIn PDF export, recommendation letters, certifications,
  writing samples) proactively, before that fallback case is even
  reached.
- **Evaluate report "why" rationale (Medium tier item, closed).**
  `evaluate_fit()` was already computing a `why` field and discarding it.
  `jd_manager.save_evaluation()` now persists it into `_evaluation`
  alongside `composite_score`/`recommendation`/`hard_blockers`/
  `evaluated_at`; `batch_evaluate.py` surfaces a short excerpt in the
  batch fit table and the full text on a single evaluation. Partially
  closes the "List Jobs" Hard-tier item's "eval notes may need richer
  persistence" open question too -- the one-line case is covered, full
  per-dimension `dimension_scores`/`archetype` persistence for a real
  drill-in view is still open.
- **Voice-anchor drafting during bootstrap (Medium tier item, closed).**
  New `bootstrap_extractors.draft_voice_anchors()` (mirrors
  `draft_background_guide()`'s pattern) drafts `voice-anchors.md` from
  writing-sample source docs, sequenced in `bootstrap_profile.py` before
  `cv.md` since voice anchors are actually injected into the
  bullet-polishing prompt. Previewed through the same accept/regenerate/
  skip UX as cv.md and the background guide.
- **`scan.py` progress display (one piece of the still-open "Prettier,
  live progress" Medium item).** Now shows `[i/total]` and an explicit
  skip-reason per job, matching the pattern established elsewhere this
  session. `liveness.py` and `batch_evaluate.py`'s separator-polish are
  still open -- see `IDEAS.md`.
- **Dry-run bug fix caught in review:** `_polish_bullet()` was writing a
  real checkpoint file even under `dry_run=True`; fixed alongside the
  above.

## JCCC education line wrap -- closed (fixed 2026-07-05, confirmed 2026-07-20)

Flagged as a low-priority Easy-tier item: the Johnson County Community
College education entry wrapped to a 2nd line at real printed page width,
unlike KU/KCKCC after their degree names got shortened. Turns out it was
already fixed at the time it was flagged -- `scripts/fixed_content.py`
(now `profiles/morgan/fixed_content.py`) had the degree label shortened
from `"Relevant Coursework, Graphic Design"` to `"Coursework, Graphic
Design"` in commit `d66ae3ec` (2026-07-05), one commit after the field
was first added. Confirmed 2026-07-20 the shortened label is still live
today, matching Morgan's recollection of the fix -- removed from
`IDEAS.md`.

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

**Security flag found during this research (2026-07-04) -- closed, removed
from `IDEAS.md`'s Easy tier 2026-07-20.** `scrapers/recommended_scraper.py`
(present in the working copy at the time) had a **LinkedIn `li_at` session
cookie hardcoded in plaintext**. Checked the fresh ZIP re-download at the
time: this file **wasn't part of the actual open-source project at all**
-- the real repo's `scrapers/` only ever had `__init__.py`,
`jobright_scraper.py`, and `linkedin_scraper.py` (which correctly sources
its cookie from `config`, not hardcoded). So this was a local, ad-hoc
script added to the working copy and never upstream. **Closed 2026-07-20:**
the file itself is confirmed deleted from job_automater (`git log` there
shows `a8c55e3 Remove stray scrapers/recommended_scraper.py`), and Morgan
confirmed the underlying exposure is moot regardless -- the `li_at` cookie
rotates so frequently on its own that any value captured back on
2026-07-04 has long since expired. The better fix that superseded the
whole manual-copy-paste-a-static-cookie pattern is already built and live:
`scan_linkedin.py`'s `get_li_at_cookie()` (see row 1.4 above) reads the
*current* cookie straight out of an already-logged-in Chrome via
`browser_cookie3` on every scan call -- nothing is ever written to disk,
so there's no static value left to leak in the first place.

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

## Multi-computer sync (Syncthing), config + docs -- done 2026-07-22

Settled the "Very Hard / Long-term" open brainstorm from 2026-07-17 (three
unevaluated options: Syncthing, cloud-folder symlinks, or git for the
text-based state). Syncthing won on the first real test against this
repo's actual shape: it's direct device-to-device, doesn't care whether a
directory holds text or binary (`.npy` embeddings), and needs zero new
remote infrastructure -- closest fit for a flat-file-per-profile design
that already treats `profile_paths.py` as the single source of truth for
every path.

- **New: `profile_paths.sync_roots(profile)`** -- names the four
  directories a profile's data lives in for sync purposes:
  `profiles/<name>/`, `jds/<name>/`, `output/<name>/`, `data/<name>/`.
  Deliberately excludes nothing, not even `.env` or `signature.*` --
  the reason those are gitignored (keeping secrets out of a shared git
  history) doesn't apply to a direct, TLS-encrypted device-to-device
  sync that never touches GitHub. This is also what resolves Morgan's
  "pull `.env` from whatever computer I'm on" wish -- syncing it was
  never actually blocked, it just needed separating from the
  git-secrecy question that made it feel risky.
- **New: `profile_paths.write_sync_ignore_files(profile)`** -- ensures
  all four directories exist and seeds each with a `.stignore`
  (Syncthing's per-folder ignore file) excluding only machine-local
  cruft (`__pycache__`, `.DS_Store`) -- idempotent, never clobbers a
  hand-edited one. Wired into `bootstrap_bullet_bank.create_new_profile()`
  so every future profile is sync-ready with zero extra steps; run once
  by hand for the existing `morgan` profile.
- **New `data_dir(profile)` helper** -- `applications_md_path()` now
  builds on it instead of hand-rolling the same join, so `data/<name>/`
  has the same one-function-per-directory shape as the other three
  roots `sync_roots()` names.
- `.gitignore`: added a `.stignore` entry (matches at every level) so
  the auto-regenerated file doesn't get accidentally tracked in
  `profiles/`/`jds/`/`data/` (it's already excluded in `output/` by the
  existing blanket rule there) -- consistent behavior across all four
  roots, and no upkeep burden since it's fully reproducible from code.
- **Deliberately not done, and correctly so per this session's own
  scoping decision:** installing Syncthing itself and pairing two real
  devices is a manual, physical-device step (the device-ID exchange has
  to happen with, or be trusted between, both machines) that can't be
  scripted from one checkout -- config and documentation only. README's
  new "Multi-computer sync" section has the actual pairing/folder-share
  walkthrough for whenever a second machine is in the picture.
- Output syncing (previously an open question -- "is `output/`/PDF
  history worth syncing?") settled: yes, include it. Small files,
  fully regenerable from `jds/` if a sync is ever missed, and it means
  a freshly-picked-up machine already has the latest tailored resume
  without a re-run.

6 new tests (`profile_paths.sync_roots`/`write_sync_ignore_files`,
`create_new_profile`'s `.stignore` seeding). Full suite: 876 tests, all
green.

## Career dashboard: vendored, themed, fixed, and wired in -- done 2026-07-22

Closed out the "Very Hard / Long-term" merge item's dashboard/TUI loose
end entirely in one day, going from "explicitly deferred" to "shipped."
Three real, separable pieces:

**1. Tried it against real data (same day, earlier), found and fixed two
real bugs.** career-ops's Go dashboard (Bubble Tea TUI) had never been
run against resume-builder's own tracker format:
- A tracker-column-count mismatch -- the Go parser was still written
  against career-ops's original 9-column tracker
  (`# Date Company Role Score Status PDF ReportLink Notes`), silently
  misreading resume-builder's 10-column one
  (`... PDF Link Report Notes`): the Link column (a real job-posting URL)
  never matched the report-link regex (harmlessly empty), but the
  Report column (a recommendation label) was being read as Notes,
  silently dropping the real Notes text underneath it -- meaning
  location/pay/last-contact, all derived from Notes via regex, were
  coming back empty for every resume-builder-sourced row. Fixed by
  detecting column count and mapping fields accordingly; the
  recommendation label now folds into the displayed notes
  (`[Selective pursue] Austin, TX (Full), $95-130K...`) instead of
  being lost.
- A real crash (`strings.Repeat` with an unclamped negative count) in
  the detail-preview pane on narrow terminal widths, found via a
  pty-driven smoke test. One-line fix matching a `max(0, ...)` guard
  already used elsewhere in the same file.
- New `resume-builder` theme (`internal/theme/resumebuilder.go`) ports
  `scripts/theme.py`'s exact hex palette (verified byte-exact in real
  rendered ANSI output); new header icons on both screens honor the same
  `RESUME_BUILDER_ICONS` convention as the interactive menu. Made the
  default via a new `-theme` flag (catppuccin-mocha/-latte still
  selectable).

**2. Closed a real documentation-drift bug, independent of the dashboard
itself.** While reviewing what was "still undecided" about the merge,
found that `IDEAS.md`'s own copy of three decisions (persistence layer,
ATS-provider scope, launchd job layout) had gone stale -- all three were
actually already decided in the punchlist on 2026-07-16, `IDEAS.md` just
never got updated to match. Corrected `IDEAS.md` to reflect the
punchlist's actual decisions rather than re-deciding anything (one real
near-miss: almost silently overwrote the already-decided "one dispatcher
job" scheduler layout with a fresh "one job per saved search" answer
before catching the conflict and confirming the original decision still
holds, for the reason it was made -- a dispatcher is what makes "one
notification, one digest per run" simple).

**3. Vendored the dashboard into resume-builder itself, same day.** The
one genuinely new decision from the merge review -- promote dashboard
integration from "later nice-to-have" to "near-term scope" -- got built
immediately rather than just recorded:
- `dashboard/` (18 `.go` files, module path + every internal import
  rewritten from `github.com/santifer/career-ops/dashboard` to
  `github.com/moreganooooo/resume-builder/dashboard`, footer branding
  updated) now lives inside this repo, builds/vets/tests clean as its
  own Go module. **This copy is authoritative going forward** --
  `career-ops/dashboard/` is not deleted, but future dashboard changes
  land here, not there.
- New `scripts/dashboard.py`: a thin wrapper, `go run .` (never
  `go build`, so no compiled binary should ever land in the repo)
  against the active profile's `data/<profile>/` via
  `profile_paths.data_dir()` -- inherits stdio rather than capturing
  output, since the whole point is a live terminal UI the user drives
  directly, unlike every other subprocess call in this codebase. A
  friendly pre-flight message ("no applications logged yet") replaces
  the raw Go error when there's nothing to show yet, and a clear
  install hint replaces a stack trace when Go itself isn't installed.
- New `resume dashboard` CLI command, `scripts/resume-cli.sh` shortcut,
  and "Career Dashboard" interactive-menu entry (next to "Browse &
  Manage Jobs," since it's the same tracker data, just visualized
  differently). New `resume doctor` check for the Go toolchain --
  optional, like the JobRight cookie and signature-image checks, never
  a hard failure.
- Verified genuinely end-to-end, not just unit-tested: a real
  (unmocked) pty-driven launch through the actual
  `dashboard.run()` -> `subprocess.run(["go", "run", ...])` -> rendered
  TUI chain, confirming no panic and correct branding, alongside the
  real CLI command's friendly no-data-yet message against the actual
  (currently empty) `morgan` profile.

11 new Python tests (6 `scripts/dashboard.py`, 3 menu wiring, 2
`resume doctor`) on top of the vendored Go module's own pre-existing test
suite (unchanged, still green as its own `go test ./...`). Full Python
suite: 912 tests, all green.

## Console polish pass: prettier reporting + whitespace improvements -- done 2026-07-22

**Overall scope:** Two related quality-of-life passes completed same day. First, finished the three-script "prettier, more informative live progress" item from IDEAS.md (liveness.py was the only piece still open; scan.py and batch_evaluate.py were done in prior weeks). Second, a comprehensive whitespace-addition sweep across 10 high-impact user-facing output areas, transforming dense wall-of-text reports into readable, scannable sections with visual hierarchy.

### Prettier reporting: liveness.py streaming progress (2026-07-22)

**Context:** The item was scoped to three scripts: scan.py (done 2026-07-17), batch_evaluate.py (done 2026-07-21), and liveness.py (remaining blocker). liveness.py was architecturally different: it shelled out to `check-liveness.mjs` once for the entire batch via `subprocess.run(..., capture_output=True)`, so all results printed at once after the Node subprocess finished -- no per-JD progress signal *during* the check. The item's notes flagged this as requiring "a real architecture change" (streaming from Node side).

**Solution:** Discovered the streaming was already built into `check-liveness.mjs` (logging to stderr while JSON results go to stdout), but Python's `capture_output=True` was swallowing it. Fixed with minimal change: use separate `stdout=PIPE, stderr=PIPE` instead of `capture_output=True` to let stderr print in real-time. No major refactor needed.

**Changes:**
1. `scripts/liveness.py`:
   - Changed subprocess call from `capture_output=True` to separate stdout/stderr handling
   - Progress from Node side now displays incrementally as each URL check completes
   - Reorganized results display: group by status (active/likely_active/expired/uncertain) instead of dumping all results
   - Each group shows file paths + reason (for non-active statuses)
   - New summary table with icons and aligned counts instead of one-line paragraph
   - Added visual separators (─) matching audit-loop/bootstrap-polish standard

2. `scripts/check-liveness.mjs`:
   - Enhanced progress output: added `[i/total]` counter per URL (was just result + path before)
   - Shows status icon + result + reason in real-time
   - Progress logs to stderr, keeping stdout clean for JSON parsing

**Result:** Users now see real-time per-URL feedback as liveness checks run, matching the scan/evaluate pattern. Instead of a pause followed by all results at once, they get immediate feedback on each posting's status.

### Comprehensive whitespace sweep: 10 high-impact output areas (2026-07-22)

**Scope:** A systematic audit identified the top 10 user-facing output areas where dense text output made it hard to scan results, group related data, or understand progress. Each location was selected for either high impact (affects 50+ output lines many users see) or medium impact (affects 10-20 output lines, new/returning users). Additions were purely strategic blank lines between logical sections using `print()` or `console.print()` with no parameters.

**Files touched:**
1. `scripts/orchestrator.py` (3 locations):
   - Resume build pipeline (4-step workflow): add spacing between step summaries
   - Resume critique results: group scores, flags, recommendations, distinctive moments with visual breaks
   - System prompt diagnostics: separate rules blocks from prompts from score prompts
   - Rules bundle loading: separate config sections
   - Bullet audit loop: blank line after each bullet's progress indicator
   - Segment cache warming: blank line after header before item list

2. `scripts/bootstrap_profile.py` (3 locations):
   - Bullet processing loop: blank line after each bullet's status line
   - Identity confirmation (dry-run): blank lines before/after profile fields
   - LinkedIn section header: blank lines around instructions

3. `scripts/menu.py` (1 location):
   - Evaluation detail display: blank lines between metadata, dimensions, legitimacy sections

**Principle:** Added blank lines at section boundaries to reduce visual density and improve scannability. No content added or removed, purely structural improvement. All additions follow existing patterns (separators in some places were already `\n`, now complemented with blank lines).

**Result:** User-facing output now has clear visual hierarchy instead of wall-of-text effect. Sections are visually grouped, making it easier to scan results, compare counts, understand progress, and spot important information.

**Not in scope (deferred, no changes):** A broader "make all scripts uniform in styling" audit didn't happen -- some scripts use icons, some don't; some use separators, some don't. That would be a larger consistency pass across the whole codebase. Today's focus was high-impact density reduction for the most user-visible output paths.

