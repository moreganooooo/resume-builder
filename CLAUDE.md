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
  macOS 12 support. A caret would silently resolve to 1.62.x and break all rendering.
- Bare `python3` on this machine may resolve to an unrelated stray venv —
  always activate `.venv/` first (see `.claude.local.md`).
- CSV-append locking (`jd_manager.py`) uses `fcntl.flock`, which is POSIX-only.
  Degrades gracefully (not a crash) on native Windows.
- The interactive menu and dashboard default to Catppuccin themes and Nerd Font glyphs — if your
  terminal doesn't have one active, set `RESUME_BUILDER_ICONS=unicode` in
  your shell profile to fall back to plain Unicode symbols. For accessibility
  or reduced motion preferences, set `RESUME_BUILDER_MOTION=reduced`.
- API keys and source-specific secrets live in the active profile's own
  `.env` file (`profiles/<name>/.env`), not a shared project-root `.env`.
- Multiple profiles can share one checkout (`profiles/<name>/`) —
  `RESUME_PROFILE` env var selects which one is active (defaults to
  `morgan` if unset). `scripts/profile_paths.py` is the single source of
  truth for every profile-scoped path; route new code through it rather
  than hand-rolling a `profiles/<name>/...` join.
- `resume doctor` is the fast way to check whether the whole environment
  (Python packages, Node/Playwright, API keys, fonts, KB files) is
  actually set up correctly, plus a real test-suite run.
- `dashboard/` is a vendored Go module (Bubble Tea TUI) — see `dashboard/CLAUDE.md` for its architecture.
- **Multi-computer sync (Syncthing):** a profile's data can sync across
  machines via Syncthing, four independent folders per profile —
  `scripts/profile_paths.sync_roots(profile)` is the single source of
  truth for exactly which four (`profiles/<name>/`, `jds/<name>/`,
  `output/<name>/`, `data/<name>/`). See README's "Multi-computer sync" section
  for the actual Syncthing setup walkthrough.

## Shortcuts
- `resume run` / `resume run jds/<profile>/some_file.txt` — batch or
  single-file mode, venv handled automatically.
- `resume test` — full test suite, venv handled automatically.
- `resume doctor` — environment/dependency/config health check + test
  suite, plain-English summary with a suggested fix per problem.
- `resume activate` — cd into the project and activate `.venv/` in the
  current shell (stays active, unlike `run`/`test` which use a subshell).
- `scripts/cli.py`'s help and errors are styled by `scripts/cli_help.py`
  (`StyledGroup`): the Go dashboard CLI's fang palette applied to Click's
  formatter, plus "✗ Error" and a fix line.
- Defined in `scripts/resume-cli.sh`, sourced from your shell profile.

## Running
- `python scripts/orchestrator.py` (no args) — batch mode: processes every
  JD not yet completed in the active profile's JDs directory.
- `python scripts/orchestrator.py jds/<profile>/some_file.txt` — single-file
  mode.
- Completed JDs move to the active profile's `completed/` folder;
  expired JDs move to `expired/`; history logs to
  `jds/<profile>/jd_tracker_log.csv` (gitignored).
- Interrupted runs resume from `output/<profile>/checkpoints/<job_key>.json`
  instead of restarting — don't delete that folder mid-run.
- `resume sample` (`scripts/build_sample.py`) is a QA smoke test: runs the
  full tailor+render pipeline against `fixtures/sample_jd.txt`, skipping
  the move-to-completed side effects a real JD gets.

## Testing
- `python -m unittest discover -s tests -v`, run from the project root with
  `.venv/` activated. Stdlib `unittest`, not pytest.

---

## Detailed Architecture Notes

For deep dives into implementation details, historical context, and measured
constraints (edge cases, quota limits, why specific patterns exist, etc.),
see [ARCHITECTURE.md](ARCHITECTURE.md).

Key topics in ARCHITECTURE.md:
- **JD metadata conventions** — underscore-prefixed keys for persistence
- **Database and file-sync patterns** — test isolation, profile handling
- **Company research tiers** — fallback strategy and measurements
- **Scoring system** — model selection, quota families, fallbacks
- **Resume building pipeline** — Steps 1-7, critique flow, recommendation retries
- **UI/dashboard internals** — Pipeline/Jobs data sources, filters, rendering
- **Email handling** — inbox sync, classifier gates, ATS detection
- **Scanning infrastructure** — board sources, deduplication, liveness checks
- **Search and knowledge base** — vector embeddings, tools ranking, lemma capping
- **Performance constraints** — Gemma TPM caps, context budgets, preflight checks
