# Voice Anchor Matcher Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement the Voice Anchor Matcher & Stylometric Anti-AI Linter (Feature #9 / Group D) to detect synthetic prose monotony (low sentence variance/burstiness, low lexical diversity, repetitive syntactic openers) and enforce authentic candidate rhythm in cover letters before final rendering.

**Architecture:** A new pure computation engine (`scripts/voice_metrics.py`) evaluates statistical stylometry against declarative thresholds in `resume-engine/scoring/voice_rules.yaml`. `scripts/validate_coverletter.py` calls this module during validation, feeding actionable violation messages into `orchestrator.py`'s single-retry loop if an LLM draft slips into robotic cadence. `resume-engine/prompts/tailor_coverletter.md` is simultaneously updated with human-cadence and sentence-variance guidelines.

**Tech Stack:** Python 3.10+, stdlib (`math`, `re`, `collections`), YAML (`pyyaml`), stdlib `unittest`.

**Spec:** `docs/superpowers/specs/2026-08-17-voice-anchor-matcher-design.md`

---

## Global Constraints

- **Deterministic & Pure:** `scripts/voice_metrics.py` contains pure functions with zero network/API side effects. All mathematical computations (mean, sample standard deviation, Type-Token Ratio) use standard library modules.
- **Robust Sentence Tokenization:** Tokenizer handles abbreviations ("e.g.", "i.e.", "Inc.", "Ph.D.", "vs."), decimal metrics ("$4.5M", "99.9%"), and punctuation-embedded tokens without false sentence splitting.
- **Backward Compatibility:** If `voice_rules.yaml` is absent or unreadable, `voice_metrics.py` falls back to sane default thresholds.
- **Pipeline Integration:** Follows the established cover-letter validation pattern in `scripts/validate_coverletter.py` and `scripts/orchestrator.py` — non-fatal warnings after retry, blocking on catastrophic failure.
- **Full Suite Regression:** Run the entire test suite (`python -m unittest discover -s tests -v`) after every task.

---

## Task 1: `voice_rules.yaml` and `scripts/voice_metrics.py`

**Files:**
- Create: `resume-engine/scoring/voice_rules.yaml`
- Create: `tests/test_voice_metrics.py`
- Create: `scripts/voice_metrics.py`

**Interfaces:**
- Module: `scripts/voice_metrics.py`
  - `split_sentences(text: str) -> list[str]`
  - `compute_sentence_length_stats(sentences: list[str]) -> dict`
  - `compute_type_token_ratio(text: str) -> dict`
  - `detect_consecutive_opener_repetitions(sentences: list[str], max_consecutive: int = 2) -> list[str]`
  - `analyze_voice_metrics(cover_letter_data: dict, rules: dict | None = None) -> list[str]`

- [ ] **Step 1: Create declarative configuration `resume-engine/scoring/voice_rules.yaml`**

```yaml
version: 1.0
# Voice Anchor & Stylometric Rules (Feature #9 / Group D)
# Sourced from Morgan Escott Design System, voice-anchors.md, and 2026 ATS/AI-Detection Research.

thresholds:
  # Sentence length burstiness & variance (in words)
  sentence_std_dev_min: 4.5       # std dev < 4.5 flags monotonous AI pacing
  sentence_span_min: 12           # (max_len - min_len) must be >= 12 words
  sentence_length_max: 42         # sentences > 42 words flag as run-on
  sentence_length_min: 3          # sentences < 3 words flag as fragments

  # Lexical diversity (Type-Token Ratio)
  type_token_ratio_min: 0.46      # unique words / total words

  # Syntactic repetition
  max_consecutive_same_opener: 2  # flags 3+ consecutive sentences starting identically
```

- [ ] **Step 2: Write unit tests in `tests/test_voice_metrics.py`**

