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
6. Optional, for the best icon experience: enable a [Nerd Font](https://www.nerdfonts.com/)
   in your terminal profile (iTerm2: Preferences → Profiles → Text → Font;
   Terminal.app: Preferences → Profiles → Text → Font). The menu's icons
   default to Nerd Font glyphs; without one active they'll render as
   blank boxes in that terminal window. No Nerd Font handy? Set
   `RESUME_BUILDER_ICONS=unicode` to use plain Unicode symbols instead —
   works everywhere, no special font required.

## CLI

`scripts/cli.py` is the actual command surface (Click-based); the `resume`
shell shortcuts below are thin wrappers around it plus a couple of extras
(`activate`, `cd`, `test`). Both are always in sync — the shortcuts just
call `python scripts/cli.py <command>` under the hood.

| Command | What it does |
|---|---|
| `resume` (no arguments) | launch the interactive menu — see "Interactive menu" below |
| `resume run` | tailor + render every pending JD in `jds/` (batch mode), splitting any multi-job export into per-job files first |
| `resume run jds/some_file.txt` | tailor + render one specific JD file |
| `resume run --pick` | interactively select which pending JD(s) to tailor — see "Picking which JDs to tailor" below |
| `resume coverletter jds/some_file.txt` | generate + render a cover letter for one JD — see "Generating cover letters" below |
| `resume coverletter --pick` | interactively select which pending JD(s) to generate a cover letter for — see "Picking which JDs to tailor" below |
| `resume polish` | interactively chat-edit an already-generated resume or cover letter — see "Polishing a resume or cover letter" below |
| `resume polish output/json/some_file_Resume.json` | polish that specific file directly, skipping the picker |
| `resume evaluate jds/some_file.txt` | score a JD's fit (go/no-go) *without* building a resume — see "Evaluating fit" below |
| `resume evaluate` | score every pending JD at once — see "Evaluating fit" below |
| `resume scan` | pull new postings from every configured source (JobRight, LinkedIn) into `jds/`, deduped against history |
| `resume scan --source jobright` | pull from just one source (repeatable flag) |
| `resume liveness` | check every pending JD's posting URL, moving confirmed-expired ones to `jds/expired/` — see "Checking posting liveness" below |
| `resume activate` | cd into the project and activate `.venv/` in your current shell — stays active, for running anything else manually |
| `resume cd` | cd into the project, no venv activation |
| `resume test` | run the full test suite (compact: dots + summary, no app-log noise) |
| `resume test -v` | same, but lists every test by name |
| `resume test -vv` | same, but shows the app's own operational logging too |
| `resume help` | print this list of commands (no menu launch) |

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
- JDs a liveness check confirms are dead move to `jds/expired/` instead —
  see "Checking posting liveness" below.
- Interrupted runs resume automatically from
  `output/checkpoints/<job_key>.json` instead of restarting.

## Interactive menu

Just typing `resume` (or `python scripts/cli.py` directly) launches an
interactive menu instead of running any single command, opening with a
block-letter title screen (bordered panel, diagonal blue-to-purple
gradient reveal — see "Colors" below) before the first arrow-key list.
Options are grouped (Discovery / Evaluation / Build / Utility) with a
category icon per item, and named after the pipeline stage they support:

- Scan for New Postings
- Check Posting Liveness
- Evaluate ALL Pending JDs / Evaluate a Specific JD
- Customize Resume for ALL Pending JDs (batch) / Customize Resume for a
  Specific JD
- Write cover letter for a Specific JD
- Polish a resume or cover letter — see "Polishing a resume or cover
  letter" below
- View Application Tracker — renders `data/applications.md` (see
  "Tracking applications" below) right in the terminal via Rich's
  Markdown renderer, table and clickable `Apply` links included, no need
  to open the file yourself

On launch, the title banner sweeps in with a diagonal blue-to-purple
gradient, followed by a live stats line (how many JDs are pending, how
many have been tailored all-time) and a rotating "did you know?" tip.
Returning to this menu after an action shows a compact one-line breadcrumb
instead of repainting the full banner. Choosing Exit prints a one-line
summary of what you actually did that session (e.g. "3 resumes tailored ·
2 cover letters written").

"Evaluate a Specific JD" and "Write cover letter for a Specific JD" use a
lightweight picker over pending/completed JDs (labeled by company/title,
no fit-scoring, no extra Gemini cost) — a different, cheaper mechanism
than `resume run --pick`/`resume coverletter --pick`'s evaluate-then-
checkbox flow (see "Picking which JDs to tailor" below), reserved for
when you already know which one you want.

**"Customize Resume for a Specific JD" is different: it only lists
already-evaluated JDs**, sorted best-fit first and labeled with each
one's score (`4.8/5 | Strong pursue | Acme | Content Strategist`) — since
building a resume for a role you haven't screened first rarely makes
sense. Evaluating (either menu option, or `resume evaluate`) persists its
score into the JD's own JSON file the first time, so this list doesn't
need a fresh Gemini call just to redisplay it. Nothing evaluated yet?
The picker prints a hint pointing at "Evaluate ALL Pending JDs"/"Evaluate
a Specific JD" instead of showing an empty list.

After an action that actually did something, a "What's next?" prompt
offers the natural next step in the pipeline (e.g. Scan → Check
Liveness → Evaluate All JDs → Customize Resume → Write Cover Letter /
Polish with Gemini), always with "Back to Menu" as an escape hatch —
nothing chains automatically without you choosing it, and a no-op action
(nothing found, declined confirmation) skips the prompt entirely rather
than asking about a step that has nothing to act on. Select Exit (or
cancel with Ctrl-C) to leave.

**Colors & icons:** every color and icon in the interactive menu is
sourced from one place, `scripts/theme.py` — explicit hex colors (blue
`#4dabf7`, purple `#673ab7`, green `#4caf50`, etc.) rather than named ANSI
colors like `cyan`, since named colors get remapped by whatever terminal
theme is active (on a dark-teal theme, `cyan` used to render as a washed-
out, nearly invisible gray). Icons default to Nerd Font glyphs (see
Setup above); set `RESUME_BUILDER_ICONS=unicode` to use plain Unicode
symbols instead if you haven't enabled one.

This is purely a navigation layer over the same commands documented
below — nothing here does anything a direct command couldn't already do,
it just means never having to remember or type a specific invocation.
Modeled on (and borrowing the color theme and scored-table styling from)
the sibling job_automater project's own interactive menu.

## Evaluating fit

`resume evaluate <jd_file>` scores a JD against a 10-dimension weighted
rubric (ported from career-ops: CV match, North Star alignment, remote
quality, level fit, comp, growth, time-to-offer, tool relevance, company
reputation, cultural signals) and prints a composite score out of 5, a
recommendation (Strong pursue / Selective pursue / Low-priority pursue /
Skip), and hard blockers if any (e.g. onsite-only). No resume is built.
Useful for triaging a pile of scanned JDs before committing to a full
tailor run. A successful evaluation does write one thing: the score and
recommendation get saved into the JD's own JSON file (an `_evaluation`
key), so "Customize Resume for a Specific JD" can filter/sort/label by it
later without spending another Gemini call — see "Interactive menu"
above. This metadata is automatically stripped back out before the JD's
text ever reaches a Gemini prompt again, so it never leaks into keyword
extraction or resume content.

**`resume evaluate` (no file argument)** scores every pending JD in one go
instead of one at a time — real cost: one Gemini call per pending JD.
**Skips any JD that's already been evaluated by default** — a successful
evaluation persists its score into the JD's own file (see below), so
re-running this doesn't re-spend a Gemini call re-scoring something
already scored. The confirmation prompt (`--yes` skips it) asks against
the real count of JDs actually about to be evaluated (the unscored ones),
not the full pending count, and a line above it reports how many
already-evaluated JDs are being skipped. Pass `--refresh` to force
re-evaluating everything anyway (overwriting existing scores). Calls are
paced (a few seconds apart) to
stay under this account's requests-per-minute tier instead of bursting
all of them at once and hitting HTTP 429s — the same pacing also applies
to `resume run --pick`/`resume coverletter --pick`, since both share this
same evaluation loop (note: `--pick`'s flows always evaluate fresh, not
skip-by-default, since showing you a checkbox list *is* the point of
that flow). Prints a sorted summary table (score, recommendation,
company, title, best-first); a JD that fails to evaluate shows `ERROR`
and sorts to the bottom rather than crashing the whole batch.

## Scanning for new postings

`resume scan` pulls job postings from JobRight (`--source jobright`) and/or
LinkedIn (`--source linkedin`) and writes new ones straight into `jds/` as
JD files, ready for `resume run`/`resume tailor`. No database — dedup is
against `jd_tracker_log.csv` and `jds/` itself (`jd_manager.job_key_known()`),
matched on any of: the posting's source job ID; the same source URL +
company name (guards against a source re-surfacing the same posting under
a new ID); or an exact normalized company name + job title match (catches
the same real job cross-posted on a completely different platform, e.g.
JobRight's aggregated listing and a separate LinkedIn scrape of the same
opening — these share no ID or URL in common at all, so only
company+title can catch them). The interactive menu's "Scan for New
Postings" asks the same question (JobRight only / LinkedIn only / Both),
defaulting to Both.

**Careful with `resume run` after a scan** — batch mode processes every
pending JD in `jds/`, so a scan that turns up dozens of postings means a
real, uninterrupted batch of resume builds (real Gemini spend) if you run
it right after. `resume evaluate` each one first, or thin the pile, before
batch-running — or use `resume run --pick` instead (below).

## Picking which JDs to tailor

`resume run --pick` is the middle ground between "tailor everything" and
"tailor one named file": it evaluates every pending JD (same confirmation
gate and real per-JD Gemini cost as batch `resume evaluate`, and `--yes`
skips the prompt the same way), then shows an interactive checkbox list —
sorted best-fit-first, each line reading `score/5 | recommendation |
company | title` — for you to arrow through and select from. Space toggles
a selection, enter confirms. Only the JD(s) you actually check get tailored
(one at a time, through the normal pipeline); selecting nothing exits
cleanly with no builds run. `resume run` (no `--pick`) is unaffected —
still processes every pending JD, same as always.

`resume coverletter --pick` is the exact same mechanism applied to cover
letters instead of resumes: same confirmation gate, same scored/sorted
checkbox list, same `--yes` — but generates a cover letter for each
selected JD instead of tailoring a resume. `resume coverletter <file>`
(a named file, no `--pick`) is unaffected — still generates a cover letter
for just that one JD, same as always. Passing both a file and `--pick`
(or neither) is a usage error rather than an ambiguous default.

## Checking posting liveness

`resume liveness` checks every pending JD's posting URL (`source_url`,
already present on anything `resume scan` wrote) via a headless Playwright
check ported from career-ops — deterministic HTTP-status/regex/DOM
classification, no LLM calls, no database. Each JD classifies as `active`,
`likely_active`, `expired`, or `uncertain`:

