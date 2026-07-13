# Bootstrap Profile Personalization Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a new Phase 0.5 to the bootstrap flow that guesses and confirms `profile.yml`, `portals.yml`, drafts `cv.md` and `user-background-guide.md`, and derives the `verified_*` ledger — all from documents already ingested in Phase 0, with terminal guess-confirm-or-edit prompts for anything that can't be safely guessed.

**Architecture:** A new `bootstrap_profile.py` orchestrator runs between Phase 0 (`run_ingestion()`) and the existing six-stage pipeline. It reads Phase 0's `checkpoint.json`/`timeline.json`/`bullet-bank-draft.csv` as guess sources, adds four new extraction functions to `bootstrap_extractors.py`, and reuses `rewrite_bullets.py`'s existing rewrite machinery for `cv.md`'s draft polish.

**Tech Stack:** Python 3.10+, `pydantic`, `questionary`, `pandas`, stdlib `unittest`, `google-genai` SDK, `gemini_client.GeminiClient`.

## Global Constraints

- `--yes` skips the six-stage pipeline's confirmation gates only; Phase 0.5's interactive prompts always run regardless of `--yes`.
- `--dry-run` is a true no-input preview for Phase 0.5: prints every guess/prompt/would-be-written file, calls no API, prompts for nothing, writes nothing.
- Never invent content for `profile.yml`'s `archetypes`/`narrative`/`superpowers`/`background_context`/`industries_of_genuine_fit`/`companies_previously_applied`/`deal_breakers`/`proof_points`/`management_evidence`/`compensation`, or for `verified_facts.json`/`verified-claims.csv`/`evidence_graph.json`/`evidence-guide.csv`/`extracted-screenshot-metrics.csv`. These are scaffolded with guided comments and empty values only.
- `key_recommendations` in `profile.yml` is only ever auto-filled from a real, already-uploaded recommendation letter — never invented.
- `morgan-background-guide.md` is renamed to `user-background-guide.md` everywhere it's referenced in the active pipeline (`orchestrator.py`, `rewrite_bullets.py`); the archived `scripts/archive/rewrite_bullets_backup.py` is dead code (confirmed via grep — nothing imports from `scripts/archive/`) and is out of scope.
- Follow the existing TDD cadence already established in this codebase: write failing test -> verify fail -> implement -> verify pass -> commit, for every task.

---

### Task 1: `bootstrap_extractors.py` — four new extraction functions

**Files:**
- Modify: `scripts/bootstrap_extractors.py` (append)
- Test: `tests/test_bootstrap_profile_extractors.py`

**Interfaces:**
- Consumes: `EXTRACTION_MODEL`, `GeminiClient`, `_generate_from_upload`, `genai` (all already in `bootstrap_extractors.py` from the earlier bootstrap plan).
- Produces (used by Task 3-7):
  - `class ContactInfo(BaseModel)` — `full_name`, `email`, `phone`, `location`, `linkedin_url`, `portfolio_url`, all `Optional[str] = None`.
  - `extract_contact_info(*, text: str | None = None, upload_path: str | None = None, dry_run: bool = False) -> ContactInfo`
  - `class RecommendationQuote(BaseModel)` — `name`, `title`, `quote`, all `Optional[str] = None`.
  - `extract_recommendation_quote(*, text: str | None = None, upload_path: str | None = None, dry_run: bool = False) -> RecommendationQuote | None` — returns `None` if no usable quote was found.
  - `class RoleSuggestions(BaseModel)` — `secondary_roles: list[str]`.
  - `suggest_secondary_roles(primary_roles: list[str], achievements_text: str, dry_run: bool = False) -> list[str]`
  - `draft_background_guide(source_texts: list[str], dry_run: bool = False) -> str`
  - `class LedgerEntry(BaseModel)` — `label: str`, `value: str`.
  - `class LedgerExtraction(BaseModel)` — `metrics: list[LedgerEntry]`, `tools: list[str]`, `projects: list[str]`, all `Field(default_factory=list)`.
  - `extract_ledger_entries(achievements_text: str, dry_run: bool = False) -> LedgerExtraction`

- [ ] **Step 1: Write the failing tests**

```python
import os
import sys
import unittest
from unittest.mock import patch

SCRIPTS_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts")
sys.path.insert(0, SCRIPTS_DIR)

import bootstrap_extractors  # noqa: E402


class TestExtractContactInfo(unittest.TestCase):

    @patch("bootstrap_extractors.GeminiClient.generate")
    def test_parses_contact_fields(self, mock_generate):
        mock_generate.return_value = (
            '{"full_name": "Jamie Rivera", "email": "jamie@example.com", '
            '"phone": "555-0100", "location": "Austin, TX", '
            '"linkedin_url": "linkedin.com/in/jamierivera", "portfolio_url": null}',
            {},
        )
        info = bootstrap_extractors.extract_contact_info(text="fake resume header text")
        self.assertEqual(info.full_name, "Jamie Rivera")
        self.assertEqual(info.email, "jamie@example.com")
        self.assertIsNone(info.portfolio_url)

    def test_requires_exactly_one_of_text_or_upload_path(self):
        with self.assertRaises(ValueError):
            bootstrap_extractors.extract_contact_info()
        with self.assertRaises(ValueError):
            bootstrap_extractors.extract_contact_info(text="a", upload_path="b")

    def test_dry_run_returns_blank_contact_info(self):
        with patch("bootstrap_extractors.GeminiClient.generate") as mock_generate:
            info = bootstrap_extractors.extract_contact_info(text="some text", dry_run=True)
            mock_generate.assert_not_called()
            self.assertIsNone(info.full_name)


class TestExtractRecommendationQuote(unittest.TestCase):

    @patch("bootstrap_extractors.GeminiClient.generate")
    def test_parses_quote_and_attribution(self, mock_generate):
        mock_generate.return_value = (
            '{"name": "Alex Chen", "title": "VP Marketing", '
            '"quote": "One of the strongest writers I have worked with."}',
            {},
        )
        quote = bootstrap_extractors.extract_recommendation_quote(text="fake letter text")
        self.assertEqual(quote.name, "Alex Chen")
        self.assertEqual(quote.title, "VP Marketing")

    @patch("bootstrap_extractors.GeminiClient.generate")
    def test_returns_none_when_no_quote_found(self, mock_generate):
        mock_generate.return_value = ('{"name": null, "title": null, "quote": null}', {})
        quote = bootstrap_extractors.extract_recommendation_quote(text="not actually a letter")
        self.assertIsNone(quote)

    def test_dry_run_returns_none(self):
        with patch("bootstrap_extractors.GeminiClient.generate") as mock_generate:
            quote = bootstrap_extractors.extract_recommendation_quote(text="some text", dry_run=True)
            mock_generate.assert_not_called()
            self.assertIsNone(quote)


class TestSuggestSecondaryRoles(unittest.TestCase):

    @patch("bootstrap_extractors.GeminiClient.generate")
    def test_returns_suggested_roles(self, mock_generate):
        mock_generate.return_value = (
            '{"secondary_roles": ["Customer Education Specialist", "Customer Adoption Specialist"]}',
            {},
        )
        roles = bootstrap_extractors.suggest_secondary_roles(
            ["Marketing Manager"], "Led onboarding programs and campaign automation."
        )
        self.assertEqual(roles, ["Customer Education Specialist", "Customer Adoption Specialist"])

    def test_dry_run_returns_empty_list(self):
        with patch("bootstrap_extractors.GeminiClient.generate") as mock_generate:
            roles = bootstrap_extractors.suggest_secondary_roles(["Marketing Manager"], "text", dry_run=True)
            mock_generate.assert_not_called()
            self.assertEqual(roles, [])


class TestDraftBackgroundGuide(unittest.TestCase):

    @patch("bootstrap_extractors.GeminiClient.generate")
    def test_returns_generated_prose(self, mock_generate):
        mock_generate.return_value = ("A marketer who blends writing and systems thinking.", {})
        draft = bootstrap_extractors.draft_background_guide(["resume summary text", "rec letter text"])
        self.assertEqual(draft, "A marketer who blends writing and systems thinking.")

    def test_dry_run_returns_empty_string(self):
        with patch("bootstrap_extractors.GeminiClient.generate") as mock_generate:
            draft = bootstrap_extractors.draft_background_guide(["text"], dry_run=True)
            mock_generate.assert_not_called()
            self.assertEqual(draft, "")


class TestExtractLedgerEntries(unittest.TestCase):

    @patch("bootstrap_extractors.GeminiClient.generate")
    def test_parses_metrics_tools_projects(self, mock_generate):
        mock_generate.return_value = (
            '{"metrics": [{"label": "Reply rate", "value": "22%"}], '
            '"tools": ["Salesforce", "Outreach.io"], "projects": ["Content Committee"]}',
            {},
        )
        result = bootstrap_extractors.extract_ledger_entries("Grew reply rate to 22% using Outreach.io.")
        self.assertEqual(len(result.metrics), 1)
        self.assertEqual(result.metrics[0].value, "22%")
        self.assertIn("Salesforce", result.tools)
        self.assertIn("Content Committee", result.projects)

    def test_dry_run_returns_empty_extraction(self):
        with patch("bootstrap_extractors.GeminiClient.generate") as mock_generate:
            result = bootstrap_extractors.extract_ledger_entries("some achievements", dry_run=True)
            mock_generate.assert_not_called()
            self.assertEqual(result.metrics, [])
            self.assertEqual(result.tools, [])
            self.assertEqual(result.projects, [])


if __name__ == "__main__":
    unittest.main()
```

Save as `tests/test_bootstrap_profile_extractors.py`.

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m unittest tests.test_bootstrap_profile_extractors -v`
Expected: FAIL with `AttributeError: module 'bootstrap_extractors' has no attribute 'ContactInfo'` (and similarly for the other new names).

- [ ] **Step 3: Write the implementation**

Append to the end of `scripts/bootstrap_extractors.py`:

```python
class ContactInfo(BaseModel):
    full_name: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = None
    location: Optional[str] = None
    linkedin_url: Optional[str] = None
    portfolio_url: Optional[str] = None


class RecommendationQuote(BaseModel):
    name: Optional[str] = None
    title: Optional[str] = None
    quote: Optional[str] = None


class RoleSuggestions(BaseModel):
    secondary_roles: list[str] = Field(default_factory=list)


class LedgerEntry(BaseModel):
    label: str
    value: str


class LedgerExtraction(BaseModel):
    metrics: list[LedgerEntry] = Field(default_factory=list)
    tools: list[str] = Field(default_factory=list)
    projects: list[str] = Field(default_factory=list)


