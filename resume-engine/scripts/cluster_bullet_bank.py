#!/usr/bin/env python3
"""
cluster_bullet_bank.py

Groups near-duplicate bullets in bullet-bank-clean.csv using TF-IDF + cosine
similarity, then joins audit scores from bullet-bank-audited.csv so every
output row has cluster info AND scores in one place.

Usage:
  python cluster_bullet_bank.py                   # uses defaults
  python cluster_bullet_bank.py --threshold 0.88  # stricter grouping
  python cluster_bullet_bank.py --report-only     # preview clusters, no files written

Outputs (all written to resume-engine/knowledge_base/):
  bullet-bank-deduplicated.csv   — one rep per cluster + audit scores, feed to rewrite script
  bullet-bank-cluster-map.csv    — every bullet mapped to its cluster + audit scores
"""

import argparse
import os
import pandas as pd
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

# --- PATH RESOLUTION ---
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(os.path.dirname(SCRIPT_DIR))
KB_DIR = os.path.join(PROJECT_ROOT, "resume-engine", "knowledge_base")

DEFAULT_INPUT      = os.path.join(KB_DIR, "bullet-bank-clean.csv")
DEFAULT_AUDIT      = os.path.join(KB_DIR, "bullet-bank-audited.csv")
DEFAULT_DEDUP_OUT  = os.path.join(KB_DIR, "bullet-bank-deduplicated.csv")
DEFAULT_MAP_OUT    = os.path.join(KB_DIR, "bullet-bank-cluster-map.csv")

# Column that holds bullet text in bullet-bank-clean.csv
BULLET_COL = "Bullet Point"
FALLBACK_COLS = ["bullet", "achievement", "text", "Bullet", "Achievement"]

# Column that holds bullet text in bullet-bank-audited.csv
AUDIT_BULLET_COL = "Bullet Point"

# Audit score columns to pull in
AUDIT_COLS = [
    "Role / Company",
    "Tags",
    "accuracy_score",
    "believability_score",
    "clarity_score",
    "ats_value",
    "manager_test",
    "weaknesses",
]

DEFAULT_THRESHOLD = 0.75


# ---------------------------------------------------------------------------
# HELPERS
# ---------------------------------------------------------------------------

def detect_col(df: pd.DataFrame, preferred: str, fallbacks: list) -> str:
    if preferred in df.columns:
        return preferred
    for col in fallbacks:
        if col in df.columns:
            print(f"  ⚠️  '{preferred}' not found — using '{col}' instead.")
            return col
    raise ValueError(
        f"Could not find bullet text column. Columns available: {df.columns.tolist()}"
    )


def load_audit(audit_path: str) -> pd.DataFrame | None:
    """Load audit CSV. Returns None (with a warning) if file doesn't exist yet."""
    if not os.path.exists(audit_path):
        print(f"  ⚠️  Audit file not found at {audit_path} — skipping score join.")
        print(f"      Run the audit script first, then re-run this to get the unified report.")
        return None
    df = pd.read_csv(audit_path)
    print(f"  ✅ Audit file loaded: {len(df)} scored bullets.")
    return df


def join_audit_scores(df_main: pd.DataFrame, df_audit: pd.DataFrame,
                      main_col: str) -> pd.DataFrame:
    """
    Left-join audit scores onto the main bullet dataframe.
    Matches on normalised bullet text (stripped, lowercased) to handle
    minor whitespace differences between the two CSVs.
    """
    present_audit_cols = [c for c in AUDIT_COLS if c in df_audit.columns]
    missing = [c for c in AUDIT_COLS if c not in df_audit.columns]
    if missing:
        print(f"  ⚠️  Audit columns not found (will be blank): {missing}")

    # Normalise join keys
    df_main = df_main.copy()
    df_main["_join_key"] = df_main[main_col].fillna("").str.strip().str.lower()

    df_audit = df_audit.copy()
    df_audit["_join_key"] = df_audit[AUDIT_BULLET_COL].fillna("").str.strip().str.lower()

    cols_to_merge = ["_join_key"] + present_audit_cols
    df_merged = df_main.merge(
        df_audit[cols_to_merge].drop_duplicates(subset="_join_key"),
        on="_join_key",
        how="left"
    ).drop(columns=["_join_key"])

    matched = df_merged["accuracy_score"].notna().sum() if "accuracy_score" in df_merged.columns else "?"
    print(f"  🔗 Audit scores joined: {matched}/{len(df_main)} bullets matched.")
    return df_merged


