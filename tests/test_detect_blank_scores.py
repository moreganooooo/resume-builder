"""Unit tests for scripts/detect_blank_scores.py."""

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

import pandas as pd

SCRIPTS_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts"
)
if SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, SCRIPTS_DIR)

import detect_blank_scores  # noqa: E402


class TestDetectBlankScores(unittest.TestCase):
    """Test suite for detect_blank_scores module."""

    def test_detect_bullet_col(self):
        """Test detection of bullet column name from various candidate column headers."""
        self.assertEqual(
            detect_blank_scores.detect_bullet_col(["Bullet Point", "col"]),
            "Bullet Point",
        )
        self.assertEqual(
            detect_blank_scores.detect_bullet_col(["bullet", "col"]), "bullet"
        )
        self.assertEqual(
            detect_blank_scores.detect_bullet_col(["achievement", "col"]), "achievement"
        )
        self.assertEqual(detect_blank_scores.detect_bullet_col(["text", "col"]), "text")
        self.assertEqual(
            detect_blank_scores.detect_bullet_col(["Bullet", "col"]), "Bullet"
        )
        self.assertEqual(
            detect_blank_scores.detect_bullet_col(["Achievement", "col"]), "Achievement"
        )
        self.assertIsNone(
            detect_blank_scores.detect_bullet_col(["unknown1", "unknown2"])
        )

    def test_scan_csv_file_not_found(self):
        """Test scan_csv when file does not exist."""
        report = detect_blank_scores.scan_csv(Path("/nonexistent/file.csv"))
        self.assertIn("error", report)
        self.assertEqual(report["error"], "File not found")

    def test_scan_csv_no_bullet_col(self):
        """Test scan_csv when file lacks a recognized bullet column."""
        with tempfile.TemporaryDirectory() as tmpdir:
            csv_path = Path(tmpdir) / "test.csv"
            pd.DataFrame([{"unrelated_col": "val"}]).to_csv(csv_path, index=False)
            report = detect_blank_scores.scan_csv(csv_path)
            self.assertIsNone(report["bullet_col"])
            self.assertIn("note", report)

    def test_scan_csv_scenarios(self):
        """Test scan_csv with fully scored and unscored rows."""
        with tempfile.TemporaryDirectory() as tmpdir:
            csv_path = Path(tmpdir) / "test.csv"
            df = pd.DataFrame(
                [
                    {
                        "Bullet Point": "Bullet 1 fully scored",
                        "hidden_gem_score": 90,
                        "hidden_gem_flag": True,
                        "hidden_gem_reason": "High impact",
                        "strength_category": "STRONG",
                    },
                    {
                        "Bullet Point": "Bullet 2 missing all scores",
                        "hidden_gem_score": None,
                        "hidden_gem_flag": None,
                        "hidden_gem_reason": "",
                        "strength_category": "",
                    },
                    {
                        "Bullet Point": "Bullet 3 partially missing scores",
                        "hidden_gem_score": 80,
                        "hidden_gem_flag": False,
                        "hidden_gem_reason": "",
                        "strength_category": None,
                    },
                ]
            )
            df.to_csv(csv_path, index=False)
            report = detect_blank_scores.scan_csv(csv_path)

            self.assertEqual(report["total_rows"], 3)
            self.assertEqual(report["bullet_col"], "Bullet Point")
            self.assertEqual(report["fully_unscored_rows"], 1)
            self.assertEqual(len(report["unscored_bullets"]), 1)
            self.assertEqual(
                report["unscored_bullets"][0], "Bullet 2 missing all scores"
            )

    def test_print_report(self):
        """Test print_report console output formatting for both error and valid reports."""
        error_report = {"path": "/fake/path.csv", "error": "File not found"}
        detect_blank_scores.print_report(error_report)

        valid_report_clean = {
            "path": "/fake/clean.csv",
            "total_rows": 5,
            "bullet_col": "Bullet Point",
            "missing_by_col": {},
            "fully_unscored_rows": 0,
            "unscored_bullets": [],
        }
        detect_blank_scores.print_report(valid_report_clean)

        valid_report_missing = {
            "path": "/fake/missing.csv",
            "total_rows": 5,
            "bullet_col": "Bullet Point",
            "missing_by_col": {"hidden_gem_score": 2},
            "fully_unscored_rows": 2,
            "unscored_bullets": ["Unscored bullet preview"],
        }
        detect_blank_scores.print_report(valid_report_missing)

    @patch("sys.argv", ["detect_blank_scores.py"])
    @patch("detect_blank_scores.scan_csv")
    def test_main_default_paths(self, mock_scan_csv):
        """Test main invocation across default paths."""
        mock_scan_csv.return_value = {
            "path": "test.csv",
            "total_rows": 0,
            "bullet_col": None,
            "missing_by_col": {},
            "fully_unscored_rows": 0,
            "unscored_bullets": [],
        }
        detect_blank_scores.main()
        self.assertTrue(mock_scan_csv.called)

    def test_main_custom_csv_and_fix_flag(self):
        """Test main invocation with --csv and --fix flags."""
        with tempfile.TemporaryDirectory() as tmpdir:
            csv_path = Path(tmpdir) / "test.csv"
            out_json = Path(tmpdir) / "output" / "json" / "unscored_bullets.json"
            pd.DataFrame(
                [
                    {
                        "Bullet Point": "Unscored bullet",
                        "hidden_gem_score": None,
                        "hidden_gem_flag": None,
                        "hidden_gem_reason": None,
                        "strength_category": None,
                    }
                ]
            ).to_csv(csv_path, index=False)

            with patch(
                "sys.argv", ["detect_blank_scores.py", "--csv", str(csv_path), "--fix"]
            ):
                with patch.object(
                    detect_blank_scores, "OUTPUT_DIR", Path(tmpdir) / "output" / "json"
                ):
                    detect_blank_scores.main()
                    self.assertTrue(out_json.exists())
                    with open(out_json, "r", encoding="utf-8") as f:
                        data = json.load(f)
                        self.assertEqual(len(data), 1)
                        self.assertEqual(data[0]["bullet"], "Unscored bullet")


if __name__ == "__main__":
    unittest.main()
