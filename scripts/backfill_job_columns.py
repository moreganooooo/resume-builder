"""backfill_job_columns.py -- repairs jobs rows whose top-level columns
were never populated from their own metadata_json.

The filesystem-to-DB migration wrote each JD's full JSON into
metadata_json/raw_text but read the top-level columns with the wrong key
spellings: scraped JD files carry job_title/company_name and keep the
score under _evaluation.composite_score (CLAUDE.md's "JD JSON metadata
convention"), while db.upsert_job only looked for title/company/
final_score. Every miss fell through to a placeholder -- "Untitled Role",
"Unknown Company", NULL -- so the dashboard's Pipeline renders real
evaluations as red 0.00s.

No data was lost: the correct values are still in metadata_json. This
script re-derives them. db.upsert_job now reads both spellings, so new
writes land correctly; this is purely a one-time repair of rows written
before that fix.

Only placeholder values are overwritten. A row that already has a real
title, company, or score is left alone, so this is safe to re-run and
safe to run after manual corrections.

Usage:
    python scripts/backfill_job_columns.py            # dry run, reports only
    python scripts/backfill_job_columns.py --apply    # writes, after backup
"""

import argparse
import json
import os
import shutil
import sqlite3
import sys
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import profile_paths  # noqa: E402

PLACEHOLDER_TITLE = "Untitled Role"
PLACEHOLDER_COMPANY = "Unknown Company"


def _payload(row: sqlite3.Row) -> dict:
    """Returns the JD's own JSON for a row, preferring metadata_json and
    falling back to raw_text. Both columns hold the same payload for
    migrated rows, but raw_text is the only one populated for some of the
    earliest ones, and a row whose metadata_json failed to parse is still
    worth trying to rescue from the other column."""
    for column in ("metadata_json", "raw_text"):
        blob = row[column]
        if not blob:
            continue
        try:
            parsed = json.loads(blob)
        except (json.JSONDecodeError, TypeError):
            continue
        if isinstance(parsed, dict):
            return parsed
    return {}


def _is_placeholder(value, placeholder: str) -> bool:
    return value is None or not str(value).strip() or str(value) == placeholder


def derive_fixes(row: sqlite3.Row) -> dict:
    """Returns the column -> corrected-value pairs this row needs, empty
    if it is already healthy. Never proposes a placeholder as a fix, and
    never overwrites a value that is already real."""
    data = _payload(row)
    if not data:
        return {}

    evaluation = data.get("_evaluation")
    if not isinstance(evaluation, dict):
        evaluation = {}

    fixes = {}

    if _is_placeholder(row["title"], PLACEHOLDER_TITLE):
        title = data.get("job_title") or data.get("title")
        if title and str(title).strip() and str(title) != PLACEHOLDER_TITLE:
            fixes["title"] = str(title).strip()

    if _is_placeholder(row["company"], PLACEHOLDER_COMPANY):
        company = data.get("company_name") or data.get("company")
        if company and str(company).strip() and str(company) != PLACEHOLDER_COMPANY:
            fixes["company"] = str(company).strip()

    if not str(row["location"] or "").strip():
        location = data.get("location")
        if location and str(location).strip():
            fixes["location"] = str(location).strip()

    # The three scores travel together on _evaluation. A score of 0 is a
    # legitimate evaluation result, so test for None rather than falsiness
    # -- `or` here would silently re-backfill a real zero every run.
    score_sources = {
        "final_score": evaluation.get("composite_score"),
        "capability_score": evaluation.get("fit_score"),
        "recruiter_score": evaluation.get("interview_odds_score"),
    }
    for column, value in score_sources.items():
        if row[column] is None and isinstance(value, (int, float)):
            fixes[column] = float(value)

    return fixes


def backfill(db_path: str, apply_changes: bool) -> dict:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row

    rows = conn.execute(
        "SELECT id, title, company, location, final_score, capability_score,"
        " recruiter_score, metadata_json, raw_text FROM jobs"
    ).fetchall()

    stats = {"scanned": len(rows), "repaired": 0, "unrecoverable": 0}
    per_column = {}
    updates = []

    for row in rows:
        fixes = derive_fixes(row)
        if not fixes:
            # Only count a row as unrecoverable if it actually needed help.
            needs_help = _is_placeholder(
                row["title"], PLACEHOLDER_TITLE
            ) or _is_placeholder(row["company"], PLACEHOLDER_COMPANY)
            if needs_help:
                stats["unrecoverable"] += 1
            continue
        stats["repaired"] += 1
        for column in fixes:
            per_column[column] = per_column.get(column, 0) + 1
        updates.append((row["id"], fixes))

    if apply_changes and updates:
        with conn:
            for job_id, fixes in updates:
                assignments = ", ".join(f"{col} = ?" for col in fixes)
                # nosec B608 -- `assignments` interpolates COLUMN NAMES
                # only, and every one is a hardcoded literal set above
                # ("title", "company", "location", and the three score
                # columns). No caller-supplied text reaches the SQL
                # string; every VALUE is bound as a parameter below.
                conn.execute(
                    f"UPDATE jobs SET {assignments}, updated_at = CURRENT_TIMESTAMP"
                    " WHERE id = ?",  # nosec B608
                    (*fixes.values(), job_id),
                )

    conn.close()
    stats["per_column"] = per_column
    return stats


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--apply",
        action="store_true",
        help="write the repairs (default is a dry run that only reports)",
    )
    parser.add_argument(
        "--profile", default=None, help="profile to repair (default: active profile)"
    )
    args = parser.parse_args()

    profile = args.profile or profile_paths.active_profile()
    db_path = os.path.join(profile_paths.PROFILES_DIR, profile, "data.db")
    if not os.path.exists(db_path):
        print(f"✗ no database at {db_path}")
        return 1

    if args.apply:
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        backup = f"{db_path}.backup-{stamp}"
        shutil.copy2(db_path, backup)
        print(f"✓ backed up to {backup}")

    stats = backfill(db_path, apply_changes=args.apply)

    verb = "repaired" if args.apply else "would repair"
    print(f"\n  scanned      {stats['scanned']} rows")
    print(f"  {verb:<12} {stats['repaired']} rows")
    for column, count in sorted(stats["per_column"].items()):
        print(f"    {column:<20} {count}")
    if stats["unrecoverable"]:
        print(
            f"  unrecoverable {stats['unrecoverable']} rows"
            " (placeholder columns, and no usable JSON to re-derive from)"
        )
    if not args.apply and stats["repaired"]:
        print("\n  dry run -- re-run with --apply to write these changes.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
