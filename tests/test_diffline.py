"""Tests for scripts/diffline.py -- the CLI before/after renderer."""

import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))

import diffline  # noqa: E402
import theme  # noqa: E402
from rich.console import Console  # noqa: E402


def plain(markup: str) -> str:
    """The line as a terminal with no color support would show it."""
    console = Console(no_color=True, force_terminal=False, width=200)
    with console.capture() as cap:
        console.print(markup, soft_wrap=True, markup=True, highlight=False)
    return cap.get().rstrip("\n")


class TestDiffLine(unittest.TestCase):
    def test_sign_column_survives_losing_the_color(self):
        """Copied into a plain-text email, the diff still reads as a diff."""
        lines = diffline.render_rewrite("old text here", "new text here", "because")
        signs = [plain(line)[0] for line in lines]
        self.assertEqual(signs, ["-", "+", "┃"])

    def test_unchanged_lines_keep_the_column(self):
        """A blank sign, not a missing one -- otherwise the text shifts."""
        same = plain(diffline.render_line("same", "kept"))
        added = plain(diffline.render_line("add", "kept"))
        self.assertEqual(same, "  kept")
        self.assertEqual(len(same), len(added))

    def test_removed_text_is_not_struck_through(self):
        line = diffline.render_line("remove", "the original bullet")
        self.assertNotIn("strike", line)
        self.assertIn("the original bullet", plain(line))

    def test_each_kind_has_its_own_color(self):
        colors = {diffline.COLORS[k] for k in ("add", "remove", "same", "note")}
        self.assertEqual(len(colors), 4)
        self.assertEqual(diffline.COLORS["add"], theme.SUCCESS)
        self.assertEqual(diffline.COLORS["remove"], theme.ERROR)

    def test_emphasis_is_bold_never_a_fill(self):
        line = diffline.render_line("add", "grew revenue 40%", emphasis=["40%"])
        self.assertIn("[bold]40%[/bold]", line)
        self.assertNotIn("on ", line)  # Rich's background syntax is "on <color>"

    def test_only_the_new_words_are_emphasized(self):
        words = diffline.changed_words(
            "Managed the email program", "Managed the email program, lifting CTR 22%"
        )
        self.assertIn("lifting", words)
        self.assertNotIn("Managed", words)

    def test_markup_in_a_bullet_is_escaped_not_interpreted(self):
        """A bullet containing brackets must not be read as Rich markup."""
        self.assertIn(
            "[Adobe]", plain(diffline.render_line("add", "Ran [Adobe] pilot"))
        )

    def test_reasoning_is_optional(self):
        self.assertEqual(len(diffline.render_rewrite("a b c", "a b d")), 2)

    def test_nothing_is_truncated(self):
        long_bullet = "word " * 60
        out = plain(diffline.render_line("add", long_bullet.strip()))
        self.assertNotIn("...", out)
        self.assertIn("word word", out)


if __name__ == "__main__":
    unittest.main()
