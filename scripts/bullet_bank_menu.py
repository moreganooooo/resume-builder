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
    in place -- see Task 3) is handled separately."""
    output = stage["output"]
    if not os.path.exists(output):
        return ("Never run", "")

    output_mtime = os.path.getmtime(output)
    for input_path in stage["inputs"]:
        if os.path.exists(input_path) and os.path.getmtime(input_path) > output_mtime:
            return ("Stale", "")

    timestamp = datetime.datetime.fromtimestamp(output_mtime).strftime("%Y-%m-%d %H:%M")
    return ("Up to date", f"as of {timestamp}")
