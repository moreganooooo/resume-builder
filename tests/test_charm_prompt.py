import json
import os
import sys
import unittest
from unittest.mock import MagicMock, patch

SCRIPTS_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts")
sys.path.insert(0, SCRIPTS_DIR)

import charm_prompt  # noqa: E402


class TestConfirm(unittest.TestCase):

    @patch("charm_prompt._compile_prompt_if_needed", return_value=None)
    @patch("charm_prompt.subprocess.run")
    def test_true_answer_builds_correct_spec_and_command(self, mock_run, mock_compile):
        mock_run.return_value = MagicMock(returncode=0, stdout=json.dumps({"confirmed": True}), stderr="")

        result = charm_prompt.confirm("Ready?", default=True)

        self.assertTrue(result)
        args = mock_run.call_args[0][0]
        self.assertEqual(args[0], "go")
        self.assertEqual(args[1], "run")
        self.assertEqual(args[2], "./cmd/prompt")
        spec = json.loads(args[3])
        self.assertEqual(spec, {"type": "confirm", "message": "Ready?", "default": True})

    @patch("charm_prompt._compile_prompt_if_needed", return_value=None)
    @patch("charm_prompt.subprocess.run")
    def test_false_answer(self, mock_run, mock_compile):
        mock_run.return_value = MagicMock(returncode=0, stdout=json.dumps({"confirmed": False}), stderr="")
        result = charm_prompt.confirm("Ready?", default=True)
        self.assertFalse(result)

    @patch("charm_prompt._compile_prompt_if_needed", return_value=None)
    @patch("charm_prompt.subprocess.run")
    def test_cancellation_returns_none(self, mock_run, mock_compile):
        mock_run.return_value = MagicMock(returncode=130, stdout="", stderr="")
        result = charm_prompt.confirm("Ready?")
        self.assertIsNone(result)

    @patch("charm_prompt._compile_prompt_if_needed", return_value=None)
    @patch("charm_prompt.questionary.confirm")
    @patch("charm_prompt.subprocess.run")
    def test_nonzero_exit_degrades_to_questionary_instead_of_raising(self, mock_run, mock_questionary_confirm, mock_compile):
        # A real Go/huh crash (not "Go missing") used to propagate as an
        # unhandled RuntimeError straight out of every menu.py call site --
        # this now degrades to questionary instead of crashing the menu.
        mock_run.return_value = MagicMock(returncode=1, stdout="", stderr="boom")
        mock_questionary_confirm.return_value.ask.return_value = True

        result = charm_prompt.confirm("Ready?")

        self.assertTrue(result)
        mock_questionary_confirm.assert_called_once()

    @patch("charm_prompt._compile_prompt_if_needed", return_value=None)
    @patch("charm_prompt.questionary.confirm")
    @patch("charm_prompt.subprocess.run")
    def test_malformed_json_degrades_to_questionary_instead_of_raising(self, mock_run, mock_questionary_confirm, mock_compile):
        mock_run.return_value = MagicMock(returncode=0, stdout="not json", stderr="")
        mock_questionary_confirm.return_value.ask.return_value = False

        result = charm_prompt.confirm("Ready?")

        self.assertFalse(result)
        mock_questionary_confirm.assert_called_once()


class TestSelect(unittest.TestCase):

    @patch("charm_prompt._compile_prompt_if_needed", return_value=None)
    @patch("charm_prompt.subprocess.run")
    def test_returns_selected_value(self, mock_run, mock_compile):
        mock_run.return_value = MagicMock(returncode=0, stdout=json.dumps({"value": "b"}), stderr="")
        result = charm_prompt.select("Pick one", [{"label": "A", "value": "a"}, {"label": "B", "value": "b"}])
        self.assertEqual(result, "b")

    @patch("charm_prompt._compile_prompt_if_needed", return_value=None)
    @patch("charm_prompt.subprocess.run")
    def test_default_is_passed_through_as_default_value(self, mock_run, mock_compile):
        mock_run.return_value = MagicMock(returncode=0, stdout=json.dumps({"value": "b"}), stderr="")
        charm_prompt.select("Pick one", [{"label": "B", "value": "b"}], default="b")
        args = mock_run.call_args[0][0]
        spec = json.loads(args[3])
        self.assertEqual(spec["default_value"], "b")

    @patch("charm_prompt._compile_prompt_if_needed", return_value=None)
    @patch("charm_prompt.subprocess.run")
    def test_cancellation_returns_none(self, mock_run, mock_compile):
        mock_run.return_value = MagicMock(returncode=130, stdout="", stderr="")
        result = charm_prompt.select("Pick one", [{"label": "A", "value": "a"}])
        self.assertIsNone(result)


class TestCheckbox(unittest.TestCase):

    @patch("charm_prompt._compile_prompt_if_needed", return_value=None)
    @patch("charm_prompt.subprocess.run")
    def test_returns_selected_values(self, mock_run, mock_compile):
        mock_run.return_value = MagicMock(returncode=0, stdout=json.dumps({"values": ["a", "b"]}), stderr="")
        result = charm_prompt.checkbox("Pick some", [{"label": "A", "value": "a"}, {"label": "B", "value": "b"}])
        self.assertEqual(result, ["a", "b"])

    @patch("charm_prompt._compile_prompt_if_needed", return_value=None)
    @patch("charm_prompt.subprocess.run")
    def test_cancellation_returns_none(self, mock_run, mock_compile):
        mock_run.return_value = MagicMock(returncode=130, stdout="", stderr="")
        result = charm_prompt.checkbox("Pick some", [{"label": "A", "value": "a"}])
        self.assertIsNone(result)


if __name__ == "__main__":
    unittest.main()
