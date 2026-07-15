# Rewrite/Audit/Gem-Scoring Pipeline Resilience — Design

## Problem

Three scripts in the bullet-bank rebuild pipeline — `rewrite_bullets.py`
(stage 3), `audit_keepers.py` (stage 4), `score_keeper_gems.py` (stage 5)
— each make real Gemini API calls per bullet and are vulnerable to the
same class of issue `cluster_bullet_bank.py` (stage 2) had before an
earlier fix this session, in three different flavors:

- `GeminiClient.generate()` (`scripts/gemini_client.py`) — the shared
  low-level function `rewrite_bullets.py`/`audit_keepers.py` use, and
  which `orchestrator.py` also uses for everyday per-JD resume builds —
  already retries 429/500/502/503/504 with exponential backoff (up to 6
  attempts) and falls back to an alternate model after 2 consecutive
  failures. But once *all* retries and the model fallback are exhausted,
  it returns `(None, {})` quietly, with no distinction between "that was
  a transient blip" and "we're out of quota for the day." The calling
  code in `rewrite_bullets.py` treats a `None` result the same as a
  legitimately weak bullet (forces `manager_test=FAIL`), sending it
  through more rewrite attempts that *each* burn through the same 6
  retries — so a real quota exhaustion causes the script to flail for a
  very long time (potentially many minutes per bullet, repeated across
  every remaining bullet) rather than stopping cleanly, mislabeling
  every affected bullet `MANUAL` in the process (implying a
  content-quality failure, not a quota issue).
- `audit_keepers.py`'s Stage 1 scoring loop only writes
  `bullet-bank-keepers-audited.csv` once, after the entire loop
  completes — an interruption partway through loses all progress in
  that stage, needing a full re-score from scratch.
- `score_keeper_gems.py` has neither retry/backoff (its own local
  `score_bullet()` uses a different client library, `google.genai`,
  with a bare `except Exception: return None`) nor incremental output
  writes (also all-or-nothing at the end of its loop).

`rewrite_bullets.py` itself already has real incremental resumability
(flushes to CSV every 5 bullets, skips already-done bullets on restart)
— it does not need a resumability fix, only the sustained-failure
detection.

## Goals

1. `GeminiClient.generate()` detects a sustained (not transient) failure
   — two consecutive calls that each exhaust all retries and the model
   fallback — and raises a distinct, actionable exception instead of
   quietly returning `(None, {})` a third time. Single source of truth:
   this also protects `orchestrator.py`'s everyday per-JD resume-building
   calls, not just the bullet-bank scripts, with no duplicated detection
   logic across three call sites.
2. `rewrite_bullets.py`'s one try/except around a `GeminiClient.generate()`
   call is fixed to not swallow this new exception as if it were an
   ordinary parse failure.
3. `audit_keepers.py`'s Stage 1 gains incremental CSV flushing (every 5
   rows, matching `rewrite_bullets.py`'s own convention) and
   automatically skips any bullet that `bullet-bank-keepers-audited.csv`
   already has a real score for — independent of the existing
   `--from-audited` flag, which keeps its own separate meaning.
4. `score_keeper_gems.py` migrates its scoring call onto the shared
   `GeminiClient.generate()` (inheriting retry/backoff/model-fallback/
   sustained-failure detection for free, instead of a fourth duplicate
   implementation) and gains incremental output flushing every 5 rows.

## Non-Goals

- No changes to `cluster_bullet_bank.py`, `embed_bullet_bank.py`, or
  `bullet_bank_menu.py` — this design is scoped to stages 3-5 only. In
  particular, nothing here touches any file `cluster_bullet_bank.py`
  reads or writes, so the user's in-progress live run of that stage is
  completely unaffected.
- No change to `--from-audited`'s existing behavior (trusting CLEAN
  rows, skipping cluster-map Source B in Stage 3) — the new
  unconditional "skip already-scored" check in Goal 3 is a distinct,
  lower-level behavior that applies regardless of the flag.
- No change to `rewrite_bullets.py`'s existing resumability (CSV flush
  cadence, `load_already_processed()`) — already correct.
