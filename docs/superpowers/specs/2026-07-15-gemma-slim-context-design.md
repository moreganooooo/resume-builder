# Gemma Slim Context Design

## Problem

Google introduced a hard 16,000 TPM (tokens-per-minute) cap on Gemma models on
July 14, 2026 (previously unlimited). `scripts/rewrite_bullets.py` tries
`gemma-4-31b-it` first for every bullet rewrite, falling back to
`gemini-3.1-flash-lite` after repeated failures. But a real observed call
(bullet 1/628, non-Treering) used 18,321 prompt tokens — already over
Gemma's entire TPM budget in a *single call*, before any rate accumulation.
This means Gemma now 429s on nearly every bullet regardless of pacing, and
the existing retry/backoff ladder (fixed earlier this session so 429s
correctly accumulate toward the 2-consecutive-failure fallback threshold)
just burns ~31 seconds of guaranteed-to-fail waiting per bullet before
falling back to flash-lite — roughly 5+ hours of pure waste across a
628-bullet run, even though every bullet does eventually succeed.

## Goal

Give Gemma a genuinely slimmed system-instruction context, built specifically
to fit comfortably under 16k tokens, so it can actually succeed on most
bullets instead of being a near-permanent guaranteed-fail-then-fallback path.
Flash-lite (250k TPM, no real pressure) keeps the existing full-quality
context unchanged, so quality never degrades when Gemma can't be used.

## Non-goals

- Not touching `audit_keepers.py` or `score_keeper_gems.py` — both already
  migrated onto the shared `GeminiClient` this session and are out of scope
  here.
- Not changing the outer per-bullet rewrite-refinement loop (`MAX_ATTEMPTS`,
  `best_version()`, scoring/decide_action logic) — only which context tier
  and which model get used per attempt.
- Not adding automated tests for rewrite quality itself — same as the rest
  of this pipeline, quality is verified by reviewing real output from a live
  run, not unit tests.

## Component Breakdown

### Gemma's slim static tier (built once, parallel to today's `static_prefix`)

| Component | Included? | Rationale |
|---|---|---|
| `verified_facts.json` | Yes, in full | Guardrail — system prompt explicitly says "do NOT invent facts outside this list" |
| `verified_tools.json` | Yes, in full | Guardrail — "never claim proficiency with any tool not present in this list" |
| `voice-anchors.md` | Yes, in full | Small (~1,025 tokens), directly serves rewrite voice-matching quality |
| `profile.yml` | No — dropped | Strategic career-positioning content, not needed to rewrite a single existing bullet |

### Gemma's slim segment bundle (per `role_company`+`tags`, parallel to today's segment bundle)

