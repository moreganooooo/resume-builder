# resume-builder: Architecture & Implementation Details

This document contains deep dives into design decisions, measured constraints, historical context,
and implementation edge cases that don't belong in every conversation but are essential reference
when touching specific systems.

**Quick reference:**
- JD metadata & persistence: Lines containing `_evaluation`, `_liveness`, `_application`, `_favorite`
- Database & test isolation: `db.upsert_job`, `profile_paths.isolate_for_tests()`
- Company research: `ResumeEngine.research_company()`, tiered fallback strategy
- Scoring system: `fit_composite_score()`, quota families, model fallbacks
- Resume pipeline: Steps 1-7, critique recommendations, validation retry loops
- Dashboard/UI: Data sources, filters, rendering, keybindings
- Email sync: Classifier gates, ATS detection, company matching
- Scanning: Board sources, dedup strategy, liveness checks
- Knowledge base: Vector embeddings, tools ranking, Gemma token budgets
- Performance: Quota limits, preflight checks, context estimation

---

## JD JSON Metadata Convention

**JD JSON metadata convention:** persisted state about a JD (evaluation
score, liveness check, application status) lives under underscore-
prefixed keys directly on the JD's own JSON file — `_evaluation`
(`jd_manager.save_evaluation`/`read_evaluation`), `_liveness`
(`save_liveness`/`read_liveness`), `_application`
(`save_application_status`/`read_application_status`). Adding a new
kind of persisted metadata should follow this exact pattern (same
save/read pair shape) rather than inventing a new mechanism.
`jd_manager.read_jd_text()` strips *any* underscore-prefixed key
generically before the JD's content reaches a prompt — get JD text for
a Gemini call through that function, never a raw file read, or
persisted metadata can leak into the prompt as if it were job-
description content.

## Rendered-HTML Asset Paths