_CONTACT_INFO_PROMPT = """
Extract this person's contact/identity information from the document text:
full name, email, phone, location (city/state), LinkedIn profile URL, and
portfolio/personal website URL if present. Use null for any field not
explicitly present in the text -- never invent a value.
"""

_RECOMMENDATION_QUOTE_PROMPT = """
This document is a letter of recommendation written about this person by
someone else. Extract the single strongest, most specific endorsing quote
from the letter, along with the name and title of the person who wrote it,
if stated. Use null for any field not explicitly present -- never invent
a name, title, or quote that isn't really in the letter.
"""

_SECONDARY_ROLES_PROMPT = """
Given a person's primary target job titles and a sample of their real
achievements, suggest 2-3 adjacent job titles they could also reasonably
target -- roles that draw on the same underlying skills but aren't
identical to the primary titles. Only suggest real, standard job titles;
do not invent a title that wouldn't make sense to a recruiter.
"""

_BACKGROUND_GUIDE_PROMPT = """
You are drafting a short narrative career-background guide from this
person's own resume/LinkedIn summary, recommendation-letter excerpts, and
achievement notes. Write 2-4 short paragraphs in third person describing
how their background/skills came together and what makes their combination
of experience distinctive. Only describe things directly supported by the
source text -- do not invent employers, dates, or accomplishments not
present in the source. If the source material is too thin to say anything
specific, write a short, honest, general paragraph instead of padding it
with invented detail.
"""

_LEDGER_PROMPT = """
Given a list of resume achievement bullets, extract three things:
- metrics: every quantified result mentioned, as a (label, value) pair
  where value is the number/stat exactly as written (e.g. "22% reply rate")
- tools: every named tool, platform, or piece of software mentioned
- projects: every named project or initiative mentioned
Only include things explicitly stated in the text. Do not invent numbers,
tool names, or project names that aren't there.
"""


def extract_contact_info(
    *, text: str | None = None, upload_path: str | None = None, dry_run: bool = False,
) -> ContactInfo:
    """Extracts identity/contact fields from a resume or LinkedIn export's
    text. Exactly one of text or upload_path must be set."""
    if (text is None) == (upload_path is None):
        raise ValueError("extract_contact_info requires exactly one of text or upload_path")

    if dry_run:
        print("[DRY RUN] would extract contact info.")
        return ContactInfo()

    if upload_path is not None:
        raw = _generate_from_upload(upload_path, _CONTACT_INFO_PROMPT, ContactInfo)
    else:
        raw, _ = GeminiClient.generate(
            model=EXTRACTION_MODEL, system_instruction=_CONTACT_INFO_PROMPT,
            contents=text, response_schema=ContactInfo, temperature=0.0,
        )
    data = GeminiClient.parse_json(raw) if isinstance(raw, str) else (raw or {})
    return ContactInfo(**data) if data else ContactInfo()


def extract_recommendation_quote(
    *, text: str | None = None, upload_path: str | None = None, dry_run: bool = False,
) -> RecommendationQuote | None:
    """Extracts a real quote + attribution from a recommendation letter.
    Returns None if no usable quote was found. Exactly one of text or
    upload_path must be set."""
    if (text is None) == (upload_path is None):
        raise ValueError("extract_recommendation_quote requires exactly one of text or upload_path")

    if dry_run:
        print("[DRY RUN] would extract a recommendation quote.")
        return None

    if upload_path is not None:
        raw = _generate_from_upload(upload_path, _RECOMMENDATION_QUOTE_PROMPT, RecommendationQuote)
    else:
        raw, _ = GeminiClient.generate(
            model=EXTRACTION_MODEL, system_instruction=_RECOMMENDATION_QUOTE_PROMPT,
            contents=text, response_schema=RecommendationQuote, temperature=0.0,
        )
    data = GeminiClient.parse_json(raw) if isinstance(raw, str) else (raw or {})
    if not data.get("quote"):
        return None
    return RecommendationQuote(**data)


def suggest_secondary_roles(
    primary_roles: list[str], achievements_text: str, dry_run: bool = False,
) -> list[str]:
    """Suggests 2-3 adjacent target job titles based on confirmed primary
    roles and a sample of real achievement text."""
    if dry_run:
        print("[DRY RUN] would suggest secondary target roles.")
        return []

    raw, _ = GeminiClient.generate(
        model=EXTRACTION_MODEL, system_instruction=_SECONDARY_ROLES_PROMPT,
        contents=f"Primary roles: {', '.join(primary_roles)}\n\nAchievements:\n{achievements_text[:4000]}",
        response_schema=RoleSuggestions, temperature=0.0,
    )
    data = GeminiClient.parse_json(raw)
    return data.get("secondary_roles", [])


def draft_background_guide(source_texts: list[str], dry_run: bool = False) -> str:
    """Synthesizes a short narrative background guide from resume/rec-letter/
    achievement-notes text already gathered during bootstrap ingestion."""
    if dry_run:
        print("[DRY RUN] would draft a background guide.")
        return ""

    combined = "\n\n---\n\n".join(t for t in source_texts if t)[:8000]
    raw, _ = GeminiClient.generate(
        model=EXTRACTION_MODEL, system_instruction=_BACKGROUND_GUIDE_PROMPT,
        contents=combined, temperature=0.4,
    )
    return (raw or "").strip()


def extract_ledger_entries(achievements_text: str, dry_run: bool = False) -> LedgerExtraction:
    """Derives simple metrics/tools/projects lists from already-extracted
    achievement bullets, for the verified_metrics/tools/projects.json
    ledger files."""
    if dry_run:
        print("[DRY RUN] would extract ledger entries (metrics/tools/projects).")
        return LedgerExtraction()

    raw, _ = GeminiClient.generate(
        model=EXTRACTION_MODEL, system_instruction=_LEDGER_PROMPT,
        contents=achievements_text[:6000], response_schema=LedgerExtraction, temperature=0.0,
    )
    data = GeminiClient.parse_json(raw)
    return LedgerExtraction(**data) if data else LedgerExtraction()
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m unittest tests.test_bootstrap_profile_extractors -v`
Expected: all tests PASS.

- [ ] **Step 5: Commit**

```bash
git add scripts/bootstrap_extractors.py tests/test_bootstrap_profile_extractors.py
git commit -m "Add contact-info, recommendation-quote, role-suggestion, background-guide, and ledger extraction"
```

---

### Task 2: Rename `morgan-background-guide.md` -> `user-background-guide.md`

**Files:**
- Modify: `scripts/rewrite_bullets.py:43,119,608`
- Modify: `scripts/orchestrator.py:207`
- Rename: `resume-engine/knowledge_base/morgan-background-guide.md` -> `resume-engine/knowledge_base/user-background-guide.md`

**Interfaces:**
- Consumes: nothing new.
- Produces: `rewrite_bullets.KB_BACKGROUND` now points at `user-background-guide.md`; every existing consumer of that constant is unaffected since the constant's usage sites don't change, only its value.

- [ ] **Step 1: Rename the file**

```bash
git mv resume-engine/knowledge_base/morgan-background-guide.md resume-engine/knowledge_base/user-background-guide.md
```

- [ ] **Step 2: Update `scripts/rewrite_bullets.py`**

Line 43 (a comment inside a docstring):

```python
  - user-background-guide.md       → tag-keyed summary
```

Line 119:

```python
KB_BACKGROUND       = os.path.join(KB_DIR, "user-background-guide.md")
```

Line 608:

```python
        self.bg_raw            = load_text_file(KB_BACKGROUND,        "user-background-guide.md")
```

- [ ] **Step 3: Update `scripts/orchestrator.py`**

Line 207, inside `KB_ALLOWLIST`:

```python
    "user-background-guide.md",
```

(Keep the list alphabetically sorted per the existing comment above `KB_ALLOWLIST` -- `"user-background-guide.md"` sorts after `"treering-archive-readme.md"` and before `"verified-claims.csv"`, so its position in the list does not change.)

- [ ] **Step 4: Run the full existing test suite to confirm no regressions**

Run: `python -m unittest discover -s tests -v`
Expected: every test PASSES, including all pre-existing tests untouched by this rename.

- [ ] **Step 5: Commit**

```bash
git add scripts/rewrite_bullets.py scripts/orchestrator.py \
  resume-engine/knowledge_base/morgan-background-guide.md \
  resume-engine/knowledge_base/user-background-guide.md
git commit -m "Rename morgan-background-guide.md to user-background-guide.md"
```

---

### Task 3: `bootstrap_profile.py` — identity/role guessing, interactive prompts, `profile.yml`

**Files:**
- Create: `scripts/bootstrap_profile.py`
- Test: `tests/test_bootstrap_profile.py`

**Interfaces:**
- Consumes: `bootstrap_bullet_bank.{SOURCE_DOCS_DIR, TIMELINE_PATH, CHECKPOINT_PATH, DRAFT_CSV_PATH, KB_DIR}` (existing); `bootstrap_extractors.{detect_file_kind, convert_legacy_doc_to_pdf, extract_local_text, extract_contact_info, extract_recommendation_quote, suggest_secondary_roles, ContactInfo, RecommendationQuote}` (existing + Task 1); `cli_art.QUESTIONARY_STYLE` (existing).
- Produces (used by Task 4-8):
  - Module-level path constants: `PROFILE_YML_PATH`, `PORTALS_YML_PATH`, `CV_MD_PATH`, `BACKGROUND_GUIDE_PATH`, `VERIFIED_METRICS_PATH`, `VERIFIED_TOOLS_PATH`, `VERIFIED_PROJECTS_PATH`, `VERIFIED_FACTS_PATH`, `VERIFIED_CLAIMS_PATH`, `EVIDENCE_GRAPH_PATH`, `EVIDENCE_GUIDE_PATH`, `SCREENSHOT_METRICS_PATH`, `RECRUITER_PATTERNS_PATH`.
  - `_load_checkpoint() -> dict`, `_load_timeline() -> list[dict]`, `_achievements_summary_text() -> str`, `_resolve_text_or_upload(path: str) -> tuple[str | None, str | None]`.
  - `_guess_contact_info(checkpoint: dict, dry_run: bool = False) -> bootstrap_extractors.ContactInfo`
  - `_guess_primary_roles(timeline: list[dict]) -> list[str]`
  - `_guess_recommendations(checkpoint: dict, dry_run: bool = False) -> list[bootstrap_extractors.RecommendationQuote]`
  - `collect_identity(dry_run: bool = False) -> dict` -- returns a dict with keys `full_name, email, phone, location, linkedin_url, portfolio_url, extra_link, primary_roles, secondary_roles, remote_preference`.
  - `write_profile_yml(identity: dict, recommendations: list) -> None`

- [ ] **Step 1: Write the failing tests**

```python
import json
import os
import shutil
import sys
import tempfile
import unittest
from unittest.mock import patch

