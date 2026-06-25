#!/usr/bin/env python3
"""
audit_keepers.py  —  Post-rewrite keeper audit pipeline

Four stages:

  Stage 1 — Audit Keepers
    Read bullet-bank-keepers.csv. For every row that either has no scores
    recorded OR has manager_test != PASS, call score_bullet() from
    rewrite_bullets.py and write the fresh scores back. Adds an
    `audit_status` column: CLEAN | NEEDS_REWRITE | MANUAL.

  Stage 2 — Diff Against Cluster Map
    Cross-reference keepers against bullet-bank-cluster-map-updated.csv
    (falls back to bullet-bank-cluster-map.csv if the updated file does
    not exist). Flags any keeper whose original text still shows MANUAL
    in the cluster map — i.e. the keeper won best_version() but the map
    never reflected that. Writes discrepancies to audit-discrepancies.csv.

  Stage 3 — Triage Queue
    Pulls all NEEDS_REWRITE bullets from Stage 1 + all MANUAL bullets
    from the cluster map that are not already in keepers. Deduplicates,
    ranks by composite score ascending (worst first), writes to
    audit-rewrite-queue.csv.

  Stage 4 — Optional Auto-Rewrite
    If --auto-rewrite flag is passed, hands each queued bullet to
    process_bullet() imported directly from rewrite_bullets.py.
    Uses the same sleep constants and process_bullet() logic — no new
    rewrite code here.

Outputs (resume-engine/knowledge_base/):
  bullet-bank-keepers-audited.csv    keepers with refreshed scores + audit_status
  audit-discrepancies.csv            cluster-map / keeper mismatches
  audit-rewrite-queue.csv            ranked rewrite queue (Stage 3)

Usage:
  python audit_keepers.py                    # run all four stages, no auto-rewrite
  python audit_keepers.py --dry-run          # score pass is mocked, no API calls
  python audit_keepers.py --auto-rewrite     # Stage 4: run the queue through process_bullet()
  python audit_keepers.py --auto-rewrite --limit 10
  python audit_keepers.py --skip-rescore     # skip Stage 1 API calls, use existing scores
"""

import argparse
import os
import sys
import time
from datetime import datetime

import pandas as pd

# ---------------------------------------------------------------------------
# PATH RESOLUTION
# ---------------------------------------------------------------------------
SCRIPT_DIR   = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(SCRIPT_DIR)
KB_DIR       = os.path.join(PROJECT_ROOT, "resume-engine", "knowledge_base")
RULES_DIR    = os.path.join(PROJECT_ROOT, "resume-engine", "rules")

if SCRIPT_DIR not in sys.path:
    sys.path.insert(0, SCRIPT_DIR)

# Import shared logic from rewrite_bullets.py — no duplication.
from rewrite_bullets import (
    RulesBundle,
    KnowledgeBase,
    build_system_prompts,
    score_bullet,
    process_bullet,
    decide_action,
    is_keeper,
    best_version,
    append_keeper,
    ensure_writable_dtypes,
    SCORE_COLS,
    NUMERIC_SCORE_COLS,
    STRING_SCORE_COLS,
    KEEPER_COLS,
    SLEEP_BETWEEN_BULLETS,
)

# ---------------------------------------------------------------------------
# FILE PATHS
# ---------------------------------------------------------------------------
KEEPERS_IN         = os.path.join(KB_DIR, "bullet-bank-keepers.csv")
KEEPERS_AUDITED    = os.path.join(KB_DIR, "bullet-bank-keepers-audited.csv")
CLUSTER_MAP_UPDATED = os.path.join(KB_DIR, "bullet-bank-cluster-map-updated.csv")
CLUSTER_MAP_IN     = os.path.join(KB_DIR, "bullet-bank-cluster-map.csv")
DISCREPANCIES_OUT  = os.path.join(KB_DIR, "audit-discrepancies.csv")
REWRITE_QUEUE_OUT  = os.path.join(KB_DIR, "audit-rewrite-queue.csv")

# ---------------------------------------------------------------------------
# HELPERS
# ---------------------------------------------------------------------------