```python
import os
import sys
import unittest

SCRIPTS_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts")
sys.path.insert(0, SCRIPTS_DIR)

import voice_metrics  # noqa: E402


class TestVoiceMetrics(unittest.TestCase):

    def test_split_sentences_handles_abbreviations_and_decimals(self):
        text = "I grew revenue by 14.5% at Acme Inc. in St. Louis. For e.g., we built tools for Ph.D. researchers."
        sentences = voice_metrics.split_sentences(text)
        self.assertEqual(len(sentences), 2)
        self.assertEqual(sentences[0], "I grew revenue by 14.5% at Acme Inc. in St. Louis.")
        self.assertEqual(sentences[1], "For e.g., we built tools for Ph.D. researchers.")

    def test_compute_sentence_length_stats(self):
        sentences = [
            "Short sentence.",                       # 2 words
            "This is a medium length sentence here.", # 7 words
            "This is a substantially longer compound sentence designed to verify that the standard deviation calculation works properly.", # 17 words
        ]
        stats = voice_metrics.compute_sentence_length_stats(sentences)
        self.assertEqual(stats["counts"], [2, 7, 17])
        self.assertAlmostEqual(stats["mean"], 8.666, places=2)
        self.assertGreater(stats["std_dev"], 6.0)
        self.assertEqual(stats["span"], 15)

    def test_uniform_ai_text_triggers_variance_violation(self):
        # Monotonous synthetic paragraph where every sentence is exactly 10-11 words
        paragraphs = [
            "The quick brown fox jumps over the very lazy sleeping dog today. "
            "Another quick brown fox jumps over another very lazy sleeping dog. "
            "A third quick brown fox jumps over that same lazy sleeping dog. "
            "Every single sentence has almost the exact same number of words."
        ]
        letter_data = {"body_paragraphs": paragraphs}
        violations = voice_metrics.analyze_voice_metrics(letter_data)
        self.assertTrue(any("monotonous" in v.lower() or "std dev" in v.lower() for v in violations))

    def test_dynamic_human_text_passes_all_checks(self):
        paragraphs = [
            "I love building systems that work quietly in the background — so people don’t have to. "
            "Over the past six years at Treering, I spearheaded our outbound communication engine, connecting with thousands of school coordinators and driving an unexpected 17% revenue surge through deeply personalized messaging. "
            "Clarity and empathy win every time.",
            "That loop of ideate, execute, and optimize is where I do my best work. "
            "Whether designing complex Salesforce workflows or crafting narrative email sequences, I focus on respecting the reader's time while earning their trust."
        ]
        letter_data = {"body_paragraphs": paragraphs}
        violations = voice_metrics.analyze_voice_metrics(letter_data)
        self.assertEqual(violations, [])

    def test_type_token_ratio_flags_repetitive_text(self):
        # Extremely repetitive vocabulary
        repetitive = "Marketing marketing marketing strategy strategy strategy growth growth growth team team team."
        letter_data = {"body_paragraphs": [repetitive]}
        violations = voice_metrics.analyze_voice_metrics(letter_data)
        self.assertTrue(any("lexical diversity" in v.lower() or "type-token" in v.lower() for v in violations))

    def test_consecutive_opener_detection(self):
        paragraphs = [
            "I built the marketing pipeline from scratch. "
            "I managed five cross-functional specialists daily. "
            "I delivered $4M in pipeline value during Q3."
        ]
        letter_data = {"body_paragraphs": paragraphs}
        violations = voice_metrics.analyze_voice_metrics(letter_data)
        self.assertTrue(any("consecutive sentences begin with" in v.lower() for v in violations))


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 3: Implement `scripts/voice_metrics.py`**

```python
"""
voice_metrics.py — Pure statistical stylometry and voice anchor validator.

Measures structural rhythm, sentence-length burstiness, lexical diversity,
and syntactic repetition in free prose (cover letters) to prevent
monotonous "AI-beige" synthetic generation and preserve authentic candidate voice.
"""

import math
import re
from typing import Any, Dict, List

_ABBREVIATIONS = (
    r"e\.g\.",
    r"i\.e\.",
    r"inc\.",
    r"corp\.",
    r"ltd\.",
    r"co\.",
    r"dr\.",
    r"mr\.",
    r"ms\.",
    r"mrs\.",
    r"vs\.",
    r"ph\.d\.",
    r"u\.s\.",
    r"st\.",
)

_ABBREV_REGEX = re.compile(r"\b(?:" + "|".join(_ABBREVIATIONS) + r")", re.IGNORECASE)
_DECIMAL_REGEX = re.compile(r"\b\d+\.\d+\b")