SCRIPTS_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts")
sys.path.insert(0, SCRIPTS_DIR)

import bootstrap_bullet_bank  # noqa: E402
import bootstrap_extractors  # noqa: E402
import bootstrap_profile  # noqa: E402


class BootstrapProfileTestCase(unittest.TestCase):
    """Redirects every relevant path constant to a fresh temp dir per test."""

    def setUp(self):
        self.tmp_dir = tempfile.mkdtemp()
        self.bootstrap_dir = os.path.join(self.tmp_dir, "bootstrap")
        bootstrap_bullet_bank.BOOTSTRAP_DIR = self.bootstrap_dir
        bootstrap_bullet_bank.SOURCE_DOCS_DIR = os.path.join(self.bootstrap_dir, "source_documents")
        bootstrap_bullet_bank.TIMELINE_PATH = os.path.join(self.bootstrap_dir, "timeline.json")
        bootstrap_bullet_bank.CHECKPOINT_PATH = os.path.join(self.bootstrap_dir, "checkpoint.json")
        bootstrap_bullet_bank.DRAFT_CSV_PATH = os.path.join(self.bootstrap_dir, "bullet-bank-draft.csv")
        os.makedirs(bootstrap_bullet_bank.SOURCE_DOCS_DIR, exist_ok=True)

        bootstrap_profile.PROFILE_YML_PATH = os.path.join(self.tmp_dir, "profile.yml")
        bootstrap_profile.PORTALS_YML_PATH = os.path.join(self.tmp_dir, "portals.yml")
        bootstrap_profile.CV_MD_PATH = os.path.join(self.tmp_dir, "cv.md")
        bootstrap_profile.BACKGROUND_GUIDE_PATH = os.path.join(self.tmp_dir, "user-background-guide.md")
        bootstrap_profile.VERIFIED_METRICS_PATH = os.path.join(self.tmp_dir, "verified_metrics.json")
        bootstrap_profile.VERIFIED_TOOLS_PATH = os.path.join(self.tmp_dir, "verified_tools.json")
        bootstrap_profile.VERIFIED_PROJECTS_PATH = os.path.join(self.tmp_dir, "verified_projects.json")
        bootstrap_profile.VERIFIED_FACTS_PATH = os.path.join(self.tmp_dir, "verified_facts.json")
        bootstrap_profile.VERIFIED_CLAIMS_PATH = os.path.join(self.tmp_dir, "verified-claims.csv")
        bootstrap_profile.EVIDENCE_GRAPH_PATH = os.path.join(self.tmp_dir, "evidence_graph.json")
        bootstrap_profile.EVIDENCE_GUIDE_PATH = os.path.join(self.tmp_dir, "evidence-guide.csv")
        bootstrap_profile.SCREENSHOT_METRICS_PATH = os.path.join(self.tmp_dir, "extracted-screenshot-metrics.csv")
        bootstrap_profile.RECRUITER_PATTERNS_PATH = os.path.join(self.tmp_dir, "recruiter_memory_patterns.json")

    def tearDown(self):
        shutil.rmtree(self.tmp_dir, ignore_errors=True)

    def _write_checkpoint(self, data: dict) -> None:
        with open(bootstrap_bullet_bank.CHECKPOINT_PATH, "w", encoding="utf-8") as f:
            json.dump(data, f)

    def _write_timeline(self, entries: list) -> None:
        with open(bootstrap_bullet_bank.TIMELINE_PATH, "w", encoding="utf-8") as f:
            json.dump(entries, f)

    def _touch_source(self, filename: str) -> None:
        with open(os.path.join(bootstrap_bullet_bank.SOURCE_DOCS_DIR, filename), "w", encoding="utf-8") as f:
            f.write("placeholder")


class TestGuessContactInfo(BootstrapProfileTestCase):

    @patch("bootstrap_profile.bootstrap_extractors.extract_contact_info")
    def test_finds_info_from_resume_file(self, mock_extract):
        self._touch_source("resume.txt")
        self._write_checkpoint({"resume.txt": {"status": "done", "doc_type": "resume"}})
        mock_extract.return_value = bootstrap_extractors.ContactInfo(full_name="Jamie Rivera", email="jamie@example.com")

        info = bootstrap_profile._guess_contact_info(bootstrap_profile._load_checkpoint())

        self.assertEqual(info.full_name, "Jamie Rivera")

    def test_returns_blank_when_no_resume_file(self):
        self._write_checkpoint({"notes.txt": {"status": "done", "doc_type": "achievement_notes"}})
        info = bootstrap_profile._guess_contact_info(bootstrap_profile._load_checkpoint())
        self.assertIsNone(info.full_name)


class TestGuessPrimaryRoles(unittest.TestCase):

    def test_returns_recent_titles_most_recent_first(self):
        timeline = [
            {"company": "Old Co", "title": "Coordinator", "start_date": "2015", "end_date": "2018"},
            {"company": "Acme Corp", "title": "Marketing Manager", "start_date": "2019", "end_date": "2022"},
        ]
        roles = bootstrap_profile._guess_primary_roles(timeline)
        self.assertEqual(roles[0], "Marketing Manager")


class TestGuessRecommendations(BootstrapProfileTestCase):

    @patch("bootstrap_profile.bootstrap_extractors.extract_recommendation_quote")
    def test_collects_quotes_from_recommendation_letters(self, mock_extract):
        self._touch_source("letter.txt")
        self._write_checkpoint({"letter.txt": {"status": "done", "doc_type": "recommendation_letter"}})
        mock_extract.return_value = bootstrap_extractors.RecommendationQuote(
            name="Alex Chen", title="VP Marketing", quote="Excellent writer."
        )

        quotes = bootstrap_profile._guess_recommendations(bootstrap_profile._load_checkpoint())

        self.assertEqual(len(quotes), 1)
        self.assertEqual(quotes[0].name, "Alex Chen")

    def test_returns_empty_list_when_no_recommendation_letters(self):
        self._write_checkpoint({"resume.txt": {"status": "done", "doc_type": "resume"}})
        quotes = bootstrap_profile._guess_recommendations(bootstrap_profile._load_checkpoint())
        self.assertEqual(quotes, [])


class TestCollectIdentityDryRun(BootstrapProfileTestCase):

    def test_dry_run_returns_guesses_without_prompting(self):
        self._write_timeline([{"company": "Acme Corp", "title": "Marketing Manager", "start_date": "2019", "end_date": "2022"}])
        self._write_checkpoint({})

        with patch("bootstrap_profile.questionary.text") as mock_text, \
             patch("bootstrap_profile.questionary.checkbox") as mock_checkbox, \
             patch("bootstrap_profile.questionary.confirm") as mock_confirm:
            identity = bootstrap_profile.collect_identity(dry_run=True)
            mock_text.assert_not_called()
            mock_checkbox.assert_not_called()
            mock_confirm.assert_not_called()

        self.assertEqual(identity["primary_roles"], ["Marketing Manager"])
        self.assertEqual(identity["secondary_roles"], [])


class TestWriteProfileYml(BootstrapProfileTestCase):

    def test_writes_candidate_and_target_roles(self):
        import yaml
        identity = {
            "full_name": "Jamie Rivera", "email": "jamie@example.com", "phone": "555-0100",
            "location": "Austin, TX", "linkedin_url": "linkedin.com/in/jamierivera",
            "portfolio_url": "", "extra_link": "", "primary_roles": ["Marketing Manager"],
            "secondary_roles": ["Customer Education Specialist"], "remote_preference": True,
        }

        bootstrap_profile.write_profile_yml(identity, recommendations=[])

        with open(bootstrap_profile.PROFILE_YML_PATH, encoding="utf-8") as f:
            data = yaml.safe_load(f)
        self.assertEqual(data["candidate"]["full_name"], "Jamie Rivera")
        self.assertEqual(data["target_roles"]["primary"], ["Marketing Manager"])
        self.assertEqual(data["target_roles"]["secondary"], ["Customer Education Specialist"])
        self.assertEqual(data["location"]["remote_required"], True)

    def test_auto_fills_key_recommendations_when_present(self):
        import yaml
        identity = {
            "full_name": "Jamie Rivera", "email": "", "phone": "", "location": "", "linkedin_url": "",
            "portfolio_url": "", "extra_link": "", "primary_roles": [], "secondary_roles": [],
            "remote_preference": False,
        }
        recs = [bootstrap_extractors.RecommendationQuote(name="Alex Chen", title="VP Marketing", quote="Excellent writer.")]

        bootstrap_profile.write_profile_yml(identity, recommendations=recs)

        with open(bootstrap_profile.PROFILE_YML_PATH, encoding="utf-8") as f:
            data = yaml.safe_load(f)
        self.assertEqual(data["key_recommendations"][0]["name"], "Alex Chen")
        self.assertEqual(data["key_recommendations"][0]["quote"], "Excellent writer.")

    def test_scaffolds_deep_sections_empty(self):
        import yaml
        identity = {
            "full_name": "", "email": "", "phone": "", "location": "", "linkedin_url": "",
            "portfolio_url": "", "extra_link": "", "primary_roles": [], "secondary_roles": [],
            "remote_preference": False,
        }
        bootstrap_profile.write_profile_yml(identity, recommendations=[])
        with open(bootstrap_profile.PROFILE_YML_PATH, encoding="utf-8") as f:
            data = yaml.safe_load(f)
        self.assertEqual(data["narrative"]["headline"], "")
        self.assertEqual(data["deal_breakers"], [""])
        self.assertEqual(data["management_evidence"], [])


if __name__ == "__main__":
    unittest.main()
```

Save as `tests/test_bootstrap_profile.py`.

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m unittest tests.test_bootstrap_profile -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'bootstrap_profile'`.

- [ ] **Step 3: Write the implementation**

