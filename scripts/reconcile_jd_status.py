"""reconcile_jd_status.py -- realigns each job row's status with where
its JD file actually lives on disk.

A JD's directory IS its status: jds/<profile>/ is pending,
jds/<profile>/expired/ is expired, jds/<profile>/archived/ is archived.
jd_manager moves files between them, but some moves never wrote the new
status back to data.db, so the two stores drifted -- the database
reported 2,184 pending jobs while only 170 pending files existed, and 439
rows disagreed outright with their own file's location.

That matters beyond tidiness: the dashboard's Pipeline hides terminal
statuses, so a row still marked "pending" whose file sits in archived/
shows up as a live opportunity the user already discarded.

The filesystem wins, deliberately. A file move is an explicit act (the
liveness sweep expiring a posting, or a person archiving one); a stale
database row is the residue of a write that did not happen.

Matching a row to its file takes two passes, because jobs.id has two
shapes. Most rows are keyed by filename. The rest are keyed by
jd_manager.compute_job_key(), which is a SHA-256 of the file's own bytes
-- so a hash id does NOT imply "no file", and matching on basename alone
silently skips them. An earlier version of this script did exactly that
and left 740 reconcilable rows untouched while reporting them as
scan-only. Rows that match neither pass really have no file and are left
alone.

Usage:
    python scripts/reconcile_jd_status.py            # dry run
    python scripts/reconcile_jd_status.py --apply    # writes, after backup
"""

import argparse
import glob
import os
import shutil
import sqlite3
import sys
from collections import Counter
from datetime import datetime
from typing import Dict

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import jd_manager  # noqa: E402
import profile_paths  # noqa: E402

# Directory name -> the status it represents. "" is the JDs root.
DIR_STATUS = {
    "": "pending",
    "expired": "expired",
    "archived": "archived",
    "completed": "completed",
}


def file_locations(jds_dir: str) -> Dict[str, str]:
    """Maps each JD basename to the status implied by its directory."""
    locations = {}
    for subdir, status in DIR_STATUS.items():
        pattern = os.path.join(jds_dir, subdir, "*.json") if subdir else os.path.join(
            jds_dir, "*.json"
        )
        for path in glob.glob(pattern):
            locations[os.path.basename(path)] = status
    return locations


def key_locations(jds_dir: str) -> Dict[str, str]:
    """Maps each JD's compute_job_key() to its directory status, for rows
    stored under a content hash rather than a filename."""
    locations = {}
    for subdir, status in DIR_STATUS.items():
        pattern = os.path.join(jds_dir, subdir, "*.json") if subdir else os.path.join(
            jds_dir, "*.json"
        )
        for path in glob.glob(pattern):
            try:
                locations[jd_manager.compute_job_key(path)] = status
            except (OSError, ValueError):
                continue
    return locations


def reconcile(db_path: str, jds_dir: str, apply_changes: bool) -> dict:
    locations = file_locations(jds_dir)
    by_key = key_locations(jds_dir)

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    rows = conn.execute("SELECT id, status FROM jobs").fetchall()

    updates = []
    transitions = Counter()
    no_file = 0

    for row in rows:
        job_id = str(row["id"])
        actual = locations.get(os.path.basename(job_id))
        if actual is None:
            actual = by_key.get(job_id)
        if actual is None:
            no_file += 1
            continue
        if actual != row["status"]:
            updates.append((actual, row["id"]))
            transitions[f"{row['status']} -> {actual}"] += 1

    if apply_changes and updates:
        with conn:
            conn.executemany(
                "UPDATE jobs SET status = ?, updated_at = CURRENT_TIMESTAMP"
                " WHERE id = ?",
                updates,
            )

    after = Counter(r[0] for r in conn.execute("SELECT status FROM jobs"))
    conn.close()

    return {
        "scanned": len(rows),
        "files_on_disk": len(locations),
        "no_file": no_file,
        "updates": len(updates),
        "transitions": transitions,
        "status_after": after,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true", help="write the corrections")
    parser.add_argument("--profile", default=None)
    args = parser.parse_args()

    profile = args.profile or profile_paths.active_profile()
    db_path = os.path.join(profile_paths.PROFILES_DIR, profile, "data.db")
    jds_dir = profile_paths.jds_dir(profile)

    if not os.path.exists(db_path):
        print(f"✗ no database at {db_path}")
        return 1

    if args.apply:
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        backup = f"{db_path}.backup-{stamp}"
        shutil.copy2(db_path, backup)
        print(f"✓ backed up to {backup}")

    stats = reconcile(db_path, jds_dir, apply_changes=args.apply)
    verb = "corrected" if args.apply else "would correct"

    print(f"\n  db rows          {stats['scanned']}")
    print(f"  files on disk    {stats['files_on_disk']}")
    print(f"  no matching file {stats['no_file']} (scan-sourced rows, left alone)")
    print(f"  {verb:<16} {stats['updates']}")
    for transition, count in stats["transitions"].most_common():
        print(f"      {transition:<28} {count}")
    if args.apply:
        print("\n  status now: " + ", ".join(
            f"{s}={n}" for s, n in stats["status_after"].most_common()
        ))
    else:
        print("\n  dry run -- re-run with --apply to write.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
