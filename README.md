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
5. Optional, only needed for `resume scan`:
   - `JOBRIGHT_COOKIE_STRING` in `.env` — a JobRight session cookie string
     (DevTools > Application > Cookies on jobright.ai). Needed for
     `--source jobright`.
   - `--source linkedin` needs no `.env` value at all — it reads your live
     `li_at` session cookie straight out of Chrome's cookie store via
     `browser_cookie3` on every run, so just be logged into LinkedIn in
     Chrome when you run it. The cookie is never written to disk. This also
     needs a real local Chrome install (Selenium drives it headlessly).

## CLI

`scripts/cli.py` is the actual command surface (Click-based); the `resume`
shell shortcuts below are thin wrappers around it plus a couple of extras
(`activate`, `cd`, `test`). Both are always in sync — the shortcuts just
call `python scripts/cli.py <command>` under the hood.

| Command | What it does |
|---|---|
| `resume run` | tailor + render every pending JD in `jds/` (batch mode), splitting any multi-job export into per-job files first |
| `resume run jds/some_file.txt` | tailor + render one specific JD file |
| `resume evaluate jds/some_file.txt` | score a JD's fit (go/no-go) *without* building a resume — see "Evaluating fit" below |
| `resume scan` | pull new postings from every configured source (JobRight, LinkedIn) into `jds/`, deduped against history |
| `resume scan --source jobright` | pull from just one source (repeatable flag) |
| `resume activate` | cd into the project and activate `.venv/` in your current shell — stays active, for running anything else manually |
| `resume cd` | cd into the project, no venv activation |
| `resume test` | run the full test suite (compact: dots + summary, no app-log noise) |
| `resume test -v` | same, but lists every test by name |
| `resume test -vv` | same, but shows the app's own operational logging too |
| `resume` (no arguments) | print this list of commands |

Source `scripts/resume-cli.sh` from your shell profile (e.g. `~/.zshrc`) to
get the `resume` command usable from any directory, with the venv handled
automatically:

```bash
source /path/to/resume-builder/scripts/resume-cli.sh
```

### Running without the shortcuts

- `python scripts/cli.py <command>` — the same commands as above, directly
  (needs the venv activated first).
- `python scripts/orchestrator.py` (no args) / `python scripts/orchestrator.py
  jds/some_file.txt` — the underlying batch/single-file pipeline `cli.py run`
  and `cli.py tailor` call; still works standalone if you want to bypass the
  CLI skin entirely.
- Completed JDs move to `jds/completed/`; history logs to
  `jds/jd_tracker_log.csv` (gitignored — may contain names/URLs) and to
  `data/applications.md` (see "Tracking applications" below).
- Interrupted runs resume automatically from
  `output/checkpoints/<job_key>.json` instead of restarting.

## Evaluating fit

`resume evaluate <jd_file>` scores a JD against a 10-dimension weighted
rubric (ported from career-ops: CV match, North Star alignment, remote
quality, level fit, comp, growth, time-to-offer, tool relevance, company
reputation, cultural signals) and prints a composite score out of 5, a
recommendation (Strong pursue / Selective pursue / Low-priority pursue /
Skip), and hard blockers if any (e.g. onsite-only). It's read-only — no
files are written, no resume is built. Useful for triaging a pile of scanned
JDs before committing to a full tailor run.

## Scanning for new postings

`resume scan` pulls job postings from JobRight (`--source jobright`) and/or
LinkedIn (`--source linkedin`) and writes new ones straight into `jds/` as
JD files, ready for `resume run`/`resume tailor`. No database — dedup is
against `jd_tracker_log.csv` and `jds/` itself
(`jd_manager.job_key_known()`), keyed by each posting's source job ID.

**Careful with `resume run` after a scan** — batch mode processes every
pending JD in `jds/`, so a scan that turns up dozens of postings means a
real, uninterrupted batch of resume builds (real Gemini spend) if you run
it right after. `resume evaluate` each one first, or thin the pile, before
batch-running.

## Tracking applications

Every completed build appends a row to two places: `jds/jd_tracker_log.csv`
(machine-readable, drives dedup/resume logic) and `data/applications.md`
(career-ops's markdown-table format — `# | Date | Company | Role | Score |
Status | PDF | Report | Notes` — for human review). Both are gitignored.
`Score`/`Report` are placeholders until an evaluate/scan result is wired
into a given row.

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

The `scan` → `evaluate` → `tailor` → `render` → `track` pipeline described
above (`resume scan`, `resume evaluate`, `resume run`/`tailor`, and
`data/applications.md`) is built as of 2026-07-04. Further feature ideas
(cover letter generation, situational work-history entries, multi-user
support, a long-term merge with sibling projects) are tracked in
`IDEAS.md`, organized by difficulty/scope. Nothing there is scheduled.

## Testing

```bash
python -m unittest discover -s tests
```

Stdlib `unittest`, not pytest (not installed) — discovery picks up every
`tests/test_*.py` file automatically. `unittest`'s own pass/fail reporting
goes to stderr, while the application code under test prints its own
operational logging to stdout — `resume test` takes advantage of this to
discard stdout by default, so the output stays a clean pass/fail summary
instead of an interleaved wall of text (see the CLI table above for the
verbose tiers).
