import json
import os
import subprocess
import sys
import unittest
from unittest.mock import MagicMock, patch

SCRIPTS_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts"
)
sys.path.insert(0, SCRIPTS_DIR)

import charm_prompt  # noqa: E402


class TestConfirm(unittest.TestCase):

    @patch("charm_prompt._compile_prompt_if_needed", return_value=None)
    @patch("charm_prompt.subprocess.run")
    def test_true_answer_builds_correct_spec_and_command(self, mock_run, mock_compile):
        mock_run.return_value = MagicMock(
            returncode=0, stdout=json.dumps({"confirmed": True}), stderr=""
        )

        result = charm_prompt.confirm("Ready?", default=True)

        self.assertTrue(result)
        args = mock_run.call_args[0][0]
        self.assertEqual(args[0], "go")
        self.assertEqual(args[1], "run")
        self.assertEqual(args[2], "./cmd/prompt")
        spec = json.loads(args[3])
        self.assertEqual(
            spec, {"type": "confirm", "message": "Ready?", "default": True}
        )

    @patch("charm_prompt._compile_prompt_if_needed", return_value=None)
    @patch("charm_prompt.subprocess.run")
    def test_false_answer(self, mock_run, mock_compile):
        mock_run.return_value = MagicMock(
            returncode=0, stdout=json.dumps({"confirmed": False}), stderr=""
        )
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
    def test_nonzero_exit_degrades_to_questionary_instead_of_raising(
        self, mock_run, mock_questionary_confirm, mock_compile
    ):
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
    def test_malformed_json_degrades_to_questionary_instead_of_raising(
        self, mock_run, mock_questionary_confirm, mock_compile
    ):
        mock_run.return_value = MagicMock(returncode=0, stdout="not json", stderr="")
        mock_questionary_confirm.return_value.ask.return_value = False

        result = charm_prompt.confirm("Ready?")

        self.assertFalse(result)
        mock_questionary_confirm.assert_called_once()


class TestSelect(unittest.TestCase):

    @patch("charm_prompt._compile_prompt_if_needed", return_value=None)
    @patch("charm_prompt.subprocess.run")
    def test_returns_selected_value(self, mock_run, mock_compile):
        mock_run.return_value = MagicMock(
            returncode=0, stdout=json.dumps({"value": "b"}), stderr=""
        )
        result = charm_prompt.select(
            "Pick one", [{"label": "A", "value": "a"}, {"label": "B", "value": "b"}]
        )
        self.assertEqual(result, "b")

    @patch("charm_prompt._compile_prompt_if_needed", return_value=None)
    @patch("charm_prompt.subprocess.run")
    def test_default_is_passed_through_as_default_value(self, mock_run, mock_compile):
        mock_run.return_value = MagicMock(
            returncode=0, stdout=json.dumps({"value": "b"}), stderr=""
        )
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
        mock_run.return_value = MagicMock(
            returncode=0, stdout=json.dumps({"values": ["a", "b"]}), stderr=""
        )
        result = charm_prompt.checkbox(
            "Pick some", [{"label": "A", "value": "a"}, {"label": "B", "value": "b"}]
        )
        self.assertEqual(result, ["a", "b"])

    @patch("charm_prompt._compile_prompt_if_needed", return_value=None)
    @patch("charm_prompt.subprocess.run")
    def test_cancellation_returns_none(self, mock_run, mock_compile):
        mock_run.return_value = MagicMock(returncode=130, stdout="", stderr="")
        result = charm_prompt.checkbox("Pick some", [{"label": "A", "value": "a"}])
        self.assertIsNone(result)


class TestOptionDict(unittest.TestCase):
    def test_dict_input(self):
        res = charm_prompt._option_dict({"label": "L", "value": "V"})
        self.assertEqual(res, {"label": "L", "value": "V"})

    def test_choice_with_string_title(self):
        choice = MagicMock()
        choice.title = "Option A"
        choice.value = "opt_a"
        res = charm_prompt._option_dict(choice)
        self.assertEqual(res, {"label": "Option A", "value": "opt_a"})

    def test_choice_with_styled_list_title(self):
        choice = MagicMock()
        choice.title = [("class:bold", "Styled "), ("", "Option")]
        choice.value = "opt_styled"
        res = charm_prompt._option_dict(choice)
        self.assertEqual(res, {"label": "Styled Option", "value": "opt_styled"})

    def test_plain_scalar_input(self):
        res = charm_prompt._option_dict("simple_string")
        self.assertEqual(res, {"label": "simple_string", "value": "simple_string"})


