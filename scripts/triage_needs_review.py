"""
triage_needs_review.py
-----------------------
Processes needs-review.csv (a temporary holding file for bullets that
failed automated quality checks during a scoring run) and routes each
row to the appropriate destination:

  KEEP   → append to bullet-bank-keepers.csv (the main keeper bank)
  REWRITE→ append to rewrite-queue.csv
  RETIRE → append to retired-bullets.csv
  (anything else is left in needs-review.csv for a human to decide)

Routing logic (priority order):
  1. If manager_test == PASS and believability_score >= 80  → KEEP
  2. If manager_test == FAIL and rewrite_attempts < 3       → REWRITE
  3. If manager_test == FAIL and rewrite_attempts >= 3      → RETIRE
  4. Else                                                   → leave (needs human)

Safe to re-run — rows already routed keep their destination marker.

Usage:
    python triage_needs_review.py
"""

import csv
import os
from datetime import date

KB_BASE        = "resume-engine/knowledge_base"
NEEDS_REVIEW   = os.path.join(KB_BASE, "needs-review.csv")
KEEPERS_CSV    = os.path.join(KB_BASE, "bullet-bank-keepers.csv")
REWRITE_QUEUE  = os.path.join(KB_BASE, "rewrite-queue.csv")
RETIRED_PATH   = os.path.join(KB_BASE, "retired-bullets.csv")

TODAY = str(date.today())

KEEP_FIELDS = [
    "Bullet Point", "Role / Company", "Tags",
    "accuracy_score", "believability_score", "clarity_score",
    "ats_value", "manager_test", "weaknesses",
    "hidden_gem_score", "hidden_gem_flag", "hidden_gem_reason",
    "final_bullet", "rewrite_status",
]

QUEUE_FIELDS = [
    "cluster_id", "cluster_size", "is_representative", "next_action",
    "Bullet Point", "Role / Company", "Tags",
    "accuracy_score", "believability_score", "clarity_score",
    "ats_value", "manager_test", "weaknesses",
    "final_bullet", "rewrite_status", "rewrite_attempts",
    "rewrite_reasoning", "context_gaps", "rewrite_date",
]


def safe_int(val, default=0):
    try:
        return int(float(str(val).strip()))
    except (ValueError, TypeError):
        return default


def append_rows(path, rows, fieldnames):
    """Append rows to CSV, writing header only if file doesn't exist."""
    exists = os.path.exists(path)
    with open(path, "a", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        if not exists:
            writer.writeheader()
        writer.writerows(rows)


def main():
    if not os.path.exists(NEEDS_REVIEW):
        print("needs-review.csv not found. Nothing to triage.")
        return

    with open(NEEDS_REVIEW, newline="", encoding="utf-8") as f:
        all_rows = list(csv.DictReader(f))

    print(f"Triaging {len(all_rows)} rows from needs-review.csv...")

    keep_rows   = []
    rewrite_rows= []
    retire_rows = []
    leftover    = []

    for row in all_rows:
        mgr_test   = str(row.get("manager_test", "")).strip().upper()
        believ     = safe_int(row.get("believability_score", 0))
        attempts   = safe_int(row.get("rewrite_attempts", 0))
        status     = str(row.get("rewrite_status", "")).strip().upper()

        # Skip already-routed rows
        if status in ("KEEPER", "REWRITE", "RETIRED", "CLOSED_OUT"):
            leftover.append(row)
            continue

        if mgr_test == "PASS" and believ >= 80:
            row["rewrite_status"] = "KEEPER"
            keep_rows.append(row)
        elif mgr_test == "FAIL" and attempts < 3:
            row["rewrite_status"] = "REWRITE"
            row["next_action"]    = "REWRITE"
            row["rewrite_date"]   = TODAY
            rewrite_rows.append(row)
        elif mgr_test == "FAIL" and attempts >= 3:
            row["rewrite_status"] = "RETIRED"
            row["next_action"]    = "CLOSED_OUT"
            row["rewrite_date"]   = TODAY
            retire_rows.append(row)
        else:
            leftover.append(row)

    print(f"  KEEP    → {len(keep_rows)}")
    print(f"  REWRITE → {len(rewrite_rows)}")
    print(f"  RETIRE  → {len(retire_rows)}")
    print(f"  Leftover (needs human): {len(leftover)}")

    if keep_rows:
        append_rows(KEEPERS_CSV, keep_rows, KEEP_FIELDS)
        print(f"  Appended {len(keep_rows)} rows to {KEEPERS_CSV}")

    if rewrite_rows:
        append_rows(REWRITE_QUEUE, rewrite_rows, QUEUE_FIELDS)
        print(f"  Appended {len(rewrite_rows)} rows to {REWRITE_QUEUE}")

    if retire_rows:
        append_rows(RETIRED_PATH, retire_rows, QUEUE_FIELDS)
        print(f"  Appended {len(retire_rows)} rows to {RETIRED_PATH}")

    # Rewrite needs-review.csv with only unrouted rows
    if leftover:
        fieldnames = list(all_rows[0].keys()) if all_rows else QUEUE_FIELDS
        with open(NEEDS_REVIEW, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
            writer.writeheader()
            writer.writerows(leftover)
        print(f"  {len(leftover)} rows remain in {NEEDS_REVIEW} for manual review.")
    else:
        os.remove(NEEDS_REVIEW)
        print(f"  All rows routed. Deleted {NEEDS_REVIEW}.")

    print("\n  Done.")


if __name__ == "__main__":
    main()
