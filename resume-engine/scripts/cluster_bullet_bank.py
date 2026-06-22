#!/usr/bin/env python3
"""
cluster_bullet_bank.py

Groups near-duplicate bullets in bullet-bank-clean.csv using TF-IDF + cosine
similarity. Outputs a deduplicated CSV (one representative per cluster) so you
never send the same bullet through the rewrite loop twice.

Usage:
  python cluster_bullet_bank.py                   # uses defaults
  python cluster_bullet_bank.py --threshold 0.88  # stricter grouping
  python cluster_bullet_bank.py --report-only     # preview clusters, no files written

Outputs:
  bullet-bank-deduplicated.csv   — one rep per cluster, feed this to the rewrite script
  bullet-bank-cluster-map.csv    — full traceability: every bullet mapped to its cluster
"""

import argparse
import os
import pandas as pd
import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

# --- PATH RESOLUTION ---
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(os.path.dirname(SCRIPT_DIR))
KB_DIR = os.path.join(PROJECT_ROOT, "resume-engine", "knowledge_base")
OUTPUT_DIR = os.path.join(PROJECT_ROOT, "resume-engine", "knowledge_base")

DEFAULT_INPUT = os.path.join(KB_DIR, "bullet-bank-clean.csv")
DEFAULT_DEDUP_OUTPUT = os.path.join(OUTPUT_DIR, "bullet-bank-deduplicated.csv")
DEFAULT_MAP_OUTPUT = os.path.join(OUTPUT_DIR, "bullet-bank-cluster-map.csv")

# The column in your CSV that holds bullet text.
# If unsure, run: python -c "import pandas as pd; print(pd.read_csv('bullet-bank-clean.csv').columns.tolist())"
BULLET_COL = "bullet"
FALLBACK_COLS = ["achievement", "text", "Bullet", "Achievement"]

DEFAULT_THRESHOLD = 0.82  # 0.82 = aggressive dedup; 0.88 = conservative


def detect_bullet_col(df: pd.DataFrame) -> str:
    """Auto-detect the bullet text column."""
    if BULLET_COL in df.columns:
        return BULLET_COL
    for col in FALLBACK_COLS:
        if col in df.columns:
            print(f"  ⚠️  '{BULLET_COL}' not found — using '{col}' instead.")
            return col
    raise ValueError(
        f"Could not find a bullet text column. Columns found: {df.columns.tolist()}\n"
        f"Set BULLET_COL at the top of the script to match your CSV."
    )


def cluster_bullets(bullets: list, threshold: float) -> list:
    """
    Greedy agglomerative clustering using TF-IDF cosine similarity.

    Each bullet is assigned to the first existing cluster where the similarity
    to the cluster seed (first member) exceeds the threshold. If no match,
    it starts a new cluster.

    Returns a list of cluster IDs (one per bullet, same order as input).
    """
    print(f"  🔢 Vectorizing {len(bullets)} bullets with TF-IDF (ngrams 1–2)...")
    vectorizer = TfidfVectorizer(ngram_range=(1, 2), stop_words="english", min_df=1)
    matrix = vectorizer.fit_transform(bullets)

    print(f"  🔗 Computing pairwise cosine similarity...")
    sim_matrix = cosine_similarity(matrix)  # (N x N) float32 — fine for ~600 bullets

    assigned = [-1] * len(bullets)
    clusters = []

    for i in range(len(bullets)):
        if assigned[i] != -1:
            continue
        cluster_id = len(clusters)
        clusters.append([i])
        assigned[i] = cluster_id
        for j in range(i + 1, len(bullets)):
            if assigned[j] == -1 and sim_matrix[i][j] >= threshold:
                assigned[j] = cluster_id
                clusters[cluster_id].append(j)

    return assigned, clusters


def pick_representative(cluster: list, bullets: list, df: pd.DataFrame) -> int:
    """
    Pick the best bullet to represent a cluster.

    Priority:
    1. Highest hidden_gem_score (if column exists)
    2. Longest bullet text (most specific/detailed)
    """
    if "hidden_gem_score" in df.columns:
        scored = [
            (i, df.iloc[i].get("hidden_gem_score", 0) or 0)
            for i in cluster
        ]
        best = max(scored, key=lambda x: (x[1], len(bullets[x[0]])))
        return best[0]
    return max(cluster, key=lambda i: len(bullets[i]))