SCORE_PRESENT_COLS = ["accuracy_score", "believability_score", "clarity_score", "ats_value"]


def _has_scores(row: pd.Series) -> bool:
    """True if the row has at least one non-null, non-zero numeric score."""
    for col in SCORE_PRESENT_COLS:
        val = pd.to_numeric(row.get(col, None), errors="coerce")
        if pd.notna(val) and val > 0:
            return True
    return False


def _composite(row: pd.Series) -> float:
    """Mirror of rewrite_bullets.best_version() composite logic."""
    numeric = sum(
        pd.to_numeric(row.get(c, 0), errors="coerce") or 0
        for c in ["accuracy_score", "believability_score", "clarity_score", "ats_value"]
    )
    mgr_bonus = 10 if str(row.get("manager_test", "")).upper() == "PASS" else 0
    return numeric + mgr_bonus


def _audit_status(row: pd.Series) -> str:
    """Classify a keeper row after scoring."""
    mgr = str(row.get("manager_test", "")).strip().upper()
    action = decide_action({
        "accuracy_score":      row.get("accuracy_score"),
        "believability_score": row.get("believability_score"),
        "clarity_score":       row.get("clarity_score"),
        "ats_value":           row.get("ats_value"),
        "manager_test":        mgr,
        "weaknesses":          row.get("weaknesses", ""),
    })
    if action == "KEEP" and mgr == "PASS":
        return "CLEAN"
    if action in ("REWRITE", "REVIEW"):
        return "NEEDS_REWRITE"
    return "MANUAL"


def _safe_str(v) -> str:
    if v is None:
        return ""
    if isinstance(v, float) and pd.isna(v):
        return ""
    return str(v)


# ---------------------------------------------------------------------------
# STAGE 1: AUDIT KEEPERS
# ---------------------------------------------------------------------------

def stage1_audit_keepers(
    df_keepers: pd.DataFrame,
    score_system: str,
    dry_run: bool = False,
    skip_rescore: bool = False,
) -> pd.DataFrame:
    """
    Re-score keepers that are missing scores or have manager_test != PASS.
    Adds / refreshes: accuracy_score, believability_score, clarity_score,
    ats_value, manager_test, weaknesses, audit_status.
    """
    print("\n" + "=" * 60)
    print("STAGE 1 — Audit Keepers")
    print("=" * 60)

    if "audit_status" not in df_keepers.columns:
        df_keepers["audit_status"] = ""

    needs_score_mask = df_keepers.apply(
        lambda r: not _has_scores(r) or str(r.get("manager_test", "")).strip().upper() != "PASS",
        axis=1,
    )
    to_score = df_keepers[needs_score_mask]
    already_clean = df_keepers[~needs_score_mask]

    print(f"   Total keepers:         {len(df_keepers)}")
    print(f"   Already CLEAN (PASS):  {len(already_clean)}")
    print(f"   Need scoring/review:   {len(to_score)}")

    # Mark already-clean rows immediately
    df_keepers.loc[~needs_score_mask, "audit_status"] = "CLEAN"

    if to_score.empty:
        print("   ✅ All keepers already clean — no scoring needed.")
        return df_keepers

    if skip_rescore:
        print("   ⏭️  --skip-rescore set: classifying with existing scores, no API calls.")
        for idx in to_score.index:
            df_keepers.loc[idx, "audit_status"] = _audit_status(df_keepers.loc[idx])
        return df_keepers

    total = len(to_score)
    for i, (idx, row) in enumerate(to_score.iterrows(), 1):
        bullet = str(row.get("Bullet Point", "")).strip()
        tags   = str(row.get("Tags", ""))
        print(f"\n   [{i}/{total}] Scoring: {bullet[:70]}...")

        scores = score_bullet(bullet, tags, score_system, dry_run=dry_run)

        for col in SCORE_COLS:
            if col in NUMERIC_SCORE_COLS:
                df_keepers.loc[idx, col] = pd.to_numeric(scores.get(col, None), errors="coerce")
            else:
                df_keepers.loc[idx, col] = _safe_str(scores.get(col, ""))
        df_keepers.loc[idx, "weaknesses"] = _safe_str(scores.get("weaknesses", ""))
        df_keepers.loc[idx, "audit_status"] = _audit_status(df_keepers.loc[idx])

        status = df_keepers.loc[idx, "audit_status"]
        mgr    = str(scores.get("manager_test", "")).upper()
        print(
            f"   → status={status}  mgr={mgr}  "
            f"acc={scores.get('accuracy_score')}  "
            f"bel={scores.get('believability_score')}  "
            f"cla={scores.get('clarity_score')}  "
            f"ats={scores.get('ats_value')}"
        )

        if i < total:
            time.sleep(SLEEP_BETWEEN_BULLETS)

    n_clean   = (df_keepers["audit_status"] == "CLEAN").sum()
    n_rewrite = (df_keepers["audit_status"] == "NEEDS_REWRITE").sum()
    n_manual  = (df_keepers["audit_status"] == "MANUAL").sum()
    print(f"\n   Stage 1 complete → CLEAN: {n_clean} | NEEDS_REWRITE: {n_rewrite} | MANUAL: {n_manual}")
    return df_keepers


