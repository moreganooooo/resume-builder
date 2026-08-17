# Voice Anchor Matcher Design

**Status**: Approved, ready for implementation planning
**Part of**: Group D, `docs/superpowers/plans/2026-08-17-cover-letter-blueprint-roadmap.md` (Feature #9)
**Author**: Antigravity & Claude (pair programming), aligned with Morgan 2026-08-17

---

## 1. Why

Feature #9 of the cover-letter blueprint addresses the **AI-detection & synthetic prose risk**: research indicates a **39% applicant rejection rate** when hiring managers or recruiters detect obvious, unedited AI generation.

While Group A (Feature #8) established a lexical blocklist for specific banned clichés ("delve", "testament to", "seamlessly"), lexical filtering alone cannot detect **structural and statistical AI tells**. Large Language Models frequently generate prose that contains zero banned words yet suffers from:
1. **Robotic Sentence Uniformity (Low Burstiness)**: LLM sentences cluster in a narrow length band (typically 16–22 words, $\sigma < 4.0$), lacking the dynamic burstiness of authentic human writing (which mixes 4–8 word punchy declarations with 25–35 word compound analytical explanations).
2. **Low Lexical Diversity (Low Type-Token Ratio)**: Synthetic prose overuses identical connective phrasing and repeated vocabulary within a 300–450 word letter.
3. **Repetitive Syntactic Openers**: LLMs frequently start consecutive sentences with identical part-of-speech patterns ("I developed...", "I led...", "I spearheaded...").
4. **Drift from Candidate Voice**: The prose sounds like generic enterprise marketing copy rather than Morgan's authentic, conversational, systems-and-human-first register captured in `voice-anchors.md` and `application-answers-index.csv`.

---

## 2. Scope

1. **Cover Letter Validation**: Pure-function stylometric & voice analysis evaluated in `scripts/validate_coverletter.py` after LLM generation in `orchestrator.py::build_tailored_coverletter()`.
2. **Deterministic Rules & Scoring Config**: Declarative metrics config in `resume-engine/scoring/voice_rules.yaml` defining actionable thresholds for variance, span, lexical diversity, and syntactic repetition.
3. **Actionable Remediation Feedback**: Detailed, specific violation descriptions passed into `orchestrator.py`'s single-retry loop so Gemini Flash Lite rewrites with varied cadence and richer vocabulary.
4. **Zero Impact on Resume Pipeline**: Resume bullets are audited through a separate rubric (`audit_bullet_bank.py` / `ai_risk.yaml`); Group D is strictly scoped to free-prose generation (cover letters, and future free-form application Q&As).

---

## 3. Architecture

Following the repository's established pure-module design:

```
                      ┌────────────────────────────────────────┐
                      │  resume-engine/scoring/voice_rules.yaml │
                      └──────────────────┬─────────────────────┘
                                         │ loads config
                                         ▼
┌───────────────────────┐      ┌─────────────────────┐
│  profiles/<profile>/  │      │                     │
│  knowledge_base/      ├─────►│ scripts/            │
│  voice-anchors.md     │      │ voice_metrics.py    │
└───────────────────────┘      │                     │
                               └─────────┬───────────┘
                                         │ imported by
                                         ▼
                               ┌─────────────────────┐
                               │ scripts/            │
                               │ validate_           │
                               │ coverletter.py      │
                               └─────────┬───────────┘
                                         │ called by
                                         ▼
                               ┌─────────────────────┐
                               │ scripts/            │
                               │ orchestrator.py     │
                               │ (Retry Loop)        │
                               └─────────────────────┘
```

### 3.1 New Module: `scripts/voice_metrics.py`
Pure computation engine with zero network/API side effects:
- `split_sentences(text: str) -> list[str]`: Punctuation- and abbreviation-aware sentence tokenizer (handles "e.g.", "i.e.", "Inc.", "vs.", numbers with decimals).
- `compute_sentence_length_stats(sentences: list[str]) -> dict`: Computes word counts per sentence, mean ($\mu$), sample standard deviation ($\sigma$), span ($\max - \min$), and coefficient of variation ($CV = \sigma / \mu$).
- `compute_type_token_ratio(text: str) -> float`: Computes Root Type-Token Ratio ($RTTR = \frac{|V|}{\sqrt{N}}$) and Standard TTR ($TTR = \frac{|V|}{N}$) after punctuation stripping and lowercasing.
- `detect_consecutive_opener_repetitions(sentences: list[str], max_consecutive: int = 2) -> list[str]`: Flags runs of 3+ sentences beginning with identical leading tokens/pronouns (e.g., three consecutive sentences starting with "I ").
- `analyze_voice_metrics(cover_letter_data: dict, rules: dict | None = None) -> list[str]`: High-level entry point returning list of human-readable violation strings.

### 3.2 Integration with `scripts/validate_coverletter.py`
- Add `_check_voice_metrics(cover_letter_data: dict, voice_rules: dict) -> list[str]` to `validate_coverletter.py`.
- Call `_check_voice_metrics` inside `validate_coverletter.validate()`.

### 3.3 Integration with `scripts/orchestrator.py`
- In `ResumeEngine.__init__()`, load `self.voice_rules = self.load_yaml(self.scoring_dir, "voice_rules.yaml")`.
- Pass `voice_rules` to `validate_coverletter.validate(..., voice_rules=self.voice_rules)`.
- If violations occur, the existing retry block formats them into `=== ISSUES TO FIX (change nothing else) ===` and calls Gemini with temperature 0.0 to fix sentence variety and pacing.

---

## 4. Stylometric Metrics & Thresholds

Based on empirical benchmarks from the research corpus (`docs/morgan_research/CoverLetterResearch/` and `docs/cover_letter_research_master_blueprint.md`):

| Metric | Target / Benchmark | Rejection Threshold | Rationale |
|---|---|---|---|
| **Sentence Length Std Dev ($\sigma$)** | $6.5 - 10.0$ words | $\sigma < 4.5$ words | Identifies robotic, monotonous cadence where all sentences are ~18 words. |
| **Sentence Length Span ($\Delta$)** | $\ge 15$ words | $\Delta < 12$ words | Ensures presence of both short punchy statements ($\le 10$ words) and complex compound thoughts ($\ge 22$ words). |
| **Max Sentence Length** | $\le 35$ words | $> 42$ words | Prevents sprawling, hard-to-parse run-on sentences. |
| **Min Sentence Length** | $4 - 8$ words | $< 3$ words | Flags accidental sentence fragment splits. |
| **Type-Token Ratio ($TTR$)** | $0.52 - 0.65$ | $TTR < 0.46$ | Detects excessive lexical repetition across the 300–450 word document. |
| **Consecutive Opener Repetition** | $\le 2$ same | $\ge 3$ consecutive | Flags repetitive "I [verb]" or "My [noun]" sentence starters. |

---

## 5. Candidate Voice Baseline Integration

Morgan's authentic voice is codified in:
1. `profiles/morgan/knowledge_base/voice-anchors.md` (curated verbatim quote specimens).
2. `profiles/morgan/knowledge_base/application-answers-index.csv` (15 real Q&A answers).
3. `profiles/morgan/knowledge_base/user-background-guide.md` (narrative principles).

### Key Stylistic Anchors:
- **Tone**: Conversational yet rigorous, empathetic, systems-oriented, craft-respecting.
- **Cadence**: Short punchy thesis sentence followed by concrete experiential elaboration (e.g., *"Journalism taught me to respect the reader’s time — marketing taught me to earn it."*).
- **Rhetorical Patterns**: Hyphenated compound descriptors, em-dash parentheticals, active verbs with clear ownership.

The system prompt in `resume-engine/prompts/tailor_coverletter.md` is updated to include explicit instruction on **sentence length variance** and **human rhythm**, ensuring the model produces high-variance prose on the first pass.

---

## 6. Error Handling & Retry Behavior

- **Deterministic & Non-Flaky**: Sentence tokenization and standard deviation math use standard library functions (`math`, `re`), guaranteeing 100% deterministic results across platforms.
- **Graceful Fallback**: If `voice_rules.yaml` is missing or unreadable, `voice_metrics.py` supplies safe internal default thresholds.
- **Single Retry Loop**: Violations trigger one targeted remediation pass. If violations remain after retry, `orchestrator.py` logs a normal warning and proceeds to PDF/DOCX rendering without crashing, matching the existing behavior for word count and grounding checks.

---

## 7. Testing Strategy

1. **Unit Tests (`tests/test_voice_metrics.py`)**:
   - `test_split_sentences_handles_abbreviations_and_decimals`: Tests "e.g.", "Ph.D.", "v1.2", "$4.5M", "St. Louis".
   - `test_uniform_ai_text_triggers_low_variance_violation`: Asserts monotonous text ($\sigma = 1.2$) triggers failure.
   - `test_dynamic_human_text_passes_variance_check`: Asserts authentic Morgan writing sample passes with $\sigma > 6.0$.
   - `test_type_token_ratio_flags_repetitive_text`: Asserts highly repetitive text fails TTR threshold.
   - `test_consecutive_opener_detection`: Asserts three consecutive "I am..." sentences are caught.
2. **Cover Letter Validator Integration (`tests/test_validate_coverletter_voice.py`)**:
   - Tests `validate()` runs voice checks when `voice_rules` is supplied.
3. **Orchestrator Integration (`tests/test_orchestrator_coverletter_voice.py`)**:
   - Asserts orchestrator passes voice rules into validator and includes voice issues in the retry prompt if detected.

---

## 8. Out of Scope

- External LLM-based "AI detector" API services (ZeroGPT, GPTZero, etc.) — these APIs are slow, expensive, non-deterministic, and prone to high false-positive rates on technical writing. Group D relies entirely on local, deterministic stylometry.
- Per-sentence embedding similarity (already built in `validate_coverletter._check_semantic_grounding`).
- Modifying resume bullet validation (already handled by `ai_risk.yaml` and `audit_bullet_bank.py`).