DEFAULT_THRESHOLDS = {
    "sentence_std_dev_min": 4.5,
    "sentence_span_min": 12,
    "sentence_length_max": 42,
    "sentence_length_min": 3,
    "type_token_ratio_min": 0.46,
    "max_consecutive_same_opener": 2,
}


def split_sentences(text: str) -> List[str]:
    """Splits text into sentences while protecting abbreviations and decimals."""
    if not text or not text.strip():
        return []

    # Mask decimals (e.g. 14.5% -> 14<DECIMAL>5%)
    masked = _DECIMAL_REGEX.sub(lambda m: m.group(0).replace(".", "<DECIMAL>"), text)

    # Mask abbreviations
    masked = _ABBREV_REGEX.sub(lambda m: m.group(0).replace(".", "<DOT>"), masked)

    # Split on sentence terminals followed by whitespace
    raw_splits = re.split(r"(?<=[.!?])\s+", masked)

    sentences = []
    for s in raw_splits:
        unmasked = s.replace("<DECIMAL>", ".").replace("<DOT>", ".").strip()
        if unmasked:
            sentences.append(unmasked)
    return sentences


def compute_sentence_length_stats(sentences: List[str]) -> Dict[str, Any]:
    """Computes word counts, mean, standard deviation, and span across sentences."""
    if not sentences:
        return {"counts": [], "mean": 0.0, "std_dev": 0.0, "span": 0, "min": 0, "max": 0}

    counts = [len(re.findall(r"\b\w+(?:[-']\w+)?\b", s)) for s in sentences]
    counts = [c for c in counts if c > 0]

    if not counts:
        return {"counts": [], "mean": 0.0, "std_dev": 0.0, "span": 0, "min": 0, "max": 0}

    n = len(counts)
    mean = sum(counts) / n
    if n > 1:
        variance = sum((x - mean) ** 2 for x in counts) / (n - 1)
        std_dev = math.sqrt(variance)
    else:
        std_dev = 0.0

    min_len = min(counts)
    max_len = max(counts)
    span = max_len - min_len

    return {
        "counts": counts,
        "mean": mean,
        "std_dev": std_dev,
        "span": span,
        "min": min_len,
        "max": max_len,
    }


def compute_type_token_ratio(text: str) -> Dict[str, float]:
    """Computes Standard and Root Type-Token Ratio for lexical diversity."""
    words = re.findall(r"\b[a-zA-Z]+(?:'[a-zA-Z]+)?\b", text.lower())
    if not words:
        return {"ttr": 1.0, "total_tokens": 0, "unique_tokens": 0}

    n = len(words)
    v = len(set(words))
    ttr = v / n
    return {"ttr": ttr, "total_tokens": n, "unique_tokens": v}


def detect_consecutive_opener_repetitions(sentences: List[str], max_consecutive: int = 2) -> List[str]:
    """Detects 3+ consecutive sentences starting with identical 1-2 word openers."""
    violations = []
    if len(sentences) < 3:
        return violations

    openers = []
    for s in sentences:
        tokens = re.findall(r"\b\w+\b", s.lower())
        if tokens:
            first_word = tokens[0]
            first_two = f"{tokens[0]} {tokens[1]}" if len(tokens) > 1 else first_word
            openers.append((first_word, first_two))
        else:
            openers.append(("", ""))

    consecutive_word_count = 1
    current_word = ""

    for i in range(len(openers)):
        word = openers[i][0]
        if not word:
            consecutive_word_count = 1
            current_word = ""
            continue

        if word == current_word:
            consecutive_word_count += 1
            if consecutive_word_count > max_consecutive:
                violations.append(
                    f"{consecutive_word_count} consecutive sentences begin with '{word.capitalize()}...'"
                )
        else:
            current_word = word
            consecutive_word_count = 1

    return list(dict.fromkeys(violations))


