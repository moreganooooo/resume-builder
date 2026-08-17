import os
import sys
import unittest

SCRIPTS_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts"
)
sys.path.insert(0, SCRIPTS_DIR)

import cli_art  # noqa: E402


class TestHintConstant(unittest.TestCase):

    def test_hint_uses_theme_icon_and_color_by_default(self):
        self.assertIn(cli_art.theme.ICONS["hint"], cli_art.HINT)
        self.assertIn(cli_art.theme.INFO, cli_art.HINT)


class TestNewUserStyleToken(unittest.TestCase):

    def test_new_user_token_registered(self):
        style_rules = dict(cli_art.QUESTIONARY_STYLE.style_rules)
        self.assertIn("new_user", style_rules)
        self.assertIn(cli_art.theme.SUCCESS, style_rules["new_user"])


class TestDisplayBootstrapIntro(unittest.TestCase):

    def test_runs_without_error_and_mentions_doc_count(self):
        console = cli_art.Console(record=True)
        original_console = cli_art.console
        cli_art.console = console
        try:
            cli_art.display_bootstrap_intro(3)
        finally:
            cli_art.console = original_console
        output = console.export_text()
        self.assertIn("3", output)


if __name__ == "__main__":
    unittest.main()
