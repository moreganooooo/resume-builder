# Cover Letter Header/Address Enrichment

## Problem

The cover letter template supports a title/tagline line and a recipient
block, but neither is populated: `render_coverletter.py` hardcodes
`TAGLINE: ""` and the recipient block is just the bare company name. There's
no structured way to address a named hiring contact, show the company's
location, or open with an impressive, grounded company fact — all things
the candidate does by hand today and wants automated per her own reference
format (a past cover letter that led directly to a "how did you know about
that?" moment with a hiring manager).

## Design

### 1. Title line under name

`render_coverletter.py` reads the matching resume's already-generated
`{stem}_Resume.json` (same stem `_build_output_stem()` already computes,
same `output_json_dir`) and pulls its `TAGLINE` field into the cover
letter's `{{TAGLINE}}` scalar — the same field `cv-template.html` renders
in the identical header slot. Falls back to `""` (today's behavior,
producing no visible tagline line) if no resume JSON exists yet, since
cover letters can be generated standalone.

No new Gemini call — this is a file read.

### 2. Company research: two new fields

`CompanyResearchSchema` (orchestrator.py) gains:

- `company_hq_location: str` — city/state, extracted only if the source
  text states it; `""` otherwise.
- `notable_highlights: List[str]` (0-3) — awards, funding, recognition,
  charitable/community initiatives, notable stats, recent or upcoming
  product launches. Distinct from the existing `company_facts` (which
  serves tone-matching/mission grounding) — this field is specifically the
  "impressive hook" material for a cover letter's opening.

`research_company.md` gets two new numbered extraction rules for these,
under the same discipline as every other field there: only if grounded in
the provided source text, never invented, empty/omitted when not
supported. No new Gemini call — same extraction call, richer schema. This
flows through all three existing tiers (own site, grounded search, JD
text) unchanged, so the existing "always produces something, but only
`company_facts`-style grounding" guarantee extends to these for free.

### 3. Address block resolution — deterministic, not model output

In `build_tailored_coverletter()`:

```python
location = research.get("company_hq_location") if research else ""
if not location:
    location = jd_data.get("location") or ""
```

Shown whenever non-empty — no "remote" filtering. Per the candidate: the
address line is a show of professionalism regardless of whether the role
itself is remote.

### 4. Named contact — JD text only, no web search for a person

`CoverLetterSchema` gains `contact_name: str = ""`, `contact_title: str =
""`. The model extracts these from the JD text as part of the existing
generation call (it already reads the JD for a named hiring manager to
build the greeting — this makes that structured instead of implicit).

Python-side fallback when the model finds nothing: check
`find_jd_contacts(jd_data)` (already-scraped real JobRight/LinkedIn
people — never invented). Pick the first entry whose `title` contains an
HR/recruiting/talent keyword (case-insensitive: "hr", "recruit", "talent",
"people"); if none match, use the first entry in the list. Leave both
fields `""` if that list is also empty.

Explicitly out of scope: a grounded web search to find a contact not named
anywhere. Getting a person's name/title wrong is a worse failure mode than
a wrong company fact (addressing someone who's left, or guessing the wrong
HR contact), and this codebase's existing bias is to skip rather than risk
a specific false claim about a real individual.

### 5. Recipient block becomes up to 3 lines

`render_coverletter.py`'s `build_recipient_block_html()` becomes:

```
Attn: {contact_name}, {contact_title}     ← only if a contact is known
{company_name}
{location}                                ← only if known
```

Line 1 falls back to `"{company_name} Hiring Team"` when no contact is
known, matching the candidate's reference PDF (e.g. "Attentive Hiring
Team" / "Attentive" / "New York, NY").

### 6. `tailor_coverletter.md` prompt updates

- Greeting default changes from `"Dear Hiring Team,"` to `"Dear {company
  name} Hiring Team,"` to match the reference format. Named-contact case
  unchanged (uses the contact's name).
- New instruction to also output `contact_name`/`contact_title` (empty
  strings if the JD doesn't name anyone) — same underlying JD read the
  greeting logic already does, now surfaced as structured fields.
- New instruction: when `notable_highlights` are present in the company
  research context block, open the letter with one as a hook (mirroring
  the candidate's reference example's opening paragraph, which leads with
  Forbes Cloud 100 / Deloitte Fast 500 / G2 ranking / customer count).
  Same "use at most 1-2, never fabricate beyond what's given" discipline
  the existing company-facts rule already uses.

`format_company_research_block()` (orchestrator.py) is extended to include
`notable_highlights` in the formatted context block the same way
`company_facts` already is.

## Files touched

- `scripts/orchestrator.py` — `CompanyResearchSchema`, `CoverLetterSchema`,
  `format_company_research_block()`, `build_tailored_coverletter()`
  (tagline read, location resolution, contact fallback).
- `scripts/render_coverletter.py` — `build_recipient_block_html()`
  signature/logic, tagline threading.
- `resume-engine/prompts/tailor_coverletter.md` — greeting default,
  `contact_name`/`contact_title` output, notable-highlight opening
  instruction.
- `resume-engine/prompts/research_company.md` — two new extraction
  fields.

No new files, no new Gemini calls — every addition rides an existing call
or is resolved deterministically in Python.

## Explicitly out of scope

- Web search to find a named contact not present in the JD text.
- Filtering the address block by remote/on-site status.
- Widening `company_research.py`'s `CANDIDATE_PATHS` scrape list (e.g.
  adding `/news`, `/press`) — the existing tiers (JD text often includes
  an "About us" blurb; grounded search can already surface recent
  news/press) are expected to cover `notable_highlights` well enough
  without adding scrape surface area.
