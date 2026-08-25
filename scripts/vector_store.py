"""
vector_store.py — Local embedded vector RAG search module.

Provides vectorized cosine similarity search over bullet bank achievements and
job posting embeddings using numpy and gemini-embedding-2 vectors.
"""

import json
import os
import sys

import numpy as np

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
if SCRIPT_DIR not in sys.path:
    sys.path.insert(0, SCRIPT_DIR)

import profile_paths
from bullet_bank_hash import bullets_sha
from gemini_client import GeminiClient


def cosine_similarity_matrix(query_vec: np.ndarray, matrix: np.ndarray) -> np.ndarray:
    """Computes cosine similarity between 1D query_vec and 2D matrix of embeddings."""
    q_norm = np.linalg.norm(query_vec)
    if q_norm == 0:
        return np.zeros(len(matrix), dtype=np.float32)

    m_norms = np.linalg.norm(matrix, axis=1)
    m_norms[m_norms == 0] = 1.0

    dot_products = np.dot(matrix, query_vec)
    return dot_products / (m_norms * q_norm)


def needs_reembed(profile: str = None) -> tuple[bool, str]:
    """Inspects the vector store without blocking or mutating state.

    Returns (is_stale: bool, reason: str).
    """
    kb_dir = profile_paths.kb_dir(profile)
    csv_path = os.path.join(kb_dir, "bullet-bank-keepers-audited.csv")
    npy_path = os.path.join(kb_dir, "bullet_vectors_ge2_d768.npy")
    meta_path = os.path.join(kb_dir, "bullet_vectors_ge2_d768.meta")

    if not os.path.exists(csv_path):
        return False, "No bullet bank CSV found"
    if not os.path.exists(npy_path):
        return True, "Embeddings file (.npy) missing"

    try:
        import pandas as pd

        df = pd.read_csv(csv_path)
        embs = np.load(npy_path)
    except Exception as e:
        return True, f"Failed to load CSV or embeddings: {e}"

    if "Bullet Point" not in df.columns:
        return False, "CSV missing 'Bullet Point' column"

    if len(df) != len(embs):
        return (
            True,
            f"Row count mismatch: CSV has {len(df)} rows, .npy has {len(embs)} vectors",
        )

    if os.path.exists(meta_path):
        try:
            with open(meta_path, "r", encoding="utf-8") as f:
                meta = json.load(f)
            current_sha = bullets_sha(df["Bullet Point"].fillna("").tolist())
            if meta.get("bullets_sha") != current_sha:
                return True, "Content hash mismatch (bullets edited)"
        except Exception as e:
            return True, f"Failed to read metadata sidecar: {e}"

    return False, "Embeddings are up to date"


def reembed(blocking: bool = True, profile: str = None):
    """Triggers bullet bank re-embedding.

    When blocking=True, executes synchronously.
    When blocking=False, spawns a background daemon thread and returns it.
    """
    import embed_bullet_bank

    if blocking:
        embed_bullet_bank.main()
        return None

    import threading

    t = threading.Thread(
        target=embed_bullet_bank.main,
        name="bullet_bank_reembed",
        daemon=True,
    )
    t.start()
    return t


def _ensure_embeddings_fresh(
    df, embs: np.ndarray, npy_path: str, meta_path: str
) -> tuple[np.ndarray | None, bool]:
    """Ensures embeddings match df row count and hash.

    Auto-reembedding is synchronous by design when called from search_bullet_bank()
    because cosine similarity ranking strictly requires the vector matrix to match
    the current bullet corpus before returning search results.
    """
    stale = False
    if len(df) != len(embs):
        stale = True
    elif os.path.exists(meta_path):
        try:
            with open(meta_path, "r", encoding="utf-8") as f:
                meta = json.load(f)
            current_sha = bullets_sha(df["Bullet Point"].fillna("").tolist())
            if meta.get("bullets_sha") != current_sha:
                stale = True
        except Exception:
            pass

    if not stale:
        return embs, True

    try:
        import embed_bullet_bank

        embed_bullet_bank.main()
        new_embs = np.load(npy_path)
        if len(df) == len(new_embs):
            return new_embs, True
    except Exception as e:
        print(
            f"Warning: vector auto-reembedding failed ({e}); falling back to keyword search."
        )

    return None, False


def search_bullet_bank(
    jd_text: str, top_k: int = 20
) -> list[tuple[str, str, str, float]]:
    """
    RAG search over bullet bank using gemini-embedding-2.
    Returns list of tuples: (bullet_text, role_company, tags, similarity_score)

    Note on blocking re-embedding: If the bullet bank CSV has changed on disk,
    this function triggers a synchronous re-embed before computing cosine scores.
    This is intentional: vector similarity search cannot produce accurate ranking
    without the updated embeddings matrix.
    """
    kb_dir = profile_paths.kb_dir()
    csv_path = os.path.join(kb_dir, "bullet-bank-keepers-audited.csv")
    npy_path = os.path.join(kb_dir, "bullet_vectors_ge2_d768.npy")
    meta_path = os.path.join(kb_dir, "bullet_vectors_ge2_d768.meta")

    if not os.path.exists(csv_path) or not os.path.exists(npy_path):
        return []

    try:
        import pandas as pd

        df = pd.read_csv(csv_path)
        embs = np.load(npy_path)
    except Exception:
        return []

    if "Bullet Point" not in df.columns:
        return []

    embs, ok = _ensure_embeddings_fresh(df, embs, npy_path, meta_path)
    if not ok or embs is None:
        return []

    jd_emb = GeminiClient.embed(jd_text[:8000])
    if jd_emb is None:
        return []

    jd_vec = np.array(jd_emb, dtype=np.float32)
    scores = cosine_similarity_matrix(jd_vec, embs)
    top_indices = np.argsort(scores)[::-1][:top_k]

    results = []
    bullets = df["Bullet Point"].fillna("").tolist()
    companies = (
        df["Role / Company"].fillna("").tolist()
        if "Role / Company" in df.columns
        else [""] * len(df)
    )
    tags = df["Tags"].fillna("").tolist() if "Tags" in df.columns else [""] * len(df)

    for idx in top_indices:
        results.append((bullets[idx], companies[idx], tags[idx], float(scores[idx])))

    return results
