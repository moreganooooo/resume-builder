import json
import os
import shutil
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

SCRIPTS_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts"
)
sys.path.insert(0, SCRIPTS_DIR)

import sync_jd_to_applications_enhanced as sync_jd  # noqa: E402


class TestLoadJson(unittest.TestCase):

    def test_valid_json_parses_normally_without_warning(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "a.json"
            path.write_text(json.dumps({"company": "Acme"}), encoding="utf-8")
            with patch(
                "sync_jd_to_applications_enhanced.cli_art.cli_warning"
            ) as mock_warn:
                result = sync_jd.load_json(path)
            self.assertEqual(result, {"company": "Acme"})
            mock_warn.assert_not_called()

    def test_empty_file_returns_empty_dict_without_warning(self):
        # An empty file is not itself an error -- see load_json's docstring.
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "empty.json"
            path.write_text("", encoding="utf-8")
            with patch(
                "sync_jd_to_applications_enhanced.cli_art.cli_warning"
            ) as mock_warn:
                result = sync_jd.load_json(path)
            self.assertEqual(result, {})
            mock_warn.assert_not_called()

    def test_malformed_json_warns_and_returns_empty_dict(self):
        # Regression: this used to fail silently, so a malformed JD JSON
        # became an all-placeholder row in applications.md with zero
        # indication anything had failed.
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "malformed.json"
            path.write_text("{not valid json at all", encoding="utf-8")
            with patch(
                "sync_jd_to_applications_enhanced.cli_art.cli_warning"
            ) as mock_warn:
                result = sync_jd.load_json(path)
            self.assertEqual(result, {})
            mock_warn.assert_called_once()
            self.assertIn(str(path), mock_warn.call_args[0][0])


class TestMainWritesSuccessMessage(unittest.TestCase):
    """main() derives project_root from __file__, so this exercises it
    against a disposable profile under the real repo root rather than
    monkeypatching Path.resolve (which would patch pathlib.Path globally,
    not just this module's usage of it)."""

    PROFILE = "_test_sync_jd_tmp_profile"

    def setUp(self):
        project_root = Path(sync_jd.__file__).resolve().parents[1]
        self.jds_dir = project_root / "jds" / self.PROFILE
        self.data_dir = project_root / "data" / self.PROFILE
        self.jds_dir.mkdir(parents=True)
        (self.jds_dir / "a.json").write_text(
            json.dumps({"date": "2026-08-01", "company": "Acme", "role": "Engineer"}),
            encoding="utf-8",
        )

    def tearDown(self):
        shutil.rmtree(self.jds_dir, ignore_errors=True)
        shutil.rmtree(self.data_dir, ignore_errors=True)

    def test_success_message_has_no_bracket_tag_and_no_double_prefix(self):
        with (
            patch(
                "sync_jd_to_applications_enhanced.cli_art.cli_success"
            ) as mock_success,
            patch(
                "sync_jd_to_applications_enhanced.cli_art.console.print"
            ) as mock_print,
        ):
            sync_jd.main(self.PROFILE)

        mock_success.assert_called_once()
        message = mock_success.call_args[0][0]
        self.assertNotIn("[sync]", message)
        self.assertIn("Wrote 1 rows", message)
        # The old bare-bracket-tag print() call site should be gone entirely.
        for call in mock_print.call_args_list:
            if call.args:
                self.assertNotIn("[sync]", call.args[0])


if __name__ == "__main__":
    unittest.main()
