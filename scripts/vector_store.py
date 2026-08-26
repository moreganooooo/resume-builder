"""
vector_store.py — Local embedded vector RAG search module.

Provides vectorized cosine similarity search over bullet bank achievements and
job posting embeddings using numpy and gemini-embedding-2 vectors.
"""

import json
import os
import re
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
    jd_text: str, top_k: int = 20, profile: str = None
) -> list[tuple[str, str, str, float]]:
    """
    RAG search over bullet bank using gemini-embedding-2.
    Returns list of tuples: (bullet_text, role_company, tags, similarity_score)

    Note on blocking re-embedding: If the bullet bank CSV has changed on disk,
    this function triggers a synchronous re-embed before computing cosine scores.
    This is intentional: vector similarity search cannot produce accurate ranking
    without the updated embeddings matrix.
    """
    kb_dir = profile_paths.kb_dir(profile)
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
    bullets = df["Bullet Point"].fillna("").tolist()
    companies = (
        df["Role / Company"].fillna("").tolist()
        if "Role / Company" in df.columns
        else [""] * len(df)
    )
    tags = df["Tags"].fillna("").tolist() if "Tags" in df.columns else [""] * len(df)

    if jd_emb is None:
        # Lexical fallback when offline / no embedding
        query_words = set(re.findall(r"\w+", jd_text.lower()))
        if not query_words:
            return []
        scored = []
        for i, b in enumerate(bullets):
            b_words = set(re.findall(r"\w+", b.lower()))
            overlap = len(query_words & b_words)
            if overlap > 0:
                score = overlap / max(len(query_words), 1)
                scored.append((b, companies[i], tags[i], float(score)))
        scored.sort(key=lambda x: x[3], reverse=True)
        return scored[:top_k]

    jd_vec = np.array(jd_emb, dtype=np.float32)
    scores = cosine_similarity_matrix(jd_vec, embs)
    top_indices = np.argsort(scores)[::-1][:top_k]

    results = []
    for idx in top_indices:
        results.append((bullets[idx], companies[idx], tags[idx], float(scores[idx])))

    return results


def search_evidence_guide(
    query: str, top_k: int = 5, profile: str = None
) -> list[dict]:
    """
    RAG search over evidence-guide.csv thematic career-proof clusters.
    Returns list of dicts with cluster metadata and similarity score.
    """
    kb_dir = profile_paths.kb_dir(profile)
    csv_path = os.path.join(kb_dir, "evidence-guide.csv")
    if not os.path.exists(csv_path):
        return []

    try:
        import csv

        with open(csv_path, "r", encoding="utf-8") as f:
            reader = list(csv.DictReader(f))
    except Exception:
        return []

    if not reader:
        return []

    query_vec = None
    query_emb = GeminiClient.embed(query[:4000])
    if query_emb is not None:
        query_vec = np.array(query_emb, dtype=np.float32)

    results = []
    query_words = set(re.findall(r"\w+", query.lower()))

    for row in reader:
        cluster = row.get("Evidence Cluster", "")
        finding = row.get("Finding", "")
        quote = row.get("Best Detail / Quote", "")
        metric = row.get("Best Metric", "")
        proves = row.get("What This Proves About Morgan", "")
        where = row.get("Where to Use It", "")
        confidence = row.get("Confidence", "Medium")

        full_text = f"{cluster} {finding} {quote} {metric} {proves} {where}".lower()

        # Score calculation
        score = 0.0
        if query_words:
            text_words = set(re.findall(r"\w+", full_text))
            overlap = len(query_words & text_words)
            if overlap > 0:
                score = overlap / max(len(query_words), 1)
                # Boost if cluster name matches
                for qw in query_words:
                    if len(qw) > 3 and qw in cluster.lower():
                        score += 0.25

        results.append(
            {
                "cluster": cluster,
                "finding": finding,
                "quote": quote,
                "metric": metric,
                "proves": proves,
                "where": where,
                "confidence": confidence,
                "score": float(score),
            }
        )

    results.sort(key=lambda x: x["score"], reverse=True)
    return results[:top_k]


def search_behavioral_stories(
    query: str, top_k: int = 3, profile: str = None
) -> list[dict]:
    """RAG search across STAR/CAR behavioral stories."""
    import evidence_bank

    stories = evidence_bank.load_behavioral_stories(profile=profile)
    filtered = evidence_bank.filter_stories(stories, query=query)
    return [evidence_bank._dump_model(s) for s in filtered[:top_k]]


def search_negotiation_levers(
    query: str, top_k: int = 3, profile: str = None
) -> list[dict]:
    """RAG search across negotiation levers."""
    import evidence_bank

    levers = evidence_bank.load_negotiation_levers(profile=profile)
    filtered = evidence_bank.filter_negotiation_levers(levers, query=query)
    return [evidence_bank._dump_model(l) for l in filtered[:top_k]]


