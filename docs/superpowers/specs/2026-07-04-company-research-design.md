# Company Research (Cover Letter + Resume Tone-Mirroring) — Design

## Problem

Cover letter generation (built 2026-07-04, see
`2026-07-04-cover-letter-generation-design.md`) deliberately shipped without
company research -- it was sequenced as a second pass. Separately,
`resume-engine/prompts/tailor_resume.md` **already contains instructions that
assume company research exists**, even though no mechanism has ever supplied
it:

- Line 69 (Summary Rules): "Mirror the company's tone (formal vs
  conversational, jargon level, keyword density) -- apply to tone only,
  never to facts."
- Line 203 (Why [Company]? section): "Must reference specific company
  research details and connect each to verified facts from Morgan's
  history."

Without a real research step feeding these instructions, the model has
likely been inferring tone from JD text alone (line 69) and, worse,
potentially fabricating plausible-sounding "company research details" to
satisfy line 203 -- a real grounding gap this feature closes, not just a
nice-to-have addition.

career-ops's own company-research process (`modes/coverletter.md` Phase 2,
`modes/pdf.md`'s Company Research Rule) assumes a live interactive agent
using WebFetch/WebSearch mid-conversation. That doesn't fit this pipeline's
architecture or Morgan's stated goal of keeping Claude's role bounded to
build-time work, not runtime operation -- confirmed 2026-07-04: research
runs as a plain Python scraper feeding the existing headless Gemini
pipeline, the same pattern already proven in `scan_linkedin.py`.

## Goals

1. `ResumeEngine.research_company(jd_data: dict) -> dict | None` fetches a
   company's About/Mission/Careers pages (when a `company_website` is known)
   and extracts tone signals + 2-3 traceable facts via one Gemini call.
2. Wire the result into **both** `build_tailored_coverletter` (Company
   Connection paragraph + Rule 4 tone-matching) and `build_tailored_resume`
   (completes what lines 69/203 already expect) -- confirmed 2026-07-04,
   both in this same pass.
3. Graceful, visible degradation: when no website is known, pages are
   unreachable, or content is too thin, print a clear, non-alarming
   terminal notice and proceed exactly as today -- never block, never
   fabricate to compensate for missing research.
4. Cover letter generation stays a fully separate, opt-in command
   (`resume coverletter <jd_file>`) -- confirmed 2026-07-04, company
   research must never make cover letters an assumed/automatic part of
   `resume tailor`/`resume run`. Many real postings don't accept a cover
   letter at all.

## Non-Goals

- No search-API fallback (Google Custom Search, Bing, etc.) when direct
  page fetches are too thin -- skip gracefully instead. No new paid API
  dependency this pass.
- No interactive/agentic research session -- pure Python scraper + Gemini,
  matching `scan_linkedin.py`'s established pattern.
- No domain-guessing when `company_website` is absent from the JD data
  (e.g. most LinkedIn-sourced JDs, per `scan_linkedin.py`'s current
  `"company_website": None`) -- skip gracefully, don't guess
  `companyname.com`.
- No changes to `build_tailored_resume`'s page-fit trim loop, validator, or
  checkpointing -- company research is an additional context input to the
  existing builder call, not a new pipeline stage.
- No change to cover letter's opt-in status -- it remains a separate CLI
  command, never auto-triggered by `tailor`/`run`.

## Architecture

```
JD file (may have a company_website field, from JobRight scans)
  → ResumeEngine.research_company(jd_data: dict) -> dict | None
      → company_research.fetch_company_pages(company_website) -- requests/
        BeautifulSoup against a fixed list of candidate paths (/about,
        /about-us, /mission, /values, /culture, /team, /careers, /jobs),
        returns combined visible text (capped ~6000 chars), "" if nothing
        useful found
      → no website, or combined text < ~200 chars → print notice, return None
      → else: one Gemini call (new prompt research_company.md) ->
        CompanyResearchSchema (tone/register/framing/jargon signals + 2-3
        traceable company facts)
      → Gemini response fails to parse → print notice, return None

  → build_tailored_coverletter(jd_path): calls research_company() once;
    if present, folds a "=== COMPANY RESEARCH ===" block into
    system_instruction for the Company Connection paragraph + Rule 4
    tone-matching. If None, behaves exactly as it does today (unchanged).

  → build_tailored_resume(jd_path, ...): calls research_company() once
    (new: parses jd_text into jd_data first); if present, folds the same
    "=== COMPANY RESEARCH ===" block into builder_system alongside
    kb_context. If None, tailor_resume.md's updated guardrail (see
    Components below) makes tone-mirroring/Why-section-research a no-op --
    it must never fabricate research-sounding content to fill the gap.
```

## Components

- **`resume-engine/prompts/research_company.md`** (new) -- system prompt
  for extracting structured signals from raw scraped company-page text.
  Explicit rule: `company_facts` must be traceable to the provided text;
  never invent beyond it. Mirrors career-ops's tone/voice-signal table
  (register, we/you framing, sentence length, jargon density, recurring
  keywords, overall tone adjective) from `modes/pdf.md`'s Company Research
  Rule.

