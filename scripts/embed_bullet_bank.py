"""embed_bullet_bank.py — One-time offline embedder.

Run this script whenever bullet-bank-keepers-audited.csv is updated.
It embeds every bullet using gemini-embedding-2 and saves:

  profiles/<profile>/knowledge_base/bullet_vectors_ge2_d768.npy
      Shape: (N, 768) float32 array, one row per bullet.

  profiles/<profile>/knowledge_base/bullet_vectors_ge2_d768.meta
      JSON sidecar: model name, dimension, row count, CSV path.

The .npy file is loaded at runtime by mine_bullet_bank() in
orchestrator.py for cosine pre-filtering. Re-run this script if you
add or change bullets — the .npy will be regenerated from scratch.

Speed:
    Uses batchEmbedContents (up to 20 bullets per API call) instead of
    embedContent (1 bullet per call). At 15 RPM free-tier limit:
      Before: 1209 calls → ~80 minutes
      After:  ~61 calls  → ~20 minutes (EMBED_SLEEP = 20s between batches)

Resume from checkpoint:
    If interrupted, saves a checkpoint after every batch.
    Re-run the same command — it picks up where it left off.
    Checkpoint is deleted automatically on successful completion.

Usage:
    python scripts/embed_bullet_bank.py

Rate limiting:
    gemini-embedding-2 free tier: 15 RPM / 1500 RPD.
    This script sleeps 4s between batches → safely under 15 RPM.

Dependencies:
    pip install requests numpy pandas python-dotenv
"""

import os
import time
import json
import sys
import requests
import numpy as np
import pandas as pd
from dotenv import load_dotenv

# --- PATH SETUP ---
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(SCRIPT_DIR)

if SCRIPT_DIR not in sys.path:
    sys.path.insert(0, SCRIPT_DIR)
import profile_paths  # noqa: E402
from atomic_write import atomic_write  # noqa: E402
from bullet_bank_hash import bullets_sha  # noqa: E402
import cli_art
import theme

load_dotenv(profile_paths.env_path(), override=True)

API_KEY  = os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
BASE_URL = "https://generativelanguage.googleapis.com/v1beta/models"
AUTH_HEADERS = {"x-goog-api-key": API_KEY}

EMBED_MODEL  = "gemini-embedding-2"
EMBED_DIM    = 768   # sweet spot for text-only
BATCH_SIZE   = 20    # batchEmbedContents supports up to ~20 requests per call
EMBED_SLEEP  = 20     # seconds between batch calls → ~15 RPM
MAX_RETRIES  = 4

KB_DIR           = profile_paths.kb_dir()
CSV_PATH         = os.path.join(KB_DIR, "bullet-bank-keepers-audited.csv")
NPY_PATH         = os.path.join(KB_DIR, f"bullet_vectors_ge2_d{EMBED_DIM}.npy")
META_PATH        = os.path.join(KB_DIR, f"bullet_vectors_ge2_d{EMBED_DIM}.meta")
CHECKPOINT_PATH  = os.path.join(KB_DIR, f"bullet_vectors_ge2_d{EMBED_DIM}.checkpoint.npz")


def embed_batch(texts: list) -> list:
    """Call batchEmbedContents for a list of strings. Returns list of float lists."""
    url = f"{BASE_URL}/{EMBED_MODEL}:batchEmbedContents"
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
        resp = requests.post(url, json=body, headers=AUTH_HEADERS, timeout=120)
        if resp.status_code == 429:
            wait = 10 * (2 ** attempt)
            cli_art.console.print(f"    ⏳ Rate limited. Waiting {wait}s (attempt {attempt+1}/{MAX_RETRIES})...", markup=False, soft_wrap=True)
            time.sleep(wait)
            continue
        resp.raise_for_status()
        embeddings = resp.json().get("embeddings", [])
        vecs = [e["values"] for e in embeddings]
        if len(vecs) != len(texts):
            # A response with a missing/short "embeddings" key would
            # otherwise silently contribute fewer rows than sent, shifting
            # every subsequent bullet's vector out of alignment with its
            # CSV row (B20, phase-9-backlog.md).
            raise RuntimeError(
                f"embed_batch: sent {len(texts)} texts but got {len(vecs)} embeddings back "
                "-- refusing to silently misalign the vector matrix."
            )
        return vecs

    raise RuntimeError(f"embed_batch failed after {MAX_RETRIES} retries.")


