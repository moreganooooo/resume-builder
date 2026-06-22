#!/usr/bin/env python3
"""
cluster_bullet_bank.py

Groups near-duplicate bullets in bullet-bank-clean.csv using TF-IDF + cosine
similarity, then joins ALL columns from bullet-bank-audited.csv so every
output row has cluster info, scores, company, tags, and weaknesses in one place.

Usage:
  python cluster_bullet_bank.py                   # uses defaults
  python cluster_bullet_bank.py --threshold 0.88  # stricter grouping
  python cluster_bullet_bank.py --report-only     # preview clusters, no files written

Outputs (written to resume-engine/knowledge_base/):
  bullet-bank-deduplicated.csv   — one rep per cluster + all audit data, feed to rewrite script
  bullet-bank-cluster-map.csv    — every bullet mapped to its cluster + all audit data
"""

import argparse
import os
import pandas as pd
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

# --- PATH RESOLUTION ---
SCRIPT_DIR   = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(os.path.dirname(SCRIPT_DIR))
KB_DIR       = os.path.join(PROJECT_ROOT, "resume-engine", "knowledge_base")

DEFAULT_INPUT     = os.path.join(KB_DIR, "bullet-bank-clean.csv")
DEFAULT_AUDIT     = os.path.join(KB_DIR, "bullet-bank-audited.csv")
DEFAULT_DEDUP_OUT = os.path.join(KB_DIR, "bullet-bank-deduplicated.csv")
DEFAULT_MAP_OUT   = os.path.join(KB_DIR, "bullet-bank-cluster-map.csv")

# Column that holds bullet text in BOTH CSVs
BULLET_COL    = "Bullet Point"
FALLBACK_COLS = ["bullet", "achievement", "text", "Bullet", "Achievement"]

# Columns that drive scoring logic (used for ordering + decide_action)
SCORE_COLS   = ["accuracy_score", "believability_score", "clarity_score", "ats_value", "manager_test"]
META_COLS    = ["Role / Company", "Tags"]
WEAKNESS_COL = "weaknesses"

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


def load_audit(audit_path: str):
    """Load audit CSV. Returns None with a warning if the file doesn't exist yet."""
    if not os.path.exists(audit_path):
        print(f"  ⚠️  Audit file not found at {audit_path} — skipping score join.")
        print(f"      Run the audit script first, then re-run this to get the unified report.")
        return None
    df = pd.read_csv(audit_path)
    print(f"  ✅ Audit file loaded: {len(df)} scored bullets | {len(df.columns)} columns.")
    print(f"     Columns: {df.columns.tolist()}")
    return df


def normalize_manager_test(value) -> str:
    """
    Normalize manager_test to always return 'PASS' or 'FAIL'.
    Handles both old format (numeric score = pass, 'fail' text = fail)
    and new format ('pass' / 'fail' text).
    """
    if pd.isna(value) or str(value).strip() == "":
        return ""
    raw = str(value).strip().upper()
    if raw == "PASS":
        return "PASS"
    if raw == "FAIL":
        return "FAIL"
    try:
        float(raw)
        return "PASS"  # numeric score in old format = passed
    except ValueError:
        return raw     # unexpected value — pass through as-is


def join_audit_scores(df_main: pd.DataFrame, df_audit: pd.DataFrame,
                      main_col: str) -> pd.DataFrame:
    """
    Left-join ALL columns from the audit CSV onto the main bullet dataframe.
    Matches on normalised bullet text (stripped + lowercased).
    Defensively drops any stale '_join_key' columns before merging.
    """
    df_main  = df_main.copy()
    df_audit = df_audit.copy()

    # Drop any stale _join_key columns left over from a previous run
    df_main.drop(columns=[c for c in df_main.columns if c == "_join_key"], inplace=True)
    df_audit.drop(columns=[c for c in df_audit.columns if c == "_join_key"], inplace=True)

    # Build normalised join keys
    df_main["_join_key"]  = df_main[main_col].fillna("").str.strip().str.lower()
    df_audit["_join_key"] = df_audit[BULLET_COL].fillna("").str.strip().str.lower()

    # Bring everything from audit except its own bullet column (already in df_main)
    audit_cols_to_bring = [c for c in df_audit.columns if c != BULLET_COL]

    df_merged = df_main.merge(
        df_audit[["_join_key"] + audit_cols_to_bring].drop_duplicates(subset="_join_key"),
        on="_join_key",
        how="left"
    ).drop(columns=["_join_key"])

    # Normalize manager_test
    if "manager_test" in df_merged.columns:
        df_merged["manager_test"] = df_merged["manager_test"].apply(normalize_manager_test)
        pass_count = (df_merged["manager_test"] == "PASS").sum()
        fail_count = (df_merged["manager_test"] == "FAIL").sum()
        print(f"  📋 manager_test normalized: {pass_count} PASS / {fail_count} FAIL")

    matched = df_merged["accuracy_score"].notna().sum() if "accuracy_score" in df_merged.columns else "?"
    print(f"  🔗 Audit join complete: {matched}/{len(df_main)} bullets matched.")
    return df_merged


