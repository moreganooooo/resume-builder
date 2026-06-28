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
from datetime import date

REWRITE_QUEUE  = "resume-engine/knowledge_base/rewrite-queue.csv"
RETIRED_PATH   = "resume-engine/knowledge_base/retired-bullets.csv"

REWRITE_HEADER = [
    "cluster_id","cluster_size","is_representative","next_action",
    "Bullet Point","Role / Company","Tags",
    "accuracy_score","believability_score","clarity_score",
    "ats_value","manager_test","weaknesses",
    "final_bullet","rewrite_status","rewrite_attempts",
    "rewrite_reasoning","context_gaps","rewrite_date",
]

TODAY = str(date.today())

RETIRED_HEADER = [
    "cluster_id","cluster_size","is_representative","next_action",
    "Bullet Point","Role / Company","Tags",
    "accuracy_score","believability_score","clarity_score",
    "ats_value","manager_test","weaknesses",
    "final_bullet","rewrite_status","rewrite_attempts",
    "rewrite_reasoning","context_gaps","rewrite_date",
    "retired_date","retire_reason",
]


def load_csv(path, header):
    if not os.path.exists(path):
        return []
    with open(path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        return list(reader)


def write_csv(path, rows, fieldnames):
    os.makedirs(os.path.dirname(path) if os.path.dirname(path) else ".", exist_ok=True)
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def main():
    queue_rows = load_csv(REWRITE_QUEUE, REWRITE_HEADER)
    if not queue_rows:
        print(f"⚠️  No rows found in {REWRITE_QUEUE} — nothing to retire.")
        return

    retired_existing = load_csv(RETIRED_PATH, RETIRED_HEADER)
    retired_bullets  = {r["Bullet Point"].strip().lower() for r in retired_existing}

    to_retire  = []
    to_keep    = []

    for row in queue_rows:
        is_rep = str(row.get("is_representative", "True")).strip().lower()
        status = str(row.get("rewrite_status", "")).strip().upper()

        if status == "RETIRED":
            to_keep.append(row)  # already retired — idempotent, leave alone
            continue

        if is_rep in ("false", "0", "no"):
            bullet_key = row.get("Bullet Point", "").strip().lower()
            if bullet_key not in retired_bullets:
                row["rewrite_status"] = "RETIRED"
                row["retired_date"]   = TODAY
                row["retire_reason"]  = "CLOSED_OUT: non-representative cluster member"
                to_retire.append(row)
                retired_bullets.add(bullet_key)
        else:
            to_keep.append(row)

    # Write updated queue (representatives only)
    write_csv(REWRITE_QUEUE, to_keep, REWRITE_HEADER)

    # Append newly retired rows to retired-bullets.csv
    all_retired = retired_existing + to_retire
    write_csv(RETIRED_PATH, all_retired, RETIRED_HEADER)

    print(f"✅  Retired {len(to_retire)} non-representative bullets.")
    print(f"   Rewrite queue now has {len(to_keep)} active rows.")
    print(f"   Retired archive now has {len(all_retired)} total rows.")


if __name__ == "__main__":
    main()