# ---------------------------------------------------------------------------
# STAGE 2: DIFF AGAINST CLUSTER MAP
# ---------------------------------------------------------------------------

def stage2_diff_cluster_map(
    df_keepers: pd.DataFrame,
) -> pd.DataFrame:
    """
    Cross-reference keepers against the cluster map.
    Returns a DataFrame of discrepancy rows written to audit-discrepancies.csv.
    """
    print("\n" + "=" * 60)
    print("STAGE 2 — Diff Against Cluster Map")
    print("=" * 60)

    # Prefer updated map; fall back to original
    if os.path.exists(CLUSTER_MAP_UPDATED):
        map_path = CLUSTER_MAP_UPDATED
        print(f"   Using updated cluster map: {os.path.basename(map_path)}")
    elif os.path.exists(CLUSTER_MAP_IN):
        map_path = CLUSTER_MAP_IN
        print(f"   ⚠️  Updated map not found — falling back to: {os.path.basename(map_path)}")
    else:
        print("   ⚠️  No cluster map found — skipping Stage 2.")
        return pd.DataFrame()

    df_map = pd.read_csv(map_path)

    # Build a lookup: bullet text → rewrite_status in cluster map
    map_status_lookup: dict = {}
    if "Bullet Point" in df_map.columns and "rewrite_status" in df_map.columns:
        for _, row in df_map.iterrows():
            bp = str(row["Bullet Point"]).strip()
            status = str(row.get("rewrite_status", "")).strip().upper()
            map_status_lookup[bp] = status
    elif "Bullet Point" in df_map.columns and "next_action" in df_map.columns:
        # Cluster map that hasn't been through a rewrite run yet
        for _, row in df_map.iterrows():
            bp = str(row["Bullet Point"]).strip()
            status = str(row.get("next_action", "")).strip().upper()
            map_status_lookup[bp] = status

    discrepancies = []
    for _, row in df_keepers.iterrows():
        bp = str(row.get("Bullet Point", "")).strip()
        map_status = map_status_lookup.get(bp, "NOT_FOUND")
        # A discrepancy is: keeper is marked CLEAN but cluster map still says MANUAL
        if map_status == "MANUAL":
            discrepancies.append({
                "Bullet Point":    bp,
                "Role / Company":  row.get("Role / Company", ""),
                "Tags":            row.get("Tags", ""),
                "keeper_status":   row.get("audit_status", ""),
                "map_status":      map_status,
                "note":            "Keeper CLEAN but cluster map still shows MANUAL — map may need re-run",
                "composite_score": _composite(row),
            })
        elif map_status == "NOT_FOUND":
            discrepancies.append({
                "Bullet Point":    bp,
                "Role / Company":  row.get("Role / Company", ""),
                "Tags":            row.get("Tags", ""),
                "keeper_status":   row.get("audit_status", ""),
                "map_status":      map_status,
                "note":            "Bullet in keepers.csv but not found in cluster map at all",
                "composite_score": _composite(row),
            })

    df_disc = pd.DataFrame(discrepancies)
    print(f"   Keepers checked:    {len(df_keepers)}")
    print(f"   Discrepancies found: {len(df_disc)}")

    if not df_disc.empty:
        df_disc.to_csv(DISCREPANCIES_OUT, index=False)
        print(f"   💾 Discrepancies written → {os.path.basename(DISCREPANCIES_OUT)}")
        for _, d in df_disc.iterrows():
            print(f"      ⚠️  [{d['map_status']}] {str(d['Bullet Point'])[:70]}")
    else:
        print("   ✅ No discrepancies — keepers and cluster map are in sync.")

    return df_disc


