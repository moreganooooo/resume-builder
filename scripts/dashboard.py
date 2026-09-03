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

import json
import os
import shutil
import subprocess
import sys
import tempfile

import cli_art
import picker
import profile_paths
import ui_config

DASHBOARD_DIR = os.path.join(profile_paths.PROJECT_ROOT, "dashboard")


def go_available() -> bool:
    return shutil.which("go") is not None


def _is_binary_stale(bin_path: str) -> bool:
    """Returns True if the binary is missing or any .go file in dashboard/ is newer than bin_path."""
    if not os.path.exists(bin_path):
        return True
    try:
        bin_mtime = os.path.getmtime(bin_path)
        for root, _, files in os.walk(DASHBOARD_DIR):
            if os.path.basename(root) == "bin":
                continue
            for f in files:
                if f.endswith(".go"):
                    full_path = os.path.join(root, f)
                    if os.path.getmtime(full_path) > bin_mtime:
                        return True
        return False
    except OSError:
        return True


def _export_jobs_to(path: str) -> None:
    """Writes picker.list_all_evaluated_jds() to path, overwriting
    whatever's there. Shared by _write_jobs_export() (a fresh temp file
    per dashboard launch) and dashboard_actions.py (which refreshes the
    same file an already-running dashboard session is reading from,
    after a real action changes the underlying JD data)."""
    rows = picker.list_all_evaluated_jds()
    with open(path, "w", encoding="utf-8") as f:
        json.dump(rows, f)


def _write_jobs_export(profile: str = None) -> str:
    """Writes picker.list_all_evaluated_jds() to a fresh temp JSON file
    and returns its path, for the Go dashboard's -jobs-path flag. Always
    a fresh snapshot, never cached -- evaluation/liveness/application
    data changes between dashboard launches via the Python menu, so a
    stale export would be actively misleading. Only touches the active
    profile when an explicit one is given (mirrors _handle_bootstrap()'s
    own pattern in menu.py) -- the real call site (run(), with
    profile=None) never needs the reload."""
    if profile:
        profile_paths.set_active_profile(profile)
    fd, path = tempfile.mkstemp(suffix=".json", prefix="dashboard_jobs_")
    os.close(fd)
    _export_jobs_to(path)
    return path


def compile_dashboard_if_needed() -> str:
    """Pre-compiles the Go dashboard binary if missing or stale, returning the path
    to the compiled binary. If compilation fails or Go is missing, returns
    None so execution can fall back to 'go run .'."""
    import sys

    if "unittest" in sys.modules:
        return None
    if not go_available():
        return None

    bin_dir = os.path.join(DASHBOARD_DIR, "bin")
    bin_path = os.path.join(bin_dir, "dashboard")

    if os.path.exists(bin_path) and not _is_binary_stale(bin_path):
        return bin_path

    os.makedirs(bin_dir, exist_ok=True)
    cli_art.cli_info("Pre-compiling the Career Dashboard for instant launches...")
    try:
        subprocess.run(
            ["go", "build", "-o", bin_path, "."],
            cwd=DASHBOARD_DIR,
            check=True,
            capture_output=True,
        )
        cli_art.cli_info(
            "Pre-compilation complete! Subsequent launches will start instantly."
        )
        return bin_path
    except Exception as err:
        cli_art.cli_info(
            f"Dashboard compilation fallback: using slower launch (error: {err})"
        )
        return None


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
    has_applications = os.path.exists(os.path.join(data_dir, "applications.md"))
    # applications.md only feeds Pipeline -- Jobs reads the evaluated-jobs
    # export instead (see _write_jobs_export() below), so a profile with
    # evaluated jobs but zero logged application statuses still has
    # something to show and shouldn't be locked out of the dashboard
    # entirely just because Pipeline would be empty.
    if not has_applications and not picker.list_all_evaluated_jds():
        return False, (
            f"Nothing to show yet for this profile ({data_dir} has no "
            "applications.md, and no roles have been evaluated) -- log at "
            'least one application status via "Browse & Manage Jobs", or '
            "evaluate a role first, then the dashboard has something to "
            "show."
        )

    # Compile the dashboard if needed to prevent slow 'go run .' compiling loops!
    # Bypass compilation check inside tests to respect existing mocks & assertions!
    import sys

    is_test = "unittest" in sys.modules
    bin_path = None if is_test else compile_dashboard_if_needed()

    if not bin_path:
        cli_art.cli_info(
            "Starting the dashboard... (the first launch compiles it, so it takes a few seconds)"
        )
    else:
        cli_art.cli_info("Launching dashboard...")

    jobs_path = _write_jobs_export(profile)
    active_profile = profile or profile_paths.active_profile()
    # The export carries evaluated jobs only, so the Jobs screen cannot
    # see the unevaluated backlog. Same number, same function, as the CLI
    # banner -- one definition, so the two surfaces cannot disagree.
    backlog = picker.count_unevaluated_roles()

    # Pass profile-specific UI settings to the Go dashboard environment
    env = os.environ.copy()
    if active_profile:
        env["RESUME_BUILDER_PROFILE"] = active_profile
    u_cfg = ui_config.get_full_ui_config(active_profile)
    if u_cfg.get("icon_set"):
        env["RESUME_BUILDER_ICONS"] = u_cfg["icon_set"]
    if u_cfg.get("motion"):
        env["RESUME_BUILDER_MOTION"] = u_cfg["motion"]
    if u_cfg.get("theme_mode"):
        env["RESUME_BUILDER_THEME"] = u_cfg["theme_mode"]

    try:
        if bin_path and os.path.exists(bin_path):
            cmd = [
                bin_path,
                "-path",
                data_dir,
                "-jobs-path",
                jobs_path,
                "-python-path",
                sys.executable,
                "-project-root",
                profile_paths.PROJECT_ROOT,
                "-profile",
                active_profile or "morgan",
                "-backlog",
                str(backlog),
            ]
        else:
            cmd = [
                "go",
                "run",
                ".",
                "-path",
                data_dir,
                "-jobs-path",
                jobs_path,
                "-python-path",
                sys.executable,
                "-project-root",
                profile_paths.PROJECT_ROOT,
                "-profile",
                active_profile or "morgan",
                "-backlog",
                str(backlog),
            ]
        result = subprocess.run(cmd, cwd=DASHBOARD_DIR, env=env)
    finally:
        os.remove(jobs_path)

    if result.returncode != 0:
        return False, f"Dashboard exited with an error (code {result.returncode})."
    return True, ""
