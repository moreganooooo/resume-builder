# cluster_bullet_bank.py Checkpoint, Batching & Rate-Limit Handling — Design

## Problem

`cluster_bullet_bank.py`'s embedding step (`load_or_build_vectors()`) makes
one real, billed `embedContent` API call per bullet (no batching) and has
no incremental checkpointing — only an all-or-nothing final `np.save()`
after the entire loop completes. A real run against 1431 bullets hit the
account's 1,000 RPD quota partway through (~bullet 1035) and had to be
interrupted. Restarting re-embeds everything from bullet 0, re-spending
real API calls already paid for. Separately, once rate-limited,
`embed_text()`'s broad `except Exception` catches the 429 the same as any
other failure and the loop just keeps burning through the remaining
bullets writing zero-vectors — wasteful, and it produces a
`bullet-bank-cluster-map.csv` that looks complete but silently isn't.

`embed_bullet_bank.py` (pipeline stage 6, embedding the *final* keeper
bank for runtime bullet-matching) already solves both problems with a
proven, working pattern: `batchEmbedContents` (20 bullets/request),
exponential-backoff retry on 429 with a hard stop after `MAX_RETRIES`, and
an incremental `.npz` checkpoint saved after every batch. This design
ports that same pattern to `cluster_bullet_bank.py`.

## Goals

1. Batch embedding calls 20-at-a-time (`batchEmbedContents`), matching
   `embed_bullet_bank.py`'s exact `BATCH_SIZE`/`EMBED_SLEEP` (20s between
   batches) — cuts required calls for 1431 bullets from 1431 to ~72,
   directly reducing RPD pressure rather than just recovering from it
   better.
2. On a 429: retry with exponential backoff (`10 * 2**attempt`, up to
   `MAX_RETRIES=4`); if still rate-limited after that, stop the whole
   script with an actionable message telling the user to swap
   `GEMINI_API_KEY` and re-run — never silently zero-fill the remainder.
3. Checkpoint vectors + progress after every batch to a file distinct
   from `embed_bullet_bank.py`'s own checkpoint (no naming collision);
   resume from the checkpoint on restart instead of re-embedding from
   bullet 0; delete the checkpoint only once the stage completes
   successfully.
4. Fix a separate, pre-existing bug found in the same code path: stage 2
   (`cluster_bullet_bank.py`) and stage 6 (`embed_bullet_bank.py`)
   currently write their final embedding caches to the *identical*
   filename (`bullet_vectors_ge2_d768.npy`) despite embedding different
   bullet sets (raw `bullet-bank-clean.csv` vs. the final
   `bullet-bank-keepers-audited.csv`). Rename stage 2's own cache to
   `bullet_vectors_ge2_d768_cluster.npy` so the two stages can never
   read or overwrite each other's embeddings.
5. Surface an in-progress checkpoint in the Bullet Bank Management
   submenu's status table (e.g. `"Never run (checkpoint at bullet
   1035/1431 -- resumable)"`) instead of a bare `"Never run"` — this is
   the exact "what's going on" question that prompted this design.

## Non-Goals

- No changes to `embed_bullet_bank.py` itself (stage 6) — it already
  works correctly and wasn't reported broken. Its own checkpoint format
  is not modified, and the new "checkpoint in progress" status display
  is wired up for the `cluster` stage only, not generalized to `embed`.
- No change to `SIMILARITY_THRESHOLD`, the clustering algorithm itself,
  or any other part of `cluster_bullet_bank.py` beyond the embedding
  step's request shape, retry/checkpoint behavior, and cache filename.
- No automatic API-key rotation — swapping `GEMINI_API_KEY` in `.env`
  when rate-limited stays a manual step (matches the user's existing
  workflow of holding several keys and swapping by hand); this design
  only makes that swap-and-resume actually resume instead of restarting.

## Architecture

### 1. Batched embedding with bounded retry

Replace `embed_text(text) -> list[float] | None` with
`embed_batch(texts: list) -> list`, mirroring `embed_bullet_bank.py`'s
implementation exactly:

```python
def embed_batch(texts: list) -> list:
    url = f"{BASE_URL}/{EMBED_MODEL}:batchEmbedContents?key={API_KEY}"
    requests_payload = [
        {
            "model": f"models/{EMBED_MODEL}",
            "content": {"parts": [{"text": t}]},
            "outputDimensionality": EMBED_DIM,
            "taskType": "RETRIEVAL_DOCUMENT",
        }
        for t in texts
    ]
    body = {"requests": requests_payload}

    for attempt in range(MAX_RETRIES):
        resp = requests.post(url, json=body, timeout=120)
        if resp.status_code == 429:
            wait = 10 * (2 ** attempt)
            print(f"    Rate limited. Waiting {wait}s (attempt {attempt+1}/{MAX_RETRIES})...")
            time.sleep(wait)
            continue
        resp.raise_for_status()
        embeddings = resp.json().get("embeddings", [])
        return [e["values"] for e in embeddings]

    raise RuntimeError(
        f"embed_batch failed after {MAX_RETRIES} retries -- still rate-limited. "
        "Swap GEMINI_API_KEY in .env and re-run this script; it will resume "
        "from the last saved checkpoint."
    )
```

`taskType: "RETRIEVAL_DOCUMENT"` is added here even though it wasn't in
`cluster_bullet_bank.py`'s original single-item payload — both scripts
embed bullet text for the same downstream purpose (cosine-similarity
comparison), so they should use the same task type for consistency.

This requires switching the HTTP client from `urllib.request` to
`requests` (already a project dependency — `embed_bullet_bank.py` and
`score_keeper_gems.py` both already depend on it) for parity with the
reference implementation, avoiding maintaining two different raw-HTTP
patterns for the same kind of call in the same codebase. `embed_text()`
is `cluster_bullet_bank.py`'s only use of `urllib.request` — the
`import urllib.request` line is removed entirely, not left unused.

An uncaught `RuntimeError` from `embed_batch()` propagates up through
`main()`, producing a non-zero exit code. `bullet_bank_menu.py`'s
`_handle_choice()` already treats any non-zero exit as a failure
(`cli_art.display_error(...)`, stays in the submenu) — no changes needed
there.

### 2. Checkpointing

New checkpoint path, distinct from `embed_bullet_bank.py`'s own
(`bullet_vectors_ge2_d768.checkpoint.npz`) to avoid any collision:

```python
CLUSTER_CHECKPOINT_PATH = os.path.join(KB_DIR, "bullet_vectors_ge2_d768_cluster.checkpoint.npz")
```

`load_checkpoint()`/`save_checkpoint()`, same shape as
`embed_bullet_bank.py`'s, plus a `total` field (needed by the submenu
status display in section 4 — `embed_bullet_bank.py`'s own checkpoint
doesn't need this since it isn't surfaced in the menu):

```python
def load_checkpoint() -> tuple:
    if os.path.exists(CLUSTER_CHECKPOINT_PATH):
        data = np.load(CLUSTER_CHECKPOINT_PATH, allow_pickle=False)
        vectors = list(data["vectors"])
        next_index = int(data["next_index"])
        print(f"  Resuming from checkpoint: {next_index} bullets already embedded.")
        return vectors, next_index
    return [], 0


def save_checkpoint(vectors: list, next_index: int, total: int) -> None:
    np.savez(
        CLUSTER_CHECKPOINT_PATH,
        vectors=np.array(vectors, dtype=np.float32),
        next_index=np.array(next_index),
        total=np.array(total),
    )
```

`load_or_build_vectors()`'s loop restructures to batch-and-checkpoint
(the existing full-output-cache check at the top, against the renamed
`VECTOR_CACHE`, is unchanged — it still short-circuits entirely if a
complete, correctly-shaped cache already exists):

```python
vectors, start_index = load_checkpoint()
total = len(bullets)

for batch_start in range(start_index, total, BATCH_SIZE):
    batch_end = min(batch_start + BATCH_SIZE, total)
    batch = bullets[batch_start:batch_end]
    vecs = embed_batch(batch)
    vectors.extend(vecs)
    save_checkpoint(vectors, batch_end, total)
    if batch_end < total:
        time.sleep(EMBED_SLEEP)

matrix = np.array(vectors, dtype=np.float32)
np.save(VECTOR_CACHE, matrix)
if os.path.exists(CLUSTER_CHECKPOINT_PATH):
    os.remove(CLUSTER_CHECKPOINT_PATH)
```

### 3. Cache filename collision fix

`VECTOR_CACHE` renamed from `bullet_vectors_ge2_d768.npy` to
`bullet_vectors_ge2_d768_cluster.npy`. This is the only line that
changes for this fix — `embed_bullet_bank.py`'s own `NPY_PATH` is
untouched. Anyone who already has a stale
`bullet_vectors_ge2_d768.npy` from a prior `cluster_bullet_bank.py` run
simply won't be found under the new name, so the stage correctly reports
"Never run" and re-embeds — no silent reuse of a file that may actually
belong to the other stage.