# ---------------------------------------------------------------------------
# STAGE 3: TRIAGE QUEUE
# ---------------------------------------------------------------------------

def stage3_build_rewrite_queue(
    df_keepers: pd.DataFrame,
) -> pd.DataFrame:
    """
    Builds the ranked rewrite queue from:
      - NEEDS_REWRITE / MANUAL rows from the audited keepers (Stage 1)
      - MANUAL rows from the cluster map that aren't already in keepers

    Sorted by composite score ascending (worst bullets first).
    """
    print("\n" + "=" * 60)
    print("STAGE 3 — Triage Queue")
    print("=" * 60)

    queue_rows = []

    # Source A: keepers that need attention
    keeper_bad_mask = df_keepers["audit_status"].isin(["NEEDS_REWRITE", "MANUAL"])
    df_keeper_bad = df_keepers[keeper_bad_mask].copy()
    df_keeper_bad["queue_source"] = "keeper_audit"
    queue_rows.append(df_keeper_bad)
    print(f"   From keeper audit (NEEDS_REWRITE + MANUAL): {len(df_keeper_bad)}")

    # Source B: MANUAL bullets in cluster map not already in keepers
    map_path = CLUSTER_MAP_UPDATED if os.path.exists(CLUSTER_MAP_UPDATED) else CLUSTER_MAP_IN
    if os.path.exists(map_path):
        df_map = pd.read_csv(map_path)
        df_map = ensure_writable_dtypes(df_map)

        status_col = "rewrite_status" if "rewrite_status" in df_map.columns else "next_action"
        manual_mask = df_map[status_col].str.strip().str.upper() == "MANUAL"
        rep_col = "is_representative"
        if rep_col in df_map.columns:
            rep_mask = df_map[rep_col].astype(str).str.strip().str.lower().isin(["true", "1", "yes"])
            manual_mask = manual_mask & rep_mask

        df_map_manual = df_map[manual_mask].copy()

        # Exclude bullets already in keepers
        keeper_bullets = set(df_keepers["Bullet Point"].dropna().str.strip())
        df_map_manual = df_map_manual[
            ~df_map_manual["Bullet Point"].str.strip().isin(keeper_bullets)
        ].copy()

        # Carry over scores if present in the cluster map
        for col in SCORE_COLS:
            if col not in df_map_manual.columns:
                df_map_manual[col] = None

        df_map_manual["queue_source"] = "cluster_map_manual"
        queue_rows.append(df_map_manual)
        print(f"   From cluster map MANUAL (not in keepers): {len(df_map_manual)}")
    else:
        print("   ⚠️  Cluster map not found — skipping cluster-map MANUAL source.")

    if not queue_rows or all(df.empty for df in queue_rows):
        print("   ✅ Queue is empty — nothing to rewrite!")
        return pd.DataFrame()

    df_queue = pd.concat(queue_rows, ignore_index=True)

    # Deduplicate on bullet text
    before_dedup = len(df_queue)
    df_queue = df_queue.drop_duplicates(subset=["Bullet Point"], keep="first").copy()
    print(f"   Deduplicated: {before_dedup} → {len(df_queue)} unique bullets")

    # Rank worst-first by composite score
    df_queue["composite_score"] = df_queue.apply(_composite, axis=1)
    df_queue = df_queue.sort_values("composite_score", ascending=True).reset_index(drop=True)
    df_queue["queue_rank"] = df_queue.index + 1

    df_queue.to_csv(REWRITE_QUEUE_OUT, index=False)
    print(f"   💾 Rewrite queue written ({len(df_queue)} bullets) → {os.path.basename(REWRITE_QUEUE_OUT)}")
    print(f"   Lowest composite: {df_queue['composite_score'].min():.0f}  "
          f"Highest: {df_queue['composite_score'].max():.0f}")

    # Print top 10 worst for easy triage
    print("\n   Top 10 worst (will be rewritten first if --auto-rewrite):")
    for _, row in df_queue.head(10).iterrows():
        bp  = str(row.get("Bullet Point", ""))[:65]
        src = row.get("queue_source", "")
        cmp = row.get("composite_score", 0)
        mgr = str(row.get("manager_test", "")).upper()
        print(f"      #{int(row['queue_rank']):>3}  [{src:<20}]  cmp={cmp:>5.0f}  mgr={mgr:<4}  {bp}...")

    return df_queue


