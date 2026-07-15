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

import questionary

import cli_art

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(SCRIPT_DIR)
KB_DIR = os.path.join(PROJECT_ROOT, "resume-engine", "knowledge_base")

RAW_CSV = os.path.join(KB_DIR, "bullet-bank-clean.csv")
AUDITED_CSV = os.path.join(KB_DIR, "bullet-bank-audited.csv")
CLUSTER_MAP_CSV = os.path.join(KB_DIR, "bullet-bank-cluster-map.csv")
KEEPERS_CSV = os.path.join(KB_DIR, "bullet-bank-keepers.csv")
KEEPERS_AUDITED_CSV = os.path.join(KB_DIR, "bullet-bank-keepers-audited.csv")
NPY_PATH = os.path.join(KB_DIR, "bullet_vectors_ge2_d768.npy")
NEEDS_REVIEW_CSV = os.path.join(KB_DIR, "needs-review.csv")
REWRITE_QUEUE_CSV = os.path.join(KB_DIR, "rewrite-queue.csv")

# Verified directly against each script's own path constants -- see
# docs/superpowers/specs/2026-07-15-bullet-bank-management-design.md's
# Architecture section 1 table.
STAGES = [
    {
        "key": "audit", "number": 1, "label": "Audit Bullet Bank (Score Quality)",
        "script": "audit_bullet_bank.py", "inputs": [RAW_CSV], "output": AUDITED_CSV,
        "api_cost": True, "status_mode": "mtime",
    },
    {
        "key": "cluster", "number": 2, "label": "Cluster & Classify Bullets",
        "script": "cluster_bullet_bank.py", "inputs": [RAW_CSV, AUDITED_CSV], "output": CLUSTER_MAP_CSV,
        "api_cost": True, "status_mode": "mtime",
    },
    {
        "key": "rewrite", "number": 3, "label": "Rewrite Weak Bullets",
        "script": "rewrite_bullets.py", "inputs": [CLUSTER_MAP_CSV], "output": KEEPERS_CSV,
        "api_cost": True, "status_mode": "mtime",
    },
    {
        "key": "audit_keepers", "number": 4, "label": "Re-Audit Keepers",
        "script": "audit_keepers.py", "inputs": [KEEPERS_CSV], "output": KEEPERS_AUDITED_CSV,
        "api_cost": True, "status_mode": "mtime",
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
        "api_cost": True, "status_mode": "mtime",
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
    """Returns (status_label, detail). status_mode='mtime' (5 of the 6
    stages, each with a distinct input/output file) compares mtimes.
    status_mode='columns' (score_keeper_gems.py, which updates its file
    in place -- same file in and out, so an mtime comparison against
    itself is meaningless) checks column completeness instead."""
    if stage.get("status_mode") == "columns":
        return _column_completeness_status(stage["output"], stage["status_columns"])

    output = stage["output"]
    if not os.path.exists(output):
        return ("Never run", "")

    output_mtime = os.path.getmtime(output)
    for input_path in stage["inputs"]:
        if os.path.exists(input_path) and os.path.getmtime(input_path) > output_mtime:
            return ("Stale", "")

    timestamp = datetime.datetime.fromtimestamp(output_mtime).strftime("%Y-%m-%d %H:%M")
    return ("Up to date", f"as of {timestamp}")


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
