# resume-builder

Tailors a resume per job description using Gemini/Gemma, then renders it to PDF.

## Setup
- Requires Python 3.10+ (code uses `str | None` syntax). Create a venv and
  `pip install -r requirements.txt`.
- PDF generation (`scripts/generate-pdf.mjs`) needs Node + Playwright's
  Chromium browser installed.

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
- `python3 -m unittest tests.test_jd_manager tests.test_orchestrator_audit_resume tests.test_orchestrator_build_checkpoint tests.test_orchestrator_main_batch -v`
  run from the project root. Stdlib `unittest`, not pytest (not installed).
