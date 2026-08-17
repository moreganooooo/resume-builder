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
from gemini_client import GeminiClient
from bullet_bank_hash import bullets_sha


def cosine_similarity_matrix(query_vec: np.ndarray, matrix: np.ndarray) -> np.ndarray:
    """Computes cosine similarity between 1D query_vec and 2D matrix of embeddings."""
    q_norm = np.linalg.norm(query_vec)
    if q_norm == 0:
        return np.zeros(len(matrix), dtype=np.float32)
    
    m_norms = np.linalg.norm(matrix, axis=1)
    m_norms[m_norms == 0] = 1.0
    
    dot_products = np.dot(matrix, query_vec)
    return dot_products / (m_norms * q_norm)


def search_bullet_bank(jd_text: str, top_k: int = 20) -> list[tuple[str, str, str, float]]:
    """
    RAG search over bullet bank using gemini-embedding-2.
    Returns list of tuples: (bullet_text, role_company, tags, similarity_score)
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

    if len(df) != len(embs):
        # Row count changed (bullet added/removed) -- re-embed instead of
        # bailing out silently. Same recovery path as the content-hash
        # mismatch below; this was previously unreachable because this
        # length check returned early before ever getting there, so
        # adding/removing a bullet permanently broke vector search until
        # someone manually reran embed_bullet_bank.py.
        try:
            import embed_bullet_bank
            embed_bullet_bank.main()
            embs = np.load(npy_path)
            if len(df) != len(embs):
                return []
        except Exception as e:
            print(f"Warning: vector auto-reembedding failed ({e}); falling back to keyword search.")
            return []

    if os.path.exists(meta_path):
        try:
            with open(meta_path, "r", encoding="utf-8") as f:
                meta = json.load(f)
            current_sha = bullets_sha(df["Bullet Point"].fillna("").tolist())
            if meta.get("bullets_sha") != current_sha:
                try:
                    import embed_bullet_bank
                    embed_bullet_bank.main()
                    embs = np.load(npy_path)
                except Exception as e:
                    print(f"Warning: vector auto-reembedding failed ({e}); falling back to keyword search.")
                    return []
        except Exception:
            pass

    jd_emb = GeminiClient.embed(jd_text[:8000])
    if jd_emb is None:
        return []

    jd_vec = np.array(jd_emb, dtype=np.float32)
    scores = cosine_similarity_matrix(jd_vec, embs)
    top_indices = np.argsort(scores)[::-1][:top_k]

    results = []
    bullets = df["Bullet Point"].fillna("").tolist()
    companies = df["Role / Company"].fillna("").tolist() if "Role / Company" in df.columns else [""] * len(df)
    tags = df["Tags"].fillna("").tolist() if "Tags" in df.columns else [""] * len(df)

    for idx in top_indices:
        results.append((bullets[idx], companies[idx], tags[idx], float(scores[idx])))

    return results
