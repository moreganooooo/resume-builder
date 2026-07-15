# Rewrite/Audit/Gem-Scoring Pipeline Resilience Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Detect sustained (quota-level) Gemini API failures once, in the
shared `GeminiClient.generate()`, and stop cleanly instead of flailing
for a long time; add incremental checkpointing to the two bullet-bank
stages (`audit_keepers.py`, `score_keeper_gems.py`) that currently only
write output once, all-or-nothing, at the end of their scoring loops.

**Architecture:** A new `SustainedFailureError` plus a class-level
consecutive-failure counter live in `gemini_client.py`, raised only after
2 consecutive calls each exhaust all retries and the model fallback.
`rewrite_bullets.py` gets a guard clause so its one broad
`except Exception` doesn't swallow this new exception.
`audit_keepers.py`'s Stage 1 and `score_keeper_gems.py`'s main loop each
gain incremental CSV flushing; `score_keeper_gems.py` additionally
migrates its scoring call onto the shared `GeminiClient` instead of a
separate client library, inheriting retry/backoff/sustained-failure
detection for free.

**Tech Stack:** Python 3.10+, `requests` (already used by
`gemini_client.py`), `pandas`, stdlib `csv`/`unittest`.

## Global Constraints

- No changes to `cluster_bullet_bank.py`, `embed_bullet_bank.py`, or
  `bullet_bank_menu.py` — the user has a live `cluster_bullet_bank.py`
  run in progress that must not be disrupted, and this work is scoped to
  stages 3-5 only.
- No change to `--from-audited`'s existing behavior in `audit_keepers.py`
  (trusting CLEAN rows, skipping Stage 3's cluster-map Source B) — the
  new unconditional "skip already-scored" check is additive and
  independent of that flag.
- No change to `rewrite_bullets.py`'s existing resumability (`CSV_FLUSH_EVERY`,
  `load_already_processed()`) — already correct, not touched.
- No change to `GeminiClient.generate()`'s existing retry count, backoff
  timing, or model-fallback mapping — only the new sustained-failure
  layer added on top of exhaustion.
- `rewrite_bullets.py`, `audit_keepers.py`, and `score_keeper_gems.py`
  have no dedicated test files and aren't part of this repo's automated
  suite (consistent with every other standalone bullet-bank pipeline
  script) — Tasks 2-4 get no new tests, only live verification.
  `gemini_client.py` already has `tests/test_gemini_client.py` — Task 1
  extends it.
- Run `python -m unittest discover -s tests` after Task 1 and confirm
  the full suite passes.

---

## File Structure

| File | Responsibility |
|---|---|
| `scripts/gemini_client.py` (modified) | New `SustainedFailureError`, `GeminiClient._consecutive_full_failures`/`SUSTAINED_FAILURE_THRESHOLD`, sustained-failure check on retry exhaustion. |
| `tests/test_gemini_client.py` (modified) | Covers the new sustained-failure behavior. |
| `scripts/rewrite_bullets.py` (modified) | `process_bullet()`'s try/except gains a `SustainedFailureError` guard clause. |
| `scripts/audit_keepers.py` (modified) | New `_merge_prior_audited_progress()` helper + `AUDIT_FLUSH_EVERY` incremental flush in `stage1_audit_keepers()`. |
| `scripts/score_keeper_gems.py` (modified) | `score_bullet()` migrated onto `GeminiClient.generate()`; new `_write_scored_csv()` helper + `GEM_FLUSH_EVERY` incremental flush in `main()`. |

---

### Task 1: `gemini_client.py` — `SustainedFailureError` + consecutive-failure counter

**Files:**
- Modify: `scripts/gemini_client.py` (add exception class + class attributes, modify the end of `generate()`)
- Test: `tests/test_gemini_client.py`

**Interfaces:**
- Produces: `gemini_client.SustainedFailureError(RuntimeError)`,
  `GeminiClient._consecutive_full_failures: int` (class attribute, starts
  at 0), `GeminiClient.SUSTAINED_FAILURE_THRESHOLD: int` (= 2).
  `GeminiClient.generate(...)`'s return type is unchanged
  (`tuple[str | None, dict]`) for anything below the threshold; raises
  `SustainedFailureError` once the threshold is reached.

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_gemini_client.py -- add this class

