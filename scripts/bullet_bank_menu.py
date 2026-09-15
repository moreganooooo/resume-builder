"""bullet_bank_menu.py -- the "Manage Bullet Bank" submenu: shows
staleness/last-run status for the 6 rebuild-pipeline stages
(audit_bullet_bank.py -> cluster_bullet_bank.py -> rewrite_bullets.py ->
audit_keepers.py -> score_keeper_gems.py -> embed_bullet_bank.py) plus 3
maintenance scripts, and runs any one of them individually as a
subprocess -- unmodified, exactly as bootstrap_bullet_bank.py's own
run_stage() does. Two maintenance scripts are optional follow-ups tied to
a specific stage and render directly under it in the menu (rewrite-queue
retirement under Rewrite Weak Bullets; audit_keepers.py --auto-rewrite,
which retries bullets still MANUAL after re-audit, under Re-Audit
Keepers). The third (needs-review triage) isn't tied to the rebuild
pipeline at all -- it clears a queue that fills up from everyday resume
builds -- so it renders in its own "Ongoing Maintenance" section instead.
See docs/superpowers/specs/2026-07-15-bullet-bank-management-design.md.
"""

import csv
import datetime
import os
import subprocess
import sys

import cli_art
import questionary

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(SCRIPT_DIR)

if SCRIPT_DIR not in sys.path:
    sys.path.insert(0, SCRIPT_DIR)
import bullet_bank_state  # noqa: E402
import profile_paths  # noqa: E402

KB_DIR = profile_paths.kb_dir()

RAW_CSV = os.path.join(KB_DIR, "bullet-bank-clean.csv")
AUDITED_CSV = os.path.join(KB_DIR, "bullet-bank-audited.csv")
CLUSTER_MAP_CSV = os.path.join(KB_DIR, "bullet-bank-cluster-map.csv")
CLUSTER_MAP_OUT_CSV = os.path.join(KB_DIR, "bullet-bank-cluster-map-updated.csv")
KEEPERS_CSV = os.path.join(KB_DIR, "bullet-bank-keepers.csv")
KEEPERS_AUDITED_CSV = os.path.join(KB_DIR, "bullet-bank-keepers-audited.csv")
NPY_PATH = os.path.join(KB_DIR, "bullet_vectors_ge2_d768.npy")
NEEDS_REVIEW_CSV = os.path.join(KB_DIR, "needs-review.csv")
REWRITE_QUEUE_CSV = os.path.join(KB_DIR, "rewrite-queue.csv")
AUDIT_REWRITE_QUEUE_CSV = os.path.join(KB_DIR, "audit-rewrite-queue.csv")
CLUSTER_CHECKPOINT_PATH = os.path.join(
    KB_DIR, "bullet_vectors_ge2_d768_cluster.checkpoint.npz"
)
EMBED_CHECKPOINT_PATH = os.path.join(KB_DIR, "bullet_vectors_ge2_d768.checkpoint.npz")
EMBED_META_PATH = os.path.join(KB_DIR, "bullet_vectors_ge2_d768.meta")
REMOVED_CSV = bullet_bank_state.removed_path(KB_DIR)


def _removed():
    """removed-bullets.csv, read fresh -- a bullet removed on purpose is
    settled work for every stage, never pending (see bullet_bank_state)."""
    return bullet_bank_state.load_removed(REMOVED_CSV)

# Statuses that mark a rewrite-stage row as done -- mirrors
# rewrite_bullets.py's own DONE_STATUSES, duplicated here rather than
# imported since importing rewrite_bullets.py just for one constant would
# pull in its whole module (pydantic schemas, prompt-building code) for a
# menu screen that only needs this one set.
REWRITE_DONE_STATUSES = {"KEEP", "MANUAL"}


