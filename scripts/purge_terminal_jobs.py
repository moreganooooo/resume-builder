"""purge_terminal_jobs.py -- removes expired and archived jobs, files and
rows together.

Expired and archived are terminal states: the liveness sweep retired the
posting, or a person deliberately discarded it. Neither is actionable
again, both are hidden from the Pipeline anyway, and together they are
the bulk of the JD corpus on disk.

What is deliberately NOT touched:
  - the knowledge base (verified tools/metrics/projects/facts, bullet
    bank, profile.yml) -- the expensive, hard-to-rebuild asset
  - jd_tracker_log.csv and applications.md -- the append-only record of
    what was actually applied to, which is the history this deletes the
    raw material for
  - anything still pending, including database-only rows with no file

Run reconcile_jd_status.py first. This keys off status, so a row whose
status has drifted from its file's actual directory would be judged on
stale information.

The database is backed up before any write, so rows are recoverable from
that copy; the JD files are not. To keep them, tar the directories off to
external storage first:

    tar czf jds-terminal.tar.gz jds/<profile>/expired jds/<profile>/archived

Usage:
    python scripts/purge_terminal_jobs.py            # dry run
    python scripts/purge_terminal_jobs.py --apply    # deletes
"""

import argparse
import glob
import os
import shutil
import sqlite3
import sys
from datetime import datetime
from typing import List

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import profile_paths  # noqa: E402

TERMINAL_STATUSES = ("expired", "archived")
TERMINAL_DIRS = ("expired", "archived")


def terminal_files(jds_dir: str) -> List[str]:
    paths = []
    for subdir in TERMINAL_DIRS:
        paths.extend(glob.glob(os.path.join(jds_dir, subdir, "*.json")))
    return paths


def purge(db_path: str, jds_dir: str, apply_changes: bool) -> dict:
    files = terminal_files(jds_dir)
    freed = sum(os.path.getsize(p) for p in files if os.path.exists(p))

    conn = sqlite3.connect(db_path)
    # `placeholders` is a run of "?" characters sized to a module
    # constant -- it carries no data, and the statuses themselves are
    # bound as parameters. The three # nosec B608 markers below say so.
    placeholders = ",".join("?" * len(TERMINAL_STATUSES))
    rows = conn.execute(
        f"SELECT COUNT(*) FROM jobs WHERE status IN ({placeholders})",  # nosec B608
        TERMINAL_STATUSES,
    ).fetchone()[0]
    remaining = conn.execute(
        f"SELECT COUNT(*) FROM jobs WHERE status NOT IN ({placeholders})",  # nosec B608
        TERMINAL_STATUSES,
    ).fetchone()[0]

    if apply_changes:
        with conn:
            conn.execute(
                f"DELETE FROM jobs WHERE status IN ({placeholders})",  # nosec B608
                TERMINAL_STATUSES,
            )
        conn.execute("VACUUM")

        for path in files:
            try:
                os.remove(path)
            except OSError:
                pass

    conn.close()
    return {
        "files": len(files),
        "bytes": freed,
        "rows": rows,
        "remaining_rows": remaining,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true", help="delete them")
    parser.add_argument("--profile", default=None)
    args = parser.parse_args()

    profile = args.profile or profile_paths.active_profile()
    db_path = os.path.join(profile_paths.profile_root(profile), "data.db")
    jds_dir = profile_paths.jds_dir(profile)

    if not os.path.exists(db_path):
        print(f"✗ no database at {db_path}")
        return 1

    if args.apply:
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        backup = f"{db_path}.backup-{stamp}"
        shutil.copy2(db_path, backup)
        print(f"✓ backed up to {backup}")

    stats = purge(db_path, jds_dir, apply_changes=args.apply)
    verb = "deleted" if args.apply else "would delete"

    print(f"\n  {verb} {stats['files']} JD files ({stats['bytes'] / 1e6:.1f} MB)")
    print(f"  {verb} {stats['rows']} database rows")
    print(f"  remaining jobs: {stats['remaining_rows']}")
    if not args.apply:
        print("\n  dry run -- re-run with --apply to delete.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