```python
#!/usr/bin/env python3
"""
bootstrap_profile.py

Phase 0.5 of the bootstrap flow: guesses and confirms profile.yml,
portals.yml, drafts cv.md and user-background-guide.md, and derives the
verified_* ledger -- all from documents Phase 0 (bootstrap_bullet_bank.py)
already ingested. See run_profile_setup() for the single entry point.
"""

import csv
import json
import os
import sys

import questionary

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(SCRIPT_DIR)
KB_DIR = os.path.join(PROJECT_ROOT, "resume-engine", "knowledge_base")

PROFILE_YML_PATH = os.path.join(KB_DIR, "profile.yml")
PORTALS_YML_PATH = os.path.join(KB_DIR, "portals.yml")
CV_MD_PATH = os.path.join(KB_DIR, "cv.md")
BACKGROUND_GUIDE_PATH = os.path.join(KB_DIR, "user-background-guide.md")
VERIFIED_METRICS_PATH = os.path.join(KB_DIR, "verified_metrics.json")
VERIFIED_TOOLS_PATH = os.path.join(KB_DIR, "verified_tools.json")
VERIFIED_PROJECTS_PATH = os.path.join(KB_DIR, "verified_projects.json")
VERIFIED_FACTS_PATH = os.path.join(KB_DIR, "verified_facts.json")
VERIFIED_CLAIMS_PATH = os.path.join(KB_DIR, "verified-claims.csv")
EVIDENCE_GRAPH_PATH = os.path.join(KB_DIR, "evidence_graph.json")
EVIDENCE_GUIDE_PATH = os.path.join(KB_DIR, "evidence-guide.csv")
SCREENSHOT_METRICS_PATH = os.path.join(KB_DIR, "extracted-screenshot-metrics.csv")
RECRUITER_PATTERNS_PATH = os.path.join(KB_DIR, "recruiter_memory_patterns.json")

if SCRIPT_DIR not in sys.path:
    sys.path.insert(0, SCRIPT_DIR)

import bootstrap_bullet_bank  # noqa: E402
import bootstrap_extractors  # noqa: E402
import cli_art  # noqa: E402


def _load_checkpoint() -> dict:
    if not os.path.exists(bootstrap_bullet_bank.CHECKPOINT_PATH):
        return {}
    with open(bootstrap_bullet_bank.CHECKPOINT_PATH, encoding="utf-8") as f:
        return json.load(f)


def _load_timeline() -> list:
    if not os.path.exists(bootstrap_bullet_bank.TIMELINE_PATH):
        return []
    with open(bootstrap_bullet_bank.TIMELINE_PATH, encoding="utf-8") as f:
        return json.load(f)


def _achievements_summary_text() -> str:
    if not os.path.exists(bootstrap_bullet_bank.DRAFT_CSV_PATH):
        return ""
    with open(bootstrap_bullet_bank.DRAFT_CSV_PATH, encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    return "\n".join(row.get("Bullet Point", "") for row in rows)


def _resolve_text_or_upload(path: str) -> tuple:
    """Re-derives a document's text-or-upload_path split for a second
    extraction pass over it (contact info / recommendation quotes) without
    modifying Phase 0's _process_one_file."""
    kind = bootstrap_extractors.detect_file_kind(path)
    if kind == "doc":
        converted = bootstrap_extractors.convert_legacy_doc_to_pdf(path)
        if converted is None:
            return None, None
        path, kind = converted, "pdf"
    if kind in ("pdf", "image"):
        return None, path
    if kind == "unsupported":
        return None, None
    return bootstrap_extractors.extract_local_text(path, kind), None


def _guess_contact_info(checkpoint: dict, dry_run: bool = False) -> bootstrap_extractors.ContactInfo:
    for filename, result in sorted(checkpoint.items()):
        if result.get("status") != "done" or result.get("doc_type") not in ("resume", "linkedin_export"):
            continue
        path = os.path.join(bootstrap_bullet_bank.SOURCE_DOCS_DIR, filename)
        text, upload_path = _resolve_text_or_upload(path)
        if text is None and upload_path is None:
            continue
        info = bootstrap_extractors.extract_contact_info(text=text, upload_path=upload_path, dry_run=dry_run)
        if any(v for v in info.model_dump().values()):
            return info
    return bootstrap_extractors.ContactInfo()


def _guess_primary_roles(timeline: list) -> list:
    seen = []
    for entry in sorted(timeline, key=lambda e: e.get("end_date") or "", reverse=True):
        title = entry.get("title")
        if title and title not in seen:
            seen.append(title)
    return seen[:3]


def _guess_recommendations(checkpoint: dict, dry_run: bool = False) -> list:
    quotes = []
    for filename, result in sorted(checkpoint.items()):
        if result.get("status") != "done" or result.get("doc_type") != "recommendation_letter":
            continue
        path = os.path.join(bootstrap_bullet_bank.SOURCE_DOCS_DIR, filename)
        text, upload_path = _resolve_text_or_upload(path)
        if text is None and upload_path is None:
            continue
        quote = bootstrap_extractors.extract_recommendation_quote(text=text, upload_path=upload_path, dry_run=dry_run)
        if quote is not None:
            quotes.append(quote)
    return quotes


def _confirm_text(label: str, guessed) -> str:
    return questionary.text(label, default=guessed or "", style=cli_art.QUESTIONARY_STYLE).ask() or ""


def _confirm_roles(label: str, guessed: list) -> list:
    if not guessed:
        extra = questionary.text(f"{label} (comma-separated, optional)", default="", style=cli_art.QUESTIONARY_STYLE).ask() or ""
        return [r.strip() for r in extra.split(",") if r.strip()]
    choices = [questionary.Choice(title=r, value=r, checked=True) for r in guessed]
    kept = questionary.checkbox(label, choices=choices, style=cli_art.QUESTIONARY_STYLE).ask() or []
    extra = questionary.text(f"Add any more {label.lower()} (comma-separated, optional)", default="", style=cli_art.QUESTIONARY_STYLE).ask() or ""
    kept.extend(r.strip() for r in extra.split(",") if r.strip())
    return kept


def collect_identity(dry_run: bool = False) -> dict:
    checkpoint = _load_checkpoint()
    timeline = _load_timeline()
    guessed = _guess_contact_info(checkpoint, dry_run=dry_run)
    primary_guess = _guess_primary_roles(timeline)

    if dry_run:
        print("[DRY RUN] would confirm identity fields:")
        print(f"  Full name: {guessed.full_name or ''}")
        print(f"  Email: {guessed.email or ''}")
        print(f"  Phone: {guessed.phone or ''}")
        print(f"  Location: {guessed.location or ''}")
        print(f"  LinkedIn URL: {guessed.linkedin_url or ''}")
        print(f"  Primary target roles: {', '.join(primary_guess)}")
        return {
            "full_name": guessed.full_name or "", "email": guessed.email or "",
            "phone": guessed.phone or "", "location": guessed.location or "",
            "linkedin_url": guessed.linkedin_url or "", "portfolio_url": guessed.portfolio_url or "",
            "extra_link": "", "primary_roles": primary_guess, "secondary_roles": [],
            "remote_preference": False,
        }

    full_name = _confirm_text("Full name:", guessed.full_name)
    email = _confirm_text("Email:", guessed.email)
    phone = _confirm_text("Phone:", guessed.phone)
    location = _confirm_text("Location (city, state):", guessed.location)
    linkedin_url = _confirm_text("LinkedIn URL:", guessed.linkedin_url)
    portfolio_url = _confirm_text("Portfolio URL (optional, press Enter to skip):", guessed.portfolio_url)
    extra_link = _confirm_text("Any other portfolio/work-sample link? (optional, press Enter to skip):", None)

    primary_roles = _confirm_roles("Primary target roles:", primary_guess)

    achievements_text = _achievements_summary_text()
    secondary_guess = (
        bootstrap_extractors.suggest_secondary_roles(primary_roles, achievements_text, dry_run=dry_run)
        if primary_roles else []
    )
    secondary_roles = _confirm_roles("Secondary target roles:", secondary_guess)

    remote_preference = questionary.confirm(
        "Are you remote-only?", default=True, style=cli_art.QUESTIONARY_STYLE,
    ).ask()

    return {
        "full_name": full_name, "email": email, "phone": phone, "location": location,
        "linkedin_url": linkedin_url, "portfolio_url": portfolio_url, "extra_link": extra_link,
        "primary_roles": primary_roles, "secondary_roles": secondary_roles,
        "remote_preference": bool(remote_preference),
    }


def _yaml_string_list(items: list, indent: str = "    ") -> str:
    if not items:
        return f"{indent}[]"
    return "\n".join(f'{indent}- "{item}"' for item in items)


def _yaml_key_recommendations(quotes: list) -> str:
    if not quotes:
        return (
            "  # If you upload recommendation letters and re-run bootstrap, we'll\n"
            "  # pull real quotes + attribution from them here automatically.\n"
            "  []"
        )
    lines = []
    for q in quotes:
        lines.append(f'  - name: "{q.name or ""}"')
        lines.append(f'    title: "{q.title or ""}"')
        lines.append(f'    quote: "{q.quote or ""}"')
    return "\n".join(lines)


_PROFILE_YML_TEMPLATE = """# Career-Ops Profile Configuration
# Generated by bootstrap -- review and expand the sections below any time.

candidate:
  full_name: "{full_name}"
  email: "{email}"
  phone: "{phone}"
  location: "{location}"
  linkedin: "{linkedin_url}"
  portfolio_url: "{portfolio_url}"
  extra_link: "{extra_link}"

target_roles:
  primary:
{primary_roles_yaml}
  secondary:
{secondary_roles_yaml}

archetypes:
  # For each role you're targeting, a short note on what specifically
  # you'd bring to it. Example:
  #   - name: "Customer Marketing Manager"
  #     level: "Mid-Senior"
  #     fit: "primary"
  #     notes: "Customer engagement, onboarding, retention campaigns..."
  archetypes: []

narrative:
  # A 1-2 sentence headline summarizing your professional identity.
  # Example: "Marketing leader who writes campaigns that perform..."
  headline: ""

  # Optional: why you're job-searching now / your story if there's a
  # gap or transition. Leave blank if not applicable.
  exit_story: ""

superpowers:
  # 3-5 things you're uniquely good at, each with a real example. These
  # often come from your own self-reflection or feedback you've received.
  - ""

background_context: >
  A paragraph on how your background came together -- the different
  tracks/experiences that combine into what you do now.

industries_of_genuine_fit:
  # Industries or company types where you'd genuinely want to work.
  - ""

companies_previously_applied: []
  # Track applications here as you go, to avoid duplicate applying.

deal_breakers:
  # Things that would make a role a bad fit, with the specific reason.
  # Example: "On-site or hybrid required -- remote-only availability"
  - ""

proof_points: []
  # Your single best, most specific hero metric per major achievement.
  # Example:
  #   - name: "PTA Council Campaign"
  #     context: "Hardest-to-reach audience in the portfolio"
  #     hero_metric: "74% open rate / 22% reply rate / 0 opt-outs"

key_recommendations:
{key_recommendations_yaml}

management_evidence: []
  # Direct quotes from real coworkers/managers confirming leadership or
  # de facto management responsibility, if you have any on record.

compensation:
  target_range: ""
  currency: "USD"
  minimum: ""
  location_flexibility: "{location_flexibility}"
  notes: ""

location:
  country: "United States"
  city: "{location}"
  timezone: ""
  visa_status: ""
  remote_required: {remote_required}
  notes: ""

cv:
  output_format: "html"
"""


def write_profile_yml(identity: dict, recommendations: list) -> None:
    content = _PROFILE_YML_TEMPLATE.format(
        full_name=identity["full_name"], email=identity["email"], phone=identity["phone"],
        location=identity["location"], linkedin_url=identity["linkedin_url"],
        portfolio_url=identity["portfolio_url"], extra_link=identity["extra_link"],
        primary_roles_yaml=_yaml_string_list(identity["primary_roles"]),
        secondary_roles_yaml=_yaml_string_list(identity["secondary_roles"]),
        key_recommendations_yaml=_yaml_key_recommendations(recommendations),
        location_flexibility="Remote only" if identity.get("remote_preference") else "",
        remote_required=str(bool(identity.get("remote_preference"))).lower(),
    )
    os.makedirs(os.path.dirname(PROFILE_YML_PATH), exist_ok=True)
    with open(PROFILE_YML_PATH, "w", encoding="utf-8") as f:
        f.write(content)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m unittest tests.test_bootstrap_profile -v`
