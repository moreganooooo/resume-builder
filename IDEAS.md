# Ideas & Future Features

A running backlog of things worth building eventually. Nothing here is scheduled --
pull an item into a real plan (see `docs/superpowers/plans/`) when it's time to build it.

Organized by difficulty/scope, easiest first, so it's easy to see what's a
quick win vs. what needs its own planning session before touching code.

- **Easy** -- small, mechanical, no open design questions.
- **Medium** -- real engineering work across a few files, but the design
  questions are answerable/scoped, not open-ended.
- **Hard** -- has at least one genuine open design question (not just
  engineering) that needs a brainstorming pass before building.
- **Very Hard / Long-term** -- big, cross-cutting, multi-session efforts;
  no design work has started on any of these yet.

## Easy

### Minor/nice-to-have

- The Johnson County Community College education line currently wraps to a
  2nd line at the real printed page width (KU/KCKCC don't anymore, after
  shortening their degree names) -- low priority, not something Morgan has
  flagged as a problem.

## Medium

### Cover letter generation

**Scope note:** the template already exists fully built; this is mostly
"build the missing plumbing" (a prompt, a render function, an orchestrator
hook) rather than open design work. The one piece that pushes toward the
harder end is the company-research step (see below) -- worth doing the
letter without it first, then layering research in.

Generate a matching cover letter alongside the resume, using the same JD input.

**Why it should be simpler than the resume pipeline:** no page-fit trimming loop,
no per-role bullet allocation, no skills-line-wrap validation, no opening-verb
uniqueness constraint. Mostly: a personalized greeting, 2-3 body paragraphs
tying specific JD/company facts to Morgan's background, and a sign-off.

**What exists already:**
- `resume-engine/templates/coverletter-template.html` -- a full template with
  `{{DATE}}`, `{{RECIPIENT_BLOCK}}`, `{{GREETING}}`, `{{BODY_PARAGRAPHS}}`,
  `{{SIGN_OFF}}`, `{{TYPED_NAME}}`, `{{TYPED_CONTACT}}` placeholders -- but it's
  not wired to anything yet (no script fills it, nothing in `orchestrator.py`
  calls it).
- The existing "Why [Company]?" section in `tailor_resume.md` is first-person,
  company-specific narrative writing -- structurally close to what a cover
  letter body needs, and a reasonable seed/reference for its prompt rules.

**What it would take:**
- A prompt (`resume-engine/prompts/tailor_coverletter.md` or similar) --
  probably reusing JD-derived archetype detection from the resume prompt.
- A render function (new script, or an addition to `render_html.py`) to fill
  `coverletter-template.html` from that output.
- Wiring into `orchestrator.py` -- likely opt-in per JD run rather than
  always-on.
- A lighter validator, if any -- note pronoun rules invert here (cover
  letters are first-person throughout, unlike the resume).
- Confirm `docs/MorganEscottSignature2025.png` (referenced by the template)
  exists and is current.
- A company-research step feeding the prompt (see below) -- this specific
  piece is closer to Hard than Medium; see the architecture-mismatch note.

**Company research -- what career-ops (`/Users/morganescott/career-ops`) does,
and an important architecture mismatch:**

career-ops has no separate "research a company" script/API call. Company
research is done entirely by a live Claude Code agent using its `WebFetch`/
`WebSearch` tools, directed by plain-markdown instructions:
- `career-ops/modes/coverletter.md`, Phase 2 ("Research Before Writing",
  ~lines 53-86): "Do not write a single sentence until the company and role
  have been researched" -- WebFetch the About/mission/values/careers pages,
  cross-reference against `_profile.md`.
- `career-ops/modes/pdf.md`'s "Company Research Rule" (~lines 502-528) does
  the same for resumes: WebFetch `/about`, `/mission`, `/values`, `/careers`,
  etc., falling back to `WebSearch("[company] mission values culture")` if
  those pages are thin.
- `career-ops/modes/deep.md` is a different, standalone mode -- it doesn't
  research anything itself, it *generates a research prompt* meant to be
  pasted into Perplexity/ChatGPT/another assistant. Not really the thing to
  port for automatic per-JD research.

**The mismatch:** all of this assumes an interactive agent session with live
web-browsing tools available mid-conversation. resume-builder's pipeline is
the opposite shape -- `orchestrator.py` calls the Gemini API directly as a
headless script (no tool-use loop, no live web access). So the mode files
aren't directly portable as-is; either (a) add an actual web-fetch step in
Python (`requests`/`BeautifulSoup` against the company's About/careers page)
before building the prompt, feeding the scraped text in as context, or (b)
run this specific step through an agentic session instead of the Gemini-API
script. Worth deciding which before building.

**Cover letter's tone-matching rule** (career-ops `modes/coverletter.md`,
"Rule 4 -- Match the company's register," ~lines 173-198) is a good, already-
written blueprint either way: "mission-driven org -> warmer, more resonant;
playful startup -> sharper, slightly more personality; conventional B2B SaaS
-> measured, crisp, lightly distinctive." Plus a "Company Connection"
paragraph that ties one specific researched fact to Morgan's history,
explicitly guarding against fake flattery.