def analyze_voice_metrics(cover_letter_data: dict, rules: dict | None = None) -> List[str]:
    """Evaluates cover letter paragraphs against voice anchor and stylometric rules."""
    paragraphs = cover_letter_data.get("body_paragraphs", [])
    if not paragraphs:
        return []

    thresholds = DEFAULT_THRESHOLDS.copy()
    if rules and isinstance(rules, dict):
        custom_t = rules.get("thresholds", {})
        thresholds.update(custom_t)

    full_text = " ".join(paragraphs)
    all_sentences = []
    for p in paragraphs:
        all_sentences.extend(split_sentences(p))

    violations = []

    # 1. Sentence length variance & rhythm
    if len(all_sentences) >= 4:
        stats = compute_sentence_length_stats(all_sentences)
        std_dev = stats["std_dev"]
        span = stats["span"]

        if std_dev < thresholds["sentence_std_dev_min"]:
            violations.append(
                f"Monotonous sentence rhythm: sentence length standard deviation is {std_dev:.1f} words "
                f"(minimum required is {thresholds['sentence_std_dev_min']:.1f}). "
                f"Vary sentence pacing with short punchy statements (4-8 words) alongside complex compound explanations (22-35 words)."
            )

        if span < thresholds["sentence_span_min"]:
            violations.append(
                f"Narrow sentence length span: shortest sentence is {stats['min']} words and longest is {stats['max']} words "
                f"(span {span} < required minimum {thresholds['sentence_span_min']} words)."
            )

        if stats["max"] > thresholds["sentence_length_max"]:
            violations.append(
                f"Sentence length exceeds readability threshold: longest sentence has {stats['max']} words "
                f"(maximum allowed is {thresholds['sentence_length_max']} words)."
            )

    # 2. Lexical diversity
    ttr_data = compute_type_token_ratio(full_text)
    if ttr_data["total_tokens"] >= 100:
        if ttr_data["ttr"] < thresholds["type_token_ratio_min"]:
            violations.append(
                f"Low lexical diversity (Type-Token Ratio {ttr_data['ttr']:.2f} < required {thresholds['type_token_ratio_min']:.2f}). "
                f"Reduce repetitive words and vary vocabulary choices."
            )

    # 3. Consecutive sentence opener repetition
    opener_issues = detect_consecutive_opener_repetitions(
        all_sentences,
        max_consecutive=thresholds["max_consecutive_same_opener"],
    )
    for issue in opener_issues:
        violations.append(f"Repetitive sentence starters: {issue}. Vary grammatical structure and sentence openings.")

    return violations
```

- [ ] **Step 4: Run unit tests**

```bash
python -m unittest tests.test_voice_metrics -v
```

- [ ] **Step 5: Commit Task 1**

```bash
git add resume-engine/scoring/voice_rules.yaml scripts/voice_metrics.py tests/test_voice_metrics.py
git commit -m "feat(voice): implement voice metrics stylometry engine and rules (Group D, part 1/4)"
```

---

## Task 2: Update System Prompt `resume-engine/prompts/tailor_coverletter.md`

**Files:**
- Modify: `resume-engine/prompts/tailor_coverletter.md`

- [ ] **Step 1: Add sentence variance and authentic rhythm guidelines to prompt**

In `resume-engine/prompts/tailor_coverletter.md`, add explicit stylistic guidance under the writing principles section:
```markdown
- **Sentence length variance & rhythm**: Avoid monotonous, machine-like cadence where every sentence is 16-20 words. Mix short, punchy declarative statements (4-8 words) with nuanced, compound analytical sentences (22-35 words).
- **Varied sentence openers**: Never begin consecutive sentences with the same pronoun or verb structure (e.g. avoid repeating "I built...", "I led...", "I managed...").
```

- [ ] **Step 2: Verify prompt assembly tests pass**

```bash
python -m unittest tests.test_orchestrator_coverletter_enrichment -v
```

- [ ] **Step 3: Commit Task 2**

```bash
git add resume-engine/prompts/tailor_coverletter.md
git commit -m "feat(prompt): add sentence variance and rhythm rules to tailor_coverletter.md (Group D, part 2/4)"
```

---

## Task 3: Integration into `scripts/validate_coverletter.py`

**Files:**
- Modify: `scripts/validate_coverletter.py`
- Create: `tests/test_validate_coverletter_voice.py`

**Interfaces:**
- Update `validate_coverletter.validate()` signature to accept optional `voice_rules: dict = None`.
- Wire `_check_voice_metrics(cover_letter_data, voice_rules)` into `validate()`.

- [ ] **Step 1: Write integration tests in `tests/test_validate_coverletter_voice.py`**

```python
import os
import sys
import unittest