| Component | Included? | Rationale |
|---|---|---|
| `cv.md` excerpt (per-role) | Yes, unchanged | Already small and role-scoped |
| `background_summary` | Yes, unchanged | Already small and tag-scoped |
| `verified_projects.json` | Yes, tag-filtered to `MAX_GEMMA_FILTER_ROWS` (new) | Concrete project facts a rewrite might reference; filtered instead of dropped or included whole |
| Treering: verified claims | Yes, tag-filtered to `MAX_GEMMA_FILTER_ROWS` (tighter than full tier's `MAX_CLAIMS_ROWS=12`) | Same guardrail, but Gemma's tier needs the tighter cap applied consistently across all filtered components, not just the new ones |
| Treering: `verified_metrics.json` | Yes, tag-filtered to `MAX_GEMMA_FILTER_ROWS` (new) | Guardrail (don't invent numbers) — filtered to stay small, not dropped |
| Treering: screenshot-metrics CSV | Yes, tag-filtered to `MAX_GEMMA_FILTER_ROWS` (new) | Same guardrail reasoning as verified_metrics |

### Flash-lite

Continues to use today's full `static_prefix` + full segment bundle,
completely unchanged. No new code path for flash-lite's context.

## Shared Tag-Filter Helper

`filter_claims_by_tags()` (existing, in `rewrite_bullets.py`) already filters
`df_claims` by matching a bullet's `tags` string against keyword lists in
`CLAIM_TAG_KEYWORDS`, falling back to `df_claims.head(MAX_CLAIMS_ROWS)` if
fewer than 3 rows match.

This gets generalized into one shared helper reusable across claims,
`verified_projects.json`, `verified_metrics.json`, and the screenshot-metrics
CSV — all four are keyword-matchable against the same `CLAIM_TAG_KEYWORDS`
mapping. The generalized helper takes a new, tighter row cap —
`MAX_GEMMA_FILTER_ROWS = 5` — used for all three of the new Gemma-tier
filters (projects, metrics, screenshots). Claims filtering for the *full*
context tier (used by flash-lite) keeps its existing `MAX_CLAIMS_ROWS = 12`
unchanged; only Gemma's tier uses the tighter cap.

`verified_metrics.json` entries have a `category`, `label`, and `context`
field to match against; the screenshot-metrics CSV has a `"Best Detail /
Notes"` text column plus campaign/batch descriptors. Both fit the same
match-then-cap approach already proven for claims.

## Model Handoff

**Problem this section solves:** `GeminiClient.generate()` currently falls
back from Gemma to flash-lite *internally*, mid-call, after 2 consecutive
429s — reusing whatever `system_instruction` the caller originally passed
in. Once Gemma gets its own slim context, an internal fallback would hand
flash-lite the *slim* context instead of the full one, which defeats the
whole point of keeping the two tiers separate.

**Fix:** Add a new parameter to `GeminiClient.generate()`:

```python
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

When `model_fallback=False`, the existing internal
`if failure_streak >= 2 and model in MODEL_FALLBACKS:` branches (both the
transport-exception one and the HTTP-status one) are skipped entirely — a
sustained failure just exhausts `max_retries` and returns `(None, {})` (or
raises `SustainedFailureError` once `SUSTAINED_FAILURE_THRESHOLD` is hit,
unchanged). Default `True` preserves current behavior for every other
caller (`orchestrator.py`, `audit_keepers.py`, `score_keeper_gems.py`, and
rewrite_bullets.py's own `score_bullet()` call) with zero changes needed at
those call sites.

`process_bullet()` in `rewrite_bullets.py` then manages the handoff
explicitly:

1. Build the bullet's prompt using the slim Gemma context, call
   `GeminiClient.generate(model="gemma-4-31b-it", ..., model_fallback=False)`.
2. If that returns `None`, build the prompt again using the full context and
   call `GeminiClient.generate(model="gemini-3.1-flash-lite", ...)` directly
   (default `model_fallback=True` is fine here — there's no third tier to
   protect).
3. `active_rewrite_model` (used for logging/output) is updated to reflect
   whichever model actually produced the result.

The existing `rewrite_parse_failures`-based fallback (switching
`active_rewrite_model` after `MAX_REWRITE_PARSE_FAILURES` consecutive parse
errors) and the outer `MAX_ATTEMPTS` refinement loop are unchanged — this
only changes which context tier and which model get used within a single
attempt.

## Testing

- **New shared tag-filter helper**: pure function (DataFrame/dict + tags
  string in, filtered subset out) — gets real unit tests covering keyword
  matching, the tighter row cap, and the "too few matches" fallback
  behavior.
- **`GeminiClient.generate(model_fallback=False)`**: extends
  `tests/test_gemini_client.py` (already mocks `requests.post` and
  `time.sleep`) with a test asserting no model swap occurs even after 2+
  consecutive 429s when the flag is `False`, and that existing
  `model_fallback=True` (default) behavior is unchanged.
- **Gemma slim static/segment tier builders**: lightweight tests confirming
  the right components are included/excluded (e.g. `profile.yml` absent,
  `verified_facts.json` present) without needing real API calls.
- **Rewrite quality with the slim context**: not unit-testable — verified by
  reviewing real rewrite output from a live run, consistent with how the
  rest of this pipeline is validated.
