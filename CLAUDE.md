# resume-builder

Tailors a resume per job description using Gemini/Gemma, then renders it to PDF.

## Tool priorities
- Prefer `codebase-memory-mcp` graph tools over grep/glob for mapping this
  repo's structure (Python core + vendored `dashboard/` Go module) —
  fall back to grep if the graph doesn't have Go coverage.
  (Lumen was uninstalled 2026-08-19 after a reindex hang — its
  `semantic_search` tool no longer exists on this machine.)

## Setup
- Requires Python 3.10+ (code uses `str | None` syntax). A venv already
  exists at `.venv/` — `source .venv/bin/activate` (or `resume activate`
  from any shell, see Shortcuts below). If it's ever missing/broken, rebuild
  with `python3 -m venv .venv && source .venv/bin/activate
  && pip install -r requirements.txt`.
- PDF generation (`scripts/generate-pdf.mjs`) needs Node + Playwright's
  Chromium browser installed: `npm install && npx playwright install
  chromium`. `node_modules/` is not guaranteed to already exist — don't
  assume it's there just because `package.json` is committed; check
  before debugging a PDF-generation failure.
- **Playwright is pinned to an exact `1.61.1`, not `^1.61.1` — do not
  loosen it.** This machine runs macOS 12, and Playwright ≥1.62 dropped
  macOS 12 support: `npx playwright install chromium` fails outright with
  "Playwright does not support chromium on mac12", so every PDF render
  dies at `chromium.launch()` with a missing-executable error. 1.61.1 is
  the last release that both supports macOS 12 and pins Chromium 1228.
  A caret would silently resolve to 1.62.x and break all rendering.
- Bare `python3` on this machine may resolve to an unrelated stray venv —
  always activate `.venv/` first (see `.claude.local.md`).
- CSV-append locking (`jd_manager.py`'s `_append_row`/`append_application_row`,
  used for `jd_tracker_log.csv` and `applications.md`) uses `fcntl.flock`,
  which is POSIX-only. It degrades gracefully (not a crash) on native
  Windows — the `import fcntl` fails, gets caught, and the append proceeds
  unlocked — but that means concurrent writers on native Windows (not
  WSL2, which is POSIX) aren't actually protected against interleaved
  lines. Low real-world risk for a single-user CLI, but worth knowing if
  native-Windows support is ever load-bearing.
- The interactive menu and dashboard default to Catppuccin themes and Nerd Font glyphs — if your
  terminal doesn't have one active, set `RESUME_BUILDER_ICONS=unicode` in
  your shell profile (or before invoking `resume`) to fall back to plain
  Unicode symbols. For accessibility or reduced motion preferences, set
  `RESUME_BUILDER_MOTION=reduced` to disable spring micro-animations. Theme
  mode can be explicitly overridden with `RESUME_BUILDER_THEME=dark` or `light`.
- API keys and source-specific secrets live in the active profile's own
  `.env` file (`profiles/<name>/.env`), not a shared project-root `.env`.
