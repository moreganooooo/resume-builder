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
| `resume test` | run the full test suite (compact: dots + summary, no app-log noise) |
| `resume test -v` | same, but lists every test by name |
| `resume test -vv` | same, but shows the app's own operational logging too |
| `resume` (no arguments) | print this list of commands |

## Running without the shortcuts

- `python scripts/orchestrator.py` (no args) — batch mode.
- `python scripts/orchestrator.py jds/some_file.txt` — single-file mode.
- Completed JDs move to `jds/completed/`; history logs to
  `jds/jd_tracker_log.csv` (gitignored — may contain names/URLs).
- Interrupted runs resume automatically from
  `output/checkpoints/<job_key>.json` instead of restarting.

## Bullet bank feedback loop

The bullet bank isn't static. During every build, `orchestrator.py`'s
bullet-audit step rewrites weak bullets and rescoring them; any rewrite that
clears the bank's real "keeper" bar (`scripts/bullet_feedback.py`) is queued
into `resume-engine/knowledge_base/needs-review.csv` automatically. Run
`python scripts/triage_needs_review.py` periodically to route those queued
rows into `bullet-bank-keepers.csv` (permanent), `rewrite-queue.csv`, or
`retired-bullets.csv` — this is a separate, manual step, not automatic, so
queued rows sit in `needs-review.csv` until you run it.

## Fonts

`resume-engine/fonts/DMSans-{Regular,ExtraBold,Italic}-static.ttf` are fixed
(non-variable) instances baked from Google's DM Sans variable font via
`fonttools varLib.instancer`. Don't swap these back for the raw variable
font — Chromium's print-to-PDF path (used by `scripts/generate-pdf.mjs`)
fragmented it into dozens of near-duplicate embedded font subsets and
coincided with a real bug where the PDF's underlying text layer came out
scrambled (visually correct on screen, but copy-pasted/ATS-extracted text
read backwards). Static instances avoid that code path entirely.

## Roadmap

Future feature ideas (cover letter generation, situational work-history
entries, multi-user support, a long-term merge with sibling projects) are
tracked in `IDEAS.md`, organized by difficulty/scope. Nothing there is
scheduled.

## Testing

```bash
python -m unittest discover -s tests
```

Stdlib `unittest`, not pytest (not installed) — discovery picks up every
`tests/test_*.py` file automatically. `unittest`'s own pass/fail reporting
goes to stderr, while the application code under test prints its own
operational logging to stdout — `resume test` takes advantage of this to
discard stdout by default, so the output stays a clean pass/fail summary
instead of an interleaved wall of text (see Shortcuts above for the
verbose tiers).