def chunk_text(text: str, chunk_size: int = 500, overlap: int = 75) -> list[str]:
    """Splits text into sliding window semantic chunks respecting paragraph/sentence breaks."""
    if not text or not text.strip():
        return []

    paras = [p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()]
    chunks = []
    current_chunk = ""

    for p in paras:
        if len(current_chunk) + len(p) + 2 <= chunk_size:
            current_chunk = f"{current_chunk}\n\n{p}".strip()
        else:
            if current_chunk:
                chunks.append(current_chunk)
            if len(p) > chunk_size:
                # Split large paragraphs by sentences
                sentences = re.split(r"(?<=[.!?])\s+", p)
                sub_chunk = ""
                for s in sentences:
                    if len(sub_chunk) + len(s) + 1 <= chunk_size:
                        sub_chunk = f"{sub_chunk} {s}".strip()
                    else:
                        if sub_chunk:
                            chunks.append(sub_chunk)
                        sub_chunk = s
                if sub_chunk:
                    current_chunk = sub_chunk
                else:
                    current_chunk = ""
            else:
                current_chunk = p

    if current_chunk:
        chunks.append(current_chunk)

    return chunks


def index_knowledge_documents(profile: str = None) -> int:
    """Chunks and embeds markdown/text knowledge base documents in the active profile."""
    kb_dir = profile_paths.kb_dir(profile)
    chunks_meta_path = os.path.join(kb_dir, "doc_chunks_ge2.json")
    chunks_npy_path = os.path.join(kb_dir, "doc_chunks_ge2.npy")

    allowed_exts = {".md", ".txt"}
    all_chunks: list[dict] = []

    for root, _, files in os.walk(kb_dir):
        for f in files:
            if any(f.endswith(ext) for ext in allowed_exts):
                if f.startswith(".") or "audit" in f.lower():
                    continue
                file_path = os.path.join(root, f)
                rel_path = os.path.relpath(file_path, kb_dir)
                try:
                    with open(file_path, "r", encoding="utf-8") as fh:
                        content = fh.read()
                    doc_chunks = chunk_text(content)
                    for i, ch in enumerate(doc_chunks):
                        all_chunks.append(
                            {
                                "source_file": rel_path,
                                "chunk_id": i,
                                "text": ch,
                            }
                        )
                except Exception:
                    continue

    if not all_chunks:
        return 0

    with open(chunks_meta_path, "w", encoding="utf-8") as fh:
        json.dump(all_chunks, fh, indent=2, ensure_ascii=False)

    texts = [c["text"] for c in all_chunks]
    embs_list = []
    for t in texts:
        emb = GeminiClient.embed(t[:2000])
        if emb is not None:
            embs_list.append(emb)
        else:
            embs_list.append([0.0] * 768)

    embs_arr = np.array(embs_list, dtype=np.float32)
    np.save(chunks_npy_path, embs_arr)
    return len(all_chunks)


def search_document_chunks(
    query: str, top_k: int = 5, profile: str = None
) -> list[dict]:
    """Semantic vector RAG search across indexed knowledge base document chunks."""
    kb_dir = profile_paths.kb_dir(profile)
    chunks_meta_path = os.path.join(kb_dir, "doc_chunks_ge2.json")
    chunks_npy_path = os.path.join(kb_dir, "doc_chunks_ge2.npy")

    if not os.path.exists(chunks_meta_path):
        # Fallback to indexing on the fly or lexical scan
        index_knowledge_documents(profile)

    if not os.path.exists(chunks_meta_path):
        return []

    try:
        with open(chunks_meta_path, "r", encoding="utf-8") as fh:
            chunks = json.load(fh)
    except Exception:
        return []

    if not chunks:
        return []

    query_emb = GeminiClient.embed(query[:2000])

    if query_emb is not None and os.path.exists(chunks_npy_path):
        try:
            matrix = np.load(chunks_npy_path)
            if len(matrix) == len(chunks):
                query_vec = np.array(query_emb, dtype=np.float32)
                scores = cosine_similarity_matrix(query_vec, matrix)
                top_indices = np.argsort(scores)[::-1][:top_k]
                results = []
                for idx in top_indices:
                    item = dict(chunks[idx])
                    item["score"] = float(scores[idx])
                    results.append(item)
                return results
        except Exception:
            pass

    # Lexical fallback
    query_words = set(re.findall(r"\w+", query.lower()))
    scored = []
    for ch in chunks:
        ch_words = set(re.findall(r"\w+", ch["text"].lower()))
        overlap = len(query_words & ch_words)
        score = overlap / max(len(query_words), 1) if query_words else 0.0
        if score > 0:
            item = dict(ch)
            item["score"] = float(score)
            scored.append(item)
    scored.sort(key=lambda x: x["score"], reverse=True)
    return scored[:top_k]


def query_rag(
    query: str,
    top_k_bullets: int = 10,
    top_k_evidence: int = 5,
    top_k_stories: int = 3,
    top_k_negotiation: int = 3,
    top_k_chunks: int = 5,
    profile: str = None,
) -> dict:
    """
    Unified RAG retrieval query across Bullet Bank, Evidence Guide, STAR Stories, Negotiation Levers, and Document Chunks.
    """
    bullets = search_bullet_bank(query, top_k=top_k_bullets, profile=profile)
    evidence = search_evidence_guide(query, top_k=top_k_evidence, profile=profile)
    stories = search_behavioral_stories(query, top_k=top_k_stories, profile=profile)
    negotiation = search_negotiation_levers(
        query, top_k=top_k_negotiation, profile=profile
    )
    doc_chunks = search_document_chunks(query, top_k=top_k_chunks, profile=profile)

    return {
        "query": query,
        "bullets": bullets,
        "evidence": evidence,
        "stories": stories,
        "negotiation": negotiation,
        "doc_chunks": doc_chunks,
    }
