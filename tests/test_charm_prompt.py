import json
import os
import shutil
import subprocess
import sys
import unittest
from unittest.mock import MagicMock, patch

SCRIPTS_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts"
)
sys.path.insert(0, SCRIPTS_DIR)

import charm_prompt  # noqa: E402
import questionary  # noqa: E402


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

    @patch("charm_prompt._compile_prompt_if_needed", return_value=None)
    @patch("charm_prompt.subprocess.run")
    def test_separators_are_excluded_from_the_options_sent_to_the_binary(
        self, mock_run, mock_compile
    ):
        # Regression: a questionary.Separator has real .title/.value
        # attributes (it subclasses Choice), so _option_dict() happily
        # serialized it as {"label": "", "value": " "} -- the Go binary
        # then rendered it as a real, blank-looking selectable row. A
        # user who arrowed onto it and hit Enter got " " back as their
        # choice; menu.py's `if not choice` guard let it through (a
        # single space is truthy), and `_HANDLERS[" "]` raised a raw
        # KeyError with nothing onscreen explaining why the menu had
        # just gone dead. See menu.py's _run_leaf_submenu/_run_with_chain.
        mock_run.return_value = MagicMock(
            returncode=0, stdout=json.dumps({"value": "a"}), stderr=""
        )
        charm_prompt.select(
            "Pick one",
            [
                questionary.Choice(title="A", value="a"),
                questionary.Separator(" "),
                questionary.Choice(title="B", value="b"),
            ],
        )
        args = mock_run.call_args[0][0]
        spec = json.loads(args[3])
        values = [opt["value"] for opt in spec["options"]]
        self.assertEqual(values, ["a", "b"])


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


class TestText(unittest.TestCase):

    @patch("charm_prompt._compile_prompt_if_needed", return_value=None)
    @patch("charm_prompt.subprocess.run")
    def test_returns_entered_value(self, mock_run, mock_compile):
        mock_run.return_value = MagicMock(
            returncode=0, stdout=json.dumps({"value": "45"}), stderr=""
        )
        result = charm_prompt.text(
            "Archive postings older than how many days?", default="30"
        )
        self.assertEqual(result, "45")
        args = mock_run.call_args[0][0]
        spec = json.loads(args[3])
        self.assertEqual(
            spec,
            {
                "type": "text",
                "message": "Archive postings older than how many days?",
                "default_value": "30",
            },
        )

    @patch("charm_prompt._compile_prompt_if_needed", return_value=None)
    @patch("charm_prompt.subprocess.run")
    def test_cancellation_returns_none(self, mock_run, mock_compile):
        mock_run.return_value = MagicMock(returncode=130, stdout="", stderr="")
        result = charm_prompt.text("Enter something:")
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


class TestIsSelectable(unittest.TestCase):
    def test_separator_is_not_selectable(self):
        self.assertFalse(charm_prompt._is_selectable(questionary.Separator(" ")))

    def test_normal_choice_is_selectable(self):
        self.assertTrue(
            charm_prompt._is_selectable(questionary.Choice(title="A", value="a"))
        )

    def test_explicitly_disabled_choice_is_not_selectable(self):
        choice = questionary.Choice(title="A", value="a", disabled="not available")
        self.assertFalse(charm_prompt._is_selectable(choice))

    def test_plain_dict_and_scalar_choices_are_selectable(self):
        self.assertTrue(charm_prompt._is_selectable({"label": "L", "value": "V"}))
        self.assertTrue(charm_prompt._is_selectable("simple_string"))


