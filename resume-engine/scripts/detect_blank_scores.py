"""
detect_blank_scores.py
-----------------------
Scans bullet-bank-audited.csv for rows with blank scoring fields and
appends them to rewrite-queue.csv. Safe to re-run — deduplicates by
bullet text before writing.

Usage:
    python detect_blank_scores.py
"""

import csv
import os

AUDITED_PATH     = "resume-engine/knowledge_base/bullet-bank-audited.csv"
REWRITE_QUEUE    = "resume-engine/knowledge_base/rewrite-queue.csv"
SCORE_FIELDS     = ["accuracy_score", "believability_score",
                    "clarity_score", "ats_value", "manager_test"]

REWRITE_HEADER = [
    "cluster_id","cluster_size","is_representative","next_action",
    "Bullet Point","Role / Company","Tags",
    "accuracy_score","believability_score","clarity_score",
    "ats_value","manager_test","weaknesses",
    "final_bullet","rewrite_status","rewrite_attempts",
    "rewrite_reasoning","context_gaps","rewrite_date",
]


def load_existing_bullets(path):
    if not os.path.exists(path):
        return set()
    with open(path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        return {row["Bullet Point"].strip() for row in reader}


def find_blank_score_rows(path):
    blank_rows = []
    with open(path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            if all(row.get(field, "").strip() == "" for field in SCORE_FIELDS):
                blank_rows.append(row)
    return blank_rows


def build_rewrite_row(source_row):
    """Convert an audited row into a rewrite-queue row."""
    return {
        "cluster_id":          "",
        "cluster_size":        "",
        "is_representative":   "True",
        "next_action":         "REWRITE",
        "Bullet Point":        source_row.get("Bullet Point", ""),
        "Role / Company":      source_row.get("Role / Company", ""),
        "Tags":                source_row.get("Tags", ""),
        "accuracy_score":      "",
        "believability_score": "",
        "clarity_score":       "",
        "ats_value":           "",
        "manager_test":        "",
        "weaknesses":          source_row.get("weaknesses", ""),
        "final_bullet":        "",
        "rewrite_status":      "PENDING",
        "rewrite_attempts":    "0",
        "rewrite_reasoning":   "Auto-detected: missing scores in bullet-bank-audited.csv",
        "context_gaps":        "",
        "rewrite_date":        "",
    }


def main():
    print("Scanning for blank-score rows in:", AUDITED_PATH)
    blank_rows = find_blank_score_rows(AUDITED_PATH)
    print(f"  Found {len(blank_rows)} blank-score row(s).")

    if not blank_rows:
        print("Nothing to do. Exiting.")
        return

    existing_bullets = load_existing_bullets(REWRITE_QUEUE)
    new_rows = [r for r in blank_rows
                if r.get("Bullet Point", "").strip() not in existing_bullets]

    if not new_rows:
        print("All blank-score bullets already exist in rewrite-queue. Nothing added.")
        return

    file_exists = os.path.exists(REWRITE_QUEUE)
    with open(REWRITE_QUEUE, "a", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=REWRITE_HEADER, extrasaction="ignore")
        if not file_exists:
            writer.writeheader()
        for row in new_rows:
            writer.writerow(build_rewrite_row(row))

    print(f"  Appended {len(new_rows)} new row(s) to {REWRITE_QUEUE}.")
    for r in new_rows:
        print(f"    - [{r.get('Role / Company','')}] {r.get('Bullet Point','')[:80]}...")


if __name__ == "__main__":
    main()
