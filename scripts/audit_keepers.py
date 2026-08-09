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

    When loading from an existing keepers-audited.csv (the default -- see
    "Source resolution" below), Source B (cluster-map MANUAL rows) is
    skipped entirely. The audited file is already the source of truth;
    only the MANUAL/NEEDS_REWRITE rows from that file need retrying.

  Stage 4 — Optional Auto-Rewrite
    If --auto-rewrite flag is passed, hands each queued bullet to
    process_bullet() imported directly from rewrite_bullets.py.
    Uses the same sleep constants and process_bullet() logic — no new
    rewrite code here.
    Records source_cluster_id on saved keeper rows so Stage 3 can
    exclude them by ID on the next run.

    A bullet that stays MANUAL after 3 rewrite attempts is recorded (by
    cluster_id) in audit-manual-attempts.csv -- NOT in
    bullet-bank-keepers-audited.csv, since embed_bullet_bank.py and
    orchestrator.py's mine_bullet_bank() treat every row of that file as
    resume-ready with no audit_status filtering, and a failed bullet
    (manager_test=FAIL) has no business being mined into a real resume.
    Stage 3 excludes these cluster_ids from Source B on future runs, same
    as it already does for successfully-kept clusters -- otherwise every
    run without --retry-manual would re-attempt the exact same failures
    from scratch, burning API calls with the same likely outcome. Pass
    --retry-manual to include them again (e.g. after adjusting a rule).

Outputs (profiles/<profile>/knowledge_base/):
  bullet-bank-keepers-audited.csv    keepers with refreshed scores + audit_status
  audit-manual-attempts.csv          cluster_ids that stayed MANUAL after a Stage 4
                                     attempt -- excluded from future queues unless
                                     --retry-manual is passed
  audit-discrepancies.csv            cluster-map / keeper mismatches
  audit-rewrite-queue.csv            ranked rewrite queue (Stage 3) — always
                                     overwritten; empty file = nothing left to do

Usage:
  python audit_keepers.py                    # run all four stages, no auto-rewrite --
                                             # loads from keepers-audited.csv by default
                                             # whenever it already exists (see "Source
                                             # resolution" below), so any manual edits
                                             # made directly to that file (e.g. a company
                                             # retag or a wording fix) are never silently
                                             # discarded by a routine re-run.
  python audit_keepers.py --dry-run          # score pass is mocked, no API calls
  python audit_keepers.py --auto-rewrite     # Stage 4: run the queue through rewriter
  python audit_keepers.py --auto-rewrite --limit 10
  python audit_keepers.py --skip-rescore     # skip Stage 1 API calls, use existing scores
  python audit_keepers.py --auto-rewrite --retry-manual
                                             # re-attempt clusters that previously
                                             # stayed MANUAL instead of skipping them
  python audit_keepers.py --rebuild-from-keepers
                                             # DESTRUCTIVE: ignore keepers-audited.csv
                                             # entirely and rebuild fresh from
                                             # keepers.csv -- discards any correction
                                             # that was only ever applied to the audited
                                             # file (audit_status/scores are also lost
                                             # for CLEAN rows, since keepers.csv doesn't
                                             # carry them). Only pass this if you
                                             # deliberately want to start over.

Source resolution:
  If bullet-bank-keepers-audited.csv already exists, it is loaded by
  default (rows already marked CLEAN are trusted as-is -- no API calls;
  cluster-map Source B is skipped entirely to prevent queue inflation).
  This makes the audited file the durable source of truth: any manual
  correction made directly to it (a retag, a reworded bullet, a fixed
  metric) survives every future run without needing to remember a flag.
  Falls back to keepers.csv only if no audited file exists yet, or if
  --rebuild-from-keepers is passed explicitly.