class TestSustainedFailureDetection(unittest.TestCase):

    def setUp(self):
        # Class-level counter persists across tests in the same process --
        # reset before and after every test in this class for isolation.
        GeminiClient._consecutive_full_failures = 0

    def tearDown(self):
        GeminiClient._consecutive_full_failures = 0

    def _rate_limited_response(self):
        resp = MagicMock()
        resp.status_code = 429
        return resp

    @patch("gemini_client.time.sleep", lambda *a, **kw: None)
    @patch("gemini_client.requests.post")
    def test_first_full_exhaustion_returns_none_without_raising(self, mock_post):
        mock_post.return_value = self._rate_limited_response()
        text, usage = GeminiClient.generate(
            model="gemini-3.1-flash-lite",
            system_instruction="sys",
            contents="do the thing",
            max_retries=2,
        )
        self.assertIsNone(text)
        self.assertEqual(usage, {})
        self.assertEqual(GeminiClient._consecutive_full_failures, 1)

    @patch("gemini_client.time.sleep", lambda *a, **kw: None)
    @patch("gemini_client.requests.post")
    def test_second_consecutive_full_exhaustion_raises(self, mock_post):
        mock_post.return_value = self._rate_limited_response()

        GeminiClient.generate(
            model="gemini-3.1-flash-lite", system_instruction="sys",
            contents="do the thing", max_retries=2,
        )
        with self.assertRaises(SustainedFailureError):
            GeminiClient.generate(
                model="gemini-3.1-flash-lite", system_instruction="sys",
                contents="do the thing", max_retries=2,
            )

    @patch("gemini_client.time.sleep", lambda *a, **kw: None)
    @patch("gemini_client.requests.post")
    def test_success_between_exhaustions_resets_the_counter(self, mock_post):
        mock_post.side_effect = [
            self._rate_limited_response(), self._rate_limited_response(),  # exhaustion 1 (max_retries=2)
            _success_response(),                                          # success -- resets counter
            self._rate_limited_response(), self._rate_limited_response(),  # exhaustion again -- only #1 now
        ]
        GeminiClient.generate(
            model="gemini-3.1-flash-lite", system_instruction="sys",
            contents="do the thing", max_retries=2,
        )
        GeminiClient.generate(
            model="gemini-3.1-flash-lite", system_instruction="sys",
            contents="do the thing", max_retries=2,
        )
        text, usage = GeminiClient.generate(
            model="gemini-3.1-flash-lite", system_instruction="sys",
            contents="do the thing", max_retries=2,
        )
        self.assertIsNone(text)
        self.assertEqual(GeminiClient._consecutive_full_failures, 1)
```

Also update the import line at the top of the file:

```python
from gemini_client import GeminiClient, MODEL_FALLBACKS, SustainedFailureError  # noqa: E402
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /Users/morganescott/resume-builder && source .venv/bin/activate && python -m unittest tests.test_gemini_client -v`
Expected: `ImportError: cannot import name 'SustainedFailureError' from 'gemini_client'`

- [ ] **Step 3: Implement**

Add the exception class in `scripts/gemini_client.py`, just before
`class GeminiClient:`:

```python
class SustainedFailureError(RuntimeError):
    """Raised when GeminiClient.generate() has exhausted retries and the
    model fallback on SUSTAINED_FAILURE_THRESHOLD consecutive calls --
    a signal this is a quota-level issue, not a transient blip."""
```

Add the two class attributes, right after `_timeout = 90`:

```python
class GeminiClient:

    _timeout = 90
    _consecutive_full_failures = 0
    SUSTAINED_FAILURE_THRESHOLD = 2
```

At the success-return point inside the retry loop (the line immediately
before `return text, usage`), reset the counter:

```python
            text = "".join(p.get("text", "") for p in parts if not p.get("thought"))
            failure_streak = 0
            GeminiClient._consecutive_full_failures = 0
            return text, usage

        return None, {}
