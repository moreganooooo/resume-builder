# Company Research Tiered Fallback + Vocabulary Mirroring Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Guarantee `ResumeEngine.research_company()` always returns usable company signal (website scrape → confidence-gated grounded search → JD text), and mirror a company's preferred vocabulary into the Summary/Why sections (via prompt) and Work Experience bullets (via a deterministic post-process).

**Architecture:** Three tiers feed one shared structured-extraction call. Tier 1 is today's scraper, unchanged. Tier 2 is a new grounded Gemini search that self-reports `high`/`medium`/`low` confidence and is only trusted at `high`. Tier 3 falls back to the JD's own text, which always exists. The extraction schema gains a `vocabulary_substitutions` field; the Summary and Why sections consume it through prompt instructions, while bullets get a deterministic, case-preserving, word-boundary regex substitution applied once after Step 5.5 — never an LLM rewrite.

**Tech Stack:** Python 3.10+, stdlib `unittest` (not pytest), `re`, Pydantic `BaseModel` for Gemini response schemas, `GeminiClient` raw-REST wrapper.

**Spec:** `docs/superpowers/specs/2026-08-11-company-research-tiered-fallback-design.md`

## Global Constraints

- Run every test from the project root with the venv active: `source .venv/bin/activate` first. Bare `python3` on this machine may resolve to an unrelated stray venv.
- Tests are stdlib `unittest`, **not pytest**. Full suite: `python -m unittest discover -s tests -v`. Single test: `python -m unittest tests.test_module.TestClass.test_name -v`.
- **Gemini grounding tools and `response_schema` cannot be combined in one call.** Any call passing `tools=[{"google_search": {}}]` must be plain-text (no `response_schema`), and vice versa. `find_company_website()` already respects this; `tests/test_company_research.py::TestFindCompanyWebsite::test_passes_google_search_tool_not_response_schema` guards it.
- Every new function that calls out to Gemini or the network must return `None`/a safe default on failure and **never raise** — callers treat failure as "proceed exactly as if this feature didn't exist."
- Resume JSON shape is `resume_data["EXPERIENCE"]` → list of dicts, each with an `"achievements"` list of bullet strings. (Not `work_experience`/`bullets` — the spec text was wrong on this; the authoritative definition is `ExperienceEntry` at `scripts/orchestrator.py:1082-1102`.)
- Underscore-prefixed keys are this repo's convention for internal metadata that must never reach a prompt as content.
- Vocabulary substitution applies to bullets **only** — never the Skills section, never the cover letter.

### Deviation from the spec (deliberate, applies to Task 3)

The spec specifies `vocabulary_substitutions: List[str]` of `"generic -> company"` strings, justified by `scripts/orchestrator.py:73-75` claiming nested Pydantic models cause a builder 400. **That comment is stale.** `ExperienceEntry`'s docstring (`scripts/orchestrator.py:1082-1096`) records that this belief was tested and disproven: the real cause was `sanitize_schema()` deleting `$defs` and leaving dangling `$ref`s, fixed by `GeminiClient.resolve_refs()`. `TemplateSchema.EXPERIENCE` is a `List[ExperienceEntry]` — a nested model in production use today.

This plan therefore uses a nested `VocabularySubstitution` model, which eliminates the `" -> "` string-splitting and its malformed-pair guard entirely. Task 3 also fixes the stale comment at `scripts/orchestrator.py:73-75`.

---

## File Structure

| File | Responsibility | Change |
|---|---|---|
| `scripts/company_research.py` | Network/text-level company research primitives | Modify: add `research_company_via_search`, `apply_vocabulary_substitutions`, `apply_vocabulary_substitutions_to_resume`, `_match_case` |
| `scripts/orchestrator.py` | Pipeline orchestration + Gemini schemas | Modify: `CompanyResearchSchema` (+ new `VocabularySubstitution`), `format_company_research_block`, `research_company`, `build_tailored_resume` wiring, stale comment at :73-75 |
| `resume-engine/prompts/research_company.md` | Extraction prompt (all 3 tiers) | Modify: generalize source framing, add field 8, add JD-source rule |
| `resume-engine/prompts/tailor_resume.md` | Resume-writing prompt | Modify: Summary rule (line 74), Why rule (line 228), new Bullet Rules guardrail |
| `tests/test_company_research.py` | Unit tests for the primitives | Modify: add `TestResearchCompanyViaSearch`, `TestApplyVocabularySubstitutions`, `TestApplyVocabularySubstitutionsToResume` |
| `tests/test_orchestrator_research_company.py` | Unit tests for the tier dispatch | Modify: update 2 existing tests, add tier-fallthrough tests |
| `tests/test_orchestrator_research_block.py` | Unit tests for block formatting | Create |

Task order is dependency-driven: pure functions first (Tasks 1-2), then the schema they key off (Task 3), then the search tier (Task 4), then the dispatch that composes all of it (Task 5), then pipeline wiring (Task 6), then prompts (Task 7), then whole-suite + live verification (Task 8).

---

### Task 1: Case-preserving vocabulary substitution (pure function)

**Files:**
- Modify: `scripts/company_research.py` (append after `find_company_website`, ~line 132)
- Test: `tests/test_company_research.py`

**Interfaces:**
- Consumes: nothing (pure, stdlib `re` only)
- Produces:
  - `_match_case(source: str, replacement: str) -> str`
  - `apply_vocabulary_substitutions(text: str, substitutions: list) -> str` — `substitutions` is a list of dicts shaped `{"generic_term": str, "company_term": str}`

- [ ] **Step 1: Write failing tests**

Append to `tests/test_company_research.py`, before the `if __name__ == "__main__":` block:

```python
class TestApplyVocabularySubstitutions(unittest.TestCase):

    SUBS = [{"generic_term": "customers", "company_term": "guests"}]

    def test_replaces_lowercase_occurrence(self):
        result = company_research.apply_vocabulary_substitutions(
            "Grew customers by 30%", self.SUBS)
        self.assertEqual(result, "Grew guests by 30%")

    def test_preserves_leading_capital(self):
        result = company_research.apply_vocabulary_substitutions(
            "Customers drove the renewal", self.SUBS)
        self.assertEqual(result, "Guests drove the renewal")

    def test_preserves_all_caps(self):
        result = company_research.apply_vocabulary_substitutions(
            "CUSTOMERS FIRST", self.SUBS)
        self.assertEqual(result, "GUESTS FIRST")

    def test_respects_word_boundaries(self):
        # "customers" must not match inside "customersuccess"
        result = company_research.apply_vocabulary_substitutions(
            "Owned customersuccess tooling", self.SUBS)
        self.assertEqual(result, "Owned customersuccess tooling")

    def test_singular_is_not_matched_by_plural_pair(self):
        # \b means "customers" cannot match the shorter "customer".
        result = company_research.apply_vocabulary_substitutions(
            "Each customer mattered", self.SUBS)
        self.assertEqual(result, "Each customer mattered")

    def test_applies_multiple_pairs_in_one_string(self):
        subs = [
            {"generic_term": "customers", "company_term": "guests"},
            {"generic_term": "employees", "company_term": "team members"},
        ]
        result = company_research.apply_vocabulary_substitutions(
            "Trained employees to serve customers", subs)
        self.assertEqual(result, "Trained team members to serve guests")

    def test_empty_substitutions_is_a_no_op(self):
        self.assertEqual(
            company_research.apply_vocabulary_substitutions("Grew customers", []),
            "Grew customers")

    def test_skips_malformed_pair_without_raising(self):
        subs = [
            {"generic_term": "", "company_term": "guests"},
            {"company_term": "guests"},
            {"generic_term": "customers", "company_term": ""},
            {"generic_term": "customers", "company_term": "guests"},
        ]
        result = company_research.apply_vocabulary_substitutions("Grew customers", subs)
        self.assertEqual(result, "Grew guests")

    def test_regex_metacharacters_in_term_are_treated_literally(self):
        subs = [{"generic_term": "C++", "company_term": "Cpp"}]
        result = company_research.apply_vocabulary_substitutions("Shipped C++ tooling", subs)
        self.assertEqual(result, "Shipped Cpp tooling")
```