- Multiple profiles can share one checkout (`profiles/<name>/`) —
  `RESUME_PROFILE` env var selects which one is active (defaults to
  `morgan` if unset). `scripts/profile_paths.py` is the single source of
  truth for every profile-scoped path; route new code through it rather
  than hand-rolling a `profiles/<name>/...` join. The Go dashboard also
  supports a direct CLI flag (`dashboard -profile <name>`) and displays the
  active user profile and title in the main menu banner.
  `profile_paths.active_profile()`'s `"morgan"` fallback is a plain
  string, not guaranteed to match a renamed profile folder's exact
  casing (macOS resolves `profiles/morgan/` and `profiles/Morgan/` to
  the same directory, but Python string comparisons like `in names`
  don't) — `menu._confirm_active_profile()` resolves it against the real
  on-disk listing case-insensitively before using it, so a renamed
  profile is picked up automatically. Follow that pattern (resolve
  against `os.listdir(profile_paths.PROFILES_DIR)`, don't compare
  `active_profile()`'s return value directly) anywhere else a profile
  name needs matching against real directories.
- `resume doctor` is the fast way to check whether the whole environment
  (Python packages, Node/Playwright, API keys, fonts, KB files) is
  actually set up correctly, plus a real test-suite run — reach for it
  before manually debugging a "why isn't this working" environment issue.
- `dashboard/` is a vendored Go module (Bubble Tea TUI) — see `dashboard/CLAUDE.md` for its architecture, vendoring history, and visual-inspection/mobile-build tooling.
- **Multi-computer sync (Syncthing):** a profile's data can sync across
  machines via Syncthing, four independent folders per profile —
  `scripts/profile_paths.sync_roots(profile)` is the single source of
  truth for exactly which four (`profiles/<name>/`, `jds/<name>/`,
  `output/<name>/`, `data/<name>/`) — never `.git/` or the repo root
  itself (concurrent file-sync of a live git working tree/object store
  is a known corruption risk; code stays on normal git push/pull, only
  data syncs). `write_sync_ignore_files(profile)` seeds a `.stignore`
  (machine-local cruft only — `__pycache__`, `.DS_Store`; deliberately
  *not* excluding `.env` or `signature.*`) in each and is called
  automatically for every new profile from
  `bootstrap_bullet_bank.create_new_profile()`. Any new profile-scoped
  directory should be added to `sync_roots()`, not hand-wired elsewhere,
  so it's covered automatically. `.env` and `signature.*` are gitignored
  (keeps them out of GitHub) but deliberately *not* excluded from sync —
  Syncthing is direct device-to-device and TLS-encrypted, never touches
  GitHub, so the reason those are gitignored doesn't apply to it; syncing
  `.env` is how a second machine gets a working `GEMINI_API_KEY` without
  it being typed in by hand. See README's "Multi-computer sync" section
  for the actual Syncthing pairing/folder-sharing walkthrough (a manual,
  per-device step that can't be scripted from here).
- **No OS keyring/vault integration for secrets — deliberate, not an
  oversight.** `GEMINI_API_KEY`, `JOBRIGHT_COOKIE_STRING`, and the
  LinkedIn `.linkedin_cookie` all sit as plaintext files under
  `profiles/<name>/`. This was considered and intentionally not built:
  the `.env`-file approach is what makes the Syncthing-based
  multi-computer story above work without per-device manual entry, and a
  single-user personal tool on trusted machines doesn't carry the same
  threat model as a multi-tenant service. Both files are covered by the
  blanket `profiles/*/` `.gitignore` rule, so there's no git-leak risk —
  the tradeoff is plaintext-at-rest on disk, not plaintext-in-git.

## Shortcuts
- `resume run` / `resume run jds/<profile>/some_file.txt` — batch or
  single-file mode (see Running below), venv handled automatically.
- `resume test` — full test suite, venv handled automatically.
- `resume doctor` — environment/dependency/config health check + test
  suite, plain-English summary with a suggested fix per problem.
- `resume activate` — cd into the project and activate `.venv/` in the
  current shell (stays active, unlike `run`/`test` which use a subshell).
- Defined in `scripts/resume-cli.sh`, sourced from your shell profile
  (`~/.zshrc` or `~/.bashrc`).

## Running
- `python scripts/orchestrator.py` (no args) — batch mode: processes every
  JD not yet completed in the active profile's JDs directory
  (`jds/<profile>/`), splitting any multi-job JSON export into per-job
  files first.
- `python scripts/orchestrator.py jds/<profile>/some_file.txt` — single-file
  mode.
- Completed JDs move to the active profile's `completed/` folder inside
  `jds/<profile>/`; expired JDs move to `expired/`; history logs to
  `jds/<profile>/jd_tracker_log.csv` (gitignored — may contain names/URLs).
- Interrupted runs resume from `output/<profile>/checkpoints/<job_key>.json`
  instead of restarting — don't delete that folder mid-run.
- Any local test fixture warning here should point to the active profile's
  JDs directory, not a shared top-level `jds/` path.
- `resume sample` (`scripts/build_sample.py`) is a QA smoke test: runs the
  full tailor+render pipeline against the permanent `fixtures/sample_jd.txt`
  fixture, calling `ResumeEngine.build_tailored_resume()`/
  `build_tailored_coverletter()` directly rather than going through
  `orchestrator.run_pipeline()` — deliberately skips the move-to-completed/
  tracker-logging side effects a real JD gets, since this fixture is meant
  to be re-run indefinitely, not treated as one real application.
  `fixtures/sample_jd.txt` lives outside `jds/<profile>/` specifically so
  `get_pending_jds()` never picks it up in a batch `resume run`. Output
  overwrites the same `output/<profile>/pdf/...` files each run (checkpoint
  is cleared first, so it's always a full fresh build).

## Testing
- `python -m unittest discover -s tests -v`, run from the project root with
  `.venv/` activated. Stdlib `unittest`, not pytest (not installed) —
  discovery picks up every `tests/test_*.py` file, so this never goes stale
  as new test files are added.

## Architecture notes
- **JD JSON metadata convention:** persisted state about a JD (evaluation
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
- **Rendered-HTML asset paths must be absolute `file://` URLs, never
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
- **Company research always produces something.**
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
- **The Go dashboard never reads SQLite.** Every screen is fed by a
  Python-produced file, not `data.db`: Browse & Manage Jobs reads a
  per-launch JSON export (`scripts/dashboard.py` ->
  `picker.list_all_evaluated_jds()`, passed as `-jobs-path`), and
  Pipeline parses `data/<profile>/applications.md`. That is why the two
  screens disagree about which jobs exist. Two consequences worth
  knowing before touching either: (1) a field added to the export needs a
  matching `model.JobRow` field or `encoding/json` fails the *whole*
  document and `LoadJobs` returns zero rows -- this silently emptied the
  Jobs screen on every launch path until `skills` was fixed to decode the
  exporter's `{skill, score, type}` objects (`model.JobSkill`); (2) a
  dashboard started straight from the binary gets no `-jobs-path`, so
  `main.go` regenerates one via `dashboard_actions.py export`.
- **`db.upsert_job` must accept both key spellings.** Scraped JD JSON
  carries `job_title`/`company_name` and keeps its score under
  `_evaluation.composite_score`; only rows normalized by `jd_manager`
  use `title`/`company`/`final_score`. Reading just the normalized names
  is what left thousands of rows at "Untitled Role"/"Unknown Company"
  with NULL scores while the real values sat in `metadata_json`.
  `scripts/backfill_job_columns.py` repairs such rows from their own
  metadata (idempotent, dry-run by default, backs up first, never
  overwrites a real value).
- **Tests must never write to a real profile database.** `db.upsert_job`
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
- **The verified ledger must never be overwritten with an empty
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
- **`inbox_sync.py` is read-only by design.** It connects over IMAP with
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
- **Pipeline and Browse & Manage Jobs share one source.** `main.go`
  derives Pipeline's rows from the same JD evaluation export Jobs reads,
  via `data.JobRowsToApplications` (falling back to `applications.md`
  only when there is no export). That converter also drops terminal
  statuses -- archived, expired, discarded, skip -- which previously
  rendered as scoreless rows indistinguishable from live applications,
  and leaves `ScoreRaw` empty rather than `0.00` for an unevaluated job.
  `reloadPipelineDataCmd` must read the same source as startup, or a
  mid-session refresh silently swaps the screen back to the old data set.
- **Tests must not write to the real profile's knowledge base either.**
  Same class of bug as the database guard above, different file:
  `test_skills_menu`'s `_add_skill()` tests pass `{"tools": []}` and
  `_save_verified_tools()` writes the whole dict it is handed, so an
  unredirected save replaced the live `verified_tools.json` with a single
  "ChatGPT" entry on every full test run -- which is exactly how that
  ledger came to hold one tool. The class now patches
  `skills_menu._get_verified_tools_path` to a temp dir. Note that
  `atomic_write` renames a temp file into place, so instrumentation that
  watches `open()` on the destination will not see these writes; watch
  `os.replace`/`os.rename` instead.
- **Repopulate the ledger with `scripts/refresh_verified_ledger.py`, not
  `bootstrap_profile.write_verified_ledger()`.** The refresh script
  touches only the three bullet-derived files and merges (existing
  entries, including hand-added `category`/`confidence`/`use_notes`, are
  never modified or dropped); it backs up first and is dry-run by
  default. `--max-chunks N` caps cost, since each chunk is one API call
  (the full bullet bank is ~37). It is additive but **not idempotent** --
  dedup is exact-match on a normalized key and the model does not return
  the same set twice, so a second pass over identical bullets adds more
  near-duplicates ("Adobe Sign program" vs "Adobe Sign pilot program").
  Run it deliberately, not on a schedule.
- **A JD's directory is its status, and the filesystem wins.**
  `jds/<profile>/` is pending, `expired/` is expired, `archived/` is
  archived. Some `jd_manager` moves never wrote the new status back to
  `data.db`, so the two drifted (439 rows disagreed with their own
  file's location, inflating "pending" from 170 to 2,184). A file move
  is an explicit act; a stale row is a write that did not happen.
  `scripts/reconcile_jd_status.py` realigns them (dry-run by default,
  backs up first) and leaves scan-sourced rows alone.
- **`jobs.id` has two shapes, and the difference matters.** A filename
  id (`2026-08-07_Rula_Sr...json`) has a JD file on disk and is
  actionable from the dashboard, since every action in
  `dashboard_actions.py` takes a `jd_path`. A hash id came from a board
  scan, exists only in the database, and has no file -- so it can be
  displayed but not tailored, archived, or liveness-checked. Any change
  that surfaces scan-sourced rows in the UI has to answer that first.
- **`inbox_sync` gates before it classifies.** Intent regexes alone are
  useless on a real mailbox: marketing copy reuses every recruiting
  keyword, so a rent reminder scored "interview" and a Quora digest
  scored "rejection" while genuine application updates scored
  "unknown". `is_job_application_mail()` requires an ATS sender, a
  sender matching a company in the jobs table, or an unambiguous
  application phrase in the SUBJECT (not the body -- newsletters bury
  those in footers), and rejects job-board alert blasts outright.
  Text is normalized through `_normalize_text()` first: every real
  rejection in the live mailbox said "we won\u2019t be moving forward"
  with a curly apostrophe, which ASCII patterns silently miss.
  ATS domains are stored as registrable domains and matched by SUFFIX
  (`_is_ats_domain`) -- the earlier `domain.split(".")[0]` read
  `talent.icims.com` as `talent` and failed every subdomained ATS
  sender, which is most of them.
- **Gmail labels are ground truth, and the gate has a measurable
  ceiling.** Gmail exposes each label as an IMAP folder, so
  `JOB_LABEL_FOLDERS` ("Job Applications", "Job Interviews", "Job
  Rejections :(") are read directly and processed with
  `trust_all=True`, bypassing the gate -- a label the user applied by
  hand beats any pattern. Those folders are also the only honest way to
  measure recall: against them the gate recovers roughly half, and what
  it misses is mostly recruiter back-and-forth ("RE:
  ArtechOBGC//IBM_Amex//Morgan Escott") identifiable only from
  conversational context -- most of it staffing-agency threads, which
  `is_recruiter_outreach()` now reaches directly (see below), lifting
  recall to 73%/70%. Gmail-specific search works over IMAP via
  `gmail_search()`, but a multi-term `X-GM-RAW` query must be sent as an
  IMAP **literal** -- imaplib splits arguments on whitespace, so passing
  it directly fails with "Could not parse command". Note that Gmail
  intermittently fails a
  single FETCH with "System Error" (raised as `IMAP4.abort`, which
  invalidates the connection), so per-message errors are skipped and the
  folder-level handler reconnects.
- **Recruiter outreach is a separate intent, not an application status.**
  An ATS reports on something you submitted; a staffing agency pitches a
  role at you. `is_recruiter_outreach()` catches the second via known
  staffing domains, self-identification ("I am a recruiter at"),
  resume-discovery phrases ("came across your resume"), or two or more
  structured spec fields ("Position ID:", "Duration:"). It is checked
  LAST in `classify_email_intent`, so a recruiter thread that reached a
  real interview or rejection reports that outcome instead.
- **`scan_sent()` answers what the inbox cannot: which applications got
  no reply at all.** A silent rejection is indistinguishable from an
  application never sent unless the outbound side is read. The
  server-side Gmail query is a broad net, not a verdict -- "following
  up" and "reaching out" are ordinary English -- so results are filtered
  by `NON_JOB_DOMAINS` (leasing offices, a school district),
  `NON_JOB_CONTEXT`, and a stricter bar for consumer-domain recipients
  (`SENT_STRICT`): a thread with a friend saying "following up" is not
  an application. `applications_without_replies()` is only as
  trustworthy as the `received` window handed to it.
- **Ledger cleanup is `scripts/dedupe_verified_ledger.py`.** Tools merge
  only when the longer name adds nothing but vendor/generic tokens
  ("Illustrator" -> "Adobe Illustrator"); plain containment would
  wrongly fuse "Facebook" into "Facebook Ads". Projects merge on a
  shared two-token prefix within one employer, which is how the
  extractor's fragmentation ("Adobe Sign pilot", "Adobe Sign ABM pilot
  messaging strategy") actually presents. Metrics are left alone --
  similar labels with different values are usually real measurements.
  It iterates to a fixed point, since collapsing one variant can expose
  another.
- **A job does not need a file to be actionable (`jd_source.py`).**
  Every action in `dashboard_actions.py` takes a `jd_path`, but most
  pending jobs live only in `data.db` (the migration keyed them by
  content hash and never wrote a file). `jd_source.resolved_jd()` takes
  either a real path or a job id: a path resolves to itself, an id
  materializes a **temporary** JD file whose changes are synced back into
  the row on exit. Temp, deliberately -- writing ~1,200 JD files just so
  file-oriented code has something to open is the thing this avoids.
  Two exceptions: tailoring calls `materialize_permanently()` because
  `run_pipeline` moves the JD into `completed/` on success (and a job
  being tailored has earned the disk), and archiving a database-only job
  calls `set_status()` rather than `archive_jd()`, which would move the
  temp file into `jds/archived/` and create the exact clutter this
  avoids. `picker.list_all_evaluated_jds()` unions these rows in with
  `path` set to the job id, which is what `resolved_jd()` consumes.
- **Expired and archived jobs are purged, not kept
  (`scripts/purge_terminal_jobs.py`).** Terminal states are not
  actionable and the Pipeline hides them anyway; they were the bulk of
  the corpus (2,881 files / 30 MB / 2,173 rows). Run
  `reconcile_jd_status.py` FIRST -- the purge keys off status, so a row
  whose status has drifted from its file's directory would be judged on
  stale information. It never touches the knowledge base, the tracker
  CSV, or `applications.md`.
- **There is ONE definition of "how many roles do I have":
  `picker.count_active_roles()`.** The CLI banner used to count JD files
  via `get_pending_jds()` (157) while both dashboard screens counted the
  evaluated export (812) -- two true numbers measuring different things,
  which reads as a bug. The banner now uses the same function. Liveness
  covers the same set too (`_gather_db_candidates`), minus roles with no
  `source_url` to check. Note `cli_art` imports `picker` lazily inside
  the function: `picker` imports `cli_art`, so a module-level import is
  circular.
- **`JDTracker` resolves its CSV path per instance, never from the
  module-level `TRACKER_CSV`.** That constant is computed once at import,
  so it survived both a profile switch and any test redirecting
  `profile_paths.PROFILES_DIR` -- which is how the suite appended two
  "completed" rows to a real tracker log on every run and inflated
  "Resumes Customized All-Time" to 198, of which 194 were fixtures.
  `scripts/reset_resume_counter.py` archives the log and starts a fresh
  one (it renames, never deletes -- `job_key_known()` reads that history
  to avoid rebuilding an existing resume).
- **`liveness._gather_db_candidates()` fails closed under tests.** A
  sweep is real Playwright network I/O; when database candidates were
  added, the existing liveness tests mocked the filesystem JD list but
  knew nothing about a database source, so the suite launched Chromium
  and began checking 643 live URLs. The guard (`db._is_unisolated_test_write`)
  is the only place that catches that for every current and future test.
  Database candidates are also restricted to EVALUATED rows, so liveness
  covers the same 812 every screen shows rather than introducing a third
  number, and honor the same 24-hour recency skip.
- **`email_matcher.py` decides WHICH saved role an email refers to.**
  Company only selects the candidate set -- a staffing agency sends many
  rejections for many roles, so matching on company alone would mark a
  live "Copywriter" application rejected because "Graphic Designer" was
  declined. Role title, date proximity, and current status discriminate
  within that set, and a role that CONFLICTS subtracts score rather than
  merely failing to add. Where the role hides depends on intent:
  rejections and status updates put it in the SUBJECT, application
  confirmations put it in the BODY. Requisition ids (`[AQ-12521]`) are
  stripped before comparison, but a parenthetical is only treated as an
  id when it is ≥40% digits -- "(Commercial B2B)" has a digit and is part
  of the real role name. Near-ties are demoted below the auto threshold:
  two roles scoring alike means nothing distinguishes them.
  `resolve_status()` never moves an application backwards (a late
  acknowledgment cannot undo a recorded interview) and never reopens a
  terminal status. Company keys are compared with whitespace collapsed
  (`_company_key`), since a saved "Khan Academy" meets a sender-derived
  "khanacademy".
- **Some ATS senders are also the employer** (`ATS_IS_ALSO_EMPLOYER` in
  `inbox_sync`): Mercor, UserTesting, TELUS, Jobright. Treating them as
  pure infrastructure erased the company name and broke matching for the
  largest single source of real status mail. When the sender IS pure
  infrastructure, the employer is read from the subject instead
  (`COMPANY_IN_SUBJECT`).
- **Embedded ACID SQLite Store (`db.py`):** `profiles/<profile>/data.db` manages connection pooling, schema initialization, and database queries for job postings, application funnel status transitions, and bullet bank achievements with transaction safety and indexed query performance.
- **Dynamic Credentials Shield (`gemini_client.py`):** `gemini_client.py` calculates API authorization headers dynamically per call via `_get_auth_headers()`, ensuring profile switches immediately adopt the active profile's `GEMINI_API_KEY`.
- **Typst Vector PDF Engine (`render_typst.py`):** Provides sub-second vector PDF generation directly from structured `.typ` document templates without headless browser overhead.
- **Every interactive prompt (confirm/select/checkbox/text) is routed
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
- **`dashboard/internal/theme/theme.go`'s `HuhTheme()` colors must come
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
- **Bullet uniqueness is enforced at selection time, not repair time.**
  "No repeated metric" and "no repeated opening verb" are whole-CV
  constraints, but the validator retry loop can only ask the model for a
  local edit — so fixing one collision routinely creates another
  somewhere it can't see, and a build can burn all four attempts without
  converging. `mine_bullet_bank()` therefore avoids *picking* a
  colliding set in the first place, keying on
  `validate_resume.uniqueness_keys()` — deliberately the same function
  the checks report on, so the two can't drift. Selection is two-pass:
  pass 1 refuses collisions, pass 2 ignores them, so per-company
  minimums and pool size are never starved by uniqueness (it is a
  preference, not a hard filter). Sorting `combined_minimums` by
  scarcity first means roles with the fewest spare bullets claim their
  metrics before roles with slack. The retry loop also **hill-climbs**:
  each attempt restarts from the best-scoring resume so far rather than
  the previous attempt's output, because Step 5 regenerates the whole
  resume and a bad attempt would otherwise poison every attempt after
  it. Widening the retry-time metric inventory to fire on widow
  violations was tried and reverted on 2026-08-12 — the model started
  deleting bullets to dodge collisions, breaking per-role minimums.