"""

import argparse
import os
import sys
import time
from datetime import datetime

import pandas as pd

import cli_art
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
MANUAL_ATTEMPTS_OUT = os.path.join(KB_DIR, "audit-manual-attempts.csv")

MANUAL_ATTEMPTS_COLS = [
    "cluster_id", "Bullet Point", "Role / Company", "Tags",
    "composite_score", "manager_test", "rewrite_attempts", "last_attempted",
]


def resolve_source_file(rebuild_from_keepers: bool, keepers_in: str, keepers_audited: str) -> str:
    """Picks which file main() loads keepers from. Defaults to
    keepers_audited whenever it already exists -- it's the durable
    source of truth and may carry manual corrections (a company retag, a
    reworded bullet, a fixed metric) that were never backported to
    keepers_in. Defaulting to keepers_in instead would silently discard
    those on every routine re-run. rebuild_from_keepers is the explicit,
    clearly-named opt-in for deliberately starting over from scratch."""
    if rebuild_from_keepers:
        return keepers_in
    if os.path.exists(keepers_audited):
        return keepers_audited
    return keepers_in


def _normalize_cluster_id(value) -> str:
    """Renders a cluster_id value the same way regardless of whether
    pandas read its source column as int64 or float64 -- the deciding
    factor is just whether ANY row in that column was blank/NaN at read
    time (a single blank cluster_id, e.g. from a just-triaged row with
    none assigned yet, forces pandas to upcast the WHOLE column to
    float64, turning "37" into 37.0). Comparing raw str(value) across two
    independently-read CSVs breaks exactly when one file has a blank
    somewhere and the other doesn't -- "37" vs "37.0" silently never
    match, even though every already-processed row in both files
    represents the same real ID. Whole numbers (int, or float with no
    fractional part) always render without a trailing ".0"; anything
    else (a non-numeric ID, if one ever exists) falls back to a plain
    stripped string. Returns "" for blank/NaN."""
    if value is None:
        return ""
    s = str(value).strip()
    if not s or s.lower() == "nan":
        return ""
    try:
        f = float(s)
    except ValueError:
        return s
    return str(int(f)) if f.is_integer() else s


def merge_new_rows_from_keepers_in(df_audited: pd.DataFrame, df_keepers_in: pd.DataFrame) -> tuple:
    """Unions any row from df_keepers_in (bullet-bank-keepers.csv, the
    live landing zone triage_needs_review.py appends new KEEP rows into
    on every real resume-build session) that isn't already represented
    in df_audited. Returns (merged_df, count_of_new_rows).

    Matches by source_cluster_id first (falling back to Bullet Point text
    only for rows with no cluster_id) -- the same primary/secondary
    matching Stage 3 already uses, and deliberately NOT text-only. A
    manual correction to the audited file (a retag, a reworded bullet, a
    fixed metric -- exactly what this file exists to protect) changes the
    bullet's text, so text-only matching would see the now-different
    audited row as unrelated to its stale keepers_in counterpart and
    wrongly re-add the old, uncorrected version as a "new" duplicate.
    IDs are compared via _normalize_cluster_id(), not raw str() -- see
    its docstring for the int64/float64 dtype mismatch this guards
    against (confirmed for real: it misclassified ~810 already-processed
    rows as "new" the first time this ran against the live bank, the
    moment a single freshly-triaged row with a blank cluster_id entered
    keepers.csv).

    Missing columns on the new rows are filled with "" rather than
    dropped, so a schema mismatch between the two files doesn't silently
    lose data."""
    if "Bullet Point" not in df_keepers_in.columns:
        return df_audited, 0

    known_ids = set()
    if "source_cluster_id" in df_audited.columns:
        known_ids = {
            nid for nid in df_audited["source_cluster_id"].map(_normalize_cluster_id) if nid
        }
    known_texts = set(df_audited.get("Bullet Point", pd.Series(dtype=str)).astype(str).str.strip())

    def _is_new(row) -> bool:
        cid = _normalize_cluster_id(row.get("source_cluster_id"))
        if cid:
            return cid not in known_ids
        return str(row.get("Bullet Point", "")).strip() not in known_texts

    new_rows = df_keepers_in[df_keepers_in.apply(_is_new, axis=1)].copy()
    if new_rows.empty:
        return df_audited, 0
    for col in df_audited.columns:
        if col not in new_rows.columns:
            new_rows[col] = ""
    new_rows = new_rows[df_audited.columns]
    merged = pd.concat([df_audited, new_rows], ignore_index=True)
    return merged, len(new_rows)

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

def _read_cluster_ids_from_file(path: str, col: str = "source_cluster_id") -> set:
    """Return the set of cluster ID values recorded in a CSV's `col` column.
    Keepers files use "source_cluster_id" (the default); audit-manual-attempts.csv
    uses "cluster_id" (see _known_manual_attempt_cluster_ids())."""
    ids: set = set()
    if not os.path.exists(path):
        return ids
    try:
        df = pd.read_csv(path, usecols=lambda c: c == col)
        raw = df[col].dropna()
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


def _known_manual_attempt_cluster_ids() -> set:
    """Cluster IDs that stayed MANUAL on a prior Stage 4 attempt (read live,
    same as _all_known_keeper_cluster_ids() -- Stage 4 updates this file
    incrementally within a run, so a re-attempted cluster in the same run
    is picked up immediately)."""
    return _read_cluster_ids_from_file(MANUAL_ATTEMPTS_OUT, col="cluster_id")


def _record_manual_attempt(row: "pd.Series", cluster_id, composite_score, manager_test, rewrite_attempts) -> None:
    """Upsert one cluster's failed-attempt record into audit-manual-attempts.csv
    so Stage 3 can exclude it from future queues (see _known_manual_attempt_cluster_ids()).
    Keyed by cluster_id -- a retried cluster (via --retry-manual) overwrites its
    prior row rather than accumulating duplicates."""
    new_row = {
        "cluster_id":       cluster_id,
        "Bullet Point":     row.get("Bullet Point", ""),
        "Role / Company":   row.get("Role / Company", ""),
        "Tags":             row.get("Tags", ""),
        "composite_score":  composite_score,
        "manager_test":     manager_test,
        "rewrite_attempts": rewrite_attempts,
        "last_attempted":   datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    }
    if os.path.exists(MANUAL_ATTEMPTS_OUT):
        df = pd.read_csv(MANUAL_ATTEMPTS_OUT)
    else:
        df = pd.DataFrame(columns=MANUAL_ATTEMPTS_COLS)
    if cluster_id != "" and cluster_id is not None and "cluster_id" in df.columns:
        df = df[df["cluster_id"].astype(str) != str(cluster_id)]
    df = pd.concat([df, pd.DataFrame([new_row])], ignore_index=True)
    df.to_csv(MANUAL_ATTEMPTS_OUT, index=False)


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
    whether this run is loading from the audited file (that has its own
    separate meaning: trust CLEAN rows, skip cluster-map Source B). This
    is what makes an interrupted Stage 1 run resume correctly without
    needing to remember a flag. Only restores audit_status/score columns
    by exact Bullet Point text match -- it does NOT restore Role/Company
    or other manual corrections, which is why main()'s source resolution
    defaults to loading the audited file wholesale instead of trying to
    diff-and-reapply corrections onto a fresh keepers.csv."""
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
        cli_art.cli_info(f"Restored {restored} already-scored row(s) from a prior keepers-audited.csv run.")

    return df_keepers