Expected: all tests PASS.

- [ ] **Step 5: Commit**

```bash
git add scripts/bootstrap_profile.py tests/test_bootstrap_profile.py
git commit -m "Add identity/role guessing, interactive confirm prompts, and profile.yml writer"
```

---

### Task 4: `bootstrap_profile.py` — `portals.yml`

**Files:**
- Modify: `scripts/bootstrap_profile.py` (append)
- Test: `tests/test_bootstrap_profile.py` (append)

**Interfaces:**
- Consumes: `_yaml_string_list` (Task 3), `PORTALS_YML_PATH` (Task 3).
- Produces (used by Task 7): `write_portals_yml(identity: dict) -> None`

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_bootstrap_profile.py`:

```python
class TestWritePortalsYml(BootstrapProfileTestCase):

    def test_seeds_title_filter_from_target_roles(self):
        import yaml
        identity = {
            "full_name": "", "email": "", "phone": "", "location": "", "linkedin_url": "",
            "portfolio_url": "", "extra_link": "",
            "primary_roles": ["Marketing Manager"], "secondary_roles": ["Customer Education Specialist"],
            "remote_preference": True,
        }

        bootstrap_profile.write_portals_yml(identity)

        with open(bootstrap_profile.PORTALS_YML_PATH, encoding="utf-8") as f:
            data = yaml.safe_load(f)
        self.assertIn("Marketing Manager", data["title_filter"]["positive"])
        self.assertIn("Customer Education Specialist", data["title_filter"]["positive"])
        self.assertIn("Remote", data["location_filter"]["always_allow"])

    def test_scaffolds_block_and_seniority_boost_empty(self):
        import yaml
        identity = {
            "full_name": "", "email": "", "phone": "", "location": "", "linkedin_url": "",
            "portfolio_url": "", "extra_link": "", "primary_roles": [], "secondary_roles": [],
            "remote_preference": False,
        }
        bootstrap_profile.write_portals_yml(identity)
        with open(bootstrap_profile.PORTALS_YML_PATH, encoding="utf-8") as f:
            data = yaml.safe_load(f)
        self.assertEqual(data["seniority_boost"], [])
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m unittest tests.test_bootstrap_profile.TestWritePortalsYml -v`
Expected: FAIL with `AttributeError: module 'bootstrap_profile' has no attribute 'write_portals_yml'`.

- [ ] **Step 3: Write the implementation**

Append to `scripts/bootstrap_profile.py`:

```python
_PORTALS_YML_TEMPLATE = """# Portal Scanner Configuration
# Generated by bootstrap -- refine title_filter/block/seniority_boost over
# time as you see real postings come through.

location_filter:
  # Words in a job posting's location field that mean "yes, apply."
  always_allow:
{always_allow_yaml}

block:
  # Words that mean "no, this isn't remote" -- e.g. on-site/hybrid signals.
  # Starts with common defaults; add more as you see them in real postings.
  - "Onsite"
  - "On-Site"
  - "Hybrid"
  - "In-office"

title_filter:
  positive:
    # Job titles worth evaluating. Seeded from your target roles --
    # add near-miss titles you keep seeing as you scan real postings.
{title_filter_yaml}
  negative: []
    # Titles that mean "skip this one," even if it matched something above.

seniority_boost: []
  # Keywords that bump a posting's priority (e.g. "Senior", "Lead").
  # Leave as-is until you have a preference.
"""


def write_portals_yml(identity: dict) -> None:
    always_allow = ["Remote", "Work from home", "Fully Remote"] if identity.get("remote_preference") else ["Remote", "Hybrid"]
    title_seed = identity["primary_roles"] + identity["secondary_roles"]
    content = _PORTALS_YML_TEMPLATE.format(
        always_allow_yaml=_yaml_string_list(always_allow),
        title_filter_yaml=_yaml_string_list(title_seed),
    )
    os.makedirs(os.path.dirname(PORTALS_YML_PATH), exist_ok=True)
    with open(PORTALS_YML_PATH, "w", encoding="utf-8") as f:
        f.write(content)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m unittest tests.test_bootstrap_profile -v`
Expected: all tests PASS.

- [ ] **Step 5: Commit**

```bash
git add scripts/bootstrap_profile.py tests/test_bootstrap_profile.py
git commit -m "Add portals.yml writer seeded from confirmed target roles"
```

---

### Task 5: `bootstrap_profile.py` — verified-facts ledger derivation and scaffolds

**Files:**
- Modify: `scripts/bootstrap_profile.py` (append)
- Test: `tests/test_bootstrap_profile.py` (append)

**Interfaces:**
- Consumes: `bootstrap_extractors.extract_ledger_entries` (Task 1), `_achievements_summary_text` (Task 3).
- Produces (used by Task 7): `write_verified_ledger(dry_run: bool = False) -> None`

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_bootstrap_profile.py`:

```python
class TestWriteVerifiedLedger(BootstrapProfileTestCase):

    @patch("bootstrap_profile.bootstrap_extractors.extract_ledger_entries")
    def test_derives_metrics_tools_projects_from_achievements(self, mock_extract):
        with open(bootstrap_bullet_bank.DRAFT_CSV_PATH, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=["Role / Company", "Tags", "Bullet Point", "source_file", "source_type"])
            writer.writeheader()
            writer.writerow({"Role / Company": "Acme Corp", "Tags": "", "Bullet Point": "- Grew reply rate to 22% using Outreach.io", "source_file": "resume.txt", "source_type": "resume"})

        mock_extract.return_value = bootstrap_extractors.LedgerExtraction(
            metrics=[bootstrap_extractors.LedgerEntry(label="Reply rate", value="22%")],
            tools=["Outreach.io"], projects=[],
        )

        bootstrap_profile.write_verified_ledger()

        with open(bootstrap_profile.VERIFIED_METRICS_PATH, encoding="utf-8") as f:
            metrics = json.load(f)
        self.assertEqual(metrics["metrics"][0]["value"], "22%")
        with open(bootstrap_profile.VERIFIED_TOOLS_PATH, encoding="utf-8") as f:
            tools = json.load(f)
        self.assertEqual(tools["tools"][0]["name"], "Outreach.io")

    def test_scaffolds_cross_source_files_empty(self):
        bootstrap_profile.write_verified_ledger(dry_run=True)

        with open(bootstrap_profile.VERIFIED_FACTS_PATH, encoding="utf-8") as f:
            facts = json.load(f)
        self.assertEqual(facts["facts"], [])

        with open(bootstrap_profile.EVIDENCE_GRAPH_PATH, encoding="utf-8") as f:
            graph = json.load(f)
        self.assertEqual(graph["nodes"], [])

        with open(bootstrap_profile.VERIFIED_CLAIMS_PATH, encoding="utf-8") as f:
            header = f.readline().strip()
        self.assertEqual(header, "Claim / Finding,Verification Status,Source File,Evidence / Detail,Metric(s),Confidence,Use in Resume?,Use in Portfolio?,Next Follow-Up")

        with open(bootstrap_profile.RECRUITER_PATTERNS_PATH, encoding="utf-8") as f:
            patterns = json.load(f)
        self.assertEqual(patterns["patterns"], [])
```