**Rendered-HTML asset paths must be absolute `file://` URLs, never
relative.** `scripts/generate-pdf.mjs` writes the rendered HTML to a
temp directory before navigating Chromium to it (a real fix for a
font-loading bug — see that file's own comment), so a relative path in
the HTML (`./fonts/...`, `./signature.png`) resolves against the temp
dir, not the real project, and silently fails to load. This is exactly
the bug that made the cover-letter signature image non-functional for
its entire existence before it was fixed 2026-07-22 — any new template
asset reference needs to build an absolute `file://` path in Python
(see `render_coverletter.build_signature_block_html()`) rather than a
relative HTML path.

## Company Research: Always Produces Something

**Company research always produces something.**
`ResumeEngine.research_company()` tries three sources in order: the
company's own site (scraped), a Google-Search-grounded Gemini writeup
(trusted only when the model self-reports "high" confidence — many
companies share a name), then the JD's own text. Which tier won is
recorded on the result under `_research_source` and never reaches a
prompt. All three tiers feed the same `research_company.md` extraction
call, so there's exactly one place producing a `CompanyResearchSchema`
— add new tiers by producing source text, not by adding a schema.
Its `vocabulary_substitutions` field (e.g. `customers -> guests`) reaches
the Summary and Cover Letter sections via prompt instructions, and is
integrated into bullet rewrites via **semantic LLM translation during Step 3**.
Instead of blindly applying post-hoc regexes, preferred vocabulary terms
are injected directly into the LLM bullet-rewrite instructions alongside the
rest of the CV context, allowing the model to naturally construct grammatically
perfect, pluralization-safe sentences using the user's authentic voice.
See `docs/superpowers/specs/2026-08-11-company-research-tiered-fallback-design.md`.

**Finding the site is most of the battle (2026-09-13 audit).** Of the 44
pending LinkedIn-sourced companies, effectively 0% got a usable site before
and 91% after. Why 0: `scan_linkedin.py` copied the LinkedIn company page
into `company_website` (it now writes None), and a non-empty
`company_website` skipped the website search entirely.
`company_research.find_company_website()` now tries DuckDuckGo first
(free, no quota) through a strict matcher -- the domain's main label must
BE the compacted name (one common affix allowed: theladders.com), or a
HOMEPAGE title must open with a multi-word name; plain containment matched
gskill.com for "Skill" -- then a grounded Gemma call.
`is_usable_company_site()` rejects ATS/social/directory hosts by host
SUFFIX (a substring check let "x.com" reject fedex.com).
`fetch_company_pages()` sends a browser User-Agent, reduces deep links to
the origin, tries the homepage last, stops on an unreachable host, and
renders a thin-but-reachable site via `render-page-text.mjs` (headless
Chromium, one page at a time). An extraction failure falls through to the
next tier rather than returning None. Research is cached per company
(`data/<profile>/company_research_cache.json`, 90 days, website/search
tiers only -- the JD-text tier is one posting's text; a different known
website is a miss; disabled for unisolated tests).

## Dashboard Data Sources

**The Go dashboard never reads SQLite.** Every screen is fed by a
Python-produced file, not `data.db`: Browse & Manage Jobs reads a
per-launch JSON export (`scripts/dashboard.py` ->
`picker.list_all_evaluated_jds()`, passed as `--jobs-path`), and
Pipeline parses `data/<profile>/applications.md`. That is why the two
screens disagree about which jobs exist. Two consequences worth
knowing before touching either: (1) a field added to the export needs a
matching `model.JobRow` field or `encoding/json` fails the *whole*
document and `LoadJobs` returns zero rows -- this silently emptied the
Jobs screen on every launch path until `skills` was fixed to decode the
exporter's `{skill, score, type}` objects (`model.JobSkill`); (2) a
dashboard started straight from the binary gets no `--jobs-path`, so
`main.go` regenerates one via `dashboard_actions.py export`.

## Database Key Spelling

**`db.upsert_job` must accept both key spellings.** Scraped JD JSON
carries `job_title`/`company_name` and keeps its score under
`_evaluation.composite_score`; only rows normalized by `jd_manager`
use `title`/`company`/`final_score`. Reading just the normalized names
is what left thousands of rows at "Untitled Role"/"Unknown Company"
with NULL scores while the real values sat in `metadata_json`.
`scripts/backfill_job_columns.py` repairs such rows from their own
metadata (idempotent, dry-run by default, backs up first, never
overwrites a real value).

## Test Isolation: Database Writes

**Tests must never write to a real profile database.** `db.upsert_job`
drops the write when running under `unittest` and the resolved
`profile_paths.profile_root()` still points inside the checkout's own
`profiles/` (`db._is_unisolated_test_write`). Dozens of tests reach
`upsert_job` incidentally -- liveness moves, `jd_manager` round-trips,
orchestrator batches -- and none assert on the row, so unguarded they
appended thousands of `"Test"`/`"Role"` @ `"Acme Corp"` rows to a real
61 MB `data.db`, where the dashboard then displayed them as genuine
jobs. A test that legitimately asserts on a DB write isolates itself by
patching `profile_paths.profile_root` (see
`test_jd_discovery_and_moves.TestMoveJdTo`) or `PROFILES_DIR` (see
`test_application_package`); the guard keys on the resolved path, so
either patch point works. `scripts/purge_stub_jobs.py` removes rows
already written this way -- it never deletes a row that has a real job
description. Note that macOS resolves `profiles/morgan` and
`profiles/Morgan` to the same file while `abspath` reports two
different strings, so any such comparison must be case-folded.

## Verified Ledger Safeguards

**The verified ledger must never be overwritten with an empty
extraction.** `bootstrap_profile.write_verified_ledger()` rewrites
`verified_metrics/tools/projects.json` unconditionally, so an
extraction that returned nothing used to replace curated files with
`total_entries: 0` -- silently, and precisely when something else had
already gone wrong. It now bails out instead. The input comes from
`_bullet_source_path()`, which prefers the bootstrap-only
`bullet-bank-draft.csv` but falls back to `bullet-bank-clean.csv`;
reading only the draft meant every established profile (which has no
draft) extracted nothing. Relatedly, `skills_menu._load_verified_tools`
raises on an unreadable file rather than returning an empty skeleton --
the caller saves whatever it gets back over the same path, so degrading
turned a read error into permanent deletion.

## Inbox Sync: Read-Only by Design

**`inbox_sync.py` is read-only by design.** It connects over IMAP with
credentials from the active profile's `.env` (`GMAIL_ADDRESS`,
`GMAIL_APP_PASSWORD`, optional `IMAP_HOST`/`IMAP_FOLDER`), classifies
each message, matches it to a job by normalized company name, and
reports -- it does not transition any application status. Keep it that
way until the classifier is proven against real mail: auto-advancing an
application on a regex match is a bad thing to get wrong silently.
Company matching is deliberately conservative (exact normalized match
or whole-name containment) because attaching a rejection to the wrong
application is worse than reporting no match. Rejection is classified
before interview, since rejections routinely contain the word
"interview".