```

Replace that final `return None, {}` (reached only when the `for attempt
in range(max_retries):` loop completes every iteration without a
`return`) with:

```python
        GeminiClient._consecutive_full_failures += 1
        if GeminiClient._consecutive_full_failures >= GeminiClient.SUSTAINED_FAILURE_THRESHOLD:
            failures = GeminiClient._consecutive_full_failures
            GeminiClient._consecutive_full_failures = 0
            raise SustainedFailureError(
                f"GeminiClient.generate() exhausted retries on {failures} consecutive "
                f"calls (model={model}) -- this looks like a sustained quota issue, not "
                "a transient blip. Swap GEMINI_API_KEY/GOOGLE_API_KEY in .env and re-run."
            )
        return None, {}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m unittest tests.test_gemini_client -v`
Expected: all PASS (5 tests — 2 existing + 3 new)

Then: `python -m unittest discover -s tests`
Expected: all PASS

- [ ] **Step 5: Commit**

```bash
git add scripts/gemini_client.py tests/test_gemini_client.py
git commit -m "$(cat <<'EOF'
Add SustainedFailureError to GeminiClient.generate()

Two consecutive calls that each exhaust all retries and the model
fallback now raise a distinct, actionable exception instead of quietly
returning (None, {}) a third time. Single source of truth -- also
protects orchestrator.py's everyday per-JD resume-building calls, not
just the bullet-bank pipeline scripts.
EOF
)"
```

---

### Task 2: `rewrite_bullets.py` — don't swallow `SustainedFailureError`

**Files:**
- Modify: `scripts/rewrite_bullets.py` (import line, `process_bullet()`'s try/except)

**Interfaces:**
- Consumes: `gemini_client.SustainedFailureError` (Task 1).

- [ ] **Step 1: N/A — no new failing test for this task**

`rewrite_bullets.py` has no dedicated test file and isn't part of this
repo's automated suite (see Global Constraints). Proceed directly to
implementation; this task is verified live in Step 4.

- [ ] **Step 2: N/A**

- [ ] **Step 3: Implement**

Update the import line (`scripts/rewrite_bullets.py:112`):

```python
from gemini_client import GeminiClient, SustainedFailureError  # noqa: E402
```

In `process_bullet()`, add a guard clause before the existing broad
`except Exception`:

```python
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

- [ ] **Step 4: Live verification**

Run: `source .venv/bin/activate && python -c "
import sys; sys.path.insert(0, 'scripts')
import rewrite_bullets
print('imports cleanly, SustainedFailureError available:', rewrite_bullets.SustainedFailureError)
"`
Expected: prints the exception class with no import errors.

