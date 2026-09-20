"""remove_bullets.py -- delete bullets from the bank for good.

Deleting a row from bullet-bank-keepers-audited.csv by hand does not stick:
Stage 4 merges bullet-bank-keepers.csv back in, and Stages 1-3 see the raw
bullet it came from as unfinished work. This script removes the bullet from
both keeper files AND records it in removed-bullets.csv, which every stage
consults (see bullet_bank_state.py), so no rerun brings it back.

    python scripts/remove_bullets.py                     # interactive search
    python scripts/remove_bullets.py --text "..." --reason "duplicate" --yes
    python scripts/remove_bullets.py --from-review review.csv --yes
    python scripts/remove_bullets.py --backfill [--yes]
    python scripts/remove_bullets.py --since-backup old-keepers-audited.csv [--yes]

--from-review reads a CSV with "Bullet Point" and "decision" columns and
removes the rows marked "remove". --backfill lists keepers.csv rows Stage 4
would still merge back into the audited bank and, with --yes, records them
as removed -- for bullets deleted by hand before this list existed. Check
the list first: a keeper triaged in since the last Stage 4 run shows up
there too, and that one is new, not removed. --since-backup records every
bullet in a backed-up pipeline file that is gone from the current file of
the same name.

Without --yes nothing is written. Both keeper files are backed up first.
Rerun Stage 6 (Embed) afterward so resume builds stop matching removed
bullets.
"""

import argparse
import csv
import datetime
import os
import shutil
import sys

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
if SCRIPT_DIR not in sys.path:
    sys.path.insert(0, SCRIPT_DIR)
import bullet_bank_state  # noqa: E402
import cli_art  # noqa: E402
import profile_paths  # noqa: E402
from atomic_write import atomic_write  # noqa: E402

KB_DIR = profile_paths.kb_dir()
KEEPERS_CSV = os.path.join(KB_DIR, "bullet-bank-keepers.csv")
KEEPERS_AUDITED_CSV = os.path.join(KB_DIR, "bullet-bank-keepers-audited.csv")
REMOVED_CSV = bullet_bank_state.removed_path(KB_DIR)


