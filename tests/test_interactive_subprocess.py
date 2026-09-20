"""Tests for scripts/interactive_subprocess.py -- the subprocess.run()
replacement that guarantees an interactive Go TUI/prompt child is cleaned
up no matter how the parent goes away (see that module's own docstring
for the ~30-orphaned-processes incident this exists to prevent).
"""

import os
import subprocess
import sys
import time
import unittest
from unittest.mock import MagicMock, patch

SCRIPTS_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts"
)
if SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, SCRIPTS_DIR)

import interactive_subprocess  # noqa: E402


class TestRunHappyPath(unittest.TestCase):
    def test_returns_completed_process_with_stdout(self):
        result = interactive_subprocess.run(
            [sys.executable, "-c", "print('hello')"],
            stdout=subprocess.PIPE,
            text=True,
        )
        self.assertEqual(result.returncode, 0)
        self.assertEqual(result.stdout.strip(), "hello")

    def test_process_removed_from_active_set_on_completion(self):
        interactive_subprocess.run([sys.executable, "-c", "pass"])
        self.assertEqual(len(interactive_subprocess._active_processes), 0)

    def test_check_true_raises_on_nonzero_exit(self):
        with self.assertRaises(subprocess.CalledProcessError):
            interactive_subprocess.run(
                [sys.executable, "-c", "import sys; sys.exit(1)"], check=True
            )

    def test_check_false_does_not_raise_on_nonzero_exit(self):
        result = interactive_subprocess.run(
            [sys.executable, "-c", "import sys; sys.exit(3)"]
        )
        self.assertEqual(result.returncode, 3)

    def test_capture_output_convenience_captures_both_streams(self):
        result = interactive_subprocess.run(
            [
                sys.executable,
                "-c",
                "import sys; print('out'); print('err', file=sys.stderr)",
            ],
            capture_output=True,
            text=True,
        )
        self.assertEqual(result.stdout.strip(), "out")
        self.assertEqual(result.stderr.strip(), "err")

    def test_timeout_kills_the_process_and_raises(self):
        with self.assertRaises(subprocess.TimeoutExpired):
            interactive_subprocess.run(
                [sys.executable, "-c", "import time; time.sleep(30)"], timeout=0.2
            )
        self.assertEqual(len(interactive_subprocess._active_processes), 0)


class TestRunExceptionCleanup(unittest.TestCase):
    """The exact gap subprocess.run() already covers on its own (an
    exception raised while blocked in communicate()) -- asserted here so
    a future refactor of run() can't silently drop it."""

    def test_keyboard_interrupt_during_communicate_kills_child_and_reraises(self):
        fake_proc = MagicMock()
        fake_proc.communicate.side_effect = KeyboardInterrupt()
        fake_proc.returncode = None

        with patch("interactive_subprocess.subprocess.Popen", return_value=fake_proc):
            with self.assertRaises(KeyboardInterrupt):
                interactive_subprocess.run(["irrelevant"])

        fake_proc.kill.assert_called_once()
        fake_proc.wait.assert_called_once()
        self.assertNotIn(fake_proc, interactive_subprocess._active_processes)


class TestTerminateAll(unittest.TestCase):
    """Exercises the SIGTERM/SIGHUP/atexit cleanup path against a REAL
    subprocess (not a mock) -- the whole point is verifying an actual OS
    process actually dies, which a mocked Popen can't demonstrate."""

    def setUp(self):
        interactive_subprocess._active_processes.clear()

    def tearDown(self):
        interactive_subprocess._active_processes.clear()

    def test_terminates_a_real_tracked_process(self):
        proc = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(30)"])
        interactive_subprocess._active_processes.add(proc)
        try:
            self.assertIsNone(proc.poll())  # still running
            interactive_subprocess._terminate_all()
            proc.wait(timeout=5)
            self.assertIsNotNone(proc.poll())
        finally:
            if proc.poll() is None:
                proc.kill()
                proc.wait()

    def test_already_finished_process_is_left_alone(self):
        proc = subprocess.Popen([sys.executable, "-c", "pass"])
        proc.wait()
        interactive_subprocess._active_processes.add(proc)
        # Must not raise even though the process is long gone.
        interactive_subprocess._terminate_all()

    def test_signum_restores_default_disposition_and_resignals(self):
        # Verifies the re-signal path without actually taking the process
        # down: patch os.kill/signal.signal to observe the calls instead.
        with (
            patch("interactive_subprocess.signal.signal") as mock_signal,
            patch("interactive_subprocess.os.kill") as mock_kill,
        ):
            interactive_subprocess._terminate_all(signum=15)
        mock_signal.assert_called_once()
        args, _ = mock_signal.call_args
        self.assertEqual(args[0], 15)
        mock_kill.assert_called_once()

    def test_no_signum_does_not_resignal(self):
        with (
            patch("interactive_subprocess.signal.signal") as mock_signal,
            patch("interactive_subprocess.os.kill") as mock_kill,
        ):
            interactive_subprocess._terminate_all()
        mock_signal.assert_not_called()
        mock_kill.assert_not_called()


class TestModuleRegistration(unittest.TestCase):
    def test_sigterm_and_sighup_have_handlers_installed(self):
        import signal

        self.assertIs(
            signal.getsignal(signal.SIGTERM), interactive_subprocess._terminate_all
        )
        if hasattr(signal, "SIGHUP"):
            self.assertIs(
                signal.getsignal(signal.SIGHUP), interactive_subprocess._terminate_all
            )


if __name__ == "__main__":
    unittest.main()