- **`expired`** JDs move automatically to `jds/expired/` (same pattern as
  `jds/completed/`), so `resume run`/`resume tailor` never wastes real
  Gemini spend tailoring a resume for a dead posting.
- **`uncertain`/`likely_active`** stay in the pending queue — only a
  confident `expired` signal moves anything. Both get flagged in the
  printed summary so you can eyeball them yourself.
- JDs without a `source_url` (e.g. manually-dropped plain-text JDs) are
  silently skipped, not flagged as anything.

This is a separate, explicit command — never auto-wired into
`scan`/`run`/`tailor`, since a real browser check per JD takes a few
seconds each and this is meant to run on your own schedule, not silently
add latency to a batch build.

## Generating cover letters

`resume coverletter <jd_file>` generates and renders a first-person cover
letter PDF for a single JD — a fully separate, opt-in command, never
auto-triggered by `resume tailor`/`resume run` (plenty of real postings
don't accept a cover letter at all). Output lands in the same
`output/json/`, `output/html/`, `output/pdf/` folders as resumes, with a
`_coverletter` filename suffix.

A lightweight validator checks the result (forbidden phrases reused from
the resume pipeline's own list, paragraph count, accidental third-person
slips) with one automatic retry on violations before the PDF renders.

**Signature image:** the template references
`docs/MorganEscottSignature2025.png` for a handwritten-style signature
under the sign-off. If that file doesn't exist yet, the PDF still renders
fine — you'll just see a blank space where the image would go until you
drop a real signature file at that path.

## Polishing a resume or cover letter

`resume polish [file]` opens an interactive terminal chat against an
already-generated resume or cover letter's JSON — for the small personal
touch-ups that don't warrant a full re-tailor. Type a plain-English
request ("make the tagline punchier," "drop the second Treering bullet"),
and each turn works like this:

1. Gemini returns the complete updated document (same schema/model the
   builder already uses — no separate chat-history plumbing, since the
   JSON file itself already encodes every previously-accepted edit).
2. A field-level diff is shown — exactly what changed, nothing hidden.
3. You accept (saves the JSON, re-renders HTML, regenerates the PDF),
   reject (discard, rephrase and try again), or quit.

No file argument launches a picker over `output/json/*.json` (newest
first); passing a path skips straight to that file. Type `done`, `exit`,
or an empty line (or Ctrl-D/Ctrl-C) to leave the chat cleanly at any
point.

## Company research

Both `resume coverletter` and `resume tailor`/`run` automatically attempt
a company-research step before writing anything, **when a JD carries a
`company_website` field** (JobRight-scanned JDs have this; most
LinkedIn-scanned ones don't). No CLI flag needed — it's fully automatic
and gracefully skips (with a printed notice, never a crash) when there's
no known website, the site's pages are unreachable, or there isn't enough
usable content:

- A plain Python scraper (`requests`/BeautifulSoup, no browser, no search
  API) fetches the company's About/Mission/Careers pages.
- One Gemini call extracts tone signals (register, formality, recurring
  brand words) and 2-3 factual, traceable statements about the company.
- The **cover letter** uses this for its "Company Connection" paragraph
  and tone-matching, instead of generic flattery.
- The **resume** uses it to tone-match the Summary and (when present) Why
  section — completing instructions that were already written into the
  tailoring prompt but had nothing feeding them before this existed. When
  no research is available, tone-mirroring is skipped entirely and the Why
  section is omitted rather than inventing research-sounding content.

## Situational/optional work history entries

Rare and automatic: `resume tailor`/`run` runs a deterministic keyword
scan against the JD text for 6 of Morgan's other real roles (Humane
Society of Greater Kansas City, Unisource Document Products, Kansas
Colloquies, KU Payroll Office, DeJoy Knauff & Blood, USitek). If a JD's
language specifically matches one (e.g. "animal welfare" for the Humane
Society role), the builder is *offered* the option — not forced — to
include a small, 2-bullet supporting entry alongside the usual six roles.
This should be rare by construction: clearing the keyword gate doesn't
mean it gets used, and for most JDs nothing changes at all. No CLI flag —
this is always on, and inert unless a JD's language genuinely triggers it.

## Voice, distinctiveness & the holistic critique

Every `resume tailor`/`run` build runs a holistic critique after the
resume is drafted (scores, flags, and actionable recommendations against
the JD). Two things happen with that critique's output beyond the score:

- It identifies **distinctive moments** (2-3 sentences already in the
  resume that read as memorable rather than generic) and **flat sections**
  (parts that read competent but interchangeable with any other
  candidate's), printed alongside the usual scores/flags. Distinctive
  moments are then protected verbatim through the automatic
  recommendation-apply pass that follows — an edit can't accidentally
  flatten the one line that actually sounds like you.
- A recommendation phrased as a reflective question about personal
  motivation ("what made this project satisfying to you?") only gets
  auto-applied if the answer is already grounded in your verified
  background — never invented. Otherwise it's printed under "Needs your
  input" as a good candidate for a `resume polish` session instead.

This calibration draws on a small curated voice reference
(`resume-engine/knowledge_base/voice-anchors.md`, generated from real past
application answers via `scripts/build_voice_anchors.py`) that both the
per-bullet audit step and cover-letter generation see, plus Morgan's own
established writing-style rubric folded directly into `style_rules.yaml`
and `critique_resume.md`. Cover letters also now see `evidence-guide.csv`
(thematic career-proof clusters), which previously only reached full
resume builds.

## Tracking applications

Every completed build appends a row to two places: `jds/jd_tracker_log.csv`
(machine-readable, drives dedup/resume logic) and `data/applications.md`
(career-ops's markdown-table format — `# | Date | Company | Role | Score |
Status | PDF | Link | Report | Notes` — for human review). Both are
gitignored. **`Link` is a clickable `[Apply](source_url)`** — the actual
posting, so you have somewhere to go apply once a resume's built.
`Score`/`Report` are still placeholders until an evaluate/scan result is
wired into a given row (a JD's own persisted `_evaluation`, see
"Evaluating fit" above, isn't currently threaded into this specific file).

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

The full `scan` → `liveness` → `evaluate` → `tailor`/`coverletter` →
`render` → `track` pipeline is built, including company research, the
(rare, automatic) situational work-history entries, the interactive
menu's pipeline-ordered chain flow, `resume polish`, and (as of
2026-07-07) the holistic critique's distinctiveness signals plus Phase 1
of the evidence-bank extension (voice anchors, a trimmed detective-findings
companion file, and cover letters gaining `evidence-guide.csv`). Also as
of 2026-07-07: the interactive menu's console output is quieter (the
trim-loop's PDF block and the keyword-extraction dump no longer repeat in
full every step) and its colors are theme-safe (see "Colors" above), and
"Customize Resume for a Specific JD" only surfaces already-evaluated,
scored, sorted JDs instead of an unfiltered list of everything pending.
Further feature ideas (multi-user support, a scheduler, the full
multi-type evidence-bank generalization, a long-term merge with sibling
projects) are tracked in `IDEAS.md`, organized by difficulty/scope.
Nothing there is scheduled.

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
