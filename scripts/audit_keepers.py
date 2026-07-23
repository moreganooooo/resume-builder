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

    NOT_FOUND entries (keepers that are rewrites not present verbatim in
    the cluster map) are expected and normal — they are counted silently
    and shown only as a summary line, not printed one-by-one.

  Stage 3 — Triage Queue
    Pulls all NEEDS_REWRITE bullets from Stage 1 + all MANUAL bullets
    from the cluster map that are not already in keepers. Deduplicates,
    ranks by composite score ascending (worst first), writes to
    audit-rewrite-queue.csv.

    audit-rewrite-queue.csv is ALWAYS overwritten on every run — even
    when the queue is empty — so a stale file from a prior run can never
    mislead you into thinking there is still work to do.

    Exclusion uses cluster_id (primary) and bullet text (secondary fallback)
    so that bullets already processed by a prior Stage 4 run are not
    re-queued even though the saved keeper text differs from the original.

    When --from-audited is set, Source B (cluster-map MANUAL rows) is
    skipped entirely. The audited file is already the source of truth;
    only the MANUAL/NEEDS_REWRITE rows from that file need retrying.

  Stage 4 — Optional Auto-Rewrite
    If --auto-rewrite flag is passed, hands each queued bullet to
    process_bullet() imported directly from rewrite_bullets.py.
    Uses the same sleep constants and process_bullet() logic — no new
    rewrite code here.
    Records source_cluster_id on saved keeper rows so Stage 3 can
    exclude them by ID on the next run.

Outputs (profiles/<profile>/knowledge_base/):
  bullet-bank-keepers-audited.csv    keepers with refreshed scores + audit_status
  audit-discrepancies.csv            cluster-map / keeper mismatches
  audit-rewrite-queue.csv            ranked rewrite queue (Stage 3) — always
                                     overwritten; empty file = nothing left to do

Usage:
  python audit_keepers.py                    # run all four stages, no auto-rewrite
  python audit_keepers.py --dry-run          # score pass is mocked, no API calls
  python audit_keepers.py --auto-rewrite     # Stage 4: run the queue through rewriter
  python audit_keepers.py --auto-rewrite --limit 10
  python audit_keepers.py --skip-rescore     # skip Stage 1 API calls, use existing scores
  python audit_keepers.py --from-audited --auto-rewrite --skip-rescore
                                             # resume from keepers-audited.csv — only
                                             # MANUAL/NEEDS_REWRITE rows are re-processed;
                                             # CLEAN rows are skipped, cluster-map Source B
                                             # is skipped entirely (no queue inflation)
