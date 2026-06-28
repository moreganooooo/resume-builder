#!/usr/bin/env python3
"""
cluster_bullet_bank.py

Groups near-duplicate bullets in the bullet bank so you can keep exactly one
representative bullet per concept cluster and queue the rest for retirement.

Inputs  (all in resume-engine/knowledge_base/):
  bullet-bank-clean.csv           raw bullet bank (must exist)

Outputs (all in resume-engine/knowledge_base/):
  bullet-bank-clustered.csv       every bullet annotated with cluster_id,
                                  cluster_size, and is_representative flag
  cluster-map.json                human-readable cluster summary
  rewrite-queue.csv               non-representative bullets queued for rewrite
                                  or retirement

Algorithm
---------
1. Embed every bullet via Gemini Embedding API (gemini-embedding-2).
2. Build a cosine-similarity matrix.
3. Threshold-cluster: any pair with cosine >= SIMILARITY_THRESHOLD are merged
   into the same cluster (single-linkage).
4. Within each cluster, elect the representative bullet (longest after
   stripping leading punctuation).
5. Write outputs.

Usage:
  python cluster_bullet_bank.py

Note: Embeddings are cached in bullet_vectors_ge2_d768.npy so you can
re-run the clustering step without re-embedding.  Delete the .npy file to
force a fresh embed pass.
"""

import os
import json
import time
import numpy as np
import pandas as pd
import urllib.request
from dotenv import load_dotenv

# ---------------------------------------------------------------------------
# PATHS
# ---------------------------------------------------------------------------
SCRIPT_DIR   = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(SCRIPT_DIR)
KB_DIR       = os.path.join(PROJECT_ROOT, "resume-engine", "knowledge_base")

load_dotenv(os.path.join(PROJECT_ROOT, ".env"), override=True)

RAW_CSV       = os.path.join(KB_DIR, "bullet-bank-clean.csv")
CLUSTERED_CSV = os.path.join(KB_DIR, "bullet-bank-clustered.csv")
CLUSTER_MAP   = os.path.join(KB_DIR, "cluster-map.json")
REWRITE_QUEUE = os.path.join(KB_DIR, "rewrite-queue.csv")
VECTOR_CACHE  = os.path.join(KB_DIR, "bullet_vectors_ge2_d768.npy")

# ---------------------------------------------------------------------------
# CONFIG
# ---------------------------------------------------------------------------
SIMILARITY_THRESHOLD = 0.88   # cosine >= this => same cluster
EMBED_MODEL          = "gemini-embedding-2"
EMBED_DIM            = 3072
EMBED_SLEEP          = 1.2    # seconds between embed calls (free-tier rate limit)

API_KEY = os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
BASE_URL = "https://generativelanguage.googleapis.com/v1beta/models"

# ---------------------------------------------------------------------------
# EMBEDDING
# ---------------------------------------------------------------------------

def embed_text(text: str) -> list[float] | None:
    url = f"{BASE_URL}/{EMBED_MODEL}:embedContent?key={API_KEY}"
    payload = {
        "model": f"models/{EMBED_MODEL}",
        "content": {"parts": [{"text": text}]},
    }
    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            body = json.loads(resp.read().decode("utf-8"))
            return body.get("embedding", {}).get("values")
    except Exception as e:
        print(f"    Embed error: {e}")
        return None


def load_or_build_vectors(bullets: list[str]) -> np.ndarray:
    """
    Load cached vectors if they exist and match the current bullet count;
    otherwise re-embed all bullets and save to cache.
    """
    if os.path.exists(VECTOR_CACHE):
        cached = np.load(VECTOR_CACHE)
        if cached.shape == (len(bullets), EMBED_DIM):
            print(f"  Loaded {len(bullets)} cached vectors from {VECTOR_CACHE}")
            return cached
        else:
            print(f"  Cache shape mismatch ({cached.shape} vs expected ({len(bullets)}, {EMBED_DIM})). Re-embedding...")

    print(f"  Embedding {len(bullets)} bullets via {EMBED_MODEL}...")
    vectors = []
    for i, bullet in enumerate(bullets):
        if i > 0 and i % 10 == 0:
            print(f"    {i}/{len(bullets)}...")
        vec = embed_text(bullet)
        if vec is None or len(vec) != EMBED_DIM:
            print(f"    Warning: bad embedding for bullet {i}, using zeros.")
            vec = [0.0] * EMBED_DIM
        vectors.append(vec)
        time.sleep(EMBED_SLEEP)

    matrix = np.array(vectors, dtype=np.float32)
    np.save(VECTOR_CACHE, matrix)
    print(f"  Saved {len(bullets)} vectors to {VECTOR_CACHE}")
    return matrix


# ---------------------------------------------------------------------------
# CLUSTERING
# ---------------------------------------------------------------------------

def cosine_similarity_matrix(matrix: np.ndarray) -> np.ndarray:
    """Returns an (N, N) cosine similarity matrix."""
    norms = np.linalg.norm(matrix, axis=1, keepdims=True)
    norms = np.where(norms == 0, 1e-9, norms)
    normed = matrix / norms
    return normed @ normed.T


