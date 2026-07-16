# Gemma Slim Context Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Give `gemma-4-31b-it` a slimmed, purpose-built system-instruction context in `rewrite_bullets.py` so a single rewrite call fits comfortably under Google's new 16,000 TPM cap, while `gemini-3.1-flash-lite`'s fallback path keeps today's full-quality context completely untouched.

**Architecture:** `KnowledgeBase` grows a second, parallel context-building path (`gemma_static_prefix` + a Gemma-specific segment cache) alongside its existing full one. A new generalized tag-filter helper (extending the existing `filter_claims_by_tags`/`CLAIM_TAG_KEYWORDS` pattern) trims `verified_projects.json`, `verified_metrics.json`, and the screenshot-metrics CSV down to a handful of tag-relevant rows for Gemma's tier only. `GeminiClient.generate()` gains an opt-out flag so `process_bullet()` can manage the Gemma→flash-lite handoff itself — explicitly, with the correct context tier for whichever model actually runs — instead of relying on `generate()`'s internal silent model swap.

**Tech Stack:** Python 3.10+, `pandas`, `pydantic`, stdlib `unittest` (run via `python -m unittest discover -s tests`).

## Global Constraints

- Test suite runs via `python -m unittest discover -s tests -v` from the project root with `.venv/` activated — not pytest.
- Do not modify `audit_keepers.py`, `score_keeper_gems.py`, `cluster_bullet_bank.py`, `embed_bullet_bank.py`, or `bullet_bank_menu.py` — all out of scope per the spec's Non-goals.
- `orchestrator.py` has its own independent copy of `filter_claims_by_tags`/`MAX_CLAIMS_ROWS` (confirmed via grep — not imported from `rewrite_bullets.py`). Do not touch `orchestrator.py`; nothing in this plan affects it.
- `GeminiClient.generate()`'s new parameter must default to preserving current behavior for every existing caller (`orchestrator.py`, `audit_keepers.py`, `score_keeper_gems.py`, `rewrite_bullets.py`'s own `score_bullet()`) with zero changes needed at those call sites.
- New row cap for Gemma-tier filtering: `MAX_GEMMA_FILTER_ROWS = 5`. Existing `MAX_CLAIMS_ROWS = 12` stays unchanged and continues to govern the full (flash-lite) tier only.

---

### Task 1: `GeminiClient.generate()` gets a `model_fallback` opt-out

**Files:**
- Modify: `scripts/gemini_client.py` (signature at line 155-164; fallback branches at lines 226-231 and 247-252)
- Test: `tests/test_gemini_client.py`

**Interfaces:**
- Produces: `GeminiClient.generate(..., model_fallback: bool = True)` — when `False`, a sustained failure exhausts `max_retries` and returns `(None, {})` (or raises `SustainedFailureError` per existing `SUSTAINED_FAILURE_THRESHOLD` logic, unchanged) without ever switching `model` mid-call. Default `True` is byte-for-byte identical to current behavior.

- [ ] **Step 1: Write the failing test**

Add to `tests/test_gemini_client.py`, inside a new test class (after `TestSustainedFailureDetection`):

```python
class TestModelFallbackOptOut(unittest.TestCase):

    def setUp(self):
        GeminiClient._consecutive_full_failures = 0

    def tearDown(self):
        GeminiClient._consecutive_full_failures = 0

    def _rate_limited_response(self):
        resp = MagicMock()
        resp.status_code = 429
        return resp

    @patch("gemini_client.time.sleep", lambda *a, **kw: None)
    @patch("gemini_client.requests.post")
    def test_no_swap_when_model_fallback_false(self, mock_post):
        mock_post.return_value = self._rate_limited_response()
        text, usage = GeminiClient.generate(
            model="gemma-4-31b-it",
            system_instruction="sys",
            contents="do the thing",
            max_retries=3,
            model_fallback=False,
        )
        self.assertIsNone(text)
        self.assertEqual(usage, {})
        # Every call must still target the original model -- no silent swap.
        for call in mock_post.call_args_list:
            self.assertIn("gemma-4-31b-it", call.args[0])
        self.assertEqual(mock_post.call_count, 3)

    @patch("gemini_client.time.sleep", lambda *a, **kw: None)
    @patch("gemini_client.requests.post")
    def test_default_still_swaps_after_two_failures(self, mock_post):
        mock_post.side_effect = [
            self._rate_limited_response(),
            self._rate_limited_response(),
            _success_response(),
        ]
        text, usage = GeminiClient.generate(
            model="gemma-4-31b-it",
            system_instruction="sys",
            contents="do the thing",
        )
        self.assertEqual(text, "ok")
        third_call_url = mock_post.call_args_list[2].args[0]
        self.assertIn("gemini-3.1-flash-lite", third_call_url)
```

- [ ] **Step 2: Run tests to verify the new ones fail**