SCRIPTS_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts")
sys.path.insert(0, SCRIPTS_DIR)

import validate_coverletter  # noqa: E402


class TestValidateCoverletterVoice(unittest.TestCase):

    def setUp(self):
        self.style_rules = {"forbidden_phrases": []}
        self.voice_rules = {
            "thresholds": {
                "sentence_std_dev_min": 4.5,
                "sentence_span_min": 12,
                "type_token_ratio_min": 0.46,
                "max_consecutive_same_opener": 2,
            }
        }

    def test_validate_includes_voice_metrics_violations(self):
        # Monotonous repetitive body paragraphs
        letter_data = {
            "greeting": "Dear Hiring Team,",
            "body_paragraphs": [
                "The quick brown fox jumps over the very lazy sleeping dog today. "
                "Another quick brown fox jumps over another very lazy sleeping dog. "
                "A third quick brown fox jumps over that same lazy sleeping dog. "
                "Every single sentence has almost the exact same number of words.",
                "I managed the team yesterday. I managed the team today. I managed the team tomorrow.",
            ],
            "sign_off": "Sincerely,",
        }
        violations = validate_coverletter.validate(
            letter_data,
            self.style_rules,
            voice_rules=self.voice_rules,
        )
        self.assertTrue(any("monotonous" in v.lower() or "sentence starters" in v.lower() for v in violations))

    def test_validate_passes_on_high_variance_natural_prose(self):
        letter_data = {
            "greeting": "Dear Hiring Team,",
            "body_paragraphs": [
                "I love building systems that work quietly in the background — so people don’t have to. "
                "Over the past six years at Treering, I spearheaded our outbound communication engine, connecting with thousands of school coordinators and driving an unexpected 17% revenue surge through deeply personalized messaging. "
                "Clarity and empathy win every time.",
                "That loop of ideate, execute, and optimize is where I do my best work. "
                "Whether designing complex Salesforce workflows or crafting narrative email sequences, I focus on respecting the reader's time while earning their trust.",
            ],
            "sign_off": "Sincerely,",
        }
        violations = validate_coverletter.validate(
            letter_data,
            self.style_rules,
            voice_rules=self.voice_rules,
        )
        voice_violations = [v for v in violations if "monotonous" in v.lower() or "lexical" in v.lower() or "starters" in v.lower()]
        self.assertEqual(voice_violations, [])


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Modify `scripts/validate_coverletter.py`**

1. Add import:
```python
import voice_metrics
```

2. Add check function:
```python
def _check_voice_metrics(cover_letter_data: dict, voice_rules: dict | None = None) -> list[str]:
    return voice_metrics.analyze_voice_metrics(cover_letter_data, rules=voice_rules)
```

3. Update `validate()`:
```python
def validate(
    cover_letter_data: dict,
    style_rules: dict,
    kb_corpus: str = "",
    keeper_bullets: list[str] = None,
    keeper_embs = None,
    voice_rules: dict = None,
) -> list[str]:
    violations = []
    violations.extend(_check_forbidden_phrases(cover_letter_data, style_rules))
    violations.extend(_check_paragraph_count(cover_letter_data))
    violations.extend(_check_word_count(cover_letter_data))
    violations.extend(_check_third_person_slip(cover_letter_data))
    violations.extend(_check_kb_traceability(cover_letter_data, kb_corpus))
    violations.extend(_check_cliched_openers(cover_letter_data))
    violations.extend(_check_semantic_grounding(cover_letter_data, keeper_bullets, keeper_embs))
    violations.extend(_check_voice_metrics(cover_letter_data, voice_rules))
    return violations
```

- [ ] **Step 3: Run validation tests**

```bash
python -m unittest tests.test_validate_coverletter tests.test_validate_coverletter_voice -v
```

- [ ] **Step 4: Commit Task 3**

```bash
git add scripts/validate_coverletter.py tests/test_validate_coverletter_voice.py
git commit -m "feat(coverletter): integrate voice metrics into validate_coverletter.py (Group D, part 3/4)"
```

