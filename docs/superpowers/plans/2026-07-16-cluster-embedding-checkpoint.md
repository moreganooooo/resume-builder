# cluster_bullet_bank.py Checkpoint & Rate-Limit Handling Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make `cluster_bullet_bank.py`'s embedding step resumable
(checkpoint after every batch, resume instead of restarting from bullet
0), batch its API calls 20-at-a-time to cut RPD consumption ~20x, stop
cleanly with an actionable message when truly rate-limited instead of
silently zero-filling the rest, fix a pre-existing cache-filename
collision with `embed_bullet_bank.py`, and surface in-progress
checkpoints in the Bullet Bank Management submenu's status table.

**Architecture:** `cluster_bullet_bank.py`'s embedding logic is rewritten
to mirror `embed_bullet_bank.py`'s already-proven `batchEmbedContents` +
exponential-backoff-retry + incremental-`.npz`-checkpoint pattern
exactly, under a distinctly-named cache/checkpoint pair. `bullet_bank_menu.py`'s
`_stage_status()` gains an optional checkpoint-progress branch, wired up
for the `cluster` stage only.

**Tech Stack:** Python 3.10+, `requests` (already a project dependency),
`numpy`, stdlib `unittest`.

## Global Constraints

- No changes to `embed_bullet_bank.py` itself — it already works
  correctly and isn't part of this fix.
- No changes to `cluster_bullet_bank.py`'s clustering algorithm,
  `SIMILARITY_THRESHOLD`, or audit-score-join logic — only the embedding
  step's request shape, retry/checkpoint behavior, and cache filename.
- `cluster_bullet_bank.py` has no existing dedicated test file and isn't
  part of this repo's automated test suite (only referenced as a mocked
  subprocess name in `tests/test_bootstrap_bullet_bank_pipeline.py`) —
  consistent with every other standalone bullet-bank pipeline script
  (`audit_bullet_bank.py`, `embed_bullet_bank.py`, etc.), which are
  verified live rather than unit tested. This plan follows that same
  convention for Task 1; only Task 2 (the new `bullet_bank_menu.py`
  logic) gets unit tests.
- Run `python -m unittest discover -s tests` after Task 2 and confirm
  the full suite passes.

---

## File Structure

| File | Responsibility |
|---|---|
| `scripts/cluster_bullet_bank.py` (modified) | `embed_text()` replaced with `embed_batch()` (batched, retry-on-429, hard-stop after exhausted retries); `load_checkpoint()`/`save_checkpoint()` added; `load_or_build_vectors()` restructured to batch-and-checkpoint; `VECTOR_CACHE` renamed. |
| `scripts/bullet_bank_menu.py` (modified) | New `CLUSTER_CHECKPOINT_PATH` constant; `cluster` stage entry gains a `checkpoint` key; `_stage_status()` gains a checkpoint-progress branch. |
| `tests/test_bullet_bank_menu.py` (modified) | Covers the new checkpoint-progress status branch. |

---

### Task 1: `cluster_bullet_bank.py` — batching, retry, checkpoint, cache rename

