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
import sys
from datetime import date

# bullet_feedback.py (which writes needs-review.csv) resolves this path from
# the script's own location, not the caller's cwd — match that here so this
# script finds the same file regardless of where it's invoked from.
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(SCRIPT_DIR)

if SCRIPT_DIR not in sys.path:
    sys.path.insert(0, SCRIPT_DIR)
import cli_art
import profile_paths  # noqa: E402
from atomic_write import atomic_write  # noqa: E402

KB_BASE = profile_paths.kb_dir()
NEEDS_REVIEW = os.path.join(KB_BASE, "needs-review.csv")
KEEPERS_CSV = os.path.join(KB_BASE, "bullet-bank-keepers.csv")
REWRITE_QUEUE = os.path.join(KB_BASE, "rewrite-queue.csv")
RETIRED_PATH = os.path.join(KB_BASE, "retired-bullets.csv")

TODAY = str(date.today())

KEEP_FIELDS = [
    "Bullet Point",
    "Role / Company",
    "Tags",
    "accuracy_score",
    "believability_score",
    "clarity_score",
    "ats_value",
    "manager_test",
    "weaknesses",
    "hidden_gem_score",
    "hidden_gem_flag",
    "hidden_gem_reason",
    "final_bullet",
    "rewrite_status",
]

# The columns that make a row traceable at all. Everything else in
# KEEP_FIELDS/QUEUE_FIELDS is either a score or a later-stage annotation, and a
# target file that predates those columns is normal; a target file missing
# these is a different file than we think it is.
REQUIRED_FIELDS = ["Bullet Point", "Role / Company"]

QUEUE_FIELDS = [
    "cluster_id",
    "cluster_size",
    "is_representative",
    "next_action",
    "Bullet Point",
    "Role / Company",
    "Tags",
    "accuracy_score",
    "believability_score",
    "clarity_score",
    "ats_value",
    "manager_test",
    "weaknesses",
    "final_bullet",
    "rewrite_status",
    "rewrite_attempts",
    "rewrite_reasoning",
    "context_gaps",
    "rewrite_date",
]


def safe_int(val, default=0):
    try:
        return int(float(str(val).strip()))
    except (ValueError, TypeError):
        return default


def read_existing_header(path) -> list | None:
    """The header actually on disk, or None if the file is absent or empty."""
    if not os.path.exists(path):
        return None
    with open(path, "r", newline="", encoding="utf-8") as f:
        return next(csv.reader(f), None)