def cluster_bullets(bullets: list, threshold: float):
    print(f"  🔢 Vectorizing {len(bullets)} bullets with TF-IDF (ngrams 1–2)...")
    vectorizer = TfidfVectorizer(ngram_range=(1, 2), stop_words="english", min_df=1)
    matrix = vectorizer.fit_transform(bullets)

    print(f"  🔗 Computing pairwise cosine similarity...")
    sim_matrix = cosine_similarity(matrix)

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
    Priority order for picking the cluster rep:
    1. Highest accuracy_score from audit (if available)
    2. hidden_gem_score (if available)
    3. Longest bullet text (most specific)
    """
    if "accuracy_score" in df.columns:
        scored = [(i, pd.to_numeric(df.iloc[i].get("accuracy_score", 0), errors="coerce") or 0)
                  for i in cluster]
        best = max(scored, key=lambda x: (x[1], len(bullets[x[0]])))
        return best[0]
    if "hidden_gem_score" in df.columns:
        scored = [(i, pd.to_numeric(df.iloc[i].get("hidden_gem_score", 0), errors="coerce") or 0)
                  for i in cluster]
        best = max(scored, key=lambda x: (x[1], len(bullets[x[0]])))
        return best[0]
    return max(cluster, key=lambda i: len(bullets[i]))


def print_cluster_preview(clusters: list, bullets: list, df: pd.DataFrame,
                          top_n: int = 10) -> None:
    multi = sorted(
        [(i, c) for i, c in enumerate(clusters) if len(c) > 1],
        key=lambda x: len(x[1]), reverse=True
    )
    has_scores = "accuracy_score" in df.columns

    print(f"\n🔍 Cluster preview (top {min(top_n, len(multi))} largest groups):\n")
    for cluster_id, members in multi[:top_n]:
        print(f"  Cluster {cluster_id} — {len(members)} bullets:")
        for idx in members:
            preview = bullets[idx][:95] + ("..." if len(bullets[idx]) > 95 else "")
            score_str = ""
            if has_scores:
                acc = df.iloc[idx].get("accuracy_score", "")
                mgr = df.iloc[idx].get("manager_test", "")
                score_str = f" [acc={acc} mgr={mgr}]"
            print(f"    • [{idx}]{score_str} {preview}")
        print()


def decide_action(row: pd.Series) -> str:
    """
    Compute a recommended next action for each rep bullet based on audit scores.
    This becomes the 'next_action' column in the output — your single decision point.
    """
    mgr = str(row.get("manager_test", "")).strip().upper()
    believability = pd.to_numeric(row.get("believability_score", None), errors="coerce")
    accuracy = pd.to_numeric(row.get("accuracy_score", None), errors="coerce")
    weaknesses = str(row.get("weaknesses", "")).strip()

    # Not yet audited — no scores present
    if pd.isna(accuracy) and pd.isna(believability):
        return "NEEDS_AUDIT"

    # Failed manager test or low believability — send to rewrite
    if mgr == "FAIL" or (believability is not None and believability < 80):
        return "REWRITE"

    # Borderline — has weaknesses noted but not a hard fail
    if weaknesses and weaknesses.lower() not in ("", "none", "nan", "n/a"):
        if accuracy is not None and accuracy >= 85:
            return "REVIEW"   # good score but has noted weaknesses — human call
        return "REWRITE"

    # Passing bullet
    return "KEEP"


# ---------------------------------------------------------------------------
# MAIN
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="Cluster + deduplicate bullets, joined with audit scores."
    )
    parser.add_argument("--input",     default=DEFAULT_INPUT,     help="Path to bullet-bank-clean.csv")
    parser.add_argument("--audit",     default=DEFAULT_AUDIT,     help="Path to bullet-bank-audited.csv")
    parser.add_argument("--output",    default=DEFAULT_DEDUP_OUT, help="Path for deduplicated output CSV")
    parser.add_argument("--map",       default=DEFAULT_MAP_OUT,   help="Path for full cluster map CSV")
    parser.add_argument("--threshold", type=float, default=DEFAULT_THRESHOLD,
                        help="Cosine similarity threshold (default 0.75). Higher = stricter.")
    parser.add_argument("--report-only", action="store_true",
                        help="Print preview without writing files.")
    args = parser.parse_args()

    print(f"\n📥 Loading bullet bank: {args.input}")
    df = pd.read_csv(args.input)
    bullet_col = detect_col(df, BULLET_COL, FALLBACK_COLS)
    bullets = df[bullet_col].fillna("").tolist()
    print(f"  ✅ {len(bullets)} bullets loaded.")
    print(f"  🎯 Similarity threshold: {args.threshold}")

    # Join audit scores before clustering so rep-picker can use them
    df_audit = load_audit(args.audit)
    if df_audit is not None:
        df = join_audit_scores(df, df_audit, bullet_col)

    assigned, clusters = cluster_bullets(bullets, args.threshold)
    rep_indices = [pick_representative(c, bullets, df) for c in clusters]

    n_original  = len(bullets)
    n_clusters  = len(clusters)
    n_saved     = n_original - n_clusters
    multi_count = sum(1 for c in clusters if len(c) > 1)

    print(f"\n✨ Results:")
    print(f"   {n_original} bullets  →  {n_clusters} clusters")
    print(f"   {n_saved} redundant rewrite calls eliminated")
    print(f"   {multi_count} clusters contain 2+ near-duplicate bullets")

    print_cluster_preview(clusters, bullets, df)

    if args.report_only:
        print("🔍 Report-only mode — no files written.")
        return

    # --- DEDUPLICATED OUTPUT (reps only) ---
    df_dedup = df.iloc[rep_indices].copy()
    df_dedup.insert(0, "cluster_id",   [assigned[i]              for i in rep_indices])
    df_dedup.insert(1, "cluster_size", [len(clusters[assigned[i]]) for i in rep_indices])
    df_dedup["next_action"] = df_dedup.apply(decide_action, axis=1)

    # Reorder: decision columns first, then bullet, then scores, then weaknesses
    score_cols  = [c for c in ["accuracy_score", "believability_score",
                               "clarity_score", "ats_value", "manager_test"] if c in df_dedup.columns]
    other_cols  = [c for c in df_dedup.columns
                   if c not in ["cluster_id", "cluster_size", "next_action",
                                bullet_col, "weaknesses"] + score_cols]
    col_order   = (["cluster_id", "cluster_size", "next_action", bullet_col]
                   + score_cols + ["weaknesses"] + other_cols)
    col_order   = [c for c in col_order if c in df_dedup.columns]  # safety filter
    df_dedup    = df_dedup[col_order]

    df_dedup.to_csv(args.output, index=False)
    print(f"\n✅ Deduplicated report saved: {args.output}")

    action_counts = df_dedup["next_action"].value_counts().to_dict()
    print(f"   next_action breakdown:")
    for action, count in sorted(action_counts.items()):
        print(f"     {action:<15} {count}")

    # --- FULL CLUSTER MAP ---
    df["cluster_id"]       = assigned
    df["cluster_size"]     = [len(clusters[cid]) for cid in assigned]
    df["is_representative"] = [i in set(rep_indices) for i in range(len(bullets))]
    map_cols  = (["cluster_id", "cluster_size", "is_representative", bullet_col]
                 + [c for c in score_cols + ["weaknesses"] if c in df.columns])
    df_map    = df[map_cols].sort_values(["cluster_id", "is_representative"],
                                         ascending=[True, False])
    df_map.to_csv(args.map, index=False)
    print(f"📋 Full cluster map saved: {args.map}\n")


if __name__ == "__main__":
    main()
