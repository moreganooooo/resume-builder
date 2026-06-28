"""
triage_needs_review.py
-----------------------
Processes needs-review.csv (a.k.a. needs_audit.csv):

  is_representative=True  -> append to rewrite-queue.csv as PENDING rewrites
  is_representative=False -> append to retired-bullets.csv as CLOSED_OUT

Clears needs-review.csv after processing (header preserved).
Safe to re-run — deduplicates by bullet text before writing.

Usage:
    python triage_needs_review.py
"""

import csv
import os
from datetime import date

NEEDS_REVIEW   = "resume-engine/knowledge_base/needs-review.csv"
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

RETIRED_HEADER = [
    "cluster_id","cluster_size","is_representative","next_action",
    "Bullet Point","Role / Company","Tags",
    "accuracy_score","believability_score","clarity_score",
    "ats_value","manager_test","weaknesses",
    "final_bullet","rewrite_status","rewrite_attempts",
    "rewrite_reasoning","context_gaps","rewrite_date",
    "retired_date","retire_reason",
]

TODAY = str(date.today())


def load_csv(path):
    if not os.path.exists(path):
        return []
    with open(path, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def write_csv(path, rows, fieldnames):
    os.makedirs(os.path.dirname(path) if os.path.dirname(path) else ".", exist_ok=True)
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def main():
    review_rows = load_csv(NEEDS_REVIEW)
    if not review_rows:
        print(f"⚠️  No rows found in {NEEDS_REVIEW} — nothing to triage.")
        return

    queue_existing   = load_csv(REWRITE_QUEUE)
    retired_existing = load_csv(RETIRED_PATH)

    queued_bullets  = {r["Bullet Point"].strip().lower() for r in queue_existing}
    retired_bullets = {r["Bullet Point"].strip().lower() for r in retired_existing}

    new_queue   = []
    new_retired = []

    for row in review_rows:
        bullet_key = row.get("Bullet Point", "").strip().lower()
        is_rep     = str(row.get("is_representative", "True")).strip().lower()

        if is_rep in ("true", "1", "yes"):
            if bullet_key not in queued_bullets:
                row["rewrite_status"]  = "PENDING"
                row["rewrite_date"]    = TODAY
                new_queue.append(row)
                queued_bullets.add(bullet_key)
        else:
            if bullet_key not in retired_bullets:
                row["rewrite_status"] = "CLOSED_OUT"
                row["retired_date"]   = TODAY
                row["retire_reason"]  = "CLOSED_OUT: non-representative from triage"
                new_retired.append(row)
                retired_bullets.add(bullet_key)

    # Write updated files
    write_csv(REWRITE_QUEUE, queue_existing + new_queue,     REWRITE_HEADER)
    write_csv(RETIRED_PATH,  retired_existing + new_retired, RETIRED_HEADER)

    # Clear needs-review.csv (preserve header)
    write_csv(NEEDS_REVIEW, [], [
        "cluster_id","cluster_size","is_representative","next_action",
        "Bullet Point","Role / Company","Tags",
        "accuracy_score","believability_score","clarity_score",
        "ats_value","manager_test","weaknesses",
    ])

    print(f"✅  Triage complete.")
    print(f"   {len(new_queue)} bullets → rewrite-queue.csv (PENDING)")
    print(f"   {len(new_retired)} bullets → retired-bullets.csv (CLOSED_OUT)")
    print(f"   needs-review.csv cleared (header preserved).")


if __name__ == "__main__":
    main()