def stage1_audit_keepers(
    df_keepers: pd.DataFrame,
    score_system: str,
    dry_run: bool = False,
    skip_rescore: bool = False,
    using_audited_source: bool = False,
) -> pd.DataFrame:
    """
    Re-score keepers that are missing scores or have manager_test != PASS.
    Adds / refreshes: accuracy_score, believability_score, clarity_score,
    ats_value, manager_test, weaknesses, audit_status.

    When using_audited_source is True (df_keepers was loaded from an
    existing keepers-audited.csv -- the default whenever that file
    exists, see main()'s "Source resolution"), rows already marked CLEAN
    are skipped entirely (no API calls, no reclassification) — they stay
    as-is.

    After scoring, merges source_cluster_id values back from the startup
    snapshot (_STARTUP_CLUSTER_ID_MAP) so that IDs stamped by
    backfill_cluster_ids.py are never lost when this function is called
    from a fresh keepers.csv that lacks the column.
    """
    cli_art.cli_info("\n" + "─" * 60)
    cli_art.cli_info("STAGE 1 — Audit Keepers")
    cli_art.cli_info("─" * 60)

    if "audit_status" not in df_keepers.columns:
        df_keepers["audit_status"] = ""
    elif df_keepers["audit_status"].dtype != object:
        # A fully-blank column round-trips through CSV as all-NaN and gets
        # inferred as float64; pandas 3.x raises LossySetitemError on any
        # later `.loc[...] = "CLEAN"` into it, so force it back to a
        # string-holding dtype before anything writes into it.
        df_keepers["audit_status"] = df_keepers["audit_status"].astype(object).fillna("")

    df_keepers = _merge_prior_audited_progress(df_keepers)

    # When loading from the audited file, rows already marked CLEAN are
    # trusted as-is — no need to re-score or reclassify them.
    if using_audited_source:
        already_clean_mask = df_keepers["audit_status"].str.strip().str.upper() == "CLEAN"
        needs_score_mask = ~already_clean_mask
        cli_art.cli_info("⚡ Loading from keepers-audited.csv: trusting existing CLEAN rows.")
    else:
        needs_score_mask = df_keepers.apply(
            lambda r: not _has_scores(r) or str(r.get("manager_test", "")).strip().upper() != "PASS",
            axis=1,
        )
        already_clean_mask = ~needs_score_mask

    to_score = df_keepers[needs_score_mask]
    already_clean = df_keepers[already_clean_mask]

    cli_art.cli_info(f"   Total keepers:         {len(df_keepers)}")
    cli_art.cli_info(f"   Already CLEAN (PASS):  {len(already_clean)}")
    cli_art.cli_info(f"   Need scoring/review:   {len(to_score)}")

    # Mark already-clean rows immediately
    df_keepers.loc[already_clean_mask, "audit_status"] = "CLEAN"

    if to_score.empty:
        cli_art.cli_success("All keepers already clean — no scoring needed.")
    elif skip_rescore:
        cli_art.cli_info("⏭️  --skip-rescore set: classifying with existing scores, no API calls.")
        for idx in to_score.index:
            df_keepers.loc[idx, "audit_status"] = _audit_status(df_keepers.loc[idx])
    else:
        total = len(to_score)
        bullets_since_flush = 0
        for i, (idx, row) in enumerate(to_score.iterrows(), 1):
            bullet = str(row.get("Bullet Point", "")).strip()
            tags   = str(row.get("Tags", ""))
            role_company = str(row.get("Role / Company", ""))
            
            cli_art.cli_info(f"\n   [{i}/{total}] Scoring: {bullet[:70]}...")

            scores = score_bullet(bullet, tags, score_system, role_company=role_company, dry_run=dry_run)

            for col in SCORE_COLS:
                if col in NUMERIC_SCORE_COLS:
                    df_keepers.loc[idx, col] = pd.to_numeric(scores.get(col, None), errors="coerce")
                else:
                    df_keepers.loc[idx, col] = _safe_str(scores.get(col, ""))
            df_keepers.loc[idx, "weaknesses"] = _safe_str(scores.get("weaknesses", ""))
            df_keepers.loc[idx, "audit_status"] = _audit_status(df_keepers.loc[idx])

            status = df_keepers.loc[idx, "audit_status"]
            mgr    = str(scores.get("manager_test", "")).upper()
            cli_art.cli_info(f"   → status={status}  mgr={mgr}  acc={scores.get('accuracy_score')}  bel={scores.get('believability_score')}  cla={scores.get('clarity_score')}  ats={scores.get('ats_value')}")

            bullets_since_flush += 1
            is_last = (i == total)
            if bullets_since_flush >= AUDIT_FLUSH_EVERY or is_last:
                df_keepers.to_csv(KEEPERS_AUDITED, index=False)
                bullets_since_flush = 0
                cli_art.cli_success(f"Flushed audited keepers ({i}/{total} scored so far).")

            if i < total:
                time.sleep(SLEEP_BETWEEN_BULLETS)

        n_clean   = (df_keepers["audit_status"] == "CLEAN").sum()
        n_rewrite = (df_keepers["audit_status"] == "NEEDS_REWRITE").sum()
        n_manual  = (df_keepers["audit_status"] == "MANUAL").sum()
        cli_art.cli_info(f"Stage 1 complete → CLEAN: {n_clean} | NEEDS_REWRITE: {n_rewrite} | MANUAL: {n_manual}")

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
            cli_art.cli_info(f"Restored {restored} source_cluster_id value(s) from pre-Stage-1 snapshot.")

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
    cli_art.cli_info("\n" + "─" * 60)
    cli_art.cli_info("STAGE 2 — Diff Against Cluster Map")
    cli_art.cli_info("─" * 60)

    # Prefer updated map; fall back to original
    if os.path.exists(CLUSTER_MAP_UPDATED):
        map_path = CLUSTER_MAP_UPDATED
        cli_art.cli_info(f"Using updated cluster map: {os.path.basename(map_path)}")
    elif os.path.exists(CLUSTER_MAP_IN):
        map_path = CLUSTER_MAP_IN
        cli_art.cli_warning(f"Updated map not found — falling back to: {os.path.basename(map_path)}")
    else:
        cli_art.cli_warning("No cluster map found — skipping Stage 2.")
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
    cli_art.cli_info(f"   Keepers checked:          {len(df_keepers)}")
    cli_art.cli_info(f"   Not found in cluster map: {n_not_found}  (expected — these are rewrites ✓)")
    cli_art.cli_info(f"   Actionable discrepancies: {len(df_disc)}")

    if not df_disc.empty:
        df_disc.to_csv(DISCREPANCIES_OUT, index=False)
        cli_art.cli_success(f"Discrepancies written → {os.path.basename(DISCREPANCIES_OUT)}")
        cli_art.cli_info("   Entries (MANUAL in cluster map, CLEAN in keepers):")
        for _, d in df_disc.iterrows():
            cli_art.cli_warning(f"[{d['map_status']}] {str(d['Bullet Point'])[:70]}")
    else:
        cli_art.cli_success("No actionable discrepancies — keepers and cluster map are in sync.")

    return df_disc


