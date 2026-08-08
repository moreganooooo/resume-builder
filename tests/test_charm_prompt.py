import json
import os
import sys
import unittest
from unittest.mock import patch, MagicMock

SCRIPTS_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts")
sys.path.insert(0, SCRIPTS_DIR)

import charm_prompt  # noqa: E402


class TestConfirm(unittest.TestCase):

    @patch("charm_prompt.subprocess.run")
    def test_true_answer_builds_correct_spec_and_command(self, mock_run):
        mock_run.return_value = MagicMock(returncode=0, stdout=json.dumps({"confirmed": True}), stderr="")

        result = charm_prompt.confirm("Ready?", default=True)

        self.assertTrue(result)
        args = mock_run.call_args[0][0]
        self.assertEqual(args[0], "go")
        self.assertEqual(args[1], "run")
        self.assertEqual(args[2], "./dashboard/cmd/prompt")
        spec = json.loads(args[3])
        self.assertEqual(spec, {"type": "confirm", "message": "Ready?", "default": True})

    @patch("charm_prompt.subprocess.run")
    def test_false_answer(self, mock_run):
        mock_run.return_value = MagicMock(returncode=0, stdout=json.dumps({"confirmed": False}), stderr="")
        result = charm_prompt.confirm("Ready?", default=True)
        self.assertFalse(result)

    @patch("charm_prompt.subprocess.run")
    def test_cancellation_returns_none(self, mock_run):
        mock_run.return_value = MagicMock(returncode=130, stdout="", stderr="")
        result = charm_prompt.confirm("Ready?")
        self.assertIsNone(result)

    @patch("charm_prompt.subprocess.run")
    def test_nonzero_exit_raises_with_stderr(self, mock_run):
        mock_run.return_value = MagicMock(returncode=1, stdout="", stderr="boom")
        with self.assertRaises(RuntimeError) as ctx:
            charm_prompt.confirm("Ready?")
        self.assertIn("boom", str(ctx.exception))

    @patch("charm_prompt.subprocess.run")
    def test_malformed_json_raises(self, mock_run):
        mock_run.return_value = MagicMock(returncode=0, stdout="not json", stderr="")
        with self.assertRaises(RuntimeError):
            charm_prompt.confirm("Ready?")


class TestSelect(unittest.TestCase):

    @patch("charm_prompt.subprocess.run")
    def test_returns_selected_value(self, mock_run):
        mock_run.return_value = MagicMock(returncode=0, stdout=json.dumps({"value": "b"}), stderr="")
        result = charm_prompt.select("Pick one", [{"label": "A", "value": "a"}, {"label": "B", "value": "b"}])
        self.assertEqual(result, "b")

    @patch("charm_prompt.subprocess.run")
    def test_default_is_passed_through_as_default_value(self, mock_run):
        mock_run.return_value = MagicMock(returncode=0, stdout=json.dumps({"value": "b"}), stderr="")
        charm_prompt.select("Pick one", [{"label": "B", "value": "b"}], default="b")
        args = mock_run.call_args[0][0]
        spec = json.loads(args[3])
        self.assertEqual(spec["default_value"], "b")

    @patch("charm_prompt.subprocess.run")
    def test_cancellation_returns_none(self, mock_run):
        mock_run.return_value = MagicMock(returncode=130, stdout="", stderr="")
        result = charm_prompt.select("Pick one", [{"label": "A", "value": "a"}])
        self.assertIsNone(result)


class TestCheckbox(unittest.TestCase):

    @patch("charm_prompt.subprocess.run")
    def test_returns_selected_values(self, mock_run):
        mock_run.return_value = MagicMock(returncode=0, stdout=json.dumps({"values": ["a", "b"]}), stderr="")
        result = charm_prompt.checkbox("Pick some", [{"label": "A", "value": "a"}, {"label": "B", "value": "b"}])
        self.assertEqual(result, ["a", "b"])

    @patch("charm_prompt.subprocess.run")
    def test_cancellation_returns_none(self, mock_run):
        mock_run.return_value = MagicMock(returncode=130, stdout="", stderr="")
        result = charm_prompt.checkbox("Pick some", [{"label": "A", "value": "a"}])
        self.assertIsNone(result)


if __name__ == "__main__":
    unittest.main()
