"""dashboard.py -- launches the career pipeline/progress dashboard
(dashboard/, a Go + Bubble Tea TUI) against the active profile's real
tracker data.

Vendored from the career-ops fork 2026-07-22 (themed to match this
project's palette/icons, plus two real pre-existing bugs fixed -- a
tracker-column-count mismatch that was silently dropping Notes/Link data,
and a crash on narrow terminal widths). This repo's copy under
dashboard/ is the authoritative one going forward; the career-ops fork's
copy is no longer where changes land -- see IDEAS_ARCHIVE.md for the full
writeup.
"""

import os
import shutil
import subprocess

import profile_paths

DASHBOARD_DIR = os.path.join(profile_paths.PROJECT_ROOT, "dashboard")


def go_available() -> bool:
    return shutil.which("go") is not None


def run(profile: str = None) -> tuple[bool, str]:
    """Launches the dashboard TUI against `profile`'s applications.md,
    full-screen and interactive -- inherits this process's stdio (unlike
    every other subprocess call in this codebase, which captures output)
    since the whole point is a live terminal UI the user actually drives.
    Returns (success, message); message is only meaningful on failure."""
    if not go_available():
        return False, (
            "Go isn't installed -- the dashboard is a separate Go/Bubble Tea "
            "TUI (dashboard/). Install it (e.g. `brew install go`) and try "
            "again."
        )

    data_dir = profile_paths.data_dir(profile)
    if not os.path.exists(os.path.join(data_dir, "applications.md")):
        return False, (
            f"No applications logged yet for this profile ({data_dir} has no "
            "applications.md) -- log at least one application status via "
            "\"Browse & Manage Jobs\" first, then the dashboard has something "
            "to show."
        )

    result = subprocess.run(["go", "run", ".", "-path", data_dir], cwd=DASHBOARD_DIR)
    if result.returncode != 0:
        return False, f"Dashboard exited with an error (code {result.returncode})."
    return True, ""
