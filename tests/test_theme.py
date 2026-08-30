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


class TestUnicodeIconsAreTextNotEmoji(unittest.TestCase):
    """The unicode icon set has silently reverted to emoji twice (see
    theme.py's _UNICODE_ICONS comment). Emoji are double-width and
    ignore the ANSI palette, which breaks Rich's column math -- assert
    the property instead of trusting the comment to hold."""

    # Emoji_Presentation=Yes blocks, plus the dingbat/symbol emoji that
    # have crept in here before (gem, floppy, magnifier, bar chart).
    EMOJI_RANGES = (
        (0x1F300, 0x1FAFF),
        (0x1F000, 0x1F2FF),
        (0x2600, 0x27BF),
    )
    # Text-presentation codepoints that live inside the ranges above but
    # are NOT emoji-by-default -- these are legitimate picks.
    TEXT_ALLOWLIST = {"✓", "✗", "⚠", "✦", "⚙", "⚒", "❮", "❯"}

    def _is_emoji(self, ch: str) -> bool:
        if ch in self.TEXT_ALLOWLIST:
            return False
        cp = ord(ch)
        return any(lo <= cp <= hi for lo, hi in self.EMOJI_RANGES)

    def test_no_unicode_icon_is_an_emoji(self):
        offenders = {
            name: glyph
            for name, glyph in theme._UNICODE_ICONS.items()
            for ch in glyph
            if self._is_emoji(ch)
        }
        self.assertEqual(
            offenders, {}, f"emoji leaked into _UNICODE_ICONS: {offenders}"
        )

    def test_every_unicode_icon_is_single_width(self):
        from wcwidth import wcswidth

        wide = {
            name: (glyph, wcswidth(glyph))
            for name, glyph in theme._UNICODE_ICONS.items()
            if wcswidth(glyph) != 1
        }
        self.assertEqual(wide, {}, f"non-single-width icons break Rich layout: {wide}")

    def test_semantic_slots_have_distinct_glyphs(self):
        """build/utility and the nav pairs are allowed to alias by design;
        everything else sharing a glyph is a collision bug."""
        aliased = {"complete", "gem", "back", "next"}
        distinct = {
            name: g for name, g in theme._UNICODE_ICONS.items() if name not in aliased
        }
        self.assertEqual(
            len(set(distinct.values())),
            len(distinct),
            f"duplicate glyphs among {sorted(distinct)}",
        )


class TestIconSetsAgree(unittest.TestCase):
    """Every icon name must exist in BOTH sets.

    questionary_icon_tuple() falls back to returning the NAME as the
    label when a key is missing, so a unicode-only key renders the
    literal word "location" in the menu for anyone on the default Nerd
    Font set -- visible only to them, and never in a test run, which
    resolves to the unicode set. That is exactly how "location" shipped
    that way.
    """

    def test_nerd_and_unicode_cover_the_same_names(self):
        self.assertEqual(
            set(theme._NERD_ICONS),
            set(theme._UNICODE_ICONS),
            "an icon defined in only one set renders as its own name",
        )

    def test_every_icon_has_a_color(self):
        self.assertEqual(set(theme._UNICODE_ICONS), set(theme._ICON_COLORS))


if __name__ == "__main__":
    unittest.main()