"""

import argparse
import os
import sys
import time
from datetime import datetime

import pandas as pd

import theme

# ---------------------------------------------------------------------------
# PATH RESOLUTION
# ---------------------------------------------------------------------------
SCRIPT_DIR   = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(SCRIPT_DIR)

if SCRIPT_DIR not in sys.path:
    sys.path.insert(0, SCRIPT_DIR)
import profile_paths  # noqa: E402

KB_DIR       = profile_paths.kb_dir()
RULES_DIR    = os.path.join(PROJECT_ROOT, "resume-engine", "rules")
SCORING_DIR  = os.path.join(PROJECT_ROOT, "resume-engine", "scoring")

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
    REWRITE_FALLBACK_MODEL,
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

AUDIT_FLUSH_EVERY = 5

# ---------------------------------------------------------------------------
# STARTUP SNAPSHOT
# ---------------------------------------------------------------------------
# Stage 1 overwrites bullet-bank-keepers-audited.csv with a fresh copy
# of bullet-bank-keepers.csv (which has no source_cluster_id values).
# Stage 3 needs the IDs that were stamped by backfill_cluster_ids.py or
# by a prior Stage 4 run.  Capture them NOW, before any file writes happen.
#
# These module-level sets are populated once at import time and never
# mutated by Stage 1's overwrite.
# ---------------------------------------------------------------------------

def _read_cluster_ids_from_file(path: str) -> set:
    """Return the set of source_cluster_id values recorded in a keepers file."""
    ids: set = set()
    if not os.path.exists(path):
        return ids
    try:
        df = pd.read_csv(path, usecols=lambda c: c == "source_cluster_id")
        raw = df["source_cluster_id"].dropna()
        for v in raw:
            sv = str(v).strip()
            if sv and sv.lower() not in ("", "nan"):
                try:
                    ids.add(int(float(sv)))
                except (ValueError, TypeError):
                    pass
    except Exception:
        pass
    return ids


def _read_bullets_from_file(path: str) -> set:
    bullets: set = set()
    if not os.path.exists(path):
        return bullets
    try:
        df = pd.read_csv(path, usecols=["Bullet Point"])
        bullets.update(df["Bullet Point"].dropna().str.strip().tolist())
    except Exception:
        pass
    return bullets


def _read_cluster_id_map_from_file(path: str) -> dict:
    """
    Return a dict of {bullet_text: source_cluster_id_str} from a keepers file.
    Used to re-attach source_cluster_id values after Stage 1 overwrites the
    audited file from keepers.csv (which lacks the column).
    """
    mapping: dict = {}
    if not os.path.exists(path):
        return mapping
    try:
        df = pd.read_csv(path, usecols=["Bullet Point", "source_cluster_id"])
        for _, row in df.iterrows():
            bp = str(row.get("Bullet Point", "")).strip()
            v  = row.get("source_cluster_id", "")
            sv = str(v).strip() if pd.notna(v) else ""
            if bp and sv and sv.lower() not in ("", "nan"):
                try:
                    mapping[bp] = str(int(float(sv)))
                except (ValueError, TypeError):
                    mapping[bp] = sv
    except Exception:
        pass
    return mapping


# Capture pre-Stage-1 state immediately on module load.
_STARTUP_DONE_IDS: set = (
    _read_cluster_ids_from_file(KEEPERS_IN)
    | _read_cluster_ids_from_file(KEEPERS_AUDITED)
)
_STARTUP_DONE_BULLETS: set = (
    _read_bullets_from_file(KEEPERS_IN)
    | _read_bullets_from_file(KEEPERS_AUDITED)
)
# Full bullet → cluster_id map captured before Stage 1 can overwrite the file.
# Stage 1 merges this back in after writing so the column is never lost.
_STARTUP_CLUSTER_ID_MAP: dict = _read_cluster_id_map_from_file(KEEPERS_AUDITED)


def _all_known_keeper_cluster_ids() -> set:
    """
    Returns the union of source_cluster_id values from both keepers files.
    Stage 3 calls this to skip cluster-map MANUAL rows whose cluster has
    already been processed.

    Returns the startup snapshot so Stage 1's file overwrite doesn't
    erase the IDs that backfill_cluster_ids.py stamped.
    Stage 4 appends to the file incrementally, so new IDs written during
    the current run are added to the snapshot dynamically.
    """
    # Re-read KEEPERS_AUDITED live so Stage 4 rows from the current run
    # are included if Stage 3 is called again (not typical, but safe).
    live_ids = _read_cluster_ids_from_file(KEEPERS_AUDITED)
    return _STARTUP_DONE_IDS | live_ids


def _all_known_keeper_bullets() -> set:
    """
    Secondary / fallback exclusion: returns bullet text from both keepers
    files. Catches legacy rows that predate source_cluster_id.
    """
    live_bullets = _read_bullets_from_file(KEEPERS_AUDITED)
    return _STARTUP_DONE_BULLETS | live_bullets


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

def _merge_prior_audited_progress(df_keepers: pd.DataFrame) -> pd.DataFrame:
    """Merges in audit_status/scores from an existing keepers-audited.csv
    for any bullet that's already been scored there -- independent of
    --from-audited, which has its own separate meaning (trust CLEAN rows,
    skip cluster-map Source B). This is what makes an interrupted Stage 1
    run resume correctly without needing to remember a flag."""
    if not os.path.exists(KEEPERS_AUDITED):
        return df_keepers

    try:
        df_prior = pd.read_csv(KEEPERS_AUDITED)
    except Exception:
        return df_keepers

    if "Bullet Point" not in df_prior.columns or "audit_status" not in df_prior.columns:
        return df_keepers

    prior_scored = df_prior[df_prior["audit_status"].astype(str).str.strip() != ""]
    if prior_scored.empty:
        return df_keepers

    prior_scored = prior_scored.drop_duplicates(subset="Bullet Point", keep="first")
    prior_lookup = prior_scored.set_index(prior_scored["Bullet Point"].astype(str).str.strip())

    merge_cols = [c for c in (["audit_status"] + SCORE_COLS + ["weaknesses"]) if c in prior_lookup.columns]

    restored = 0
    for idx, row in df_keepers.iterrows():
        bp = str(row.get("Bullet Point", "")).strip()
        if bp in prior_lookup.index and str(row.get("audit_status", "")).strip() == "":
            prior_row = prior_lookup.loc[bp]
            for col in merge_cols:
                df_keepers.loc[idx, col] = prior_row[col]
            restored += 1

    if restored:
        print(f"   {theme.ICONS['resume']}  Restored {restored} already-scored row(s) from a prior keepers-audited.csv run.")

    return df_keepers


def stage1_audit_keepers(
    df_keepers: pd.DataFrame,
    score_system: str,
    dry_run: bool = False,
    skip_rescore: bool = False,
    from_audited: bool = False,
) -> pd.DataFrame:
    """
    Re-score keepers that are missing scores or have manager_test != PASS.
    Adds / refreshes: accuracy_score, believability_score, clarity_score,
    ats_value, manager_test, weaknesses, audit_status.

    When --from-audited is set, rows already marked CLEAN are skipped
    entirely (no API calls, no reclassification) — they stay as-is.

    After scoring, merges source_cluster_id values back from the startup
    snapshot (_STARTUP_CLUSTER_ID_MAP) so that IDs stamped by
    backfill_cluster_ids.py are never lost when this function is called
    from a fresh keepers.csv that lacks the column.
    """
    print("\n" + "─" * 60)
    print("STAGE 1 — Audit Keepers")
    print("─" * 60)

    if "audit_status" not in df_keepers.columns:
        df_keepers["audit_status"] = ""

    df_keepers = _merge_prior_audited_progress(df_keepers)

    # When loading from the audited file, rows already marked CLEAN are
    # trusted as-is — no need to re-score or reclassify them.
    if from_audited:
        already_clean_mask = df_keepers["audit_status"].str.strip().str.upper() == "CLEAN"
        needs_score_mask = ~already_clean_mask
        print(f"   ⚡ --from-audited mode: trusting existing CLEAN rows.")
    else:
        needs_score_mask = df_keepers.apply(
            lambda r: not _has_scores(r) or str(r.get("manager_test", "")).strip().upper() != "PASS",
            axis=1,
        )
        already_clean_mask = ~needs_score_mask

    to_score = df_keepers[needs_score_mask]
    already_clean = df_keepers[already_clean_mask]

    print(f"   Total keepers:         {len(df_keepers)}")
    print(f"   Already CLEAN (PASS):  {len(already_clean)}")
    print(f"   Need scoring/review:   {len(to_score)}")

    # Mark already-clean rows immediately
    df_keepers.loc[already_clean_mask, "audit_status"] = "CLEAN"

    if to_score.empty:
        print("   {theme.ICONS['success']} All keepers already clean — no scoring needed.")
    elif skip_rescore:
        print("   ⏭️  --skip-rescore set: classifying with existing scores, no API calls.")
        for idx in to_score.index:
            df_keepers.loc[idx, "audit_status"] = _audit_status(df_keepers.loc[idx])
    else:
        total = len(to_score)
        bullets_since_flush = 0
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

            bullets_since_flush += 1
            is_last = (i == total)
            if bullets_since_flush >= AUDIT_FLUSH_EVERY or is_last:
                df_keepers.to_csv(KEEPERS_AUDITED, index=False)
                bullets_since_flush = 0
                print(f"   {theme.ICONS['save']} Flushed audited keepers ({i}/{total} scored so far).")

            if i < total:
                time.sleep(SLEEP_BETWEEN_BULLETS)

        n_clean   = (df_keepers["audit_status"] == "CLEAN").sum()
        n_rewrite = (df_keepers["audit_status"] == "NEEDS_REWRITE").sum()
        n_manual  = (df_keepers["audit_status"] == "MANUAL").sum()
        print(f"\n   Stage 1 complete → CLEAN: {n_clean} | NEEDS_REWRITE: {n_rewrite} | MANUAL: {n_manual}")

    # ------------------------------------------------------------------
    # Restore source_cluster_id from the startup snapshot.
    # keepers.csv never has this column; keepers-audited.csv does after
    # backfill_cluster_ids.py has run.  Without this merge, every Stage 1
    # write would silently wipe the column, causing Stage 3 to see 0
    # known IDs and re-queue all 262 MANUAL bullets on every --auto-rewrite
    # run.
    # ------------------------------------------------------------------
    if "source_cluster_id" not in df_keepers.columns:
        df_keepers["source_cluster_id"] = ""

    if _STARTUP_CLUSTER_ID_MAP:
        restored = 0
        for idx, row in df_keepers.iterrows():
            current = str(row.get("source_cluster_id", "")).strip()
            if current and current.lower() not in ("", "nan"):
                continue  # already has an ID — leave it alone
            bp = str(row.get("Bullet Point", "")).strip()
            stamped = _STARTUP_CLUSTER_ID_MAP.get(bp, "")
            if stamped:
                df_keepers.loc[idx, "source_cluster_id"] = stamped
                restored += 1
        if restored:
            print(f"   {theme.ICONS['resume']} Restored {restored} source_cluster_id value(s) from pre-Stage-1 snapshot.")

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

    NOT_FOUND entries are expected and normal: keepers that are rewrites will
    not match any row in the cluster map verbatim. They are counted silently
    and shown only as a summary line at the end.
    """
    print("\n" + "─" * 60)
    print("STAGE 2 — Diff Against Cluster Map")
    print("─" * 60)

    # Prefer updated map; fall back to original
    if os.path.exists(CLUSTER_MAP_UPDATED):
        map_path = CLUSTER_MAP_UPDATED
        print(f"   Using updated cluster map: {os.path.basename(map_path)}")
    elif os.path.exists(CLUSTER_MAP_IN):
        map_path = CLUSTER_MAP_IN
        print(f"   {theme.ICONS['warning']}  Updated map not found — falling back to: {os.path.basename(map_path)}")
    else:
        print("   {theme.ICONS['warning']}  No cluster map found — skipping Stage 2.")
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
    n_not_found = 0  # expected: rewrites won't match cluster map text verbatim

    for _, row in df_keepers.iterrows():
        bp = str(row.get("Bullet Point", "")).strip()
        map_status = map_status_lookup.get(bp, "NOT_FOUND")

        if map_status == "MANUAL":
            # Actionable: keeper is CLEAN but cluster map still shows MANUAL
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
            # Normal: rewritten bullets live in keepers but not in the cluster map verbatim.
            # Count silently; do NOT append to discrepancies.
            n_not_found += 1

    df_disc = pd.DataFrame(discrepancies)
    print(f"   Keepers checked:          {len(df_keepers)}")
    print(f"   Not found in cluster map: {n_not_found}  (expected — these are rewrites ✓)")
    print(f"   Actionable discrepancies: {len(df_disc)}")

    if not df_disc.empty:
        df_disc.to_csv(DISCREPANCIES_OUT, index=False)
        print(f"   {theme.ICONS['save']} Discrepancies written → {os.path.basename(DISCREPANCIES_OUT)}")
        print("   Entries (MANUAL in cluster map, CLEAN in keepers):")
        for _, d in df_disc.iterrows():
            print(f"      {theme.ICONS['warning']}  [{d['map_status']}] {str(d['Bullet Point'])[:70]}")
    else:
        print("   {theme.ICONS['success']} No actionable discrepancies — keepers and cluster map are in sync.")

    return df_disc


