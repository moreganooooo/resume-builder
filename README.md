# resume-builder

Tailors a resume to a specific job description using Gemini/Gemma, then
renders it to an ATS-ready PDF. Content and formatting rules are enforced
both through prompting and through deterministic Python validation, rather
than trusting the model to follow formatting instructions on its own.

## Setup

1. Requires Python 3.10+ and Node (for PDF generation via Playwright).
2. Create the virtual environment and install Python dependencies:
   ```bash
   python3 -m venv .venv
   source .venv/bin/activate
   pip install -r requirements.txt
   ```
3. Install Node dependencies and Playwright's Chromium browser (needed by
   `scripts/generate-pdf.mjs`):
   ```bash
   npm install
   npx playwright install chromium
   ```
4. Create a `.env` file in the project root with your API key:
   ```
   GEMINI_API_KEY=your-key-here
   ```

## Shortcuts

Source `scripts/resume-cli.sh` from your shell profile (e.g. `~/.zshrc`) to
get a `resume` command usable from any directory, with the venv handled
automatically:

```bash
source /path/to/resume-builder/scripts/resume-cli.sh
```

| Command | What it does |
|---|---|
| `resume activate` | cd into the project and activate `.venv/` in your current shell — stays active, for running anything else manually |
| `resume cd` | cd into the project, no venv activation |
| `resume run` | batch mode — processes every pending JD in `jds/`, splitting any multi-job export into per-job files first |
| `resume run jds/some_file.txt` | single-file mode — tailor a resume for one specific JD |
| `resume test` | run the full test suite |
| `resume` (no arguments) | print this list of commands |

## Running without the shortcuts

- `python scripts/orchestrator.py` (no args) — batch mode.
- `python scripts/orchestrator.py jds/some_file.txt` — single-file mode.
- Completed JDs move to `jds/completed/`; history logs to
  `jds/jd_tracker_log.csv` (gitignored — may contain names/URLs).
- Interrupted runs resume automatically from
  `output/checkpoints/<job_key>.json` instead of restarting.

## Testing

```bash
python -m unittest discover -s tests -v
```

Stdlib `unittest`, not pytest (not installed) — discovery picks up every
`tests/test_*.py` file automatically.
