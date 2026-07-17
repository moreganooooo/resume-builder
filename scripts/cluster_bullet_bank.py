#!/usr/bin/env python3
"""
cluster_bullet_bank.py

Groups near-duplicate bullets in the bullet bank, joins each one with its
audit scores, decides a next_action per bullet, and elects one representative
per cluster — the file rewrite_bullets.py reads to know what to rewrite.

Inputs  (all in profiles/<profile>/knowledge_base/):
  bullet-bank-clean.csv           raw bullet bank (must exist)
  bullet-bank-audited.csv         per-bullet scores from audit_bullet_bank.py
                                  (must exist — run that script first if it
                                  doesn't; bullets not found in it are marked
                                  NEEDS_AUDIT rather than blocking the run)

Outputs (all in profiles/<profile>/knowledge_base/):
  bullet-bank-cluster-map.csv     every bullet with cluster_id, cluster_size,
                                  is_representative, next_action, and every
                                  joined audit column — this is what
                                  rewrite_bullets.py (CLUSTER_MAP_IN) reads
  cluster-map.json                human-readable cluster summary
  rewrite-queue.csv               non-representative bullets queued for rewrite
                                  or retirement

Algorithm
---------
1. Embed every bullet via Gemini Embedding API (gemini-embedding-2).
2. Build a cosine-similarity matrix.
3. Threshold-cluster: any pair with cosine >= SIMILARITY_THRESHOLD are merged
   into the same cluster (single-linkage).
4. Join audit scores onto each bullet by normalized text match.
5. Within each cluster, elect the representative bullet: highest
   accuracy_score if any member has one, otherwise longest text.
6. Assign next_action per bullet:
     NEEDS_AUDIT — no accuracy_score AND no believability_score (unscored)
     KEEP        — manager_test PASS, believability >= 80, no weaknesses
     REWRITE     — manager_test FAIL, or believability < 80,
                   or (weaknesses present AND accuracy < 85)
     REVIEW      — weaknesses present but accuracy >= 85 (strong content,
                   human judgment call rather than an automated rewrite)
7. Write outputs.

Usage:
  python cluster_bullet_bank.py

Note: Embeddings are cached in bullet_vectors_ge2_d768_cluster.npy so you
can re-run the clustering step without re-embedding. Delete the .npy file
to force a fresh embed pass. If interrupted mid-embedding (rate limit,
Ctrl-C), progress is checkpointed after every batch of 20 --
re-running this script resumes from where it left off instead of
starting over.
"""

import os
import json
import sys
import time
import numpy as np
import pandas as pd
import requests
from dotenv import load_dotenv

# ---------------------------------------------------------------------------
# PATHS
# ---------------------------------------------------------------------------
SCRIPT_DIR   = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(SCRIPT_DIR)

if SCRIPT_DIR not in sys.path:
    sys.path.insert(0, SCRIPT_DIR)
import profile_paths  # noqa: E402

KB_DIR       = profile_paths.kb_dir()

load_dotenv(os.path.join(PROJECT_ROOT, ".env"), override=True)

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
SIMILARITY_THRESHOLD = 0.92   # cosine >= this => same cluster
EMBED_MODEL          = "gemini-embedding-2"
EMBED_DIM            = 768    # gemini-embedding-2 native dimension
BATCH_SIZE           = 20     # batchEmbedContents supports up to ~20 requests per call
EMBED_SLEEP          = 20     # seconds between batch calls -- matches embed_bullet_bank.py's proven interval
MAX_RETRIES          = 4

API_KEY = os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
BASE_URL = "https://generativelanguage.googleapis.com/v1beta/models"
AUTH_HEADERS = {"x-goog-api-key": API_KEY}

# ---------------------------------------------------------------------------
# EMBEDDING
# ---------------------------------------------------------------------------

def embed_batch(texts: list) -> list:
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


# Same candidate list audit_bullet_bank.py uses, so both scripts agree on
# which column holds the actual bullet text across the various CSV variants
# in this project ("Bullet Point" is what every real file in this repo uses —
# the previous "bullet" in df.columns check never matched it and silently
# fell back to the first column, which is "Role / Company").
BULLET_COL_CANDIDATES = ["bullet", "achievement", "Bullet Point"]


def detect_bullet_col(columns) -> str:
    for c in BULLET_COL_CANDIDATES:
        if c in columns:
            return c
    raise ValueError(f"No known bullet column found. Columns: {list(columns)}")


def elect_representative(group: pd.DataFrame, bullet_col: str) -> int:
    """
    Choose the representative bullet within a cluster: highest accuracy_score
    if any member of the cluster has one, otherwise the longest bullet text
    after stripping leading `- ` or `* `.
    Returns the index of the elected row.
    """
    if "accuracy_score" in group.columns and group["accuracy_score"].notna().any():
        return group["accuracy_score"].idxmax()
    lengths = group[bullet_col].str.strip().str.lstrip("-* ").str.len()
    return lengths.idxmax()