### Company-values/terminology mirroring in the resume itself (later, after cover letters)

**Scope note:** depends on the cover letter's company-research step existing
first (same architecture-mismatch question applies here too). Once that's
solved, this part itself is close to Easy -- career-ops already has a
working, narrowly-scoped blueprint to port almost as-is.

Once cover-letter company research exists, reuse it to also tone-match the
resume's Summary and (when present) Why section to the target company's
voice -- not just the JD's literal keywords, which the pipeline already
mirrors.

career-ops already does exactly this in `modes/pdf.md` (~lines 502-528),
scoped narrowly on purpose: "tone mirroring applies ONLY to Summary (tone
and word choice, not facts) and the Why section (framing and register).
Never to job titles, dates, bullet achievements, or skills." It maps signals
like formal-vs-conversational register, "we" vs "you" framing, and 1-2
recurring brand words, to be echoed "naturally... where genuinely
applicable" -- explicitly never copying phrases verbatim. That scoping (and
the "never touches facts" boundary) is worth carrying over as-is; it's a
good, already-tested guardrail against tone-matching sliding into
misrepresentation.

## Hard

### Situational/optional work history entries

**Scope note:** the wiring itself (new `fixed_content.py` entries, a new
prompt section) is Easy -- mechanically identical to the existing six roles.
What makes this Hard is a real, unresolved design question: the 2-page
budget is already tight, so adding a 7th role almost certainly means
deciding which of the existing six to bump, per situation -- that's a
judgment call, not a data-entry task, and needs its own brainstorming pass
before building.

Let the builder swap in one of Morgan's other real roles when a JD is
specifically relevant to it, instead of always using the same fixed six
(Mercor, Treering, Inside Sales Team, Element 8/Strategy LLC, VML, Callahan
Creek). Examples raised: Humane Society of Greater Kansas City (animal
welfare roles), Unisource Document Products (print production), Kansas
Colloquies/The Chieftain (journalism), KU Payroll Office and DeJoy Knauff &
Blood (payroll/tax/clerical/sensitive-info roles), USitek (clerical +
graphic design blend). Rare, deliberate use only -- not a default behavior.

**Good news:** verified bullet content for all of these already exists in
`resume-engine/knowledge_base/bullet-bank-clean.csv` (worth double-checking
completeness/dates per company before building, but this isn't a
from-scratch content-gathering project).

**What it would take -- the wiring is straightforward, the judgment calls are not:**
- `fixed_content.py` needs `COMPANY_META` / `COMPANY_TITLE_DESCRIPTOR` (etc.)
  entries for each optional company -- mechanically identical to the existing
  six.
- `tailor_resume.md` needs a new section spelling out each optional role, its
  trigger condition (what makes a JD relevant to it), and explicit guardrails
  ("only when clearly helpful, essentially never for most JDs").