# ---------------------------------------------------------------------------
# STAGE 3: TRIAGE QUEUE
# ---------------------------------------------------------------------------

def stage3_build_rewrite_queue(
    df_keepers: pd.DataFrame,
    using_audited_source: bool = False,
    retry_manual: bool = False,
) -> pd.DataFrame:
    """
    Builds the ranked rewrite queue from:
      - NEEDS_REWRITE / MANUAL rows from the audited keepers (Stage 1)
      - MANUAL rows from the cluster map that aren't already processed
        (Source B — SKIPPED when using_audited_source is True, since the
        audited file is already the source of truth and we only want to
        retry the stragglers, not re-inflate the queue with cluster-map
        rows)

    Clusters recorded in audit-manual-attempts.csv (stayed MANUAL after a
    prior Stage 4 attempt) are also excluded from Source B by default --
    otherwise every run would blindly re-attempt the same failures with
    the same likely outcome. Pass retry_manual=True (--retry-manual) to
    include them again.

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
    cli_art.cli_info("\n" + "─" * 60)
    cli_art.cli_info("STAGE 3 — Triage Queue")
    cli_art.cli_info("─" * 60)

    queue_rows = []

    # Source A: keepers that need attention (MANUAL / NEEDS_REWRITE from Stage 1)
    keeper_bad_mask = df_keepers["audit_status"].isin(["NEEDS_REWRITE", "MANUAL"])
    df_keeper_bad = df_keepers[keeper_bad_mask].copy()

    # Exclude clusters already recorded as a failed Stage 4 attempt -- same
    # protection Source B already has below. Without this, a bullet that
    # stayed MANUAL has its keeper row deleted by stage4_auto_rewrite()'s
    # MANUAL branch, gets silently resurrected from keepers.csv by
    # merge_new_rows_from_keepers_in() on the very next run (its
    # source_cluster_id is no longer in the audited file, so it looks
    # "new"), gets rescored back to MANUAL, and lands right back here --
    # forever, with no forward progress (confirmed for real: the same 6
    # bullets kept cycling through --auto-rewrite run after run).
    if not retry_manual:
        manual_attempt_ids = _known_manual_attempt_cluster_ids()
        if manual_attempt_ids and "source_cluster_id" in df_keeper_bad.columns:
            before_a = len(df_keeper_bad)

            def _to_int_id(v):
                try:
                    return int(float(str(v)))
                except (ValueError, TypeError):
                    return None

            df_keeper_bad = df_keeper_bad[
                ~df_keeper_bad["source_cluster_id"].apply(_to_int_id).isin(manual_attempt_ids)
            ].copy()
            excluded_a = before_a - len(df_keeper_bad)
            if excluded_a:
                cli_art.console.print(f"   Excluded {excluded_a} already-attempted MANUAL bullet(s) from keeper audit "
                      f"(pass --retry-manual to include them again)", markup=False, soft_wrap=True)

    df_keeper_bad["queue_source"] = "keeper_audit"
    queue_rows.append(df_keeper_bad)
    cli_art.console.print(f"   From keeper audit (NEEDS_REWRITE + MANUAL): {len(df_keeper_bad)}", markup=False, soft_wrap=True)

    # Source B: MANUAL bullets in cluster map not already processed.
    # SKIPPED when using_audited_source is True — the audited file is the
    # source of truth, and pulling cluster-map MANUALs would re-inflate
    # the queue back to the full original size (exactly the problem
    # we're fixing).
    if using_audited_source:
        cli_art.console.print("   Source B (cluster-map MANUAL): SKIPPED — loading from keepers-audited.csv.", markup=False, soft_wrap=True)
        cli_art.console.print("   Only retrying MANUAL/NEEDS_REWRITE rows from keepers-audited.csv.", markup=False, soft_wrap=True)
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

            # PRIMARY exclusion: by cluster_id (already-kept clusters, plus
            # already-failed clusters unless --retry-manual was passed)
            done_ids = _all_known_keeper_cluster_ids()
            if not retry_manual:
                done_ids = done_ids | _known_manual_attempt_cluster_ids()
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
                suffix = "" if retry_manual else " (pass --retry-manual to include previously-failed clusters again)"
                cli_art.console.print(f"   Excluded {excluded} already-processed bullets (kept, or previously MANUAL){suffix}", markup=False, soft_wrap=True)

            # Carry over scores if present in the cluster map
            for col in SCORE_COLS:
                if col not in df_map_manual.columns:
                    df_map_manual[col] = None

            df_map_manual["queue_source"] = "cluster_map_manual"
            queue_rows.append(df_map_manual)
            cli_art.console.print(f"   From cluster map MANUAL (not in keepers): {len(df_map_manual)}", markup=False, soft_wrap=True)
        else:
            cli_art.console.print(f"   {theme.colorize_icon('warning')}  Cluster map not found — skipping cluster-map MANUAL source.", soft_wrap=True)

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
        cli_art.console.print(f"   {theme.colorize_icon('success')} Queue is empty — nothing to rewrite!", soft_wrap=True)
        cli_art.console.print(f"   {theme.colorize_icon('save')} Rewrite queue cleared → {os.path.basename(REWRITE_QUEUE_OUT)} (0 rows)", soft_wrap=True)
        return pd.DataFrame()

    df_queue = pd.concat(queue_rows, ignore_index=True)

    # Deduplicate on bullet text
    before_dedup = len(df_queue)
    df_queue = df_queue.drop_duplicates(subset=["Bullet Point"], keep="first").copy()
    cli_art.console.print(f"   Deduplicated: {before_dedup} → {len(df_queue)} unique bullets", markup=False, soft_wrap=True)

    if df_queue.empty:
        cli_art.console.print(f"   {theme.colorize_icon('success')} Queue is empty — nothing to rewrite!", soft_wrap=True)
        cli_art.console.print(f"   {theme.colorize_icon('save')} Rewrite queue cleared → {os.path.basename(REWRITE_QUEUE_OUT)} (0 rows)", soft_wrap=True)
        return pd.DataFrame()

    # Rank worst-first by composite score
    df_queue["composite_score"] = df_queue.apply(_composite, axis=1)
    df_queue = df_queue.sort_values("composite_score", ascending=True).reset_index(drop=True)
    df_queue["queue_rank"] = df_queue.index + 1

    df_queue.to_csv(REWRITE_QUEUE_OUT, index=False)
    cli_art.console.print(f"   {theme.colorize_icon('save')} Rewrite queue written ({len(df_queue)} bullets) → {os.path.basename(REWRITE_QUEUE_OUT)}", soft_wrap=True)
    cli_art.console.print(f"   Lowest composite: {df_queue['composite_score'].min():.0f}  "
          f"Highest: {df_queue['composite_score'].max():.0f}", markup=False, soft_wrap=True)

    # Print top 10 worst for easy triage
    cli_art.console.print("\n   Top 10 worst (will be rewritten first if --auto-rewrite):", markup=False, soft_wrap=True)
    for _, row in df_queue.head(10).iterrows():
        bp  = str(row.get("Bullet Point", ""))[:65]
        src = row.get("queue_source", "")
        cmp = row.get("composite_score", 0)
        mgr = str(row.get("manager_test", "")).upper()
        cli_art.console.print(f"      #{int(row['queue_rank']):>3}  [{src:<20}]  cmp={cmp:>5.0f}  mgr={mgr:<4}  {bp}...", markup=False, soft_wrap=True)

    return df_queue


# ---------------------------------------------------------------------------
# STAGE 4: AUTO-REWRITE
# ---------------------------------------------------------------------------

def _remove_rows_matching_bullet_text(df_keepers: pd.DataFrame, bullet_text: str) -> tuple:
    """Drops every row whose Bullet Point exactly matches bullet_text.
    Returns (filtered_df, count_removed). Used by stage4_auto_rewrite() to
    retire a bullet's original (pre-rewrite) row(s) -- including any
    duplicate copies of the same text -- once that bullet has been
    resolved (KEEP or MANUAL), so a superseded row never lingers
    alongside its replacement to be re-scored and re-queued forever."""
    if not bullet_text or "Bullet Point" not in df_keepers.columns:
        return df_keepers, 0
    mask = df_keepers["Bullet Point"].astype(str).str.strip() == bullet_text
    n = int(mask.sum())
    if n == 0:
        return df_keepers, 0
    return df_keepers[~mask].reset_index(drop=True), n


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
    cli_art.console.print("\n" + "─" * 60, markup=False, soft_wrap=True)
    cli_art.console.print("STAGE 4 — Auto-Rewrite", markup=False, soft_wrap=True)
    cli_art.console.print("─" * 60, markup=False, soft_wrap=True)

    if df_queue.empty:
        cli_art.console.print(f"   {theme.colorize_icon('success')} Queue is empty — nothing to auto-rewrite.", soft_wrap=True)
        return df_keepers

    df_run = df_queue.copy()
    if limit:
        df_run = df_run.head(limit)
        cli_art.console.print(f"   --limit set: processing {limit} of {len(df_queue)} queued bullets.", markup=False, soft_wrap=True)

    total  = len(df_run)
    n_keep = 0
    n_manual = 0

    for i, (_, row) in enumerate(df_run.iterrows(), 1):
        original_bullet_text = str(row.get("Bullet Point", "")).strip()
        bullet_preview = original_bullet_text[:60]
        cli_art.console.print(f"\n{chr(9472) * 60}", markup=False, soft_wrap=True)
        cli_art.console.print(f"[{i}/{total}] {bullet_preview}...", markup=False, soft_wrap=True)
        cli_art.console.print(f"   Source: {row.get('queue_source', '')}  "
              f"Composite: {row.get('composite_score', '?')}", markup=False, soft_wrap=True)

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

        # Record the originating cluster_id so Stage 3 can exclude it by ID
        # on the next run, whether this attempt ends in KEEP or MANUAL
        # (works even though the saved bullet text may differ from the
        # original cluster-map text). Source B rows (cluster map) carry
        # this under "cluster_id"; Source A rows (keepers-audited.csv)
        # carry it under "source_cluster_id" instead -- checking only
        # "cluster_id" silently produced an empty ID for every Source A
        # bullet (confirmed for real: MANUAL bullets originating from
        # keeper audit were always recorded with cluster_id="", so Stage
        # 3's manual-attempt exclusion could never match them and they
        # kept re-queuing every run).
        source_cluster_id = ""
        raw_cluster_id = row.get("cluster_id")
        if raw_cluster_id is None or pd.isna(raw_cluster_id):
            raw_cluster_id = row.get("source_cluster_id")
        if raw_cluster_id is not None and pd.notna(raw_cluster_id) and str(raw_cluster_id).strip() != "":
            try:
                source_cluster_id = int(float(str(raw_cluster_id)))
            except (ValueError, TypeError):
                source_cluster_id = str(raw_cluster_id)

        # Remove every row in df_keepers whose text exactly matches this
        # bullet's ORIGINAL (pre-rewrite) text, whether the outcome below
        # is KEEP or MANUAL. Stage 3 already deduplicates the queue by
        # exact text before processing, but df_keepers itself can still
        # hold more than one identical copy (e.g. the same achievement
        # triaged from two separate real resume-build sessions, with no
        # dedup on append) -- without this, only the ONE instance that
        # was actually processed gets resolved, and every duplicate copy
        # is left behind marked NEEDS_REWRITE/MANUAL forever, silently
        # re-scored and re-queued on every future run even after this
        # bullet has already been successfully rewritten.
        df_keepers, n_superseded = _remove_rows_matching_bullet_text(df_keepers, original_bullet_text)

        if result["rewrite_status"] == "KEEP":
            n_keep += 1

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
            cli_art.console.print(f"   {theme.colorize_icon('success')} KEEPER saved (source_cluster_id={source_cluster_id})."
                  f"{f' Removed {n_superseded} superseded duplicate row(s).' if n_superseded else ''}", soft_wrap=True)
        else:
            n_manual += 1
            _record_manual_attempt(
                row=row,
                cluster_id=source_cluster_id,
                composite_score=row.get("composite_score", ""),
                manager_test=result.get("manager_test", ""),
                rewrite_attempts=result.get("rewrite_attempts", 0),
            )
            # append_keeper() saves incrementally on the KEEP path; MANUAL
            # never touches disk otherwise, so the removal above (and any
            # future interrupted-run resumability) needs its own save
            # here rather than waiting for main()'s final save.
            df_keepers.to_csv(KEEPERS_AUDITED, index=False)
            cli_art.console.print(f"   🔧 MANUAL — best version retained, not added to keepers. "
                  f"Recorded (cluster_id={source_cluster_id}) so it won't retry every run."
                  f"{f' Removed {n_superseded} stale duplicate row(s).' if n_superseded else ''}", markup=False, soft_wrap=True)

        if i < total:
            time.sleep(SLEEP_BETWEEN_BULLETS)

    cli_art.console.print(f"\n   Stage 4 complete → KEEP: {n_keep} | MANUAL: {n_manual}", markup=False, soft_wrap=True)
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
        "--rebuild-from-keepers",
        action="store_true",
        help=(
            "DESTRUCTIVE: ignore keepers-audited.csv even if it exists, and rebuild "
            "from keepers.csv instead. Discards any correction that was only ever "
            "applied to the audited file (a retag, a reworded bullet, a fixed "
            "metric), and loses audit_status/scores for CLEAN rows too, since "
            "keepers.csv doesn't carry them. Only pass this if you deliberately "
            "want to start over -- the default (loading the audited file whenever "
            "it exists) is almost always what you want."
        ),
    )
    parser.add_argument(
        "--retry-manual",
        action="store_true",
        help=(
            "Re-include clusters recorded in audit-manual-attempts.csv (stayed "
            "MANUAL on a prior Stage 4 run). By default these are excluded from "
            "Source B so every run doesn't blindly re-attempt the same failures."
        ),
    )
    args = parser.parse_args()

    cli_art.console.print("\n" + "#" * 60, markup=False, soft_wrap=True)
    cli_art.console.print("  audit_keepers.py  —  Keeper Audit Pipeline", markup=False, soft_wrap=True)
    cli_art.console.print("#" * 60, markup=False, soft_wrap=True)
    cli_art.console.print(f"  dry_run:             {args.dry_run}", markup=False, soft_wrap=True)
    cli_art.console.print(f"  skip_rescore:        {args.skip_rescore}", markup=False, soft_wrap=True)
    cli_art.console.print(f"  auto_rewrite:        {args.auto_rewrite}", markup=False, soft_wrap=True)
    cli_art.console.print(f"  rebuild_from_keepers: {args.rebuild_from_keepers}", markup=False, soft_wrap=True)
    cli_art.console.print(f"  retry_manual:        {args.retry_manual}", markup=False, soft_wrap=True)
    cli_art.console.print(f"  limit:               {args.limit}", markup=False, soft_wrap=True)

    # --- Resolve source file ---
    source_file = resolve_source_file(args.rebuild_from_keepers, KEEPERS_IN, KEEPERS_AUDITED)
    if source_file == KEEPERS_AUDITED:
        cli_art.console.print(f"\n   ⚡ Loading from {os.path.basename(KEEPERS_AUDITED)} (default -- preserves manual corrections).", markup=False, soft_wrap=True)
        cli_art.console.print(   "      CLEAN rows will be skipped; cluster-map Source B skipped entirely.", markup=False, soft_wrap=True)
    elif args.rebuild_from_keepers:
        cli_art.console.print(f"\n   {theme.colorize_icon('warning')}  --rebuild-from-keepers: loading fresh from "
              f"{os.path.basename(KEEPERS_IN)}, discarding any correction only present in "
              f"{os.path.basename(KEEPERS_AUDITED)}.", soft_wrap=True)

    using_audited_source = source_file == KEEPERS_AUDITED

    if not os.path.exists(source_file):
        cli_art.console.print(f"\n{theme.colorize_icon('error')}  {source_file} not found. Run rewrite_bullets.py first.", soft_wrap=True)
        sys.exit(1)

    df_keepers = pd.read_csv(source_file)

    # Defaulting to KEEPERS_AUDITED (above) protects manual corrections,
    # but triage_needs_review.py appends new KEEP rows straight into
    # KEEPERS_IN on every real resume-build session -- those would
    # otherwise never reach the audited file again once it exists. Union
    # in anything from KEEPERS_IN not already present here (by Bullet
    # Point text) so new bullets still get promoted through the pipeline.
    if using_audited_source and os.path.exists(KEEPERS_IN):
        df_keepers, n_new = merge_new_rows_from_keepers_in(df_keepers, pd.read_csv(KEEPERS_IN))
        if n_new:
            cli_art.console.print(f"   {theme.colorize_icon('hint')} Picked up {n_new} new row(s) from "
                  f"{os.path.basename(KEEPERS_IN)} not yet in {os.path.basename(KEEPERS_AUDITED)}.", soft_wrap=True)

    df_keepers = ensure_writable_dtypes(df_keepers)

    # Ensure all expected columns exist
    for col in KEEPER_COLS + ["audit_status"]:
        if col not in df_keepers.columns:
            df_keepers[col] = ""

    cli_art.console.print(f"\n   📂 Loaded keepers: {len(df_keepers)} rows from {os.path.basename(source_file)}", markup=False, soft_wrap=True)
    cli_art.console.print(f"   📌 Startup snapshot: {len(_STARTUP_DONE_IDS)} cluster IDs "
          f"| {len(_STARTUP_DONE_BULLETS)} bullet texts already processed", markup=False, soft_wrap=True)

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
        using_audited_source=using_audited_source,
    )

    # Save audited keepers after Stage 1.
    # source_cluster_id values are already restored inside stage1_audit_keepers()
    # from _STARTUP_CLUSTER_ID_MAP, so this write preserves them correctly.
    df_keepers.to_csv(KEEPERS_AUDITED, index=False)
    cli_art.console.print(f"\n   {theme.colorize_icon('save')} Audited keepers → {os.path.basename(KEEPERS_AUDITED)}", soft_wrap=True)

    # ── Stage 2 ───────────────────────────────────────────────────────────────
    _df_disc = stage2_diff_cluster_map(df_keepers)

    # ── Stage 3 ───────────────────────────────────────────────────────────────
    # Pass using_audited_source so Stage 3 knows to skip Source B (cluster-map MANUALs)
    df_queue = stage3_build_rewrite_queue(df_keepers, using_audited_source=using_audited_source, retry_manual=args.retry_manual)

    # ── Stage 4 (optional) ───────────────────────────────────────────────
    if args.auto_rewrite:
        if df_queue.empty:
            cli_art.console.print("\n   STAGE 4 skipped — queue is empty.", markup=False, soft_wrap=True)
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
            cli_art.console.print(f"\n   {theme.colorize_icon('save')} Final audited keepers saved → {os.path.basename(KEEPERS_AUDITED)}", soft_wrap=True)
    else:
        if not df_queue.empty:
            cli_art.console.print(
                f"\n   {len(df_queue)} bullets queued. "
                f"Run with --auto-rewrite to process them."
            , markup=False, soft_wrap=True)

    cli_art.console.print("\n" + "─" * 60, markup=False, soft_wrap=True)
    cli_art.console.print(f"  {theme.colorize_icon('success')}  audit_keepers.py complete", soft_wrap=True)
    cli_art.console.print(f"     Audited keepers  → {os.path.basename(KEEPERS_AUDITED)}", markup=False, soft_wrap=True)
    cli_art.console.print(f"     Discrepancies    → {os.path.basename(DISCREPANCIES_OUT)}", markup=False, soft_wrap=True)
    cli_art.console.print(f"     Rewrite queue    → {os.path.basename(REWRITE_QUEUE_OUT)}", markup=False, soft_wrap=True)
    cli_art.console.print("─" * 60 + "\n", markup=False, soft_wrap=True)


if __name__ == "__main__":
    main()
