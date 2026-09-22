"""Unit tests for sync_dashboard_theme.py."""

import os
import sys
import tempfile
import unittest
from unittest.mock import patch

SCRIPTS_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts"
)
if SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, SCRIPTS_DIR)

from sync_dashboard_theme import (
    DASHBOARD_THEME_PATH,
    SUBSCORE_LABELS_PATH,
    SUPPORTED_THEMES,
    build_go_theme_source,
    build_subscore_labels_source,
    get_active_theme,
    set_active_theme,
)


class TestGeneratedFilesAreInSync(unittest.TestCase):
    """Both Go files are GENERATED, and nothing else proves they still
    match their generator.

    Two distinct regressions this catches. (1) Drift: editing
    theme.py/_FIT_DIMENSION_GROUPS without re-running the script leaves
    the dashboard on stale values -- and `resume doctor`'s auto-repair
    silently rewrites the file out from under whoever hand-edited it.
    (2) Formatting: the generator emitted an un-gofmt'd map literal, so
    every run produced a formatting-only diff that gofmt immediately
    undid, which made a real content change indistinguishable from noise.
    Comparing generated source against the committed bytes covers both,
    since gofmt alignment is part of those bytes.
    """

    def _assert_in_sync(self, path, generated):
        with open(path, "r", encoding="utf-8") as f:
            committed = f.read()
        self.assertEqual(
            committed,
            generated,
            f"{os.path.basename(path)} is out of sync with its generator. "
            "Re-run: python scripts/sync_dashboard_theme.py",
        )

    def test_dashboard_theme_matches_generator(self):
        self._assert_in_sync(DASHBOARD_THEME_PATH, build_go_theme_source())

    def test_subscore_labels_match_generator(self):
        self._assert_in_sync(SUBSCORE_LABELS_PATH, build_subscore_labels_source())

    def test_subscore_labels_map_is_gofmt_aligned(self):
        """gofmt pads a map literal's values to one column past the
        longest key, so every value starts at the same column. Asserted
        directly rather than only via the byte comparison above, so the
        failure names the actual rule when someone changes the emitter."""
        entry_lines = [
            line
            for line in build_subscore_labels_source().split("\n")
            if line.startswith('\t"')
        ]
        self.assertTrue(entry_lines, "no map entries were generated")
        columns = {line.index('"', line.index(":")) for line in entry_lines}
        self.assertEqual(
            len(columns),
            1,
            f"map values start at {len(columns)} different columns; gofmt aligns them to one",
        )


class TestSyncDashboardTheme(unittest.TestCase):

    def setUp(self):
        self.tmp_dir = tempfile.TemporaryDirectory()
        self.patcher = patch(
            "profile_paths.profile_root", return_value=self.tmp_dir.name
        )
        self.patcher.start()

    def tearDown(self):
        self.patcher.stop()
        self.tmp_dir.cleanup()

    def test_default_theme(self):
        self.assertEqual(get_active_theme(), "modern")

    def test_set_and_get_theme(self):
        self.assertTrue(set_active_theme("cyberpunk"))
        self.assertEqual(get_active_theme(), "cyberpunk")

    def test_invalid_theme(self):
        self.assertFalse(set_active_theme("nonexistent_theme"))
        self.assertEqual(get_active_theme(), "modern")


if __name__ == "__main__":
    unittest.main()