Run: `source .venv/bin/activate && python -m unittest tests.test_gemini_client.TestModelFallbackOptOut -v`
Expected: `test_no_swap_when_model_fallback_false` FAILS with `TypeError: generate() got an unexpected keyword argument 'model_fallback'`. `test_default_still_swaps_after_two_failures` passes already (it's exercising existing default behavior) — that's fine, it's here as a regression guard for Step 3.

- [ ] **Step 3: Add the `model_fallback` parameter**

In `scripts/gemini_client.py`, change the `generate()` signature (currently lines 155-164):

```python
    @staticmethod
    def generate(
        model: str,
        system_instruction: str,
        contents: str,
        response_schema=None,
        temperature: float = 0.0,
        max_retries: int = 6,
        max_output_tokens: int = None,
        service_tier: str = "standard",
        model_fallback: bool = True,
    ) -> tuple[str | None, dict]:
```

Then guard both existing fallback branches. The transport-exception branch (currently):

```python
            except requests.exceptions.RequestException as e:
                failure_streak += 1
                if failure_streak >= 2 and model in MODEL_FALLBACKS:
```

becomes:

```python
            except requests.exceptions.RequestException as e:
                failure_streak += 1
                if model_fallback and failure_streak >= 2 and model in MODEL_FALLBACKS:
```

And the HTTP-status branch (currently):

```python
            if resp.status_code in RETRYABLE:
                if failure_streak >= 2 and model in MODEL_FALLBACKS:
```

becomes:

```python
            if resp.status_code in RETRYABLE:
                if model_fallback and failure_streak >= 2 and model in MODEL_FALLBACKS:
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `source .venv/bin/activate && python -m unittest tests.test_gemini_client -v`
Expected: all tests pass, including the two new ones and every pre-existing test in the file (7 previously + 2 new = 9).

- [ ] **Step 5: Commit**

```bash
git add scripts/gemini_client.py tests/test_gemini_client.py
git commit -m "Add model_fallback opt-out to GeminiClient.generate()

Lets a caller disable the internal Gemma<->flash-lite model swap for
a specific call, so context built for one model never silently ends
up being sent to the other. Default True preserves existing behavior
for every current caller."
```

---

### Task 2: Generalize `filter_claims_by_tags` with a `max_rows` parameter

**Files:**
- Modify: `scripts/rewrite_bullets.py` (function at lines 563-585)
- Create: `tests/test_rewrite_bullets.py`

**Interfaces:**
- Consumes: `CLAIM_TAG_KEYWORDS` (dict, existing, lines 278-294), `MAX_CLAIMS_ROWS = 12` (existing, line 170).
- Produces: `filter_claims_by_tags(df_claims: pd.DataFrame, tags: str, max_rows: int = MAX_CLAIMS_ROWS) -> pd.DataFrame` — same behavior as today when called with no `max_rows` (existing call site at line 670 is untouched and keeps working identically).

- [ ] **Step 1: Write the failing test**

Create `tests/test_rewrite_bullets.py`:

```python
import os
import sys
import unittest

import pandas as pd

SCRIPTS_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts")
sys.path.insert(0, SCRIPTS_DIR)

from rewrite_bullets import filter_claims_by_tags  # noqa: E402


def _claims_df():
    return pd.DataFrame({
        "Claim / Finding": [
            "Built 62+ email sequences",
            "Managed Salesforce CRM data hygiene",
            "Led content committee governance",
            "Sourced $1M+ in revenue",
            "Designed brand identity for Element 8",
        ],
        "Metric(s)": ["62 sequences", "2000+ accounts", "100+ assets", "$1M+", "N/A"],
        "Confidence": ["High", "High", "High", "High", "High"],
        "Evidence / Detail": ["", "", "", "", ""],
    })


class TestFilterClaimsByTagsMaxRows(unittest.TestCase):

    def test_default_max_rows_matches_existing_constant(self):
        df = pd.concat([_claims_df()] * 5, ignore_index=True)  # 25 rows, all [email]-matchable
        filtered = filter_claims_by_tags(df, "[email]")
        self.assertLessEqual(len(filtered), 12)  # MAX_CLAIMS_ROWS default unchanged

    def test_custom_max_rows_caps_tighter(self):
        df = pd.concat([_claims_df()] * 5, ignore_index=True)
        filtered = filter_claims_by_tags(df, "[email]", max_rows=5)
        self.assertLessEqual(len(filtered), 5)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `source .venv/bin/activate && python -m unittest tests.test_rewrite_bullets -v`
Expected: `test_custom_max_rows_caps_tighter` FAILS with `TypeError: filter_claims_by_tags() got an unexpected keyword argument 'max_rows'`.

- [ ] **Step 3: Add the `max_rows` parameter**

In `scripts/rewrite_bullets.py`, change `filter_claims_by_tags` (currently lines 563-585) from:

```python
def filter_claims_by_tags(df_claims: pd.DataFrame, tags: str) -> pd.DataFrame:
    if df_claims.empty:
        return df_claims
    tags_lower = tags.lower() if isinstance(tags, str) else ""
    keywords = []
    include_all = False
    for tag, kws in CLAIM_TAG_KEYWORDS.items():
        if tag in tags_lower:
            if not kws:
                include_all = True
                break
            keywords.extend(kws)
    if include_all or not keywords:
        return df_claims.head(MAX_CLAIMS_ROWS)
    text_cols = [c for c in df_claims.columns if df_claims[c].dtype == object]
    pattern = "|".join(re.escape(k) for k in keywords)
    mask = df_claims[text_cols].apply(
        lambda col: col.str.contains(pattern, case=False, na=False)
    ).any(axis=1)
    filtered = df_claims[mask]
    if len(filtered) < 3:
        filtered = df_claims.head(MAX_CLAIMS_ROWS)
    return filtered.head(MAX_CLAIMS_ROWS)
```

to:

```python
def filter_claims_by_tags(df_claims: pd.DataFrame, tags: str, max_rows: int = MAX_CLAIMS_ROWS) -> pd.DataFrame:
    if df_claims.empty:
        return df_claims
    tags_lower = tags.lower() if isinstance(tags, str) else ""
    keywords = []
    include_all = False
    for tag, kws in CLAIM_TAG_KEYWORDS.items():
        if tag in tags_lower:
            if not kws:
                include_all = True
                break
            keywords.extend(kws)
    if include_all or not keywords:
        return df_claims.head(max_rows)
    text_cols = [c for c in df_claims.columns if df_claims[c].dtype == object]
    pattern = "|".join(re.escape(k) for k in keywords)
    mask = df_claims[text_cols].apply(
        lambda col: col.str.contains(pattern, case=False, na=False)
    ).any(axis=1)
    filtered = df_claims[mask]
    if len(filtered) < 3:
        filtered = df_claims.head(max_rows)
    return filtered.head(max_rows)
```

(This is a signature change only — every internal `MAX_CLAIMS_ROWS` reference becomes `max_rows`, which defaults to `MAX_CLAIMS_ROWS`, so the existing call site at line 670 — `filter_claims_by_tags(self.df_claims, tags)` — behaves identically.)

- [ ] **Step 4: Run tests to verify they pass**

Run: `source .venv/bin/activate && python -m unittest tests.test_rewrite_bullets -v`
Expected: both tests pass.

- [ ] **Step 5: Run the full suite to confirm no regressions**

Run: `source .venv/bin/activate && python -m unittest discover -s tests`
Expected: `OK`, same total count as before plus the 2 new tests.

- [ ] **Step 6: Commit**

```bash
git add scripts/rewrite_bullets.py tests/test_rewrite_bullets.py
git commit -m "Add max_rows parameter to filter_claims_by_tags

Defaults to the existing MAX_CLAIMS_ROWS so the current call site is
unaffected -- lets Gemma's upcoming slim context request a tighter cap
without duplicating the filtering logic."
```

---

### Task 3: Add `filter_json_entries_by_tags` for list-of-dict KB files

**Files:**
- Modify: `scripts/rewrite_bullets.py`
- Test: `tests/test_rewrite_bullets.py`

**Interfaces:**
- Consumes: `CLAIM_TAG_KEYWORDS` (existing).
- Produces:
  - `MAX_GEMMA_FILTER_ROWS = 5` (new module-level constant, placed next to `MAX_CLAIMS_ROWS` at line 170).
  - `load_json_entries(path: str, list_key: str) -> list[dict]` — loads a KB file shaped like `{"_meta": {...}, "<list_key>": [...]}` (matches `verified_metrics.json`'s `"metrics"` key and `verified_projects.json`'s `"projects"` key) and returns the parsed list of entry dicts (not a pre-serialized string, unlike `load_json_file`).
  - `filter_json_entries_by_tags(entries: list[dict], tags: str, max_rows: int) -> list[dict]` — same keyword-match-then-cap behavior as `filter_claims_by_tags`, but operating on a list of dicts (matches against every string value in each dict) instead of a DataFrame.

- [ ] **Step 1: Write the failing test**

Add to `tests/test_rewrite_bullets.py`:

```python
from rewrite_bullets import filter_json_entries_by_tags, load_json_entries  # noqa: E402


def _metric_entries():
    return [
        {"id": "m1", "category": "campaign_performance", "label": "Email open rate", "context": "PTA sequence, 74% open"},
        {"id": "m2", "category": "campaign_performance", "label": "Email reply rate", "context": "Hot Zone sequence, 39% reply"},
        {"id": "m3", "category": "ops", "label": "CRM pipeline scrub", "context": "Uncovered $3M+ in stale Salesforce pipeline"},
        {"id": "m4", "category": "design", "label": "Brand flyer", "context": "COVID response flyer, Illustrator"},
    ]


class TestFilterJsonEntriesByTags(unittest.TestCase):

    def test_keyword_match_filters_to_relevant_entries(self):
        filtered = filter_json_entries_by_tags(_metric_entries(), "[email]", max_rows=5)
        ids = {e["id"] for e in filtered}
        self.assertIn("m1", ids)
        self.assertIn("m2", ids)

    def test_respects_max_rows_cap(self):
        entries = _metric_entries() * 3  # 12 entries, all [ops]-matchable via "salesforce"/"crm"
        filtered = filter_json_entries_by_tags(entries, "[ops]", max_rows=3)
        self.assertLessEqual(len(filtered), 3)

    def test_too_few_matches_falls_back_to_head(self):
        # "[generalist]" has no keywords in CLAIM_TAG_KEYWORDS -> include_all -> head(max_rows)
        filtered = filter_json_entries_by_tags(_metric_entries(), "[generalist]", max_rows=2)
        self.assertEqual(len(filtered), 2)

    def test_load_json_entries_reads_list_under_key(self):
        entries = load_json_entries(
            os.path.join(SCRIPTS_DIR, "..", "resume-engine", "knowledge_base", "verified_metrics.json"),
            "metrics",
        )
        self.assertIsInstance(entries, list)
        self.assertGreater(len(entries), 0)
        self.assertIn("category", entries[0])
```

- [ ] **Step 2: Run test to verify it fails**

Run: `source .venv/bin/activate && python -m unittest tests.test_rewrite_bullets -v`
Expected: `TestFilterJsonEntriesByTags` tests FAIL with `ImportError: cannot import name 'filter_json_entries_by_tags'`.

- [ ] **Step 3: Implement `MAX_GEMMA_FILTER_ROWS`, `load_json_entries`, and `filter_json_entries_by_tags`**

In `scripts/rewrite_bullets.py`, change line 170 from:

```python
MAX_CLAIMS_ROWS    = 12
```

to:

```python
MAX_CLAIMS_ROWS         = 12
MAX_GEMMA_FILTER_ROWS   = 5   # tighter cap for Gemma's slim tier -- see docs/superpowers/specs/2026-07-15-gemma-slim-context-design.md
```

Add `load_json_entries` next to `load_json_file` (after line 484, before `trim_profile_yml`):

```python
def load_json_entries(path: str, list_key: str) -> list:
    """Loads a KB file shaped like {"_meta": {...}, "<list_key>": [...]}
    and returns the parsed list of entry dicts -- unlike load_json_file,
    which returns a pre-serialized compact JSON string for direct prompt
    injection, this keeps the structure so callers can filter entries."""
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        entries = data.get(list_key, []) if isinstance(data, dict) else []
        print(f"   ✅ Loaded {list_key} entries ({len(entries)} rows)")
        return entries
    except Exception as e:
        print(f"   ⚠️ Could not load {list_key} entries: {e}")
        return []
```

Add `filter_json_entries_by_tags` directly after `filter_claims_by_tags` (after line 585 in the pre-Task-2 file; after Task 2's edit, directly following the updated function):

```python
def filter_json_entries_by_tags(entries: list, tags: str, max_rows: int) -> list:
    if not entries:
        return entries
    tags_lower = tags.lower() if isinstance(tags, str) else ""
    keywords = []
    include_all = False
    for tag, kws in CLAIM_TAG_KEYWORDS.items():
        if tag in tags_lower:
            if not kws:
                include_all = True
                break
            keywords.extend(kws)
    if include_all or not keywords:
        return entries[:max_rows]

    def _entry_matches(entry: dict) -> bool:
        haystack = " ".join(str(v) for v in entry.values() if isinstance(v, str)).lower()
        return any(kw in haystack for kw in keywords)

    filtered = [e for e in entries if _entry_matches(e)]
    if len(filtered) < 3:
        filtered = entries[:max_rows]
    return filtered[:max_rows]
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `source .venv/bin/activate && python -m unittest tests.test_rewrite_bullets -v`
Expected: all `TestFilterJsonEntriesByTags` tests pass, plus the pre-existing `TestFilterClaimsByTagsMaxRows` tests from Task 2 still pass.

- [ ] **Step 5: Commit**

```bash
git add scripts/rewrite_bullets.py tests/test_rewrite_bullets.py
git commit -m "Add filter_json_entries_by_tags for list-of-dict KB files

Same keyword-match-then-cap pattern as filter_claims_by_tags, applied
to verified_metrics.json/verified_projects.json's {\"_meta\", \"<key>\": [...]}
shape. MAX_GEMMA_FILTER_ROWS=5 is the tighter cap Gemma's slim tier
will use for all three newly-filtered components."
```

---

### Task 4: `KnowledgeBase` grows a Gemma-specific slim context path

**Files:**
- Modify: `scripts/rewrite_bullets.py` (`KnowledgeBase` class, currently lines 601-718)
- Test: `tests/test_rewrite_bullets.py`

**Interfaces:**
- Consumes: `filter_claims_by_tags(df, tags, max_rows=...)` (Task 2), `filter_json_entries_by_tags(entries, tags, max_rows)` + `load_json_entries` + `MAX_GEMMA_FILTER_ROWS` (Task 3), existing `extract_cv_section`, `build_background_summary`, `is_treering_bullet`, `get_verified_claims_text`.
- Produces:
  - `KnowledgeBase.gemma_static_prefix: str` (built once at init, parallel to `static_prefix`).
  - `KnowledgeBase.context_block_for_bullet_gemma(role_company: str, tags: str) -> str` — same signature/shape as the existing `context_block_for_bullet`, but returns the slim tier.
  - `warm_segment_cache(df)` now also populates a `_gemma_segment_cache` alongside the existing `_segment_cache`.

- [ ] **Step 1: Write the failing test**

Add to `tests/test_rewrite_bullets.py`:

```python
from rewrite_bullets import KnowledgeBase  # noqa: E402


class TestKnowledgeBaseGemmaTier(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.kb = KnowledgeBase()

    def test_gemma_static_prefix_excludes_profile(self):
        # profile.yml is dropped entirely from Gemma's tier -- its trimmed
        # content includes "target_roles:" per trim_profile_yml's KEEP_SECTIONS.
        if self.kb.profile:
            self.assertNotIn(self.kb.profile, self.kb.gemma_static_prefix)

    def test_gemma_static_prefix_includes_guardrails_and_voice(self):
        if self.kb.verified_facts:
            self.assertIn("VERIFIED FACTS", self.kb.gemma_static_prefix)
        if self.kb.verified_tools:
            self.assertIn("VERIFIED TOOLS", self.kb.gemma_static_prefix)
        if self.kb.voice_anchors:
            self.assertIn("VOICE ANCHORS", self.kb.gemma_static_prefix)

    def test_gemma_static_prefix_smaller_than_full(self):
        self.assertLess(len(self.kb.gemma_static_prefix), len(self.kb.static_prefix))

    def test_context_block_for_bullet_gemma_returns_slim_segment(self):
        df = pd.DataFrame({
            "Role / Company": ["Treering Yearbooks"],
            "Tags": ["[email]"],
        })
        self.kb.warm_segment_cache(df)
        gemma_block = self.kb.context_block_for_bullet_gemma("Treering Yearbooks", "[email]")
        full_block = self.kb.context_block_for_bullet("Treering Yearbooks", "[email]")
        self.assertIsInstance(gemma_block, str)
        self.assertLessEqual(len(gemma_block), len(full_block))
```

- [ ] **Step 2: Run test to verify it fails**

Run: `source .venv/bin/activate && python -m unittest tests.test_rewrite_bullets.TestKnowledgeBaseGemmaTier -v`
Expected: FAILS with `AttributeError: 'KnowledgeBase' object has no attribute 'gemma_static_prefix'`.

- [ ] **Step 3: Load parsed entry forms in `KnowledgeBase.__init__`**

In `scripts/rewrite_bullets.py`, `KnowledgeBase.__init__` (currently lines 602-623), change:

```python
    def __init__(self):
        print("\n📚 Loading knowledge base context...")
        self.cv_full           = load_text_file(KB_CV,               "cv.md")
        self.bg_raw            = load_text_file(KB_BACKGROUND,        "user-background-guide.md")
        raw_profile            = load_text_file(KB_PROFILE,           "profile.yml")
        self.profile           = trim_profile_yml(raw_profile)
        self.df_claims         = load_verified_claims(KB_VERIFIED_CLAIMS)
        self.screenshot_metrics = load_screenshot_metrics(KB_SCREENSHOT_METRICS)
        self.verified_facts    = load_json_file(KB_VERIFIED_FACTS,    "verified_facts.json")
        self.verified_metrics  = load_json_file(KB_VERIFIED_METRICS,  "verified_metrics.json")
        self.verified_projects = load_json_file(KB_VERIFIED_PROJECTS, "verified_projects.json")
        self.verified_tools    = load_json_file(KB_VERIFIED_TOOLS,    "verified_tools.json")
        self.recruiter_patterns = load_json_file(KB_RECRUITER_PATTERNS, "recruiter_memory_patterns.json")
        self.voice_anchors      = load_text_file(KB_VOICE_ANCHORS,    "voice-anchors.md")

        print(f"   💥 profile.yml trimmed to {len(self.profile):,} chars")

        self.static_prefix = self._build_static_prefix()
        print(f"   📌 Static prefix (Tier 1): {len(self.static_prefix):,} chars — shared across ALL bullets")

        self._segment_cache: dict = {}
        print("   ℹ️  Call warm_segment_cache(df_map) before starting the rewrite loop.\n")
```

to:

```python
    def __init__(self):
        print("\n📚 Loading knowledge base context...")
        self.cv_full           = load_text_file(KB_CV,               "cv.md")
        self.bg_raw            = load_text_file(KB_BACKGROUND,        "user-background-guide.md")
        raw_profile            = load_text_file(KB_PROFILE,           "profile.yml")
        self.profile           = trim_profile_yml(raw_profile)
        self.df_claims         = load_verified_claims(KB_VERIFIED_CLAIMS)
        self.screenshot_metrics = load_screenshot_metrics(KB_SCREENSHOT_METRICS)
        self.screenshot_df      = load_verified_claims(KB_SCREENSHOT_METRICS)  # same CSV, DataFrame form for Gemma-tier filtering
        self.verified_facts    = load_json_file(KB_VERIFIED_FACTS,    "verified_facts.json")
        self.verified_metrics  = load_json_file(KB_VERIFIED_METRICS,  "verified_metrics.json")
        self.metrics_entries   = load_json_entries(KB_VERIFIED_METRICS, "metrics")
        self.verified_projects = load_json_file(KB_VERIFIED_PROJECTS, "verified_projects.json")
        self.projects_entries  = load_json_entries(KB_VERIFIED_PROJECTS, "projects")
        self.verified_tools    = load_json_file(KB_VERIFIED_TOOLS,    "verified_tools.json")
        self.recruiter_patterns = load_json_file(KB_RECRUITER_PATTERNS, "recruiter_memory_patterns.json")
        self.voice_anchors      = load_text_file(KB_VOICE_ANCHORS,    "voice-anchors.md")

        print(f"   💥 profile.yml trimmed to {len(self.profile):,} chars")

        self.static_prefix = self._build_static_prefix()
        print(f"   📌 Static prefix (Tier 1): {len(self.static_prefix):,} chars — shared across ALL bullets")

        self.gemma_static_prefix = self._build_gemma_static_prefix()
        print(f"   📌 Gemma static prefix (slim): {len(self.gemma_static_prefix):,} chars — Gemma-only, flash-lite keeps the full tier")

        self._segment_cache: dict = {}
        self._gemma_segment_cache: dict = {}
        print("   ℹ️  Call warm_segment_cache(df_map) before starting the rewrite loop.\n")
```

`load_verified_claims` already does exactly what's needed for a raw DataFrame read of a CSV (it's not claims-specific despite the name — it just reads a CSV into a DataFrame, optionally filtering a `"Use in Resume?"` column if present, which `extracted-screenshot-metrics.csv` doesn't have, so it's a plain read for this file). Reusing it avoids adding a near-duplicate loader.

- [ ] **Step 4: Add `_build_gemma_static_prefix` and `_build_gemma_segment_bundle`, update `warm_segment_cache` and add `context_block_for_bullet_gemma`**

In `scripts/rewrite_bullets.py`, add these methods to `KnowledgeBase` directly after `_build_static_prefix` (after line 657):

```python
    def _build_gemma_static_prefix(self) -> str:
        """Slim static tier for Gemma only -- see docs/superpowers/specs/
        2026-07-15-gemma-slim-context-design.md. Keeps only guardrails
        (verified_facts, verified_tools) and voice_anchors (small, directly
        serves rewrite quality). Drops profile.yml entirely -- that's
        strategic career-positioning content, not needed to rewrite a
        single existing bullet."""
        sections = []
        if self.verified_facts:
            sections.append(
                "=== VERIFIED FACTS (high-confidence claims — use freely) ===\n"
                "These are the only facts about Morgan's career that are evidence-backed.\n"
                "Do NOT invent facts outside this list.\n"
                + self.verified_facts
            )
        if self.verified_tools:
            sections.append(
                "=== VERIFIED TOOLS (HF002 guard — only claim tools listed here) ===\n"
                "Never claim proficiency with any tool not present in this list.\n"
                + self.verified_tools
            )
        if self.voice_anchors:
            sections.append(
                "=== VOICE ANCHORS (real past answers, themes and quotes worth echoing) ===\n"
                + self.voice_anchors
            )
        return "\n\n".join(sections)

    def _build_gemma_segment_bundle(self, role_company: str, tags: str) -> str:
        """Slim segment bundle for Gemma only. cv excerpt and background
        summary are unchanged (already small); verified_projects and, for
        Treering bullets, claims/metrics/screenshots are tag-filtered to
        MAX_GEMMA_FILTER_ROWS instead of included whole or at the looser
        MAX_CLAIMS_ROWS cap."""
        sections = []
        cv_section = extract_cv_section(self.cv_full, role_company)
        if cv_section:
            label = ("ROLE CONTEXT (cv.md excerpt)"
                     if cv_section != self.cv_full else "CAREER OVERVIEW (cv.md)")
            sections.append(f"=== {label} ===\n{cv_section}")
        bg_summary = build_background_summary(tags)
        if bg_summary:
            sections.append(f"=== BACKGROUND CONTEXT ===\n{bg_summary}")

        filtered_projects = filter_json_entries_by_tags(self.projects_entries, tags, MAX_GEMMA_FILTER_ROWS)
        if filtered_projects:
            sections.append(
                "=== VERIFIED PROJECTS (tag-filtered) ===\n"
                "Use these to add accurate project detail and scope.\n"
                + json.dumps(filtered_projects, ensure_ascii=False, separators=(",", ":"))
            )

        if is_treering_bullet(role_company):
            filtered_claims = filter_claims_by_tags(self.df_claims, tags, max_rows=MAX_GEMMA_FILTER_ROWS)
            claims_text = get_verified_claims_text(filtered_claims)
            if claims_text:
                sections.append(
                    "=== VERIFIED CLAIMS & METRICS (Treering — resume-usable, tag-filtered) ===\n"
                    "Use these to inject real, verified metrics where appropriate. "
                    "Do NOT use metrics marked Medium or Low confidence as hard facts.\n"
                    + claims_text
                )
            filtered_screenshots = filter_claims_by_tags(self.screenshot_df, tags, max_rows=MAX_GEMMA_FILTER_ROWS)
            if not filtered_screenshots.empty:
                sections.append(
                    "=== SCREENSHOT-SOURCED METRICS (tag-filtered) ===\n"
                    + filtered_screenshots.to_csv(index=False)
                )
            filtered_metrics = filter_json_entries_by_tags(self.metrics_entries, tags, MAX_GEMMA_FILTER_ROWS)
            if filtered_metrics:
                sections.append(
                    "=== VERIFIED METRICS (authoritative — tag-filtered) ===\n"
                    "These are the ONLY numeric metrics that may be cited as hard facts in Treering bullets.\n"
                    + json.dumps(filtered_metrics, ensure_ascii=False, separators=(",", ":"))
                )
        return "\n\n".join(sections)
```

Update `warm_segment_cache` (currently lines 689-701) from:

```python
    def warm_segment_cache(self, df: pd.DataFrame) -> None:
        self._segment_cache = {}
        pairs = df[["Role / Company", "Tags"]].drop_duplicates()
        print(f"\n🔥 Warming segment cache for {len(pairs)} unique (company, tags) combos...")
        for _, row in pairs.iterrows():
            rc   = str(row["Role / Company"])
            tags = str(row["Tags"])
            key  = (rc, tags)
            bundle = self._build_segment_bundle(rc, tags)
            self._segment_cache[key] = bundle
            treering_flag = " [Treering+claims]" if is_treering_bullet(rc) else ""
            print(f"   📦 ({rc[:30]!r}, {tags[:40]!r}) → {len(bundle):,} chars{treering_flag}")
        print(f"   ✅ {len(self._segment_cache)} segment bundles ready.\n")
```

to:

```python
    def warm_segment_cache(self, df: pd.DataFrame) -> None:
        self._segment_cache = {}
        self._gemma_segment_cache = {}
        pairs = df[["Role / Company", "Tags"]].drop_duplicates()
        print(f"\n🔥 Warming segment cache for {len(pairs)} unique (company, tags) combos...")
        for _, row in pairs.iterrows():
            rc   = str(row["Role / Company"])
            tags = str(row["Tags"])
            key  = (rc, tags)
            bundle = self._build_segment_bundle(rc, tags)
            self._segment_cache[key] = bundle
            gemma_bundle = self._build_gemma_segment_bundle(rc, tags)
            self._gemma_segment_cache[key] = gemma_bundle
            treering_flag = " [Treering+claims]" if is_treering_bullet(rc) else ""
            print(f"   📦 ({rc[:30]!r}, {tags[:40]!r}) → {len(bundle):,} chars{treering_flag} (Gemma: {len(gemma_bundle):,} chars)")
        print(f"   ✅ {len(self._segment_cache)} segment bundles ready.\n")
```

Add `context_block_for_bullet_gemma` directly after `context_block_for_bullet` (after line 709):

```python
    def context_block_for_bullet_gemma(self, role_company: str, tags: str) -> str:
        key = (role_company, tags)
        if key not in self._gemma_segment_cache:
            print(f"   ⚠️ Gemma cache miss for {key} — building segment on demand.")
            self._gemma_segment_cache[key] = self._build_gemma_segment_bundle(role_company, tags)
        segment = self._gemma_segment_cache[key]
        return f"{self.gemma_static_prefix}\n\n{segment}" if segment else self.gemma_static_prefix
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `source .venv/bin/activate && python -m unittest tests.test_rewrite_bullets -v`
Expected: all `TestKnowledgeBaseGemmaTier` tests pass, plus every earlier test in the file.

- [ ] **Step 6: Run the full suite to confirm no regressions**

Run: `source .venv/bin/activate && python -m unittest discover -s tests`
Expected: `OK`.

- [ ] **Step 7: Commit**

```bash
git add scripts/rewrite_bullets.py tests/test_rewrite_bullets.py
git commit -m "Add Gemma-specific slim context tier to KnowledgeBase

gemma_static_prefix drops profile.yml, keeps verified_facts/tools/
voice-anchors whole. context_block_for_bullet_gemma() mirrors the
existing full-tier method but pulls from a parallel, tag-filtered
segment cache (projects/metrics/screenshots/claims capped at
MAX_GEMMA_FILTER_ROWS=5). Flash-lite's existing full-tier path is
completely untouched."
```

---

### Task 5: `process_bullet()` manages the Gemma→flash-lite handoff explicitly

**Files:**
- Modify: `scripts/rewrite_bullets.py` (`process_bullet`, currently lines 1068-1186)
- Test: `tests/test_rewrite_bullets.py`

**Interfaces:**
- Consumes: `KnowledgeBase.context_block_for_bullet_gemma` (Task 4), `KnowledgeBase.context_block_for_bullet` (existing), `GeminiClient.generate(..., model_fallback=...)` (Task 1).
- Produces: `process_bullet(...)` return shape is unchanged (same dict keys as today) — this task only changes which context tier and which model get used per attempt, and adds an immediate Gemma→flash-lite handoff on confirmed Gemma exhaustion.

- [ ] **Step 1: Write the failing test**

Add to `tests/test_rewrite_bullets.py`:

```python
from unittest.mock import patch
from rewrite_bullets import process_bullet, KnowledgeBase  # noqa: E402


class TestProcessBulletGemmaHandoff(unittest.TestCase):

    def setUp(self):
        self.kb = KnowledgeBase()
        df = pd.DataFrame({
            "Role / Company": ["Acme Corp"],
            "Tags": ["[content]"],
        })
        self.kb.warm_segment_cache(df)
        self.row = pd.Series({
            "Bullet Point": "Wrote content for a team.",
            "Role / Company": "Acme Corp",
            "Tags": "[content]",
            "weaknesses": "",
            "accuracy_score": None, "believability_score": None,
            "clarity_score": None, "ats_value": None, "manager_test": None,
        })

    @patch("rewrite_bullets.time.sleep", lambda *a, **kw: None)
    @patch("rewrite_bullets.score_bullet")
    @patch("rewrite_bullets.GeminiClient.generate")
    def test_gemma_exhaustion_falls_back_to_flash_lite_with_full_context(self, mock_generate, mock_score):
        # First call (Gemma) exhausts and returns None; second call
        # (flash-lite) succeeds. Assert: exactly 2 generate() calls, the
        # first targets gemma-4-31b-it with model_fallback=False, the
        # second targets gemini-3.1-flash-lite with the FULL context
        # (longer than Gemma's slim one).
        mock_generate.side_effect = [
            (None, {}),
            ('{"rewritten_bullet": "Authored content for a cross-functional team.", "reasoning": "", "context_gaps": ""}', {}),
        ]
        mock_score.return_value = {
            "accuracy_score": 95, "believability_score": 95, "clarity_score": 95,
            "ats_value": 90, "manager_test": "PASS", "weaknesses": "",
        }

        result = process_bullet(self.row, self.kb, rewrite_system="sys", score_system="score-sys", dry_run=False)

        self.assertEqual(mock_generate.call_count, 2)
        first_call_kwargs = mock_generate.call_args_list[0].kwargs
        second_call_kwargs = mock_generate.call_args_list[1].kwargs

        self.assertEqual(first_call_kwargs["model"], "gemma-4-31b-it")
        self.assertEqual(first_call_kwargs["model_fallback"], False)

        self.assertEqual(second_call_kwargs["model"], "gemini-3.1-flash-lite")
        self.assertGreater(
            len(second_call_kwargs["contents"]), len(first_call_kwargs["contents"])
        )
        self.assertEqual(result["rewrite_status"], "KEEP")


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `source .venv/bin/activate && python -m unittest tests.test_rewrite_bullets.TestProcessBulletGemmaHandoff -v`
Expected: FAILS — with the current code, `mock_generate.call_args_list[0].kwargs` has no `model_fallback` key (`KeyError`), since `process_bullet` doesn't pass it yet; the first call also currently reuses the single, unified `kb_context`, not a Gemma-specific slim one.

- [ ] **Step 3: Restructure `process_bullet`**

In `scripts/rewrite_bullets.py`, change `process_bullet` (currently lines 1068-1138, the setup and attempt loop through the exception handling) from:

```python
    kb_context = kb.context_block_for_bullet(role_company, tags)
    kb_context_chars = len(kb_context)

    current_bullet = original_bullet
    current_scores = original_scores.copy()
    last_rewrite = last_reasoning = last_gaps = ""
    active_rewrite_model   = REWRITE_MODEL
    rewrite_parse_failures = 0

    for attempt in range(1, MAX_ATTEMPTS + 1):
        print(f"   🖊  Attempt {attempt}/{MAX_ATTEMPTS}... (model: {active_rewrite_model})")

        use_minimal_schema = GEMMA_MINIMAL_JSON and "gemma" in active_rewrite_model.lower()
        runner_schema = RewriteOutputMinimalSchema if use_minimal_schema else RewriteOutputSchema

        prompt = build_rewrite_prompt(
            bullet=current_bullet,
            tags=tags,
            weaknesses=str(current_scores.get("weaknesses", "")),
            kb_context=kb_context,
            attempt=attempt,
            prev_scores=current_scores if attempt > 1 else None,
            minimal_schema=use_minimal_schema,
        )

        if dry_run:
            print(f"\n{'='*60}\nDRY RUN PROMPT (attempt {attempt}):\n{prompt}\n{'='*60}\n")
            rewritten = f"[DRY RUN] {original_bullet}"
            reasoning = "dry-run"
            gaps = ""
        else:
            try:
                raw, usage = GeminiClient.generate(
                    model=active_rewrite_model,
                    system_instruction=rewrite_system,
                    contents=prompt,
                    temperature=0.7,
                    response_schema=runner_schema,
                )
                _log_cache_stats(usage, kb_context_chars, attempt)
                parsed = GeminiClient.parse_json(raw)
                rewritten = str(parsed.get("rewritten_bullet", "")).strip()
                reasoning = str(parsed.get("reasoning", "")).strip()
                gaps      = str(parsed.get("context_gaps", "")).strip()

                if not rewritten:
                    raise ValueError("Empty rewritten_bullet in response")

            except SustainedFailureError:
                raise
            except Exception as e:
                rewrite_parse_failures += 1
                print(f"   ⚠️ Rewrite parse error (attempt {attempt}): {e}")
                if rewrite_parse_failures >= MAX_REWRITE_PARSE_FAILURES and active_rewrite_model != REWRITE_FALLBACK_MODEL:
                    print(f"   🔄 Switching to fallback model: {REWRITE_FALLBACK_MODEL}")
                    active_rewrite_model = REWRITE_FALLBACK_MODEL
                time.sleep(SLEEP_ON_RETRY)
                continue
```

to:

```python
    kb_context_gemma = kb.context_block_for_bullet_gemma(role_company, tags)
    kb_context_full  = kb.context_block_for_bullet(role_company, tags)

    current_bullet = original_bullet
    current_scores = original_scores.copy()
    last_rewrite = last_reasoning = last_gaps = ""
    active_rewrite_model   = REWRITE_MODEL
    rewrite_parse_failures = 0

    for attempt in range(1, MAX_ATTEMPTS + 1):
        print(f"   🖊  Attempt {attempt}/{MAX_ATTEMPTS}... (model: {active_rewrite_model})")

        is_gemma_attempt = "gemma" in active_rewrite_model.lower()
        kb_context = kb_context_gemma if is_gemma_attempt else kb_context_full

        use_minimal_schema = GEMMA_MINIMAL_JSON and is_gemma_attempt
        runner_schema = RewriteOutputMinimalSchema if use_minimal_schema else RewriteOutputSchema

        prompt = build_rewrite_prompt(
            bullet=current_bullet,
            tags=tags,
            weaknesses=str(current_scores.get("weaknesses", "")),
            kb_context=kb_context,
            attempt=attempt,
            prev_scores=current_scores if attempt > 1 else None,
            minimal_schema=use_minimal_schema,
        )

        if dry_run:
            print(f"\n{'='*60}\nDRY RUN PROMPT (attempt {attempt}):\n{prompt}\n{'='*60}\n")
            rewritten = f"[DRY RUN] {original_bullet}"
            reasoning = "dry-run"
            gaps = ""
        else:
            try:
                raw, usage = GeminiClient.generate(
                    model=active_rewrite_model,
                    system_instruction=rewrite_system,
                    contents=prompt,
                    temperature=0.7,
                    response_schema=runner_schema,
                    model_fallback=not is_gemma_attempt,
                )
                _log_cache_stats(usage, len(kb_context), attempt)

                if raw is None and is_gemma_attempt:
                    # Gemma exhausted its own retries (model_fallback=False,
                    # so no internal swap happened) -- a confirmed capacity
                    # exhaustion, not a one-off parse hiccup. Hand off to
                    # flash-lite with the FULL context immediately rather
                    # than retrying Gemma again with the same slim context.
                    print(f"   🔄 Gemma exhausted retries — switching to fallback model: {REWRITE_FALLBACK_MODEL}")
                    active_rewrite_model = REWRITE_FALLBACK_MODEL
                    time.sleep(SLEEP_ON_RETRY)
                    continue

                parsed = GeminiClient.parse_json(raw)
                rewritten = str(parsed.get("rewritten_bullet", "")).strip()
                reasoning = str(parsed.get("reasoning", "")).strip()
                gaps      = str(parsed.get("context_gaps", "")).strip()

                if not rewritten:
                    raise ValueError("Empty rewritten_bullet in response")

            except SustainedFailureError:
                raise
            except Exception as e:
                rewrite_parse_failures += 1
                print(f"   ⚠️ Rewrite parse error (attempt {attempt}): {e}")
                if rewrite_parse_failures >= MAX_REWRITE_PARSE_FAILURES and active_rewrite_model != REWRITE_FALLBACK_MODEL:
                    print(f"   🔄 Switching to fallback model: {REWRITE_FALLBACK_MODEL}")
                    active_rewrite_model = REWRITE_FALLBACK_MODEL
                time.sleep(SLEEP_ON_RETRY)
                continue
```

Everything after this block (scoring, `decide_action`, KEEP/MANUAL handling, the final `return` statements) is unchanged.

- [ ] **Step 4: Run tests to verify they pass**

Run: `source .venv/bin/activate && python -m unittest tests.test_rewrite_bullets -v`
Expected: `TestProcessBulletGemmaHandoff` passes, plus every earlier test in the file.

- [ ] **Step 5: Run the full suite to confirm no regressions**

Run: `source .venv/bin/activate && python -m unittest discover -s tests`
Expected: `OK`.

- [ ] **Step 6: Verify with a real dry run**

Run: `source .venv/bin/activate && python scripts/rewrite_bullets.py --limit 1 --dry-run`
Expected: no crash; printed prompt shows the Gemma slim context (noticeably shorter than a full-context prompt would be — no `profile.yml`/`TARGET ROLES & PROFILE` section present).

- [ ] **Step 7: Commit**

```bash
git add scripts/rewrite_bullets.py tests/test_rewrite_bullets.py
git commit -m "process_bullet(): explicit Gemma-to-flash-lite handoff

Gemma attempts now use the slim context with model_fallback=False;
on a confirmed exhaustion (raw is None), hands off immediately to
flash-lite with the full context instead of retrying Gemma again or
risking flash-lite silently inheriting Gemma's slim context via
GeminiClient's internal fallback."
```

---

## Self-Review Notes

- **Spec coverage:** Problem/Goal (Tasks 4-5), Component Breakdown static tier (Task 4), Component Breakdown segment bundle (Tasks 3-4), Shared Tag-Filter Helper (Tasks 2-3), Model Handoff (Tasks 1, 5), Testing (every task's test steps; rewrite-quality-with-slim-context explicitly left to live-run review per Task 5 Step 6 and the spec's Non-goals).
- **Type consistency:** `filter_claims_by_tags(df, tags, max_rows=...)` (Task 2) and `filter_json_entries_by_tags(entries, tags, max_rows)` (Task 3) share the same `max_rows` parameter name and position; `context_block_for_bullet_gemma(role_company, tags)` (Task 4) matches the existing `context_block_for_bullet(role_company, tags)` signature exactly, as does `_build_gemma_static_prefix`/`_build_gemma_segment_bundle` mirroring `_build_static_prefix`/`_build_segment_bundle`.
- **No placeholders:** every step above shows complete code, not a description of intended code.
