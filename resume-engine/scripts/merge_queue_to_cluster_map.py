"""
merge_queue_to_cluster_map.py
------------------------------
Merges rewrite-queue.csv into bullet-bank-cluster-map.csv so that
rewrite_bullets.py picks up the queued bullets on its next run.

Logic:
  - Loads rewrite-queue.csv (the active PENDING rows after triage)
  - Loads bullet-bank-cluster-map.csv
  - For each queue row:
      * If the exact bullet text already exists in the cluster map
        AND its next_action is already REWRITE/REVIEW -> skip (already queued)
      * If it exists but has a different next_action -> update that row
        in-place to next_action=REWRITE, rewrite_status=PENDING
      * If it doesn't exist at all -> append as a new row
  - Writes the result back to bullet-bank-cluster-map.csv
  - Clears rewrite-queue.csv (header only) on success

Safe to re-run -- idempotent by bullet text.

Usage:
    python merge_queue_to_cluster_map.py
"""

import csv
import os
from datetime import date

REWRITE_QUEUE    = "resume-engine/knowledge_base/rewrite-queue.csv"
CLUSTER_MAP      = "resume-engine/knowledge_base/bullet-bank-cluster-map.csv"

# Cluster map column order (must match existing file exactly)
CLUSTER_HEADER = [
    "cluster_id", "cluster_size", "is_representative", "next_action",
    "Bullet Point", "Role / Company", "Tags",
    "accuracy_score", "believability_score", "clarity_score",
    "ats_value", "manager_test", "weaknesses",
    "source", "rewrite_attempts", "rewrite_reasoning",
    "context_gaps", "rewrite_date",
]

# rewrite-queue header (no "source" column)
QUEUE_HEADER = [
    "cluster_id", "cluster_size", "is_representative", "next_action",
    "Bullet Point", "Role / Company", "Tags",
    "accuracy_score", "believability_score", "clarity_score",
    "ats_value", "manager_test", "weaknesses",
    "final_bullet", "rewrite_status", "rewrite_attempts",
    "rewrite_reasoning", "context_gaps", "rewrite_date",
]

TODAY = str(date.today())


def load_csv(path):
    with open(path, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def save_csv(path, rows, fieldnames):
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def to_cluster_row(queue_row):
    """Convert a rewrite-queue row into a cluster-map row."""
    return {
        "cluster_id":          queue_row.get("cluster_id", ""),
        "cluster_size":        queue_row.get("cluster_size", ""),
        "is_representative":   "True",
        "next_action":         "REWRITE",
        "Bullet Point":        queue_row.get("Bullet Point", ""),
        "Role / Company":      queue_row.get("Role / Company", ""),
        "Tags":                queue_row.get("Tags", ""),
        "accuracy_score":      "",
        "believability_score": "",
        "clarity_score":       "",
        "ats_value":           "",
        "manager_test":        "",
        "weaknesses":          queue_row.get("weaknesses", ""),
        "source":              "rewrite_queue",
        "rewrite_attempts":    "0",
        "rewrite_reasoning":   "",
        "context_gaps":        "",
        "rewrite_date":        "",
    }


def main():
    if not os.path.exists(REWRITE_QUEUE):
        print("rewrite-queue.csv not found. Exiting.")
        return
    if not os.path.exists(CLUSTER_MAP):
        print("bullet-bank-cluster-map.csv not found. Exiting.")
        return

    queue_rows = [r for r in load_csv(REWRITE_QUEUE)
                  if r.get("Bullet Point", "").strip()]
    print(f"Loaded {len(queue_rows)} active row(s) from rewrite-queue.csv.")

    if not queue_rows:
        print("Nothing in queue. Exiting.")
        return

    cluster_rows = load_csv(CLUSTER_MAP)
    print(f"Loaded {len(cluster_rows)} row(s) from bullet-bank-cluster-map.csv.")

    # Build lookup: bullet text -> list of row indices in cluster map
    cluster_index = {}
    for i, row in enumerate(cluster_rows):
        key = row.get("Bullet Point", "").strip()
        cluster_index.setdefault(key, []).append(i)

    appended = 0
    updated  = 0
    skipped  = 0

    for qrow in queue_rows:
        bullet = qrow.get("Bullet Point", "").strip()
        if not bullet:
            continue

        if bullet in cluster_index:
            # Check if any existing entry is already queued for rewrite
            indices = cluster_index[bullet]
            already_queued = any(
                cluster_rows[i].get("next_action", "").strip().upper()
                in ("REWRITE", "REVIEW")
                for i in indices
            )
            if already_queued:
                print(f"  skip (already queued): {bullet[:70]}...")
                skipped += 1
            else:
                # Update the first matching representative row
                for i in indices:
                    if cluster_rows[i].get("is_representative", "").strip().upper() == "TRUE":
                        cluster_rows[i]["next_action"]      = "REWRITE"
                        cluster_rows[i]["rewrite_attempts"] = "0"
                        cluster_rows[i]["rewrite_date"]     = ""
                        print(f"  update (set to REWRITE): {bullet[:70]}...")
                        updated += 1
                        break
                else:
                    # No representative row found; update first match anyway
                    cluster_rows[indices[0]]["next_action"] = "REWRITE"
                    print(f"  update (no rep row; updated first): {bullet[:70]}...")
                    updated += 1
        else:
            new_row = to_cluster_row(qrow)
            cluster_rows.append(new_row)
            cluster_index[bullet] = [len(cluster_rows) - 1]
            print(f"  append (new entry): {bullet[:70]}...")
            appended += 1

    print(f"\nSummary: {appended} appended | {updated} updated | {skipped} skipped.")

    save_csv(CLUSTER_MAP, cluster_rows, CLUSTER_HEADER)
    print(f"  Wrote {len(cluster_rows)} row(s) to {CLUSTER_MAP}.")

    # Clear rewrite-queue (preserve header)
    save_csv(REWRITE_QUEUE, [], QUEUE_HEADER)
    print(f"  Cleared {REWRITE_QUEUE} (header preserved).")
    print(f"\nDone! Run rewrite_bullets.py to process the {appended + updated} queued bullet(s).")


if __name__ == "__main__":
    main()