- [ ] **Step 2: Run tests and verify they fail**

```bash
source .venv/bin/activate && python -m unittest tests.test_company_research.TestApplyVocabularySubstitutions -v
```

Expected: FAIL — `AttributeError: module 'company_research' has no attribute 'apply_vocabulary_substitutions'`

- [ ] **Step 3: Write the implementation**

Append to `scripts/company_research.py` after `find_company_website`:

```python
def _match_case(source: str, replacement: str) -> str:
    """Makes `replacement` echo `source`'s capitalization, so substituting
    mid-sentence vs. sentence-initial vs. all-caps text all read naturally."""
    if source.isupper():
        return replacement.upper()
    if source[:1].isupper():
        return replacement[:1].upper() + replacement[1:]
    return replacement


def apply_vocabulary_substitutions(text: str, substitutions: list) -> str:
    """
    Swaps a generic noun for a company's own preferred term (e.g.
    "customers" -> "guests") in already-written text.

    Deliberately deterministic rather than an LLM rewrite: this runs over
    resume bullets, which are pre-audited verified text ("bullet bank is
    LEGO not prose inspiration", style_rules.yaml:19). A regex substitution
    can only change the target noun -- it structurally cannot alter a
    metric, a verb, or a claim, which an LLM asked to "mirror company
    vocabulary" absolutely could. See
    docs/superpowers/specs/2026-08-11-company-research-tiered-fallback-design.md.

    Word-boundary matched and case-preserving. Malformed pairs are skipped
    rather than raised on -- these terms come from a model, not a human.
    """
    if not text or not substitutions:
        return text

    for pair in substitutions:
        if not isinstance(pair, dict):
            continue
        generic = (pair.get("generic_term") or "").strip()
        preferred = (pair.get("company_term") or "").strip()
        if not generic or not preferred:
            continue
        # re.escape keeps a term like "C++" literal rather than a broken pattern.
        pattern = re.compile(rf"\b{re.escape(generic)}\b", re.IGNORECASE)
        text = pattern.sub(lambda m: _match_case(m.group(0), preferred), text)

    return text
```

- [ ] **Step 4: Run tests and verify they pass**

```bash
source .venv/bin/activate && python -m unittest tests.test_company_research.TestApplyVocabularySubstitutions -v
```

Expected: PASS (9 tests)

- [ ] **Step 5: Commit**

```bash
git add scripts/company_research.py tests/test_company_research.py
git commit -m "feat(research): add case-preserving vocabulary substitution"
```

---

### Task 2: Apply substitutions to resume bullets