# ---------------------------------------------------------------------------
# AUDIT SCORE JOIN + NEXT-ACTION DECISION
# ---------------------------------------------------------------------------

def normalize_bullet_text(text: str) -> str:
    """Canonical join key: strip + lowercase so whitespace/casing don't break the match."""
    return str(text).strip().lower()


def normalize_manager_test(value) -> str:
    """
    manager_test has shown up in two formats across audit runs: a PASS/FAIL
    string, or (from an older scoring version) a bare numeric score where any
    number meant a pass. Normalize both into a consistent PASS/FAIL/"" here,
    once, so decide_action() never has to special-case either format.
    """
    if pd.isna(value):
        return ""
    s = str(value).strip().upper()
    if s in ("PASS", "FAIL"):
        return s
    try:
        float(s)
        return "PASS"  # old format: any numeric score meant a pass
    except ValueError:
        return ""


def decide_action(row) -> str:
    """
    KEEP        — manager_test PASS, believability >= 80, no weaknesses
    REWRITE     — manager_test FAIL, or believability < 80,
                  or (weaknesses present AND accuracy < 85)
    REVIEW      — weaknesses present but accuracy >= 85 (strong underlying
                  content, phrasing/framing flagged — human call, not an
                  automated rewrite that might make it worse)
    NEEDS_AUDIT — no accuracy_score and no believability_score at all
    """
    accuracy = row.get("accuracy_score")
    believability = row.get("believability_score")
    manager_test = row.get("manager_test_normalized")
    weaknesses = row.get("weaknesses")
    has_weaknesses = isinstance(weaknesses, str) and weaknesses.strip() != ""

    if pd.isna(accuracy) and pd.isna(believability):
        return "NEEDS_AUDIT"

    believability = believability if not pd.isna(believability) else 0
    accuracy = accuracy if not pd.isna(accuracy) else 0

    if manager_test == "FAIL" or believability < 80 or (has_weaknesses and accuracy < 85):
        return "REWRITE"
    if has_weaknesses and accuracy >= 85:
        return "REVIEW"
    return "KEEP"


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

    if not os.path.exists(AUDITED_CSV):
        print(f"  ERROR: {AUDITED_CSV} not found.")
        print("  Run audit_bullet_bank.py first to score every bullet — this")
        print("  script needs those scores to assign next_action.")
        return

    df = pd.read_csv(RAW_CSV)
    print(f"  Loaded {len(df)} bullets from {RAW_CSV}")

    bullet_col = detect_bullet_col(df.columns)
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

    # --- JOIN AUDIT SCORES ---
    audited = pd.read_csv(AUDITED_CSV)
    audited_bullet_col = detect_bullet_col(audited.columns)
    audited["_join_key"] = audited[audited_bullet_col].map(normalize_bullet_text)
    audited = audited.drop_duplicates(subset="_join_key", keep="first")
    score_cols_present = [c for c in AUDIT_SCORE_COLS if c in audited.columns]

    df["_join_key"] = df[bullet_col].map(normalize_bullet_text)
    df = df.merge(
        audited[["_join_key"] + score_cols_present],
        on="_join_key", how="left",
    )
    df = df.drop(columns=["_join_key"])
    df["manager_test_normalized"] = df.get("manager_test").map(normalize_manager_test) \
        if "manager_test" in df.columns else ""
    n_pass = (df["manager_test_normalized"] == "PASS").sum()
    n_fail = (df["manager_test_normalized"] == "FAIL").sum()
    print(f"  Audit join: manager_test normalized: {n_pass} PASS / {n_fail} FAIL")

    # --- ELECT REPRESENTATIVES ---
    rep_indices = set()
    for cid, group in df.groupby("cluster_id"):
        rep_idx = elect_representative(group, bullet_col)
        rep_indices.add(rep_idx)

    df["is_representative"] = df.index.isin(rep_indices)

    # --- DECIDE NEXT ACTION ---
    df["next_action"] = df.apply(decide_action, axis=1)
    df = df.drop(columns=["manager_test_normalized"])

    # --- STATS ---
    n_clusters   = df["cluster_id"].nunique()
    n_singletons = (df["cluster_size"] == 1).sum()
    n_dupes      = len(df) - df["is_representative"].sum()
    print(f"  Clusters: {n_clusters}  |  Singletons: {n_singletons}  |  Non-representative: {n_dupes}")
    print(f"  next_action breakdown:\n{df['next_action'].value_counts().to_string()}")

    # --- WRITE CLUSTER MAP CSV (rewrite_bullets.py's CLUSTER_MAP_IN) ---
    front_cols = ["cluster_id", "cluster_size", "is_representative", "next_action", bullet_col]
    other_cols = [c for c in df.columns if c not in front_cols]
    df = df[front_cols + other_cols]
    df.to_csv(CLUSTER_MAP_CSV, index=False)
    print(f"  Wrote {len(df)} rows to {CLUSTER_MAP_CSV}")

    # --- WRITE CLUSTER MAP JSON (human-readable summary) ---
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