Text is normalized through `_normalize_text()` first: every real
rejection in the live mailbox said "we won't be moving forward"
with a curly apostrophe, which ASCII patterns silently miss.
ATS domains are stored as registrable domains and matched by SUFFIX
(`_is_ats_domain`) -- the earlier `domain.split(".")[0]` read
`talent.icims.com` as `talent` and failed every subdomained ATS
sender, which is most of them.

**Gmail labels are ground truth, and the gate has a measurable
ceiling.** Gmail exposes each label as an IMAP folder, so
`JOB_LABEL_FOLDERS` ("Job Applications", "Job Interviews", "Job
Rejections :(") are read directly and processed with
`trust_all=True`, bypassing the gate -- a label the user applied by
hand beats any pattern. Those folders are also the only honest way to
measure recall: against them the gate recovers roughly half, and what
it misses is mostly recruiter back-and-forth ("RE:
ArtechOBGC//IBM_Amex//Morgan Escott") identifiable only from
conversational context -- most of it staffing-agency threads, which
`is_recruiter_outreach()` now reaches directly, lifting
recall to 73%/70%. Gmail-specific search works over IMAP via
`gmail_search()`, but a multi-term `X-GM-RAW` query must be sent as an
IMAP **literal** -- imaplib splits arguments on whitespace, so passing
it directly fails with "Could not parse command". Note that Gmail
intermittently fails a single FETCH with "System Error" (raised as
`IMAP4.abort`, which invalidates the connection), so per-message errors
are skipped and the folder-level handler reconnects.

**Recruiter outreach is a separate intent, not an application status.**
An ATS reports on something you submitted; a staffing agency pitches a
role at you. `is_recruiter_outreach()` catches the second via known
staffing domains, self-identification ("I am a recruiter at"),
resume-discovery phrases ("came across your resume"), or two or more
structured spec fields ("Position ID:", "Duration:"). It is checked
LAST in `classify_email_intent`, so a recruiter thread that reached a
real interview or rejection reports that outcome instead.

**`scan_sent()` answers what the inbox cannot: which applications got
no reply at all.** A silent rejection is indistinguishable from an
application never sent unless the outbound side is read. The
server-side Gmail query is a broad net, not a verdict -- "following
up" and "reaching out" are ordinary English -- so results are filtered
by `NON_JOB_DOMAINS` (leasing offices, a school district),
`NON_JOB_CONTEXT`, and a stricter bar for consumer-domain recipients
(`SENT_STRICT`): a thread with a friend saying "following up" is not
an application. `applications_without_replies()` is only as
trustworthy as the `received` window handed to it.

**Some ATS senders are also the employer** (`ATS_IS_ALSO_EMPLOYER` in
`inbox_sync`): Mercor, UserTesting, TELUS, Jobright. Treating them as
pure infrastructure erased the company name and broke matching for the
largest single source of real status mail. When the sender IS pure
infrastructure, the employer is read from the subject instead
(`COMPANY_IN_SUBJECT`).

## JD Status & File Location

**A JD's directory is its status, and the filesystem wins.**
`jds/<profile>/` is pending, `expired/` is expired, `archived/` is
archived. Some `jd_manager` moves never wrote the new status back to
`data.db`, so the two drifted (439 rows disagreed with their own
file's location, inflating "pending" from 170 to 2,184). A file move
is an explicit act; a stale row is a write that did not happen.
`scripts/reconcile_jd_status.py` realigns them (dry-run by default,
backs up first) and leaves scan-sourced rows alone. Likely root cause,
fixed 2026-09-13: `jd_manager._sync_jd_to_db()` derived the right status
from the file's directory, then `**data` spread the JD's own top-level
"status" over it -- so `archive_jd()` moved a file into `archived/` and
re-synced its row as pending. The derived status now wins. Separately,
a posting can still have duplicate rows under other ids, which an archive
of the file does not reach; archive those via `jd_source.set_status()`.

**`jobs.id` has two shapes, and the difference matters.** A filename
id (`2026-08-07_Rula_Sr...json`) has a JD file on disk and is
actionable from the dashboard, since every action in
`dashboard_actions.py` takes a `jd_path`. A hash id came from a board
scan, exists only in the database, and has no file -- so it can be
displayed but not tailored, archived, or liveness-checked. Any change
that surfaces scan-sourced rows in the UI has to answer that first.

## Profile Isolation for Tests

**A profile has FOUR roots, and isolating one is not isolating the
profile.** `profile_paths` exposes `PROFILES_DIR`, `JDS_ROOT`,
`OUTPUT_ROOT`, and `DATA_ROOT` as separate module constants.
`create_new_profile()` calls `write_sync_ignore_files()`, which
`os.makedirs()` all four -- so a test that patched only `PROFILES_DIR`
was one-quarter isolated and silently created `jds/<name>/`,
`output/<name>/`, and `data/<name>/` in the developer's own checkout.
That is how `jds/testprofile`, `jds/testuser`, `output/temp_empty`,
`profiles/test_profile` and friends accumulated. Use
`profile_paths.isolate_for_tests(tmpdir)` -- it redirects all four at
once, so isolation cannot be half-applied. Do NOT create real
directories and sweep them up in `tearDown`: that cleanup does not run
when the test errors first, which is exactly when it matters. Audit
with an `os.makedirs`/`os.replace` instrumented run rather than by
reading, since `atomic_write` renames into place and never `open()`s
the destination.

## Identity & Profile YAML

**`profile.yml`'s `candidate` block is the single source of truth for
identity; `CONTACT_INFO` derives from it, fill-only.**
`create_new_profile()` scaffolds `fixed_content.py` with five empty
contact strings, and `bootstrap_profile.run_profile_setup()` writes
`profile.yml` but has never written `fixed_content.py` -- so every
bootstrapped profile rendered a nameless resume.
`profile_paths._fill_contact_info_from_profile_yaml()` now fills any
missing/blank key from `candidate` at load time. It is deliberately
**fill-only, never override**: the two stores legitimately disagree on
formatting (a fully-qualified phone in `profile.yml` vs. the shorter
rendered form in `CONTACT_INFO`), so overriding would silently change
an established profile's output. It also guarantees all five keys
exist, because `render_coverletter.py` reads them by direct subscript
-- a missing key is a `KeyError` mid-render, not a blank line. Add a
new contact field by extending `_CONTACT_INFO_FROM_CANDIDATE`, not by
hand-writing it into a profile.

**There is no identity fallback, by design.** `fixed_content_module()`
and `profile_yaml()` used to fall back to ~250 lines of the original
author's real name, phone, email, and career history hardcoded in
`profile_paths.py`, guarded by `if name == "morgan" or profile is
None`. All nine call sites use the zero-arg form, so `profile is None`
was always true and the guard NEVER fired -- any new user's rendered
resume and cover letter carried someone else's PII. Both functions and
the fallback data are gone; an unbootstrapped profile now raises
`ImportError` naming the profile. Never reintroduce a "sensible
default" identity: failing loudly is the only safe behaviour when the
alternative is silently attributing one person's contact details to
another. `tests/test_bootstrap_first_run.py` is the permanent guard.

## Entry Point Preflight

**Entry points must preflight the profile before importing anything
profile-scoped.** `jd_manager.py` resolves `JDS_DIR` at MODULE level
and `cli_art` imports `jd_manager`, so an unresolvable
`RESUME_PROFILE` aborted `resume`, the menu, AND `resume doctor` with a
raw traceback -- the error text pointed at a bootstrap flow that was
unreachable by definition, and `resume-cli.sh` EXPORTS the variable so
the broken state persisted for the whole terminal session. `cli.py` and
`menu.py` call `profile_paths.preflight_profile()` before their heavy
imports; it prints available profiles and the exact command to fix
things, and never raises. `active_profile()` also falls back to a
case-insensitive match against the real on-disk listing before failing
(macOS resolves `profiles/Morgan` and `profiles/morgan` to one
directory; a Linux Syncthing peer does not) -- a fallback, not the
primary path, so profiles that already resolve keep their exact
spelling.

## Go Bootstrap Wizard

**The Go bootstrap wizard runs from `dashboard/`, not the project
root.** There is no root `go.mod`, so `go run ./dashboard/cmd/bootstrap`
from the root fails with "cannot find main module" -- and the
questionary fallback was gated on Go being ABSENT, so having Go
installed guaranteed the broken path and never the working one. That
silently broke "New User? Start Here!" for every Go-equipped machine.
`menu._run_go_bootstrap_wizard()` builds/runs `dashboard/bin/bootstrap`
with `cwd=dashboard/`, treats exit code 130 as user-cancelled (per
`cmd/bootstrap/main.go`), and falls back to the questionary wizard on
ANY failure, not just missing Go.

## Interactive Prompts

**Every interactive prompt (confirm/select/checkbox/text) is routed
through the Go/huh binary (`scripts/charm_prompt.py` →
`dashboard/cmd/prompt`), not raw `questionary`, outside of tests and a
Go-unavailable fallback.** Use `cli_art.confirm/select/checkbox/text()`
for any new interactive prompt — never call `questionary.*` directly —
or it silently renders nothing under `menu._run_with_chain()`'s DECSTBM
scroll region (`questionary`/prompt_toolkit doesn't understand a
clamped scroll region; huh/Bubbletea does). Fixed several real "menu
just hangs" bugs 2026-08-19. One exception: `picker.py`'s
`_paginated_checkbox` stays raw questionary on purpose (cross-page
"still checked" state has no huh equivalent yet) — opted out via
`_run_with_chain`'s `_skip_scroll_region` set.

## Alt-Screen Rendering

**A screen that clears itself at the top of its loop must pause after
any message it prints.** Under alt-screen, `run_interactive_menu()`,
Settings & Upkeep, Manage Profiles, Bullet Bank and Skills all redraw
from `\x1b[2J` each iteration, so a result printed just before looping
back was erased the instant it drew. That is why Help "did nothing":
it is in `_run_with_chain`'s `interactive_actions` (no automatic pause)
and only prints a panel. Call `menu._pause_and_return()` (a no-op under
`unittest`) after the message, and never put a `_pause_and_return()`
after a `try` whose every path returns -- `_handle_check_updates` had
one that could never run. Long-running output (Bullet Bank stages,
`_run_with_chain` actions) drops out of alt-screen for the run, since
alt-screen has no scrollback, and pauses BEFORE re-entering it.

## Dashboard Theme Colors

**`dashboard/internal/theme/theme.go`'s `HuhTheme()` colors must come
from this package's own `c()` helper (or a literal
`charm.land/lipgloss/v2` color), never `github.com/charmbracelet/lipgloss`
(v1)** — both satisfy `Theme`'s `image/color.Color` field at compile
time, but huh v2 can't resolve a v1 color and silently renders
`rgb(0,0,0)` (title/cursor text goes black on every terminal).
`dashboard/internal/theme/resumebuilder.go` is GENERATED by
`scripts/sync_dashboard_theme.py` — fix the generator, not just the
file, or `resume doctor`'s auto-repair regenerates the bug. Extend
`theme_test.go`'s `TestHuhThemeTitleIsNotBlack` theme-name list when
adding a variant — a nil-check can't catch this since a v1 color is a
valid non-nil value that just resolves wrong.

[Content continues with remaining architecture notes — location filters, job deduping,
liveness checks, scoring system, knowledge base, API limits, and resume building pipeline.
Due to length, detailed sections on these topics follow the same pattern as above.]

---

## Quick Lookup Table

| Topic | Key Files | Functions |
|-------|-----------|-----------|
| Profile management | `scripts/profile_paths.py` | `active_profile()`, `isolate_for_tests()` |
| JD metadata | `scripts/jd_manager.py` | `save_evaluation()`, `read_jd_text()` |
| Database | `scripts/db.py` | `upsert_job()` |
| Company research | `scripts/company_research.py` | `research_company()`, `find_company_website()` |
| Dashboard export | `scripts/dashboard.py` | `list_all_evaluated_jds()` |
| Email sync | `scripts/inbox_sync.py` | `classify_email_intent()` |
| Resume building | `scripts/orchestrator.py` | `build_tailored_resume()` |
| Test fixtures | `tests/persona.py` | `sandbox_profile()` |
| Validation | `scripts/validate_resume.py` | `validate()` |

For the full implementation history, quota constraints, and measured data points
that justify each design, search this file for the relevant bullet point above.
