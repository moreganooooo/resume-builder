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

    def test_json_with_trailing_data_parses_first_object(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "extra.json"
            path.write_text('{"company": "Acme"} extra trailing text', encoding="utf-8")
            result = sync_jd.load_json(path)
            self.assertEqual(result, {"company": "Acme"})

    def test_file_read_os_error_warns_and_returns_empty_dict(self):
        path = Path("/nonexistent/path/never_exists.json")
        with patch("sync_jd_to_applications_enhanced.cli_art.cli_warning") as mock_warn:
            result = sync_jd.load_json(path)
            self.assertEqual(result, {})
            mock_warn.assert_called_once()


class TestHelpers(unittest.TestCase):
    def test_format_score(self):
        self.assertEqual(sync_jd.format_score({"composite_score": 4.5}), "4.50/5")
        self.assertEqual(sync_jd.format_score({"composite_score": 5}), "5.00/5")
        self.assertEqual(sync_jd.format_score({}), "NA")
        self.assertEqual(sync_jd.format_score({"composite_score": "high"}), "NA")

    def test_parse_existing_md(self):
        with tempfile.TemporaryDirectory() as tmp:
            md_path = Path(tmp) / "applications.md"
            self.assertEqual(sync_jd.parse_existing_md(md_path), {})

            content = (
                "| # | Date | Company | Role | Score | Status | PDF | Link | Report | Notes |\n"
                "|---|------|---------|------|-------|--------|-----|------|--------|-------|\n"
                "Random non-table line\n"
                "| 1 | short | row |\n"
                "| 1 | 2026-08-01 | Acme | Dev | 4.50/5 | Evaluated | ✓ | [Apply](url) | rep.pdf | Call next week |\n"
            )
            md_path.write_text(content, encoding="utf-8")
            existing = sync_jd.parse_existing_md(md_path)
            self.assertEqual(
                existing.get(("2026-08-01", "Acme", "Dev")), "Call next week"
            )

    def test_format_row(self):
        data = {
            "date": "2026-08-01",
            "company": "Acme",
            "role": "Lead",
            "evaluation": {"composite_score": 4.2},
            "status": "Interview",
            "has_pdf": True,
            "source_url": "https://example.com",
            "report_path": "report.pdf",
            "notes": "Custom note",
        }
        row = sync_jd.format_row(1, data, preserved_notes="Old note")
        self.assertIn(
            "| 1 | 2026-08-01 | Acme | Lead | 4.20/5 | Interview | ✓ | [Apply](https://example.com) | report.pdf | Custom note |",
            row,
        )

        data_no_notes = {
            "date": "2026-08-01",
            "company": "Acme",
            "role": "Lead",
        }
        row_preserved = sync_jd.format_row(2, data_no_notes, preserved_notes="Old note")
        self.assertIn("Old note |", row_preserved)


class TestMainWritesSuccessMessage(unittest.TestCase):
    """main() now resolves its paths through profile_paths instead of
    hand-rolling them off __file__, so this runs fully sandboxed. It used
    to have to create jds/_test_sync_jd_tmp_profile and
    data/_test_sync_jd_tmp_profile under the real repo root and remove them
    in tearDown -- which left them behind on any error before that point."""

    PROFILE = "_test_sync_jd_tmp_profile"

    def setUp(self):
        import profile_paths

        self._tmp = tempfile.TemporaryDirectory()
        self._iso = profile_paths.isolate_for_tests(self._tmp.name)
        self._iso.__enter__()
        self.jds_dir = Path(profile_paths.jds_dir(self.PROFILE))
        self.data_dir = Path(profile_paths.data_dir(self.PROFILE))
        self.jds_dir.mkdir(parents=True)
        (self.jds_dir / "a.json").write_text(
            json.dumps({"date": "2026-08-01", "company": "Acme", "role": "Engineer"}),
            encoding="utf-8",
        )

    def tearDown(self):
        self._iso.__exit__(None, None, None)
        self._tmp.cleanup()

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

    def test_main_no_json_files_exits(self):
        for f in self.jds_dir.glob("*.json"):
            f.unlink()
        with patch("sync_jd_to_applications_enhanced.cli_art.cli_error") as mock_err:
            with self.assertRaises(SystemExit) as cm:
                sync_jd.main(self.PROFILE)
            self.assertEqual(cm.exception.code, 1)
            mock_err.assert_called_once()


if __name__ == "__main__":
    unittest.main()
