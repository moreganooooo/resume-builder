"""embed_bullet_bank.py — One-time offline embedder.

Run this script whenever bullet-bank-clean.csv is updated.
It embeds every bullet using gemini-embedding-2 and saves:

  resume-engine/knowledge_base/bullet_vectors_ge2_d768.npy
      Shape: (N, 768) float32 array, one row per bullet.

  resume-engine/knowledge_base/bullet_vectors_ge2_d768.meta
      JSON sidecar: model name, dimension, row count, CSV path.

The .npy file is loaded at runtime by mine_bullet_bank() in
orchestrator.py for cosine pre-filtering. Re-run this script if you
add or change bullets — the .npy will be regenerated from scratch.

Usage:
    python scripts/embed_bullet_bank.py

Rate limiting:
    gemini-embedding-2 free tier: ~1,500 RPD / 15 RPM.
    This script sleeps 4s between each call (~15 RPM ceiling).
    A 200-row CSV takes ~13 minutes. Run it offline / overnight.
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
load_dotenv(os.path.join(PROJECT_ROOT, ".env"))

API_KEY = os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
BASE_URL = "https://generativelanguage.googleapis.com/v1beta/models"

EMBED_MODEL = "gemini-embedding-2"
EMBED_DIM = 768          # sweet spot for text-only; upgrade to 1536 if adding image/PDF KB docs
EMBED_SLEEP = 4          # seconds between calls → ~15 RPM, safely at free-tier ceiling
MAX_RETRIES = 4

KB_DIR = os.path.join(PROJECT_ROOT, "resume-engine", "knowledge_base")
CSV_PATH = os.path.join(KB_DIR, "bullet-bank-clean.csv")
NPY_PATH = os.path.join(KB_DIR, f"bullet_vectors_ge2_d{EMBED_DIM}.npy")
META_PATH = os.path.join(KB_DIR, f"bullet_vectors_ge2_d{EMBED_DIM}.meta")


def embed_text(text: str) -> list:
    """Call gemini-embedding-2 embedContent endpoint. Returns a list of floats."""
    url = f"{BASE_URL}/{EMBED_MODEL}:embedContent?key={API_KEY}"
    body = {
        "model": f"models/{EMBED_MODEL}",
        "content": {"parts": [{"text": text}]},
        "outputDimensionality": EMBED_DIM,
    }
    for attempt in range(MAX_RETRIES):
        resp = requests.post(url, json=body, timeout=60)
        if resp.status_code == 429:
            wait = 5 * (2 ** attempt)
            print(f"    ⏳ Rate limited. Waiting {wait}s (attempt {attempt+1}/{MAX_RETRIES})...")
            time.sleep(wait)
            continue
        resp.raise_for_status()
        return resp.json()["embedding"]["values"]
    raise RuntimeError(f"embed_text failed after {MAX_RETRIES} retries.")


def main():
    if not API_KEY:
        raise EnvironmentError("GEMINI_API_KEY / GOOGLE_API_KEY not set in .env")

    if not os.path.exists(CSV_PATH):
        raise FileNotFoundError(f"Bullet bank not found: {CSV_PATH}")

    df = pd.read_csv(CSV_PATH)

    # Detect the bullet text column (same logic as orchestrator.py)
    bullet_col = None
    for candidate in ("bullet", "achievement"):
        if candidate in df.columns:
            bullet_col = candidate
            break
    if bullet_col is None:
        # Fall back: stringify the whole row
        bullets = [" ".join(str(v) for v in row.values) for _, row in df.iterrows()]
    else:
        bullets = df[bullet_col].astype(str).tolist()

    print(f"📄 Loaded {len(bullets)} bullets from {CSV_PATH}")
    print(f"🔢 Embedding with {EMBED_MODEL} @ {EMBED_DIM}d  ({EMBED_SLEEP}s between calls)")
    print(f"⏱  Estimated time: ~{len(bullets) * EMBED_SLEEP // 60}m {len(bullets) * EMBED_SLEEP % 60}s\n")

    vectors = []
    for i, bullet in enumerate(bullets):
        print(f"   [{i+1:>4}/{len(bullets)}] {bullet[:80]}{'...' if len(bullet) > 80 else ''}")
        vec = embed_text(bullet)
        vectors.append(vec)
        if i < len(bullets) - 1:
            time.sleep(EMBED_SLEEP)

    matrix = np.array(vectors, dtype=np.float32)  # shape: (N, EMBED_DIM)
    np.save(NPY_PATH, matrix)
    print(f"\n✅ Saved {matrix.shape} vector matrix → {NPY_PATH}")

    meta = {
        "model": EMBED_MODEL,
        "dim": EMBED_DIM,
        "rows": len(bullets),
        "csv": CSV_PATH,
        "bullet_col": bullet_col or "(stringified row)",
    }
    with open(META_PATH, "w") as f:
        json.dump(meta, f, indent=2)
    print(f"📋 Saved metadata sidecar → {META_PATH}")
    print("\n🎉 Done. Run this script again whenever bullet-bank-clean.csv changes.")


if __name__ == "__main__":
    main()