# ---------------------------------------------------------------------------
# PROGRESS FUNCTIONS
#
# Four of the six stages can be left genuinely mid-run (interrupted, or
# resumed across sessions) with their declared "output" file present but
# incomplete -- a plain mtime comparison can't tell "fully done" from
# "partially done", so it was reporting a clean "Up to date" the moment ANY
# output existed, even with hundreds of bullets still pending. Each
# function below returns (done, total), or None if there's nothing to
# report yet (falls through to the normal mtime/never-run check).
#
# The other two stages don't need this: cluster_bullet_bank.py writes its
# final CLUSTER_MAP_CSV exactly once, atomically, only after all in-memory
# clustering is complete (the only partial state is mid-embedding, already
# covered by its "checkpoint" key below); score_keeper_gems.py is already
# covered by status_mode="columns", which checks per-row completeness
# directly rather than trusting a timestamp.
# ---------------------------------------------------------------------------


def _audit_progress():
    if not os.path.exists(RAW_CSV):
        return None
    with open(RAW_CSV, newline="", encoding="utf-8") as f:
        raw_texts = {str(row.get("Bullet Point")) for row in csv.DictReader(f)}
    total = len(raw_texts)
    if os.path.exists(AUDITED_CSV):
        # audit_bullet_bank.py flushes to disk after every row and its
        # output only ever contains rows actually scored so far, so row
        # count would be the progress signal here -- EXCEPT that script's
        # own resume-from-checkpoint logic skips a raw row whenever its
        # exact Bullet Point text already appears in the audited output
        # (deliberately: never re-score identical text). A raw bank with
        # duplicate rows -- e.g. the same achievement re-extracted from
        # two overlapping source documents, not yet collapsed by the
        # cluster stage that runs after this one -- always finishes with
        # fewer audited ROWS than raw ROWS by design, which used to read
        # here as a permanently-stuck "N pending" for duplicates that will
        # never be processed, could never shrink, and were not actually
        # unfinished work. Comparing unique TEXT on both sides instead
        # matches what audit_bullet_bank.py itself considers "already
        # scored," so the two can't drift out of sync again.
        with open(AUDITED_CSV, newline="", encoding="utf-8") as f:
            audited_texts = {str(row.get("Bullet Point")) for row in csv.DictReader(f)}
    else:
        audited_texts = set()
    removed = _removed()
    done = sum(1 for t in raw_texts if t in audited_texts or removed.settles(t))
    return (done, total)


def _rewrite_progress():
    # Lazy pandas -- Lite Mode omits it; see requirements-lite.txt (F20).
    import pandas as pd

    if not os.path.exists(CLUSTER_MAP_CSV):
        return None
    df = pd.read_csv(CLUSTER_MAP_CSV)
    mask_rep = (
        df["is_representative"]
        .astype(str)
        .str.strip()
        .str.lower()
        .isin(["true", "1", "yes"])
    )
    mask_action = (
        df["next_action"]
        .astype(str)
        .str.strip()
        .str.upper()
        .isin(["REWRITE", "REVIEW"])
    )
    target = df[mask_rep & mask_action]
    total = len(target)
    if total == 0:
        return (0, 0)

    # Mirrors rewrite_bullets.py's own load_already_processed(): a target
    # bullet counts as done if it shows up KEEP/MANUAL in the incremental
    # cluster-map output, or anywhere in the keepers CSV (which also holds
    # bullets seeded as already-KEEP before any rewrite run).
    done_bullets = set()
    if os.path.exists(CLUSTER_MAP_OUT_CSV):
        df_out = pd.read_csv(CLUSTER_MAP_OUT_CSV)
        if "rewrite_status" in df_out.columns and "Bullet Point" in df_out.columns:
            done_mask = (
                df_out["rewrite_status"]
                .astype(str)
                .str.strip()
                .str.upper()
                .isin(REWRITE_DONE_STATUSES)
            )
            done_bullets |= set(
                df_out.loc[done_mask, "Bullet Point"].dropna().str.strip()
            )
            if "final_bullet" in df_out.columns:
                done_bullets |= set(
                    df_out.loc[done_mask, "final_bullet"].dropna().str.strip()
                )
    if os.path.exists(KEEPERS_CSV):
        df_k = pd.read_csv(KEEPERS_CSV)
        if "Bullet Point" in df_k.columns:
            done_bullets |= set(df_k["Bullet Point"].dropna().str.strip())
        # original_bullet (added alongside rewrite_bullets.py's
        # load_already_processed() fix) holds the raw text a keeper was
        # rewritten FROM, which is what actually matches a target row's
        # raw "Bullet Point" -- the keeper's own "Bullet Point" column
        # holds the FINAL rewritten text instead. Rows written before this
        # column existed just contribute nothing extra here.
        if "original_bullet" in df_k.columns:
            done_bullets |= set(df_k["original_bullet"].dropna().str.strip())

    removed = _removed()
    done = int(
        target["Bullet Point"]
        .astype(str)
        .str.strip()
        .map(lambda t: t in done_bullets or removed.settles(t))
        .sum()
    )
    return (done, total)