def _read(path):
    if not os.path.exists(path):
        return [], []
    with open(path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        return list(reader), list(reader.fieldnames or [])


def _write(path, rows, fieldnames):
    with atomic_write(path, newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def backup(paths) -> str:
    stamp = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
    dest = os.path.join(KB_DIR, "backups", f"remove-{stamp}")
    os.makedirs(dest, exist_ok=True)
    for path in paths:
        if os.path.exists(path):
            shutil.copy2(path, dest)
    return dest


def find_rows(texts) -> list:
    """Rows (from the audited bank, else keepers.csv) whose Bullet Point
    matches one of `texts` after normalization -- one row per text."""
    wanted = {bullet_bank_state.normalize(t) for t in texts} - {""}
    found = {}
    for path in (KEEPERS_AUDITED_CSV, KEEPERS_CSV):
        for row in _read(path)[0]:
            key = bullet_bank_state.normalize(row.get("Bullet Point"))
            if key in wanted and key not in found:
                found[key] = row
    return list(found.values())


def remove(rows, reason) -> tuple:
    """Records `rows` as removed and deletes every copy from both keeper
    files. Returns (tombstones added, rows deleted)."""
    keys = {bullet_bank_state.normalize(r.get("Bullet Point")) for r in rows} - {""}
    added = bullet_bank_state.record_removed(REMOVED_CSV, rows, reason)
    deleted = 0
    for path in (KEEPERS_AUDITED_CSV, KEEPERS_CSV):
        existing, fieldnames = _read(path)
        kept = [
            r
            for r in existing
            if bullet_bank_state.normalize(r.get("Bullet Point")) not in keys
        ]
        if len(kept) != len(existing):
            deleted += len(existing) - len(kept)
            _write(path, kept, fieldnames)
    return added, deleted


def backfill_candidates() -> list:
    """keepers.csv rows Stage 4's merge would add back to the audited bank."""
    import audit_keepers
    import pandas as pd

    if not (os.path.exists(KEEPERS_CSV) and os.path.exists(KEEPERS_AUDITED_CSV)):
        return []
    df_audited = pd.read_csv(KEEPERS_AUDITED_CSV)
    df_in = pd.read_csv(KEEPERS_CSV)
    merged, n_new = audit_keepers.merge_new_rows_from_keepers_in(
        df_audited, df_in, bullet_bank_state.load_removed(REMOVED_CSV)
    )
    if not n_new:
        return []
    return merged.tail(n_new).fillna("").to_dict("records")


def since_backup_candidates(backup_path) -> list:
    """Bullets in a backed-up pipeline file that are gone from the current
    file of the same name (bullet-bank-audited.csv, -keepers-audited.csv,
    ...) -- a cleanup done by hand before the removed list existed."""
    current = {
        bullet_bank_state.normalize(r.get("Bullet Point"))
        for r in _read(os.path.join(KB_DIR, os.path.basename(backup_path)))[0]
    }
    removed = bullet_bank_state.load_removed(REMOVED_CSV)
    return [
        r
        for r in _read(backup_path)[0]
        if bullet_bank_state.normalize(r.get("Bullet Point")) not in current
        and not removed.blocks(r.get("Bullet Point"))
    ]


def review_candidates(review_path) -> list:
    rows = _read(review_path)[0]
    marked = [
        r["Bullet Point"]
        for r in rows
        if str(r.get("decision", "")).strip().lower() == "remove"
    ]
    return find_rows(marked)


def _show(rows):
    for row in rows:
        company = row.get("Role / Company", "")
        # markup=False: bullet text can contain [brackets].
        cli_art.console.print(
            f"  [{company}] {row.get('Bullet Point', '')}", markup=False, soft_wrap=True
        )


def _interactive():
    phrase = cli_art.text("Search the keeper bank for (a word or phrase):")
    if not phrase:
        return
    needle = bullet_bank_state.normalize(phrase)
    matches = [
        r
        for r in _read(KEEPERS_AUDITED_CSV)[0] or _read(KEEPERS_CSV)[0]
        if needle in bullet_bank_state.normalize(r.get("Bullet Point"))
    ]
    if not matches:
        cli_art.cli_info(f'No keeper bullets contain "{phrase}".')
        return
    labels = {
        f"[{r.get('Role / Company', '')}] {r.get('Bullet Point', '')}": r
        for r in matches
    }
    picked = cli_art.checkbox("Which bullets should be removed for good?", list(labels))
    if not picked:
        return
    reason = cli_art.text("Why? (saved with the removal)", default="removed by hand")
    if not cli_art.confirm(f"Remove {len(picked)} bullet(s)?", default=False):
        return
    _apply([labels[p] for p in picked], reason or "removed by hand", delete=True)


def _apply(rows, reason, delete):
    dest = backup([KEEPERS_CSV, KEEPERS_AUDITED_CSV, REMOVED_CSV])
    if delete:
        added, deleted = remove(rows, reason)
    else:
        added, deleted = bullet_bank_state.record_removed(REMOVED_CSV, rows, reason), 0
    cli_art.cli_success(
        f"Recorded {added} removal(s); deleted {deleted} row(s) from the keeper files."
    )
    cli_art.cli_info(f"Backup: {dest}")
    if deleted:
        cli_art.cli_info("Rerun Stage 6 (Embed) so resume builds stop matching them.")


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--text", action="append", help="exact bullet text (repeatable)")
    group.add_argument("--from-review", metavar="CSV")
    group.add_argument("--backfill", action="store_true")
    group.add_argument("--since-backup", metavar="CSV")
    parser.add_argument("--reason", default=None)
    parser.add_argument("--yes", action="store_true", help="write changes")
    args = parser.parse_args(argv)

    if args.text:
        rows, reason, delete = (
            find_rows(args.text),
            args.reason or "removed by hand",
            True,
        )
    elif args.from_review:
        rows, reason, delete = (
            review_candidates(args.from_review),
            args.reason or "near-duplicate review",
            True,
        )
    elif args.backfill:
        rows, reason, delete = (
            backfill_candidates(),
            args.reason or "backfill: deleted from audited bank before removed list",
            False,
        )
    elif args.since_backup:
        rows, reason, delete = (
            since_backup_candidates(args.since_backup),
            args.reason or "backfill: deleted from audited bank before removed list",
            False,
        )
    else:
        _interactive()
        return 0

    if not rows:
        cli_art.cli_info("Nothing to remove.")
        return 0
    _show(rows)
    if not args.yes:
        cli_art.cli_info(f"{len(rows)} bullet(s) listed. Rerun with --yes to apply.")
        return 0
    _apply(rows, reason, delete)
    return 0


if __name__ == "__main__":
    sys.exit(main())
