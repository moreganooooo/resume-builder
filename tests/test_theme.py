import os
import sys
import unittest
from unittest.mock import patch

SCRIPTS_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts")
sys.path.insert(0, SCRIPTS_DIR)

import importlib

import theme  # noqa: E402
import orchestrator  # noqa: E402


class TestIconSwitch(unittest.TestCase):

    def test_defaults_to_nerd_font_icons(self):
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("RESUME_BUILDER_ICONS", None)
            reloaded = importlib.reload(theme)
        self.assertEqual(reloaded.ICONS["success"], "")

    def test_unicode_env_var_switches_to_unicode_icons(self):
        with patch.dict(os.environ, {"RESUME_BUILDER_ICONS": "unicode"}):
            reloaded = importlib.reload(theme)
        self.assertEqual(reloaded.ICONS["success"], "✓")
        importlib.reload(theme)  # restore default for subsequent tests

    def test_unrecognized_value_falls_back_to_nerd_font(self):
        with patch.dict(os.environ, {"RESUME_BUILDER_ICONS": "banana"}):
            reloaded = importlib.reload(theme)
        self.assertEqual(reloaded.ICONS["success"], "")
        importlib.reload(theme)

    def test_bullet_bank_icon_exists_in_both_sets(self):
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("RESUME_BUILDER_ICONS", None)
            nerd = importlib.reload(theme)
        self.assertIn("bullet_bank", nerd.ICONS)
        with patch.dict(os.environ, {"RESUME_BUILDER_ICONS": "unicode"}):
            unicode_theme = importlib.reload(theme)
        self.assertIn("bullet_bank", unicode_theme.ICONS)
        importlib.reload(theme)


class TestRecommendationColors(unittest.TestCase):

    def test_keys_match_fit_evaluation_schema_literal(self):
        schema_values = orchestrator.FitEvaluationSchema.model_fields["recommendation"].annotation.__args__
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