class TestCompilationAndGoAvailable(unittest.TestCase):
    @patch("charm_prompt._go_available", return_value=False)
    def test_compile_when_no_go(self, mock_go):
        self.assertIsNone(charm_prompt._compile_prompt_if_needed())

    @patch("charm_prompt._go_available", return_value=True)
    @patch("charm_prompt._prompt_binary_is_stale", return_value=False)
    @patch("os.path.exists", return_value=True)
    def test_compile_when_bin_exists_and_fresh(self, mock_exists, mock_stale, mock_go):
        self.assertEqual(
            charm_prompt._compile_prompt_if_needed(), charm_prompt._BIN_PATH
        )

    @patch("charm_prompt._go_available", return_value=True)
    @patch("charm_prompt._prompt_binary_is_stale", return_value=True)
    @patch("os.path.exists", return_value=True)
    @patch("os.makedirs")
    @patch("subprocess.run")
    def test_compile_rebuilds_when_bin_is_stale(
        self, mock_run, mock_makedirs, mock_exists, mock_stale, mock_go
    ):
        # Regression: a binary that merely *exists* used to be trusted
        # forever, so a Go source fix (e.g. the 2026-08-19 dark-theme
        # color fix) had no effect until someone deleted dashboard/bin/
        # prompt by hand. Staleness must force a rebuild even though the
        # file is present.
        res = charm_prompt._compile_prompt_if_needed()
        self.assertEqual(res, charm_prompt._BIN_PATH)
        mock_run.assert_called_once()

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


class TestPromptBinaryIsStale(unittest.TestCase):
    def setUp(self):
        import tempfile
        import time

        self.tmpdir = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.tmpdir, ignore_errors=True)
        self.bin_path = os.path.join(self.tmpdir, "bin", "prompt")
        os.makedirs(os.path.dirname(self.bin_path))
        with open(self.bin_path, "w") as f:
            f.write("stub")
        self.now = time.time()
        os.utime(self.bin_path, (self.now, self.now))

    def _write_source(self, relpath: str, mtime: float):
        path = os.path.join(self.tmpdir, relpath)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w") as f:
            f.write("package main")
        os.utime(path, (mtime, mtime))
        return path

    def test_source_newer_than_binary_is_stale(self):
        orig_dir, orig_bin = charm_prompt._DASHBOARD_DIR, charm_prompt._BIN_PATH
        charm_prompt._DASHBOARD_DIR = self.tmpdir
        charm_prompt._BIN_PATH = self.bin_path
        try:
            self._write_source("internal/theme/theme.go", self.now + 10)
            self.assertTrue(charm_prompt._prompt_binary_is_stale())
        finally:
            charm_prompt._DASHBOARD_DIR = orig_dir
            charm_prompt._BIN_PATH = orig_bin

    def test_source_older_than_binary_is_not_stale(self):
        orig_dir, orig_bin = charm_prompt._DASHBOARD_DIR, charm_prompt._BIN_PATH
        charm_prompt._DASHBOARD_DIR = self.tmpdir
        charm_prompt._BIN_PATH = self.bin_path
        try:
            self._write_source("internal/theme/theme.go", self.now - 10)
            self.assertFalse(charm_prompt._prompt_binary_is_stale())
        finally:
            charm_prompt._DASHBOARD_DIR = orig_dir
            charm_prompt._BIN_PATH = orig_bin

    def test_ignores_files_under_bin_directory(self):
        # The compiled binary itself lives under bin/ -- walking into that
        # directory and comparing the binary's own mtime against itself
        # (or leftover build artifacts there) must never count as "source
        # changed", or every run would rebuild unconditionally.
        orig_dir, orig_bin = charm_prompt._DASHBOARD_DIR, charm_prompt._BIN_PATH
        charm_prompt._DASHBOARD_DIR = self.tmpdir
        charm_prompt._BIN_PATH = self.bin_path
        try:
            self._write_source("bin/leftover.go", self.now + 10)
            self.assertFalse(charm_prompt._prompt_binary_is_stale())
        finally:
            charm_prompt._DASHBOARD_DIR = orig_dir
            charm_prompt._BIN_PATH = orig_bin


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

    @patch("charm_prompt._go_available", return_value=False)
    @patch("charm_prompt.questionary.text")
    def test_text_fallback(self, mock_q, mock_go):
        mock_q.return_value.ask.return_value = "typed value"
        self.assertEqual(charm_prompt.text("Fallback?"), "typed value")


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

    @patch("charm_prompt._go_available", return_value=True)
    @patch("charm_prompt._run_prompt", side_effect=RuntimeError("crashed"))
    @patch("charm_prompt.questionary.text")
    def test_text_degrade(self, mock_q, mock_run, mock_go):
        mock_q.return_value.ask.return_value = "fallback_text"
        res = charm_prompt.text("How many days?")
        self.assertEqual(res, "fallback_text")


