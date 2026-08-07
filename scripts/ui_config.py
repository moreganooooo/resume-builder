"""
ui_config.py -- persisted per-profile terminal-UI preferences. Today just
the Nerd Font vs. Unicode icon-set choice from the first-launch prompt
(B33): asked once in a real terminal, persisted here, never asked again.
Same small-JSON-file-per-profile pattern as maintenance.py
(profile_paths.maintenance_log_path()) -- no new tracker-file convention.
"""

import json
import os

import profile_paths
from atomic_write import atomic_write

ICON_SETS = ("nerd", "unicode")


def get_icon_set(profile: str = None) -> str | None:
    """Returns "nerd"/"unicode" if this profile has already answered the
    first-launch prompt, or None if it hasn't (or the config is missing/
    unreadable -- treated the same as "never answered")."""
    path = profile_paths.ui_config_path(profile)
    if not os.path.exists(path):
        return None
    try:
        with open(path, "r", encoding="utf-8") as f:
            config = json.load(f)
    except (json.JSONDecodeError, OSError, UnicodeDecodeError):
        return None
    value = config.get("icon_set")
    return value if value in ICON_SETS else None


def save_icon_set(icon_set: str, profile: str = None) -> None:
    """Persists the first-launch icon-set choice. Never raises -- a
    failure to persist just means the prompt asks again next launch,
    which is annoying, not broken."""
    if icon_set not in ICON_SETS:
        raise ValueError(f"icon_set must be one of {ICON_SETS}, got {icon_set!r}")
    path = profile_paths.ui_config_path(profile)
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        config = {}
        if os.path.exists(path):
            try:
                with open(path, "r", encoding="utf-8") as f:
                    config = json.load(f)
            except (json.JSONDecodeError, OSError, UnicodeDecodeError):
                config = {}
        config["icon_set"] = icon_set
        with atomic_write(path, encoding="utf-8") as f:
            json.dump(config, f, indent=2)
    except OSError:
        pass
