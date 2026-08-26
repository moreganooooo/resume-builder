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

from sync_dashboard_theme import SUPPORTED_THEMES, get_active_theme, set_active_theme


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
