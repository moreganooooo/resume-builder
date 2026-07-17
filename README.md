# resume-builder

### A job-search system that actually reads the room.

Not a "type in your job title, get a resume" toy. This is a full pipeline —
**scan** postings, **check** they're still real, **score** your actual fit,
**tailor** a resume (and cover letter) in your own voice, **render** it to a
punishingly ATS-clean PDF, and **track** where you sent it — built because I
was tired of every AI resume tool doing exactly one of those steps badly and
calling it a product.

Everything it writes comes from a verified bank of things you've actually
done. It will never invent a metric. It will never call you a
"results-driven self-starter" (that phrase is *hard-banned*, along with
about 30 of its cousins — see [`style_rules.yaml`](resume-engine/rules/style_rules.yaml)
if you don't believe me). And it argues with itself before it lets a single
sentence out the door: an LLM drafts, a different pass audits it for
truthfulness, and deterministic Python checks the parts that shouldn't be
left to a language model's judgment at all — page count, line wrapping,
whether two bullets accidentally open with the same verb.

Want to see what actually comes out the other end? [`resume_example.pdf`](resume_example.pdf)
is a real sample, not a mockup.

## Why this exists

Job searching is a numbers game dressed up as a writing exercise. You don't
need one perfect resume — you need *this specific role* to see the version
of you that speaks to it, without you rewriting your whole history by hand
fifty times, and without a chatbot quietly making things up to sound
impressive. So I built the thing I actually wanted: a system that knows the
difference between "tailored" and "fabricated," and treats that line as
load-bearing.

## What makes this different

- **It cannot lie about you, structurally.** Every bullet the builder is
  allowed to use lives in an audited bank (`bullet-bank-keepers-audited.csv`)
  that's already been scored for truthfulness, banned language, and vague
  verbs *before* a single job description ever sees it. The per-JD builder
  can rephrase and select — it can't invent. Numbers are checked against
  `verified_metrics.json`; a claim with no receipts doesn't make the cut.
- **It's a pipeline, not a one-shot generator.** `scan` pulls in real
  postings (JobRight, LinkedIn), `liveness` confirms they're still open,
  `evaluate` scores your actual fit against a 10-dimension weighted rubric
  *before* you spend a build on it, `tailor`/`coverletter` write the
  documents, `render` turns them into PDFs, `track` logs the whole thing.
  Most tools stop at step 4 and call it done.
- **It reads the company, not just the job title.** When a posting carries
  a company website, a research pass reads their About/Mission/Careers
  pages and tone-matches your Summary and "Why" section to their actual
  register — mission-driven org gets warmer, sharp B2B SaaS gets crisper —
  never fabricated, and skipped entirely (not faked) when there's nothing
  real to draw from.
- **It protects the sentences that sound like you.** A holistic critique
  pass after every build flags *distinctive moments* (the lines that read
  as unmistakably you) versus *flat sections* (competent but interchangeable
  with anyone else's resume) — and the automatic edit pass is forbidden from
  touching the distinctive ones. Nothing here optimizes you into beige.
- **It gets smarter about you over time.** Every accepted rewrite during a
  real build gets queued back into the bullet bank's review pipeline
  automatically. Your bank isn't a static file you filled out once — it
  compounds.
- **It knows when to break its own pattern.** A deterministic keyword gate
  + LLM judgment call can surface one of your other real roles (the ones
  that don't make the default cut) when — and only when — a posting is
  specifically relevant to it. Rare, on purpose, and logged every time it
  fires so "rare" stays a checkable fact, not a hope.
- **It respects your rate limit and your time.** Batch evaluation paces
  itself under your API tier's requests-per-minute cap instead of faceplanting
  into a wall of 429s, and skips anything already scored by default so you
  never pay twice for the same answer.
- **Your data stays yours.** No cloud database, no vendor lock-in — CSVs and
  JSON on your own disk, gitignored where it matters. Open a text editor and
  you can read every row of your own application history.
- **It fixed a bug most tools don't even know they have.** Chromium's
  print-to-PDF path can silently scramble a PDF's underlying text layer —
  looks perfect on screen, reads backwards to an ATS parser or a copy-paste.
  Fixed at the font level (see [Fonts](#fonts) below) so it never happens
  quietly.

## The pipeline

```
   scan            liveness          evaluate           tailor / render          track
┌─────────┐     ┌───────────┐     ┌───────────┐     ┌──────────────────┐     ┌──────────┐
│ JobRight│ ──▶ │  is this  │ ──▶ │ score fit │ ──▶ │  write it in     │ ──▶ │  log the │
│ LinkedIn│     │ posting   │     │ against a │     │  YOUR voice from │     │  build,  │
│         │     │ still     │     │ 10-dim    │     │  a verified bank,│     │  link the│
│         │     │ live?     │     │ rubric    │     │  render clean PDF│     │  posting │
└─────────┘     └───────────┘     └───────────┘     └──────────────────┘     └──────────┘
```

Every stage runs standalone or chained through the interactive menu — see
below. Nothing auto-triggers the next stage without you choosing it.

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

Source `scripts/resume-cli.sh` from your shell profile (`~/.zshrc` or
`~/.bashrc` both work) to get a `resume` command usable from any directory,
with the venv handled automatically:

```bash
source /path/to/resume-builder/scripts/resume-cli.sh
```

## Take it for a spin

The fastest way in is the interactive menu — just run:

```bash
resume
```

That opens a block-letter title screen (diagonal blue-to-purple gradient,
because why not) with a live stats line and a rotating tip, then an
arrow-key menu grouped by pipeline stage: Discovery, Evaluation, Build,
Utility. Every option maps to a CLI command underneath — the menu is just
a friendlier way in, never a different code path.

Prefer the command line directly? Drop a job description into `jds/` and:

```bash
resume evaluate jds/some_role.txt   # is this even worth building for?
resume run jds/some_role.txt        # tailor + render a resume
resume coverletter jds/some_role.txt # tailor + render a cover letter
```

## CLI reference

`scripts/cli.py` is the actual command surface (Click-based); the `resume`
shell shortcuts are thin wrappers around it plus a couple of extras
(`activate`, `cd`, `test`) — both always in sync, since the shortcuts just
call `python scripts/cli.py <command>` underneath.

| Command | What it does |
|---|---|
| `resume` (no arguments) | launch the interactive menu |
| `resume run` | tailor + render every pending JD in `jds/` (batch mode), splitting any multi-job export into per-job files first |
| `resume run jds/some_file.txt` | tailor + render one specific JD file |
| `resume run --pick` | evaluate everything pending, then check off which ones to actually build |
| `resume coverletter jds/some_file.txt` | generate + render a cover letter for one JD |
| `resume coverletter --pick` | same evaluate-then-checkbox flow, for cover letters |
| `resume polish` | interactively chat-edit an already-generated resume or cover letter |
| `resume polish output/json/some_file_Resume.json` | polish that specific file directly, skipping the picker |
| `resume evaluate jds/some_file.txt` | score a JD's fit (go/no-go) *without* building a resume |
| `resume evaluate` | score every pending JD at once |
| `resume scan` | pull new postings from every configured source (JobRight, LinkedIn) into `jds/`, deduped against history |
| `resume scan --source jobright` | pull from just one source (repeatable flag) |
| `resume liveness` | check every pending JD's posting URL, moving confirmed-expired ones to `jds/expired/` |
| `resume activate` | cd into the project and activate `.venv/` in your current shell — stays active |
| `resume cd` | cd into the project, no venv activation |
| `resume test` | run the full test suite (compact: dots + summary, no app-log noise) |
| `resume test -v` | same, but lists every test by name |
| `resume test -vv` | same, but shows the app's own operational logging too |
| `resume help` | print this list of commands (no menu launch) |

Running `python scripts/cli.py <command>` directly works the same way
(venv activated first) if you'd rather skip the shell shortcuts.
`python scripts/orchestrator.py` (no args, or with a JD file) is the
underlying batch/single-file pipeline `cli.py run`/`cli.py tailor` call —
still works standalone if you want to bypass the CLI skin entirely.
Completed JDs move to `jds/completed/`; expired ones move to
`jds/expired/`; interrupted runs resume automatically from
`output/checkpoints/<job_key>.json` instead of restarting from scratch.

## The interactive menu, in more detail

Options are named after the pipeline stage they support — Scan for New
Postings, Check Posting Liveness, Evaluate ALL/a Specific JD, Customize
Resume for ALL/a Specific JD, Write Cover Letter, Polish, View Application
Tracker. **"Customize Resume for a Specific JD" only shows already-evaluated
JDs**, sorted best-fit-first and labeled with a score
(`4.8/5 | Strong pursue | Acme | Content Strategist`) — building a resume
for a role you haven't screened first rarely makes sense, so the picker
just doesn't offer that as an option.

After anything that actually did something, a "What's next?" prompt offers
the natural next pipeline step (Scan → Liveness → Evaluate → Customize →
Cover Letter/Polish), always with "Back to Menu" as an out — nothing chains
automatically without you choosing it. Exit prints a one-line summary of
what happened that session (e.g. "3 resumes tailored · 2 cover letters
written").

Every color and icon is sourced from one place (`scripts/theme.py`) with
explicit hex values rather than named ANSI colors, since named colors get
silently remapped by whatever terminal theme is active. Icons default to
Nerd Font glyphs; set `RESUME_BUILDER_ICONS=unicode` if you don't have one
enabled.

## Evaluating fit

`resume evaluate <jd_file>` scores a JD against a 10-dimension weighted
rubric (CV match, North Star alignment, remote quality, level fit, comp,
growth, time-to-offer, tool relevance, company reputation, cultural
signals) and prints a composite score out of 5, a recommendation (Strong
pursue / Selective pursue / Low-priority pursue / Skip), and hard blockers
if any (e.g. onsite-only) — no resume gets built. The score is saved into
the JD's own file so later steps (like the resume picker above) can sort
and filter by it without spending another API call.

`resume evaluate` (no file) scores everything pending at once, skipping
anything already scored by default so re-runs don't re-spend a call
re-scoring the same JD — `--refresh` forces a full re-check. Calls are
paced to stay under your account's rate limit rather than bursting all at
once and hitting HTTP 429s.

## Scanning for new postings

`resume scan` pulls postings from JobRight and/or LinkedIn straight into
`jds/`, ready to evaluate or tailor. Dedup runs against history on three
signals — the posting's own source ID, a same-URL-plus-company match, or an
exact normalized company+title match — the last one exists specifically to
catch the same real job cross-posted on a completely different platform
(JobRight's aggregated listing vs. a separate LinkedIn scrape), which share
no ID or URL at all.

**Careful running `resume run` right after a scan** — batch mode processes
every pending JD, so a scan that turns up two dozen postings means two
dozen real builds if you fire it off immediately. Evaluate first, or use
`resume run --pick` (below) to choose.

## Picking which JDs to tailor

`resume run --pick` sits between "tailor everything" and "tailor one named
file": it evaluates every pending JD, then shows a scored, sorted,
checkbox-style list to pick from — space toggles, enter confirms, only
what's checked gets built. `resume coverletter --pick` is the same
mechanism for cover letters. Neither one touches `resume run`/
`resume coverletter <file>`'s normal behavior — those still do exactly
what they've always done.

## Checking posting liveness

`resume liveness` runs a headless, deterministic check (no LLM calls) on
every pending JD's posting URL. Confirmed-`expired` postings move
automatically to `jds/expired/`, so you never waste a real API call
tailoring a resume for a dead listing. `uncertain`/`likely_active` stay put
and get flagged in the summary for you to eyeball. This is a separate,
explicit command — it's never silently wired into a batch build, since a
real browser check per posting takes a few seconds each.

## Generating cover letters

`resume coverletter <jd_file>` writes and renders a first-person cover
letter PDF for a single JD — fully opt-in, never auto-triggered by a
resume build, since plenty of postings don't ask for one at all. A
lightweight validator checks the result (banned phrases, paragraph count,
accidental third-person slips) with one automatic retry before the PDF
renders.

**Signature image:** references `docs/MorganEscottSignature2025.png` for a
handwritten-style signature under the sign-off. Missing that file just
means a blank space where the signature goes — the PDF still renders fine.

## Polishing a resume or cover letter

`resume polish [file]` opens an interactive terminal chat against an
already-generated document. Type a plain-English request ("make the
tagline punchier," "drop the second Treering bullet"), and each turn:

1. Sends back the complete updated document (no separate chat-history
   plumbing needed — the JSON file already encodes every prior edit).
2. Shows a field-level diff — exactly what changed, nothing hidden.
3. Lets you accept (saves, re-renders HTML + PDF), reject (rephrase and
   try again), or quit.

No file argument launches a picker over your most recent builds. Type
`done`, `exit`, an empty line, or Ctrl-D/Ctrl-C to leave cleanly at any
point.

## Company research

Both `coverletter` and `tailor`/`run` automatically attempt a
company-research pass whenever a JD carries a `company_website` field — no
flag needed, and it gracefully skips (with a printed notice, never a
crash) when there's no known site or nothing usable to read. A plain
Python scraper (no browser, no search API) pulls the company's About/
Mission/Careers pages; one model call extracts tone signals and a couple
of factual, traceable statements. The cover letter uses this for its
Company Connection paragraph; the resume uses it to tone-match the Summary
and Why section. No research available means no tone-mirroring and no Why
section — never invented content standing in for the real thing.

## Situational work-history entries

Rare and fully automatic: `tailor`/`run` runs a deterministic keyword scan
against the JD for six of my other real roles that don't make the default
cut (animal welfare, print production, journalism, payroll/clerical work,
graphic design). If a JD's language specifically matches one, the builder
is *offered* — never forced — a small, 2-bullet supporting entry alongside
the usual lineup. Clearing the keyword gate doesn't guarantee it gets
used; for most JDs, nothing changes at all. Nothing to configure — always
on, inert until a JD's own language genuinely calls for it.

## Voice, distinctiveness & the holistic critique

Every build runs a holistic critique after the resume is drafted —
scores, flags, actionable recommendations against the JD — plus two
things purpose-built to protect your actual voice:

- It identifies **distinctive moments** (lines that read as unmistakably
  you) and **flat sections** (competent but generic). Distinctive moments
  are protected verbatim through the automatic edit pass that follows — an
  edit can't accidentally flatten the one line that sounds like you.
- A recommendation phrased as a reflective personal question only
  auto-applies if the answer is already grounded in your verified
  background — never invented. Otherwise it surfaces under "Needs your
  input" as a good candidate for a `resume polish` session.

This draws on a small curated voice reference
(`resume-engine/knowledge_base/voice-anchors.md`) built from real past
application answers, plus a full writing-style rubric folded directly into
`style_rules.yaml` — the same rules that ban "results-driven professional"
and friends outright.

## Tracking applications

Every completed build appends a row to `jds/jd_tracker_log.csv`
(machine-readable, drives dedup/resume logic) and `data/applications.md`
(a human-readable markdown table — Date, Company, Role, Score, Status,
PDF, Link, Report, Notes). Both gitignored. `Link` is a clickable
`[Apply](source_url)` straight to the real posting, so there's always
somewhere to go once a resume's built.

## Bullet Bank Management

The menu's "Manage Bullet Bank" entry runs the six-stage curation pipeline
that keeps the underlying bullet bank sharp — audit, cluster/dedupe,
rewrite weak entries, re-audit, score for standout ("hidden gem") material,
and re-embed for runtime matching. A status table (never run / stale / up
to date) is computed straight from each stage's actual output file, so it
never drifts out of sync with reality. Every stage checkpoints and resumes
on its own.

The bank also isn't static day-to-day: every real build queues any
accepted bullet rewrite that clears the bank's quality bar into a review
queue automatically. Run `python scripts/triage_needs_review.py`
periodically to route those into permanent keepers, a rewrite queue, or
retirement — a deliberate manual checkpoint, not a silent auto-merge.

## Fonts

`resume-engine/fonts/DMSans-{Regular,ExtraBold,Italic}-static.ttf` are
fixed (non-variable) instances baked from Google's DM Sans variable font.
Don't swap these back for the raw variable font — Chromium's
print-to-PDF path fragmented it into dozens of near-duplicate embedded
subsets and coincided with a real bug where the PDF's underlying text
layer came out scrambled: visually correct on screen, backwards when
copy-pasted or parsed by an ATS. Static instances sidestep that code path
entirely.

## Roadmap

The full pipeline — scan, liveness, evaluate, tailor/coverletter, render,
track — is built and in daily use, along with company research,
situational work-history entries, the interactive menu, `resume polish`,
and the holistic critique's distinctiveness signals. What's still ahead —
multi-user support, a background scheduler, the full evidence-bank
generalization, a long-term merge with two sibling projects — is tracked
in [`IDEAS.md`](IDEAS.md), organized by difficulty and scope, with full
build history in [`IDEAS_ARCHIVE.md`](IDEAS_ARCHIVE.md). Nothing there is
scheduled; it's a backlog, not a promise.

## Testing

```bash
python -m unittest discover -s tests
```

Stdlib `unittest`, not pytest — discovery picks up every `tests/test_*.py`
file automatically. `resume test` discards the application's own stdout
logging by default so what you see is a clean pass/fail summary, not an
interleaved wall of text (`resume test -v`/`-vv` bring it back if you want
it).
