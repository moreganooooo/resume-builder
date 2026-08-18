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
MOTION_PREFERENCES = ("full", "reduced")
DEFAULT_VIEWS = ("pipeline", "jobs", "progress")
THEME_MODES = ("resume-builder", "catppuccin-mocha", "catppuccin-latte")


def get_full_ui_config(profile: str = None) -> dict:
    """Returns the parsed ui_config.json dictionary or an empty dict if missing/invalid."""
    path = profile_paths.ui_config_path(profile)
    if not os.path.exists(path):
        return {}
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
            return data if isinstance(data, dict) else {}
    except (json.JSONDecodeError, OSError, UnicodeDecodeError):
        return {}


def get_icon_set(profile: str = None) -> str | None:
    """Returns "nerd"/"unicode" if this profile has already answered the
    first-launch prompt, or None if it hasn't (or the config is missing/
    unreadable -- treated the same as "never answered")."""
    config = get_full_ui_config(profile)
    value = config.get("icon_set")
    return value if value in ICON_SETS else None


def get_motion_preference(profile: str = None) -> str:
    """Returns 'full' or 'reduced' (defaulting to 'full' or RESUME_BUILDER_MOTION env)."""
    env_motion = os.environ.get("RESUME_BUILDER_MOTION", "").lower()
    if env_motion in MOTION_PREFERENCES:
        return env_motion
    config = get_full_ui_config(profile)
    val = config.get("motion")
    return val if val in MOTION_PREFERENCES else "full"


def get_celebrations_enabled(profile: str = None) -> bool:
    """Returns True if particle/confetti celebrations are enabled."""
    if get_motion_preference(profile) == "reduced":
        return False
    config = get_full_ui_config(profile)
    return config.get("celebrations_enabled", True)


def get_default_view(profile: str = None) -> str:
    """Returns the default landing view ('pipeline', 'jobs', 'progress')."""
    config = get_full_ui_config(profile)
    val = config.get("default_view")
    return val if val in DEFAULT_VIEWS else "pipeline"


def get_theme_mode(profile: str = None) -> str:
    """Returns the theme mode name."""
    config = get_full_ui_config(profile)
    val = config.get("theme_mode")
    return val if val in THEME_MODES else "resume-builder"


def save_ui_preference(key: str, value, profile: str = None) -> None:
    """Saves an individual UI preference to ui_config.json atomically."""
    path = profile_paths.ui_config_path(profile)
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        config = get_full_ui_config(profile)
        config[key] = value
        with atomic_write(path, encoding="utf-8") as f:
            json.dump(config, f, indent=2)
    except OSError:
        pass


def save_icon_set(icon_set: str, profile: str = None) -> None:
    """Persists the first-launch icon-set choice. Never raises -- a
    failure to persist just means the prompt asks again next launch,
    which is annoying, not broken."""
    if icon_set not in ICON_SETS:
        raise ValueError(f"icon_set must be one of {ICON_SETS}, got {icon_set!r}")
    save_ui_preference("icon_set", icon_set, profile=profile)