# ---------------------------------------------------------------------------
# STAGE 4: AUTO-REWRITE
# ---------------------------------------------------------------------------

def stage4_auto_rewrite(
    df_queue: pd.DataFrame,
    kb: KnowledgeBase,
    rewrite_system: str,
    score_system: str,
    df_keepers: pd.DataFrame,
    limit: int = None,
    dry_run: bool = False,
) -> pd.DataFrame:
    """
    Passes each queued bullet through process_bullet() from rewrite_bullets.py.
    KEEP results are appended to the audited keepers CSV.
    """
    print("\n" + "=" * 60)
    print("STAGE 4 — Auto-Rewrite")
    print("=" * 60)

    if df_queue.empty:
        print("   ✅ Queue is empty — nothing to auto-rewrite.")
        return df_keepers

    df_run = df_queue.copy()
    if limit:
        df_run = df_run.head(limit)
        print(f"   ⚙️  --limit set: processing {limit} of {len(df_queue)} queued bullets.")

    total  = len(df_run)
    n_keep = 0
    n_manual = 0

    for i, (_, row) in enumerate(df_run.iterrows(), 1):
        bullet_preview = str(row.get("Bullet Point", ""))[:60]
        print(f"\n{'─' * 60}")
        print(f"[{i}/{total}] {bullet_preview}...")
        print(f"   Source: {row.get('queue_source', '')}  "
              f"Composite: {row.get('composite_score', '?')}")

        result = process_bullet(
            row=row,
            kb=kb,
            rewrite_system=rewrite_system,
            score_system=score_system,
            dry_run=dry_run,
        )

        if result["rewrite_status"] == "KEEP":
            n_keep += 1
            keeper_row = {
                "Bullet Point":      result["final_bullet"],
                "Role / Company":    row.get("Role / Company", ""),
                "Tags":              row.get("Tags", ""),
                "source":            "audit_rewrite",
                "rewrite_attempts":  result.get("rewrite_attempts", 0),
                "rewrite_reasoning": result.get("rewrite_reasoning", ""),
                "context_gaps":      result.get("context_gaps", ""),
                "audit_status":      "CLEAN",
                **{col: result.get(col, "") for col in SCORE_COLS},
                "weaknesses":        result.get("weaknesses", ""),
            }
            df_keepers = append_keeper(df_keepers, keeper_row, KEEPERS_AUDITED)
            print(f"   ✅ KEEPER saved to audited keepers.")
        else:
            n_manual += 1
            print(f"   🔧 MANUAL — best version retained, not added to keepers.")

        if i < total:
            time.sleep(SLEEP_BETWEEN_BULLETS)

    print(f"\n   Stage 4 complete → KEEP: {n_keep} | MANUAL: {n_manual}")
    return df_keepers