---

## Task 4: Integration into `scripts/orchestrator.py` & Full Verification

**Files:**
- Modify: `scripts/orchestrator.py`
- Create: `tests/test_orchestrator_coverletter_voice.py`
- Modify: `docs/superpowers/plans/2026-08-17-cover-letter-blueprint-roadmap.md`

- [ ] **Step 1: Write orchestrator integration test in `tests/test_orchestrator_coverletter_voice.py`**

```python
import os
import sys
import unittest
from unittest.mock import MagicMock, patch

SCRIPTS_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts")
sys.path.insert(0, SCRIPTS_DIR)

from orchestrator import ResumeEngine  # noqa: E402


class TestOrchestratorCoverletterVoice(unittest.TestCase):

    def setUp(self):
        self.engine = ResumeEngine()

    def test_voice_rules_loaded_in_engine_init(self):
        self.assertTrue(hasattr(self.engine, "voice_rules"))
        self.assertIsInstance(self.engine.voice_rules, dict)
        self.assertIn("thresholds", self.engine.voice_rules)

    @patch("gemini_client.GeminiClient.generate")
    @patch("validate_pdf_text.validate_coverletter_pdf_text", return_value=[])
    @patch("subprocess.run")
    def test_voice_violations_trigger_retry_with_issues_block(self, mock_subp, mock_val_pdf, mock_gen):
        mock_subp.return_value = MagicMock(returncode=0, stdout="ok", stderr="")

        # Return monotonous text on attempt 1, natural text on attempt 2
        bad_json = '{"company_name": "Acme", "greeting": "Dear Team,", "body_paragraphs": ["I worked at Acme Corp yesterday. I worked at Acme Corp today. I worked at Acme Corp tomorrow. I worked at Acme Corp forever."], "sign_off": "Sincerely,"}'
        good_json = '{"company_name": "Acme", "greeting": "Dear Team,", "body_paragraphs": ["I love building systems that work quietly in the background — so people don’t have to. Over the past six years at Treering, I spearheaded our outbound communication engine, connecting with thousands of school coordinators and driving an unexpected 17% revenue surge through deeply personalized messaging. Clarity and empathy win every time.", "That loop of ideate, execute, and optimize is where I thrive. Whether designing complex Salesforce workflows or crafting narrative email sequences, I focus on respecting the reader\'s time while earning their trust."], "sign_off": "Sincerely,"}'

        mock_gen.side_effect = [
            (bad_json, MagicMock(prompt_token_count=100, candidates_token_count=100)),
            (good_json, MagicMock(prompt_token_count=100, candidates_token_count=100)),
        ]

        # Use an existing test JD
        jd_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "jds", "morgan", "AcmeCorp_ContentStrategist.txt")
        if not os.path.exists(jd_path):
            self.skipTest("AcmeCorp JD fixture not present")

        result = self.engine.build_tailored_coverletter(jd_path)
        self.assertTrue(result)
        self.assertEqual(mock_gen.call_count, 2)
        retry_contents = mock_gen.call_args_list[1][1]["contents"]
        self.assertIn("=== ISSUES TO FIX", retry_contents)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Wire `voice_rules` into `scripts/orchestrator.py`**

1. In `ResumeEngine.__init__()`:
```python
self.voice_rules = self.load_yaml(self.scoring_dir, "voice_rules.yaml")
```

2. In `ResumeEngine.build_tailored_coverletter()`:
Pass `voice_rules=self.voice_rules` to both `validate_coverletter.validate()` calls (initial check and post-retry check).

- [ ] **Step 3: Run the full test suite**

```bash
python -m unittest discover -s tests -v
```

- [ ] **Step 4: Update `docs/superpowers/plans/2026-08-17-cover-letter-blueprint-roadmap.md`**

Mark Group D as complete and document test count.

- [ ] **Step 5: Commit Task 4**

```bash
git add scripts/orchestrator.py tests/test_orchestrator_coverletter_voice.py docs/superpowers/plans/2026-08-17-cover-letter-blueprint-roadmap.md
git commit -m "feat(orchestrator): wire voice rules into cover letter generation pipeline (Group D, part 4/4)"
```
