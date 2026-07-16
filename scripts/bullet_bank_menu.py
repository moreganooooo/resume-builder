"""bullet_bank_menu.py -- the "Manage Bullet Bank" submenu: shows
staleness/last-run status for the 6 rebuild-pipeline stages
(audit_bullet_bank.py -> cluster_bullet_bank.py -> rewrite_bullets.py ->
audit_keepers.py -> score_keeper_gems.py -> embed_bullet_bank.py) plus the
2 needs-review/rewrite-queue maintenance scripts, and runs any one of them
individually as a subprocess -- unmodified, exactly as
bootstrap_bullet_bank.py's own run_stage() does. See
docs/superpowers/specs/2026-07-15-bullet-bank-management-design.md.
"""

import csv
import datetime
import os
import subprocess
import sys

import numpy as np
import pandas as pd
import questionary

import cli_art

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(SCRIPT_DIR)
KB_DIR = os.path.join(PROJECT_ROOT, "resume-engine", "knowledge_base")

RAW_CSV = os.path.join(KB_DIR, "bullet-bank-clean.csv")
AUDITED_CSV = os.path.join(KB_DIR, "bullet-bank-audited.csv")
CLUSTER_MAP_CSV = os.path.join(KB_DIR, "bullet-bank-cluster-map.csv")
CLUSTER_MAP_OUT_CSV = os.path.join(KB_DIR, "bullet-bank-cluster-map-updated.csv")
KEEPERS_CSV = os.path.join(KB_DIR, "bullet-bank-keepers.csv")
KEEPERS_AUDITED_CSV = os.path.join(KB_DIR, "bullet-bank-keepers-audited.csv")
NPY_PATH = os.path.join(KB_DIR, "bullet_vectors_ge2_d768.npy")
NEEDS_REVIEW_CSV = os.path.join(KB_DIR, "needs-review.csv")
REWRITE_QUEUE_CSV = os.path.join(KB_DIR, "rewrite-queue.csv")
CLUSTER_CHECKPOINT_PATH = os.path.join(KB_DIR, "bullet_vectors_ge2_d768_cluster.checkpoint.npz")
EMBED_CHECKPOINT_PATH = os.path.join(KB_DIR, "bullet_vectors_ge2_d768.checkpoint.npz")

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
        total = sum(1 for _ in csv.DictReader(f))
    done = 0
    if os.path.exists(AUDITED_CSV):
        # audit_bullet_bank.py flushes to disk after every row and its
        # output only ever contains rows actually scored so far -- unlike
        # the other stages, row count IS the progress signal here.
        with open(AUDITED_CSV, newline="", encoding="utf-8") as f:
            done = sum(1 for _ in csv.DictReader(f))
    return (done, total)


def _rewrite_progress():
    if not os.path.exists(CLUSTER_MAP_CSV):
        return None
    df = pd.read_csv(CLUSTER_MAP_CSV)
    mask_rep = df["is_representative"].astype(str).str.strip().str.lower().isin(["true", "1", "yes"])
    mask_action = df["next_action"].astype(str).str.strip().str.upper().isin(["REWRITE", "REVIEW"])
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
            done_mask = df_out["rewrite_status"].astype(str).str.strip().str.upper().isin(REWRITE_DONE_STATUSES)
            done_bullets |= set(df_out.loc[done_mask, "Bullet Point"].dropna().str.strip())
            if "final_bullet" in df_out.columns:
                done_bullets |= set(df_out.loc[done_mask, "final_bullet"].dropna().str.strip())
    if os.path.exists(KEEPERS_CSV):
        df_k = pd.read_csv(KEEPERS_CSV)
        if "Bullet Point" in df_k.columns:
            done_bullets |= set(df_k["Bullet Point"].dropna().str.strip())

    done = int(target["Bullet Point"].astype(str).str.strip().isin(done_bullets).sum())
    return (done, total)


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


