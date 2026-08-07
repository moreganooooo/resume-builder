import os
import sys
import unittest
from unittest.mock import patch

SCRIPTS_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts")
sys.path.insert(0, SCRIPTS_DIR)

import theme  # noqa: E402
import sync_dashboard_theme  # noqa: E402


class TestBuildGoThemeSource(unittest.TestCase):

    def test_embeds_current_theme_py_hex_values(self):
        source = sync_dashboard_theme.build_go_theme_source()
        self.assertIn(f'lipgloss.Color("{theme.BRAND_ACCENT}")', source)
        self.assertIn(f'lipgloss.Color("{theme.SUCCESS}")', source)
        self.assertIn(f'lipgloss.Color("{theme.WARNING}")', source)
        self.assertIn(f'lipgloss.Color("{theme.BRAND}")', source)
        self.assertIn(f'lipgloss.Color("{theme.ERROR}")', source)
        self.assertIn(f'lipgloss.Color("{theme.INFO}")', source)

    def test_is_valid_go_package_declaration(self):
        source = sync_dashboard_theme.build_go_theme_source()
        self.assertTrue(source.startswith("package theme\n"))
        self.assertIn("func newResumeBuilder() Theme {", source)

    def test_matches_the_real_checked_in_file(self):
        # The whole point of this generator -- the committed file must
        # already equal what this produces, or doctor's drift check
        # would fail on a clean checkout.
        with open(sync_dashboard_theme.DASHBOARD_THEME_PATH, "r", encoding="utf-8") as f:
            actual = f.read()
        self.assertEqual(actual, sync_dashboard_theme.build_go_theme_source())


class TestSync(unittest.TestCase):

    def setUp(self):
        self.tmp_path = os.path.join(os.path.dirname(__file__), "_tmp_resumebuilder.go")
        self._patcher = patch("sync_dashboard_theme.DASHBOARD_THEME_PATH", self.tmp_path)
        self._patcher.start()

    def tearDown(self):
        self._patcher.stop()
        if os.path.exists(self.tmp_path):
            os.remove(self.tmp_path)

    def test_creates_the_file_and_reports_changed(self):
        self.assertFalse(os.path.exists(self.tmp_path))
        changed = sync_dashboard_theme.sync()
        self.assertTrue(changed)
        self.assertTrue(os.path.exists(self.tmp_path))

    def test_no_op_when_already_in_sync(self):
        sync_dashboard_theme.sync()
        changed_again = sync_dashboard_theme.sync()
        self.assertFalse(changed_again)


if __name__ == "__main__":
    unittest.main()