**Files:**
- Modify: `scripts/cluster_bullet_bank.py` (imports, constants, `embed_text` → `embed_batch`, `load_or_build_vectors`, module docstring's "Note")

**Interfaces:**
- Produces: `cluster_bullet_bank.embed_batch(texts: list) -> list`
  (replaces `embed_text`), `cluster_bullet_bank.load_checkpoint() ->
  tuple[list, int]`, `cluster_bullet_bank.save_checkpoint(vectors: list,
  next_index: int, total: int) -> None`,
  `cluster_bullet_bank.CLUSTER_CHECKPOINT_PATH: str` (new constant,
  `resume-engine/knowledge_base/bullet_vectors_ge2_d768_cluster.checkpoint.npz`),
  `cluster_bullet_bank.VECTOR_CACHE: str` (renamed value,
  `resume-engine/knowledge_base/bullet_vectors_ge2_d768_cluster.npy`).

- [ ] **Step 1: N/A — no new failing test for this task**

`cluster_bullet_bank.py` has no dedicated test file and isn't part of
this repo's automated suite (see Global Constraints). Proceed directly
to implementation; this task is verified live in Step 4.

- [ ] **Step 2: N/A**

- [ ] **Step 3: Implement**

Replace the imports block (`scripts/cluster_bullet_bank.py:51-57`):

```python
import os
import json
import time
import numpy as np
import pandas as pd
import requests
from dotenv import load_dotenv
```

(`import urllib.request` is removed — `embed_text()` was its only use in
this file.)

Replace the module docstring's "Note" paragraph (originally lines 46-48):

```
Note: Embeddings are cached in bullet_vectors_ge2_d768_cluster.npy so you
can re-run the clustering step without re-embedding. Delete the .npy file
to force a fresh embed pass. If interrupted mid-embedding (rate limit,
Ctrl-C), progress is checkpointed after every batch of 20 --
re-running this script resumes from where it left off instead of
starting over.
```

Replace the `PATHS`/`CONFIG` constants (originally lines 68-89):

```python
RAW_CSV                 = os.path.join(KB_DIR, "bullet-bank-clean.csv")
AUDITED_CSV             = os.path.join(KB_DIR, "bullet-bank-audited.csv")
CLUSTER_MAP_CSV         = os.path.join(KB_DIR, "bullet-bank-cluster-map.csv")
CLUSTER_MAP             = os.path.join(KB_DIR, "cluster-map.json")
REWRITE_QUEUE           = os.path.join(KB_DIR, "rewrite-queue.csv")
VECTOR_CACHE            = os.path.join(KB_DIR, "bullet_vectors_ge2_d768_cluster.npy")
CLUSTER_CHECKPOINT_PATH = os.path.join(KB_DIR, "bullet_vectors_ge2_d768_cluster.checkpoint.npz")

AUDIT_SCORE_COLS = [
    "accuracy_score", "believability_score", "clarity_score",
    "ats_value", "manager_test", "weaknesses",
]

# ---------------------------------------------------------------------------
# CONFIG
# ---------------------------------------------------------------------------
SIMILARITY_THRESHOLD = 0.75   # cosine >= this => same cluster
EMBED_MODEL          = "gemini-embedding-2"
EMBED_DIM            = 768    # gemini-embedding-2 native dimension
BATCH_SIZE           = 20     # batchEmbedContents supports up to ~20 requests per call
EMBED_SLEEP          = 20     # seconds between batch calls -- matches embed_bullet_bank.py's proven interval
MAX_RETRIES          = 4

API_KEY = os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
BASE_URL = "https://generativelanguage.googleapis.com/v1beta/models"
```

(`VECTOR_CACHE` renamed to end in `_cluster.npy` -- fixes the pre-existing
collision with `embed_bullet_bank.py`'s own `NPY_PATH`, which resolves to
the un-suffixed `bullet_vectors_ge2_d768.npy`. `EMBED_SLEEP` changes from
`1.2` (per-bullet) to `20` (per-batch, matching `embed_bullet_bank.py`
exactly) since batching changes what the sleep is spacing out.)

Replace `embed_text()` and `load_or_build_vectors()` (originally lines
95-145) with:

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
            print(f"    Rate limited. Waiting {wait}s (attempt {attempt + 1}/{MAX_RETRIES})...")
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


def load_or_build_vectors(bullets: list[str]) -> np.ndarray:
    """
    Load cached vectors if they exist and match the current bullet count;
    otherwise embed in batches of BATCH_SIZE, checkpointing after every
    batch so an interruption (rate limit, Ctrl-C) can resume instead of
    re-embedding from scratch.
    """
    if os.path.exists(VECTOR_CACHE):
        cached = np.load(VECTOR_CACHE)
        if cached.shape == (len(bullets), EMBED_DIM):
            print(f"  Loaded {len(bullets)} cached vectors from {VECTOR_CACHE}")
            return cached
        else:
            print(f"  Cache shape mismatch ({cached.shape} vs expected ({len(bullets)}, {EMBED_DIM})). Re-embedding...")

    total = len(bullets)
    vectors, start_index = load_checkpoint()
    print(f"  Embedding {total} bullets via {EMBED_MODEL} (batches of {BATCH_SIZE}, starting at {start_index})...")

    for batch_start in range(start_index, total, BATCH_SIZE):
        batch_end = min(batch_start + BATCH_SIZE, total)
        batch = bullets[batch_start:batch_end]
        print(f"    {batch_end}/{total}...")
        vecs = embed_batch(batch)
        vectors.extend(vecs)
        save_checkpoint(vectors, batch_end, total)
        if batch_end < total:
            time.sleep(EMBED_SLEEP)

    matrix = np.array(vectors, dtype=np.float32)
    np.save(VECTOR_CACHE, matrix)
    print(f"  Saved {total} vectors to {VECTOR_CACHE}")
    if os.path.exists(CLUSTER_CHECKPOINT_PATH):
        os.remove(CLUSTER_CHECKPOINT_PATH)
    return matrix
```

- [ ] **Step 4: Live verification**

Run: `source .venv/bin/activate && python scripts/cluster_bullet_bank.py`
against the real bullet bank. Confirm the progress line now advances in
steps of 20 (not 1) and prints far fewer total API calls. After a few
batches complete, `Ctrl-C` it. Confirm
`resume-engine/knowledge_base/bullet_vectors_ge2_d768_cluster.checkpoint.npz`
exists. Re-run the same command and confirm it prints "Resuming from
checkpoint: N bullets already embedded" and continues from there rather
than restarting at 0. Let it run to completion and confirm
`bullet_vectors_ge2_d768_cluster.npy` is written, the checkpoint file is
removed, and `bullet-bank-cluster-map.csv` is produced as before.

- [ ] **Step 5: Commit**

```bash
git add scripts/cluster_bullet_bank.py
git commit -m "$(cat <<'EOF'
Batch cluster_bullet_bank.py's embedding, add checkpoint/resume, fix cache collision

Ports embed_bullet_bank.py's proven batchEmbedContents + exponential-
backoff-retry + incremental-checkpoint pattern: 20 bullets/request
instead of 1 (~20x fewer API calls), a hard stop with an actionable
message after MAX_RETRIES on a 429 instead of silently zero-filling the
rest, and a checkpoint saved after every batch so an interruption
resumes instead of re-embedding from bullet 0.

Also renames this script's own vector cache to
bullet_vectors_ge2_d768_cluster.npy -- it previously collided with
embed_bullet_bank.py's identically-named cache despite the two scripts
embedding different bullet sets (raw bullet-bank-clean.csv here vs. the
final bullet-bank-keepers-audited.csv there).
EOF
)"
```

---

### Task 2: Surface in-progress checkpoints in the Bullet Bank submenu

**Files:**
- Modify: `scripts/bullet_bank_menu.py` (new constant, `cluster` stage entry, `_stage_status`)
- Test: `tests/test_bullet_bank_menu.py`

**Interfaces:**
- Consumes: `cluster_bullet_bank.CLUSTER_CHECKPOINT_PATH`'s value
  (mirrored, not imported — `bullet_bank_menu.py` defines its own copy of
  the path the same way it already does for every other file constant,
  consistent with how it already resolves `AUDITED_CSV`/`KEEPERS_CSV`/etc.
  independently rather than importing them from each pipeline script).
- Produces: `bullet_bank_menu.CLUSTER_CHECKPOINT_PATH: str`;
  `bullet_bank_menu._stage_status()` gains a checkpoint-aware branch
  (same signature, additive behavior only).

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_bullet_bank_menu.py -- add this class

class TestStageStatusChecksCheckpoint(unittest.TestCase):

    def setUp(self):
        self.tmp_dir = tempfile.mkdtemp()
        self.checkpoint_path = os.path.join(self.tmp_dir, "checkpoint.npz")

    def tearDown(self):
        for name in os.listdir(self.tmp_dir):
            os.remove(os.path.join(self.tmp_dir, name))
        os.rmdir(self.tmp_dir)

    def _write_checkpoint(self, next_index, total):
        import numpy as np
        np.savez(
            self.checkpoint_path,
            vectors=np.zeros((next_index, 4), dtype=np.float32),
            next_index=np.array(next_index),
            total=np.array(total),
        )

    def test_missing_output_with_checkpoint_reports_progress(self):
        self._write_checkpoint(next_index=1035, total=1431)
        stage = {
            "output": os.path.join(self.tmp_dir, "missing.csv"),
            "inputs": [], "status_mode": "mtime",
            "checkpoint": self.checkpoint_path,
        }
        status, detail = bullet_bank_menu._stage_status(stage)
        self.assertEqual(status, "Never run")
        self.assertEqual(detail, "checkpoint at bullet 1035/1431 -- resumable")

    def test_missing_output_without_checkpoint_key_is_unaffected(self):
        stage = {
            "output": os.path.join(self.tmp_dir, "missing.csv"),
            "inputs": [], "status_mode": "mtime",
        }
        status, detail = bullet_bank_menu._stage_status(stage)
        self.assertEqual(status, "Never run")
        self.assertEqual(detail, "")

    def test_missing_output_with_checkpoint_key_but_no_file_is_unaffected(self):
        stage = {
            "output": os.path.join(self.tmp_dir, "missing.csv"),
            "inputs": [], "status_mode": "mtime",
            "checkpoint": os.path.join(self.tmp_dir, "no_such_checkpoint.npz"),
        }
        status, detail = bullet_bank_menu._stage_status(stage)
        self.assertEqual(status, "Never run")
        self.assertEqual(detail, "")


class TestClusterStageHasCheckpointKey(unittest.TestCase):

    def test_cluster_stage_has_checkpoint_key(self):
        cluster_stage = next(s for s in bullet_bank_menu.STAGES if s["key"] == "cluster")
        self.assertIn("checkpoint", cluster_stage)
        self.assertTrue(cluster_stage["checkpoint"].endswith("_cluster.checkpoint.npz"))
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /Users/morganescott/resume-builder && source .venv/bin/activate && python -m unittest tests.test_bullet_bank_menu.TestStageStatusChecksCheckpoint tests.test_bullet_bank_menu.TestClusterStageHasCheckpointKey -v`
Expected: `test_missing_output_with_checkpoint_reports_progress` FAILS (detail is `""`, not the checkpoint message); `test_cluster_stage_has_checkpoint_key` FAILS (`KeyError`/`assertIn` failure — no `checkpoint` key yet). The other two tests already pass against current behavior (they pin the *unaffected* cases) — that's expected and fine.

