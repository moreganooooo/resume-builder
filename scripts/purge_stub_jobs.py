"""purge_stub_jobs.py -- removes contentless stub rows from the jobs table.

Two sources fed junk into the jobs table:

1. Test fixtures. tests/test_application_package.py ran
   build_application_package() for real against the developer's own
   active profile, so every full test run wrote "Test"/"Role" @ "Acme
   Corp" rows into a real profiles/<name>/data.db. That test is isolated
   now (it redirects profile_paths.PROFILES_DIR at setUp), but the rows
   it already wrote are still there.
2. Partial syncs that created a row from an application status alone,
   carrying {"job_title": "Role"} and nothing else.

Both classes are indistinguishable from real jobs in the dashboard's
Pipeline, where they render as scoreless entries.

The predicate is deliberately conservative: a row with a non-empty
description is NEVER deleted, whatever its title or company looks like.
Everything removed is a row with no job description at all AND a
placeholder title, a known fixture company, or an example.com URL.

Usage:
    python scripts/purge_stub_jobs.py            # dry run, reports only
    python scripts/purge_stub_jobs.py --apply    # deletes, after backup
"""

import argparse
import json
import os
import shutil
import sqlite3
import sys
from collections import Counter
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import profile_paths  # noqa: E402

PLACEHOLDER_TITLES = {"", "Test", "Role", "Untitled Role"}
FIXTURE_COMPANIES = {"Acme", "Acme Corp", "Testco", "Unknown Company"}
FIXTURE_URL_HOSTS = ("example.com", "example.org")

# Fixture URLs that are not on an example.* host. The board-scanner
# tests post against a fake Greenhouse slug, and those rows DO carry a
# description -- see _is_seeded_fixture for why that matters.
FIXTURE_URL_MARKERS = ("greenhouse.io/testco",)


def _payload(row: sqlite3.Row) -> dict:
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


def _is_seeded_fixture(row: sqlite3.Row, data: dict) -> bool:
    """True for a row that is unmistakably test-suite output.

    The description veto below rests on "no fixture populates a
    description". That stopped being true: 390 rows titled "Senior
    Content Strategist" @ "Testco" reached a real data.db between
    2026-08-17 and 2026-08-20 (before db._is_unisolated_test_write
    existed), each carrying a full fake description AND a fake
    Greenhouse URL. They survived every purge, and a liveness sweep
    dutifully checked all 390 against the same dead fixture URL --
    rendering as bare content hashes, since their metadata_json has no
    job_title/company_name for a label to use.

    Requires BOTH signals: a fixture company AND a fixture URL. Either
    alone could plausibly be a real posting; together they cannot be.
    """
    url = str(data.get("source_url") or "")
    company = str(row["company"] or "").strip()
    return company in FIXTURE_COMPANIES and any(
        marker in url for marker in FIXTURE_URL_MARKERS
    )


def is_stub(row: sqlite3.Row) -> bool:
    """True for a row carrying no recoverable job content.

    A real description is an absolute veto -- the one field that makes a
    row useful to the user -- EXCEPT where the description itself came
    from a fixture (see _is_seeded_fixture).
    """
    data = _payload(row)
    if _is_seeded_fixture(row, data):
        return True
    if str(data.get("description") or "").strip():
        return False

    url = str(data.get("source_url") or "")
    if any(host in url for host in FIXTURE_URL_HOSTS):
        return True

    if str(row["title"] or "").strip() in PLACEHOLDER_TITLES:
        return True

    return str(row["company"] or "").strip() in FIXTURE_COMPANIES


def purge(db_path: str, apply_changes: bool) -> dict:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row

    rows = conn.execute(
        "SELECT id, title, company, status, metadata_json, raw_text FROM jobs"
    ).fetchall()

    stubs = [row for row in rows if is_stub(row)]
    stats = {
        "scanned": len(rows),
        "stubs": len(stubs),
        "kept": len(rows) - len(stubs),
        "by_title": Counter(row["title"] for row in stubs),
        "by_status": Counter(row["status"] for row in stubs),
    }

    if apply_changes and stubs:
        with conn:
            conn.executemany(
                "DELETE FROM jobs WHERE id = ?", [(row["id"],) for row in stubs]
            )
        conn.execute("VACUUM")

    conn.close()
    return stats


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--apply",
        action="store_true",
        help="delete the stub rows (default is a dry run that only reports)",
    )
    parser.add_argument(
        "--profile", default=None, help="profile to clean (default: active profile)"
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

    stats = purge(db_path, apply_changes=args.apply)

    verb = "deleted" if args.apply else "would delete"
    print(f"\n  scanned  {stats['scanned']} rows")
    print(f"  {verb:<8} {stats['stubs']} stub rows")
    print(f"  kept     {stats['kept']} rows with real job content")
    for title, count in stats["by_title"].most_common():
        print(f"    title {title!r:<18} {count}")
    print(
        "  by status: "
        + ", ".join(f"{s}={n}" for s, n in stats["by_status"].most_common())
    )
    if not args.apply and stats["stubs"]:
        print("\n  dry run -- re-run with --apply to delete these rows.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