def cluster_bullets(bullets: list, threshold: float):
    print(f"  🔢 Vectorizing {len(bullets)} bullets with TF-IDF (ngrams 1–2)...")
    vectorizer = TfidfVectorizer(ngram_range=(1, 2), stop_words="english", min_df=1)
    matrix     = vectorizer.fit_transform(bullets)

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
    Priority:
    1. Highest accuracy_score (if audit data present)
    2. Highest hidden_gem_score (if present)
    3. Longest bullet text
    """
    if "accuracy_score" in df.columns:
        scored = [(i, pd.to_numeric(df.iloc[i].get("accuracy_score", 0), errors="coerce") or 0)
                  for i in cluster]
        return max(scored, key=lambda x: (x[1], len(bullets[x[0]])))[0]
    if "hidden_gem_score" in df.columns:
        scored = [(i, pd.to_numeric(df.iloc[i].get("hidden_gem_score", 0), errors="coerce") or 0)
                  for i in cluster]
        return max(scored, key=lambda x: (x[1], len(bullets[x[0]])))[0]
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
            preview   = bullets[idx][:95] + ("..." if len(bullets[idx]) > 95 else "")
            score_str = ""
            if has_scores:
                acc     = df.iloc[idx].get("accuracy_score", "")
                mgr     = df.iloc[idx].get("manager_test", "")
                company = df.iloc[idx].get("Role / Company", "")
                score_str = f" [acc={acc} mgr={mgr} co={company}]"
            print(f"    • [{idx}]{score_str} {preview}")
        print()


def decide_action(row: pd.Series) -> str:
    """
    Recommended next action per bullet. manager_test is already
    normalized to PASS/FAIL by the time this runs.
    """
    mgr           = str(row.get("manager_test",      "")).strip().upper()
    believability = pd.to_numeric(row.get("believability_score", None), errors="coerce")
    accuracy      = pd.to_numeric(row.get("accuracy_score",      None), errors="coerce")
    weaknesses    = str(row.get("weaknesses", "")).strip()

    if pd.isna(accuracy) and pd.isna(believability):
        return "NEEDS_AUDIT"
    if mgr == "FAIL" or (pd.notna(believability) and believability < 80):
        return "REWRITE"
    if weaknesses and weaknesses.lower() not in ("", "none", "nan", "n/a"):
        return "REVIEW" if (pd.notna(accuracy) and accuracy >= 85) else "REWRITE"
    return "KEEP"


def build_col_order(df: pd.DataFrame, bullet_col: str) -> list:
    """
    Fixed column order for output CSVs:
      cluster_id | cluster_size | next_action | Bullet Point
      | Role / Company | Tags
      | accuracy_score | believability_score | clarity_score | ats_value | manager_test
      | weaknesses
      | everything else
    """
    pinned_front  = ["cluster_id", "cluster_size", "next_action", bullet_col]
    pinned_meta   = [c for c in META_COLS  if c in df.columns]
    pinned_scores = [c for c in SCORE_COLS if c in df.columns]
    pinned_weak   = [WEAKNESS_COL] if WEAKNESS_COL in df.columns else []
    already       = set(pinned_front + pinned_meta + pinned_scores + pinned_weak)
    remainder     = [c for c in df.columns if c not in already]
    return pinned_front + pinned_meta + pinned_scores + pinned_weak + remainder


# ---------------------------------------------------------------------------
# MAIN
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="Cluster + deduplicate bullets with full audit data in one unified report."
    )
    parser.add_argument("--input",       default=DEFAULT_INPUT,     help="Path to bullet-bank-clean.csv")
    parser.add_argument("--audit",       default=DEFAULT_AUDIT,     help="Path to bullet-bank-audited.csv")
    parser.add_argument("--output",      default=DEFAULT_DEDUP_OUT, help="Path for deduplicated output CSV")
    parser.add_argument("--map",         default=DEFAULT_MAP_OUT,   help="Path for full cluster map CSV")
    parser.add_argument("--threshold",   type=float, default=DEFAULT_THRESHOLD,
                        help="Cosine similarity threshold (default 0.75). Higher = stricter.")
    parser.add_argument("--report-only", action="store_true",
                        help="Print cluster preview without writing any files.")
    args = parser.parse_args()

    print(f"\n📥 Loading bullet bank: {args.input}")
    df         = pd.read_csv(args.input)
    bullet_col = detect_col(df, BULLET_COL, FALLBACK_COLS)
    bullets    = df[bullet_col].fillna("").tolist()
    print(f"  ✅ {len(bullets)} bullets loaded.")
    print(f"  🎯 Similarity threshold: {args.threshold}")

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

    # --- DEDUPLICATED OUTPUT (one rep per cluster) ---
    df_dedup = df.iloc[rep_indices].copy()
    df_dedup.insert(0, "cluster_id",   [assigned[i]               for i in rep_indices])
    df_dedup.insert(1, "cluster_size", [len(clusters[assigned[i]]) for i in rep_indices])
    df_dedup["next_action"] = df_dedup.apply(decide_action, axis=1)

    col_order = build_col_order(df_dedup, bullet_col)
    df_dedup  = df_dedup[[c for c in col_order if c in df_dedup.columns]]
    df_dedup.to_csv(args.output, index=False)
    print(f"\n✅ Deduplicated report saved: {args.output}")
    print(f"   Columns: {df_dedup.columns.tolist()}")

    action_counts = df_dedup["next_action"].value_counts().to_dict()
    print(f"   next_action breakdown:")
    for action, count in sorted(action_counts.items()):
        print(f"     {action:<15} {count}")

    # --- FULL CLUSTER MAP (every bullet, all columns) ---
    df["cluster_id"]        = assigned
    df["cluster_size"]      = [len(clusters[cid]) for cid in assigned]
    df["is_representative"] = [i in set(rep_indices) for i in range(len(bullets))]
    df["next_action"]       = df.apply(decide_action, axis=1)

    map_col_order = ["cluster_id", "cluster_size", "is_representative"] + \
                    [c for c in build_col_order(df, bullet_col)
                     if c not in ("cluster_id", "cluster_size")]
    df_map = df[[c for c in map_col_order if c in df.columns]] \
               .sort_values(["cluster_id", "is_representative"], ascending=[True, False])
    df_map.to_csv(args.map, index=False)
    print(f"📋 Full cluster map saved: {args.map}\n")


if __name__ == "__main__":
    main()