# ---------------------------------------------------------------------------
# STAGE 3: TRIAGE QUEUE
# ---------------------------------------------------------------------------

def stage3_build_rewrite_queue(
    df_keepers: pd.DataFrame,
    from_audited: bool = False,
) -> pd.DataFrame:
    """
    Builds the ranked rewrite queue from:
      - NEEDS_REWRITE / MANUAL rows from the audited keepers (Stage 1)
      - MANUAL rows from the cluster map that aren't already processed
        (Source B — SKIPPED when --from-audited is set, since the audited
        file is already the source of truth and we only want to retry the
        stragglers, not re-inflate the queue with cluster-map rows)

    audit-rewrite-queue.csv is ALWAYS overwritten on every run, even when
    the queue is empty. This prevents a stale file from a prior run from
    misleading you into thinking there is still work to do.

    Exclusion uses cluster_id as the primary key (stored in
    source_cluster_id on saved keeper rows) so that bullets already
    processed by a prior Stage 4 run are not re-queued even though the
    saved bullet text differs from the original cluster-map bullet text.
    Falls back to bullet-text matching for rows with no cluster_id.

    Sorted by composite score ascending (worst first).
    """
    print("\n" + "─" * 60)
    print("STAGE 3 — Triage Queue")
    print("─" * 60)

    queue_rows = []

    # Source A: keepers that need attention (MANUAL / NEEDS_REWRITE from Stage 1)
    keeper_bad_mask = df_keepers["audit_status"].isin(["NEEDS_REWRITE", "MANUAL"])
    df_keeper_bad = df_keepers[keeper_bad_mask].copy()
    df_keeper_bad["queue_source"] = "keeper_audit"
    queue_rows.append(df_keeper_bad)
    print(f"   From keeper audit (NEEDS_REWRITE + MANUAL): {len(df_keeper_bad)}")

    # Source B: MANUAL bullets in cluster map not already processed.
    # SKIPPED when --from-audited is set — the audited file is the source
    # of truth, and pulling cluster-map MANUALs would re-inflate the queue
    # back to the full original size (exactly the problem we're fixing).
    if from_audited:
        print("   Source B (cluster-map MANUAL): SKIPPED — --from-audited mode.")
        print("   Only retrying MANUAL/NEEDS_REWRITE rows from keepers-audited.csv.")
    else:
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

            # PRIMARY exclusion: by cluster_id
            done_ids = _all_known_keeper_cluster_ids()
            before   = len(df_map_manual)

            if done_ids and "cluster_id" in df_map_manual.columns:
                def _to_int_id(v):
                    try:
                        return int(float(str(v)))
                    except (ValueError, TypeError):
                        return None

                df_map_manual = df_map_manual[
                    ~df_map_manual["cluster_id"].apply(_to_int_id).isin(done_ids)
                ].copy()

            # SECONDARY / FALLBACK exclusion: by bullet text
            all_keeper_bullets = _all_known_keeper_bullets()
            df_map_manual = df_map_manual[
                ~df_map_manual["Bullet Point"].str.strip().isin(all_keeper_bullets)
            ].copy()

            excluded = before - len(df_map_manual)
            if excluded:
                print(f"   Excluded {excluded} already-processed bullets (found in keepers or keepers-audited)")

            # Carry over scores if present in the cluster map
            for col in SCORE_COLS:
                if col not in df_map_manual.columns:
                    df_map_manual[col] = None

            df_map_manual["queue_source"] = "cluster_map_manual"
            queue_rows.append(df_map_manual)
            print(f"   From cluster map MANUAL (not in keepers): {len(df_map_manual)}")
        else:
            print("   {theme.ICONS['warning']}  Cluster map not found — skipping cluster-map MANUAL source.")

    # ------------------------------------------------------------------
    # ALWAYS overwrite the queue file — even when empty.
    # A stale non-empty file from a prior run must never survive a clean
    # run that produced zero work items. Write the header-only CSV first,
    # then overwrite again below if there are actual rows.
    # ------------------------------------------------------------------
    pd.DataFrame(columns=["Bullet Point", "queue_source", "composite_score", "queue_rank"]).to_csv(
        REWRITE_QUEUE_OUT, index=False
    )

    if not queue_rows or all(df.empty for df in queue_rows):
        print("   {theme.ICONS['success']} Queue is empty — nothing to rewrite!")
        print(f"   {theme.ICONS['save']} Rewrite queue cleared → {os.path.basename(REWRITE_QUEUE_OUT)} (0 rows)")
        return pd.DataFrame()

    df_queue = pd.concat(queue_rows, ignore_index=True)

    # Deduplicate on bullet text
    before_dedup = len(df_queue)
    df_queue = df_queue.drop_duplicates(subset=["Bullet Point"], keep="first").copy()
    print(f"   Deduplicated: {before_dedup} → {len(df_queue)} unique bullets")

    if df_queue.empty:
        print("   {theme.ICONS['success']} Queue is empty — nothing to rewrite!")
        print(f"   {theme.ICONS['save']} Rewrite queue cleared → {os.path.basename(REWRITE_QUEUE_OUT)} (0 rows)")
        return pd.DataFrame()

    # Rank worst-first by composite score
    df_queue["composite_score"] = df_queue.apply(_composite, axis=1)
    df_queue = df_queue.sort_values("composite_score", ascending=True).reset_index(drop=True)
    df_queue["queue_rank"] = df_queue.index + 1

    df_queue.to_csv(REWRITE_QUEUE_OUT, index=False)
    print(f"   {theme.ICONS['save']} Rewrite queue written ({len(df_queue)} bullets) → {os.path.basename(REWRITE_QUEUE_OUT)}")
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
    rewrite_system_gemma: str,
    score_system: str,
    df_keepers: pd.DataFrame,
    limit: int = None,
    dry_run: bool = False,
) -> pd.DataFrame:
    """
    Passes each queued bullet through process_bullet() from rewrite_bullets.py.
    KEEP results are appended to the audited keepers CSV.

    Records source_cluster_id on each saved keeper row so that Stage 3 can
    exclude that cluster on the next run by ID rather than by bullet text.
    """
    print("\n" + "─" * 60)
    print("STAGE 4 — Auto-Rewrite")
    print("─" * 60)

    if df_queue.empty:
        print("   {theme.ICONS['success']} Queue is empty — nothing to auto-rewrite.")
        return df_keepers

    df_run = df_queue.copy()
    if limit:
        df_run = df_run.head(limit)
        print(f"   --limit set: processing {limit} of {len(df_queue)} queued bullets.")

    total  = len(df_run)
    n_keep = 0
    n_manual = 0

    for i, (_, row) in enumerate(df_run.iterrows(), 1):
        bullet_preview = str(row.get("Bullet Point", ""))[:60]
        print(f"\n{chr(9472) * 60}")
        print(f"[{i}/{total}] {bullet_preview}...")
        print(f"   Source: {row.get('queue_source', '')}  "
              f"Composite: {row.get('composite_score', '?')}")

        result = process_bullet(
            row=row,
            kb=kb,
            rewrite_system=rewrite_system,
            rewrite_system_gemma=rewrite_system_gemma,
            score_system=score_system,
            dry_run=dry_run,
            # These bullets already failed a first Gemma-led pass (that's
            # exactly how they ended up queued here) -- start straight on
            # flash-lite rather than spending another round of Gemma
            # attempts/backoff on bullets already known to need the
            # stronger model.
            start_model=REWRITE_FALLBACK_MODEL,
        )

        if result["rewrite_status"] == "KEEP":
            n_keep += 1

            # Record the originating cluster_id so Stage 3 can exclude it
            # by ID on the next run (works even though the bullet text changed).
            source_cluster_id = ""
            if "cluster_id" in row and pd.notna(row["cluster_id"]):
                try:
                    source_cluster_id = int(float(str(row["cluster_id"])))
                except (ValueError, TypeError):
                    source_cluster_id = str(row["cluster_id"])

            keeper_row = {
                "Bullet Point":      result["final_bullet"],
                "Role / Company":    row.get("Role / Company", ""),
                "Tags":              row.get("Tags", ""),
                "source":            "audit_rewrite",
                "source_cluster_id": source_cluster_id,
                "rewrite_attempts":  result.get("rewrite_attempts", 0),
                "rewrite_reasoning": result.get("rewrite_reasoning", ""),
                "context_gaps":      result.get("context_gaps", ""),
                "audit_status":      "CLEAN",
                **{col: result.get(col, "") for col in SCORE_COLS},
                "weaknesses":        result.get("weaknesses", ""),
            }
            df_keepers = append_keeper(df_keepers, keeper_row, KEEPERS_AUDITED)
            print(f"   {theme.ICONS['success']} KEEPER saved (source_cluster_id={source_cluster_id}).")
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
    parser.add_argument(
        "--from-audited",
        action="store_true",
        help=(
            "Load from keepers-audited.csv instead of keepers.csv. "
            "CLEAN rows are trusted as-is (no API calls). Only MANUAL/NEEDS_REWRITE "
            "rows are re-processed. Cluster-map Source B is skipped entirely to "
            "prevent queue inflation. Use this after a completed run to retry only "
            "the stragglers without re-processing the full set."
        ),
    )
    args = parser.parse_args()

    print("\n" + "#" * 60)
    print("  audit_keepers.py  —  Keeper Audit Pipeline")
    print("#" * 60)
    print(f"  dry_run:      {args.dry_run}")
    print(f"  skip_rescore: {args.skip_rescore}")
    print(f"  auto_rewrite: {args.auto_rewrite}")
    print(f"  from_audited: {args.from_audited}")
    print(f"  limit:        {args.limit}")

    # --- Resolve source file ---
    if args.from_audited and os.path.exists(KEEPERS_AUDITED):
        source_file = KEEPERS_AUDITED
        print(f"\n   ⚡ --from-audited: loading from {os.path.basename(KEEPERS_AUDITED)}")
        print(   "      CLEAN rows will be skipped; cluster-map Source B skipped entirely.")
    else:
        source_file = KEEPERS_IN
        if args.from_audited:
            print(f"\n   {theme.ICONS['warning']}  --from-audited set but {os.path.basename(KEEPERS_AUDITED)} not found.")
            print(   "      Falling back to keepers.csv.")

    if not os.path.exists(source_file):
        print(f"\n{theme.ICONS['error']}  {source_file} not found. Run rewrite_bullets.py first.")
        sys.exit(1)

    df_keepers = pd.read_csv(source_file)
    df_keepers = ensure_writable_dtypes(df_keepers)

    # Ensure all expected columns exist
    for col in KEEPER_COLS + ["audit_status"]:
        if col not in df_keepers.columns:
            df_keepers[col] = ""

    print(f"\n   📂 Loaded keepers: {len(df_keepers)} rows from {os.path.basename(source_file)}")
    print(f"   📌 Startup snapshot: {len(_STARTUP_DONE_IDS)} cluster IDs "
          f"| {len(_STARTUP_DONE_BULLETS)} bullet texts already processed")

    # --- Load rules + KB only when scoring is needed ---
    rules = kb = rewrite_system = rewrite_system_gemma = score_system = None

    needs_api = (
        (not args.skip_rescore)
        or args.auto_rewrite
    )

    if needs_api:
        rules = RulesBundle(RULES_DIR, SCORING_DIR)
        kb    = KnowledgeBase()

        # Warm segment cache over the full keepers set (cheapest: one pass)
        kb.warm_segment_cache(df_keepers)
        rewrite_system, rewrite_system_gemma, score_system = build_system_prompts(rules, kb)

    # ── Stage 1 ───────────────────────────────────────────────────────────────
    df_keepers = stage1_audit_keepers(
        df_keepers,
        score_system=score_system or "",
        dry_run=args.dry_run,
        skip_rescore=args.skip_rescore,
        from_audited=args.from_audited,
    )

    # Save audited keepers after Stage 1.
    # source_cluster_id values are already restored inside stage1_audit_keepers()
    # from _STARTUP_CLUSTER_ID_MAP, so this write preserves them correctly.
    df_keepers.to_csv(KEEPERS_AUDITED, index=False)
    print(f"\n   {theme.ICONS['save']} Audited keepers → {os.path.basename(KEEPERS_AUDITED)}")

    # ── Stage 2 ───────────────────────────────────────────────────────────────
    _df_disc = stage2_diff_cluster_map(df_keepers)

    # ── Stage 3 ───────────────────────────────────────────────────────────────
    # Pass from_audited so Stage 3 knows to skip Source B (cluster-map MANUALs)
    df_queue = stage3_build_rewrite_queue(df_keepers, from_audited=args.from_audited)

    # ── Stage 4 (optional) ───────────────────────────────────────────────
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
                rewrite_system_gemma=rewrite_system_gemma,
                score_system=score_system,
                df_keepers=df_keepers,
                limit=args.limit,
                dry_run=args.dry_run,
            )
            # Final save after Stage 4 rewrites are appended
            df_keepers.to_csv(KEEPERS_AUDITED, index=False)
            print(f"\n   {theme.ICONS['save']} Final audited keepers saved → {os.path.basename(KEEPERS_AUDITED)}")
    else:
        if not df_queue.empty:
            print(
                f"\n   {len(df_queue)} bullets queued. "
                f"Run with --auto-rewrite to process them."
            )

    print("\n" + "─" * 60)
    print("  {theme.ICONS['success']}  audit_keepers.py complete")
    print(f"     Audited keepers  → {os.path.basename(KEEPERS_AUDITED)}")
    print(f"     Discrepancies    → {os.path.basename(DISCREPANCIES_OUT)}")
    print(f"     Rewrite queue    → {os.path.basename(REWRITE_QUEUE_OUT)}")
    print("─" * 60 + "\n")


if __name__ == "__main__":
    main()
