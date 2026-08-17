import os
import sys
import unittest
from unittest.mock import patch

SCRIPTS_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts"
)
sys.path.insert(0, SCRIPTS_DIR)

import ui_config  # noqa: E402


class TestUiConfig(unittest.TestCase):

    def setUp(self):
        self.tmp_dir = os.path.join(os.path.dirname(__file__), "_tmp_ui_config")
        os.makedirs(self.tmp_dir, exist_ok=True)
        self.path = os.path.join(self.tmp_dir, "ui_config.json")
        self._patcher = patch(
            "ui_config.profile_paths.ui_config_path", return_value=self.path
        )
        self._patcher.start()

    def tearDown(self):
        self._patcher.stop()
        if os.path.exists(self.path):
            os.remove(self.path)
        os.rmdir(self.tmp_dir)

    def test_get_returns_none_when_never_saved(self):
        self.assertIsNone(ui_config.get_icon_set())

    def test_save_then_get_round_trips(self):
        ui_config.save_icon_set("unicode")
        self.assertEqual(ui_config.get_icon_set(), "unicode")

    def test_save_rejects_unknown_icon_set(self):
        with self.assertRaises(ValueError):
            ui_config.save_icon_set("banana")

    def test_get_returns_none_on_corrupted_json(self):
        with open(self.path, "w", encoding="utf-8") as f:
            f.write("{not valid json")
        self.assertIsNone(ui_config.get_icon_set())

    def test_get_ignores_unrecognized_persisted_value(self):
        # Simulates a hand-edited or stale config -- treated the same as
        # "never answered" rather than crashing theme.py's resolution.
        with open(self.path, "w", encoding="utf-8") as f:
            f.write('{"icon_set": "banana"}')
        self.assertIsNone(ui_config.get_icon_set())

    def test_save_preserves_other_config_keys(self):
        with open(self.path, "w", encoding="utf-8") as f:
            f.write('{"other_key": "keep me"}')
        ui_config.save_icon_set("nerd")
        import json

        with open(self.path, "r", encoding="utf-8") as f:
            config = json.load(f)
        self.assertEqual(config["other_key"], "keep me")
        self.assertEqual(config["icon_set"], "nerd")


if __name__ == "__main__":
    unittest.main()