def print_cluster_preview(clusters: list, bullets: list, top_n: int = 10) -> None:
    """Print the largest clusters so you can sanity-check the grouping."""
    multi = [(i, c) for i, c in enumerate(clusters) if len(c) > 1]
    multi_sorted = sorted(multi, key=lambda x: len(x[1]), reverse=True)

    print(f"\n🔍 Cluster preview (top {min(top_n, len(multi_sorted))} largest groups):\n")
    for cluster_id, members in multi_sorted[:top_n]:
        print(f"  Cluster {cluster_id} — {len(members)} bullets:")
        for idx in members:
            preview = bullets[idx][:100] + ("..." if len(bullets[idx]) > 100 else "")
            print(f"    • [{idx}] {preview}")
        print()


def main():
    parser = argparse.ArgumentParser(
        description="Deduplicate bullet-bank-clean.csv by clustering near-duplicate bullets."
    )
    parser.add_argument(
        "--input", default=DEFAULT_INPUT,
        help=f"Path to input CSV (default: {DEFAULT_INPUT})"
    )
    parser.add_argument(
        "--output", default=DEFAULT_DEDUP_OUTPUT,
        help=f"Path for deduplicated output CSV (default: {DEFAULT_DEDUP_OUTPUT})"
    )
    parser.add_argument(
        "--map", default=DEFAULT_MAP_OUTPUT,
        help=f"Path for cluster map CSV (default: {DEFAULT_MAP_OUTPUT})"
    )
    parser.add_argument(
        "--threshold", type=float, default=DEFAULT_THRESHOLD,
        help=f"Cosine similarity threshold for clustering (default: {DEFAULT_THRESHOLD}). "
             f"Higher = stricter (fewer merges). Try 0.82–0.92."
    )
    parser.add_argument(
        "--report-only", action="store_true",
        help="Preview clusters without writing output files."
    )
    args = parser.parse_args()

    print(f"\n📥 Loading: {args.input}")
    df = pd.read_csv(args.input)
    bullet_col = detect_bullet_col(df)
    bullets = df[bullet_col].fillna("").tolist()
    print(f"  ✅ {len(bullets)} bullets loaded.")
    print(f"  🎯 Similarity threshold: {args.threshold}")

    assigned, clusters = cluster_bullets(bullets, args.threshold)

    # Pick one representative per cluster
    rep_indices = [pick_representative(c, bullets, df) for c in clusters]

    # Stats
    n_original = len(bullets)
    n_clusters = len(clusters)
    n_saved = n_original - n_clusters
    multi_member = sum(1 for c in clusters if len(c) > 1)

    print(f"\n✨ Results:")
    print(f"   {n_original} bullets  →  {n_clusters} clusters")
    print(f"   {n_saved} redundant rewrite calls eliminated")
    print(f"   {multi_member} clusters contain 2+ near-duplicate bullets")

    print_cluster_preview(clusters, bullets)

    if args.report_only:
        print("🔍 Report-only mode — no files written.")
        return

    # Write deduplicated CSV (representatives only)
    df_dedup = df.iloc[rep_indices].copy()
    df_dedup["cluster_id"] = [assigned[i] for i in rep_indices]
    df_dedup["cluster_size"] = [len(clusters[assigned[i]]) for i in rep_indices]
    df_dedup.to_csv(args.output, index=False)
    print(f"\n✅ Deduplicated CSV saved: {args.output}")
    print(f"   Feed this into the rewrite script to skip redundant bullets.")

    # Write cluster map (full traceability)
    df["cluster_id"] = assigned
    df["cluster_size"] = [len(clusters[cid]) for cid in assigned]
    df["is_representative"] = [i in rep_indices for i in range(len(bullets))]
    df_map = df[["cluster_id", "cluster_size", "is_representative", bullet_col]].sort_values(
        ["cluster_id", "is_representative"], ascending=[True, False]
    )
    df_map.to_csv(args.map, index=False)
    print(f"📋 Cluster map saved: {args.map}")
    print(f"   Use this to trace which bullets were merged into which cluster.\n")


if __name__ == "__main__":
    main()
