"""reset_resume_counter.py -- resets the "Resumes Customized All-Time"
counter by archiving the completion tracker and starting a fresh one.

That figure comes from jd_tracker_log.csv, which gets one row per
mark_completed() and is never rewritten -- that is what makes it an
"all-time" total. Resetting it is therefore a deliberate act, not
routine maintenance.

The reason it needs resetting here: the test suite appended two
"completed" rows to the real tracker on every run (JDTracker read a
module-level TRACKER_CSV resolved at import, so redirecting the profile
in a test did not move it), so the historical count is mostly fixtures
rather than real resumes. That leak is fixed; this clears what it left.

The old log is renamed, never deleted -- the tracker is also the record
of which jobs were completed, and jd_manager.job_key_known() reads it to
avoid rebuilding a resume that already exists. Archiving means that
history stays on disk even though the counter starts again.

Usage:
    python scripts/reset_resume_counter.py            # dry run
    python scripts/reset_resume_counter.py --apply    # archive and reset
"""

import argparse
import csv
import os
import sys
from collections import Counter
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import profile_paths  # noqa: E402

HEADER = [
    "job_key",
    "job_title",
    "company_name",
    "source_file",
    "status",
    "date_processed",
    "output_json",
    "output_pdf",
    "error_message",
]


def summarize(path: str) -> dict:
    if not os.path.exists(path):
        return {"rows": 0, "completed": 0, "fixtures": 0}
    with open(path, newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))

    statuses = Counter(r.get("status", "") for r in rows)
    # Rows written by the test fixture, identifiable by its source file.
    fixtures = sum(1 for r in rows if "test_job" in (r.get("source_file") or ""))
    return {
        "rows": len(rows),
        "completed": statuses.get("completed", 0),
        "fixtures": fixtures,
        "statuses": statuses,
    }


def reset(path: str, apply_changes: bool) -> dict:
    stats = summarize(path)
    if not apply_changes or not os.path.exists(path):
        return stats

    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    archive = f"{path}.archived-{stamp}"
    os.rename(path, archive)
    stats["archive"] = archive

    with open(path, "w", newline="", encoding="utf-8") as f:
        csv.writer(f).writerow(HEADER)
    return stats


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true", help="archive and reset")
    parser.add_argument("--profile", default=None)
    args = parser.parse_args()

    if args.profile:
        profile_paths.set_active_profile(args.profile)
    path = profile_paths.tracker_csv_path()

    stats = reset(path, apply_changes=args.apply)

    print(f"\n  tracker: {path}")
    print(f"  rows           {stats['rows']}")
    print(f"  completed      {stats['completed']}  (the banner's all-time figure)")
    print(f"  test fixtures  {stats['fixtures']}")
    if args.apply:
        print(f"\n  archived to {stats.get('archive')}")
        print("  counter is now 0")
    else:
        print("\n  dry run -- re-run with --apply to archive and reset to 0.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
