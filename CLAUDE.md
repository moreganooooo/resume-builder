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
- **The backlog has one definition too, and it is a WORK LIST, not just a
  count: `picker.unevaluated_roles()`.** It returns
  `(file_paths, database_only_job_ids)`;
  `count_unevaluated_roles()` reports its size and
  `batch_evaluate.evaluate_all_pending()` does the work, so the number
  the banner promises is exactly what gets evaluated. That pairing is the
  point: "Evaluate ALL Pending Roles" used to build its work list from
  `jd_manager.get_pending_jds()`, which lists FILES, while most pending
  jobs are database-only hash-keyed scan rows -- so 627 of a 1,337
  backlog were counted, displayed, and silently skipped. Database ids are
  evaluated through `jd_source.resolved_jd()` (temp file, synced back on
  exit). Two consequences: the database half FAILS CLOSED under
  `unittest` when the profile is not isolated (`db._is_unisolated_test_write`,
  the same guard `liveness._gather_db_candidates` uses) -- unguarded, a
  test that patches only the filesystem list pulls the developer's real
  pending rows into a work list that would spend real API calls; and a
  `Skip` verdict on a database-only job must call `jd_source.set_status()`
  AFTER the `resolved_jd()` block, because leaving that block runs
  `sync_back()`, which writes the payload's status over the row and
  silently reverts the archive.
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
- **Tests must not depend on who is operating the checkout.** Use
  `tests/persona.py` for any identity a test needs, and
  `persona.sandbox_profile()` for a complete throwaway profile (identity,
  fictional employers, education, situational roles, tag taxonomy,
  scanner filters). `tests/test_no_operator_identity.py` enforces this by
  reading the ACTIVE profile's `profile.yml` at runtime and failing if
  those values appear anywhere in `tests/` -- so it protects whoever runs
  it, not one fixed person. A test that hardcodes the operator's name,
  employers, or profile name either passes only on their machine or
  asserts facts about one resume rather than about the pipeline.
  Measured: a second user's run went from **233 failures to 7**.
  Two traps worth knowing: a `tearDown` that falls back to a hardcoded
  profile name raises inside `set_active_profile()` for anyone who lacks
  that profile AND leaves `RESUME_PROFILE` poisoned for every later test
  (129 cascading errors from one line); and `active_profile()` returning a
  hardcoded default when `RESUME_PROFILE` is unset silently handed other
  users paths to a nonexistent profile -- `_default_profile()` now
  resolves against what is actually on disk.
- **Renaming a profile moves four directories that other tools track by
  absolute path.** `profile_paths.rename_profile()` is the one place that
  does it: it applies the same name validation `create_new_profile()`
  uses (rename previously accepted `/` and `..`), checks every
  destination BEFORE moving any of them, and resolves "is this the active
  profile?" before the move rather than after (afterwards
  `active_profile()` can no longer find it and raises out of the menu).
  `rename_side_effects()` carries the three things it cannot fix, and the
  menu shows them before confirming: **Syncthing** (each root is a
  separate folder configured by path on every device -- the old paths go
  missing and may propagate as a deletion; pause, repoint, resume),
  **git** (`board_scanner/*.yml` are tracked, so it reads as a delete plus
  an untracked add), and **the shell** (`RESUME_PROFILE` is exported per
  terminal by `resume-cli.sh`).
- **`.gitignore` must exclude `profiles/*/*`, never `profiles/*/`.** Git
  cannot re-include a file whose PARENT DIRECTORY is excluded, so the
  directory-form pattern made both `!profiles/*/board_scanner/` negations
  dead and a new or renamed profile's board_scanner YAML silently
  un-committable. `profiles/morgan/`'s files survived only because they
  were already tracked, and gitignore does not apply to tracked files --
  which is exactly why it went unnoticed. Verify any change here with
  `git check-ignore -v --no-index <path>` (without `--no-index`, tracked
  files report "not ignored" regardless of the rules and you learn
  nothing).
