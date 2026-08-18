# resume-builder

Tailors a resume per job description using Gemini/Gemma, then renders it to PDF.

## Tool priorities
- Prefer `codebase-memory-mcp` graph tools over grep/glob for mapping this
  repo's structure (Python core + vendored `dashboard/` Go module) —
  fall back to grep if the graph doesn't have Go coverage.
- Prefer Lumen `semantic_search` to locate the right file before reading
  it whole, especially in `scripts/` where filenames don't always match
  behavior 1:1.

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
- `resume doctor` is the fast way to check whether the whole environment
  (Python packages, Node/Playwright, API keys, fonts, KB files) is
  actually set up correctly, plus a real test-suite run — reach for it
  before manually debugging a "why isn't this working" environment issue.
- `dashboard/` is a native Go module leveraging the Charmbracelet ecosystem (Bubble Tea v2, Lip Gloss v2, Glamour Markdown, Harmonica physics, and Huh forms, launched via `resume dashboard`).
  - Pre-compilation: `scripts/dashboard.py` and `scripts/charm_prompt.py` dynamically compile their Go binaries (`dashboard/bin/dashboard` and `dashboard/bin/prompt`) on first launch for sub-millisecond execution (gitignored - never committed). They gracefully fall back to slow `go run` or Questionary prompts if Go is unavailable.
  - Interactive Screens: Includes Pipeline checkpoint tracker, Jobs accordion browser, Knowledge Base Explorer (`viewKB` for browsing tools, metrics, facts, and projects with Glamour-rendered markdown viewports and live substring filtering), Progress monitor with Bubbles progress bars, and Report view.
  - Harmonica Physics & Responsive Viewport: Smooth spring-eased reveal animations and automatic terminal resize reflow with 80x24 minimum viewport warning cards.
  - **Visual TUI Inspection**: Generate high-DPI retina snapshots with `python3 scripts/capture_tui_visuals.py --out artifacts/tui_capture.png`. Claude can read/view `artifacts/tui_capture.png` directly to visually audit terminal layout, alignment, and color contrast.
  - **VHS Recordings**: Tapes located in `dashboard/tapes/` (`menu.tape`, `pipeline.tape`, `jobs.tape`, `kb_view.tape`, `mobile.tape`) record animated GIFs via `vhs <tape_path>`.
  - **Android & Mobile Termux**: Termux (`TERMUX_VERSION`) and mobile mode (`RESUME_BUILDER_MOBILE=1`) are auto-detected, relaxing minimum terminal dimensions to 35x12 and enabling full touch/tap navigation via `tea.WithMouseCellMotion()`. Run `./scripts/build_mobile.sh` to cross-compile static ARM64/AMD64 binaries into `dist/mobile/`. Slash commands `/visual-tui`, `/build-mobile`, and `/audit-tui` are available in `.claude/commands/`.
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
- **`dashboard/` was vendored from the `career-ops` sibling repo's
  `dashboard/` on 2026-07-22** (themed to this project's palette/icons,
  plus two real bugs fixed there — a tracker-column-count mismatch and a
  narrow-terminal crash). This repo's copy is authoritative going
  forward; `career-ops/dashboard/` is not where future dashboard changes
  should land, and may drift stale over time. See `IDEAS_ARCHIVE.md` for
  the full writeup.
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
- **Embedded ACID SQLite Store (`db.py`):** `profiles/<profile>/data.db` manages connection pooling, schema initialization, and database queries for job postings, application funnel status transitions, and bullet bank achievements with transaction safety and indexed query performance.
- **Dynamic Credentials Shield (`gemini_client.py`):** `gemini_client.py` calculates API authorization headers dynamically per call via `_get_auth_headers()`, ensuring profile switches immediately adopt the active profile's `GEMINI_API_KEY`.
- **Typst Vector PDF Engine (`render_typst.py`):** Provides sub-second vector PDF generation directly from structured `.typ` document templates without headless browser overhead.
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
