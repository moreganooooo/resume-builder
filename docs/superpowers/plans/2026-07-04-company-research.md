# Company Research (Cover Letter + Resume Tone-Mirroring) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fetch a company's own About/Mission/Careers pages (when known) and feed the resulting tone signals + traceable facts into both `build_tailored_coverletter` (Company Connection paragraph + tone-matching) and `build_tailored_resume` (completing what `tailor_resume.md` already assumes exists at lines 69/203, but never received).

**Architecture:** A plain `requests`/BeautifulSoup scraper (`company_research.py`, mirroring `scan_linkedin.py`'s established pattern) feeds a single Gemini call (`ResumeEngine.research_company()`) that extracts structured tone signals + facts. Both builder methods fold the result into their existing system-instruction context when present, and fall back to unchanged, pre-feature behavior when it's `None`.

**Tech Stack:** Python 3.10+, Pydantic, `requests` + `beautifulsoup4` (both already dependencies), the existing `GeminiClient`.

## Global Constraints

- No search-API fallback (Google/Bing) when direct page fetches are too thin — skip gracefully instead.
- No interactive/agentic research session — pure Python scraper + Gemini only.
- No domain-guessing when `company_website` is absent from the JD data — skip gracefully, never guess `companyname.com`.
- No changes to `build_tailored_resume`'s page-fit trim loop, validator, or checkpointing.
- Cover letter generation (`resume coverletter <jd_file>`) stays a fully separate, opt-in command — never auto-triggered by `tailor`/`run`.
- Every skip path in `research_company()` prints a clear, non-alarming terminal notice (not an error) and returns `None` — never raises, never blocks either caller.
- `MIN_USEFUL_CHARS = 200`, `EARLY_STOP_CHARS = 1500`, `MAX_TOTAL_CHARS = 6000` (exact thresholds from the spec).
- Spec: `docs/superpowers/specs/2026-07-04-company-research-design.md`.

---

### Task 1: `company_research.py` scraper module

**Files:**
- Create: `scripts/company_research.py`
- Test: `tests/test_company_research.py`

**Interfaces:**
- Consumes: nothing from other tasks (pure module, `requests`/`beautifulsoup4` only).
- Produces: `company_research.fetch_company_pages(company_website: str) -> str` (combined visible text, capped at `MAX_TOTAL_CHARS`, `""` if nothing useful found), `company_research.CANDIDATE_PATHS`, `company_research.MIN_USEFUL_CHARS`, `company_research.MAX_TOTAL_CHARS` (all module-level constants). Task 2's `ResumeEngine.research_company()` calls `fetch_company_pages` and reads `MIN_USEFUL_CHARS` directly from this module.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_company_research.py`:

```python
import os
import sys
import unittest
from unittest.mock import MagicMock, patch

SCRIPTS_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts")
sys.path.insert(0, SCRIPTS_DIR)

import company_research  # noqa: E402


def _response(status_code=200, text=""):
    resp = MagicMock()
    resp.status_code = status_code
    resp.text = text
    return resp


class TestCandidateUrls(unittest.TestCase):

    def test_adds_https_scheme_when_missing(self):
        urls = company_research._candidate_urls("acme.com")
        self.assertTrue(all(u.startswith("https://acme.com") for u in urls))

    def test_strips_trailing_slash_before_appending_paths(self):
        urls = company_research._candidate_urls("https://acme.com/")
        self.assertIn("https://acme.com/about", urls)
        self.assertNotIn("https://acme.com//about", urls)

    def test_includes_all_candidate_paths(self):
        urls = company_research._candidate_urls("https://acme.com")
        for path in company_research.CANDIDATE_PATHS:
            self.assertIn(f"https://acme.com{path}", urls)


class TestExtractVisibleText(unittest.TestCase):

    def test_strips_script_and_style_tags(self):
        html = "<html><head><style>.x{color:red}</style></head><body><script>evil()</script><p>Real content</p></body></html>"
        text = company_research._extract_visible_text(html)
        self.assertEqual(text, "Real content")

    def test_collapses_whitespace(self):
        html = "<p>Line one</p>\n\n<p>   Line   two   </p>"
        text = company_research._extract_visible_text(html)
        self.assertEqual(text, "Line one Line two")


class TestFetchCompanyPages(unittest.TestCase):

    @patch("company_research.requests.get")
    def test_returns_empty_string_when_all_candidates_fail(self, mock_get):
        mock_get.return_value = _response(status_code=404, text="")
        result = company_research.fetch_company_pages("acme.com")
        self.assertEqual(result, "")
        self.assertEqual(mock_get.call_count, len(company_research.CANDIDATE_PATHS))

    @patch("company_research.requests.get")
    def test_stops_early_once_enough_content_collected(self, mock_get):
        big_text = "<p>" + ("word " * 400) + "</p>"  # ~2000 chars visible, over EARLY_STOP_CHARS
        mock_get.return_value = _response(status_code=200, text=big_text)
        result = company_research.fetch_company_pages("acme.com")
        self.assertGreater(len(result), 0)
        self.assertEqual(mock_get.call_count, 1)

    @patch("company_research.requests.get")
    def test_combines_text_across_multiple_successful_pages(self, mock_get):
        mock_get.side_effect = (
            [
                _response(status_code=200, text="<p>About us content.</p>"),
                _response(status_code=404, text=""),
                _response(status_code=200, text="<p>Careers page content.</p>"),
            ]
            + [_response(status_code=404, text="")] * (len(company_research.CANDIDATE_PATHS) - 3)
        )
        result = company_research.fetch_company_pages("acme.com")
        self.assertIn("About us content.", result)
        self.assertIn("Careers page content.", result)

    @patch("company_research.requests.get")
    def test_caps_combined_text_at_max_total_chars(self, mock_get):
        huge_text = "<p>" + ("x" * 10000) + "</p>"
        mock_get.return_value = _response(status_code=200, text=huge_text)
        result = company_research.fetch_company_pages("acme.com")
        self.assertLessEqual(len(result), company_research.MAX_TOTAL_CHARS)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /Users/morganescott/resume-builder && source .venv/bin/activate && python -m unittest tests.test_company_research -v`
Expected: `ModuleNotFoundError: No module named 'company_research'` (file doesn't exist yet).

- [ ] **Step 3: Write the implementation**

Create `scripts/company_research.py`:

```python
"""
company_research.py — Fetches a company's About/Mission/Careers pages via
plain requests/BeautifulSoup (no browser automation, no search API) for
ResumeEngine.research_company() to feed into a Gemini call.

Deliberately not an agentic/WebFetch-driven process (career-ops's
approach) -- matches the plain-scraper pattern already proven in
scan_linkedin.py, keeping Claude's role bounded to build-time work, not
runtime operation.
"""

import re

import requests
from bs4 import BeautifulSoup

CANDIDATE_PATHS = ["/about", "/about-us", "/mission", "/values", "/culture", "/team", "/careers", "/jobs"]
MIN_USEFUL_CHARS = 200
EARLY_STOP_CHARS = 1500
MAX_TOTAL_CHARS = 6000
REQUEST_TIMEOUT_SECONDS = 10


def _candidate_urls(company_website: str) -> list:
    base = company_website.rstrip("/")
    if not base.startswith("http://") and not base.startswith("https://"):
        base = f"https://{base}"
    return [f"{base}{path}" for path in CANDIDATE_PATHS]


def _extract_visible_text(html: str) -> str:
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["script", "style"]):
        tag.decompose()
    text = soup.get_text(separator=" ")
    return re.sub(r"\s+", " ", text).strip()


def fetch_company_pages(company_website: str) -> str:
    """
    Tries each candidate path in order, collecting visible text until
    EARLY_STOP_CHARS is reached or all candidates are exhausted. Returns
    combined text (capped at MAX_TOTAL_CHARS), or "" if nothing useful was
    found. Network/HTTP errors on any single candidate are caught and
    skipped -- the function moves on rather than aborting.
    """
    collected = []
    total_chars = 0

    for url in _candidate_urls(company_website):
        try:
            response = requests.get(url, timeout=REQUEST_TIMEOUT_SECONDS)
        except requests.exceptions.RequestException:
            continue
        if response.status_code != 200:
            continue

        text = _extract_visible_text(response.text)
        if not text:
            continue

        collected.append(text)
        total_chars += len(text)
        if total_chars >= EARLY_STOP_CHARS:
            break

    combined = " ".join(collected)
    return combined[:MAX_TOTAL_CHARS]
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd /Users/morganescott/resume-builder && source .venv/bin/activate && python -m unittest tests.test_company_research -v`
Expected: all 8 tests pass.

- [ ] **Step 5: Run the full suite to confirm no regressions**

Run: `source .venv/bin/activate && python -m unittest discover -s tests`
Expected: `OK`, test count increased by 8 from the prior total (172 → 180).

- [ ] **Step 6: Commit**

```bash
git add scripts/company_research.py tests/test_company_research.py
git commit -m "$(cat <<'EOF'
Add company page scraper (requests/BeautifulSoup, no search API)

Part of company research (see
docs/superpowers/specs/2026-07-04-company-research-design.md). Mirrors
scan_linkedin.py's plain-scraper pattern -- no agentic session needed.

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
EOF
)"
```

---

### Task 2: `research_company.md`, `CompanyResearchSchema`, `ResumeEngine.research_company()`

**Files:**
- Create: `resume-engine/prompts/research_company.md`
- Modify: `scripts/orchestrator.py:7` (add `import company_research` near the top-level imports)
- Modify: `scripts/orchestrator.py:629` (add `CompanyResearchSchema` class, immediately after `CoverLetterSchema`, before `class CritiqueSchema`)
- Modify: `scripts/orchestrator.py:629` (add `_parse_jd_data` and `format_company_research_block` module-level functions in the same location, alongside the new schema)
- Modify: `scripts/orchestrator.py:1455` (add `research_company` method to `ResumeEngine`, between `evaluate_fit` and `build_tailored_coverletter`)

**Interfaces:**
- Consumes: `company_research.fetch_company_pages(str) -> str`, `company_research.MIN_USEFUL_CHARS` (Task 1); `self.load_prompt(filename) -> str` (existing); `GeminiClient.generate(...)`/`GeminiClient.parse_json(...)` (existing); module-level `BUILDER_MODEL` (existing).
- Produces: `_parse_jd_data(jd_text: str) -> dict` (best-effort JSON parse, `{}` on any failure), `format_company_research_block(research: dict) -> str` (formats a `CompanyResearchSchema`-shaped dict into the `=== COMPANY RESEARCH ===` context block), `ResumeEngine.research_company(self, jd_data: dict) -> dict | None`. Tasks 3 and 4 call all three of these exact names with these exact signatures.

There is no meaningful unit test for `research_company()` itself without mocking the Gemini API (this codebase's convention, per `dummy_jd.txt`, is a real live call instead) — Step 5 below is that verification.

- [ ] **Step 1: Write the prompt**

Create `resume-engine/prompts/research_company.md`:

```markdown
# Research Company

# Role

You are extracting tone signals and factual highlights from a company's own About/Mission/Careers page text, for later use in tailoring a cover letter and resume tone-mirroring. You are not writing anything customer-facing yourself.

# Task

Read the scraped company page text and extract:
1. **overall_tone_adjective** -- one short phrase describing the company's overall voice (e.g. "warm and mission-driven," "playful and irreverent," "measured and technical").
2. **register** -- "formal", "conversational", or "mixed".
3. **pronoun_framing** -- "we-centric" (community/company-first framing), "you-centric" (audience/customer-first framing), or "mixed".
4. **sentence_style** -- "short and punchy", "long and flowing", or "mixed".
5. **jargon_density** -- "high", "moderate", or "low".
6. **recurring_keywords** -- 1-3 brand words or phrases that genuinely repeat in the text (e.g. "impact", "bold", "rigorous"). Do not invent ones that aren't actually there.
7. **company_facts** -- 2-3 short, factual statements about the company's mission, product, or what they actually do, each one traceable directly to the provided text. Never invent a fact not present in the text.

# Rules

- Every `company_facts` entry must be grounded in the provided text -- if the text doesn't clearly support a fact, leave it out rather than guessing.
- If the text is thin or generic, it's fine for tone fields to be more general ("mixed", "moderate") rather than forcing a strong read that isn't supported.
- Do not editorialize or add opinion -- this is extraction, not commentary.

# Output

Respond with the structured company research JSON only: `overall_tone_adjective`, `register`, `pronoun_framing`, `sentence_style`, `jargon_density`, `recurring_keywords` (list), `company_facts` (list of 2-3).
```

- [ ] **Step 2: Add the import**

In `scripts/orchestrator.py`, find line 7:

```python
import requests
```

Change to:

```python
import requests
import company_research
```

- [ ] **Step 3: Add the schema and helper functions**

In `scripts/orchestrator.py`, find:

```python
class CritiqueSchema(BaseModel):
```

Insert immediately before it:

```python
class CompanyResearchSchema(BaseModel):
    overall_tone_adjective: str       = Field(description="One short phrase describing the company's overall voice.")
    register:               Literal["formal", "conversational", "mixed"]
    pronoun_framing:        Literal["we-centric", "you-centric", "mixed"]
    sentence_style:         Literal["short and punchy", "long and flowing", "mixed"]
    jargon_density:         Literal["high", "moderate", "low"]
    recurring_keywords:     List[str] = Field(description="1-3 brand words/phrases that genuinely repeat in the source text.")
    company_facts:          List[str] = Field(description="2-3 short, factual statements traceable directly to the source text.")


def _parse_jd_data(jd_text: str) -> dict:
    """Best-effort parse of a JD file's raw text as JSON; {} if it isn't
    (e.g. a plain-text JD, or one without a company_website field)."""
    try:
        data = json.loads(jd_text)
        return data if isinstance(data, dict) else {}
    except (json.JSONDecodeError, UnicodeDecodeError):
        return {}


def format_company_research_block(research: dict) -> str:
    """Formats a CompanyResearchSchema-shaped dict into the
    '=== COMPANY RESEARCH ===' context block both build_tailored_coverletter
    and build_tailored_resume fold into their system-instruction context."""
    return (
        "\n\n=== COMPANY RESEARCH ===\n"
        f"Overall tone: {research.get('overall_tone_adjective', '')}\n"
        f"Register: {research.get('register', '')} | Framing: {research.get('pronoun_framing', '')} | "
        f"Sentence style: {research.get('sentence_style', '')} | Jargon: {research.get('jargon_density', '')}\n"
        f"Recurring brand words: {', '.join(research.get('recurring_keywords', []))}\n"
        "Company facts (use at most 1-2, never fabricate beyond these):\n"
        + "\n".join(f"- {fact}" for fact in research.get('company_facts', []))
    )

```

- [ ] **Step 4: Add the method**

In `scripts/orchestrator.py`, find the blank line between `evaluate_fit`'s `return evaluation` and `def build_tailored_coverletter(`. Insert:

```python
    def research_company(self, jd_data: dict) -> dict | None:
        """
        Fetches a company's About/Mission/Careers pages (if a
        company_website is known in jd_data) and extracts tone signals +
        traceable facts via one Gemini call. Returns None (with a printed,
        non-alarming notice) if no website is known, pages are
        unreachable/too thin, or the model response can't be parsed --
        callers must treat None as "proceed exactly as if this feature
        didn't exist." See
        docs/superpowers/specs/2026-07-04-company-research-design.md.
        """
        company_website = jd_data.get("company_website")
        if not company_website:
            print("  ℹ️  Company research skipped: no company website known for this JD.")
            return None

        scraped_text = company_research.fetch_company_pages(company_website)
        if len(scraped_text) < company_research.MIN_USEFUL_CHARS:
            print(f"  ℹ️  Company research skipped: couldn't find enough usable content on {company_website}.")
            return None

        research_prompt = self.load_prompt("research_company.md")
        research_text, _ = GeminiClient.generate(
            model=BUILDER_MODEL,
            system_instruction=research_prompt,
            contents=f"=== SCRAPED COMPANY PAGE TEXT ===\n{scraped_text}",
            response_schema=CompanyResearchSchema,
            temperature=0.0,
        )
        research_data = GeminiClient.parse_json(research_text or "")
        if not research_data:
            print("  ℹ️  Company research skipped: model response couldn't be parsed.")
            return None

        print(f"  ✅ Company research complete for {company_website}.")
        return research_data

```

- [ ] **Step 5: Live verification (real network + real Gemini)**

Pick one of the already-scanned JobRight JDs (these have a real `company_website` field):

```bash
source .venv/bin/activate
python3 -c "
import sys, json
sys.path.insert(0, 'scripts')
import orchestrator

# Find a scanned JD with a real company_website
import glob
jd_data = None
for path in glob.glob('jds/*.json'):
    with open(path) as f:
        data = json.load(f)
    if data.get('company_website'):
        jd_data = data
        print('Using JD:', path, '| website:', data['company_website'])
        break

engine = orchestrator.ResumeEngine()
result = engine.research_company(jd_data)
print('---RESULT---')
print(json.dumps(result, indent=2) if result else 'None (skipped)')
"
```

Expected: prints which JD/website it used, then either a populated `CompanyResearchSchema` dict (tone fields + 2-3 `company_facts`) or a clear skip notice if that particular company's site didn't yield enough content — both are valid outcomes; the goal is confirming the method runs end-to-end without crashing and produces sensible output when it does succeed.

- [ ] **Step 6: Run the full test suite to confirm no regressions**

Run: `source .venv/bin/activate && python -m unittest discover -s tests`
Expected: `OK`, same test count as after Task 1 (this task added no new automated tests, per the note above).

- [ ] **Step 7: Commit**

```bash
git add resume-engine/prompts/research_company.md scripts/orchestrator.py
git commit -m "$(cat <<'EOF'
Add CompanyResearchSchema, research_company.md, and ResumeEngine.research_company()

Live-verified against a real scanned JD's company website. Part of
company research (see
docs/superpowers/specs/2026-07-04-company-research-design.md).

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
EOF
)"
```

---

### Task 3: Wire into `build_tailored_coverletter`

**Files:**
- Modify: `scripts/orchestrator.py:1469` (fold in `research_company()` call)
- Modify: `resume-engine/prompts/tailor_coverletter.md` (replace the "no company research" rule)

**Interfaces:**
- Consumes: `_parse_jd_data`, `format_company_research_block`, `ResumeEngine.research_company` (all Task 2).
- Produces: no new interface — `build_tailored_coverletter`'s existing signature/return shape is unchanged, just its behavior when research succeeds.

- [ ] **Step 1: Update the prompt**

In `resume-engine/prompts/tailor_coverletter.md`, find:

```
- No company research beyond what's in the job description itself -- do not claim to know anything about the company's culture, mission, or values that isn't stated in the JD text. (A later pass will add real company research; this version deliberately doesn't fake it.)
```

Replace with:

```
- If a `=== COMPANY RESEARCH ===` block is present in the context, use it for exactly two things: (1) the Company Connection -- tie **one** researched fact to a real piece of Morgan's background, avoiding generic flattery ("I've always admired your innovative culture") in favor of something specific and true; (2) tone-matching per this register: mission-driven org -> warmer, more resonant; playful startup -> sharper, slightly more personality; conventional B2B SaaS -> measured, crisp, lightly distinctive; advocacy/impact org -> purposeful, human, values-aware. Never copy the company's own phrases verbatim.
- If no `=== COMPANY RESEARCH ===` block is present, do not claim to know anything about the company's culture, mission, or values beyond what's stated in the JD text itself -- proceed without it, exactly as before.
```

- [ ] **Step 2: Wire the method call**

In `scripts/orchestrator.py`, find (inside `build_tailored_coverletter`):

```python
        coverletter_prompt = self.load_prompt("tailor_coverletter.md")
        background_context = self.build_audit_static_prefix()
        system_instruction = f"{coverletter_prompt}\n\n{background_context}"
```

Change to:

```python
        jd_data = _parse_jd_data(jd_text)
        research = self.research_company(jd_data)
        research_block = format_company_research_block(research) if research else ""

        coverletter_prompt = self.load_prompt("tailor_coverletter.md")
        background_context = self.build_audit_static_prefix()
        system_instruction = f"{coverletter_prompt}\n\n{background_context}{research_block}"
```

- [ ] **Step 3: Run the full test suite to confirm no regressions**

Run: `source .venv/bin/activate && python -m unittest discover -s tests`
Expected: `OK`, same test count as after Task 2.

- [ ] **Step 4: Live verification (real network + real Gemini)**

```bash
cp jds/completed/smoketest_dummy_jd.json jds/smoketest_research_cl.json
source .venv/bin/activate
python3 -c "
import sys
sys.path.insert(0, 'scripts')
import orchestrator
engine = orchestrator.ResumeEngine()
result = engine.build_tailored_coverletter('jds/smoketest_research_cl.json')
print('company_name:', result.get('company_name'))
for i, p in enumerate(result.get('body_paragraphs', [])):
    print(f'  paragraph {i+1}:', p)
"
```

Expected: since this fixture JD has no `company_website` field, expect the `"ℹ️  Company research skipped: no company website known for this JD."` notice and an otherwise-unchanged cover letter (confirms the fallback path). Then clean up:

```bash
rm -f jds/smoketest_research_cl.json output/json/smoketest_research_cl_coverletter.json output/html/smoketest_research_cl_coverletter.html output/pdf/smoketest_research_cl_coverletter.pdf
```

- [ ] **Step 5: Commit**

```bash
git add scripts/orchestrator.py resume-engine/prompts/tailor_coverletter.md
git commit -m "$(cat <<'EOF'
Fold company research into build_tailored_coverletter()

Live-verified the fallback path (no company_website -> notice printed,
letter unchanged). Part of company research (see
docs/superpowers/specs/2026-07-04-company-research-design.md).

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
EOF
)"
```

---

### Task 4: Wire into `build_tailored_resume`

**Files:**
- Modify: `scripts/orchestrator.py:1676` (fold in `research_company()` call inside the fresh-build branch)
- Modify: `resume-engine/prompts/tailor_resume.md` (clarify lines 69 and 203 to reference the new context block, add no-fabrication guardrails)

**Interfaces:**
- Consumes: `_parse_jd_data`, `format_company_research_block`, `ResumeEngine.research_company` (Task 2).
- Produces: no new interface — `build_tailored_resume`'s existing signature/return shape is unchanged.

This is the highest-stakes task in this plan: `build_tailored_resume` is the most complex, already-proven part of the system (page-fit trim loop, validator, checkpointing). Step 5 below is a real before/after comparison, not just a single smoke test.

- [ ] **Step 1: Update the Summary Rules**

In `resume-engine/prompts/tailor_resume.md`, find:

```
- Mirror the company's tone (formal vs conversational, jargon level, keyword density) — apply to tone only, never to facts
```

Replace with:

```
- Mirror the company's tone (formal vs conversational, jargon level, keyword density) — apply to tone only, never to facts
- Use the `=== COMPANY RESEARCH ===` context block (if present) as the actual source for this tone-mirroring — its register/framing/jargon_density/recurring_keywords fields describe the real signal to match. If no such block is present, skip tone-mirroring entirely rather than guessing from the JD text alone
```

- [ ] **Step 2: Update the Why section rule**

In the same file, find:

```
- Must reference specific company research details and connect each to verified facts from Morgan's history
```

Replace with:

```
- Must reference specific company research details and connect each to verified facts from Morgan's history
- Source those "specific company research details" ONLY from the `=== COMPANY RESEARCH ===` context block's `company_facts` field, if present. If no such block is present, do not include this Why section at all — set SECTION_WHY and WHY_TEXT to empty strings rather than inventing research-sounding details to satisfy this rule
```

- [ ] **Step 3: Wire the method call**

In `scripts/orchestrator.py`, find (inside `build_tailored_resume`'s fresh-build branch):

```python
            kb_context = self.load_knowledge_base()

            # Gap 1: KB goes into system_instruction, not contents, so the
            # ~105k-token kb_context forms a stable, cacheable prefix if
            # Gemini's automatic caching kicks in across nearby calls (e.g.
            # consecutive JDs in batch mode reusing the same kb_context
            # bytes) -- NOT within this one call, and NOT reused by the
            # retry/fix loop or trim loop below, both of which deliberately
            # use build_prompt alone (no kb_context) to keep those calls
            # cheap. The variable tail (JD + bullets) sits alone in
            # combined_contents.
            builder_system = f"{build_prompt}\n\n{kb_context}"
```

Change to:

```python
            kb_context = self.load_knowledge_base()

            jd_data = _parse_jd_data(jd_text)
            research = self.research_company(jd_data)
            research_block = format_company_research_block(research) if research else ""

            # Gap 1: KB goes into system_instruction, not contents, so the
            # ~105k-token kb_context forms a stable, cacheable prefix if
            # Gemini's automatic caching kicks in across nearby calls (e.g.
            # consecutive JDs in batch mode reusing the same kb_context
            # bytes) -- NOT within this one call, and NOT reused by the
            # retry/fix loop or trim loop below, both of which deliberately
            # use build_prompt alone (no kb_context) to keep those calls
            # cheap. The variable tail (JD + bullets) sits alone in
            # combined_contents. research_block is appended after kb_context
            # for the same reason -- it's per-JD variable content, but small
            # enough that keeping it out of the cacheable prefix costs
            # little and keeps the prefix identical across JDs targeting
            # different companies.
            builder_system = f"{build_prompt}\n\n{kb_context}{research_block}"
```

- [ ] **Step 4: Run the full test suite to confirm no regressions**

Run: `source .venv/bin/activate && python -m unittest discover -s tests`
Expected: `OK`, same test count as after Task 3.

- [ ] **Step 5: Live verification — before/after comparison (real network + real Gemini)**

First, find a scanned JD with a real `company_website` and run the full tailor pipeline on it:

```bash
python3 -c "
import glob, json, shutil
for path in glob.glob('jds/*.json'):
    with open(path) as f:
        data = json.load(f)
    if data.get('company_website'):
        shutil.copy(path, 'jds/smoketest_research_resume.json')
        print('Using:', path, '| website:', data['company_website'])
        break
"
source .venv/bin/activate
python scripts/cli.py tailor jds/smoketest_research_resume.json
```

Expected: console output shows either `"✅ Company research complete for {website}."` or one of the skip notices, followed by the pipeline completing exactly as it always has (same 7 steps, same validator/critique behavior). If research succeeded, open the resulting JSON and confirm the Why section (if present) references a real, traceable fact rather than something generic-sounding:

```bash
cat output/json/smoketest_research_resume_resume.json | python3 -c "import json,sys; d=json.load(sys.stdin); print('WHY_TEXT:', d.get('WHY_TEXT', '(none)'))"
```

Then, confirm the fallback path with the no-website fixture:

```bash
cp jds/completed/smoketest_dummy_jd.json jds/smoketest_research_fallback.json
python scripts/cli.py tailor jds/smoketest_research_fallback.json
```

Expected: `"ℹ️  Company research skipped: no company website known for this JD."`, and the resume output is otherwise unchanged in shape from prior tailor runs (same steps, same validator behavior) — confirming JDs without a known company site are completely unaffected by this feature.

Clean up all test artifacts:

```bash
rm -f jds/smoketest_research_resume.json jds/smoketest_research_fallback.json \
  output/json/smoketest_research_resume_resume.json output/html/smoketest_research_resume_resume.html output/pdf/smoketest_research_resume_resume.pdf \
  output/json/smoketest_research_fallback_resume.json output/html/smoketest_research_fallback_resume.html output/pdf/smoketest_research_fallback_resume.pdf
```

(If either run left a JD tracker/`applications.md` row, that's expected and fine to leave — same as any other completed build; it's real pipeline output, not a defect.)

- [ ] **Step 6: Commit**

```bash
git add scripts/orchestrator.py resume-engine/prompts/tailor_resume.md
git commit -m "$(cat <<'EOF'
Fold company research into build_tailored_resume()

Completes what tailor_resume.md's Summary Rules (line 69) and Why section
(line 203) already assumed existed but never received -- tone-mirroring
and Why-section research claims are now either grounded in real scraped
data or skipped entirely, never fabricated. Live-verified both the
research-succeeds path (real Why-section fact) and the no-website
fallback path (fully unchanged output). Completes company research (see
docs/superpowers/specs/2026-07-04-company-research-design.md).

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
EOF
)"
```
