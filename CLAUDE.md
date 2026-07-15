# resume-builder

Tailors a resume per job description using Gemini/Gemma, then renders it to PDF.

## Setup
- Requires Python 3.10+ (code uses `str | None` syntax). A venv already
  exists at `.venv/` — `source .venv/bin/activate` (or `resume activate`
  from any shell, see Shortcuts below). If it's ever missing/broken, rebuild
  with `/usr/local/bin/python3.13 -m venv .venv && source .venv/bin/activate
  && pip install -r requirements.txt`.
- PDF generation (`scripts/generate-pdf.mjs`) needs Node + Playwright's
  Chromium browser installed.
- Bare `python3` on this machine may resolve to an unrelated stray venv —
  always activate `.venv/` first (see `.claude.local.md`).
- The interactive menu's icons default to Nerd Font glyphs — if your
  terminal doesn't have one active, set `RESUME_BUILDER_ICONS=unicode` in
  your shell profile (or before invoking `resume`) to fall back to plain
  Unicode symbols. See README's "Colors" section for how to enable a
  Nerd Font instead.

## Shortcuts
- `resume run` / `resume run jds/some_file.txt` — batch or single-file mode
  (see Running below), venv handled automatically.
- `resume test` — full test suite, venv handled automatically.
- `resume activate` — cd into the project and activate `.venv/` in the
  current shell (stays active, unlike `run`/`test` which use a subshell).
- Defined in `scripts/resume-cli.sh`, sourced from `~/.zshrc`.

## Running
- `python scripts/orchestrator.py` (no args) — batch mode: processes every
  JD not yet completed in `jds/`, splitting any multi-job JSON export into
  per-job files first.
- `python scripts/orchestrator.py jds/some_file.txt` — single-file mode.
- Completed JDs move to `jds/completed/`; history logs to
  `jds/jd_tracker_log.csv` (gitignored — may contain names/URLs).
- Interrupted runs resume from `output/checkpoints/<job_key>.json` instead
  of restarting — don't delete that folder mid-run.
- `jds/dummy_jd.txt` is a real test fixture kept there on purpose — batch
  mode will process it for real (real API calls) unless removed.

## Testing
- `python -m unittest discover -s tests -v`, run from the project root with
  `.venv/` activated. Stdlib `unittest`, not pytest (not installed) —
  discovery picks up every `tests/test_*.py` file, so this never goes stale
  as new test files are added.
