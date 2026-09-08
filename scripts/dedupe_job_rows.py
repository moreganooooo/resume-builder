"""dedupe_job_rows.py -- merges jobs table rows that share a dedup_hash but
ended up with different ids, keeping exactly one row per real posting.

db.upsert_job() previously keyed ON CONFLICT(id) only, so a posting
re-scraped under a different id (e.g. the RSS aggregator company-name bug
fixed 2026-09-05, where realworkfromanywhere/jobspresso/authenticjobs all
collapsed every listing to the same company string and only dedup_hash
still distinguished real postings from each other -- though this can
happen from any provider whose id computation isn't perfectly stable
across scans) landed as a brand-new row instead of updating the existing
one. upsert_job() itself is now fixed to merge into an existing dedup_hash
match going forward; this script cleans up the duplicates that already
accumulated before that fix.

Excludes the generic "Untitled Role"/"Unknown Company" fallback pair, same
guard as upsert_job() -- two genuinely different postings that both failed
to parse a title/company would otherwise hash identically and get wrongly
merged.

Keeper selection within a duplicate group:
  1. A terminal status (archived/expired/rejected/discarded) outranks a
     non-terminal one (pending/evaluating/etc.) -- a terminal status
     reflects a deliberate decision (or a liveness sweep's verdict)
     already made about that posting, and letting a stale re-scraped
     "pending" duplicate outrank it would silently resurrect a job that
     was already dealt with.
  2. Within the same status tier, the row with the higher final_score
     wins (more evaluation information survives).
  3. Ties fall back to the most recently created_at (freshest raw_text/
     description).

application_log and verification_audit_log rows are repointed from a
losing id to the keeper's id before the losing rows are deleted, so
nothing is orphaned even though no such references existed in the corpus
this was written against.

The database is backed up before any --apply write.

Usage:
    python scripts/dedupe_job_rows.py            # dry run
    python scripts/dedupe_job_rows.py --apply    # merges
"""

import argparse
import os
import shutil
import sys
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import db  # noqa: E402
import profile_paths  # noqa: E402

_TERMINAL_STATUSES = ("archived", "expired", "rejected", "discarded")


def _status_rank(status: str) -> int:
    """0 = terminal (outranks), 1 = everything else."""
    return 0 if status in _TERMINAL_STATUSES else 1


def _keeper(rows_oldest_first: list) -> dict:
    """rows_oldest_first must already be sorted by created_at ascending --
    the tie-break uses each row's ordinal position rather than parsing the
    timestamp text, so "most recent" is just "highest index"."""

    def sort_key(indexed_row):
        index, row = indexed_row
        return (
            _status_rank(row["status"]),
            -(row["final_score"] or 0.0),
            -index,
        )

    return sorted(enumerate(rows_oldest_first), key=sort_key)[0][1]


def find_duplicate_groups(conn) -> list:
    cursor = conn.execute(
        "SELECT dedup_hash, COUNT(*) as c FROM jobs "
        "WHERE dedup_hash IS NOT NULL AND dedup_hash != '' "
        "AND NOT (title = 'Untitled Role' AND company = 'Unknown Company') "
        "GROUP BY dedup_hash HAVING c > 1"
    )
    hashes = [row["dedup_hash"] for row in cursor.fetchall()]

    groups = []
    for dedup_hash in hashes:
        rows = conn.execute(
            "SELECT id, title, company, status, final_score, created_at "
            "FROM jobs WHERE dedup_hash = ? ORDER BY created_at",
            (dedup_hash,),
        ).fetchall()
        rows = [dict(r) for r in rows]
        keeper = _keeper(rows)
        losers = [r for r in rows if r["id"] != keeper["id"]]
        if losers:
            groups.append(
                {"dedup_hash": dedup_hash, "keeper": keeper, "losers": losers}
            )
    return groups


def apply_merge(conn, groups: list) -> int:
    merged = 0
    with conn:
        for group in groups:
            keeper_id = group["keeper"]["id"]
            for loser in group["losers"]:
                conn.execute(
                    "UPDATE application_log SET job_id = ? WHERE job_id = ?",
                    (keeper_id, loser["id"]),
                )
                conn.execute(
                    "UPDATE verification_audit_log SET job_id = ? WHERE job_id = ?",
                    (keeper_id, loser["id"]),
                )
                conn.execute("DELETE FROM jobs WHERE id = ?", (loser["id"],))
                merged += 1
    return merged


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true", help="merge duplicates")
    parser.add_argument("--profile", default=None)
    args = parser.parse_args()

    profile = args.profile or profile_paths.active_profile()
    db_path = db.get_db_path(profile)
    conn = db.get_db(profile)

    try:
        groups = find_duplicate_groups(conn)
        total_losers = sum(len(g["losers"]) for g in groups)

        print(
            f"Duplicate groups found: {len(groups)} ({total_losers} row(s) to merge away)\n"
        )
        for group in groups:
            keeper = group["keeper"]
            print(
                f"  [{keeper['company']}] {keeper['title']} -- "
                f"keeping {keeper['id'][:12]}… ({keeper['status']}, "
                f"score={keeper['final_score']}), merging away "
                f"{len(group['losers'])} row(s)"
            )

        if not groups:
            print("Nothing to do.")
            return 0

        if args.apply:
            stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
            backup = f"{db_path}.backup-{stamp}"
            shutil.copy2(db_path, backup)
            print(f"\n✓ backed up to {backup}")
            merged = apply_merge(conn, groups)
            print(f"\nmerged away {merged} duplicate row(s).")
        else:
            print("\ndry run -- re-run with --apply to merge these after review.")

        return 0
    finally:
        conn.close()


if __name__ == "__main__":
    raise SystemExit(main())
