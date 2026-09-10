"""One-off repair for checkpoint.json entries poisoned by the pre-fix
upload bug: a file that hit an empty/blocked Gemini response used to get
silently checkpointed as "done" with zero extracted content, and "done"
is permanently skipped by run_ingestion() -- so no later re-run, even
with today's retry/null-check fixes, would ever touch it again.

This finds exactly those entries (status "done", but no achievements,
work_experience, or certificate content) and resets them to "failed" so
the next `resume` bootstrap/Drop New Knowledge run retries them for
real. It never touches an entry that has real extracted content, and
backs up checkpoint.json before writing.

Usage:
    python scripts/reset_empty_checkpoint_entries.py [--profile NAME] [--apply]

Dry-run by default; pass --apply to actually rewrite the checkpoint.
"""

import argparse
import json
import os
import shutil
import sys

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, SCRIPT_DIR)

import profile_paths  # noqa: E402


def _is_empty_done_entry(result: dict) -> bool:
    if result.get("status") != "done":
        return False
    doc_type = result.get("doc_type")
    if doc_type in ("resume", "linkedin_export"):
        return not result.get("work_experience") and not result.get(
            "certificates_found"
        )
    if doc_type == "certificate":
        return not result.get("certificate")
    return not result.get("achievements")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--profile", default=None)
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()

    kb_dir = profile_paths.kb_dir(args.profile)
    checkpoint_path = os.path.join(kb_dir, "bootstrap", "checkpoint.json")
    if not os.path.exists(checkpoint_path):
        print(f"No checkpoint found at {checkpoint_path}")
        return

    with open(checkpoint_path, encoding="utf-8") as f:
        checkpoint = json.load(f)

    poisoned = [f for f, r in checkpoint.items() if _is_empty_done_entry(r)]

    if not poisoned:
        print("No empty 'done' entries found -- nothing to reset.")
        return

    print(
        f"Found {len(poisoned)} file(s) checkpointed 'done' with zero extracted content:"
    )
    for f in poisoned:
        print(f"  - {f}")

    if not args.apply:
        print("\nDry run -- pass --apply to reset these so they're retried.")
        return

    backup_path = checkpoint_path + ".bak"
    shutil.copy2(checkpoint_path, backup_path)
    print(f"\nBacked up checkpoint to {backup_path}")

    for f in poisoned:
        checkpoint[f] = {
            "status": "failed",
            "doc_type": checkpoint[f].get("doc_type", "other"),
            "reason": "reset by reset_empty_checkpoint_entries.py -- was falsely 'done' with zero results",
        }

    with open(checkpoint_path, "w", encoding="utf-8") as f:
        json.dump(checkpoint, f, indent=2)

    print(f"Reset {len(poisoned)} entries to 'failed'. Re-run ingestion to retry them.")


if __name__ == "__main__":
    main()
