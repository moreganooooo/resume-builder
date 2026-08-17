"""
retire_rewrite_queue.py
------------------------
Marks all is_representative=False rows in rewrite-queue.csv as
RETIRED / CLOSED_OUT and writes them to retired-bullets.csv,
then removes them from rewrite-queue.csv.

Safe to re-run — uses rewrite_status=RETIRED as the idempotency marker.

Usage:
    python retire_rewrite_queue.py
"""

import csv
import os
import sys
from datetime import date

# Resolved from the script's own location, not the caller's cwd — matches
# every other script in this pipeline (cluster_bullet_bank.py, which writes
# rewrite-queue.csv, included).
SCRIPT_DIR    = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT  = os.path.dirname(SCRIPT_DIR)

if SCRIPT_DIR not in sys.path:
    sys.path.insert(0, SCRIPT_DIR)
import cli_art
import profile_paths  # noqa: E402
from atomic_write import atomic_write  # noqa: E402

KB_DIR        = profile_paths.kb_dir()
REWRITE_QUEUE = os.path.join(KB_DIR, "rewrite-queue.csv")
RETIRED_PATH  = os.path.join(KB_DIR, "retired-bullets.csv")

REWRITE_HEADER = [
    "cluster_id","cluster_size","is_representative","next_action",
    "Bullet Point","Role / Company","Tags",
    "accuracy_score","believability_score","clarity_score",
    "ats_value","manager_test","weaknesses",
    "final_bullet","rewrite_status","rewrite_attempts",
    "rewrite_reasoning","context_gaps","rewrite_date",
]

TODAY = str(date.today())


def main():
    if not os.path.exists(REWRITE_QUEUE):
        cli_art.cli_warning("rewrite-queue.csv not found. Exiting.")
        return

    with open(REWRITE_QUEUE, newline="", encoding="utf-8") as f:
        all_rows = list(csv.DictReader(f))

    keep_rows    = []
    retire_rows  = []

    for row in all_rows:
        is_rep = row.get("is_representative", "").strip().lower()
        status = row.get("rewrite_status", "").strip().upper()

        if is_rep == "false" and status != "RETIRED":
            row["rewrite_status"] = "RETIRED"
            row["rewrite_date"]   = TODAY
            row["next_action"]    = "CLOSED_OUT"
            retire_rows.append(row)
        else:
            keep_rows.append(row)

    cli_art.cli_info(f"Retiring {len(retire_rows)} non-representative rows.")
    cli_art.cli_info(f"Keeping {len(keep_rows)} rows in rewrite-queue.")

    retired_exists = os.path.exists(RETIRED_PATH)
    with open(RETIRED_PATH, "a", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=REWRITE_HEADER, extrasaction="ignore")
        if not retired_exists:
            writer.writeheader()
        writer.writerows(retire_rows)
    cli_art.cli_success(f"Appended {len(retire_rows)} rows to {RETIRED_PATH}.")

    with atomic_write(REWRITE_QUEUE, newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=REWRITE_HEADER, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(keep_rows)
    cli_art.cli_success(f"Rewrote {REWRITE_QUEUE} with {len(keep_rows)} active rows.")


if __name__ == "__main__":
    main()
