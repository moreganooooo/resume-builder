import os
import subprocess
import sys
import unittest
from unittest.mock import MagicMock, patch

SCRIPTS_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts")
sys.path.insert(0, SCRIPTS_DIR)

import git_update  # noqa: E402

_EXPECTED_CWD = os.path.dirname(os.path.dirname(os.path.abspath(git_update.__file__)))


class TestGitCommand(unittest.TestCase):

    @patch("git_update.subprocess.run")
    def test_prefixes_cmd_with_git_and_sets_expected_kwargs(self, mock_run):
        mock_run.return_value = MagicMock(returncode=0, stdout=" clean \n", stderr="")
        returncode, stdout, stderr = git_update._git_command(["status", "--porcelain"])

        mock_run.assert_called_once_with(
            ["git", "status", "--porcelain"],
            cwd=_EXPECTED_CWD,
            capture_output=True,
            text=True,
            timeout=10,
        )
        self.assertEqual(returncode, 0)
        self.assertEqual(stdout, "clean")
        self.assertEqual(stderr, "")

    @patch("git_update.subprocess.run", side_effect=subprocess.TimeoutExpired(cmd="git", timeout=10))
    def test_returns_failure_tuple_on_timeout(self, mock_run):
        returncode, stdout, stderr = git_update._git_command(["fetch"])
        self.assertEqual(returncode, 1)
        self.assertEqual(stdout, "")
        self.assertIn("timed out", stderr)

    @patch("git_update.subprocess.run", side_effect=FileNotFoundError)
    def test_returns_failure_tuple_when_git_binary_missing(self, mock_run):
        returncode, stdout, stderr = git_update._git_command(["fetch"])
        self.assertEqual(returncode, 1)
        self.assertEqual(stdout, "")
        self.assertIn("failed", stderr)


class TestHasUncommittedChanges(unittest.TestCase):

    @patch("git_update._git_command", return_value=(0, "", ""))
    def test_false_on_clean_tree(self, mock_cmd):
        self.assertFalse(git_update.has_uncommitted_changes())
        mock_cmd.assert_called_once_with(["status", "--porcelain"])

    @patch("git_update._git_command", return_value=(0, " M scripts/menu.py", ""))
    def test_true_when_status_reports_changes(self, mock_cmd):
        self.assertTrue(git_update.has_uncommitted_changes())

    @patch("git_update._git_command", return_value=(1, "", "not a git repository"))
    def test_false_when_git_command_itself_fails(self, mock_cmd):
        # Deliberately fails closed: a broken git invocation should never
        # be reported as "no changes" and skip the safety check upstream.
        self.assertFalse(git_update.has_uncommitted_changes())


class TestCheckForUpdates(unittest.TestCase):

    @patch("git_update._git_command")
    def test_reports_updates_available(self, mock_cmd):
        mock_cmd.side_effect = [(0, "", ""), (0, "3", "")]
        has_updates, message = git_update.check_for_updates()
        self.assertTrue(has_updates)
        self.assertEqual(message, "3 new commit(s) available")

    @patch("git_update._git_command")
    def test_reports_already_up_to_date(self, mock_cmd):
        mock_cmd.side_effect = [(0, "", ""), (0, "0", "")]
        has_updates, message = git_update.check_for_updates()
        self.assertFalse(has_updates)
        self.assertEqual(message, "Already up to date")

    @patch("git_update._git_command")
    def test_fetch_failure_short_circuits_before_rev_list(self, mock_cmd):
        mock_cmd.return_value = (1, "", "could not resolve host")
        has_updates, message = git_update.check_for_updates()
        self.assertFalse(has_updates)
        self.assertIn("Failed to fetch", message)
        mock_cmd.assert_called_once()

    @patch("git_update._git_command")
    def test_rev_list_failure_is_reported(self, mock_cmd):
        mock_cmd.side_effect = [(0, "", ""), (1, "", "unknown revision")]
        has_updates, message = git_update.check_for_updates()
        self.assertFalse(has_updates)
        self.assertIn("Failed to check commits", message)

    @patch("git_update._git_command")
    def test_unparseable_commit_count_is_reported(self, mock_cmd):
        mock_cmd.side_effect = [(0, "", ""), (0, "not-a-number", "")]
        has_updates, message = git_update.check_for_updates()
        self.assertFalse(has_updates)
        self.assertEqual(message, "Unable to parse commit count")

    @patch("git_update._git_command")
    def test_fetches_and_diffs_against_origin_main(self, mock_cmd):
        mock_cmd.side_effect = [(0, "", ""), (0, "1", "")]
        git_update.check_for_updates()
        mock_cmd.assert_any_call(["fetch", "origin", "main"])
        mock_cmd.assert_any_call(["rev-list", "--count", "main..origin/main"])


class TestPullUpdates(unittest.TestCase):

    @patch("git_update._git_command", return_value=(0, "Already up to date.", ""))
    def test_success_returns_stdout(self, mock_cmd):
        success, message = git_update.pull_updates()
        self.assertTrue(success)
        self.assertEqual(message, "Already up to date.")
        mock_cmd.assert_called_once_with(["pull", "origin", "main"])

    @patch("git_update._git_command", return_value=(0, "", ""))
    def test_success_with_empty_stdout_uses_fallback_message(self, mock_cmd):
        success, message = git_update.pull_updates()
        self.assertTrue(success)
        self.assertEqual(message, "Successfully updated")

    @patch("git_update._git_command", return_value=(1, "", "conflict, aborting"))
    def test_failure_reports_stderr(self, mock_cmd):
        success, message = git_update.pull_updates()
        self.assertFalse(success)
        self.assertIn("Pull failed", message)
        self.assertIn("conflict, aborting", message)


if __name__ == "__main__":
    unittest.main()