- [ ] **Step 3: Implement**

Add `import numpy as np` to `scripts/bullet_bank_menu.py`'s imports
(alongside `csv`/`datetime`/`os`/`subprocess`/`sys`).

Add the new constant, near the other path constants:

```python
CLUSTER_CHECKPOINT_PATH = os.path.join(KB_DIR, "bullet_vectors_ge2_d768_cluster.checkpoint.npz")
```

Add a `"checkpoint"` key to the `cluster` entry in `STAGES`:

```python
    {
        "key": "cluster", "number": 2, "label": "Cluster & Classify Bullets",
        "script": "cluster_bullet_bank.py", "inputs": [RAW_CSV, AUDITED_CSV], "output": CLUSTER_MAP_CSV,
        "api_cost": True, "status_mode": "mtime", "checkpoint": CLUSTER_CHECKPOINT_PATH,
    },
```

Replace `_stage_status()`:

```python
def _stage_status(stage: dict) -> tuple:
    """Returns (status_label, detail). status_mode='mtime' (5 of the 6
    stages, each with a distinct input/output file) compares mtimes.
    status_mode='columns' (score_keeper_gems.py, which updates its file
    in place -- same file in and out, so an mtime comparison against
    itself is meaningless) checks column completeness instead. A stage
    with a 'checkpoint' key reports in-progress resume state when its
    real output doesn't exist yet."""
    if stage.get("status_mode") == "columns":
        return _column_completeness_status(stage["output"], stage["status_columns"])

    output = stage["output"]
    if not os.path.exists(output):
        checkpoint = stage.get("checkpoint")
        if checkpoint and os.path.exists(checkpoint):
            return _checkpoint_progress_status(checkpoint)
        return ("Never run", "")

    output_mtime = os.path.getmtime(output)
    for input_path in stage["inputs"]:
        if os.path.exists(input_path) and os.path.getmtime(input_path) > output_mtime:
            return ("Stale", "")

    timestamp = datetime.datetime.fromtimestamp(output_mtime).strftime("%Y-%m-%d %H:%M")
    return ("Up to date", f"as of {timestamp}")


def _checkpoint_progress_status(checkpoint_path: str) -> tuple:
    data = np.load(checkpoint_path, allow_pickle=False)
    next_index = int(data["next_index"])
    total = int(data["total"])
    return ("Never run", f"checkpoint at bullet {next_index}/{total} -- resumable")
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m unittest tests.test_bullet_bank_menu -v`
Expected: all PASS

