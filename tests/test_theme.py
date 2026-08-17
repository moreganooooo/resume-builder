import os
import sys
import unittest
from unittest.mock import patch

SCRIPTS_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts"
)
sys.path.insert(0, SCRIPTS_DIR)

import importlib

import orchestrator  # noqa: E402
import theme  # noqa: E402


class TestIconSwitch(unittest.TestCase):
    """B33's priority chain: explicit RESUME_BUILDER_ICONS=unicode wins
    outright > this profile's persisted first-launch answer
    (ui_config.get_icon_set()) > a real terminal with no answer yet
    defaults to Nerd Font (the interactive prompt asks properly at
    startup) > no terminal (tests, CI, piped output) with no answer
    defaults to Unicode -- deterministic, never garbled."""

    def tearDown(self):
        # Every test here mutates process-global state (env var, or the
        # module-level ICONS reload) -- always leave it clean for whatever
        # test runs next, regardless of pass/fail.
        os.environ.pop("RESUME_BUILDER_ICONS", None)
        importlib.reload(theme)

    def test_env_var_override_wins_even_with_a_persisted_nerd_answer(self):
        with patch.dict(os.environ, {"RESUME_BUILDER_ICONS": "unicode"}):
            with patch("ui_config.get_icon_set", return_value="nerd"):
                reloaded = importlib.reload(theme)
        self.assertEqual(reloaded.ICONS["success"], "✓")

    def test_unrecognized_env_value_falls_through_to_persisted_or_default(self):
        with patch.dict(os.environ, {"RESUME_BUILDER_ICONS": "banana"}):
            with patch("ui_config.get_icon_set", return_value="unicode"):
                reloaded = importlib.reload(theme)
        self.assertEqual(reloaded.ICONS["success"], "✓")

    def test_persisted_choice_is_honored_over_the_tty_default(self):
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("RESUME_BUILDER_ICONS", None)
            with (
                patch("sys.stdin.isatty", return_value=True),
                patch("ui_config.get_icon_set", return_value="unicode"),
            ):
                reloaded = importlib.reload(theme)
        self.assertEqual(reloaded.ICONS["success"], "✓")

    def test_real_terminal_with_no_answer_defaults_to_nerd_font(self):
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("RESUME_BUILDER_ICONS", None)
            with (
                patch("sys.stdin.isatty", return_value=True),
                patch("ui_config.get_icon_set", return_value=None),
            ):
                reloaded = importlib.reload(theme)
        self.assertEqual(reloaded.ICONS["success"], "")

    def test_non_tty_with_no_answer_defaults_to_unicode(self):
        # The deliberate behavior change from the old design (which always
        # failed toward Nerd Font): a non-interactive run with no
        # persisted answer can't ask, so it defaults to the icon set
        # that's never garbled rather than the one that might be.
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("RESUME_BUILDER_ICONS", None)
            with (
                patch("sys.stdin.isatty", return_value=False),
                patch("ui_config.get_icon_set", return_value=None),
            ):
                reloaded = importlib.reload(theme)
        self.assertEqual(reloaded.ICONS["success"], "✓")

    def test_bullet_bank_icon_exists_in_both_sets(self):
        self.assertIn("bullet_bank", theme._NERD_ICONS)
        self.assertIn("bullet_bank", theme._UNICODE_ICONS)

    def test_set_icon_set_switches_the_live_module_global(self):
        theme.set_icon_set("unicode")
        self.assertEqual(theme.ICONS["success"], "✓")
        theme.set_icon_set("nerd")
        self.assertEqual(theme.ICONS["success"], "")

    def test_set_icon_set_rejects_an_unknown_name(self):
        with self.assertRaises(ValueError):
            theme.set_icon_set("banana")


class TestRecommendationColors(unittest.TestCase):

    def test_keys_match_fit_evaluation_schema_literal(self):
        schema_values = orchestrator.FitEvaluationSchema.model_fields[
            "recommendation"
        ].annotation.__args__
        self.assertEqual(set(theme.RECOMMENDATION_COLORS.keys()), set(schema_values))
        self.assertEqual(set(theme.RECOMMENDATION_STYLES.keys()), set(schema_values))

    def test_skip_style_is_not_bold_others_are(self):
        self.assertNotIn("bold", theme.RECOMMENDATION_STYLES["Skip"])
        self.assertIn("bold", theme.RECOMMENDATION_STYLES["Strong pursue"])


class TestQuestionaryStyle(unittest.TestCase):

    def test_new_user_token_is_success_colored(self):
        style_rules = dict(theme.QUESTIONARY_STYLE.style_rules)
        self.assertIn("new_user", style_rules)
        self.assertIn(theme.SUCCESS, style_rules["new_user"])


if __name__ == "__main__":
    unittest.main()