class TestRunPromptDirectly(unittest.TestCase):
    @patch("charm_prompt._compile_prompt_if_needed", return_value="/custom/bin/prompt")
    @patch("os.path.exists", return_value=True)
    @patch("subprocess.run")
    def test_run_with_existing_bin(self, mock_run, mock_exists, mock_compile):
        mock_run.return_value = MagicMock(returncode=0, stdout='{"ok": true}')
        res = charm_prompt._run_prompt({"test": 1})
        self.assertEqual(res, {"ok": True})
        self.assertEqual(mock_run.call_args[0][0][0], "/custom/bin/prompt")


@unittest.skipUnless(sys.platform != "win32", "pty is POSIX-only")
@unittest.skipUnless(charm_prompt._go_available(), "requires the go toolchain")
class TestRealBinaryOverAPty(unittest.TestCase):
    """Every test above mocks subprocess.run -- proves the JSON *contract*
    (given this stdout/stderr, _run_prompt returns that), never that the
    real compiled binary actually renders and responds to a real terminal.
    That gap is exactly how two real bugs slipped through 100% green runs:
    (1) _run_prompt() used to capture_output=True both streams, silently
    hanging every select()/confirm() call forever (huh/Bubbletea need a
    real tty on stderr, not a pipe, to do raw-mode drawing) -- (2) huh's
    own dark-background autodetect, which needs a real terminal round
    trip too, was defaulting to light-mode colors. A pty is the cheapest
    stand-in for "a real terminal" available in a test: unlike a plain
    pipe, reads/writes through it behave like a tty (isatty() is true,
    raw mode is settable), which is exactly the distinction both bugs
    hinged on."""

    @classmethod
    def setUpClass(cls):
        cls.bin_path = charm_prompt._compile_prompt_if_needed()
        if not cls.bin_path or not os.path.exists(cls.bin_path):
            raise unittest.SkipTest("could not compile dashboard/cmd/prompt")

    def _run_over_pty(self, spec: dict, keypress: bytes = b"\r"):
        import pty
        import select as select_mod
        import time

        master_fd, slave_fd = pty.openpty()
        proc = subprocess.Popen(
            [self.bin_path, json.dumps(spec)],
            cwd=charm_prompt._DASHBOARD_DIR,
            stdin=slave_fd,
            stderr=slave_fd,  # huh/Bubbletea render here -- must be a tty
            stdout=subprocess.PIPE,  # the JSON answer -- the only piped stream
            text=True,
            close_fds=True,
        )
        os.close(slave_fd)
        try:
            # Give the form a moment to actually paint before "pressing"
            # anything -- this is also what would time out if stderr were
            # a plain pipe instead of a pty (bug #1 above).
            # huh's cursor blinks continuously once painted, so waiting for
            # an idle gap never fires -- a short fixed budget is more
            # reliable. In practice the first frame lands well under 1s.
            deadline = time.time() + 3
            rendered = False
            while time.time() < deadline:
                ready, _, _ = select_mod.select([master_fd], [], [], 0.2)
                if master_fd in ready:
                    if os.read(master_fd, 4096):
                        rendered = True
                if proc.poll() is not None:
                    break
            os.write(master_fd, keypress)
            stdout, _ = proc.communicate(timeout=5)
        finally:
            os.close(master_fd)
        return rendered, proc.returncode, stdout

    def test_confirm_renders_and_returns_clean_json(self):
        rendered, returncode, stdout = self._run_over_pty(
            {"type": "confirm", "message": "Proceed?", "default": True}
        )
        self.assertTrue(rendered, "nothing was ever written to the pty (hang)")
        self.assertEqual(returncode, 0)
        self.assertEqual(json.loads(stdout), {"confirmed": True})

    def test_select_renders_and_returns_clean_json(self):
        rendered, returncode, stdout = self._run_over_pty(
            {
                "type": "select",
                "message": "Pick one",
                "options": [
                    {"label": "testprofile", "value": "testprofile"},
                    {"label": "test_profile", "value": "test_profile"},
                ],
            }
        )
        self.assertTrue(rendered, "nothing was ever written to the pty (hang)")
        self.assertEqual(returncode, 0)
        self.assertEqual(json.loads(stdout), {"value": "testprofile"})


if __name__ == "__main__":
    unittest.main()
