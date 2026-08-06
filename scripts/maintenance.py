"""
maintenance.py — "when did this background/administrative task last run"
tracking for the Maintenance submenu (doctor script now, whatever else
gets added later). One small persisted JSON file per profile
(profile_paths.maintenance_log_path()), keyed by task name -- no new
tracker-file convention, matches the pattern this project already uses
everywhere else (checkpoint.json, jd_tracker_log.csv, etc.).
"""

import datetime
import json
import os

import profile_paths
from atomic_write import atomic_write


def record_run(task_name: str) -> None:
    """Stamps task_name with the current time. Never raises -- a failure
    to persist "last run" is not worth blocking on."""
    path = profile_paths.maintenance_log_path()
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        log = {}
        if os.path.exists(path):
            try:
                with open(path, "r", encoding="utf-8") as f:
                    log = json.load(f)
            except (json.JSONDecodeError, OSError, UnicodeDecodeError):
                log = {}
        log[task_name] = datetime.datetime.now().isoformat(timespec="seconds")
        with atomic_write(path, encoding="utf-8") as f:
            json.dump(log, f, indent=2)
    except OSError:
        pass


def get_last_run(task_name: str) -> str | None:
    """Returns the ISO timestamp task_name last ran, or None if it's
    never been recorded."""
    path = profile_paths.maintenance_log_path()
    if not os.path.exists(path):
        return None
    try:
        with open(path, "r", encoding="utf-8") as f:
            log = json.load(f)
    except (json.JSONDecodeError, OSError, UnicodeDecodeError):
        return None
    return log.get(task_name)
