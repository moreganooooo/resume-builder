# resume-builder

Tailors a resume per job description using Gemini/Gemma, then renders it to PDF.

## Setup
- Requires Python 3.10+ (code uses `str | None` syntax). A venv already
  exists at `.venv/` — `source .venv/bin/activate` (or `resume activate`
  from any shell, see Shortcuts below). If it's ever missing/broken, rebuild
  with `/usr/local/bin/python3.13 -m venv .venv && source .venv/bin/activate
  && pip install -r requirements.txt`.
- PDF generation (`scripts/generate-pdf.mjs`) needs Node + Playwright's
  Chromium browser installed: `npm install && npx playwright install
  chromium`. `node_modules/` is not guaranteed to already exist — don't
  assume it's there just because `package.json` is committed; check
  before debugging a PDF-generation failure.
- Bare `python3` on this machine may resolve to an unrelated stray venv —
  always activate `.venv/` first (see `.claude.local.md`).
- The interactive menu's icons default to Nerd Font glyphs — if your
  terminal doesn't have one active, set `RESUME_BUILDER_ICONS=unicode` in
  your shell profile (or before invoking `resume`) to fall back to plain
  Unicode symbols.
- API keys and source-specific secrets live in the active profile's own
  `.env` file (`profiles/<name>/.env`), not a shared project-root `.env`.
- Multiple profiles can share one checkout (`profiles/<name>/`) —
  `RESUME_PROFILE` env var selects which one is active (defaults to
  `morgan` if unset). `scripts/profile_paths.py` is the single source of
  truth for every profile-scoped path; route new code through it rather
  than hand-rolling a `profiles/<name>/...` join.
- `resume doctor` is the fast way to check whether the whole environment
  (Python packages, Node/Playwright, API keys, fonts, KB files) is
  actually set up correctly, plus a real test-suite run — reach for it
  before manually debugging a "why isn't this working" environment issue.
- `dashboard/` is a vendored Go module (Bubble Tea TUI, `resume
  dashboard`) — the one part of this repo not in Python. `scripts/
  dashboard.py` shells out to it via `go run .` (never `go build`, so no
  compiled binary should ever land in the repo). Needs the Go toolchain
  installed; everything else in this repo does not.
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