Then run the full test suite once to confirm this script's import
changes haven't broken anything it's referenced from:
Run: `python -m unittest discover -s tests`
Expected: all PASS (this script itself has no dedicated tests, but
`tests/test_bootstrap_bullet_bank_pipeline.py` references its filename
as a mocked subprocess string — confirm that's unaffected).

- [ ] **Step 5: Commit**

```bash
git add scripts/rewrite_bullets.py
git commit -m "$(cat <<'EOF'
Don't swallow SustainedFailureError in rewrite_bullets.py

process_bullet()'s one broad except Exception (around the rewrite-
generate call) would otherwise treat a sustained quota failure the same
as an ordinary parse error and keep retrying instead of stopping.
EOF
)"
```

---

### Task 3: `audit_keepers.py` — Stage 1 incremental flush + unconditional skip

**Files:**
- Modify: `scripts/audit_keepers.py` (new constant + helper, `stage1_audit_keepers()`)

**Interfaces:**
- Produces: `audit_keepers._merge_prior_audited_progress(df_keepers: pd.DataFrame) -> pd.DataFrame`,
  `audit_keepers.AUDIT_FLUSH_EVERY: int` (= 5).

- [ ] **Step 1: N/A — no new failing test for this task**

`audit_keepers.py` has no dedicated test file (see Global Constraints).
Proceed directly to implementation; verified live in Step 4.

- [ ] **Step 2: N/A**

- [ ] **Step 3: Implement**

Add the constant near the other module-level constants in
`scripts/audit_keepers.py` (after `REWRITE_QUEUE_OUT`):

```python
AUDIT_FLUSH_EVERY = 5
```

Add the new helper, just before `stage1_audit_keepers()`:

```python
def _merge_prior_audited_progress(df_keepers: pd.DataFrame) -> pd.DataFrame:
    """Merges in audit_status/scores from an existing keepers-audited.csv
    for any bullet that's already been scored there -- independent of
    --from-audited, which has its own separate meaning (trust CLEAN rows,
    skip cluster-map Source B). This is what makes an interrupted Stage 1
    run resume correctly without needing to remember a flag."""
    if not os.path.exists(KEEPERS_AUDITED):
        return df_keepers

    try:
        df_prior = pd.read_csv(KEEPERS_AUDITED)
    except Exception:
        return df_keepers

    if "Bullet Point" not in df_prior.columns or "audit_status" not in df_prior.columns:
        return df_keepers

    prior_scored = df_prior[df_prior["audit_status"].astype(str).str.strip() != ""]
    if prior_scored.empty:
        return df_keepers

    prior_scored = prior_scored.drop_duplicates(subset="Bullet Point", keep="first")
    prior_lookup = prior_scored.set_index(prior_scored["Bullet Point"].astype(str).str.strip())

    merge_cols = [c for c in (["audit_status"] + SCORE_COLS + ["weaknesses"]) if c in prior_lookup.columns]

    restored = 0
    for idx, row in df_keepers.iterrows():
        bp = str(row.get("Bullet Point", "")).strip()
        if bp in prior_lookup.index and str(row.get("audit_status", "")).strip() == "":
            prior_row = prior_lookup.loc[bp]
            for col in merge_cols:
                df_keepers.loc[idx, col] = prior_row[col]
            restored += 1

    if restored:
        print(f"   ♻️  Restored {restored} already-scored row(s) from a prior keepers-audited.csv run.")

    return df_keepers
```

In `stage1_audit_keepers()`, call the new helper right after the
`audit_status` column is ensured:

```python
    if "audit_status" not in df_keepers.columns:
        df_keepers["audit_status"] = ""

    df_keepers = _merge_prior_audited_progress(df_keepers)

    if from_audited:
```

Add the incremental flush inside the scoring loop (the `else:` branch
that calls `score_bullet()` per row):

```python
        total = len(to_score)
        bullets_since_flush = 0
        for i, (idx, row) in enumerate(to_score.iterrows(), 1):
            bullet = str(row.get("Bullet Point", "")).strip()
            tags   = str(row.get("Tags", ""))
            print(f"\n   [{i}/{total}] Scoring: {bullet[:70]}...")

            scores = score_bullet(bullet, tags, score_system, dry_run=dry_run)

            for col in SCORE_COLS:
                if col in NUMERIC_SCORE_COLS:
                    df_keepers.loc[idx, col] = pd.to_numeric(scores.get(col, None), errors="coerce")
                else:
                    df_keepers.loc[idx, col] = _safe_str(scores.get(col, ""))
            df_keepers.loc[idx, "weaknesses"] = _safe_str(scores.get("weaknesses", ""))
            df_keepers.loc[idx, "audit_status"] = _audit_status(df_keepers.loc[idx])

            status = df_keepers.loc[idx, "audit_status"]
            mgr    = str(scores.get("manager_test", "")).upper()
            print(
                f"   → status={status}  mgr={mgr}  "
                f"acc={scores.get('accuracy_score')}  "
                f"bel={scores.get('believability_score')}  "
                f"cla={scores.get('clarity_score')}  "
                f"ats={scores.get('ats_value')}"
            )

            bullets_since_flush += 1
            is_last = (i == total)
            if bullets_since_flush >= AUDIT_FLUSH_EVERY or is_last:
                df_keepers.to_csv(KEEPERS_AUDITED, index=False)
                bullets_since_flush = 0
                print(f"   💾 Flushed audited keepers ({i}/{total} scored so far).")

            if i < total:
                time.sleep(SLEEP_BETWEEN_BULLETS)
```

(This replaces the original loop body — same logic, with the new
`bullets_since_flush`/flush block added right after the existing
per-row print, before the existing `if i < total: time.sleep(...)`.)

- [ ] **Step 4: Live verification**

Run: `source .venv/bin/activate && python -c "
import sys; sys.path.insert(0, 'scripts')
import audit_keepers
print('AUDIT_FLUSH_EVERY:', audit_keepers.AUDIT_FLUSH_EVERY)
print('_merge_prior_audited_progress exists:', hasattr(audit_keepers, '_merge_prior_audited_progress'))
"`
Expected: prints `5` and `True`, no import errors.

Then: `python -m unittest discover -s tests`
Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add scripts/audit_keepers.py
git commit -m "$(cat <<'EOF'
Add incremental flush + unconditional resume to audit_keepers.py Stage 1

Stage 1 previously only wrote bullet-bank-keepers-audited.csv once,
after its entire scoring loop completed -- an interruption partway
through lost all progress in that stage. Now flushes every 5 rows, and
_merge_prior_audited_progress() restores already-scored rows from a
prior (even partial) run on every invocation, independent of
--from-audited (which keeps its own separate meaning).
EOF
)"
```

---

### Task 4: `score_keeper_gems.py` — migrate to `GeminiClient` + incremental flush

**Files:**
- Modify: `scripts/score_keeper_gems.py` (imports, `score_bullet()`, `main()`)

**Interfaces:**
- Produces: `score_keeper_gems.score_bullet(system_prompt: str, bullet: str)
  -> dict | None` (signature change — was
  `score_bullet(client, system_prompt, bullet)`),
  `score_keeper_gems._write_scored_csv(path: str, rows: list, final_headers: list) -> None`,
  `score_keeper_gems.GEM_FLUSH_EVERY: int` (= 5).

- [ ] **Step 1: N/A — no new failing test for this task**

`score_keeper_gems.py` has no dedicated test file (see Global
Constraints). Proceed directly to implementation; verified live in
Step 4.

- [ ] **Step 2: N/A**

- [ ] **Step 3: Implement**

Replace the imports block (`scripts/score_keeper_gems.py:21-30`):

```python
import argparse
import csv
import json
import os
import sys
import time
from pathlib import Path