def _embed_progress():
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
        "key": "audit", "number": 1, "label": "Audit Bullet Bank (Score Quality)",
        "script": "audit_bullet_bank.py", "inputs": [RAW_CSV], "output": AUDITED_CSV,
        "api_cost": True, "status_mode": "progress", "progress_fn": _audit_progress,
    },
    {
        "key": "cluster", "number": 2, "label": "Cluster & Classify Bullets",
        "script": "cluster_bullet_bank.py", "inputs": [RAW_CSV, AUDITED_CSV], "output": CLUSTER_MAP_CSV,
        "api_cost": True, "status_mode": "mtime", "checkpoint": CLUSTER_CHECKPOINT_PATH,
    },
    {
        "key": "rewrite", "number": 3, "label": "Rewrite Weak Bullets",
        "script": "rewrite_bullets.py", "inputs": [CLUSTER_MAP_CSV], "output": KEEPERS_CSV,
        "api_cost": True, "status_mode": "progress", "progress_fn": _rewrite_progress,
    },
    {
        "key": "audit_keepers", "number": 4, "label": "Re-Audit Keepers",
        "script": "audit_keepers.py", "inputs": [KEEPERS_CSV], "output": KEEPERS_AUDITED_CSV,
        "api_cost": True, "status_mode": "progress", "progress_fn": _audit_keepers_progress,
    },
    {
        "key": "score_gems", "number": 5, "label": "Score Hidden Gems",
        "script": "score_keeper_gems.py", "inputs": [KEEPERS_AUDITED_CSV], "output": KEEPERS_AUDITED_CSV,
        "api_cost": True, "status_mode": "columns",
        "status_columns": ["hidden_gem_score", "hidden_gem_flag"],
    },
    {
        "key": "embed", "number": 6, "label": "Embed Bullet Bank (Final Step)",
        "script": "embed_bullet_bank.py", "inputs": [KEEPERS_AUDITED_CSV], "output": NPY_PATH,
        "api_cost": True, "status_mode": "progress", "progress_fn": _embed_progress,
    },
]

MAINTENANCE = [
    {
        "key": "triage", "label": "Triage Needs-Review Queue",
        "script": "triage_needs_review.py", "watched_file": NEEDS_REVIEW_CSV, "api_cost": False,
    },
    {
        "key": "retire", "label": "Retire Abandoned Rewrite-Queue Bullets",
        "script": "retire_rewrite_queue.py", "watched_file": REWRITE_QUEUE_CSV, "api_cost": False,
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
                return ("In progress", f"{done}/{total} processed ({total - done} pending)")

    output = stage["output"]
    if not os.path.exists(output):
        checkpoint = stage.get("checkpoint")
        if checkpoint and os.path.exists(checkpoint):
            return _checkpoint_progress_status(checkpoint)
        return ("Never run", "")

    output_mtime = os.path.getmtime(output)
    for input_path in stage["inputs"]:
        if os.path.exists(input_path) and os.path.getmtime(input_path) > output_mtime:
            return ("Stale", "")

    timestamp = datetime.datetime.fromtimestamp(output_mtime).strftime("%Y-%m-%d %H:%M")
    return ("Up to date", f"as of {timestamp}")


def _checkpoint_progress_status(checkpoint_path: str) -> tuple:
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

    if entry["key"] == "retire":
        if not os.path.exists(path):
            return "none pending"
        with open(path, newline="", encoding="utf-8") as f:
            rows = list(csv.DictReader(f))
        pending = sum(1 for row in rows if (row.get("is_representative") or "").strip().lower() == "false")
        return "none pending" if pending == 0 else f"{pending} bullet(s) pending retirement"

    return ""


def _confirm(label: str) -> bool:
    return bool(questionary.confirm(
        f'Ready to run "{label}"? This calls the Gemini API and may take a while.',
        default=True, style=cli_art.QUESTIONARY_STYLE,
    ).ask())


def _handle_choice(choice: str) -> None:
    entry = _ALL_ENTRIES[choice]
    if entry.get("api_cost") and not _confirm(entry["label"]):
        return
    script_path = os.path.join(SCRIPT_DIR, entry["script"])
    result = subprocess.run([sys.executable, script_path])
    if result.returncode != 0:
        cli_art.display_error(f"{entry['script']} exited with an error -- check the output above.")


def _build_choices() -> list:
    choices = [
        questionary.Choice(title=f"{stage['number']}. {stage['label']}", value=stage["key"])
        for stage in STAGES
    ]
    choices.append(questionary.Separator())
    choices += [questionary.Choice(title=entry["label"], value=entry["key"]) for entry in MAINTENANCE]
    choices.append(questionary.Choice(title="Back to Main Menu", value="__back__"))
    return choices


def run_bullet_bank_menu() -> None:
    while True:
        stage_rows = [(s["number"], s["label"], *_stage_status(s)) for s in STAGES]
        maintenance_rows = [(m["label"], _maintenance_status(m)) for m in MAINTENANCE]
        cli_art.render_bullet_bank_status(stage_rows, maintenance_rows)

        choice = questionary.select(
            "Bullet Bank Management:", choices=_build_choices(), style=cli_art.QUESTIONARY_STYLE,
        ).ask()

        if not choice or choice == "__back__":
            return
        _handle_choice(choice)
