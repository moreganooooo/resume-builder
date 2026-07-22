"""
git_update.py — Check for and apply updates from the remote main branch.
Handles checking for unpushed local changes, fetching remote updates, and
prompting the user to update if new commits are available.
"""

import os
import subprocess


def _git_command(cmd: list[str]) -> tuple[int, str, str]:
    """Execute a git command and return (returncode, stdout, stderr)."""
    try:
        result = subprocess.run(
            ["git"] + cmd,
            cwd=os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            capture_output=True,
            text=True,
            timeout=10,
        )
        return result.returncode, result.stdout.strip(), result.stderr.strip()
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return 1, "", "git command failed or timed out"


def has_uncommitted_changes() -> bool:
    """Check if there are any uncommitted changes in the working tree."""
    returncode, stdout, _ = _git_command(["status", "--porcelain"])
    if returncode != 0:
        return False
    return bool(stdout)


def check_for_updates() -> tuple[bool, str]:
    """
    Check if there are new commits on the remote main branch.
    Returns (has_updates: bool, message: str)

    - has_updates=False if unable to check or no git repo
    - message explains the status (for logging/debugging)
    """
    # Fetch latest from remote
    returncode, _, stderr = _git_command(["fetch", "origin", "main"])
    if returncode != 0:
        return False, f"Failed to fetch: {stderr}"

    # Compare local main with remote/main
    returncode, stdout, stderr = _git_command(
        ["rev-list", "--count", "main..origin/main"]
    )
    if returncode != 0:
        return False, f"Failed to check commits: {stderr}"

    try:
        commits_behind = int(stdout)
        if commits_behind > 0:
            return True, f"{commits_behind} new commit(s) available"
        return False, "Already up to date"
    except ValueError:
        return False, "Unable to parse commit count"


def pull_updates() -> tuple[bool, str]:
    """
    Pull the latest changes from remote main branch.
    Returns (success: bool, message: str)
    """
    returncode, stdout, stderr = _git_command(["pull", "origin", "main"])
    if returncode != 0:
        return False, f"Pull failed: {stderr}"
    return True, stdout if stdout else "Successfully updated"
