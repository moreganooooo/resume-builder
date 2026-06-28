"""embed_bullet_bank.py — One-time offline embedder.

Run this script whenever bullet-bank-keepers-audited.csv is updated.
It embeds every bullet using gemini-embedding-2 and saves:

  resume-engine/knowledge_base/bullet_vectors_ge2_d768.npy
      Shape: (N, 768) float32 array, one row per bullet.

  resume-engine/knowledge_base/bullet_vectors_ge2_d768.meta
      JSON sidecar: model name, dimension, row count, CSV path.

The .npy file is loaded at runtime by mine_bullet_bank() in
orchestrator.py for cosine pre-filtering. Re-run this script if you
add or change bullets — the .npy will be regenerated from scratch.

Speed:
    Uses batchEmbedContents (up to 20 bullets per API call) instead of
    embedContent (1 bullet per call). At 15 RPM free-tier limit:
      Before: 1209 calls → ~80 minutes
      After:  ~61 calls  → ~4 minutes

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
import requests
import numpy as np
import pandas as pd
from dotenv import load_dotenv

# --- PATH SETUP ---
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(SCRIPT_DIR)
load_dotenv(os.path.join(PROJECT_ROOT, ".env"), override=True)

API_KEY  = os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
BASE_URL = "https://generativelanguage.googleapis.com/v1beta/models"

EMBED_MODEL  = "gemini-embedding-2"
EMBED_DIM    = 768   # sweet spot for text-only
BATCH_SIZE   = 20    # batchEmbedContents supports up to ~20 requests per call
EMBED_SLEEP  = 20     # seconds between batch calls → ~15 RPM
MAX_RETRIES  = 4

KB_DIR           = os.path.join(PROJECT_ROOT, "resume-engine", "knowledge_base")
CSV_PATH         = os.path.join(KB_DIR, "bullet-bank-keepers-audited.csv")
NPY_PATH         = os.path.join(KB_DIR, f"bullet_vectors_ge2_d{EMBED_DIM}.npy")
META_PATH        = os.path.join(KB_DIR, f"bullet_vectors_ge2_d{EMBED_DIM}.meta")
CHECKPOINT_PATH  = os.path.join(KB_DIR, f"bullet_vectors_ge2_d{EMBED_DIM}.checkpoint.npz")


def embed_batch(texts: list) -> list:
    """Call batchEmbedContents for a list of strings. Returns list of float lists."""
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
            print(f"    ⏳ Rate limited. Waiting {wait}s (attempt {attempt+1}/{MAX_RETRIES})...")
            time.sleep(wait)
            continue
        resp.raise_for_status()
        embeddings = resp.json().get("embeddings", [])
        return [e["values"] for e in embeddings]

    raise RuntimeError(f"embed_batch failed after {MAX_RETRIES} retries.")


def load_checkpoint():
    """Load saved vectors and resume index from checkpoint file if it exists."""
    if os.path.exists(CHECKPOINT_PATH):
        data = np.load(CHECKPOINT_PATH, allow_pickle=False)
        vectors = list(data["vectors"])
        start_index = int(data["next_index"])
        print(f"   ♻️  Resuming from checkpoint: {start_index} bullets already embedded.")
        return vectors, start_index
    return [], 0


def save_checkpoint(vectors: list, next_index: int):
    """Save current progress to checkpoint file."""
    np.savez(
        CHECKPOINT_PATH,
        vectors=np.array(vectors, dtype=np.float32),
        next_index=np.array(next_index),
    )


def main():
    if not API_KEY:
        raise EnvironmentError("GEMINI_API_KEY / GOOGLE_API_KEY not set in .env")

    print(f"   🔑 Using key: {API_KEY[:8]}... (length {len(API_KEY)})")

    if not os.path.exists(CSV_PATH):
        raise FileNotFoundError(f"Bullet bank not found: {CSV_PATH}")

    df = pd.read_csv(CSV_PATH)

    bullet_col = None
    for candidate in ("bullet", "achievement"):
        if candidate in df.columns:
            bullet_col = candidate
            break
    if bullet_col is None:
        bullets = [" ".join(str(v) for v in row.values) for _, row in df.iterrows()]
    else:
        bullets = df[bullet_col].astype(str).tolist()

    total = len(bullets)
    print(f"📄 Loaded {total} bullets from {CSV_PATH}")

    vectors, start_index = load_checkpoint()

    remaining = total - start_index
    n_batches = (remaining + BATCH_SIZE - 1) // BATCH_SIZE
    est_secs  = n_batches * EMBED_SLEEP
    print(f"🔢 Embedding with {EMBED_MODEL} @ {EMBED_DIM}d")
    print(f"📦 Batch size: {BATCH_SIZE} bullets/call → {n_batches} API calls remaining")
    print(f"⏱  Estimated time: ~{est_secs // 60}m {est_secs % 60}s\n")

    batch_num = 0
    for batch_start in range(start_index, total, BATCH_SIZE):
        batch_end   = min(batch_start + BATCH_SIZE, total)
        batch       = bullets[batch_start:batch_end]
        batch_num  += 1

        print(f"   Batch {batch_num}/{n_batches}  "
              f"[bullets {batch_start+1}–{batch_end}/{total}]  "
              f"{batch[0][:60]}{'...' if len(batch[0]) > 60 else ''}")

        vecs = embed_batch(batch)
        vectors.extend(vecs)

        # Checkpoint after every batch
        save_checkpoint(vectors, batch_end)

        if batch_end < total:
            time.sleep(EMBED_SLEEP)

    # All done — write final outputs
    matrix = np.array(vectors, dtype=np.float32)  # shape: (N, EMBED_DIM)
    np.save(NPY_PATH, matrix)
    print(f"\n✅ Saved {matrix.shape} vector matrix → {NPY_PATH}")

    meta = {
        "model": EMBED_MODEL,
        "dim": EMBED_DIM,
        "rows": total,
        "csv": CSV_PATH,
        "bullet_col": bullet_col or "(stringified row)",
    }
    with open(META_PATH, "w") as f:
        json.dump(meta, f, indent=2)
    print(f"📋 Saved metadata sidecar → {META_PATH}")

    if os.path.exists(CHECKPOINT_PATH):
        os.remove(CHECKPOINT_PATH)
        print(f"🧹 Checkpoint file removed.")

    print("\n🎉 Done. Run this script again whenever bullet-bank-keepers-audited.csv changes.")


if __name__ == "__main__":
    main()