**Files:**
- Modify: `scripts/company_research.py` (append after Task 1's function)
- Test: `tests/test_company_research.py`

**Interfaces:**
- Consumes: `apply_vocabulary_substitutions(text, substitutions)` from Task 1
- Produces: `apply_vocabulary_substitutions_to_resume(resume_data: dict, substitutions: list) -> dict` — mutates and returns `resume_data`, touching only `resume_data["EXPERIENCE"][*]["achievements"][*]`

- [ ] **Step 1: Write failing tests**

Append to `tests/test_company_research.py`:

```python
class TestApplyVocabularySubstitutionsToResume(unittest.TestCase):

    SUBS = [{"generic_term": "customers", "company_term": "guests"}]

    def _resume(self):
        return {
            "SUMMARY": "Strategist who grows customers",
            "EXPERIENCE": [
                {"company": "Acme", "achievements": [
                    "Grew customers by 30%",
                    "Launched a loyalty program",
                ]},
                {"company": "Globex", "achievements": ["Retained customers at 94%"]},
            ],
        }

    def test_substitutes_in_every_role_s_achievements(self):
        result = company_research.apply_vocabulary_substitutions_to_resume(
            self._resume(), self.SUBS)
        self.assertEqual(result["EXPERIENCE"][0]["achievements"][0], "Grew guests by 30%")
        self.assertEqual(result["EXPERIENCE"][1]["achievements"][0], "Retained guests at 94%")

    def test_leaves_untargeted_bullets_byte_identical(self):
        result = company_research.apply_vocabulary_substitutions_to_resume(
            self._resume(), self.SUBS)
        self.assertEqual(result["EXPERIENCE"][0]["achievements"][1], "Launched a loyalty program")

    def test_does_not_touch_the_summary(self):
        # The Summary is model-written with the vocabulary already in context;
        # this deterministic pass is bullets-only by design.
        result = company_research.apply_vocabulary_substitutions_to_resume(
            self._resume(), self.SUBS)
        self.assertEqual(result["SUMMARY"], "Strategist who grows customers")

    def test_empty_substitutions_returns_resume_unchanged(self):
        original = self._resume()
        result = company_research.apply_vocabulary_substitutions_to_resume(original, [])
        self.assertEqual(result, self._resume())

    def test_tolerates_missing_or_malformed_experience(self):
        for resume in ({}, {"EXPERIENCE": None}, {"EXPERIENCE": ["not a dict"]},
                       {"EXPERIENCE": [{"company": "Acme"}]},
                       {"EXPERIENCE": [{"achievements": "not a list"}]},
                       {"EXPERIENCE": [{"achievements": [None, 42]}]}):
            with self.subTest(resume=resume):
                company_research.apply_vocabulary_substitutions_to_resume(resume, self.SUBS)
```

- [ ] **Step 2: Run tests and verify they fail**

```bash
source .venv/bin/activate && python -m unittest tests.test_company_research.TestApplyVocabularySubstitutionsToResume -v
```

Expected: FAIL — `AttributeError: module 'company_research' has no attribute 'apply_vocabulary_substitutions_to_resume'`

- [ ] **Step 3: Write the implementation**

Append to `scripts/company_research.py`:

```python
def apply_vocabulary_substitutions_to_resume(resume_data: dict, substitutions: list) -> dict:
    """
    Applies apply_vocabulary_substitutions() to every Work Experience
    bullet in a built resume dict, in place, returning the same dict.

    Bullets only -- not SUMMARY or the Why section (both are model-written
    with the vocabulary already in their prompt context) and not Skills
    (category and tool names are precise technical terms, not
    customer-facing prose). Defensive about shape because it runs on
    model-generated JSON.
    """
    if not substitutions or not isinstance(resume_data, dict):
        return resume_data

    for role in resume_data.get("EXPERIENCE") or []:
        if not isinstance(role, dict):
            continue
        achievements = role.get("achievements")
        if not isinstance(achievements, list):
            continue
        role["achievements"] = [
            apply_vocabulary_substitutions(bullet, substitutions) if isinstance(bullet, str) else bullet
            for bullet in achievements
        ]

    return resume_data
```

- [ ] **Step 4: Run tests and verify they pass**

```bash
source .venv/bin/activate && python -m unittest tests.test_company_research.TestApplyVocabularySubstitutionsToResume -v
```

Expected: PASS (5 tests)

- [ ] **Step 5: Commit**

```bash
git add scripts/company_research.py tests/test_company_research.py
git commit -m "feat(research): apply vocabulary substitutions to resume bullets"
```

---

### Task 3: Schema field + research block line + extraction prompt

**Files:**
- Modify: `scripts/orchestrator.py:73-75` (stale comment), `scripts/orchestrator.py:903-910` (`CompanyResearchSchema`), `scripts/orchestrator.py:985-997` (`format_company_research_block`)
- Modify: `resume-engine/prompts/research_company.md`
- Test: `tests/test_orchestrator_research_block.py` (create)

**Interfaces:**
- Consumes: nothing from earlier tasks
- Produces:
  - `orchestrator.VocabularySubstitution` — Pydantic model with `generic_term: str`, `company_term: str`
  - `CompanyResearchSchema.vocabulary_substitutions: List[VocabularySubstitution]`
  - `format_company_research_block(research: dict) -> str` — now emits a `Preferred vocabulary:` line when `research["vocabulary_substitutions"]` is non-empty

- [ ] **Step 1: Write failing test**

Create `tests/test_orchestrator_research_block.py`:

```python
import os
import sys
import unittest

SCRIPTS_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts")
sys.path.insert(0, SCRIPTS_DIR)

import orchestrator  # noqa: E402


class TestFormatCompanyResearchBlock(unittest.TestCase):

    BASE = {
        "overall_tone_adjective": "warm and neighborly",
        "tone_register": "conversational",
        "pronoun_framing": "we-centric",
        "sentence_style": "short and punchy",
        "jargon_density": "low",
        "recurring_keywords": ["neighborly", "community"],
        "company_facts": ["Runs 400 neighborhood stores."],
    }

    def test_omits_vocabulary_line_when_field_absent(self):
        block = orchestrator.format_company_research_block(dict(self.BASE))
        self.assertNotIn("Preferred vocabulary", block)

    def test_omits_vocabulary_line_when_field_is_empty(self):
        block = orchestrator.format_company_research_block(
            dict(self.BASE, vocabulary_substitutions=[]))
        self.assertNotIn("Preferred vocabulary", block)

    def test_includes_vocabulary_line_when_pairs_present(self):
        block = orchestrator.format_company_research_block(dict(
            self.BASE,
            vocabulary_substitutions=[
                {"generic_term": "customers", "company_term": "guests"},
                {"generic_term": "employees", "company_term": "team members"},
            ],
        ))
        self.assertIn("Preferred vocabulary", block)
        self.assertIn("customers -> guests", block)
        self.assertIn("employees -> team members", block)

    def test_skips_malformed_pairs_in_the_line(self):
        block = orchestrator.format_company_research_block(dict(
            self.BASE,
            vocabulary_substitutions=[
                {"generic_term": "", "company_term": "guests"},
                {"generic_term": "customers", "company_term": "guests"},
                "not a dict",
            ],
        ))
        vocab_line = block.split("Preferred vocabulary")[1]
        self.assertIn("customers -> guests", vocab_line)
        # Exactly one pair survived -- no separator means no second entry.
        self.assertNotIn(",", vocab_line.split(": ", 1)[1])

    def test_still_renders_the_existing_fields(self):
        block = orchestrator.format_company_research_block(dict(self.BASE))
        self.assertIn("=== COMPANY RESEARCH ===", block)
        self.assertIn("warm and neighborly", block)
        self.assertIn("Runs 400 neighborhood stores.", block)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run test and verify it fails**

```bash
source .venv/bin/activate && python -m unittest tests.test_orchestrator_research_block -v
```

Expected: FAIL on `test_includes_vocabulary_line_when_pairs_present` — `AssertionError: 'Preferred vocabulary' not found in ...`

- [ ] **Step 3: Add the schema model**

Replace `scripts/orchestrator.py:903-910` with:

```python
class VocabularySubstitution(BaseModel):
    generic_term:  str = Field(description="The common/generic word the candidate's resume would normally use, e.g. 'customers'.")
    company_term:  str = Field(description="The company's own preferred word for that same thing, e.g. 'guests'.")

class CompanyResearchSchema(BaseModel):
    overall_tone_adjective: str       = Field(description="One short phrase describing the company's overall voice.")
    tone_register:          Literal["formal", "conversational", "mixed"]
    pronoun_framing:        Literal["we-centric", "you-centric", "mixed"]
    sentence_style:         Literal["short and punchy", "long and flowing", "mixed"]
    jargon_density:         Literal["high", "moderate", "low"]
    recurring_keywords:     List[str] = Field(description="1-3 brand words/phrases that genuinely repeat in the source text.")
    company_facts:          List[str] = Field(description="2-3 short, factual statements traceable directly to the source text.")
    vocabulary_substitutions: List[VocabularySubstitution] = Field(
        description="0-3 generic-term/company-term pairs where the source text clearly and repeatedly prefers its own word over the common one. Empty list if none genuinely qualify."
    )
```

- [ ] **Step 4: Update the research block formatter**

Replace `scripts/orchestrator.py:985-997` (the whole `format_company_research_block` function) with:

```python
def format_company_research_block(research: dict) -> str:
    """Formats a CompanyResearchSchema-shaped dict into the
    '=== COMPANY RESEARCH ===' context block both build_tailored_coverletter
    and build_tailored_resume fold into their system-instruction context."""
    block = (
        "\n\n=== COMPANY RESEARCH ===\n"
        f"Overall tone: {research.get('overall_tone_adjective', '')}\n"
        f"Register: {research.get('tone_register', '')} | Framing: {research.get('pronoun_framing', '')} | "
        f"Sentence style: {research.get('sentence_style', '')} | Jargon: {research.get('jargon_density', '')}\n"
        f"Recurring brand words: {', '.join(research.get('recurring_keywords', []))}\n"
        "Company facts (use at most 1-2, never fabricate beyond these):\n"
        + "\n".join(f"- {fact}" for fact in research.get('company_facts', []))
    )

    pairs = [
        f"{p.get('generic_term')} -> {p.get('company_term')}"
        for p in (research.get("vocabulary_substitutions") or [])
        if isinstance(p, dict) and p.get("generic_term") and p.get("company_term")
    ]
    if pairs:
        block += (
            "\nPreferred vocabulary (use the company's term in place of the generic one "
            f"wherever it reads naturally): {', '.join(pairs)}"
        )

    return block
```

- [ ] **Step 5: Fix the stale nested-schema comment**

Replace `scripts/orchestrator.py:72-75` — currently:

```python
# BUILDER_MODEL: handles JD keyword extraction and the final resume assembly.
#   gemini-3.1-flash-lite for quota reasons. TemplateSchema is now flattened
#   (List[dict] instead of List[NestedModel]) to avoid the deeply-nested
#   $defs in responseSchema that caused the builder 400.
```

with:

```python
# BUILDER_MODEL: handles JD keyword extraction and the final resume assembly.
#   gemini-3.1-flash-lite for quota reasons. Nested response models are fine
#   here -- TemplateSchema was briefly flattened to List[dict] on the theory
#   that nested $defs caused a builder 400, but that was disproven and
#   reverted (see ExperienceEntry's docstring: the real cause was
#   sanitize_schema() dropping $defs, fixed by GeminiClient.resolve_refs()).
```

- [ ] **Step 6: Update the extraction prompt**

In `resume-engine/prompts/research_company.md`:

Replace line 5:

```markdown
You are extracting tone signals and factual highlights from text about a company -- scraped from the company's own About/Mission/Careers pages, gathered via a web search, or drawn directly from a job posting the company wrote -- for later use in tailoring a cover letter and resume tone-mirroring. You are not writing anything customer-facing yourself.
```

Replace line 9 (`Read the scraped company page text and extract:`) with:

```markdown
Read the provided company text and extract:
```

Add after line 16 (the `company_facts` item):

```markdown
8. **vocabulary_substitutions** -- 0-3 pairs where the company clearly and repeatedly uses its own word in place of a common one (e.g. a retailer that always says "guests" rather than "customers," or "team members" rather than "employees"). Each pair is `generic_term` (the common word) and `company_term` (theirs). Only include a pair when the preference is unmistakable and repeated in the text -- a single incidental usage is not enough. Return an empty list when nothing genuinely qualifies; never invent a pair to fill this field.
```

Add to the `# Rules` section, after line 20:

```markdown
- If the provided text is a job posting rather than the company's own site, `company_facts` must restate only what the posting itself states about the company. Do not add outside claims, and do not treat the role's requirements as facts about the company.
- A `vocabulary_substitutions` pair must be a pure synonym swap for the same thing -- never a pair that would change a claim's meaning if substituted (e.g. "managed -> led" is not a vocabulary substitution).
```

Replace line 26 (the `# Output` line):

```markdown
Respond with the structured company research JSON only: `overall_tone_adjective`, `tone_register`, `pronoun_framing`, `sentence_style`, `jargon_density`, `recurring_keywords` (list), `company_facts` (list of 2-3), `vocabulary_substitutions` (list of 0-3 `{generic_term, company_term}` objects).
```

- [ ] **Step 7: Run tests and verify they pass**

```bash
source .venv/bin/activate && python -m unittest tests.test_orchestrator_research_block -v
```

Expected: PASS (5 tests)

- [ ] **Step 8: Commit**

```bash
git add scripts/orchestrator.py resume-engine/prompts/research_company.md tests/test_orchestrator_research_block.py
git commit -m "feat(research): extract company vocabulary preferences"
```

---

### Task 4: Tier 2 — confidence-gated grounded search

**Files:**
- Modify: `scripts/company_research.py` (append after `find_company_website`, before Task 1's functions), plus the module docstring
- Test: `tests/test_company_research.py`

**Interfaces:**
- Consumes: `GeminiClient.generate`, module constant `FIND_WEBSITE_MODEL`
- Produces:
  - `company_research.SEARCH_RESEARCH_MODEL` — module constant
  - `company_research._CONFIDENCE_PATTERN` — compiled regex
  - `research_company_via_search(company_name: str, context_hint: str = "") -> str | None` — returns the search's descriptive text **only** when the model self-reports `high` confidence; `None` otherwise. (Note: returns just the text, not a `(confidence, text)` tuple — the caller has no use for a confidence it isn't allowed to act on.)

- [ ] **Step 1: Write failing tests**

Append to `tests/test_company_research.py`:

```python
class TestResearchCompanyViaSearch(unittest.TestCase):

    HIGH = "CONFIDENCE: high\nAcme calls its customers guests and leads with neighborly warmth."

    def test_returns_none_when_company_name_missing(self):
        self.assertIsNone(company_research.research_company_via_search(""))
        self.assertIsNone(company_research.research_company_via_search(None))

    @patch("company_research.GeminiClient.generate")
    def test_returns_text_on_high_confidence(self, mock_generate):
        mock_generate.return_value = (self.HIGH, {})
        result = company_research.research_company_via_search("Acme Corp")
        self.assertIn("neighborly warmth", result)

    @patch("company_research.GeminiClient.generate")
    def test_strips_the_confidence_line_from_the_returned_text(self, mock_generate):
        mock_generate.return_value = (self.HIGH, {})
        result = company_research.research_company_via_search("Acme Corp")
        self.assertNotIn("CONFIDENCE:", result)

    @patch("company_research.GeminiClient.generate")
    def test_returns_none_on_medium_confidence(self, mock_generate):
        mock_generate.return_value = ("CONFIDENCE: medium\nProbably a retailer.", {})
        self.assertIsNone(company_research.research_company_via_search("Acme Corp"))

    @patch("company_research.GeminiClient.generate")
    def test_returns_none_on_low_confidence(self, mock_generate):
        mock_generate.return_value = ("CONFIDENCE: low\nNot sure which Acme this is.", {})
        self.assertIsNone(company_research.research_company_via_search("Acme Corp"))

    @patch("company_research.GeminiClient.generate")
    def test_returns_none_when_confidence_line_missing(self, mock_generate):
        # Fail closed: unlabeled output is never trusted.
        mock_generate.return_value = ("Acme is a warm, neighborly retailer.", {})
        self.assertIsNone(company_research.research_company_via_search("Acme Corp"))

    @patch("company_research.GeminiClient.generate")
    def test_returns_none_when_high_confidence_has_no_body_text(self, mock_generate):
        mock_generate.return_value = ("CONFIDENCE: high", {})
        self.assertIsNone(company_research.research_company_via_search("Acme Corp"))

    @patch("company_research.GeminiClient.generate")
    def test_passes_google_search_tool_not_response_schema(self, mock_generate):
        mock_generate.return_value = (self.HIGH, {})
        company_research.research_company_via_search("Acme Corp")
        _, kwargs = mock_generate.call_args
        self.assertEqual(kwargs.get("tools"), [{"google_search": {}}])
        self.assertNotIn("response_schema", kwargs)

    @patch("company_research.GeminiClient.generate")
    def test_includes_context_hint_in_the_prompt(self, mock_generate):
        mock_generate.return_value = (self.HIGH, {})
        company_research.research_company_via_search("Acme Corp", "Senior CRM Manager, retail")
        _, kwargs = mock_generate.call_args
        self.assertIn("Senior CRM Manager, retail", kwargs.get("contents", ""))

    @patch("company_research.GeminiClient.generate")
    def test_returns_none_on_api_exception_instead_of_raising(self, mock_generate):
        mock_generate.side_effect = RuntimeError("network error")
        self.assertIsNone(company_research.research_company_via_search("Acme Corp"))
```

- [ ] **Step 2: Run tests and verify they fail**

```bash
source .venv/bin/activate && python -m unittest tests.test_company_research.TestResearchCompanyViaSearch -v
```

Expected: FAIL — `AttributeError: module 'company_research' has no attribute 'research_company_via_search'`

- [ ] **Step 3: Write the implementation**

Add the constant next to `FIND_WEBSITE_MODEL` (`scripts/company_research.py:41`):

```python
FIND_WEBSITE_MODEL = "gemini-3.1-flash-lite"
SEARCH_RESEARCH_MODEL = "gemini-3.1-flash-lite"

# Tier 2's self-reported confidence. Anything but "high" falls through to
# Tier 3 -- many companies share a name, and a confidently-wrong writeup
# about the wrong Acme is worse than falling back to the JD's own text.
_CONFIDENCE_PATTERN = re.compile(r"^\s*CONFIDENCE:\s*(high|medium|low)\b", re.IGNORECASE)
```

Then append the function after `find_company_website`:

```python
def research_company_via_search(company_name: str, context_hint: str = "") -> str | None:
    """
    Tier 2 of ResumeEngine.research_company()'s fallback chain: when no
    company website is known or scrapeable, ask Gemini (with Google Search
    grounding) to describe the company's tone, values, and language
    directly.

    Like find_company_website(), this is a plain-text call with no
    response_schema -- grounding and structured output can't be combined
    in one request. Its output is fed to the same research_company.md
    extraction call the scraped-page path uses, so there's exactly one
    place that produces CompanyResearchSchema.

    The model self-reports confidence on a leading `CONFIDENCE:` line, and
    only "high" is trusted; anything else (including a missing or
    unparseable line) returns None so the caller falls through to Tier 3.
    Returns None on any failure and never raises.
    """
    if not company_name:
        return None

    hint = f"\n\nContext from the job posting (use this to disambiguate same-named companies): {context_hint}" if context_hint else ""

    try:
        text, _ = GeminiClient.generate(
            model=SEARCH_RESEARCH_MODEL,
            system_instruction=(
                "You research companies' public voice and values. Your first "
                "line must be exactly 'CONFIDENCE: high', 'CONFIDENCE: medium', "
                "or 'CONFIDENCE: low' -- reporting how certain you are that "
                "you found the specific company asked about, not how much you "
                "found. Say 'high' only when the identifying details you found "
                "clearly match the company described. Many companies share a "
                "name; if you cannot tell which one this is, say 'low'. After "
                "that line, describe in plain prose: what the company does, "
                "their stated mission and values, the tone of their public "
                "writing, and any distinctive words they use for everyday "
                "things (for example calling customers 'guests'). Use only "
                "what you actually found -- never fill gaps with plausible "
                "guesses."
            ),
            contents=f"Research the company \"{company_name}\".{hint}",
            tools=[{"google_search": {}}],
            temperature=0.0,
        )
    except Exception:
        return None

    if not text:
        return None

    match = _CONFIDENCE_PATTERN.match(text)
    if not match or match.group(1).lower() != "high":
        return None

    body = text[match.end():].strip()
    return body or None
```

Finally, extend the module docstring's `find_company_website()` paragraph (`scripts/company_research.py:11-17`) to cover both grounded calls — replace "find_company_website() is the one exception" with:

```
find_company_website() and research_company_via_search() are the exceptions
to "no search API" above -- both are real, separate Gemini calls using
Google Search grounding, used as fallbacks when no company_website is
already known from the JD source, or when the site that is known turns out
to be unscrapeable/too thin (see ResumeEngine.research_company()). Both are
kept as distinct plain-text calls (no response_schema) rather than folded
into the extraction call, since grounding tools and structured JSON output
can't be combined in a single Gemini call.
```

- [ ] **Step 4: Run tests and verify they pass**

```bash
source .venv/bin/activate && python -m unittest tests.test_company_research -v
```

Expected: PASS (all tests in the file, including the pre-existing `TestFindCompanyWebsite` ones)

- [ ] **Step 5: Commit**

```bash
git add scripts/company_research.py tests/test_company_research.py
git commit -m "feat(research): add confidence-gated grounded search tier"
```

---

### Task 5: Three-tier dispatch in `research_company()`

**Files:**
- Modify: `scripts/orchestrator.py:2391-2431` (`research_company`), `:2536-2537` and `:2794-2795` (call sites)
- Test: `tests/test_orchestrator_research_company.py`

**Interfaces:**
- Consumes: `company_research.research_company_via_search` (Task 4), `format_company_research_block` (Task 3)
- Produces:
  - `ResumeEngine._extract_company_research(self, source_text: str, source_label: str) -> dict | None`
  - `ResumeEngine.research_company(self, jd_data: dict, jd_text: str = "") -> dict | None` — **signature change**: new optional `jd_text` argument carrying the raw JD text for Tier 3. Result dict carries `_research_source` (`"website"` / `"search"` / `"jd_text"`).

- [ ] **Step 1: Write failing tests**

Replace the entire body of `tests/test_orchestrator_research_company.py` with:

```python
import os
import sys
import unittest
from unittest.mock import patch

SCRIPTS_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts")
sys.path.insert(0, SCRIPTS_DIR)

import orchestrator  # noqa: E402

_RESEARCH_JSON = '{"overall_tone_adjective": "warm", "company_facts": ["Sells things."]}'


class TestResearchCompanyWebsiteFallback(unittest.TestCase):
    """Covers the 2026-07-21 fallback: research_company() used to give up
    immediately when jd_data had no company_website (true unconditionally
    for scan_linkedin.py's JDs). It now tries
    company_research.find_company_website() first."""

    def setUp(self):
        self.engine = orchestrator.ResumeEngine()

    @patch("orchestrator.company_research.research_company_via_search", return_value=None)
    @patch("orchestrator.company_research.find_company_website")
    def test_falls_through_to_lower_tiers_when_no_website_found(self, mock_find, mock_search):
        mock_find.return_value = None
        # No jd_text either, so every tier is exhausted -> None.
        result = self.engine.research_company({"company_name": "Acme Corp"})
        self.assertIsNone(result)
        mock_find.assert_called_once_with("Acme Corp")

    @patch("orchestrator.GeminiClient.generate")
    @patch("orchestrator.company_research.fetch_company_pages")
    @patch("orchestrator.company_research.find_company_website")
    def test_uses_found_website_to_proceed_with_research(self, mock_find, mock_fetch, mock_generate):
        mock_find.return_value = "https://www.acme.com"
        mock_fetch.return_value = "x" * 300
        mock_generate.return_value = (_RESEARCH_JSON, {})

        self.engine.research_company({"company_name": "Acme Corp"})

        mock_fetch.assert_called_once_with("https://www.acme.com")

    @patch("orchestrator.company_research.research_company_via_search", return_value=None)
    @patch("orchestrator.company_research.find_company_website")
    def test_does_not_call_fallback_when_website_already_known(self, mock_find, mock_search):
        with patch("orchestrator.company_research.fetch_company_pages", return_value=""):
            self.engine.research_company({"company_name": "Acme Corp", "company_website": "acme.com"})
        mock_find.assert_not_called()


class TestResearchCompanyTierFallback(unittest.TestCase):
    """The 2026-08-11 guarantee: research_company() should produce signal
    for effectively every JD -- website scrape, then confidence-gated
    grounded search, then the JD's own text."""

    def setUp(self):
        self.engine = orchestrator.ResumeEngine()
        self.jd_data = {"company_name": "Acme Corp", "company_website": "https://www.acme.com"}
        self.jd_text = "Acme Corp is hiring a CRM Manager to delight our guests."

    @patch("orchestrator.GeminiClient.generate")
    @patch("orchestrator.company_research.research_company_via_search")
    @patch("orchestrator.company_research.fetch_company_pages")
    def test_tier1_used_when_scrape_is_usable(self, mock_fetch, mock_search, mock_generate):
        mock_fetch.return_value = "x" * 300
        mock_generate.return_value = (_RESEARCH_JSON, {})

        result = self.engine.research_company(self.jd_data, self.jd_text)

        self.assertEqual(result["_research_source"], "website")
        mock_search.assert_not_called()

    @patch("orchestrator.GeminiClient.generate")
    @patch("orchestrator.company_research.research_company_via_search")
    @patch("orchestrator.company_research.fetch_company_pages")
    def test_tier2_used_when_scrape_is_thin_and_search_is_high_confidence(
            self, mock_fetch, mock_search, mock_generate):
        mock_fetch.return_value = ""
        mock_search.return_value = "Acme calls its customers guests."
        mock_generate.return_value = (_RESEARCH_JSON, {})

        result = self.engine.research_company(self.jd_data, self.jd_text)

        self.assertEqual(result["_research_source"], "search")

    @patch("orchestrator.GeminiClient.generate")
    @patch("orchestrator.company_research.research_company_via_search")
    @patch("orchestrator.company_research.fetch_company_pages")
    def test_tier3_used_when_search_is_not_high_confidence(
            self, mock_fetch, mock_search, mock_generate):
        mock_fetch.return_value = ""
        mock_search.return_value = None  # medium/low/failed all surface as None
        mock_generate.return_value = (_RESEARCH_JSON, {})

        result = self.engine.research_company(self.jd_data, self.jd_text)

        self.assertEqual(result["_research_source"], "jd_text")

    @patch("orchestrator.GeminiClient.generate")
    @patch("orchestrator.company_research.research_company_via_search")
    @patch("orchestrator.company_research.find_company_website")
    @patch("orchestrator.company_research.fetch_company_pages")
    def test_always_returns_something_when_jd_text_exists(
            self, mock_fetch, mock_find, mock_search, mock_generate):
        # The core guarantee: no website, no search result -- still not None.
        mock_find.return_value = None
        mock_fetch.return_value = ""
        mock_search.return_value = None
        mock_generate.return_value = (_RESEARCH_JSON, {})

        result = self.engine.research_company({"company_name": "Acme Corp"}, self.jd_text)

        self.assertIsNotNone(result)

    @patch("orchestrator.GeminiClient.generate")
    @patch("orchestrator.company_research.research_company_via_search")
    @patch("orchestrator.company_research.fetch_company_pages")
    def test_passes_jd_context_hint_to_the_search_tier(
            self, mock_fetch, mock_search, mock_generate):
        mock_fetch.return_value = ""
        mock_search.return_value = "Acme is neighborly."
        mock_generate.return_value = (_RESEARCH_JSON, {})

        self.engine.research_company(
            dict(self.jd_data, job_title="Senior CRM Manager"), self.jd_text)

        args, _ = mock_search.call_args
        self.assertEqual(args[0], "Acme Corp")
        self.assertIn("Senior CRM Manager", args[1])

    @patch("orchestrator.GeminiClient.generate")
    @patch("orchestrator.company_research.research_company_via_search")
    @patch("orchestrator.company_research.fetch_company_pages")
    def test_returns_none_when_extraction_cannot_be_parsed(
            self, mock_fetch, mock_search, mock_generate):
        mock_fetch.return_value = "x" * 300
        mock_generate.return_value = ("not json at all", {})

        self.assertIsNone(self.engine.research_company(self.jd_data, self.jd_text))

    @patch("orchestrator.GeminiClient.generate")
    @patch("orchestrator.company_research.research_company_via_search")
    @patch("orchestrator.company_research.fetch_company_pages")
    def test_research_source_never_reaches_the_prompt_block(
            self, mock_fetch, mock_search, mock_generate):
        mock_fetch.return_value = "x" * 300
        mock_generate.return_value = (_RESEARCH_JSON, {})

        result = self.engine.research_company(self.jd_data, self.jd_text)
        block = orchestrator.format_company_research_block(result)

        self.assertNotIn("_research_source", block)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run tests and verify they fail**

```bash
source .venv/bin/activate && python -m unittest tests.test_orchestrator_research_company -v
```

Expected: FAIL — `KeyError: '_research_source'` on the tier tests, and `AttributeError` on `orchestrator.company_research.research_company_via_search` if Task 4 was skipped.

- [ ] **Step 3: Rewrite `research_company`**

Replace `scripts/orchestrator.py:2391-2431` in full with:

```python
    def _extract_company_research(self, source_text: str, source_label: str) -> dict | None:
        """
        The single structured-extraction call behind all three of
        research_company()'s tiers -- each tier's job is only to produce
        source text, so there's exactly one place that produces a
        CompanyResearchSchema-shaped dict.

        source_label is internal bookkeeping (which tier won) and is
        returned under the underscore-prefixed _research_source key so it
        can never be mistaken for prompt content; format_company_research_block
        ignores it. Returns None if the model response can't be parsed.
        """
        research_prompt = self.load_prompt("research_company.md")
        research_text, _ = GeminiClient.generate(
            model=BUILDER_MODEL,
            system_instruction=research_prompt,
            contents=f"=== COMPANY SOURCE TEXT ===\n{source_text}",
            response_schema=CompanyResearchSchema,
            temperature=0.0,
        )
        research_data = GeminiClient.parse_json(research_text or "")
        if not research_data:
            cli_art.console.print(f"  {theme.colorize_icon('hint')} Company research skipped: model response couldn't be parsed.", soft_wrap=True)
            return None

        research_data["_research_source"] = source_label
        return research_data

    def research_company(self, jd_data: dict, jd_text: str = "") -> dict | None:
        """
        Extracts a company's tone signals, traceable facts, and preferred
        vocabulary, trying three sources in descending order of quality:

          1. The company's own About/Mission/Careers pages, if a
             company_website is known in jd_data or findable via a Google
             Search grounding lookup keyed on company_name.
          2. A grounded search writeup of the company, used only when the
             model self-reports "high" confidence that it found the right
             company (many companies share a name -- see
             company_research.research_company_via_search).
          3. The JD's own text, which always exists.

        Tier 3 means this effectively never returns None any more, which is
        the point: every role should have something real to tailor against.
        The remaining None paths are an empty jd_text (operationally a
        non-occurrence) and an unparseable model response. Callers must
        still treat None as "proceed exactly as if this feature didn't
        exist." See
        docs/superpowers/specs/2026-08-11-company-research-tiered-fallback-design.md.
        """
        # --- Tier 1: the company's own site ---
        company_website = jd_data.get("company_website")
        if not company_website:
            company_website = company_research.find_company_website(jd_data.get("company_name"))
            if company_website:
                cli_art.console.print(f"  {theme.colorize_icon('hint')} No company website on file -- found one via search: {company_website}", soft_wrap=True)

        if company_website:
            scraped_text = company_research.fetch_company_pages(company_website)
            if len(scraped_text) >= company_research.MIN_USEFUL_CHARS:
                research_data = self._extract_company_research(scraped_text, "website")
                if research_data:
                    cli_art.console.print(f"  {theme.colorize_icon('success')} Company research complete for {company_website}.", soft_wrap=True)
                return research_data
            cli_art.console.print(f"  {theme.colorize_icon('hint')} Couldn't find enough usable content on {company_website} -- trying a web search instead.", soft_wrap=True)
        else:
            cli_art.console.print(f"  {theme.colorize_icon('hint')} No company website known for this JD -- trying a web search instead.", soft_wrap=True)

        # --- Tier 2: grounded search, trusted only at high confidence ---
        company_name = jd_data.get("company_name")
        context_hint = ", ".join(str(v) for v in (jd_data.get("job_title"), jd_data.get("industry")) if v)
        search_text = company_research.research_company_via_search(company_name, context_hint)
        if search_text:
            research_data = self._extract_company_research(search_text, "search")
            if research_data:
                cli_art.console.print(f"  {theme.colorize_icon('success')} Company research complete for {company_name} (from a web search).", soft_wrap=True)
            return research_data

        # --- Tier 3: the JD's own text ---
        if not jd_text.strip():
            cli_art.console.print(f"  {theme.colorize_icon('hint')} Company research skipped: nothing usable found for this JD.", soft_wrap=True)
            return None

        research_data = self._extract_company_research(jd_text, "jd_text")
        if research_data:
            cli_art.console.print(f"  {theme.colorize_icon('success')} Company research complete for {company_name} (from the job posting's own text).", soft_wrap=True)
        return research_data
```

- [ ] **Step 4: Pass `jd_text` at both call sites**

`scripts/orchestrator.py:2536-2537` (in `build_tailored_coverletter`) — replace:

```python
        jd_data = _parse_jd_data(jd_text)
        research = self.research_company(jd_data)
```

with:

```python
        jd_data = _parse_jd_data(jd_text)
        research = self.research_company(jd_data, jd_text)
```

`scripts/orchestrator.py:2794-2795` (in `build_tailored_resume`) — replace:

```python
            jd_data = _parse_jd_data(jd_text)
            research = self.research_company(jd_data)
```

with:

```python
            jd_data = _parse_jd_data(jd_text)
            research = self.research_company(jd_data, jd_text)
```

- [ ] **Step 5: Run tests and verify they pass**

```bash
source .venv/bin/activate && python -m unittest tests.test_orchestrator_research_company -v
```

Expected: PASS (10 tests)

- [ ] **Step 6: Commit**

```bash
git add scripts/orchestrator.py tests/test_orchestrator_research_company.py
git commit -m "feat(research): always find something via 3-tier fallback"
```

---

### Task 6: Wire the bullet substitution into the resume pipeline

**Files:**
- Modify: `scripts/orchestrator.py:3033-3034` (checkpoint write), `scripts/orchestrator.py:3324` (insertion point before Step 6)
- Test: `tests/test_orchestrator_vocabulary_wiring.py` (create)

**Interfaces:**
- Consumes: `company_research.apply_vocabulary_substitutions_to_resume` (Task 2), `research["vocabulary_substitutions"]` (Task 3), `research_company()` (Task 5)
- Produces: `checkpoint["vocabulary_substitutions"]` — the pairs list, persisted at the same point as `checkpoint["resume_data"]`

**Why the checkpoint:** `research` is assigned only inside `build_tailored_resume`'s fresh-build branch (`scripts/orchestrator.py:2791` `else:`). On a resumed run, `resume_data` comes from the checkpoint at `:2788` and that branch never executes, so referencing `research` at Step 6 would raise `NameError` — the exact failure class the comments at `:2777-2786` were written about. Persisting the pairs makes both paths work identically.

- [ ] **Step 1: Write failing test**

Create `tests/test_orchestrator_vocabulary_wiring.py`:

```python
import os
import sys
import unittest

SCRIPTS_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts")
sys.path.insert(0, SCRIPTS_DIR)

import company_research  # noqa: E402
import orchestrator  # noqa: E402


class TestVocabularyWiringContract(unittest.TestCase):
    """build_tailored_resume applies vocabulary substitutions from the
    checkpoint (not from an in-scope `research` variable) so a resumed run
    behaves identically to a fresh one -- `research` is assigned only in
    the fresh-build branch."""

    def test_substitution_reads_from_checkpoint_not_research_variable(self):
        source = orchestrator.inspect.getsource(orchestrator.ResumeEngine.build_tailored_resume)
        self.assertIn('checkpoint["vocabulary_substitutions"]', source)
        self.assertIn("apply_vocabulary_substitutions_to_resume", source)

    def test_substitution_runs_before_the_save_step(self):
        source = orchestrator.inspect.getsource(orchestrator.ResumeEngine.build_tailored_resume)
        subst_at = source.index("apply_vocabulary_substitutions_to_resume(")
        save_at = source.index("# --- Step 6: Save output ---")
        self.assertLess(subst_at, save_at)

    def test_end_to_end_substitution_on_a_built_resume_shape(self):
        resume_data = {
            "SUMMARY": "Strategist",
            "EXPERIENCE": [{"company": "Acme", "achievements": ["Grew customers by 30%"]}],
        }
        pairs = [{"generic_term": "customers", "company_term": "guests"}]
        result = company_research.apply_vocabulary_substitutions_to_resume(resume_data, pairs)
        self.assertEqual(result["EXPERIENCE"][0]["achievements"][0], "Grew guests by 30%")


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run test and verify it fails**

```bash
source .venv/bin/activate && python -m unittest tests.test_orchestrator_vocabulary_wiring -v
```

Expected: FAIL — either `AttributeError: module 'orchestrator' has no attribute 'inspect'` or `AssertionError: 'checkpoint["vocabulary_substitutions"]' not found in ...`

- [ ] **Step 3: Import `inspect` in orchestrator**

`scripts/orchestrator.py` does not currently import `inspect` (verified while writing this plan). Add it to the stdlib import block, in alphabetical position among the existing stdlib imports.

- [ ] **Step 4: Persist the pairs into the checkpoint**

Replace `scripts/orchestrator.py:3033-3034`:

```python
            checkpoint["resume_data"] = resume_data
            jd_manager.save_checkpoint(job_key, checkpoint)
```

with:

```python
            checkpoint["resume_data"] = resume_data
            # Persisted (rather than read off `research` at the Step 6 call
            # site) because `research` only exists in this fresh-build
            # branch -- a resumed run enters at the `resume_data is not
            # None` branch above and would otherwise both NameError and
            # silently lose the substitution.
            checkpoint["vocabulary_substitutions"] = (research or {}).get("vocabulary_substitutions", [])
            jd_manager.save_checkpoint(job_key, checkpoint)
```

- [ ] **Step 5: Apply the substitution before Step 6**

Insert immediately before `scripts/orchestrator.py:3324`'s `# --- Step 6: Save output ---`, at 8-space indentation:

```python
        # Mirror the company's own vocabulary into bullet text (e.g.
        # "customers" -> "guests"). Deliberately last, after Step 5.5's
        # recommendation pass: running it here means no later step can
        # reword a bullet back out of the company's language, and it's a
        # deterministic regex swap rather than an LLM edit, so it cannot
        # touch a metric, verb, or claim.
        resume_data = company_research.apply_vocabulary_substitutions_to_resume(
            resume_data, checkpoint.get("vocabulary_substitutions", [])
        )

```

- [ ] **Step 6: Run tests and verify they pass**

```bash
source .venv/bin/activate && python -m unittest tests.test_orchestrator_vocabulary_wiring -v
```

Expected: PASS (3 tests)

- [ ] **Step 7: Commit**

```bash
git add scripts/orchestrator.py tests/test_orchestrator_vocabulary_wiring.py
git commit -m "feat(research): mirror company vocabulary into resume bullets"
```

---

### Task 7: Prompt updates for Summary, Why, and bullet guardrail

**Files:**
- Modify: `resume-engine/prompts/tailor_resume.md` (lines 74, 118, 228)
- Test: `tests/test_tailor_prompt_vocabulary.py` (create)

**Interfaces:**
- Consumes: the `Preferred vocabulary` line emitted by `format_company_research_block` (Task 3)
- Produces: no code interface — prompt text only

- [ ] **Step 1: Write failing test**

Create `tests/test_tailor_prompt_vocabulary.py`:

```python
import os
import unittest

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PROMPT_PATH = os.path.join(PROJECT_ROOT, "resume-engine", "prompts", "tailor_resume.md")


class TestTailorPromptVocabularyRules(unittest.TestCase):
    """Guards the 2026-08-11 vocabulary-mirroring instructions against
    silent removal during future prompt edits."""

    @classmethod
    def setUpClass(cls):
        with open(PROMPT_PATH, "r", encoding="utf-8") as f:
            cls.prompt = f.read()

    def test_summary_and_why_rules_reference_the_vocabulary_field(self):
        self.assertGreaterEqual(self.prompt.count("vocabulary_substitutions"), 2)

    def test_bullet_rules_forbid_model_side_rewording_for_vocabulary(self):
        bullet_section = self.prompt.split("# Bullet Rules")[1].split("\n#")[0]
        self.assertIn("vocabulary_substitutions", bullet_section)
        self.assertIn("Do not reword", bullet_section)

    def test_drops_the_stale_no_research_block_fallbacks(self):
        # A COMPANY RESEARCH block is now effectively always present, so
        # "skip if absent" instructions would misfire.
        self.assertNotIn("skip tone-mirroring entirely", self.prompt)
        self.assertNotIn("do not include this Why section at all", self.prompt)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run test and verify it fails**

```bash
source .venv/bin/activate && python -m unittest tests.test_tailor_prompt_vocabulary -v
```

Expected: FAIL on all three tests.

- [ ] **Step 3: Update the Summary rule**

In `resume-engine/prompts/tailor_resume.md`, replace line 74 in full:

```markdown
- Use the `=== COMPANY RESEARCH ===` context block as the actual source for this tone-mirroring — its tone_register/pronoun_framing/jargon_density/recurring_keywords fields describe the real signal to match. When that block carries a `Preferred vocabulary` line, use the company's own term in place of the generic one anywhere it reads naturally in the Summary — this is the strongest single signal that the candidate already speaks their language. Never bend a fact to fit a term: if the company's word doesn't actually apply to what the candidate did, keep the accurate word
```

- [ ] **Step 4: Update the Why-section rule**

Replace line 228 in full:

```markdown
- Source those "specific company research details" ONLY from the `=== COMPANY RESEARCH ===` context block's `company_facts` field — never invent research-sounding details to satisfy this rule. When the block carries a `Preferred vocabulary` line, use the company's own terms here too; this section is where mirroring their language reads most naturally
```

- [ ] **Step 5: Add the bullet guardrail**

Insert after line 118 (`- No parentheses in bullets; use commas or semicolons`):

```markdown
- Do not reword, paraphrase, or restructure a bullet to match the company's tone or `vocabulary_substitutions` — bullets come from the pre-audited bullet bank, and a separate deterministic pass applies the company's preferred terms after you're done. Your job for bullets is selection and arrangement, not rewriting for voice
```

- [ ] **Step 6: Run tests and verify they pass**

```bash
source .venv/bin/activate && python -m unittest tests.test_tailor_prompt_vocabulary -v
```

Expected: PASS (3 tests)

- [ ] **Step 7: Commit**

```bash
git add resume-engine/prompts/tailor_resume.md tests/test_tailor_prompt_vocabulary.py
git commit -m "feat(prompts): mirror company vocabulary in Summary and Why"
```

---

### Task 8: Full-suite regression + live verification

**Files:**
- Modify: `CLAUDE.md` (Architecture notes)
- Test: whole suite

**Interfaces:**
- Consumes: everything from Tasks 1-7
- Produces: nothing — verification and documentation only

- [ ] **Step 1: Run the full test suite**

```bash
source .venv/bin/activate && python -m unittest discover -s tests -v 2>&1 | tail -30
```

Expected: PASS. If anything unrelated to this work fails, check whether it failed before this branch's changes (`git stash && python -m unittest discover -s tests 2>&1 | tail -5 && git stash pop`) before treating it as a regression.

- [ ] **Step 2: Verify the banned-phrase consistency test still passes**

The prompt edits touched `tailor_resume.md`, which that test reads:

```bash
source .venv/bin/activate && python -m unittest tests.test_banned_phrase_consistency -v
```

Expected: PASS

- [ ] **Step 3: Run the sample smoke test end-to-end**

```bash
source .venv/bin/activate && resume sample
```

Expected: completes and writes a PDF. Confirm the console shows one of the three research notices ("Company research complete for ... ", possibly with "(from a web search)" or "(from the job posting's own text)").

- [ ] **Step 4: Verify each tier against a real JD**

Run `resume run jds/<profile>/<file>` for each case and confirm the console notice names the expected tier:

1. A JD with a known-good `company_website` → "Company research complete for `<url>`." (Tier 1, unchanged behavior)
2. A LinkedIn-sourced JD with no `company_website`, for a real findable company → "(from a web search)" (Tier 2)
3. A JD for an obscure/private company with no meaningful search presence → "(from the job posting's own text)" (Tier 3). Open the resulting resume and confirm the Why section's facts don't overreach beyond what the JD itself states.

- [ ] **Step 5: Eyeball a vocabulary substitution**

For whichever run produced a non-empty `vocabulary_substitutions`, diff the affected bullet against its bullet-bank source:

```bash
source .venv/bin/activate && python -c "
import json, sys
p = sys.argv[1]
d = json.load(open(p))
for role in d.get('EXPERIENCE', []):
    for b in role.get('achievements', []):
        print(f\"{role.get('company')}: {b}\")
" output/<profile>/json/<file>_Resume.json
```

Expected: only the target noun changed. No metric, verb, or claim differs from the bullet bank's text.

- [ ] **Step 6: Document the tiering in CLAUDE.md**

Add to the `## Architecture notes` section:

```markdown
- **Company research always produces something.**
  `ResumeEngine.research_company()` tries three sources in order: the
  company's own site (scraped), a Google-Search-grounded Gemini writeup
  (trusted only when the model self-reports "high" confidence — many
  companies share a name), then the JD's own text. Which tier won is
  recorded on the result under `_research_source` and never reaches a
  prompt. All three tiers feed the same `research_company.md` extraction
  call, so there's exactly one place producing a `CompanyResearchSchema`
  — add new tiers by producing source text, not by adding a schema.
  Its `vocabulary_substitutions` field (e.g. `customers -> guests`)
  reaches the Summary and Why sections through prompt instructions, but
  reaches bullets **only** through
  `company_research.apply_vocabulary_substitutions_to_resume()`, a
  deterministic regex pass run just before Step 6 — bullets are
  pre-audited verified text, so the model is explicitly forbidden from
  rewording them for tone. See
  `docs/superpowers/specs/2026-08-11-company-research-tiered-fallback-design.md`.
```

- [ ] **Step 7: Commit**

```bash
git add CLAUDE.md
git commit -m "docs: describe the company-research tier chain in CLAUDE.md"
```

---

## Self-Review

**Spec coverage:** Goal 1 (always find something) → Tasks 4-5. Goal 2 (capture vocabulary) → Task 3. Goal 3 (reaches Summary/Why/bullets) → Tasks 1-2 (mechanism), 6 (wiring), 7 (prompts). Every spec component maps to a task: `research_company_via_search` → Task 4; `apply_vocabulary_substitutions` → Task 1; `apply_vocabulary_substitutions_to_resume` → Task 2; `research_company.md` edits → Task 3; schema field → Task 3; `format_company_research_block` → Task 3; `research_company()` rewrite → Task 5; Step 5.5/6 call site → Task 6; `tailor_resume.md` edits → Task 7; testing section → distributed across Tasks 1-7 plus Task 8's live verification.

**Two deliberate deviations from the spec,** both from facts checked against the code while writing this plan and both flagged inline: (1) nested `VocabularySubstitution` model instead of `"a -> b"` strings, because the spec's cited justification (`orchestrator.py:73-75`) is contradicted by `ExperienceEntry`'s docstring; (2) `EXPERIENCE[*].achievements[*]` instead of the spec's `work_experience[*].bullets[*]`, which is simply the wrong field name.

**Two gaps the spec did not cover,** both resolved here: (1) `research_company()` had no access to the JD text it needs for Tier 3 — `_parse_jd_data()` returns `{}` for plain-text JDs, so `jd_data` cannot be relied on to carry it; resolved with an optional `jd_text` parameter (Task 5, Step 4). (2) `research` is out of scope on the checkpoint-resume path, so the Step 6 call site would `NameError`; resolved by persisting the pairs into the checkpoint (Task 6).

**Placeholder scan:** no TBDs, no "add error handling" hand-waving, every step has runnable commands or literal code.

**Type consistency:** `substitutions` is a `list[dict]` with keys `generic_term`/`company_term` at every layer — schema (Task 3), pure function (Task 1), resume walker (Task 2), block formatter (Task 3), checkpoint (Task 6). `research_company_via_search` returns `str | None` consistently in Task 4's implementation, Task 4's tests, and Task 5's mocks.
