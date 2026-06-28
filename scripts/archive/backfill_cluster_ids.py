#!/usr/bin/env python3
"""
backfill_cluster_ids.py  —  One-time utility

Stamps `source_cluster_id` onto rows in bullet-bank-keepers-audited.csv
that were saved before Stage 4 started recording that column.

Matching strategy (applied in order, stops at first hit per keeper row):

  1. Exact text match  — keeper bullet text matches a cluster map row verbatim
     (handles the rare case where a bullet passed Stage 4 without any rewrite)

  2. Fuzzy match (MANUAL rows only, same Role/Company + Tags)
     — uses difflib SequenceMatcher ratio >= FUZZY_THRESHOLD (default 0.35)
     — covers rewrites: the rewritten text shares enough tokens with the
       original to score above the threshold even though it isn't identical

  3. Fuzzy match (ALL rows, same Role/Company + Tags)
     — same threshold, broader pool — last resort before giving up

  4. Fuzzy match (ALL rows, same Role/Company only — no tag constraint)
     — threshold lowered by TAG_FREE_DISCOUNT (default 0.05) to compensate
       for the wider pool; catches bullets whose tags drifted between stages
       or whose company has zero rows for that exact tag combo in the map

Rows with no match are left blank and printed for manual review.

Usage:
  python scripts/backfill_cluster_ids.py
  python scripts/backfill_cluster_ids.py --threshold 0.45   # stricter
  python scripts/backfill_cluster_ids.py --dry-run          # print only, no write
  python scripts/backfill_cluster_ids.py --all-rows         # re-stamp rows that
                                                             # already have an ID
"""

import argparse
import os
import sys
from difflib import SequenceMatcher

import pandas as pd

# ---------------------------------------------------------------------------
# PATHS
# ---------------------------------------------------------------------------
SCRIPT_DIR   = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(SCRIPT_DIR)
KB_DIR       = os.path.join(PROJECT_ROOT, "resume-engine", "knowledge_base")

KEEPERS_AUDITED     = os.path.join(KB_DIR, "bullet-bank-keepers-audited.csv")
CLUSTER_MAP_UPDATED = os.path.join(KB_DIR, "bullet-bank-cluster-map-updated.csv")
CLUSTER_MAP_IN      = os.path.join(KB_DIR, "bullet-bank-cluster-map.csv")

FUZZY_THRESHOLD_DEFAULT = 0.35  # conservative — avoids false matches across companies
TAG_FREE_DISCOUNT       = 0.05  # Pass 4 uses threshold - this value (wider pool = lower bar)


# ---------------------------------------------------------------------------
# HELPERS
# ---------------------------------------------------------------------------

def _norm(text: str) -> str:
    """Lowercase, strip, collapse whitespace for comparison."""
    return " ".join(str(text).lower().split())


def _ratio(a: str, b: str) -> float:
    return SequenceMatcher(None, _norm(a), _norm(b)).ratio()


def _norm_tags(tags) -> str:
    """Normalise tags to a sorted, lowercase string for grouping."""
    if pd.isna(tags) or str(tags).strip() == "":
        return ""
    parts = [t.strip().lower() for t in str(tags).replace(",", " ").split() if t.strip()]
    return " ".join(sorted(parts))


def _norm_company(company) -> str:
    return str(company).strip().lower() if pd.notna(company) else ""


def _to_str_id(v) -> str:
    """Convert a cluster_id value to a clean string (no '.0' suffix)."""
    try:
        return str(int(float(str(v))))
    except (ValueError, TypeError):
        return str(v)