- **The real design question:** the 2-page budget is already tight with six
  roles and per-role bullet-count floors ("never drop Element 8/VML/Callahan
  Creek below 3 bullets", etc.). Including a 7th role almost certainly means
  *swapping it in for* one of the existing six for that run, not just adding
  it on top -- which means deciding, per archetype/trigger, which of the six
  is safe to bump. That's a real design conversation, not just a data-entry
  task -- worth a proper brainstorming/planning pass before building.
- Possibly worth a deterministic keyword pre-check in `orchestrator.py`
  (scan the JD for trigger terms per optional company) rather than relying
  purely on the LLM's own judgment call, so triggering is testable.

## Very Hard / Long-term

### Long-term: merge with career-ops and job_automater

**Scope note:** the biggest item on this list. Spans three separate
codebases (this project plus two mature sibling projects), one of which
(job_automater) is currently in a partially broken state and being
repaired independently. No merge design has started -- this section is
pure scope-awareness/reference material for when that conversation happens,
not something to pick up casually.

The eventual goal is a single system, with resume-builder replacing the
resume-generation features of both `/Users/morganescott/career-ops` and
`/Users/morganescott/job_automater`. Rough shape as of 2026-07-03:

- **From career-ops** ("the glue"): the dashboard, application tracker
  (markdown/YAML, treated as the source of truth), and the multi-agent
  "mode" pipeline (job-board scanning via `providers/`, JD-fit evaluation,
  tracker updates) -- see the cover-letter section above for what it does
  for company research/tone-matching specifically.
- **From job_automater**, five pieces Morgan wants to keep (findings below;
  concrete file paths so this doesn't need re-researching later):
  - **CLI** -- `cli.py`, a Click-based `job-agent`-style command group:
    `fetch-jobs`, `list-jobs`, `generate-docs`, `apply`, `status`, `setup`,
    `validate-config`/`config`, `config-info`, `interactive`.
  - **"Doctor" script** -- there's no single file literally named "doctor";
    it's really two complementary pieces, confirmed against a fresh,
    complete copy of the repo (Morgan re-downloaded the ZIP to
    `/Users/morganescott/Downloads/job_automater-main` on 2026-07-03, since
    her working copy at `/Users/morganescott/job_automater` looks to have
    lost some files in a GitHub sync -- see below): `system_checker.py`
    (checks *system* dependencies -- Python version, MongoDB, pdflatex, pip
    -- run via the `setup` command through `setup_wizard.py`) and
    `config_validator.py` (checks *config values* -- API keys, contact
    fields, address, LinkedIn URL, work-auth fields -- exposed via
    `validate-config`/`config`). Together those two are the real doctor
    equivalent. (`check-all.py`/`check-db.py` are separate, thinner,
    Mongo-only checkers, present in the working copy but not the fresh ZIP --
    likely local-only scripts Morgan added herself.)
  - **Interview setup** -- confirmed again against the fresh ZIP: **doesn't
    exist in job_automater**, not even a partial version. The likely source
    of the mix-up: `RESEARCH_FINDINGS_COMPETITORS.md` (a competitive-analysis
    doc in the repo) lists "Interview scheduler" as a low-priority,
    not-yet-built roadmap idea and notes competitors having "mock interview
    prep" -- that's probably what got remembered as an existing feature.
    career-ops's `modes/interview-prep.md` (Glassdoor-query-based interview
    intel) is the thing that's actually built and worth porting instead.
  - **Jobright scraping** -- `scrapers/jobright_scraper.py`. Plain REST API
    calls (no browser automation) against a configurable base URL,
    cookie-authenticated, paginated, filters out anything below a 70 match
    score, writes to MongoDB + a JSON backup file.
  - **LinkedIn scraping** -- `scrapers/linkedin_scraper.py`. Browser
    automation via the `linkedin_jobs_scraper` package (Selenium under the
    hood) using hardcoded search queries, plus a supplementary authenticated
    `requests`/BeautifulSoup pass to detect "Top Applicant" badges. Same
    Mongo + JSON-backup output pattern as Jobright.

  **Security flag, found during this research, not yet fixed:**
  `scrapers/recommended_scraper.py` (present in the working copy) has a
  **LinkedIn `li_at` session cookie hardcoded in plaintext**. Checked the
  fresh ZIP re-download: this file **isn't part of the actual open-source
  project at all** -- the real repo's `scrapers/` only has `__init__.py`,
  `jobright_scraper.py`, and `linkedin_scraper.py` (which correctly sources
  its cookie from `config`, not hardcoded). So this is a local, ad-hoc script
  Morgan or something added to her working copy and never upstream --
  doesn't change the fix (that cookie is still a live credential sitting on
  disk; rotate it and don't carry the file forward), just clarifies it's not
  a public/upstream exposure.

  **Working-copy vs. fresh-ZIP diff, confirmed 2026-07-03:** the fresh
  download at `/Users/morganescott/Downloads/job_automater-main` has several
  files genuinely missing from the working copy at
  `/Users/morganescott/job_automater` -- `config.py`, `main.py`, and the
  `job-agent`/`job-agent-clean` CLI wrapper scripts (thin bash scripts that
  activate the venv and run `cli.py`) all exist in the ZIP but not the
  working copy. This confirms real files were lost, likely during the
  GitHub sync Morgan mentioned -- she's repairing this herself, possibly by
  diffing against the fresh ZIP or the upstream repo
  (https://github.com/bchikara/job_automater) directly.

No merge design work has started; this is scope-awareness for when that
conversation happens, not a plan.

### Multi-user support -- let other people (starting with Dominick) use this

**Scope note:** roughly tied with the merge as the biggest item here.
Splits into a mechanical (if broad) half -- separating engine from
per-user profile data -- and a genuinely unsolved half: designing an
onboarding flow that gets a brand-new user to a usable, trustworthy bullet
bank fast. That second half is a process/UX design problem, not an
engineering one, and needs its own brainstorming pass.

Right now the whole pipeline is Morgan-specific, not just in data but in
structure: `scripts/fixed_content.py` is literally her contact info/company
facts/certifications/education as Python constants, and
`resume-engine/prompts/tailor_resume.md` + `resume-engine/rules/*.yaml` are
written assuming her specific companies, roles, and voice. Making this
usable by someone else is really two separate problems:

**1. Generalizing the engine.** Splitting "engine" (generic pipeline logic)
from "profile" (a per-user directory holding their own fixed-content
equivalent, bullet bank, and knowledge base) so a second person's data
doesn't live inside Morgan's files. Mechanical but broad -- touches most of
`scripts/` and `resume-engine/`.

**2. The harder problem Morgan actually asked about: how does a new user
build their own bullet bank in the first place**, when they don't have
100+ audited variations sitting around already? Options raised: a guided
interview/Q&A process, a profile file/form to fill out, a LinkedIn data
export, or sharing project write-ups directly.

Checked what's already reusable vs. what's a real gap:
- **Already built and reusable:** the audit/critique/scoring machinery
  (`resume-engine/prompts/critique_bullet.md`, `rules/truthfulness_rules.yaml`,
  `rules/language_quality.yaml`, `rules/verb_taxonomy.yaml`, etc.) already
  takes a rough, self-written bullet and scores it for credibility, banned
  language, vague verbs, and believability, then proposes a rewrite. That's
  exactly the "polish a new user's rough draft into a verified bullet" step
  -- and it's the same machinery already battle-tested on Morgan's own
  material (`bullet-bank-audited.csv` etc. show a lot of iteration through
  it).
- **Not built yet, a real gap:** nothing today turns raw source material --
  a LinkedIn export, an old resume, project write-ups, or an interview
  transcript -- into first-*draft* bullets in the first place.
  `extract_evidence.md` (despite the name) deconstructs an *existing*
  bullet to check its credibility; it doesn't generate new ones from raw
  material. That initial extraction step is the thing to actually design/build.
- **The genuinely hard part isn't mechanical.** This whole system's identity
  is "never fabricate, everything traceable to real verified history."
  Morgan's bullet bank got that grounding from years of lived history plus a
  lot of manual auditing across many CSV iterations. A new user's onboarding
  flow has to front-load that same rigor in far less time -- that's a
  process/UX design question (how much interview depth is enough?) more than
  an engineering one, and probably deserves its own brainstorming pass
  before building anything.

**Refined onboarding idea (2026-07-03): light seed + grow-as-you-go, not a
big upfront audit.** Morgan's proposal: a new user doesn't need 1,000+
pre-audited bullets -- just one existing resume, a filled-out profile/a few
Q&A answers, maybe a LinkedIn PDF export and a couple project docs, as a
*seed*. The bullet bank then grows naturally over real usage, as the builder
rewrites/expands that seed material differently per JD.

This is sound, but it changes *where* the truthfulness verification happens,
which is worth being explicit about rather than assuming it's free:
- Today, verification is front-loaded -- the bullet bank is pre-audited once,
  and the per-JD builder is bounded to rephrasing/selecting from an
  already-trusted pool (never fabricate is enforceable because the pool
  itself was vetted first).
- In the light-seed model, verification has to move to *per-run human
  review* instead -- the user reviews/approves each newly generated resume
  (as they naturally would anyway), and that approval is what confirms a
  newly expanded or reworded bullet didn't drift into embellishment. That's
  a perfectly reasonable trade (arguably closer to how a human resume writer
  actually works with a new client), just a different mechanism than what
  this codebase currently has -- the "never invent a metric that wasn't in
  the source material" guardrails need to hold during that expansion step,
  not just during selection.
- **Correction (2026-07-03):** the harvest-back loop already exists --
  I'd said it didn't and Morgan caught it. `scripts/bullet_feedback.py`,
  wired into `orchestrator.py`'s bullet-audit step (~line 1206), already
  queues any accepted bullet rewrite that clears the bank's real "KEEP" bar
  (`decide_action() == KEEP` and `manager_test == PASS`) into
  `needs-review.csv` automatically, during every resume build. A separate
  pass, `scripts/triage_needs_review.py`, then routes those queued rows: PASS
  + believability >=80 -> `bullet-bank-keepers.csv` (permanent); FAIL with
  attempts left -> `rewrite-queue.csv`; FAIL, out of attempts ->
  `retired-bullets.csv`. So "grows over time" is already real for Morgan's
  own bank today -- the multi-user version of this is "make this per-user
  scoped" (each user's own needs-review/keepers/retired CSVs), not "invent it
  from scratch." Also worth noting: promotion into the permanent keeper bank
  isn't fully automatic -- `triage_needs_review.py` is a separate run, which
  is itself a nice built-in curation checkpoint, and maps well onto the
  "verification moves to human review" idea above.
- Expect the first few resumes for a brand-new user to be thinner/less
  specific than what Morgan gets today, simply because there's less pool to
  draw from yet -- that's an inherent, expected bootstrapping curve, not a
  bug to fix.

No design work has started; this is scope-awareness for a future
conversation, not a plan.
