# Company Research: Tiered Fallback + Vocabulary Mirroring

## Problem

`ResumeEngine.research_company()` returns `None` whenever `company_website`
is absent and cannot be found (`company_research.find_company_website()`
fails), or the site's content is too thin (`< MIN_USEFUL_CHARS`). In
practice this means a large share of JDs — anything sourced from LinkedIn
with no company URL, or a company whose site is thin/unreachable — get zero
tone or values signal today, and `build_tailored_coverletter`/
`build_tailored_resume` proceed exactly as if research were never attempted.

Even when research succeeds, its signal only reaches the Summary's tone
descriptors (`tone_register`, `pronoun_framing`, `jargon_density`,
`recurring_keywords`) and the "Why [Company]?" section's `company_facts`.
It has no concept of a company's *specific* preferred vocabulary (e.g. a
company that calls its customers "guests"), and nothing links that
vocabulary to Work Experience bullets — which are locked in at Step 3,
before `research_company()` ever runs at Step 4.

## Goals

1. `research_company()` produces usable signal for effectively every JD —
   the only remaining `None` path is a JD whose `jd_text` itself is empty
   or unusable (an operational non-occurrence, kept only as a documented
   last resort, not designed around).
2. Research signal captures a company's specific preferred vocabulary
   (e.g. "guests" over "customers"), not just broad tone descriptors.