### 4. Submenu status: surface in-progress checkpoints

In `bullet_bank_menu.py`, the `cluster` entry in `STAGES` gains a
`checkpoint` key pointing at `CLUSTER_CHECKPOINT_PATH`. `_stage_status()`
checks it when the stage's real output is missing:

```python
def _stage_status(stage: dict) -> tuple:
    ...
    output = stage["output"]
    if not os.path.exists(output):
        checkpoint = stage.get("checkpoint")
        if checkpoint and os.path.exists(checkpoint):
            data = np.load(checkpoint, allow_pickle=False)
            next_index = int(data["next_index"])
            total = int(data["total"])
            return ("Never run", f"checkpoint at bullet {next_index}/{total} -- resumable")
        return ("Never run", "")
    ...
```

This only fires for `cluster` (the one stage that now has a checkpoint);
every other stage's `stage` dict simply has no `checkpoint` key, so
`stage.get("checkpoint")` is `None` and behavior is unchanged.

## Data Flow

```
run_bullet_bank_menu() -> "Cluster & Classify Bullets" chosen
  -> subprocess: cluster_bullet_bank.py
       load_or_build_vectors(bullets)
         load_checkpoint() -- 0 bullets if none, or resumes at next_index
         for each batch of 20:
           embed_batch() -- batchEmbedContents, retries on 429, raises after MAX_RETRIES
           save_checkpoint() -- after every batch
         (all batches done) -> np.save(VECTOR_CACHE) -> remove checkpoint
       ... clustering continues unchanged ...
  -> exit code 0 (success) or non-zero (RuntimeError propagated)
       bullet_bank_menu._handle_choice() already handles non-zero via cli_art.display_error()

Next menu visit, before a successful full run:
  _stage_status({"output": VECTOR_CACHE-adjacent CLUSTER_MAP_CSV, "checkpoint": CLUSTER_CHECKPOINT_PATH, ...})
    -> output missing, checkpoint present -> "Never run (checkpoint at bullet N/total -- resumable)"
```

## Error Handling

- `embed_batch()` exhausting `MAX_RETRIES` on 429: raises `RuntimeError`
  with an actionable message (swap key, re-run, resumes automatically).
  Non-429 HTTP errors (`resp.raise_for_status()`) propagate immediately,
  no retry — matches `embed_bullet_bank.py`'s existing behavior exactly.
- Checkpoint file present but corrupted/unreadable (e.g. truncated by a
  hard kill mid-write): `np.load` would raise; this is an existing,
  accepted risk in `embed_bullet_bank.py`'s identical pattern too, so no
  new handling is introduced here beyond what the proven reference
  already does (not addressed by this design — consistent with it, not
  a regression).
- A stale checkpoint whose `total` no longer matches the current
  `bullet-bank-clean.csv` row count (e.g. bullets were added/removed
  between runs): not explicitly guarded — mirrors
  `embed_bullet_bank.py`'s own checkpoint, which has the same
  characteristic gap. Out of scope for this design.

## Testing

- `bullet_bank_menu._stage_status()`: new test — a stage dict with a
  `checkpoint` key pointing at a temp `.npz` file (containing
  `next_index`/`total`) and a missing `output` file returns `("Never
  run", "checkpoint at bullet N/total -- resumable")`; a stage dict
  without a `checkpoint` key behaves exactly as before (regression
  check against the existing mtime tests).
- `cluster_bullet_bank.py`'s new `embed_batch()`/checkpoint logic: no
  dedicated unit tests, consistent with this repo's existing convention
  of not unit-testing the standalone bullet-bank pipeline scripts
  themselves (verified live instead, as `audit_bullet_bank.py`/
  `embed_bullet_bank.py` already are) — `tests/test_bootstrap_bullet_bank_pipeline.py`'s
  existing mocked reference to `"cluster_bullet_bank.py"` as a subprocess
  name is unaffected by any of these internal changes.
- Live verification: run the Cluster & Classify stage against a small
  slice of real bullets (or the full bank), Ctrl-C it partway through,
  confirm a `bullet_vectors_ge2_d768_cluster.checkpoint.npz` exists with
  a `next_index` less than the total, re-run and confirm it resumes from
  that index (no re-embedding of already-completed bullets) rather than
  restarting from 0. Confirm the submenu's status table shows the
  "checkpoint at bullet N/total" detail while incomplete, and that a
  full successful run produces `bullet_vectors_ge2_d768_cluster.npy`,
  removes the checkpoint, and flips status to "Up to date."