Then: `python -m unittest discover -s tests`
Expected: all PASS

- [ ] **Step 5: Commit**

```bash
git add scripts/bullet_bank_menu.py tests/test_bullet_bank_menu.py
git commit -m "$(cat <<'EOF'
Surface in-progress checkpoints in the Bullet Bank status table

The cluster stage now reports "Never run (checkpoint at bullet
N/total -- resumable)" instead of a bare "Never run" when it's been
interrupted mid-embedding -- answers exactly the "what's going on"
question a partial run leaves you with.
EOF
)"
```

- [ ] **Step 6: Live verification**

Run `resume`, open "Manage Bullet Bank." If a checkpoint file exists from
Task 1's live verification, confirm the status table shows "Never run
(checkpoint at bullet N/1431 -- resumable)" for the Cluster & Classify
row. Run that stage to completion and confirm the status flips to "Up to
date."

## Final Verification

- [ ] Run the full suite one more time: `python -m unittest discover -s tests -v`
  Expected: all tests PASS.
- [ ] Confirm a full end-to-end Cluster & Classify run (with or without a
  deliberate interruption partway through) produces
  `bullet_vectors_ge2_d768_cluster.npy` and `bullet-bank-cluster-map.csv`,
  and that the submenu status correctly reflects each state along the
  way (never run → in-progress/resumable → up to date).