def single_linkage_cluster(sim_matrix: np.ndarray, threshold: float) -> list[int]:
    """
    Single-linkage clustering: assign cluster IDs.
    Returns a list of cluster_id per row (0-indexed).
    """
    n = sim_matrix.shape[0]
    cluster_ids = list(range(n))  # each bullet starts in its own cluster

    def find(x):
        while cluster_ids[x] != x:
            cluster_ids[x] = cluster_ids[cluster_ids[x]]  # path compression
            x = cluster_ids[x]
        return x

    def union(x, y):
        rx, ry = find(x), find(y)
        if rx != ry:
            cluster_ids[ry] = rx  # merge ry into rx

    for i in range(n):
        for j in range(i + 1, n):
            if sim_matrix[i, j] >= threshold:
                union(i, j)

    # Normalise cluster IDs to sequential integers
    root_to_id = {}
    result = []
    for i in range(n):
        root = find(i)
        if root not in root_to_id:
            root_to_id[root] = len(root_to_id)
        result.append(root_to_id[root])
    return result


def elect_representative(group: pd.DataFrame) -> int:
    """
    Choose the representative bullet within a cluster:
    longest bullet text after stripping leading `- ` or `* `.
    Returns the index of the elected row.
    """
    col = "bullet" if "bullet" in group.columns else group.columns[0]
    lengths = group[col].str.strip().str.lstrip("-* ").str.len()
    return lengths.idxmax()


# ---------------------------------------------------------------------------
# MAIN
# ---------------------------------------------------------------------------

def main():
    print("\n" + "=" * 60)
    print("  CLUSTER BULLET BANK")
    print("=" * 60)

    if not os.path.exists(RAW_CSV):
        print(f"  ERROR: {RAW_CSV} not found.")
        return

    df = pd.read_csv(RAW_CSV)
    print(f"  Loaded {len(df)} bullets from {RAW_CSV}")

    bullet_col = "bullet" if "bullet" in df.columns else df.columns[0]
    bullets = df[bullet_col].fillna("").tolist()

    # --- EMBED ---
    matrix = load_or_build_vectors(bullets)

    # --- CLUSTER ---
    print(f"  Computing cosine similarity matrix ({len(bullets)}x{len(bullets)})...")
    sim_matrix = cosine_similarity_matrix(matrix)
    print(f"  Clustering at threshold={SIMILARITY_THRESHOLD}...")
    cluster_ids = single_linkage_cluster(sim_matrix, SIMILARITY_THRESHOLD)

    df["cluster_id"]   = cluster_ids
    df["cluster_size"] = df["cluster_id"].map(df["cluster_id"].value_counts())

    # --- ELECT REPRESENTATIVES ---
    rep_indices = set()
    for cid, group in df.groupby("cluster_id"):
        rep_idx = elect_representative(group)
        rep_indices.add(rep_idx)

    df["is_representative"] = df.index.isin(rep_indices)

    # --- STATS ---
    n_clusters   = df["cluster_id"].nunique()
    n_singletons = (df["cluster_size"] == 1).sum()
    n_dupes      = len(df) - df["is_representative"].sum()
    print(f"  Clusters: {n_clusters}  |  Singletons: {n_singletons}  |  Non-representative: {n_dupes}")

    # --- WRITE CLUSTERED CSV ---
    df.to_csv(CLUSTERED_CSV, index=False)
    print(f"  Wrote {len(df)} rows to {CLUSTERED_CSV}")

    # --- WRITE CLUSTER MAP ---
    cluster_map = {}
    for cid, group in df.groupby("cluster_id"):
        rep_row   = group[group["is_representative"]].iloc[0]
        rep_text  = rep_row[bullet_col]
        members   = group[bullet_col].tolist()
        cluster_map[str(cid)] = {
            "size":            len(members),
            "representative":  rep_text,
            "members":         members,
        }
    with open(CLUSTER_MAP, "w", encoding="utf-8") as f:
        json.dump(cluster_map, f, indent=2, ensure_ascii=False)
    print(f"  Wrote cluster map to {CLUSTER_MAP}")

    # --- WRITE REWRITE QUEUE ---
    non_rep = df[~df["is_representative"]].copy()
    # Add queue metadata columns if not already present
    for col, default in [
        ("next_action",      "REVIEW"),
        ("rewrite_status",   ""),
        ("rewrite_attempts", 0),
        ("rewrite_reasoning",""),
        ("context_gaps",     ""),
        ("rewrite_date",     ""),
        ("final_bullet",     ""),
    ]:
        if col not in non_rep.columns:
            non_rep[col] = default

    if os.path.exists(REWRITE_QUEUE):
        existing = pd.read_csv(REWRITE_QUEUE)
        existing_bullets = set(existing[bullet_col].fillna("").tolist())
        new_rows = non_rep[~non_rep[bullet_col].isin(existing_bullets)]
        if len(new_rows) > 0:
            combined = pd.concat([existing, new_rows], ignore_index=True)
            combined.to_csv(REWRITE_QUEUE, index=False)
            print(f"  Appended {len(new_rows)} new rows to existing {REWRITE_QUEUE} ({len(combined)} total)")
        else:
            print(f"  No new rows to append — {REWRITE_QUEUE} already up to date.")
    else:
        non_rep.to_csv(REWRITE_QUEUE, index=False)
        print(f"  Wrote {len(non_rep)} rows to {REWRITE_QUEUE}")

    print("\n  Done.")


if __name__ == "__main__":
    main()