# ---------------------------------------------------------------------------
# MAIN
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="Backfill source_cluster_id on legacy keeper rows"
    )
    parser.add_argument(
        "--threshold", type=float, default=FUZZY_THRESHOLD_DEFAULT,
        help=f"Fuzzy match minimum ratio (default {FUZZY_THRESHOLD_DEFAULT})"
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Print results but do not write the file"
    )
    parser.add_argument(
        "--all-rows", action="store_true",
        help="Re-stamp ALL rows, even those that already have a source_cluster_id"
    )
    args = parser.parse_args()

    print("\n" + "#" * 60)
    print("  backfill_cluster_ids.py")
    print("#" * 60)
    print(f"  threshold:        {args.threshold}")
    print(f"  pass-4 threshold: {max(args.threshold - TAG_FREE_DISCOUNT, 0.15):.2f}  (company-only, no tag constraint)")
    print(f"  dry_run:          {args.dry_run}")
    print(f"  all_rows:         {args.all_rows}")

    # --- Load keepers-audited ---
    if not os.path.exists(KEEPERS_AUDITED):
        print(f"\n❌  {KEEPERS_AUDITED} not found.")
        print("    Run audit_keepers.py first so the file exists locally.")
        sys.exit(1)

    df_keepers = pd.read_csv(KEEPERS_AUDITED, dtype={"source_cluster_id": str})
    if "source_cluster_id" not in df_keepers.columns:
        df_keepers["source_cluster_id"] = ""
    else:
        # Normalise any existing values (e.g. "69.0" → "69")
        df_keepers["source_cluster_id"] = df_keepers["source_cluster_id"].apply(
            lambda v: _to_str_id(v) if pd.notna(v) and str(v).strip() not in ("", "nan") else ""
        )

    # Decide which rows need stamping
    if args.all_rows:
        needs_stamp = pd.Series([True] * len(df_keepers), index=df_keepers.index)
    else:
        needs_stamp = df_keepers["source_cluster_id"].apply(
            lambda v: pd.isna(v) or str(v).strip() == ""
        )

    n_total   = len(df_keepers)
    n_targets = needs_stamp.sum()
    n_already = n_total - n_targets
    print(f"\n   📂 Loaded {n_total} rows from bullet-bank-keepers-audited.csv")
    print(f"   Already stamped: {n_already}  |  Need stamping: {n_targets}")

    if n_targets == 0:
        print("\n   ✅  All rows already have source_cluster_id — nothing to do.")
        return

    # --- Load cluster map ---
    if os.path.exists(CLUSTER_MAP_UPDATED):
        map_path = CLUSTER_MAP_UPDATED
        print(f"   Using: {os.path.basename(map_path)}")
    elif os.path.exists(CLUSTER_MAP_IN):
        map_path = CLUSTER_MAP_IN
        print(f"   ⚠️   Updated map not found — using: {os.path.basename(map_path)}")
    else:
        print("   ❌  No cluster map found — cannot backfill.")
        sys.exit(1)

    df_map = pd.read_csv(map_path)

    # Normalised helper columns on the cluster map (working copies, not saved)
    df_map["_norm_bullet"]  = df_map["Bullet Point"].apply(_norm)
    df_map["_norm_company"] = df_map["Role / Company"].apply(_norm_company)
    df_map["_norm_tags"]    = df_map["Tags"].apply(_norm_tags)

    status_col = "rewrite_status" if "rewrite_status" in df_map.columns else "next_action"

    # Build exact-match lookup: normalised bullet text → cluster_id (as str)
    exact_lookup: dict = {}
    for _, row in df_map.iterrows():
        key = row["_norm_bullet"]
        if key and key not in exact_lookup:
            exact_lookup[key] = _to_str_id(row["cluster_id"])

    print(f"   Cluster map: {len(df_map)} rows  |  {len(exact_lookup)} unique bullets\n")

    # Pass 4 threshold — slightly lower since the pool is wider (no tag filter)
    p4_threshold = max(args.threshold - TAG_FREE_DISCOUNT, 0.15)

    # --- Match loop ---
    n_exact   = 0
    n_fuzzy_m = 0  # fuzzy, MANUAL pool
    n_fuzzy_a = 0  # fuzzy, all-rows pool (with tags)
    n_fuzzy_c = 0  # fuzzy, company-only pool (no tag constraint) — Pass 4
    n_miss    = 0
    misses    = []

    for idx in df_keepers[needs_stamp].index:
        row      = df_keepers.loc[idx]
        bullet   = str(row.get("Bullet Point", "")).strip()
        company  = _norm_company(row.get("Role / Company", ""))
        tags     = _norm_tags(row.get("Tags", ""))
        norm_bp  = _norm(bullet)

        matched_id   = None  # always a str when set
        match_method = None

        # ── Pass 1: exact text match (any cluster map row) ──────────────────
        if norm_bp in exact_lookup:
            matched_id   = exact_lookup[norm_bp]
            match_method = "exact"
            n_exact += 1

        # ── Pass 2: fuzzy, MANUAL rows, same company+tags ────────────────────
        if matched_id is None:
            pool = df_map[
                (df_map["_norm_company"] == company)
                & (df_map["_norm_tags"]    == tags)
                & (df_map[status_col].str.strip().str.upper() == "MANUAL")
            ]
            if not pool.empty:
                best_ratio = 0.0
                best_cid   = None
                for _, crow in pool.iterrows():
                    r = _ratio(bullet, crow["Bullet Point"])
                    if r > best_ratio:
                        best_ratio = r
                        best_cid   = _to_str_id(crow["cluster_id"])
                if best_ratio >= args.threshold:
                    matched_id   = best_cid
                    match_method = f"fuzzy-manual (ratio={best_ratio:.2f})"
                    n_fuzzy_m   += 1

        # ── Pass 3: fuzzy, ALL rows, same company+tags ───────────────────────
        if matched_id is None:
            pool = df_map[
                (df_map["_norm_company"] == company)
                & (df_map["_norm_tags"]    == tags)
            ]
            if not pool.empty:
                best_ratio = 0.0
                best_cid   = None
                for _, crow in pool.iterrows():
                    r = _ratio(bullet, crow["Bullet Point"])
                    if r > best_ratio:
                        best_ratio = r
                        best_cid   = _to_str_id(crow["cluster_id"])
                if best_ratio >= args.threshold:
                    matched_id   = best_cid
                    match_method = f"fuzzy-all (ratio={best_ratio:.2f})"
                    n_fuzzy_a   += 1

        # ── Pass 4: fuzzy, ALL rows, same company ONLY (no tag constraint) ───
        # Catches bullets whose tags drifted between stages, or companies with
        # zero cluster-map rows for that exact tag combo (e.g. Misc./Unassigned,
        # Kansas Colloquies). Uses a slightly lower threshold to compensate for
        # the wider pool.
        if matched_id is None:
            pool = df_map[df_map["_norm_company"] == company]
            if not pool.empty:
                best_ratio = 0.0
                best_cid   = None
                for _, crow in pool.iterrows():
                    r = _ratio(bullet, crow["Bullet Point"])
                    if r > best_ratio:
                        best_ratio = r
                        best_cid   = _to_str_id(crow["cluster_id"])
                if best_ratio >= p4_threshold:
                    matched_id   = best_cid
                    match_method = f"fuzzy-company (ratio={best_ratio:.2f})"
                    n_fuzzy_c   += 1

        # ── Record result ────────────────────────────────────────────────────
        if matched_id is not None:
            df_keepers.loc[idx, "source_cluster_id"] = matched_id
            print(f"   ✅  [{match_method}]  cluster_id={matched_id}")
            print(f"       Keeper:  {bullet[:80]}")
        else:
            n_miss += 1
            misses.append({
                "index":          idx,
                "Bullet Point":   bullet,
                "Role / Company": row.get("Role / Company", ""),
                "Tags":           row.get("Tags", ""),
            })
            print(f"   ❓  NO MATCH  {bullet[:80]}")

    # --- Summary ---
    print("\n" + "=" * 60)
    print("  Backfill summary")
    print("=" * 60)
    print(f"  Rows processed:      {n_targets}")
    print(f"  Exact matches:       {n_exact}")
    print(f"  Fuzzy-MANUAL:        {n_fuzzy_m}")
    print(f"  Fuzzy-ALL (w/ tags): {n_fuzzy_a}")
    print(f"  Fuzzy-company only:  {n_fuzzy_c}  ← Pass 4 (new)")
    print(f"  No match:            {n_miss}")

    if misses:
        print(f"\n  ⚠️   {n_miss} rows could not be matched — review manually:")
        for m in misses:
            print(f"      row {m['index']:>4}  [{m['Role / Company']}  {m['Tags']}]")
            print(f"             {m['Bullet Point'][:90]}")
        print(
            "\n  Tip: re-run with --threshold 0.25 to cast a wider net, "
            "or stamp cluster_id manually in the CSV."
        )

    # --- Write ---
    if args.dry_run:
        print("\n  🔍  --dry-run set: file NOT written.")
    else:
        df_keepers.to_csv(KEEPERS_AUDITED, index=False)
        stamped = n_exact + n_fuzzy_m + n_fuzzy_a + n_fuzzy_c
        print(f"\n  💾  Written → {os.path.basename(KEEPERS_AUDITED)}")
        print(f"      {stamped} rows now have source_cluster_id")
        print(f"      {n_miss} rows still blank (see above)")

    print("=" * 60 + "\n")


if __name__ == "__main__":
    main()