def _cluster_progress():
    """Clean bullets present in the cluster map, by normalized TEXT. The map
    used to be judged by mtime, so any edit to the clean or audited file --
    including a deliberate removal -- read as "Stale" while a real addition
    made after the last run could still read "Up to date". A bullet removed
    on purpose counts as done: clustering it again only feeds it back into
    rewriting."""
    if not os.path.exists(RAW_CSV) or not os.path.exists(CLUSTER_MAP_CSV):
        return None
    norm = bullet_bank_state.normalize
    with open(RAW_CSV, newline="", encoding="utf-8") as f:
        raw = {norm(row.get("Bullet Point")) for row in csv.DictReader(f)} - {""}
    with open(CLUSTER_MAP_CSV, newline="", encoding="utf-8") as f:
        mapped = {norm(row.get("Bullet Point")) for row in csv.DictReader(f)}
    removed = _removed()
    done = sum(1 for t in raw if t in mapped or removed.settles(t))
    return (done, len(raw))


def _audit_keepers_progress():
    if not os.path.exists(KEEPERS_AUDITED_CSV):
        return None
    with open(KEEPERS_AUDITED_CSV, newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    total = len(rows)
    if total == 0:
        return (0, 0)
    done = sum(1 for row in rows if (row.get("audit_status") or "").strip())
    return (done, total)


def _embed_index_current():
    """True/False when the primary index's stored bullets_sha does / does not
    match keepers-audited's current bullet text; None when either side is
    missing (the plain existence/mtime check decides then). Content, not
    mtime: a column-only rewrite of keepers-audited (Step 5 scoring gems)
    bumps its mtime without touching a bullet, and read as "Stale" here."""
    import json

    from bullet_bank_hash import bullets_sha

    if not (os.path.exists(EMBED_META_PATH) and os.path.exists(KEEPERS_AUDITED_CSV)):
        return None
    try:
        with open(EMBED_META_PATH, "r", encoding="utf-8") as f:
            meta = json.load(f)
    except (OSError, ValueError):
        return None
    with open(KEEPERS_AUDITED_CSV, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        # Same column choice and empty-cell handling as embed_bullet_bank.main().
        col = next(
            (c for c in ("Bullet Point", "bullet", "achievement") if c in (reader.fieldnames or [])),
            None,
        )
        if col is None:
            return None
        texts = [row.get(col) or "" for row in reader]
    return meta.get("bullets_sha") == bullets_sha(texts) and meta.get("rows") == len(texts)


def _embed_progress():
    # Lazy numpy -- Lite Mode omits it; see requirements-lite.txt (F20).
    import numpy as np

    if not os.path.exists(EMBED_CHECKPOINT_PATH):
        # No checkpoint means either never run or fully complete (the
        # final .npy is only ever written once, after the full batch loop
        # finishes) -- either way, let the normal mtime/never-run check
        # below decide.
        return None
    data = np.load(EMBED_CHECKPOINT_PATH, allow_pickle=False)
    done = int(data["next_index"])
    total = done
    if os.path.exists(KEEPERS_AUDITED_CSV):
        with open(KEEPERS_AUDITED_CSV, newline="", encoding="utf-8") as f:
            total = sum(1 for _ in csv.DictReader(f))
    return (done, max(total, done))


# Verified directly against each script's own path constants -- see
# docs/superpowers/specs/2026-07-15-bullet-bank-management-design.md's
# Architecture section 1 table.
STAGES = [
    {
        "key": "audit",
        "number": 1,
        "label": "Audit Bullet Bank (Score Quality)",
        "description": "scores every raw bullet for accuracy, clarity, and impact",
        "script": "audit_bullet_bank.py",
        "inputs": [RAW_CSV],
        "output": AUDITED_CSV,
        "api_cost": True,
        "status_mode": "progress",
        "progress_fn": _audit_progress,
    },
    {
        "key": "cluster",
        "number": 2,
        "label": "Cluster & Classify Bullets",
        "description": "groups near-duplicate bullets, flags which ones need rewriting",
        "script": "cluster_bullet_bank.py",
        "inputs": [RAW_CSV, AUDITED_CSV],
        "output": CLUSTER_MAP_CSV,
        "api_cost": True,
        "status_mode": "progress",
        "progress_fn": _cluster_progress,
        "checkpoint": CLUSTER_CHECKPOINT_PATH,
    },
    {
        "key": "rewrite",
        "number": 3,
        "label": "Rewrite Weak Bullets",
        "description": "rewrites flagged bullets via Gemini until each one passes",
        "script": "rewrite_bullets.py",
        "inputs": [CLUSTER_MAP_CSV],
        "output": KEEPERS_CSV,
        "api_cost": True,
        "status_mode": "progress",
        "progress_fn": _rewrite_progress,
    },
    {
        "key": "audit_keepers",
        "number": 4,
        "label": "Re-Audit Keepers",
        "description": "rescores keepers, builds a queue of bullets still needing work",
        "script": "audit_keepers.py",
        "inputs": [KEEPERS_CSV],
        "output": KEEPERS_AUDITED_CSV,
        "api_cost": True,
        "status_mode": "progress",
        "progress_fn": _audit_keepers_progress,
    },
    {
        "key": "score_gems",
        "number": 5,
        "label": "Score Hidden Gems",
        "description": "flags standout bullets worth surfacing more often",
        "script": "score_keeper_gems.py",
        "inputs": [KEEPERS_AUDITED_CSV],
        "output": KEEPERS_AUDITED_CSV,
        "api_cost": True,
        "status_mode": "columns",
        "status_columns": ["hidden_gem_score", "hidden_gem_flag"],
    },
    {
        "key": "embed",
        "number": 6,
        "label": "Embed Bullet Bank (Final Step)",
        "description": "builds the embeddings real resume builds match against, plus the\n"
        "backup model's index used when the primary is rate-limited\n",
        "script": "embed_bullet_bank.py",
        "inputs": [KEEPERS_AUDITED_CSV],
        "output": NPY_PATH,
        "api_cost": True,
        "status_mode": "progress",
        "progress_fn": _embed_progress,
        "current_fn": _embed_index_current,
    },
]

# Each entry's "after_stage" (a STAGES key, or None) says where it renders
# in _build_choices(): right under that stage as an optional follow-up, or
# -- when None -- down in the standalone "Ongoing Maintenance" section,
# for the one entry (triage) that isn't tied to a specific pipeline stage
# at all (needs-review.csv fills up from everyday resume builds, not from
# running the 6-stage rebuild).
MAINTENANCE = [
    {
        "key": "triage",
        "label": "Triage Needs-Review Queue",
        "after_stage": None,
        "description": "routes bullets queued during real resume builds into keepers/rewrite/retired",
        "script": "triage_needs_review.py",
        "watched_file": NEEDS_REVIEW_CSV,
        "api_cost": False,
    },
    {
        "key": "remove",
        "label": "Remove Bullets",
        "after_stage": None,
        "description": "deletes bullets from the bank for good -- every stage remembers,\n"
        "so a rerun never brings them back\n",
        "script": "remove_bullets.py",
        "watched_file": REMOVED_CSV,
        "api_cost": False,
    },
    {
        "key": "retire",
        "label": "Retire Abandoned Rewrite-Queue Bullets",
        "after_stage": "rewrite",
        "description": "clears out bullets that ran out of rewrite attempts without becoming keepers",
        "script": "retire_rewrite_queue.py",
        "watched_file": REWRITE_QUEUE_CSV,
        "api_cost": False,
    },
    {
        "key": "auto_rewrite",
        "label": "Auto-Rewrite Manual Bullets",
        "after_stage": "audit_keepers",
        "description": "retries bullets still MANUAL after re-audit through the rewriter again",
        "script": "audit_keepers.py",
        "args": ["--auto-rewrite"],
        "watched_file": AUDIT_REWRITE_QUEUE_CSV,
        "api_cost": True,
    },
]

_ALL_ENTRIES = {entry["key"]: entry for entry in STAGES + MAINTENANCE}


def _stage_status(stage: dict) -> tuple:
    """Returns (status_label, detail). status_mode='mtime' (cluster_bullet_bank.py
    only -- its final CSV is written once, atomically, so file existence
    genuinely means "done") compares mtimes. status_mode='columns'
    (score_keeper_gems.py, which updates its file in place -- same file in
    and out, so an mtime comparison against itself is meaningless) checks
    column completeness instead. status_mode='progress' (the four stages
    that flush partial results to their output file as they go) checks a
    real done/total count via the stage's progress_fn -- an output file
    existing does NOT mean a progress-mode stage is finished, so this runs
    before the file-existence check below, not after. A stage with a
    'checkpoint' key reports in-progress resume state when its real output
    doesn't exist yet."""
    if stage.get("status_mode") == "columns":
        return _column_completeness_status(stage["output"], stage["status_columns"])

    if stage.get("status_mode") == "progress":
        progress = stage["progress_fn"]()
        if progress is not None:
            done, total = progress
            if total > 0 and done < total:
                return (
                    "In progress",
                    f"{done}/{total} processed ({total - done} pending)",
                )
            # done >= total (including total == 0): every target bullet
            # this stage cares about is already handled. The progress
            # count is authoritative here -- don't fall through to the
            # mtime-vs-input check below, which would wrongly report
            # "Stale" whenever an upstream file's mtime moves for a
            # reason that didn't add real new work (e.g. cluster_bullet_
            # bank.py rewriting bullet-bank-cluster-map.csv with the same
            # target bullets under newly-stable cluster IDs -- confirmed
            # for real: this stage kept reporting Stale immediately after
            # a run that correctly found 0 bullets left to process).
            progress_output = stage["output"]
            if os.path.exists(progress_output):
                timestamp = datetime.datetime.fromtimestamp(
                    os.path.getmtime(progress_output)
                ).strftime("%Y-%m-%d %H:%M")
                return ("Up to date", f"as of {timestamp}")

    output = stage["output"]
    if not os.path.exists(output):
        checkpoint = stage.get("checkpoint")
        if checkpoint and os.path.exists(checkpoint):
            return _checkpoint_progress_status(checkpoint)
        return ("Never run", "")

    output_mtime = os.path.getmtime(output)
    timestamp = datetime.datetime.fromtimestamp(output_mtime).strftime("%Y-%m-%d %H:%M")

    # A stage that can compare content (the embed index's stored hash)
    # decides by that instead of mtime; None falls back to mtime.
    current_fn = stage.get("current_fn")
    current = current_fn() if current_fn else None
    if current is True:
        return ("Up to date", f"as of {timestamp}")
    if current is False:
        return ("Stale", "bullet text changed since last embed")

    for input_path in stage["inputs"]:
        if os.path.exists(input_path) and os.path.getmtime(input_path) > output_mtime:
            return ("Stale", "")

    return ("Up to date", f"as of {timestamp}")


def _safe_stage_status(stage: dict) -> tuple:
    """_stage_status(), but a malformed or half-written pipeline file (a
    missing column, a corrupt CSV or checkpoint) is reported on its own row
    instead of raising out of the status render -- which made the whole
    Bullet Bank screen unopenable, including the very stage that would
    rebuild the bad file."""
    try:
        return _stage_status(stage)
    except Exception as e:  # noqa: BLE001 -- see docstring
        return ("Unreadable", f"{type(e).__name__}: {e}")


def _safe_maintenance_status(entry: dict) -> str:
    """Same guard as _safe_stage_status() for the maintenance rows."""
    try:
        return _maintenance_status(entry)
    except Exception as e:  # noqa: BLE001 -- see _safe_stage_status
        return f"unreadable ({type(e).__name__})"


def _checkpoint_progress_status(checkpoint_path: str) -> tuple:
    # Lazy numpy -- Lite Mode omits it; see requirements-lite.txt (F20).
    import numpy as np

    data = np.load(checkpoint_path, allow_pickle=False)
    next_index = int(data["next_index"])
    total = int(data["total"])
    return ("Never run", f"checkpoint at bullet {next_index}/{total} -- resumable")


def _column_completeness_status(csv_path: str, columns: list) -> tuple:
    if not os.path.exists(csv_path):
        return ("Never run", "")
    with open(csv_path, newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    if not rows:
        return ("Never run", "")
    for col in columns:
        if any(not (row.get(col) or "").strip() for row in rows):
            return ("Stale", "")
    return ("Up to date", "")


def _maintenance_status(entry: dict) -> str:
    path = entry["watched_file"]

    if entry["key"] == "triage":
        if not os.path.exists(path):
            return "empty -- nothing to triage"
        with open(path, newline="", encoding="utf-8") as f:
            count = sum(1 for _ in csv.DictReader(f))
        return "empty -- nothing to triage" if count == 0 else f"{count} row(s) waiting"

    if entry["key"] == "remove":
        count = len(_removed())
        return "none removed yet" if count == 0 else f"{count} removed so far"

    if entry["key"] == "retire":
        if not os.path.exists(path):
            return "none pending"
        with open(path, newline="", encoding="utf-8") as f:
            rows = list(csv.DictReader(f))
        pending = sum(
            1
            for row in rows
            if (row.get("is_representative") or "").strip().lower() == "false"
        )
        return (
            "none pending"
            if pending == 0
            else f"{pending} bullet(s) pending retirement"
        )

    if entry["key"] == "auto_rewrite":
        # audit-rewrite-queue.csv (Stage 3's output) is a snapshot taken
        # BEFORE Stage 4 processes it -- nothing rewrites this file
        # afterward, even though Stage 4 (part of this very action) may
        # have just resolved every one of those bullets. Reading its row
        # count here would show what went INTO the run, not what's left
        # OUTSTANDING after it -- confirmed for real: a run that
        # successfully resolved all 11 queued bullets (0 left MANUAL/
        # NEEDS_REWRITE in the audited file) still displayed "11 queued"
        # afterward, making it look like nothing happened. Recompute live
        # from the audited keepers file instead, same criterion Stage 3's
        # own Source A uses, so this always reflects current reality.
        if not os.path.exists(KEEPERS_AUDITED_CSV):
            return "empty -- nothing queued"
        with open(KEEPERS_AUDITED_CSV, newline="", encoding="utf-8") as f:
            rows = list(csv.DictReader(f))
        pending = sum(
            1
            for row in rows
            if (row.get("audit_status") or "").strip() in ("MANUAL", "NEEDS_REWRITE")
        )
        return (
            "empty -- nothing queued"
            if pending == 0
            else f"{pending} bullet(s) queued for auto-rewrite"
        )

    return ""


def _confirm(label: str) -> bool:
    return cli_art.confirm(
        f'Ready to run "{label}"? This calls the Gemini API and may take a while.',
        default=True,
    )


def _handle_choice(choice: str) -> None:
    entry = _ALL_ENTRIES[choice]
    if entry.get("api_cost") and not _confirm(entry["label"]):
        return

    import menu

    scroll_region_modified = False
    suspended_alt_screen = False
    title = f"BULLET BANK | {entry['label'].upper()}"

    # Same approach as menu._run_with_chain(): the alternate screen buffer
    # has no real scrollback, and a pipeline stage prints per-bullet
    # progress for hundreds of bullets -- everything that scrolled past the
    # top was gone for good. Drop to the primary screen for the run so the
    # terminal's native scrollback works, then re-enter alt-screen after.
    if menu._should_use_alt_screen():
        sys.stdout.write("\x1b[?1049l")
        sys.stdout.flush()
        suspended_alt_screen = True

    # Clear screen and draw the compact banner!
    sys.stdout.write("\x1b[2J\x1b[H")
    sys.stdout.flush()
    cli_art.display_compact_banner(title)

    if not suspended_alt_screen:
        # The pinned footer only stays pinned via the DECSTBM clamp below,
        # and that clamp is exactly what breaks scrollback -- so both only
        # apply when we're still inside alt-screen (no scrollback to lose).
        cli_art.display_execution_footer()

        # Set dynamic scroll region to freeze rows 1-4 (header) and the bottom row (footer)
        import shutil

        _, rows = shutil.get_terminal_size()
        sys.stdout.write(f"\x1b[5;{rows-1}r")
        sys.stdout.write("\x1b[5;1H")
        sys.stdout.flush()
        scroll_region_modified = True

    try:
        script_path = os.path.join(SCRIPT_DIR, entry["script"])
        result = subprocess.run([sys.executable, script_path, *entry.get("args", [])])
        if result.returncode != 0:
            cli_art.display_error(
                f"{entry['script']} exited with an error -- check the output above."
            )
    finally:
        if scroll_region_modified:
            # Clean up: restore the scroll region back to the entire screen window
            sys.stdout.write("\x1b[r")
            sys.stdout.flush()
        # run_bullet_bank_menu() clears the screen at the top of its loop
        # under alt-screen, so without a pause the stage's whole output --
        # including the "exited with an error" line -- vanished unread.
        # Paused BEFORE re-entering alt-screen, so the output is read on the
        # primary screen, where it can still be scrolled back through.
        menu._pause_and_return()
        if suspended_alt_screen:
            sys.stdout.write("\x1b[?1049h\x1b[H")
            sys.stdout.flush()


def _build_choices() -> list:
    choices = []
    for stage in STAGES:
        choices.append(
            questionary.Choice(
                title=[
                    ("class:text", f"{stage['number']}. {stage['label']}  "),
                    ("class:description", f"({stage['description']})"),
                ],
                value=stage["key"],
            )
        )
        for entry in MAINTENANCE:
            if entry["after_stage"] == stage["key"]:
                choices.append(
                    questionary.Choice(
                        title=[
                            (
                                "class:description",
                                f"      ↳ {entry['label']} (optional follow-up: ",
                            ),
                            ("class:description", f"{entry['description']})"),
                        ],
                        value=entry["key"],
                    )
                )

    standalone = [entry for entry in MAINTENANCE if entry["after_stage"] is None]
    if standalone:
        choices.append(questionary.Separator(" "))
        choices.append(
            questionary.Separator("── Ongoing Maintenance (optional, run anytime) ──")
        )
        for entry in standalone:
            choices.append(
                questionary.Choice(
                    title=[
                        ("class:text", f"{entry['label']}  "),
                        ("class:description", f"({entry['description']})"),
                    ],
                    value=entry["key"],
                )
            )

    choices.append(questionary.Separator(" "))
    choices.append(questionary.Choice(title="Back to Main Menu", value="__back__"))
    return choices


def run_bullet_bank_menu() -> None:
    # Check if we should use alternate screen / fullscreen mode
    import menu

    use_alt = menu._should_use_alt_screen()

    while True:
        if use_alt:
            sys.stdout.write("\x1b[2J\x1b[H")
            sys.stdout.flush()
            cli_art.display_compact_banner("BULLET BANK MANAGEMENT")
            cli_art.display_footer_commands()

        stage_rows = [(s["number"], s["label"], *_safe_stage_status(s)) for s in STAGES]
        maintenance_rows = [
            (m["label"], _safe_maintenance_status(m)) for m in MAINTENANCE
        ]

        cli_art.console.print()
        cli_art.render_bullet_bank_status(stage_rows, maintenance_rows)
        cli_art.console.print()

        choice = cli_art.select("Bullet Bank Management:", choices=_build_choices())

        if not choice or choice == "__back__":
            return
        _handle_choice(choice)
