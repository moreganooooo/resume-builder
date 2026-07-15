import os
import sys
import unittest

SCRIPTS_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts")
sys.path.insert(0, SCRIPTS_DIR)

from rich.console import Console

import cli_art  # noqa: E402


def _rendered(fn, *args, **kwargs):
    console = Console(record=True, width=100)
    original = cli_art.console
    cli_art.console = console
    try:
        fn(*args, **kwargs)
    finally:
        cli_art.console = original
    return console.export_text()


class TestDisplayError(unittest.TestCase):

    def test_renders_message_in_a_bordered_panel(self):
        output = _rendered(cli_art.display_error, "Evaluation failed.")
        self.assertIn("Evaluation failed.", output)
        self.assertIn(cli_art.theme.ICONS["error"], output)


class TestDisplaySuccess(unittest.TestCase):

    def test_renders_message_with_icon_no_border(self):
        output = _rendered(cli_art.display_success, "Resume built.")
        self.assertIn("Resume built.", output)
        self.assertIn(cli_art.theme.ICONS["success"], output)
        # No panel border characters -- success stays lightweight.
        self.assertNotIn("╭", output)  # ╭ (rounded-panel corner)


if __name__ == "__main__":
    unittest.main()