class TestCompilationAndGoAvailable(unittest.TestCase):
    @patch("charm_prompt._go_available", return_value=False)
    def test_compile_when_no_go(self, mock_go):
        self.assertIsNone(charm_prompt._compile_prompt_if_needed())

    @patch("charm_prompt._go_available", return_value=True)
    @patch("os.path.exists", return_value=True)
    def test_compile_when_bin_exists(self, mock_exists, mock_go):
        self.assertEqual(
            charm_prompt._compile_prompt_if_needed(), charm_prompt._BIN_PATH
        )

    @patch("charm_prompt._go_available", return_value=True)
    @patch("os.path.exists", return_value=False)
    @patch("os.makedirs")
    @patch("subprocess.run")
    def test_compile_build_success(self, mock_run, mock_makedirs, mock_exists, mock_go):
        res = charm_prompt._compile_prompt_if_needed()
        self.assertEqual(res, charm_prompt._BIN_PATH)
        mock_run.assert_called_once()

    @patch("charm_prompt._go_available", return_value=True)
    @patch("os.path.exists", return_value=False)
    @patch("os.makedirs")
    @patch("subprocess.run", side_effect=subprocess.CalledProcessError(1, "cmd"))
    def test_compile_build_failure(self, mock_run, mock_makedirs, mock_exists, mock_go):
        self.assertIsNone(charm_prompt._compile_prompt_if_needed())


class TestFallbackWhenGoNotAvailable(unittest.TestCase):
    @patch("charm_prompt._go_available", return_value=False)
    @patch("charm_prompt.questionary.confirm")
    def test_confirm_fallback(self, mock_q, mock_go):
        mock_q.return_value.ask.return_value = True
        self.assertTrue(charm_prompt.confirm("Fallback?"))

    @patch("charm_prompt._go_available", return_value=False)
    @patch("charm_prompt.questionary.select")
    def test_select_fallback(self, mock_q, mock_go):
        mock_q.return_value.ask.return_value = "opt1"
        self.assertEqual(charm_prompt.select("Fallback?", ["opt1"]), "opt1")

    @patch("charm_prompt._go_available", return_value=False)
    @patch("charm_prompt.questionary.checkbox")
    def test_checkbox_fallback(self, mock_q, mock_go):
        mock_q.return_value.ask.return_value = ["opt1"]
        self.assertEqual(charm_prompt.checkbox("Fallback?", ["opt1"]), ["opt1"])


class TestDegradationOnRuntimeError(unittest.TestCase):
    @patch("charm_prompt._go_available", return_value=True)
    @patch("charm_prompt._run_prompt", side_effect=RuntimeError("crashed"))
    @patch("charm_prompt.questionary.select")
    def test_select_degrade(self, mock_q, mock_run, mock_go):
        mock_q.return_value.ask.return_value = "fallback_val"
        res = charm_prompt.select("Choice?", ["A", "B"])
        self.assertEqual(res, "fallback_val")

    @patch("charm_prompt._go_available", return_value=True)
    @patch("charm_prompt._run_prompt", side_effect=RuntimeError("crashed"))
    @patch("charm_prompt.questionary.checkbox")
    def test_checkbox_degrade(self, mock_q, mock_run, mock_go):
        mock_q.return_value.ask.return_value = ["fallback_box"]
        res = charm_prompt.checkbox("Boxes?", ["A", "B"])
        self.assertEqual(res, ["fallback_box"])


class TestRunPromptDirectly(unittest.TestCase):
    @patch("charm_prompt._compile_prompt_if_needed", return_value="/custom/bin/prompt")
    @patch("os.path.exists", return_value=True)
    @patch("subprocess.run")
    def test_run_with_existing_bin(self, mock_run, mock_exists, mock_compile):
        mock_run.return_value = MagicMock(returncode=0, stdout='{"ok": true}')
        res = charm_prompt._run_prompt({"test": 1})
        self.assertEqual(res, {"ok": True})
        self.assertEqual(mock_run.call_args[0][0][0], "/custom/bin/prompt")


if __name__ == "__main__":
    unittest.main()