# ---------------------------------------------------------------------------
# MAIN
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="Keeper audit + rewrite queue pipeline")
    parser.add_argument("--dry-run",      action="store_true", help="Mock API calls, no cost")
    parser.add_argument("--skip-rescore", action="store_true", help="Skip Stage 1 API scoring")
    parser.add_argument("--auto-rewrite", action="store_true", help="Stage 4: run queue through rewriter")
    parser.add_argument("--limit",        type=int, default=None, help="Cap Stage 4 bullets")
    args = parser.parse_args()

    print("\n" + "#" * 60)
    print("  audit_keepers.py  —  Keeper Audit Pipeline")
    print("#" * 60)
    print(f"  dry_run:      {args.dry_run}")
    print(f"  skip_rescore: {args.skip_rescore}")
    print(f"  auto_rewrite: {args.auto_rewrite}")
    print(f"  limit:        {args.limit}")

    # --- Load keepers ---
    if not os.path.exists(KEEPERS_IN):
        print(f"\n❌  {KEEPERS_IN} not found. Run rewrite_bullets.py first.")
        sys.exit(1)

    df_keepers = pd.read_csv(KEEPERS_IN)
    df_keepers = ensure_writable_dtypes(df_keepers)

    # Ensure all expected columns exist
    for col in KEEPER_COLS + ["audit_status"]:
        if col not in df_keepers.columns:
            df_keepers[col] = ""

    print(f"\n   📂 Loaded keepers: {len(df_keepers)} rows from {os.path.basename(KEEPERS_IN)}")

    # --- Load rules + KB only when scoring is needed ---
    rules = kb = rewrite_system = score_system = None

    needs_api = (
        (not args.skip_rescore)
        or args.auto_rewrite
    )

    if needs_api:
        rules = RulesBundle(RULES_DIR)
        kb    = KnowledgeBase()

        # Warm segment cache over the full keepers set (cheapest: one pass)
        kb.warm_segment_cache(df_keepers)
        rewrite_system, score_system = build_system_prompts(rules, kb)

    # ── Stage 1 ──────────────────────────────────────────────────────────────
    df_keepers = stage1_audit_keepers(
        df_keepers,
        score_system=score_system or "",
        dry_run=args.dry_run,
        skip_rescore=args.skip_rescore,
    )

    # Save audited keepers after Stage 1
    df_keepers.to_csv(KEEPERS_AUDITED, index=False)
    print(f"\n   💾 Audited keepers → {os.path.basename(KEEPERS_AUDITED)}")

    # ── Stage 2 ──────────────────────────────────────────────────────────────
    _df_disc = stage2_diff_cluster_map(df_keepers)

    # ── Stage 3 ──────────────────────────────────────────────────────────────
    df_queue = stage3_build_rewrite_queue(df_keepers)

    # ── Stage 4 (optional) ───────────────────────────────────────────────────
    if args.auto_rewrite:
        if df_queue.empty:
            print("\n   STAGE 4 skipped — queue is empty.")
        else:
            # Warm cache again over the queue-specific bullets for best prefix hits
            if kb is not None:
                kb.warm_segment_cache(df_queue)
            df_keepers = stage4_auto_rewrite(
                df_queue=df_queue,
                kb=kb,
                rewrite_system=rewrite_system,
                score_system=score_system,
                df_keepers=df_keepers,
                limit=args.limit,
                dry_run=args.dry_run,
            )
            # Final save after Stage 4 rewrites are appended
            df_keepers.to_csv(KEEPERS_AUDITED, index=False)
            print(f"\n   💾 Final audited keepers saved → {os.path.basename(KEEPERS_AUDITED)}")
    else:
        if not df_queue.empty:
            print(
                f"\n   ℹ️  {len(df_queue)} bullets queued. "
                f"Run with --auto-rewrite to process them."
            )

    print("\n" + "=" * 60)
    print("  ✅  audit_keepers.py complete")
    print(f"     Audited keepers  → {os.path.basename(KEEPERS_AUDITED)}")
    print(f"     Discrepancies    → {os.path.basename(DISCREPANCIES_OUT)}")
    print(f"     Rewrite queue    → {os.path.basename(REWRITE_QUEUE_OUT)}")
    print("=" * 60 + "\n")


if __name__ == "__main__":
    main()
