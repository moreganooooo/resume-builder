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

TODAY = str(date.today())


def load_existing_bullets(path):
    if not os.path.exists(path):
        return set()
    with open(path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        return {row["Bullet Point"].strip() for row in reader}


def main():
    if not os.path.exists(NEEDS_REVIEW):
        print("needs-review.csv not found. Exiting.")
        return

    with open(NEEDS_REVIEW, newline="", encoding="utf-8") as f:
        all_rows = list(csv.DictReader(f))

    print(f"Loaded {len(all_rows)} rows from needs-review.csv.")

    to_rewrite = []
    to_retire  = []

    for row in all_rows:
        is_rep = row.get("is_representative", "").strip().lower()
        if is_rep == "true":
            to_rewrite.append(row)
        else:
            to_retire.append(row)

    print(f"  is_representative=True  -> rewrite queue: {len(to_rewrite)}")
    print(f"  is_representative=False -> retire/close:  {len(to_retire)}")

    # Append to rewrite-queue (deduplicated)
    existing_rq  = load_existing_bullets(REWRITE_QUEUE)
    new_rq_rows  = [r for r in to_rewrite
                    if r.get("Bullet Point","").strip() not in existing_rq]

    rq_exists = os.path.exists(REWRITE_QUEUE)
    with open(REWRITE_QUEUE, "a", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=REWRITE_HEADER, extrasaction="ignore")
        if not rq_exists:
            writer.writeheader()
        for row in new_rq_rows:
            row["next_action"]    = "REWRITE"
            row["rewrite_status"] = "PENDING"
            row["rewrite_date"]   = ""
            writer.writerow(row)

    print(f"  Added {len(new_rq_rows)} new rows to rewrite-queue.csv"
          f" ({len(to_rewrite) - len(new_rq_rows)} already present, skipped).")

    # Append to retired-bullets (deduplicated)
    existing_ret = load_existing_bullets(RETIRED_PATH)
    new_ret_rows = [r for r in to_retire
                    if r.get("Bullet Point","").strip() not in existing_ret]

    ret_exists = os.path.exists(RETIRED_PATH)
    with open(RETIRED_PATH, "a", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=REWRITE_HEADER, extrasaction="ignore")
        if not ret_exists:
            writer.writeheader()
        for row in new_ret_rows:
            row["rewrite_status"] = "RETIRED"
            row["next_action"]    = "CLOSED_OUT"
            row["rewrite_date"]   = TODAY
            writer.writerow(row)

    print(f"  Retired {len(new_ret_rows)} rows to retired-bullets.csv.")

    # Clear needs-review.csv (preserve header)
    with open(NEEDS_REVIEW, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=REWRITE_HEADER, extrasaction="ignore")
        writer.writeheader()

    print("  needs-review.csv cleared (header preserved).")


if __name__ == "__main__":
    main()