- No change to the retry counts, backoff timing, or model-fallback
  mapping already in `GeminiClient.generate()` — only the *new*
  sustained-failure layer on top of exhaustion.
- No automatic API-key rotation — swapping `GEMINI_API_KEY` on a
  sustained-failure abort stays a manual step, consistent with the
  cluster-script fix earlier this session.

## Architecture

### 1. `gemini_client.py` — `SustainedFailureError` + consecutive-failure counter

```python
class SustainedFailureError(RuntimeError):
    """Raised when GeminiClient.generate() has exhausted retries and the
    model fallback on SUSTAINED_FAILURE_THRESHOLD consecutive calls --
    a signal this is a quota-level issue, not a transient blip."""


class GeminiClient:
    _timeout = 90
    _consecutive_full_failures = 0
    SUSTAINED_FAILURE_THRESHOLD = 2

    @staticmethod
    def generate(...):
        ...
        for attempt in range(max_retries):
            ...  # existing retry loop body, unchanged
            # (on success, before `return text, usage`:)
            GeminiClient._consecutive_full_failures = 0
            return text, usage

        # Reached only after exhausting max_retries without success
        GeminiClient._consecutive_full_failures += 1
        if GeminiClient._consecutive_full_failures >= GeminiClient.SUSTAINED_FAILURE_THRESHOLD:
            failures = GeminiClient._consecutive_full_failures
            GeminiClient._consecutive_full_failures = 0  # reset for any caller that recovers
            raise SustainedFailureError(
                f"GeminiClient.generate() exhausted retries on {failures} consecutive "
                f"calls (model={model}) -- this looks like a sustained quota issue, not "
                "a transient blip. Swap GEMINI_API_KEY/GOOGLE_API_KEY in .env and re-run."
            )
        return None, {}
```

The counter is a class attribute, not instance state — shared across
every call within one script's process, and naturally reset to 0 every
time a *new* pipeline-stage script starts (each stage runs as its own
subprocess), which is exactly the right granularity: no cross-run
persistence needed, no risk of a stale counter from a previous
invocation.

Threshold of 2: each exhausted call already spent real time in its own
6-attempt backoff (up to ~5 minutes worst case), so 2 consecutive full
exhaustions is a conservative but not excessive signal — roughly 10
minutes of genuine, escalating retry effort before concluding this
isn't transient.

### 2. `rewrite_bullets.py` — don't swallow `SustainedFailureError`

`process_bullet()`'s rewrite-generate call is the *only* call site in
these three scripts that wraps a `GeminiClient.generate()` call in a
broad `except Exception`. It needs a guard clause before that catch:

```python
try:
    raw, usage = GeminiClient.generate(...)
    ...
except SustainedFailureError:
    raise
except Exception as e:
    rewrite_parse_failures += 1
    ...
```