def append_rows(path, rows, fieldnames):
    """Append rows to a CSV, writing against the header that is actually on
    disk rather than the caller's expected field list.

    This used to trust `fieldnames` unconditionally and write the header only
    when the file was absent. When the two disagreed, DictWriter emitted
    values *positionally* under the existing header -- no exception, still
    well-formed CSV, silently wrong from the first differing column onward.
    That is what happened to bullet-bank-keepers.csv: KEEP_FIELDS is 14
    columns, the real file has 16 and diverges at index 9, so every accepted
    rewrite landed with source='77' and rewrite_date='KEEPER'. Irreversible,
    because the caller deletes needs-review.csv in the same run.

    Columns present on disk but not supplied by the caller are written empty;
    a caller field that has no column on disk is a real schema mismatch and
    raises, because silently dropping it is how provenance was lost.
    """
    disk_header = read_existing_header(path)
    if disk_header is None:
        with open(path, "a", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
            writer.writeheader()
            writer.writerows(rows)
        return

    missing_required = [name for name in REQUIRED_FIELDS if name not in disk_header]
    if missing_required:
        raise ValueError(
            f"{path} is missing required column(s) {missing_required}. "
            f"On disk: {disk_header}. Refusing to append -- a bullet without "
            f"these can't be traced back to anything."
        )

    dropped = [name for name in fieldnames if name not in disk_header]
    if dropped:
        # Not fatal: KEEP_FIELDS carries columns the keepers file legitimately
        # doesn't have yet (hidden_gem_*, final_bullet, rewrite_status are
        # added by later stages). Say so out loud rather than dropping them
        # silently -- silence is what let the column shift go unnoticed.
        cli_art.cli_warning(
            f"{os.path.basename(path)} has no column for {dropped} -- not written."
        )

    with open(path, "a", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=disk_header, extrasaction="ignore")
        writer.writerows(
            {name: row.get(name, "") for name in disk_header} for row in rows
        )


def existing_keeper_bullets(path) -> set:
    """Exact Bullet Point text already present in bullet-bank-keepers.csv.
    Used to skip re-appending a bullet that's already there -- the same
    achievement can independently trigger needs-review.csv entries from
    more than one real resume-build session, and this file has never
    deduplicated against what it's about to append to."""
    if not os.path.exists(path):
        return set()
    with open(path, newline="", encoding="utf-8") as f:
        return {
            row.get("Bullet Point", "").strip()
            for row in csv.DictReader(f)
            if row.get("Bullet Point", "").strip()
        }


def main():
    if not os.path.exists(NEEDS_REVIEW):
        cli_art.cli_info("needs-review.csv not found. Nothing to triage.")
        return

    with open(NEEDS_REVIEW, newline="", encoding="utf-8") as f:
        all_rows = list(csv.DictReader(f))

    cli_art.cli_info(f"Triaging {len(all_rows)} rows from needs-review.csv...")

    keep_rows = []
    rewrite_rows = []
    retire_rows = []
    leftover = []
    n_duplicate = 0

    # Snapshot of what's already in the keeper bank, updated as this batch
    # adds to it, so two identical rows within the SAME needs-review.csv
    # (not just across separate past runs) are also caught.
    known_bullets = existing_keeper_bullets(KEEPERS_CSV)

    for row in all_rows:
        mgr_test = str(row.get("manager_test", "")).strip().upper()
        believ = safe_int(row.get("believability_score", 0))
        attempts = safe_int(row.get("rewrite_attempts", 0))
        status = str(row.get("rewrite_status", "")).strip().upper()

        # Skip already-routed rows
        if status in ("KEEPER", "REWRITE", "RETIRED", "CLOSED_OUT"):
            leftover.append(row)
            continue

        if mgr_test == "PASS" and believ >= 80:
            bullet_text = str(row.get("Bullet Point", "")).strip()
            if bullet_text and bullet_text in known_bullets:
                n_duplicate += 1
                continue  # already in the keeper bank -- don't re-add it, and don't leave it behind either
            row["rewrite_status"] = "KEEPER"
            keep_rows.append(row)
            if bullet_text:
                known_bullets.add(bullet_text)
        elif mgr_test == "FAIL" and attempts < 3:
            row["rewrite_status"] = "REWRITE"
            row["next_action"] = "REWRITE"
            row["rewrite_date"] = TODAY
            rewrite_rows.append(row)
        elif mgr_test == "FAIL" and attempts >= 3:
            row["rewrite_status"] = "RETIRED"
            row["next_action"] = "CLOSED_OUT"
            row["rewrite_date"] = TODAY
            retire_rows.append(row)
        else:
            leftover.append(row)

    cli_art.render_triage_summary_table(
        {
            "keep": len(keep_rows),
            "rewrite": len(rewrite_rows),
            "retire": len(retire_rows),
            "duplicate": n_duplicate,
            "leftover": len(leftover),
        }
    )

    if keep_rows:
        append_rows(KEEPERS_CSV, keep_rows, KEEP_FIELDS)
        cli_art.cli_success(f"Appended {len(keep_rows)} rows to {KEEPERS_CSV}")

    if rewrite_rows:
        append_rows(REWRITE_QUEUE, rewrite_rows, QUEUE_FIELDS)
        cli_art.cli_success(f"Appended {len(rewrite_rows)} rows to {REWRITE_QUEUE}")

    if retire_rows:
        append_rows(RETIRED_PATH, retire_rows, QUEUE_FIELDS)
        cli_art.cli_success(f"Appended {len(retire_rows)} rows to {RETIRED_PATH}")

    # Rewrite needs-review.csv with only unrouted rows
    if leftover:
        fieldnames = list(all_rows[0].keys()) if all_rows else QUEUE_FIELDS
        with atomic_write(NEEDS_REVIEW, newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
            writer.writeheader()
            writer.writerows(leftover)
        cli_art.cli_info(
            f"{len(leftover)} rows remain in {NEEDS_REVIEW} for manual review."
        )
    else:
        os.remove(NEEDS_REVIEW)
        cli_art.cli_success(f"All rows routed. Deleted {NEEDS_REVIEW}.")

    cli_art.cli_success("Done.")


if __name__ == "__main__":
    main()
