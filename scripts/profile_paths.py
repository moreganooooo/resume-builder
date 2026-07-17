"""profile_paths.py — the single source of truth for "which profile is
active" and every filesystem path derived from it. Every script that used
to hand-roll its own PROJECT_ROOT/resume-engine/knowledge_base (or
PROJECT_ROOT/jds, PROJECT_ROOT/output, PROJECT_ROOT/data) path routes
through here instead, so profiles/<name>/ becomes the one place a
profile's personalization data lives, and jds/<name>/, output/<name>/,
data/<name>/ become the one place a profile's operational data lives --
with zero risk of two profiles colliding in the same checkout.

RESUME_PROFILE unset defaults to "morgan" (backward compatible with every
existing workflow). RESUME_PROFILE set to a name with no matching
profiles/<name>/ directory is a hard failure, not a silent fallback --
silently reading the wrong profile's data on a typo is exactly the bug
this module exists to prevent.
"""

import importlib.util
import os

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(SCRIPT_DIR)
PROFILES_DIR = os.path.join(PROJECT_ROOT, "profiles")


def active_profile() -> str:
    name = os.environ.get("RESUME_PROFILE")
    if name is None:
        return "morgan"
    if not os.path.isdir(os.path.join(PROFILES_DIR, name)):
        raise ValueError(
            f"RESUME_PROFILE is set to {name!r}, but profiles/{name}/ does not exist. "
            "Check for a typo, or create it via the bootstrap 'New Profile' flow."
        )
    return name


# Modules that compute profile-scoped paths as module-level constants
# (resolved once at import time, per this project's existing SCRIPT_DIR/
# PROJECT_ROOT convention) rather than through this module's functions.
# cli.py and menu.py both import these -- and everything that in turn
# imports them (picker.py, scan.py, batch_evaluate.py, liveness.py all
# reference jd_manager.<CONSTANT> via attribute access, never `from
# jd_manager import X`) -- at their own top level, before any --profile
# flag or interactive gate can run. Switching RESUME_PROFILE mid-process
# without reloading these leaves them silently pointed at whichever
# profile was active when the long-running menu/CLI process first
# started, defeating the entire point of runtime profile-switching.
_RELOAD_ON_PROFILE_SWITCH = ("jd_manager", "polish")


def set_active_profile(name: str) -> None:
    """Sets RESUME_PROFILE and reloads every already-imported module whose
    profile-scoped path constants were resolved at their own import time
    -- use this instead of assigning os.environ["RESUME_PROFILE"] directly
    anywhere a profile switch needs to actually take effect for the rest
    of a running process (the interactive menu gate, the CLI --profile
    flag, bootstrap creating and switching to a new profile)."""
    import importlib
    import sys

    os.environ["RESUME_PROFILE"] = name
    for module_name in _RELOAD_ON_PROFILE_SWITCH:
        if module_name in sys.modules:
            importlib.reload(sys.modules[module_name])


def profile_root(profile: str = None) -> str:
    return os.path.join(PROFILES_DIR, profile or active_profile())


def kb_dir(profile: str = None) -> str:
    return os.path.join(profile_root(profile), "knowledge_base")


def situational_roles_path(profile: str = None) -> str:
    return os.path.join(profile_root(profile), "situational_roles.yaml")


def fixed_content_module(profile: str = None):
    """Dynamically imports profiles/<profile>/fixed_content.py and returns
    the loaded module object -- the per-profile replacement for a static
    `import fixed_content`."""
    name = profile or active_profile()
    path = os.path.join(profile_root(name), "fixed_content.py")
    if not os.path.exists(path):
        raise ImportError(
            f"profiles/{name}/fixed_content.py not found -- has this profile been bootstrapped?"
        )
    spec = importlib.util.spec_from_file_location(f"fixed_content_{name}", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def jds_dir(profile: str = None) -> str:
    return os.path.join(PROJECT_ROOT, "jds", profile or active_profile())


def output_dir(profile: str = None) -> str:
    return os.path.join(PROJECT_ROOT, "output", profile or active_profile())


def checkpoints_dir(profile: str = None) -> str:
    return os.path.join(output_dir(profile), "checkpoints")


def applications_md_path(profile: str = None) -> str:
    return os.path.join(PROJECT_ROOT, "data", profile or active_profile(), "applications.md")


def tracker_csv_path(profile: str = None) -> str:
    return os.path.join(jds_dir(profile), "jd_tracker_log.csv")