Every other call site (`score_bullet()` in both `rewrite_bullets.py` and
`audit_keepers.py`'s Stage 1 loop) has no surrounding try/except at all,
so `SustainedFailureError` already propagates naturally there, straight
through `main()`, producing a non-zero exit — which `bullet_bank_menu.py`
already handles correctly via `cli_art.display_error(...)`. No menu
changes needed.

### 3. `audit_keepers.py` — Stage 1 incremental flush + unconditional skip

`stage1_audit_keepers()` gains a flush counter (mirroring
`rewrite_bullets.py`'s `CSV_FLUSH_EVERY`) that writes
`bullet-bank-keepers-audited.csv` every 5 scored rows, not just once
after the whole loop.

Separately, before computing `needs_score_mask`, a new step merges in
any row from an existing `bullet-bank-keepers-audited.csv` that already
has a non-blank `audit_status` — matched by bullet text — and marks it
as already-done, **regardless of whether `--from-audited` was passed**.
This is what actually makes an interrupted run resume correctly:
`--from-audited` keeps its existing, separate meaning (trust CLEAN rows
without rescoring them, skip Stage 3's cluster-map Source B entirely);
this new check is a lower-level "don't redo work already paid for," and
applies unconditionally on every run.

### 4. `score_keeper_gems.py` — migrate to `GeminiClient` + incremental flush

Drop the `google.genai`/`types` imports and the `client = genai.Client(...)`
setup. `score_bullet()` simplifies to:

```python
def score_bullet(system_prompt: str, bullet: str) -> dict | None:
    raw, _usage = GeminiClient.generate(
        model=MODEL,
        system_instruction=system_prompt,
        contents=bullet,
        response_schema=HiddenGemSchema,
        temperature=0.0,
    )
    if raw is None:
        return None
    return GeminiClient.parse_json(raw)
```

No try/except needed around it — `GeminiClient.generate()` already
handles ordinary failures internally, and `SustainedFailureError` should
propagate naturally.

The main loop gains an incremental flush (every 5 rows) writing
`args.output`. Since `args.input`/`args.output` already default to the
*same* file, and the existing skip-logic (`if not row.get("hidden_gem_score")`)
already reads fresh from that file on every run, no additional
"detect prior progress" logic is needed here beyond the flush itself —
unlike `audit_keepers.py`'s case, where input and output are different
files.

## Data Flow

```
GeminiClient.generate() called from:
  rewrite_bullets.py:  process_bullet() [rewrite call, try/except guarded]
                       score_bullet()   [no guard needed, propagates naturally]
  audit_keepers.py:    stage1_audit_keepers() -> score_bullet() [imported, no guard needed]
                       stage4_auto_rewrite()  -> process_bullet() [imported, already guarded]
  score_keeper_gems.py: score_bullet() [new, no guard needed]

  -> 2 consecutive full exhaustions (any model, any of the above call sites,
     within one script's process) -> SustainedFailureError raised
  -> propagates through main() uncaught -> non-zero exit
  -> bullet_bank_menu._handle_choice() already displays this via cli_art.display_error()
```

## Error Handling

- A single exhausted call (not yet at threshold): unchanged from today
  — returns `(None, {})`, caller treats it as a scoring/rewrite failure
  for that one call, per existing logic.
- Two consecutive exhausted calls: `SustainedFailureError` raised,
  counter reset to 0 (so if the script is re-run and recovers, it isn't
  pre-loaded with a stale near-threshold count — moot in practice since
  each script run is a fresh process, but keeps the class attribute
  correct if any single process ever called `generate()` again after
  catching this, e.g. in a test).
- `audit_keepers.py` Stage 1 interrupted mid-flush: the last full
  5-row batch before the interruption is on disk; the partial batch
  since then is lost (same acceptable granularity as
  `rewrite_bullets.py`'s existing `CSV_FLUSH_EVERY` behavior) — a
  re-run picks up from the last flushed row via the new unconditional
  skip check.
- `score_keeper_gems.py` interrupted mid-flush: same 5-row granularity
  and same resume behavior via its existing skip-logic once the flush
  is in place.

## Testing

- None of `rewrite_bullets.py`, `audit_keepers.py`, or
  `score_keeper_gems.py` have dedicated test files today (consistent
  with every other standalone bullet-bank pipeline script — verified
  live, not unit tested). This design follows that same convention for
  those three files.
- `gemini_client.py` already has `tests/test_gemini_client.py` (mocks
  `gemini_client.requests.post`/`gemini_client.time.sleep`, covers the
  existing model-fallback behavior). `SustainedFailureError` is new,
  class-level, shared state with real behavioral consequences (an
  uncaught exception that changes a script's exit code), so it gets new
  test classes added to that same file, following its existing
  mocking conventions: a mocked `requests.post` returning 429 on every
  call verifies `generate()` returns `(None, {})` on the first
  exhaustion and raises `SustainedFailureError` on the second
  consecutive exhaustion; a successful call between two exhaustions
  resets the counter so a third exhaustion afterward does *not*
  immediately raise (needs its own two in a row).
- Live verification: since these are real, billed API scripts, live
  end-to-end verification (deliberately triggering an actual sustained
  429) is impractical to force on demand. Verification here is the
  above unit test (which exercises the exact code path relied upon) plus
  a live run of each script's normal (successful) path to confirm the
  incremental-flush and skip-logic changes don't alter behavior on the
  happy path — no bullet double-scored, no output format change.
