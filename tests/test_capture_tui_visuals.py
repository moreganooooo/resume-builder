"""Keeps the capture script's screen list in step with the tapes on disk.

A tape that is not in ALL_SCREENS is never captured by `--screen all` and
cannot be named with `--screen <name>` at all -- so it silently stops being
re-recorded, and its artifact goes stale while every other screen refreshes.
That is exactly what happened to the insights, kb_skills and pipeline_board
tapes, which sat unrunnable until 2026-09-22.
"""

import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))

import capture_tui_visuals  # noqa: E402

TAPES_DIR = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "..", "dashboard", "tapes"
)


def _tape_names() -> set:
    return {
        name[: -len(".tape")]
        for name in os.listdir(TAPES_DIR)
        if name.endswith(".tape")
    }


class TestCaptureScreensMatchTapes(unittest.TestCase):
    def test_every_tape_is_capturable(self):
        missing = sorted(_tape_names() - set(capture_tui_visuals.ALL_SCREENS))
        self.assertEqual(
            [],
            missing,
            "these tapes exist but `--screen all` will never run them; "
            "add them to ALL_SCREENS",
        )

    def test_every_listed_screen_has_a_tape(self):
        # The other direction: a name with no tape fails at capture time
        # with "VHS tape not found" rather than at review time.
        orphaned = sorted(set(capture_tui_visuals.ALL_SCREENS) - _tape_names())
        self.assertEqual([], orphaned, "these screens have no tape to run")

    def test_screen_names_are_unique(self):
        screens = capture_tui_visuals.ALL_SCREENS
        self.assertEqual(len(screens), len(set(screens)))


if __name__ == "__main__":
    unittest.main()