Add `import csv` to the test file's imports if not already present (it is, via the module-level `import csv` already used elsewhere in this file's helper methods -- if not, add `import csv` alongside the existing `import json` line at the top of `tests/test_bootstrap_profile.py`).

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m unittest tests.test_bootstrap_profile.TestWriteVerifiedLedger -v`
Expected: FAIL with `AttributeError: module 'bootstrap_profile' has no attribute 'write_verified_ledger'`.

- [ ] **Step 3: Write the implementation**

Append to `scripts/bootstrap_profile.py`:

```python
def write_verified_ledger(dry_run: bool = False) -> None:
    achievements_text = _achievements_summary_text()
    extraction = (
        bootstrap_extractors.extract_ledger_entries(achievements_text, dry_run=dry_run)
        if achievements_text else bootstrap_extractors.LedgerExtraction()
    )

    os.makedirs(os.path.dirname(VERIFIED_METRICS_PATH), exist_ok=True)

    metrics_json = {
        "_meta": {"source": "bootstrap ingestion", "total_entries": len(extraction.metrics)},
        "metrics": [
            {"id": f"metric_{i + 1:03d}", "label": m.label, "value": m.value}
            for i, m in enumerate(extraction.metrics)
        ],
    }
    with open(VERIFIED_METRICS_PATH, "w", encoding="utf-8") as f:
        json.dump(metrics_json, f, indent=2)

    tools_json = {
        "_meta": {"source": "bootstrap ingestion", "total_entries": len(extraction.tools)},
        "tools": [{"id": f"tool_{i + 1:03d}", "name": t} for i, t in enumerate(extraction.tools)],
    }
    with open(VERIFIED_TOOLS_PATH, "w", encoding="utf-8") as f:
        json.dump(tools_json, f, indent=2)

    projects_json = {
        "_meta": {"source": "bootstrap ingestion", "total_entries": len(extraction.projects)},
        "projects": [{"id": f"proj_{i + 1:03d}", "name": p} for i, p in enumerate(extraction.projects)],
    }
    with open(VERIFIED_PROJECTS_PATH, "w", encoding="utf-8") as f:
        json.dump(projects_json, f, indent=2)

    empty_facts = {
        "_meta": {"source": "", "total_entries": 0,
                  "note": "Add facts here as you cross-reference multiple sources over time."},
        "facts": [],
    }
    with open(VERIFIED_FACTS_PATH, "w", encoding="utf-8") as f:
        json.dump(empty_facts, f, indent=2)

    empty_graph = {
        "_meta": {
            "source": "",
            "description": "Relationship graph connecting metrics, facts, projects, tools. Build this up as your evidence grows.",
            "node_types": ["metric", "fact", "project", "tool"],
        },
        "nodes": [], "edges": [],
    }
    with open(EVIDENCE_GRAPH_PATH, "w", encoding="utf-8") as f:
        json.dump(empty_graph, f, indent=2)

    with open(VERIFIED_CLAIMS_PATH, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow([
            "Claim / Finding", "Verification Status", "Source File", "Evidence / Detail",
            "Metric(s)", "Confidence", "Use in Resume?", "Use in Portfolio?", "Next Follow-Up",
        ])

    with open(EVIDENCE_GUIDE_PATH, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow([
            "Evidence Cluster", "Finding", "Source File(s)", "Best Detail / Quote", "Best Metric",
            "What This Proves About You", "Where to Use It", "Confidence", "Source URL / Notes",
        ])

    with open(SCREENSHOT_METRICS_PATH, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow([
            "Source Batch", "Campaign / Screenshot Title", "Screenshot File(s)", "Contacted",
            "Reached", "Reached %", "Opened", "Open %", "Replied", "Reply %", "Clicked %",
            "Bounced", "Bounce %", "Opted Out", "Opt-Out %", "Best Detail / Notes", "Confidence", "Reviewed",
        ])

    empty_recruiter_patterns = {
        "_meta": {"note": "Builds up over real recruiter feedback and application outcomes."},
        "patterns": [],
    }
    with open(RECRUITER_PATTERNS_PATH, "w", encoding="utf-8") as f:
        json.dump(empty_recruiter_patterns, f, indent=2)
```

Add `import csv` to the top of `scripts/bootstrap_profile.py`'s existing import block (alongside `import json`) if not already present -- it is not yet present from Task 3, so add it now.

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m unittest tests.test_bootstrap_profile -v`
Expected: all tests PASS.

- [ ] **Step 5: Commit**

```bash
git add scripts/bootstrap_profile.py tests/test_bootstrap_profile.py
git commit -m "Derive verified_metrics/tools/projects.json from achievements; scaffold the rest of the ledger"
```

---

### Task 6: `bootstrap_profile.py` — `cv.md` draft with reused rewrite polish

**Files:**
- Modify: `scripts/bootstrap_profile.py` (append)
- Test: `tests/test_bootstrap_profile.py` (append)

**Interfaces:**
- Consumes: `_load_timeline`, `_achievements_summary_text`'s underlying CSV read pattern (Task 3); `rewrite_bullets.{RulesBundle, KnowledgeBase, build_system_prompts, process_bullet, RULES_DIR, SCORING_DIR}` (existing, reused as-is).
- Produces (used by Task 7): `write_cv_md(identity: dict, dry_run: bool = False) -> None`

**Important testing note:** `RulesBundle`/`KnowledgeBase` are imported by name into `bootstrap_profile`'s namespace (`from rewrite_bullets import RulesBundle, KnowledgeBase, ...`), so unit tests must patch them as `bootstrap_profile.RulesBundle` / `bootstrap_profile.KnowledgeBase` / `bootstrap_profile.process_bullet` (not `rewrite_bullets.RulesBundle`) -- otherwise the real classes would read the *actual* repo's `resume-engine/knowledge_base/` files instead of the test's temp-dir fixtures, since `rewrite_bullets.py`'s own path constants are independent of `bootstrap_profile.py`'s redirected ones.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_bootstrap_profile.py`:

```python
class TestWriteCvMd(BootstrapProfileTestCase):

    @patch("bootstrap_profile.questionary.select")
    @patch("bootstrap_profile.process_bullet")
    @patch("bootstrap_profile.build_system_prompts", return_value=("rewrite sys", "score sys"))
    @patch("bootstrap_profile.KnowledgeBase")
    @patch("bootstrap_profile.RulesBundle")
    def test_accept_writes_header_and_per_role_sections(
        self, mock_rules_cls, mock_kb_cls, mock_build_prompts, mock_process_bullet, mock_select,
    ):
        self._write_timeline([
            {"company": "Acme Corp", "title": "Marketing Manager", "start_date": "2019", "end_date": "2022", "needs_review": False, "conflict_note": None},
        ])
        with open(bootstrap_bullet_bank.DRAFT_CSV_PATH, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=["Role / Company", "Tags", "Bullet Point", "source_file", "source_type"])
            writer.writeheader()
            writer.writerow({"Role / Company": "Acme Corp", "Tags": "", "Bullet Point": "- Grew email list by 40%", "source_file": "resume.txt", "source_type": "resume"})

        mock_process_bullet.return_value = {"final_bullet": "Grew the email list by 40% through segmentation."}
        mock_select.return_value.ask.return_value = "accept"

        identity = {
            "full_name": "Jamie Rivera", "email": "jamie@example.com", "phone": "",
            "location": "Austin, TX", "linkedin_url": "", "portfolio_url": "", "extra_link": "",
            "primary_roles": [], "secondary_roles": [], "remote_preference": False,
        }

        bootstrap_profile.write_cv_md(identity)

        with open(bootstrap_profile.CV_MD_PATH, encoding="utf-8") as f:
            content = f.read()
        self.assertIn("Jamie Rivera", content)
        self.assertIn("Marketing Manager", content)
        self.assertIn("Acme Corp", content)
        self.assertIn("Grew the email list by 40% through segmentation.", content)
        mock_process_bullet.assert_called_once()

    @patch("bootstrap_profile.questionary.select")
    @patch("bootstrap_profile.process_bullet")
    @patch("bootstrap_profile.build_system_prompts", return_value=("rewrite sys", "score sys"))
    @patch("bootstrap_profile.KnowledgeBase")
    @patch("bootstrap_profile.RulesBundle")
    def test_builds_rules_and_kb_once_not_per_bullet(
        self, mock_rules_cls, mock_kb_cls, mock_build_prompts, mock_process_bullet, mock_select,
    ):
        self._write_timeline([{"company": "Acme Corp", "title": "Manager", "start_date": "2019", "end_date": "2022", "needs_review": False, "conflict_note": None}])
        with open(bootstrap_bullet_bank.DRAFT_CSV_PATH, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=["Role / Company", "Tags", "Bullet Point", "source_file", "source_type"])
            writer.writeheader()
            writer.writerow({"Role / Company": "Acme Corp", "Tags": "", "Bullet Point": "- First bullet", "source_file": "resume.txt", "source_type": "resume"})
            writer.writerow({"Role / Company": "Acme Corp", "Tags": "", "Bullet Point": "- Second bullet", "source_file": "resume.txt", "source_type": "resume"})

        mock_process_bullet.return_value = {"final_bullet": "polished"}
        mock_select.return_value.ask.return_value = "accept"
        identity = {"full_name": "Jamie", "email": "", "phone": "", "location": "", "linkedin_url": "", "portfolio_url": "", "extra_link": "", "primary_roles": [], "secondary_roles": [], "remote_preference": False}

        bootstrap_profile.write_cv_md(identity)

        self.assertEqual(mock_rules_cls.call_count, 1)
        self.assertEqual(mock_kb_cls.call_count, 1)
        self.assertEqual(mock_process_bullet.call_count, 2)

    @patch("bootstrap_profile.questionary.select")
    @patch("bootstrap_profile.process_bullet")
    @patch("bootstrap_profile.build_system_prompts", return_value=("rewrite sys", "score sys"))
    @patch("bootstrap_profile.KnowledgeBase")
    @patch("bootstrap_profile.RulesBundle")
    def test_skip_writes_empty_file(
        self, mock_rules_cls, mock_kb_cls, mock_build_prompts, mock_process_bullet, mock_select,
    ):
        self._write_timeline([{"company": "Acme Corp", "title": "Manager", "start_date": "2019", "end_date": "2022", "needs_review": False, "conflict_note": None}])
        with open(bootstrap_bullet_bank.DRAFT_CSV_PATH, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=["Role / Company", "Tags", "Bullet Point", "source_file", "source_type"])
            writer.writeheader()
            writer.writerow({"Role / Company": "Acme Corp", "Tags": "", "Bullet Point": "- First bullet", "source_file": "resume.txt", "source_type": "resume"})

        mock_process_bullet.return_value = {"final_bullet": "polished"}
        mock_select.return_value.ask.return_value = "skip"
        identity = {"full_name": "Jamie", "email": "", "phone": "", "location": "", "linkedin_url": "", "portfolio_url": "", "extra_link": "", "primary_roles": [], "secondary_roles": [], "remote_preference": False}

        bootstrap_profile.write_cv_md(identity)

        with open(bootstrap_profile.CV_MD_PATH, encoding="utf-8") as f:
            content = f.read()
        self.assertEqual(content, "")

    def test_dry_run_writes_without_prompting(self):
        with patch("bootstrap_profile.questionary.select") as mock_select, \
             patch("bootstrap_profile.RulesBundle"), patch("bootstrap_profile.KnowledgeBase"), \
             patch("bootstrap_profile.build_system_prompts", return_value=("rewrite sys", "score sys")), \
             patch("bootstrap_profile.process_bullet", return_value={"final_bullet": "polished"}):
            identity = {"full_name": "Jamie", "email": "", "phone": "", "location": "", "linkedin_url": "", "portfolio_url": "", "extra_link": "", "primary_roles": [], "secondary_roles": [], "remote_preference": False}
            bootstrap_profile.write_cv_md(identity, dry_run=True)
            mock_select.assert_not_called()
        self.assertTrue(os.path.exists(bootstrap_profile.CV_MD_PATH))
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m unittest tests.test_bootstrap_profile.TestWriteCvMd -v`
Expected: FAIL with `AttributeError: module 'bootstrap_profile' has no attribute 'write_cv_md'`.

- [ ] **Step 3: Write the implementation**

Add this import near the top of `scripts/bootstrap_profile.py`, alongside the existing `import bootstrap_bullet_bank` block:

```python
import pandas as pd

from rewrite_bullets import RulesBundle, KnowledgeBase, build_system_prompts, process_bullet, RULES_DIR, SCORING_DIR
```

Append to the end of `scripts/bootstrap_profile.py`:

```python
def _build_cv_draft_rows() -> list:
    timeline = _load_timeline()
    if not os.path.exists(bootstrap_bullet_bank.DRAFT_CSV_PATH):
        return []
    with open(bootstrap_bullet_bank.DRAFT_CSV_PATH, encoding="utf-8") as f:
        rows = list(csv.DictReader(f))

    by_company = {}
    for row in rows:
        by_company.setdefault(row["Role / Company"], []).append(row["Bullet Point"])

    ordered = sorted(timeline, key=lambda e: e.get("end_date") or "", reverse=True)
    result = []
    seen_companies = set()
    for entry in ordered:
        company = entry["company"]
        seen_companies.add(company)
        result.append({
            "company": company, "title": entry.get("title") or "",
            "start_date": entry.get("start_date") or "", "end_date": entry.get("end_date") or "",
            "bullets": by_company.get(company, []),
        })
    for company, bullets in by_company.items():
        if company not in seen_companies and company != "Misc. / Unassigned":
            result.append({"company": company, "title": "", "start_date": "", "end_date": "", "bullets": bullets})
    return result


def _polish_bullet(bullet: str, role_company: str, kb, rewrite_system: str, score_system: str, dry_run: bool = False) -> str:
    row = pd.Series({"Bullet Point": bullet, "Tags": "", "Role / Company": role_company, "weaknesses": ""})
    result = process_bullet(row, kb, rewrite_system, score_system, dry_run)
    return result.get("final_bullet", bullet)


def _assemble_cv_draft(identity: dict, rows: list, kb, rewrite_system: str, score_system: str, dry_run: bool) -> str:
    lines = [f"# {identity['full_name']}", ""]
    contact_parts = [p for p in (identity.get("email"), identity.get("phone"), identity.get("location"), identity.get("linkedin_url")) if p]
    if contact_parts:
        lines.append(" | ".join(contact_parts))
        lines.append("")

    for role in rows:
        header = f"## {role['title']} — {role['company']}" if role["title"] else f"## {role['company']}"
        date_range = f" ({role['start_date']} - {role['end_date']})" if role["start_date"] else ""
        lines.append(header + date_range)
        for bullet in role["bullets"]:
            polished = _polish_bullet(bullet, role["company"], kb, rewrite_system, score_system, dry_run)
            lines.append(f"- {polished}")
        lines.append("")

    return "\n".join(lines)


def write_cv_md(identity: dict, dry_run: bool = False) -> None:
    rows = _build_cv_draft_rows()
    rules = RulesBundle(RULES_DIR, SCORING_DIR)
    kb = KnowledgeBase()
    rewrite_system, score_system = build_system_prompts(rules, kb)

    if dry_run:
        print("[DRY RUN] would draft cv.md and preview it for accept/regenerate/skip.")
        content = _assemble_cv_draft(identity, rows, kb, rewrite_system, score_system, dry_run)
        os.makedirs(os.path.dirname(CV_MD_PATH), exist_ok=True)
        with open(CV_MD_PATH, "w", encoding="utf-8") as f:
            f.write(content)
        return

    content = _assemble_cv_draft(identity, rows, kb, rewrite_system, score_system, dry_run)
    choice = "skip"
    while True:
        print("\n--- Draft cv.md ---\n")
        print(content)
        print("\n--- End draft ---\n")
        choice = questionary.select(
            "What would you like to do with this draft?",
            choices=[
                questionary.Choice(title="Accept it as-is", value="accept"),
                questionary.Choice(title="Regenerate", value="regenerate"),
                questionary.Choice(title="Skip -- I'll write my own later", value="skip"),
            ],
            style=cli_art.QUESTIONARY_STYLE,
        ).ask()
        if choice == "regenerate":
            content = _assemble_cv_draft(identity, rows, kb, rewrite_system, score_system, dry_run)
            continue
        break

    os.makedirs(os.path.dirname(CV_MD_PATH), exist_ok=True)
    with open(CV_MD_PATH, "w", encoding="utf-8") as f:
        f.write(content if choice == "accept" else "")
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m unittest tests.test_bootstrap_profile -v`
Expected: all tests PASS.

- [ ] **Step 5: Commit**

```bash
git add scripts/bootstrap_profile.py tests/test_bootstrap_profile.py
git commit -m "Add cv.md draft assembly reusing rewrite_bullets.py's rewrite/score loop"
```

---

### Task 7: `bootstrap_profile.py` — `user-background-guide.md` draft/preview and `run_profile_setup()`

**Files:**
- Modify: `scripts/bootstrap_profile.py` (append)
- Test: `tests/test_bootstrap_profile.py` (append)

**Interfaces:**
- Consumes: `bootstrap_extractors.draft_background_guide` (Task 1), `_resolve_text_or_upload` (Task 3), all `write_*` functions (Tasks 3-6).
- Produces (used by Task 8): `run_profile_setup(dry_run: bool = False) -> dict` -- returns `{"full_name": str, "primary_roles": int, "secondary_roles": int, "recommendations_found": int}`.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_bootstrap_profile.py`:

```python
class TestWriteBackgroundGuide(BootstrapProfileTestCase):

    @patch("bootstrap_profile.questionary.select")
    @patch("bootstrap_profile.bootstrap_extractors.draft_background_guide")
    def test_accepts_draft_and_writes_file(self, mock_draft, mock_select):
        self._touch_source("resume.txt")
        self._write_checkpoint({"resume.txt": {"status": "done", "doc_type": "resume"}})
        mock_draft.return_value = "A marketer who blends writing and systems thinking."
        mock_select.return_value.ask.return_value = "accept"

        bootstrap_profile.write_background_guide(bootstrap_profile._load_checkpoint())

        with open(bootstrap_profile.BACKGROUND_GUIDE_PATH, encoding="utf-8") as f:
            content = f.read()
        self.assertEqual(content, "A marketer who blends writing and systems thinking.")

    @patch("bootstrap_profile.questionary.select")
    @patch("bootstrap_profile.bootstrap_extractors.draft_background_guide")
    def test_skip_writes_empty_file(self, mock_draft, mock_select):
        self._touch_source("resume.txt")
        self._write_checkpoint({"resume.txt": {"status": "done", "doc_type": "resume"}})
        mock_draft.return_value = "Some draft text."
        mock_select.return_value.ask.return_value = "skip"

        bootstrap_profile.write_background_guide(bootstrap_profile._load_checkpoint())

        with open(bootstrap_profile.BACKGROUND_GUIDE_PATH, encoding="utf-8") as f:
            content = f.read()
        self.assertEqual(content, "")

    def test_dry_run_writes_without_prompting(self):
        with patch("bootstrap_profile.questionary.select") as mock_select, \
             patch("bootstrap_profile.bootstrap_extractors.draft_background_guide", return_value="") as mock_draft:
            bootstrap_profile.write_background_guide({}, dry_run=True)
            mock_select.assert_not_called()
            mock_draft.assert_called_once()


class TestRunProfileSetup(BootstrapProfileTestCase):

    @patch("bootstrap_profile.write_background_guide")
    @patch("bootstrap_profile.write_cv_md")
    @patch("bootstrap_profile.write_verified_ledger")
    @patch("bootstrap_profile.write_portals_yml")
    @patch("bootstrap_profile.write_profile_yml")
    @patch("bootstrap_profile.collect_identity")
    @patch("bootstrap_profile._guess_recommendations", return_value=[])
    def test_calls_every_writer_in_order(
        self, mock_guess_recs, mock_collect_identity, mock_write_profile,
        mock_write_portals, mock_write_ledger, mock_write_cv, mock_write_bg,
    ):
        mock_collect_identity.return_value = {
            "full_name": "Jamie Rivera", "primary_roles": ["Marketing Manager"], "secondary_roles": [],
        }

        summary = bootstrap_profile.run_profile_setup()

        mock_write_profile.assert_called_once()
        mock_write_portals.assert_called_once()
        mock_write_ledger.assert_called_once()
        mock_write_cv.assert_called_once()
        mock_write_bg.assert_called_once()
        self.assertEqual(summary["full_name"], "Jamie Rivera")
        self.assertEqual(summary["primary_roles"], 1)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m unittest tests.test_bootstrap_profile.TestWriteBackgroundGuide tests.test_bootstrap_profile.TestRunProfileSetup -v`
Expected: FAIL with `AttributeError: module 'bootstrap_profile' has no attribute 'write_background_guide'` (and similarly for `run_profile_setup`).

- [ ] **Step 3: Write the implementation**

Append to `scripts/bootstrap_profile.py`:

```python
def _gather_background_source_texts(checkpoint: dict) -> list:
    texts = []
    for filename, result in sorted(checkpoint.items()):
        if result.get("status") != "done":
            continue
        if result.get("doc_type") not in ("resume", "linkedin_export", "recommendation_letter", "achievement_notes"):
            continue
        path = os.path.join(bootstrap_bullet_bank.SOURCE_DOCS_DIR, filename)
        text, _upload_path = _resolve_text_or_upload(path)
        if text:
            texts.append(text)
    return texts


def write_background_guide(checkpoint: dict, dry_run: bool = False) -> None:
    source_texts = _gather_background_source_texts(checkpoint)

    if dry_run:
        print("[DRY RUN] would draft user-background-guide.md and preview it for accept/regenerate/skip.")
        draft = bootstrap_extractors.draft_background_guide(source_texts, dry_run=dry_run)
        os.makedirs(os.path.dirname(BACKGROUND_GUIDE_PATH), exist_ok=True)
        with open(BACKGROUND_GUIDE_PATH, "w", encoding="utf-8") as f:
            f.write(draft)
        return

    draft = bootstrap_extractors.draft_background_guide(source_texts) if source_texts else ""
    choice = "skip"
    while True:
        print("\n--- Draft background guide ---\n")
        print(draft or "(nothing drafted -- no usable source text found)")
        print("\n--- End draft ---\n")
        choice = questionary.select(
            "What would you like to do with this draft?",
            choices=[
                questionary.Choice(title="Accept it as-is", value="accept"),
                questionary.Choice(title="Regenerate", value="regenerate"),
                questionary.Choice(title="Skip -- I'll write my own later", value="skip"),
            ],
            style=cli_art.QUESTIONARY_STYLE,
        ).ask()
        if choice == "regenerate":
            draft = bootstrap_extractors.draft_background_guide(source_texts)
            continue
        break

    os.makedirs(os.path.dirname(BACKGROUND_GUIDE_PATH), exist_ok=True)
    with open(BACKGROUND_GUIDE_PATH, "w", encoding="utf-8") as f:
        f.write(draft if choice == "accept" else "")


def run_profile_setup(dry_run: bool = False) -> dict:
    checkpoint = _load_checkpoint()
    identity = collect_identity(dry_run=dry_run)
    recommendations = _guess_recommendations(checkpoint, dry_run=dry_run)
    write_profile_yml(identity, recommendations)
    write_portals_yml(identity)
    write_verified_ledger(dry_run=dry_run)
    write_cv_md(identity, dry_run=dry_run)
    write_background_guide(checkpoint, dry_run=dry_run)
    return {
        "full_name": identity["full_name"],
        "primary_roles": len(identity["primary_roles"]),
        "secondary_roles": len(identity["secondary_roles"]),
        "recommendations_found": len(recommendations),
    }
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m unittest tests.test_bootstrap_profile -v`
Expected: all tests PASS.

- [ ] **Step 5: Commit**

```bash
git add scripts/bootstrap_profile.py tests/test_bootstrap_profile.py
git commit -m "Add background-guide draft/preview flow and run_profile_setup() entry point"
```

---

### Task 8: `bootstrap_bullet_bank.py` — wire Phase 0.5 into `main()`

**Files:**
- Modify: `scripts/bootstrap_bullet_bank.py`
- Test: `tests/test_bootstrap_bullet_bank_pipeline.py` (append)

**Interfaces:**
- Consumes: `bootstrap_profile.run_profile_setup(dry_run: bool) -> dict` (Task 7).
- Produces: `main()` now runs Phase 0.5 between `run_ingestion()`/`print_ingestion_summary()` and the `--dry-run` early-return / `run_full_pipeline()` call.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_bootstrap_bullet_bank_pipeline.py`:

```python
class TestMainCallsProfileSetup(unittest.TestCase):

    @patch("bootstrap_bullet_bank.bootstrap_profile.run_profile_setup")
    @patch("bootstrap_bullet_bank.run_full_pipeline")
    @patch("bootstrap_bullet_bank.run_ingestion")
    @patch("sys.argv", ["bootstrap_bullet_bank.py"])
    def test_profile_setup_runs_between_ingestion_and_pipeline(
        self, mock_run_ingestion, mock_run_full_pipeline, mock_profile_setup,
    ):
        mock_run_ingestion.return_value = {"extracted": 0, "attributed": 0, "flagged": 0, "certificates": 0}
        mock_profile_setup.return_value = {"full_name": "", "primary_roles": 0, "secondary_roles": 0, "recommendations_found": 0}

        bootstrap_bullet_bank.main()

        mock_profile_setup.assert_called_once_with(dry_run=False)
        mock_run_ingestion.assert_called_once()
        mock_run_full_pipeline.assert_called_once()

    @patch("bootstrap_bullet_bank.bootstrap_profile.run_profile_setup")
    @patch("bootstrap_bullet_bank.run_full_pipeline")
    @patch("bootstrap_bullet_bank.run_ingestion")
    @patch("sys.argv", ["bootstrap_bullet_bank.py", "--dry-run"])
    def test_profile_setup_receives_dry_run_flag(
        self, mock_run_ingestion, mock_run_full_pipeline, mock_profile_setup,
    ):
        mock_run_ingestion.return_value = {"extracted": 0, "attributed": 0, "flagged": 0, "certificates": 0}
        mock_profile_setup.return_value = {"full_name": "", "primary_roles": 0, "secondary_roles": 0, "recommendations_found": 0}

        bootstrap_bullet_bank.main()

        mock_profile_setup.assert_called_once_with(dry_run=True)
        mock_run_full_pipeline.assert_not_called()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m unittest tests.test_bootstrap_bullet_bank_pipeline.TestMainCallsProfileSetup -v`
Expected: FAIL with `AttributeError: module 'bootstrap_bullet_bank' has no attribute 'bootstrap_profile'`.

- [ ] **Step 3: Write the implementation**

In `scripts/bootstrap_bullet_bank.py`, add the import alongside the existing bootstrap imports near the top:

```python
import bootstrap_extractors  # noqa: E402
import bootstrap_profile  # noqa: E402
import bootstrap_timeline  # noqa: E402
import tag_bullet_bank  # noqa: E402
```

In `main()`, insert the Phase 0.5 call between the ingestion summary and the dry-run early return:

```python
def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--yes", action="store_true", help="Skip confirmation gates and run the full pipeline unattended.")
    parser.add_argument("--dry-run", action="store_true", help="Print prompts instead of calling the API, and skip the real six-stage pipeline entirely.")
    args = parser.parse_args()

    summary = run_ingestion(dry_run=args.dry_run)
    print_ingestion_summary(summary)

    bootstrap_profile.run_profile_setup(dry_run=args.dry_run)

    if args.dry_run:
        print("\n--dry-run set: skipping the six-stage pipeline.")
        return

    run_full_pipeline(skip_confirm=args.yes)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m unittest tests.test_bootstrap_bullet_bank_pipeline -v`
Expected: all tests PASS.

- [ ] **Step 5: Commit**

```bash
git add scripts/bootstrap_bullet_bank.py tests/test_bootstrap_bullet_bank_pipeline.py
git commit -m "Wire Phase 0.5 profile setup into bootstrap_bullet_bank.py's main()"
```

---

### Task 9: End-to-end fixture-based integration test for the full dry-run flow

**Files:**
- Modify: `tests/test_bootstrap_end_to_end.py` (append)

**Interfaces:**
- Consumes: everything from Tasks 1-8.
- Produces: no new production code -- proves Phase 0 + Phase 0.5 work together end to end under `--dry-run`, with zero API calls and zero prompts.

- [ ] **Step 1: Write the failing test**

Append to `tests/test_bootstrap_end_to_end.py`:

```python
import bootstrap_profile  # noqa: E402


class TestPhaseZeroPointFiveDryRunEndToEnd(BootstrapEndToEndTestCase):
    """Runs Phase 0 then Phase 0.5, both under dry_run=True, over real
    fixture files -- proving the whole chain (ingestion -> checkpoint ->
    timeline -> identity guessing -> file writing) doesn't crash and
    produces every expected file, with zero API calls and zero prompts."""

    def setUp(self):
        super().setUp()
        self.profile_yml_path = os.path.join(self.tmp_dir, "profile.yml")
        self.portals_yml_path = os.path.join(self.tmp_dir, "portals.yml")
        self.cv_md_path = os.path.join(self.tmp_dir, "cv.md")
        self.background_guide_path = os.path.join(self.tmp_dir, "user-background-guide.md")
        bootstrap_profile.PROFILE_YML_PATH = self.profile_yml_path
        bootstrap_profile.PORTALS_YML_PATH = self.portals_yml_path
        bootstrap_profile.CV_MD_PATH = self.cv_md_path
        bootstrap_profile.BACKGROUND_GUIDE_PATH = self.background_guide_path
        bootstrap_profile.VERIFIED_METRICS_PATH = os.path.join(self.tmp_dir, "verified_metrics.json")
        bootstrap_profile.VERIFIED_TOOLS_PATH = os.path.join(self.tmp_dir, "verified_tools.json")
        bootstrap_profile.VERIFIED_PROJECTS_PATH = os.path.join(self.tmp_dir, "verified_projects.json")
        bootstrap_profile.VERIFIED_FACTS_PATH = os.path.join(self.tmp_dir, "verified_facts.json")
        bootstrap_profile.VERIFIED_CLAIMS_PATH = os.path.join(self.tmp_dir, "verified-claims.csv")
        bootstrap_profile.EVIDENCE_GRAPH_PATH = os.path.join(self.tmp_dir, "evidence_graph.json")
        bootstrap_profile.EVIDENCE_GUIDE_PATH = os.path.join(self.tmp_dir, "evidence-guide.csv")
        bootstrap_profile.SCREENSHOT_METRICS_PATH = os.path.join(self.tmp_dir, "extracted-screenshot-metrics.csv")
        bootstrap_profile.RECRUITER_PATTERNS_PATH = os.path.join(self.tmp_dir, "recruiter_memory_patterns.json")

    def test_full_dry_run_flow_writes_every_phase_0_5_file(self):
        with open(os.path.join(bootstrap_bullet_bank.SOURCE_DOCS_DIR, "My_Resume.txt"), "w", encoding="utf-8") as f:
            f.write("Jamie Rivera\njamie@example.com\nAcme Corp, Marketing Manager, 2019-2022\n- Grew email list by 40%")

        bootstrap_bullet_bank.run_ingestion(dry_run=True)
        bootstrap_profile.run_profile_setup(dry_run=True)

        for path in (
            self.profile_yml_path, self.portals_yml_path, self.cv_md_path, self.background_guide_path,
            bootstrap_profile.VERIFIED_METRICS_PATH, bootstrap_profile.VERIFIED_TOOLS_PATH,
            bootstrap_profile.VERIFIED_PROJECTS_PATH, bootstrap_profile.VERIFIED_FACTS_PATH,
            bootstrap_profile.VERIFIED_CLAIMS_PATH, bootstrap_profile.EVIDENCE_GRAPH_PATH,
            bootstrap_profile.EVIDENCE_GUIDE_PATH, bootstrap_profile.SCREENSHOT_METRICS_PATH,
            bootstrap_profile.RECRUITER_PATTERNS_PATH,
        ):
            self.assertTrue(os.path.exists(path), f"expected {path} to exist")
```

- [ ] **Step 2: Run test to verify it fails or passes for the right reasons**

Run: `python -m unittest tests.test_bootstrap_end_to_end -v`

Since every production function this test touches already exists from Tasks 1-8, this should PASS immediately if everything upstream was wired correctly. If it fails, it's exposing a real integration bug (most likely a path-constant not being respected by `write_cv_md`'s reused `KnowledgeBase()`/`RulesBundle()` construction, since those read from `rewrite_bullets.py`'s own independent path constants rather than `bootstrap_profile.py`'s -- fix the root cause rather than patching around it here). Note that under `dry_run=True`, `write_cv_md`'s `RulesBundle(RULES_DIR, SCORING_DIR)` and `KnowledgeBase()` still construct for real (reading the actual repo's rule/scoring/knowledge-base files -- harmless local file reads, not API calls), and `process_bullet(..., dry_run=True)` short-circuits only the Gemini call itself.

- [ ] **Step 3: If needed, fix integration issues found**

- [ ] **Step 4: Run the full test suite to confirm no regressions**

Run: `python -m unittest discover -s tests -v`
Expected: every test in `tests/` PASSES, including all pre-existing tests untouched by this plan.

- [ ] **Step 5: Commit**

```bash
git add tests/test_bootstrap_end_to_end.py
git commit -m "Add end-to-end dry-run integration test covering Phase 0 + Phase 0.5"
```