def load_checkpoint(expected_sha: str):
    """Load saved vectors and resume index from checkpoint file if it
    exists and its bullet-text hash still matches the current bank --
    editing the bank during a rate-limit pause (a multi-hour stall
    invites exactly that) would otherwise resume with row i of the
    checkpointed matrix no longer corresponding to row i of the CSV,
    permanently and silently (B20, phase-9-backlog.md)."""
    if os.path.exists(CHECKPOINT_PATH):
        data = np.load(CHECKPOINT_PATH, allow_pickle=False)
        saved_sha = str(data["bullets_sha"]) if "bullets_sha" in data else None
        if saved_sha != expected_sha:
            cli_art.console.print(f"   {theme.colorize_icon('warning')}  Bullet bank changed since this checkpoint was saved "
                  "-- discarding stale progress and starting over.", soft_wrap=True)
            os.remove(CHECKPOINT_PATH)
            return [], 0
        vectors = list(data["vectors"])
        start_index = int(data["next_index"])
        cli_art.console.print(f"   {theme.colorize_icon('resume')}  Resuming from checkpoint: {start_index} bullets already embedded.", soft_wrap=True)
        return vectors, start_index
    return [], 0


def save_checkpoint(vectors: list, next_index: int, bullets_sha_value: str):
    """Save current progress to checkpoint file."""
    np.savez(
        CHECKPOINT_PATH,
        vectors=np.array(vectors, dtype=np.float32),
        next_index=np.array(next_index),
        bullets_sha=np.array(bullets_sha_value),
    )


def main():
    if not API_KEY:
        raise EnvironmentError("GEMINI_API_KEY / GOOGLE_API_KEY not set in .env")

    cli_art.console.print("   Using API key from environment (value redacted).", markup=False, soft_wrap=True)

    if not os.path.exists(CSV_PATH):
        raise FileNotFoundError(f"Bullet bank not found: {CSV_PATH}")

    df = pd.read_csv(CSV_PATH)

    bullet_col = None
    for candidate in ("Bullet Point", "bullet", "achievement"):
        if candidate in df.columns:
            bullet_col = candidate
            break
    if bullet_col is None:
        raise ValueError(f"No known bullet column found. Columns: {list(df.columns)}")
    # fillna("") before astype(str), not after -- orchestrator.py's
    # mine_bullet_bank() hashes this same column via .fillna(""), and the
    # two sides must agree on NaN handling or a bank with no real content
    # change at all would still produce a hash mismatch ("nan" vs "").
    bullets = df[bullet_col].fillna("").astype(str).tolist()

    total = len(bullets)
    cli_art.console.print(f"{theme.colorize_icon('bullet_bank')} Loaded {total} bullets from {CSV_PATH}", soft_wrap=True)
    current_sha = bullets_sha(bullets)

    vectors, start_index = load_checkpoint(current_sha)

    remaining = total - start_index
    n_batches = (remaining + BATCH_SIZE - 1) // BATCH_SIZE
    est_secs  = n_batches * EMBED_SLEEP
    cli_art.console.print(f"{theme.colorize_icon('build')} Embedding with {EMBED_MODEL} @ {EMBED_DIM}d", soft_wrap=True)
    cli_art.console.print(f"Batch size: {BATCH_SIZE} bullets/call → {n_batches} API calls remaining", markup=False, soft_wrap=True)
    cli_art.console.print(f"Estimated time: ~{est_secs // 60}m {est_secs % 60}s\n", markup=False, soft_wrap=True)

    batch_num = 0
    for batch_start in range(start_index, total, BATCH_SIZE):
        batch_end   = min(batch_start + BATCH_SIZE, total)
        batch       = bullets[batch_start:batch_end]
        batch_num  += 1

        cli_art.console.print(f"   Batch {batch_num}/{n_batches}  "
              f"[bullets {batch_start+1}–{batch_end}/{total}]  "
              f"{batch[0][:60]}{'...' if len(batch[0]) > 60 else ''}", markup=False, soft_wrap=True)

        vecs = embed_batch(batch)
        vectors.extend(vecs)

        # Checkpoint after every batch
        save_checkpoint(vectors, batch_end, current_sha)

        if batch_end < total:
            time.sleep(EMBED_SLEEP)

    # All done — write final outputs
    matrix = np.array(vectors, dtype=np.float32)  # shape: (N, EMBED_DIM)
    np.save(NPY_PATH, matrix)
    cli_art.console.print(f"\n{theme.colorize_icon('success')} Saved {matrix.shape} vector matrix → {NPY_PATH}", soft_wrap=True)

    meta = {
        "model": EMBED_MODEL,
        "dim": EMBED_DIM,
        "rows": total,
        "csv": CSV_PATH,
        "bullet_col": bullet_col or "(stringified row)",
        "bullets_sha": current_sha,
    }
    with atomic_write(META_PATH) as f:
        json.dump(meta, f, indent=2)
    cli_art.console.print(f"{theme.colorize_icon('save')} Saved metadata sidecar → {META_PATH}", soft_wrap=True)

    if os.path.exists(CHECKPOINT_PATH):
        os.remove(CHECKPOINT_PATH)
        cli_art.console.print(f"Checkpoint file removed.", markup=False, soft_wrap=True)

    cli_art.console.print(f"\n{theme.colorize_icon('complete')} Done. Run this script again whenever bullet-bank-keepers-audited.csv changes.", soft_wrap=True)


if __name__ == "__main__":
    main()