from dotenv import load_dotenv
from pydantic import BaseModel, Field
```

(`from google import genai` is removed — no longer needed.)

Add the shared-client import right after `load_dotenv(PROJECT_ROOT / ".env")`:

```python
SCRIPT_DIR   = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parent
KB_DIR       = PROJECT_ROOT / "resume-engine" / "knowledge_base"
SCORING_DIR  = PROJECT_ROOT / "resume-engine" / "scoring"

load_dotenv(PROJECT_ROOT / ".env")

if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from gemini_client import GeminiClient  # noqa: E402
```

Add the flush constant near `SLEEP_SECONDS`/`MODEL`:

```python
GEM_THRESHOLD  = 90    # hidden_gem_score >= 90 → hidden_gem_flag = True
SLEEP_SECONDS  = 4     # politeness delay between API calls
GEM_FLUSH_EVERY = 5    # flush scored CSV to disk every N bullets
MODEL          = "gemma-4-31b-it"   # Gemma 4 31B — best free-tier allotment
```

Replace `score_bullet()`:

```python
def score_bullet(system_prompt: str, bullet: str) -> dict | None:
    """Score a single bullet. Returns a dict or None on failure. Uses the
    shared GeminiClient (gemini_client.py) instead of a separate client
    library -- inherits its retry/backoff/model-fallback/sustained-
    failure detection for free. SustainedFailureError is intentionally
    not caught here -- it should propagate straight up."""
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

Add a small helper, right after `score_bullet()`:

```python
def _write_scored_csv(path: str, rows: list, final_headers: list) -> None:
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=final_headers, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)
```

In `main()`, remove the client-init block:

```python
    system_prompt = build_system_prompt()
```

(Deletes the `api_key = os.environ.get(...)` and `client = genai.Client(...)`
lines that used to precede `system_prompt = build_system_prompt()`.)

Move the header-building block to *before* the scoring loop (originally
it was built after), and restructure the loop to flush incrementally:

```python
    # Build final header (add new cols if not present) -- computed before
    # the loop so the incremental flush below can use the same headers.
    new_cols = ["hidden_gem_score", "hidden_gem_flag", "hidden_gem_reason"]
    final_headers = list(headers) + [c for c in new_cols if c not in headers]

    gem_count    = 0
    strong_count = 0
    error_count  = 0
    scored_since_flush = 0

    for n, i in enumerate(to_score_idx, start=1):
        bullet = rows[i].get(bullet_col, "").strip()
        if not bullet:
            rows[i]["hidden_gem_score"]  = ""
            rows[i]["hidden_gem_flag"]   = ""
            rows[i]["hidden_gem_reason"] = ""
            continue

        print(f"  [{n}/{len(to_score_idx)}] Scoring: {bullet[:80]}...")

        if n > 1:
            time.sleep(SLEEP_SECONDS)

        result = score_bullet(system_prompt, bullet)
        if result:
            score  = result.get("hidden_gem_score", 0)
            flag   = score >= GEM_THRESHOLD
            reason = result.get("hidden_gem_reason", "")

            rows[i]["hidden_gem_score"]  = score
            rows[i]["hidden_gem_flag"]   = flag
            rows[i]["hidden_gem_reason"] = reason

            if flag:
                gem_count += 1
                print(f"    💎 GEM [{score}] {reason}")
            elif score >= 75:
                strong_count += 1
                print(f"    ✨ Strong [{score}]")
            else:
                print(f"    📋 Score: {score}")
        else:
            rows[i]["hidden_gem_score"]  = ""
            rows[i]["hidden_gem_flag"]   = ""
            rows[i]["hidden_gem_reason"] = "ERROR: scoring failed"
            error_count += 1

        scored_since_flush += 1
        is_last = (n == len(to_score_idx))
        if scored_since_flush >= GEM_FLUSH_EVERY or is_last:
            _write_scored_csv(args.output, rows, final_headers)
            scored_since_flush = 0
            print(f"    💾 Flushed scored CSV ({n}/{len(to_score_idx)} processed).")

    print(f"\n✅ Scored CSV saved: {args.output}")
    print(f"   💎 Hidden Gems:  {gem_count}")
    print(f"   ✨ Strong:        {strong_count}")
    print(f"   ❌ Errors:        {error_count}")

    # Write gems-only CSV
    gem_rows = [r for r in rows if str(r.get("hidden_gem_flag", "")).lower() == "true"]
    if gem_rows:
        Path(args.gems).parent.mkdir(parents=True, exist_ok=True)
        with open(args.gems, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=final_headers, extrasaction="ignore")
            writer.writeheader()
            writer.writerows(gem_rows)
        print(f"   💎 Gems-only CSV: {args.gems} ({len(gem_rows)} rows)")
```

(This replaces the old standalone "Build final header"/"Write main
output" block that used to come *after* the loop — the incremental flush
now covers that same final write via the `is_last` check, so nothing is
lost. The gems-only CSV write at the end is unchanged.)

- [ ] **Step 4: Live verification**

Run: `source .venv/bin/activate && python -c "
import sys; sys.path.insert(0, 'scripts')
import score_keeper_gems
print('GEM_FLUSH_EVERY:', score_keeper_gems.GEM_FLUSH_EVERY)
print('score_bullet signature check:', score_keeper_gems.score_bullet.__code__.co_varnames[:2])
"`
Expected: prints `5` and `('system_prompt', 'bullet')`, no import errors
(confirms the old `client` parameter is gone).

Then run it via its real CLI:
Run: `python scripts/score_keeper_gems.py --dry-run`
Expected: prints the first 5 rows that would be scored, no API calls,
no errors (confirms the script still runs end-to-end after the import/
client changes).

Then: `python -m unittest discover -s tests`
Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add scripts/score_keeper_gems.py
git commit -m "$(cat <<'EOF'
Migrate score_keeper_gems.py to GeminiClient, add incremental flush

Drops the separate google.genai client in favor of the shared
GeminiClient.generate() -- inherits retry/backoff/model-fallback/
sustained-failure detection instead of a fourth duplicate
implementation. Also flushes the scored CSV every 5 rows instead of
only once at the very end, so an interruption doesn't lose all
progress (the existing skip-already-scored logic already reads fresh
from the same input/output file, so it just needed the flush to work).
EOF
)"
```

## Final Verification

- [ ] Run the full suite one more time: `python -m unittest discover -s tests -v`
  Expected: all tests PASS.
- [ ] Confirm `cluster_bullet_bank.py`, `embed_bullet_bank.py`, and
  `bullet_bank_menu.py` show no diffs from this work:
  `git diff --stat scripts/cluster_bullet_bank.py scripts/embed_bullet_bank.py scripts/bullet_bank_menu.py`
  Expected: no output (no changes).
- [ ] Whenever a real rewrite/audit/gem-scoring run happens next, confirm
  the incremental flushes are visible in the console output ("Flushed
  audited keepers ...", "Flushed scored CSV ...") and that interrupting
  and re-running either script picks up from where it left off instead
  of re-scoring already-done bullets.