- **`gemini_client._get_auth_headers()` is the test-network chokepoint,
  and it fails CLOSED.** All four `requests.post()` sites in that module
  build their headers through it, which is why the guard lives there
  rather than at each call site. Without it the suite made **78 live
  calls to `generativelanguage.googleapis.com` on every full run** --
  real spend, real 429s, and a wall-clock that swung between 127s and
  274s depending on rate limiting. Under `unittest` it now raises
  `TestNetworkBlockedError` unless `RESUME_ALLOW_TEST_NETWORK=1` is set
  (same escape hatch as `websearch_ddg.py`'s `_TEST_NETWORK_ENV`).
  Raising rather than returning a canned response is deliberate: a guard
  that degraded silently would leave those tests green while asserting
  nothing, which is worse than the original bug -- the same reasoning as
  `db._is_unisolated_test_write` dropping a write instead of faking one.
  `tests/test_gemini_client.py` opts in via `setUpModule()` because every
  test there mocks `requests.post` and only trips the guard through
  argument evaluation; a test added there WITHOUT that mock will make a
  real billable call. Verify with an instrumented run (patch
  `requests.Session.request` and `httpx.Client.send`), not by reading.
- **A profile has FOUR roots, and isolating one is not isolating the
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
- **`profile.yml`'s `candidate` block is the single source of truth for
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
- **There is no identity fallback, by design.** `fixed_content_module()`
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
- **Entry points must preflight the profile before importing anything
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
- **The Go bootstrap wizard runs from `dashboard/`, not the project
  root.** There is no root `go.mod`, so `go run ./dashboard/cmd/bootstrap`
  from the root fails with "cannot find main module" -- and the
  questionary fallback was gated on Go being ABSENT, so having Go
  installed guaranteed the broken path and never the working one. That
  silently broke "New User? Start Here!" for every Go-equipped machine.
  `menu._run_go_bootstrap_wizard()` builds/runs `dashboard/bin/bootstrap`
  with `cwd=dashboard/`, treats exit code 130 as user-cancelled (per
  `cmd/bootstrap/main.go`), and falls back to the questionary wizard on
  ANY failure, not just missing Go.
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
- **Location and commute radius are one switch, and it is opt-in.**
  `scripts/geo_distance.py` resolves a location string to a point
  (bundled GeoNames centroids in `assets/geodata/`, ~680 KB gzipped, NOT
  `data/` -- that is profile-scoped and a Syncthing root, and this is
  shared read-only reference data). `scripts/location_filter.py` turns
  that into a verdict: exclusion fencing ("Excluding CA, CO, NY"),
  compound hubs scored by NEAREST ("Austin, TX OR Overland Park, KS"),
  radius, and international rejection. `scripts/location_settings.py` is
  the editor behind Settings & Upkeep. Three rules that look like details
  and are not: (1) an unresolvable location is KEPT for review, never
  treated as far away -- surfacing an unknown is cheap to eyeball,
  silently dropping a commutable role is not; (2) `distance_miles` is
  `None` when unknown, never `0`, and decodes into a `*float64` on the Go
  side so a nearest-first sort cannot float unknowns to the top; (3) a
  posting whose workplace mode cannot be determined is never dropped on
  mode alone, because providers routinely omit the field.
  `workplace_mode` accepts a single value or a LIST (`[remote, onsite]`)
  for the combination one value cannot express. The whole thing is
  inert until a `location:` block exists in `scan_filters.yml`: that
  block both relaxes the keyword `block:` list (which rejects
  "Onsite"/"Hybrid" outright) and supplies the radius replacing it, so
  the two can never be out of step.
- **The location gate has exactly one chokepoint.**
  `scan_boards._passes_location_filter()` -- `scan_ats.py` routes through
  it too, so anything added there covers both scanners. It is NOT in
  `prefilter.py`, which reads JD body prose at batch-sweep time for
  deal-breaker phrases; that is a different input at a different stage
  and stays a downstream safety net. A provider whose location format the
  resolver cannot parse silently defeats the radius by landing in the
  permissive "unresolvable" bucket -- adzuna did exactly this by
  reporting "Buffalo, Erie County" (city, COUNTY) until it was mapped
  from its structured `area` array instead.
- **"Hybrid preferred" is a second, later chokepoint, not a third
  location gate.** `location_filter.evaluate_location()` short-circuits
  past the radius entirely once it classifies a posting REMOTE -- so a
  posting whose `location` field says "Remote" but whose BODY separately
  prefers hybrid candidates sailed through unrestricted, because that
  preference lives in prose the location gate never reads. It can't be
  checked at the same point as the general radius gate either: that gate
  runs before the description is fetched (the whole reason
  `_passes_location_filter` takes only a location string), and prose
  requires the description to exist. `location_filter.evaluate_hybrid_preference()`
  is called from `scan_boards._passes_hybrid_preference_filter()` at the
  same point as the hours/compensation gates -- after the description
  exists -- and reuses the SAME `location:` radius the general gate
  uses, deliberately, rather than a second hardcoded threshold that
  could drift from what the user actually configured. Deliberately
  narrow: it only fires on a stated PREFERENCE ("hybrid preferred",
  "ideally hybrid") -- a stated REQUIREMENT is already caught by
  `classify_workplace()`/the keyword `block:` list, so matching that too
  would just duplicate an existing rejection. Resolves distance from the
  `location` field's own named city, same as the general radius gate --
  it does not scan the description for a city, so "Remote (US)" with a
  hybrid-preferred body and no named office stays in the permissive
  "unresolvable, kept for review" bucket, per the same
  unresolvable-is-not-far rule as everywhere else in this file.
- **Aggregators are discovery sources; ATS boards are text sources.**
  Measured: greenhouse a median of 8,898 description characters,
  workday 8,427, indeed 3,983 -- versus jooble ~275 and adzuna EXACTLY
  500, both with a trailing ellipsis and no recovery path (both posting
  pages 403 every fetch, browser User-Agent included). That is their
  business model, not a bug to fix. A provider that knows its text is a
  blurb sets `description_is_teaser`, which
  `scan_boards._flag_thin_description()` honors REGARDLESS of length --
  adzuna's 500 chars clears `MIN_DESCRIPTION_CHARS`, so length alone
  would report it as complete. That constant was raised 200 -> 600,
  calibrated against this profile's own corpus: the thinnest real
  posting from any full-text source is 632 characters, and teasers
  cluster near 275, so 600 sits in the empty gap between the two
  populations.
- **`scripts/discover_local_employers.py` bridges the two.** It reads
  local postings, extracts employer names, probes each for a public ATS
  board, and appends confirmed hits to `tracked_companies.yml`. Two
  false-positive classes were found by running it live and both would
  have attributed a national company's postings to a local employer:
  (1) slug guessing -- a first-word fallback matched "Stellar Roofing"
  to whatever company owns the `stellar` board, and five of six hits in
  the first run were this; only full-name slugs are tried now; (2)
  unverified ownership -- where a provider discloses who owns a board the
  name must match, since SmartRecruiters answered for "Evolution Dental
  Science" with a board named plainly "Evolution". Ashby and Lever
  disclose no owner, so there the strict slug is the only evidence.
  Detection also requires a NON-EMPTY posting list: SmartRecruiters
  returns 200 with `totalFound: 0` for slugs that do not exist at all.
- **A liveness sweep's temp files must be per-run, never a fixed path.**
  `liveness._run_temp_paths()` generates a unique input/output pair for
  every `check-liveness.mjs` spawn. They used to be two module-level
  constants shared by every sweep of a profile, and `open(path, "w")`
  truncates -- so an overlapping run, or an orphaned Node child from a run
  killed mid-check, destroyed a live run's results while both children
  exited 0. Never reintroduce a shared temp path here: the child writes
  its whole result blob once, at exit, so a truncation is a total loss of
  that sweep, and the failure is silent (exit 0 plus an unreadable file).
  `leftover_temp_files()` finds residue from killed runs, and is what the
  cleanup tests assert on rather than hardcoding generated names.
- **A liveness verdict distinguishes "could not tell" from "was never
  shown the page."** `blocked` (`liveness-core.mjs`) covers anti-bot
  interstitials and login walls, checked AFTER the expired patterns so a
  genuinely closed posting behind a wall still reports `expired`, and
  after the apply-control check so a readable page is never called
  blocked. It was measured, not guessed: of 364 `uncertain` verdicts, 121
  were withheld pages (48 Indeed, 29 LinkedIn) and 208 were
  `insufficient_content` -- JS-rendered aggregators and Workday SPAs that
  had not painted their body before `liveness-browser.mjs`'s fixed
  1,200 ms wait elapsed. That wait now polls
  (`readRenderedBodyText`) only for pages that come up short of
  `MIN_CONTENT_CHARS`, which is exported from `liveness-core.mjs` so the
  reader and the classifier cannot disagree about the threshold. A fast
  page pays nothing; raising the fixed wait for every URL would have
  added minutes to a sweep already running 15.
- **A JD with no description is never written (`scan.run_scan`).**
  Writing one makes the emptiness permanent -- `job_key_known()` skips
  that posting on every later scan, so the good version never lands.
  Only workday produced these (28 of 615 on 2026-08-21): its listing
  endpoint carries no body text and its posting page is a JS SPA, so
  `_fetch_posting_text` cannot recover one either. The underlying cause
  was workday's detail fetches SHARING pagination's 20s budget; they now
  have their own, and workday gets a longer subprocess timeout via
  `scan_boards.PROVIDER_TIMEOUT_SECONDS` rather than raising the default
  for all providers. Its ctx pacing (`minGapMs: 250`, fully serialized)
  is deliberate politeness toward the target site and is NOT a knob to
  turn -- ~76 postings genuinely need ~46s.
- **Indeed is a Python source, and only Indeed.** `scripts/scan_indeed.py`
  is registered in `scan.py`'s `SOURCE_FETCHERS` alongside jobright and
  linkedin, because Indeed has no free public API and the only
  maintained scraper is JobSpy (MIT), a Python library. Of JobSpy's five
  sites, only Indeed works: zip_recruiter 403s (Cloudflare, and
  `curl_cffi` impersonation does not help -- tested), glassdoor 400s with
  "location not parsed", google returns 0 results even with
  `google_search_term`, and linkedin returns an EMPTY location field that
  would defeat the radius filter (and is already covered by
  `scan_linkedin.py`). Those measurements, including a control run where
  Indeed succeeded in the same process, are recorded in that module's
  docstring so they read as tested-and-rejected rather than untried.
  Note JobSpy hard-pins `numpy==1.26.3`, which will fight any Dependabot
  bump of numpy.
- **Websearch sweeps: Python searches, Node filters.** Brave's free tier
  became metered, so DuckDuckGo is the default backend
  (`scripts/websearch_ddg.py`) and Brave is used only when
  `BRAVE_API_KEY` is set. The search MUST happen in Python: DuckDuckGo's
  HTML endpoint answers a plain Node fetch with HTTP 202 and an empty
  challenge page after the first request or two, pacing and browser
  User-Agent included. The filtering deliberately stays in
  `websearch.mjs`, where the blocked-domain list, job-URL recognition and
  provider promotion already live -- results ride along on the entry as
  `_results`. `search()` returns `[]` under `unittest` unless
  `RESUME_ALLOW_TEST_NETWORK` is set, because every scan_ats test that
  exercises the sweep loop reaches it and the suite otherwise fires real
  queries (the same shape as the liveness/Playwright regression above).
- **Skill-matrix coverage is a RANK, not a cosine.** Gemini text
  embeddings occupy a narrow cone: measured 2026-08-24 over this
  profile's own 844-bullet corpus, two RANDOMLY chosen bullets had a
  median cosine of 0.727, and 5% of unrelated pairs already exceeded
  0.85. Because `dashboard_actions._matrix()` scores a skill by its MAX
  similarity across the whole bank, any affine rescale of raw cosine is
  degenerate -- the original `(x - 0.50) / 0.35` mapping pinned 95% of
  queries at 100% and never returned below 63.9%, so the bar could not
  express a gap, which is the only thing a "Skills Gap Matrix" exists to
  show. `_coverage_percentile()` instead ranks the skill's best match
  against `_coverage_reference()`, the distribution of each bullet's
  similarity to its nearest OTHER bullet (the diagonal MUST be masked --
  unmasked, every bullet's best match is itself at 1.0 and the scale
  collapses to a constant). This needs no hand-tuned constants and
  re-calibrates itself as the bank grows or the embedding model changes.
  Do not reintroduce a fixed band; if you want one, measure it against
  real skill-phrase embeddings first, not bullet-to-bullet similarity.
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
- **A posting's body is full of money that is not the salary
  (`scripts/compensation.py`).** Taking the first dollar figure in a body
  was measured against the real 1,761-body corpus at a $40,000 floor and
  rejected 99 postings — essentially all of them benefits ($50 monthly
  internet stipend, $2,000 professional-development stipend, $4,000
  travel allowance). Same inverted signal that ruled out
  keyword-detecting unpaid work (241 hits for "unpaid"/"volunteer"/
  "stipend" in that corpus, **zero** true positives — "volunteer" is the
  company's volunteering program, and the one "unpaid" is "paid and
  unpaid time away from work"). A figure now counts only when
  `_PAY_ANCHOR` matches its ±60-char window and `_BENEFIT_NEAR` does
  not. Two traps: the period-word scan must take the NEAREST cue, not
  the first in list order (a salary near "20-25 hours per week"
  annualized $95,000 to $4.9M); and a provider's salary FIELD needs
  `require_anchor=False`, since ashby's "$100K – $130K" tier summary
  carries no sentence to anchor against. Compare against the MAX, never
  the min — a $30-95K band clears a $40K floor. Pay is an EMPLOYER
  property (0–100% coverage within a single provider), unlike employment
  type, so there is no provider-level salary expectation and
  `require_stated` defaults off: a floor narrows the ~27% that disclose,
  not the list. `describe_bias()` exists so the UI says that out loud.
- **Weekly hours refine part-time; they do not filter the corpus
  (`scripts/work_hours.py`).** Only 2.3% of postings state hours, but
  **27% of part-time ones do**, and the values cluster exactly on the
  distinction that matters (10-20 vs 24-30 vs 40). The dominant false
  positive is duration, not schedule — "respond within 24 hours", "48
  hours notice", "40 hours of PTO" — so a match REQUIRES an explicit
  weekly unit; that is what makes a number a schedule. Comparison is
  OVERLAP, not containment: a 10-30 hour posting satisfies a 20-40 want,
  and requiring containment would reject every flexible role. An
  open-ended bound stays open — "up to 25 hours" says nothing about the
  floor, and filling one in invents a fact the posting never stated.
- **`jd_manager.save_evaluation` is an ALLOWLIST, not a copy.** A key the
  model produces and `orchestrator` assembles is silently discarded
  unless it is named there. That is what happened to `capability_gaps`
  for its entire existence: `CapabilityEvaluationSchema` required it,
  orchestrator injected it, and **0 of 1,138** evaluated JDs on disk
  carried it. Anything added to an evaluation schema needs a line in that
  dict too — `tests/test_compensation.py` asserts every
  `CapabilityEvaluationSchema` field appears in the writer. Existing
  evaluations cannot be backfilled for a field that was never saved.
  Experience gaps render BELOW and separate from hard blockers in the
  Jobs detail pane: a gap is something to address in an application, a
  blocker is a reason not to apply, and one merged list conflates them.
- **A score has a VINTAGE, and nothing in the row says so
  (`picker.SCORING_EPOCH`).** Three commits changed what a fit score
  MEANS -- `032153ca` rebuilt Fit/Interview Odds (2026-08-16),
  `27e6d6b9` added proximity scoring (2026-08-22), `a2939fe2` started
  sending the candidate's credentials to the evaluator (2026-08-30) --
  and a stored evaluation looks identical whichever it came from.
  Measured 2026-08-31: **0 of 2,130** evaluated rows carried a
  current-system score, and 351 had no `evaluated_at` at all (treated as
  stale, since the field was added later -- its absence dates the record
  rather than excusing it). Only the PENDING subset is worth repairing;
  the rest is archived or expired. `pending_roles(evaluated_before=...)`
  is the general walker and `unevaluated_roles()`/`stale_roles()` are
  thin wrappers over it, so the count a surface shows and the set the
  evaluator walks cannot drift. Bump `SCORING_EPOCH` when a commit
  changes what a score means -- NOT for a newly persisted field, which is
  a gap in the record rather than an error in it -- and batch scoring
  changes, since a bump costs one API call per pending role.
  `_evaluation["scoring_version"]` (`jd_manager.SCORING_VERSION`) now
  rides alongside `evaluated_at` on every newly saved evaluation --
  `_evaluation_is_stale()` checks it first, an exact int comparison, and
  only falls back to the `SCORING_EPOCH` date-string comparison for
  evaluations saved before the field existed. It does not resolve the
  351 undated rows: there is nothing in them to derive a version from,
  so they stay stale by the same absence-dates-the-record rule as
  before. Bump both together, the same day, for the same reason.
- **`role_track` (IC vs. manager) is wired into `evaluate_capability.md`
  / `CapabilityEvaluationSchema`, and it is a SORT/display facet, never a
  gate -- do not build an exclusion filter on it without a labeled
  accuracy bar first.** `scripts/build_role_track_holdout.py`'s hand
  labels (134/134 done) measure why: of 49 postings whose only manager
  signal was the title (`title-only` + `neither` strata), **zero** were
  people managers, while `title+body` is 29 managers of 40 -- title
  carries no signal, body evidence does. The schema's negative
  instruction is written from that measurement, not a guess, and
  `role_track: "unknown"` is the *correct* answer for roughly 40% of
  postings (the model is told this explicitly, or it fills the gap with
  a title-derived guess -- the exact bias the field exists to avoid).
  `role_track_evidence` (the deciding quoted phrase) is what makes the
  holdout cheap to label and a wrong verdict correctable, and is required
  before any future opt-in exclusion (`manager` + `high` confidence +
  non-empty evidence). Surfaced read-only in the Jobs detail pane
  (`jobs.go`) only for `manager`/`player_coach` -- `unknown`/`ic` render
  nothing, since flagging the expected-40%-unknown case on every row
  would read as a data problem it isn't. The holdout's own excerpt
  generator (`_excerpt()`) used to cap at 900 chars and fall back to
  `body[:900]` -- mostly "About us..." boilerplate -- whenever its
  report-evidence regex found nothing, starving the labeler of exactly
  the text a body-only signal needs. Bodies under
  `MAX_FULL_EXCERPT_CHARS` (6000) are now shown whole;
  `--refresh-excerpts` rewrites excerpts for an already-labeled CSV in
  place (label/note untouched) rather than requiring `--force`, which
  would discard the labels to get wider text.
  `scripts/eval_role_track.py` (real Gemini calls, manual/not-CI) now
  measures actual model precision/recall against the holdout: **90.3%
  precision / 90.3% recall** as of 2026-09-02, after fixing one holdout
  mislabel (a `title-only` "Partner Sales Manager" row was labeled
  `manager` on the phrase "hold that partner accountable for the
  outcomes they own" -- that's holding an external partner company
  accountable, not a direct report; no headcount/hiring/review language
  anywhere and the role itself reports INTO another team, so it doesn't
  meet the prompt's own manager criteria; relabeled to `ic`). One
  genuine miss remains (`body-only`, an Anthropic "Revenue Strategy &
  Operations" posting containing "no direct reports initially... you
  will build the team over time" -- exactly the prompt's own
  reports-come-later example) and it is **not a class-imbalance/
  low-confidence artifact**: repeatability-tested at temperature=0.7,
  8/8 calls returned `ic` at `high` confidence, correctly quoting the
  trigger phrase as evidence while still concluding `ic`. Two prompt
  fixes were tried and both are confirmed NULL results, don't retry
  either without new evidence: (1) a broader four-dimension "Kamsa"
  rubric restructuring the whole role_track paragraph -- made things
  worse (87.5%/87.5%, one new false positive); (2) a surgical one-clause
  hard-rule addition ("if the phrase you are about to quote says or
  implies reports are coming later, `role_track` MUST be `manager`") --
  zero measured effect, identical 8/8 `ic` verdict and evidence quote
  before and after. The per-confidence breakdown was already in
  `eval_role_track.py` (nothing to build) but had never been run and
  read: all 31 manager/player_coach predictions on the 134-row
  holdout -- the 28 true positives AND all 3 false positives -- came
  back at `role_track_confidence: "high"`. A confidence gate on top of
  the verdict is therefore a no-op on this holdout (precision stays
  90.3% either way), which is the "all high confidence" floor of the
  scenario table in `docs/role_track.md`, not an improvement -- but
  still clears the ≥90% bar. `role_track` has since graduated to an
  opt-in, default-OFF **Jobs-screen view filter** (`[r]` key,
  `model.JobRow.IsManagerTrack()`, `dashboard/internal/ui/screens/jobs.go`)
  gated on manager-or-player_coach at high confidence -- deliberately a
  VIEW filter, not a scan-time/database gate, so the one known false
  negative (the Anthropic case above) never gets permanently dropped
  from the corpus; toggling the filter off always shows every posting
  again. Full history in `docs/role_track.md`.
- **`evaluate_all_pending(skip_evaluated=False)` was DEAD, and the shape
  of that bug recurs.** Its default work list came from
  `unevaluated_roles()`, which by definition holds nothing that has a
  score, so "force re-evaluate everything" walked the never-evaluated
  backlog and silently changed nothing -- there was no way to re-score
  any role at all. A flag that filters a set which already excludes its
  targets is not a weak flag, it is a no-op that reads as a feature.
- **A subscore the model cannot ground is invented, not estimated.**
  `compensation_viability` is 15% of Practical Pursue and its schema
  field reads "vs. stated target/floor" -- but no floor was ever passed
  to the prompt, and the rubric ("5 = likely strong and viable") plus
  "or likely range if unstated" actively invited a guess for the ~73% of
  postings that disclose nothing. `orchestrator.build_compensation_context()`
  now hands the evaluator `compensation.py`'s deterministic parse and the
  configured floor, and the rubric separates **stated-and-below** (2)
  from **NOT STATED** (3). Those are opposite facts and collapsing them
  is the whole bug: silence is not evidence of a low offer. The rubric
  also says "do not re-read the figures yourself", so the model cannot
  re-derive the benefit figures (`$50` internet stipend) that
  `_PAY_ANCHOR`/`_BENEFIT_NEAR` exist to exclude. Any future subscore
  that references a user setting must actually be SENT that setting --
  grep the prompt before trusting a schema description.
- **Stress and stretch enter `composite_score` as Python math, never an
  LLM subscore -- same reasoning as the proximity bonus and stale-posting
  penalty.** `orchestrator.fit_composite_score()` takes
  `stress_signal_count` (the number of `scripts/stress_signals.py`
  categories detected in the posting's own body, computed fresh each
  evaluation in `rescore_evaluation_with_location()`, never persisted) and
  `capability_gap_count` (`len(capability_gaps)`, a deterministic count
  distinct from `fit_subscores.level_plausibility`'s already-weighted
  subjective screen-risk judgment). Weighted asymmetrically by explicit
  user request: a posting with zero detected stress categories earns
  `LOW_STRESS_BONUS` (0.40), larger than the cost of any single detected
  category (`STRESS_SIGNAL_PENALTY_PER_CATEGORY`, 0.25, capped at 0.75) --
  finding a comfortable role is the stated goal, not merely avoiding red
  flags, so "clean" is rewarded rather than just spared a penalty.
  `capability_gaps` costs `STRETCH_GAP_PENALTY_PER_ITEM` (0.20/gap,
  capped at 0.80). These five values, plus the `funnel_friction` remote/
  onsite ±1 nudge described below, are chosen to match a stated
  preference rather than a corpus-measured precision number (see
  docs/superpowers/specs/2026-09-01-stress-challenge-scoring-design.md
  for the caveat that this skipped the corpus-validation step `role_track`
  and `work_hours.py`/`compensation.py` all went through first) -- but as
  of the `scoring_weights:` block below, they're no longer hardcoded
  Python literals; a user can retune them without a code change.
- **A remote posting competes against a bigger applicant pool than an
  onsite one, and `funnel_friction` says so.** `orchestrator.evaluate_fit()`
  step 5b (`scripts/orchestrator.py`) classifies the posting with the
  same `location_filter.classify_workplace()` used everywhere else in
  the location pipeline, then nudges the LLM's own `funnel_friction`
  subscore by ±1 (capped to 1-5) -- REMOTE gets harder, ONSITE gets
  easier, HYBRID/UNKNOWN are left alone since there's no deterministic
  local-pool-size signal to anchor a nudge to. This runs immediately
  after, and compounds with, the existing Tier-1/Tier-3 prestige-tier
  calibration (step 5) rather than replacing it -- same reasoning as
  that step: `funnel_friction` is exactly the kind of thing an LLM can
  underweight without an explicit anchor, and workplace mode is already
  a deterministic, structured field by the time evaluation runs, so
  there's no reason to trust a free-floating LLM guess over it. Like the
  prestige-tier nudge, this is a preference-weighted constant (±1), not
  a corpus-measured precision number.
- **`hard_blockers` used to unconditionally zero every score it touched,
  with zero precision measurement -- ever.** Any non-empty `hard_blockers`
  list from `evaluate_recruiter.md` forced `composite_score = 0` and
  `recommendation = "Skip"` (`orchestrator.py`
  `rescore_evaluation_with_location`), a stronger and less-validated gate
  than `role_track` was pre-graduation, and free text mixing "no
  bachelor's degree" in with "requires an active security clearance."
  Each blocker item now carries a `category`
  (`years_experience`/`degree`/`certification`/`citizenship_clearance`/
  `onsite_commute`/`other`, `HardBlockerSchema` in `scripts/schemas.py`).
  `orchestrator.EXPERIENCE_BLOCKER_CATEGORIES = ("years_experience",
  "degree")` carves those two out into a separate `experience_blockers`
  list -- persisted through the same allowlist as `hard_blockers`
  (`jd_manager.save_evaluation`) -- and they no longer zero anything;
  every OTHER category keeps the original unconditional zero-out
  behavior unchanged, including `is_spurious_commute_blocker`'s existing
  `onsite_commute` carve-out. Same reversibility principle as
  `role_track`: `experience_blockers` surfaces only as an opt-in view
  filter on both Jobs (`[c]`) and Pipeline (`[x]`, see below) -- a plain
  `len(...ExperienceBlockers) == 0` presence check in both screens, since
  `HardBlocker` carries no confidence field to gate on the way
  `RoleTrackConfidence` does. Not a gate, and won't become one without
  clearing the same ≥90% holdout bar `role_track` did -- see the "should
  this eventually be a hard stop" discussion below.
  `jd_manager.SCORING_VERSION` was bumped to `3` (2026-09-02) for this
  change, which is sufficient on its own to stale-flag every
  pre-existing evaluation -- `picker._evaluation_is_stale()` checks the
  int `scoring_version` first and only falls back to the `SCORING_EPOCH`
  date-string comparison for evaluations saved before that field
  existed, so a separate `SCORING_EPOCH` bump was not needed here.
  **The holdout labeling spreadsheet for `years_experience`/`degree`
  precision is not filled in yet** (as of 2026-09-02) -- `docs/hard_blockers.md`,
  referenced in a code comment (`orchestrator.py`, near
  `EXPERIENCE_BLOCKER_CATEGORIES`), does not exist yet either. Until that
  measurement exists, treat `experience_blockers`/`IsExperienceBlocked()`
  as unvalidated display/filter-only signal, same caution as any
  pre-holdout `role_track` state.
- **Six previously-hardcoded scoring constants are now a
  `scoring_weights:` block in `scan_filters.yml`, editable from Settings
  & Upkeep -- "Scoring Weights & Preferences" in `menu.py`.** Covers the
  five stress/stretch constants documented above
  (`stress_signal_penalty_per_category`, `stress_signal_max_penalty`,
  `low_stress_bonus`, `stretch_gap_penalty_per_item`,
  `stretch_gap_max_penalty`) plus the `funnel_friction` remote/onsite
  nudge magnitude. `content_settings.read_scoring_weights()` always
  returns all six keys (defaults merged with any override, so
  `orchestrator.py` never needs its own fallback), and
  `describe_scoring_weights()` only lists keys that differ from default
  for the menu header, since the common case is unedited. Same pattern
  as `_COMPENSATION_KEYS`: `_SCORING_WEIGHTS_KEYS` is an explicit
  allowlist, so a stray key in the YAML can't silently round-trip
  through the editor and look supported.
- **Pipeline has full filter parity with Jobs for the audited signals --
  and one filter (`[x]`, experience blockers) that Jobs itself doesn't
  have yet.** `dashboard/internal/model/career.go`'s `CareerApplication`
  gained `Workplace`, `EmploymentType`, pay/hours fields,
  `StressSignals`, `CapabilityGaps`, `RoleTrack`, and `ExperienceBlockers`;
  `jobs_to_apps.go`'s `JobRowsToApplications` populates them directly
  from `JobRow`/`Evaluation`, the same source Jobs itself reads (not the
  dead `deriveNoteFields`/markdown-tracker path). `pipeline.go` filters:
  `[w]` workplace, `[e]` employment type, `[$]` pay, `[t]` role track,
  `[x]` experience blockers. Jobs assigns `[r]` to role track (`[t]`
  would collide with nothing on Jobs, but `[r]` is Pipeline's own
  refresh key, so Pipeline uses `[t]` instead -- a deliberate, documented
  keybinding divergence, not a parity gap). **Jobs now has its own
  `experienceBlockerFilter` too**, bound to `[c]` (`w`/`e`/`$`/`r` were
  already taken there) -- opt-in view filter, footer legend, and
  detail-pane rendering, same shape as `[r]`/`roleTrackFilter` and
  Pipeline's own `[x]`. Both screens filter with a plain
  `len(...ExperienceBlockers) == 0` presence check, since `HardBlocker`
  carries no confidence field to gate on the way `RoleTrackConfidence`
  does.
- **`scripts/find_retroactively_excluded_roles.py` checks whether a
  PENDING role would be excluded under TODAY's config, even though it
  was saved under an older one -- two independent checks, counted
  separately.** Gate failures re-run the same deterministic scan-time
  gates `scan_boards.py` applies
  (`_passes_employment_filter`/`_passes_compensation_filter`/
  `_passes_hours_filter`/`_passes_location_filter`/
  `_passes_hybrid_preference_filter`) against the JD's own saved fields
  and the CURRENT `scan_filters.yml`. Score-based flags recompute
  `composite_score`/`recommendation` with current `fit_composite_score()`
  (current `scoring_weights`, current stress/capability-gap math) and
  flag anything that now comes out `Skip` -- evaluated roles only, since
  there's no score to recompute on a role that's never been evaluated.
  Covers the FULL pending population deliberately: gate-checking only
  already-evaluated rows (`picker.list_all_evaluated_jds()`) would miss
  the population most at risk -- roles scraped under an old filter
  config that haven't been evaluated yet, which `batch_evaluate.py` is
  about to spend an API call scoring. `picker.pending_roles()` (file
  paths + database-only ids, no evaluation required) is what reaches
  them; they get the gate check only. Same safe-maintenance-script shape
  as `purge_terminal_jobs.py`: dry-run by default, `--apply` required,
  `data.db` backed up via `shutil.copy2` before any write, restricted to
  PENDING roles only (never touches applied/interviewing/offer or any
  later funnel status) as a hard safety rule, not a toggle. **This gap is
  now closed automatically, not just by manual habit:**
  `batch_evaluate.evaluate_all_pending()` calls this module's
  `filter_gate_passing()` (gate check only, no score recompute) as a
  pre-flight on its auto-derived work list before spending any API call
  -- a role that wouldn't pass today's `scan_filters.yml` gates is
  excluded from the run and reported, never evaluated. Scoped to
  `auto_derived` work lists only (`pending_paths is None`); an explicit
  caller-supplied pick, e.g. `resume run --pick` naming one specific JD,
  bypasses this and always evaluates what was asked for. Deliberately
  non-destructive -- excluded roles are left out of that run, not
  archived; this script's own `--apply` mode (or a manual re-run) is
  still what archives them for good after review.