- **`CompanyResearchSchema`** (new Pydantic model, alongside the existing
  schemas in `orchestrator.py`):
  ```python
  class CompanyResearchSchema(BaseModel):
      overall_tone_adjective: str
      register:           Literal["formal", "conversational", "mixed"]
      pronoun_framing:    Literal["we-centric", "you-centric", "mixed"]
      sentence_style:     Literal["short and punchy", "long and flowing", "mixed"]
      jargon_density:     Literal["high", "moderate", "low"]
      recurring_keywords: List[str]  # 1-3 genuinely repeated brand words
      company_facts:      List[str]  # 2-3 short, factual, traceable statements
  ```

- **`scripts/company_research.py`** (new) --
  `fetch_company_pages(company_website: str) -> str`: tries the candidate
  paths in order, stops early once combined visible text reaches
  `EARLY_STOP_CHARS = 1500` (enough signal from 2-3 successful pages
  without exhaustively fetching all 8 candidates every time), or once all
  candidates are exhausted. Combined text is capped at
  `MAX_TOTAL_CHARS = 6000` before being returned. Returns `""` if nothing
  useful was found (combined text stays under `MIN_USEFUL_CHARS = 200`,
  the threshold `research_company()` uses to decide "too thin, skip").
  Internal helpers (`_extract_visible_text(html)`,
  `_candidate_urls(company_website)`) are pure and unit-testable without
  network access; `fetch_company_pages` itself is tested with `requests.get`
  mocked (standard, low-risk HTTP mocking -- distinct from mocking an LLM's
  semantic output, which this codebase deliberately avoids elsewhere).

- **`ResumeEngine.research_company(self, jd_data: dict) -> dict | None`**
  (new method) -- orchestrates fetch → Gemini → schema. Prints one of the
  three notices (Goals #3) and returns `None` on any skip/failure path;
  returns the filled `CompanyResearchSchema` dict on success.

- **`resume-engine/prompts/tailor_coverletter.md`** (modify) -- replace the
  current "No company research beyond what's in the job description
  itself..." rule with: use the optional `COMPANY RESEARCH` context block
  when present for the Company Connection paragraph (tie **one** researched
  fact to Morgan's real history, explicit fake-flattery guard) and Rule 4
  tone-matching (mission-driven → warmer, playful startup → sharper, B2B
  SaaS → measured); fall back to today's exact behavior when the block is
  absent.

- **`resume-engine/prompts/tailor_resume.md`** (modify, minimally) -- add
  one clarifying line each to the existing Summary Rules (line 69) and Why
  section (line 203) pointing at the new `COMPANY RESEARCH` block by name,
  plus an explicit no-fabrication guardrail: **if no such block is present,
  skip tone-mirroring entirely and omit company-specific claims from (or
  drop) the Why section** -- never invent research-sounding content to
  satisfy the existing instruction. This is a correctness fix to an
  existing gap, not new behavior invention.

- **`build_tailored_resume`** (modify) -- parse `jd_data` from `jd_text`
  near the existing JD-text read (graceful no-op dict if not JSON), call
  `self.research_company(jd_data)` once, fold the result into
  `builder_system` alongside `kb_context` when present.

- **`build_tailored_coverletter`** (modify) -- same `research_company()`
  call, folded into `system_instruction` when present.

## Data Flow

```
resume coverletter jds/some_jd.json  (or resume tailor / resume run)
  → parse jd_data from the JD file (graceful if not JSON)
  → engine.research_company(jd_data)
      → no company_website → print notice → None
      → fetch_company_pages() → "" (unreachable/thin) → print notice → None
      → fetch succeeds → Gemini call → CompanyResearchSchema dict
      → Gemini fails to parse → print notice → None
  → (coverletter) fold into system_instruction, or proceed unchanged if None
  → (resume) fold into builder_system, or proceed unchanged (no
    fabrication) if None
  → rest of each pipeline continues exactly as it does today
```

## Error Handling

- Every `research_company()` skip path prints a clear, non-alarming notice
  (this is expected/normal for most JDs, not an error state) and returns
  `None` -- never raises, never blocks either caller.
- A `requests` exception (timeout, connection error, non-200 status) during
  `fetch_company_pages` for any single candidate path is caught per-path;
  the function moves on to the next candidate rather than aborting the
  whole fetch.
- `GeminiClient.generate`/`parse_json` failure inside `research_company`
  is treated as a skip (notice + `None`), identical to the thin-content
  path -- callers don't need to distinguish "couldn't fetch" from "couldn't
  extract."

## Testing

- Unit tests (no network, no Gemini): `_extract_visible_text` (strips
  script/style, collapses whitespace, given a fixed HTML string) and
  `_candidate_urls` (builds the expected path list from a base URL,
  including trailing-slash/missing-scheme handling). `fetch_company_pages`
  tested with `requests.get` mocked: confirms it tries multiple candidate
  paths, stops early once enough content is collected, and returns `""`
  when every candidate fails.
- Live verification (real network + real Gemini, matching every other
  integration point built this project):
  1. `resume coverletter` against a real JD with a known `company_website`
     (one of the already-scanned JobRight JDs has one) -- confirm the
     research notice/success prints and the Company Connection paragraph
     references a real, traceable fact.
  2. `resume tailor` on that same JD, and separately on a JD *without* a
     known website (e.g. a LinkedIn-sourced one) -- compare: the first
     should show a subtly tone-adjusted Summary/Why grounded in real
     facts; the second must behave identically to pre-feature output
     (highest-stakes check, since `build_tailored_resume` is the most
     complex, already-proven part of the system).