3. That vocabulary reaches the Summary and Why section (via prompt
   instructions, same mechanism as today's tone-mirroring) **and** Work
   Experience bullets, without an LLM rewording already-audited bullet
   text.

## Non-Goals

- No numeric confidence percentage for the new search tier — categorical
  `high`/`medium`/`low`, consistent with this schema's existing `Literal`
  fields, avoids false precision from an uncalibrated model.
- No change to Step 3's bullet-audit prompt — bullets are audited exactly
  as today (JD-keyword-driven, no company-research context). Vocabulary
  reaches bullets only via a deterministic post-process, never by giving
  the audit/refine model latitude to reword bullets for tone.
- No deterministic vocabulary substitution in the cover letter. Cover
  letters are freeform generated text already covered by the existing
  tone-mirroring instruction; `vocabulary_substitutions` becomes available
  to that prompt for free via the schema change, but no separate
  post-process is added there this pass.
- No expansion of `CANDIDATE_PATHS` or homepage-root fetch in
  `company_research.py` — separable follow-up if Tier 1 coverage proves
  too thin in practice; not required to satisfy Goal 1 since Tiers 2/3
  already guarantee a result.
- No new caching or retry/backoff for the search tier — existing
  `GeminiClient` retry/backoff already covers transient failures.
- No substitution applied to the Skills section — category/tool names are
  precise technical terms, not customer-facing prose.

## Architecture

```
ResumeEngine.research_company(jd_data)
  Tier 1 (existing, unchanged): company_research.fetch_company_pages(company_website)
    scraped_text >= MIN_USEFUL_CHARS
      -> extract_company_research(scraped_text, source_label="website")

  Tier 2 (new, only if Tier 1 unusable):
    company_research.research_company_via_search(company_name, jd_context_hint)
      -> one grounded, schema-less Gemini call (tools=[{"google_search": {}}],
         no response_schema -- same constraint find_company_website already
         respects), returns (confidence, text) or None
      confidence == "high"
        -> extract_company_research(text, source_label="search")
      confidence in ("medium", "low") or call failed
        -> fall through to Tier 3

  Tier 3 (new, always available):
    extract_company_research(jd_text, source_label="jd_text")
      -> only remaining None path: jd_text itself empty/unusable
```

`extract_company_research()` is the existing structured-extraction call
(current `research_company()` body from "call Gemini with
`CompanyResearchSchema`" onward), factored out so all three tiers feed the
same prompt + schema rather than each tier inventing its own extraction
logic. `source_label` is threaded through only for the console notice and
the result dict's `_research_source` key — it does not reach the prompt.

## Components

### `scripts/company_research.py`

- **New `research_company_via_search(company_name: str, context_hint: str = "") -> tuple[str, str] | None`**
  Mirrors `find_company_website()`'s existing pattern: one grounded,
  schema-less Gemini call, `temperature=0.0`, wrapped in a blanket
  `except Exception: return None` (never raises). The prompt asks the
  model to prefix its answer with `CONFIDENCE: high|medium|low` on its own
  line, followed by what it found about the company's tone, values, and
  language, using `context_hint` (the JD's title/industry) to help
  disambiguate same-named companies. A response missing a parseable
  `CONFIDENCE:` prefix is treated as failure (fail closed — never trust
  unlabeled confidence).
  ```python
  _CONFIDENCE_PATTERN = re.compile(r"^\s*CONFIDENCE:\s*(high|medium|low)", re.IGNORECASE)
  ```

- **New `apply_vocabulary_substitutions(text: str, substitutions: list[str]) -> str`**
  Pure function. Each entry in `substitutions` is a `"generic_term ->
  company_term"` string (see schema shape below). For each pair, does a
  case-preserving, word-boundary regex substitution of `generic_term` with
  `company_term` (title-case source match -> title-case replacement,
  all-caps -> all-caps, else replacement used as-given). Skips any pair
  that doesn't split cleanly into two non-empty terms rather than raising.

- **New `apply_vocabulary_substitutions_to_resume(resume_data: dict, substitutions: list[str]) -> dict`**
  Thin wrapper: walks only `work_experience[*].bullets[*]` and applies
  `apply_vocabulary_substitutions` to each bullet string. No-ops
  immediately (returns `resume_data` unchanged) when `substitutions` is
  empty.

### `resume-engine/prompts/research_company.md`

- Generalize the opening framing (currently: "You are extracting tone
  signals and factual highlights from a company's own About/Mission/
  Careers page text...") to cover all three source types: "...from text
  about a company — scraped from their own website, gathered via a web
  search, or drawn directly from a job posting they wrote."
- Add extraction guidance for the new `vocabulary_substitutions` field:
  look for a distinctive, *repeated* preferred term the company uses in
  place of a common noun (e.g. "guests" instead of "customers," "team
  members" instead of "employees"). Only include a pair when the
  substitution is clearly and repeatedly used in the source text — never
  invent one to fill the field. 0-3 pairs, empty list when nothing
  qualifies.
- Add a note for when the source is JD text specifically (Tier 3):
  `company_facts` should restate only what the JD itself already states —
  do not treat this as license to add outside claims the JD didn't make.
- Keep the existing guardrail ("Every `company_facts` entry must be
  grounded in the provided text...") unchanged — it already covers all
  three source types once the framing above is generalized.

### `scripts/orchestrator.py`

- `CompanyResearchSchema` gains:
  ```python
  vocabulary_substitutions: List[str] = Field(
      description="0-3 pairs formatted as 'generic_term -> company_term' "
                  "(e.g. 'customers -> guests'). Only include a pair when "
                  "the source text clearly and repeatedly prefers that term."
  )
  ```
  A flat `List[str]` rather than a nested sub-model, per the existing
  precedent at `scripts/orchestrator.py:73-75` (`TemplateSchema` was
  deliberately de-nested — `List[dict]` instead of `List[NestedModel]` —
  because deeply-nested `$defs` in `responseSchema` caused a 400 from the
  builder model). This extraction call also runs on `BUILDER_MODEL`, so
  the same constraint applies here.
- `research_company()` rewritten to implement the 3-tier flow above. The
  returned dict gains a `_research_source` key (`"website"` / `"search"`
  / `"jd_text"`) — underscore-prefixed per this repo's existing convention
  for internal metadata that must not reach a prompt as content. It is
  popped off before the dict is handed to `format_company_research_block`,
  and used only for the console notice (e.g. "Company research: no site
  found, used web search instead" / "...used the job description text
  instead").
- `format_company_research_block()` gains one more line, printed only
  when `vocabulary_substitutions` is non-empty:
  `Preferred vocabulary (use in place of the generic term wherever natural): customers -> guests`
- New call site in `build_tailored_resume`, immediately after Step 5.5
  (recommendation-apply loop) and before Step 6 (save output):
  ```python
  resume_data = company_research.apply_vocabulary_substitutions_to_resume(
      resume_data, research.get("vocabulary_substitutions", []) if research else []
  )
  ```
  Placed after Step 5.5 specifically so the substitution is immune to any
  earlier step rewording bullet text, and is the very last thing to touch
  bullet content before it's persisted.

### `resume-engine/prompts/tailor_resume.md`

- **Summary Rules (~line 74):** extend the existing tone-mirroring line to
  also reference `vocabulary_substitutions` explicitly, not just the tone
  fields — e.g. "...its `tone_register`/`pronoun_framing`/
  `jargon_density`/`recurring_keywords`/`vocabulary_substitutions` fields
  describe the real signal to match." Drop the "if no such block is
  present, skip tone-mirroring" fallback language — a `=== COMPANY
  RESEARCH ===` block is now always present.
- **Why [Company]? Section (~line 227-228):** same addition —
  `vocabulary_substitutions` called out alongside `company_facts` as
  something the section may draw on, since vocabulary isn't a "fact" and
  could otherwise be read as out of scope for this section.
- **Bullet Rules (near line 111):** add one guardrail line making clear
  that vocabulary mirroring for bullets happens via a separate,
  deterministic post-process outside the model's own writing — the model
  must not reword or paraphrase bullets to match company vocabulary
  itself. This prevents the model from double-guessing bullet text now
  that it can see `vocabulary_substitutions` in context, which could
  otherwise conflict with the deterministic pass or violate the existing
  "bullet bank is LEGO, not prose to rephrase" rule
  (`style_rules.yaml:19`).

## Data Flow

1. `build_tailored_resume` reaches Step 4, calls `research =
   self.research_company(jd_data)` — now always returns a dict (barring
   the JD-text-empty edge case).
2. `research_block = format_company_research_block(research)` — includes
   the new vocabulary line when present — folded into `builder_system`
   exactly as today.
3. Model generates Summary/Why per the updated prompt instructions,
   selects bullets from the bullet bank exactly as today (Step 3's output,
   untouched by research).
4. Step 5 (critique) and Step 5.5 (apply recommendations) run unchanged.
5. Immediately before Step 6's save, `apply_vocabulary_substitutions_to_resume`
   runs once over the final `resume_data`'s bullet text.
6. Step 6/7 (save, render, PDF) proceed unchanged.

## Error Handling

- Tier 2's grounded call raising or returning malformed output is caught
  and treated as a Tier 2 failure -> falls to Tier 3 (mirrors
  `find_company_website`'s existing blanket `except Exception: return
  None`).
- A missing or unparseable `CONFIDENCE:` line is treated as not-high ->
  falls to Tier 3 (fail closed).
- Tier 3's extraction call failing to parse is the one remaining genuine
  `None` from `research_company()` — same failure handling as today
  (`GeminiClient.parse_json` failure), console notice unchanged in spirit.
- `apply_vocabulary_substitutions` skips any pair that doesn't split
  cleanly into two non-empty terms, and skips a pair whose `generic_term`
  regex fails to compile (defensive, since the terms come from a model)
  rather than raising and aborting the save.
- Empty `vocabulary_substitutions` list is a no-op at every layer (schema
  default empty list, block-formatting skips the line, substitution
  wrapper returns `resume_data` unchanged).

## Testing

Unit tests (no network), extending the existing files/conventions:

- `tests/test_company_research.py`:
  - `research_company_via_search`: mocked `GeminiClient.generate` returning
    `CONFIDENCE: high/medium/low/<missing>` prefixes -> only `"high"`
    returns usable `(confidence, text)`; others return `None`. Mirrors
    `test_find_company_website`'s existing mock pattern, including the
    grounding-vs-schema assertion (`tools == [{"google_search": {}}]`,
    `"response_schema" not in kwargs`).
  - `apply_vocabulary_substitutions`: case-preserving substitution
    (capitalized at sentence start, literal plural forms as given in the
    pair), word-boundary correctness (doesn't match inside an unrelated
    word), multiple pairs applied in one string, empty-list no-op,
    malformed pair (no `" -> "` separator) skipped without raising.

- `tests/test_orchestrator_research_company.py`: extend the existing
  `TestResearchCompanyWebsiteFallback` mock-dispatch pattern with:
  - Tier 1 success path unchanged (existing tests keep passing as-is).
  - Tier 1 thin + Tier 2 `"high"` confidence -> Tier 2 path used, result
    tagged `_research_source == "search"`.
  - Tier 1 thin + Tier 2 `"medium"`/`"low"`/failure -> falls to Tier 3,
    result tagged `_research_source == "jd_text"`.
  - Tier 1 and Tier 2 both unusable, non-empty `jd_text` -> Tier 3 still
    produces a non-`None` result (the core "always finds something"
    guarantee).
  - `format_company_research_block` includes the vocabulary line only
    when `vocabulary_substitutions` is non-empty.

Live verification (manual, one `resume tailor` run each):

1. A JD with a known-good `company_website` -> confirm Tier 1 behavior is
   unchanged.
2. A LinkedIn-sourced JD with no `company_website` for a real, findable
   company -> confirm Tier 2 fires and the console notice says so.
3. A JD for an obscure/private company with no meaningful search presence
   -> confirm Tier 3 fires, Summary/Why still read naturally, and
   `company_facts` don't overreach beyond what the JD itself states.
4. Whichever run (if any) surfaces a non-empty `vocabulary_substitutions`
   -> eyeball the affected bullet to confirm only the target noun changed,
   nothing else in the bullet's wording or structure moved.
