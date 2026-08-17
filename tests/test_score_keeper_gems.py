"""Unit tests for scripts/score_keeper_gems.py."""

# pylint: disable=no-member

import csv
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

SCRIPTS_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts"
)
if SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, SCRIPTS_DIR)

import score_keeper_gems  # noqa: E402


class TestScoreKeeperGems(unittest.TestCase):
    """Test suite for score_keeper_gems module."""

    def test_detect_col(self):
        """Test detection of bullet column and fallback columns."""
        self.assertEqual(
            score_keeper_gems.detect_col(["Bullet Point", "Other"]), "Bullet Point"
        )
        self.assertEqual(
            score_keeper_gems.detect_col(["achievement", "Other"]), "achievement"
        )
        with self.assertRaises(ValueError):
            score_keeper_gems.detect_col(["invalid_1", "invalid_2"])

    def test_build_system_prompt(self):
        """Test system prompt builder with existing and missing scoring YAML."""
        prompt = score_keeper_gems.build_system_prompt()
        self.assertIn("Hidden Gem", prompt)

    @patch("score_keeper_gems.GeminiClient.generate")
    @patch("score_keeper_gems.GeminiClient.parse_json")
    def test_score_bullet_success_and_failure(self, mock_parse_json, mock_generate):
        """Test score_bullet helper on success, API failure, and parse error."""
        mock_generate.return_value = ('{"score": 95}', MagicMock())
        mock_parse_json.return_value = {
            "hidden_gem_score": 95,
            "hidden_gem_flag": True,
            "hidden_gem_reason": "Great",
        }

        res = score_keeper_gems.score_bullet("prompt", "Grew user retention by 40%")
        self.assertIsNotNone(res)
        self.assertEqual(res["hidden_gem_score"], 95)

        # Failure returns None
        mock_generate.return_value = (None, None)
        self.assertIsNone(score_keeper_gems.score_bullet("prompt", "Some bullet"))

    def test_main_empty_file(self):
        """Test main when input CSV has no rows."""
        with tempfile.TemporaryDirectory() as tmpdir:
            csv_path = Path(tmpdir) / "empty.csv"
            csv_path.write_text("", encoding="utf-8")

            with patch("sys.argv", ["score_keeper_gems.py", "--input", str(csv_path)]):
                score_keeper_gems.main()

    def test_main_dry_run_and_all_scored(self):
        """Test main in dry-run mode and when all rows are already scored."""
        with tempfile.TemporaryDirectory() as tmpdir:
            csv_path = Path(tmpdir) / "test.csv"
            with open(csv_path, "w", newline="", encoding="utf-8") as f:
                writer = csv.DictWriter(
                    f, fieldnames=["Bullet Point", "hidden_gem_score"]
                )
                writer.writeheader()
                writer.writerow(
                    {"Bullet Point": "Unscored bullet", "hidden_gem_score": ""}
                )

            # Dry-run
            with patch(
                "sys.argv",
                ["score_keeper_gems.py", "--input", str(csv_path), "--dry-run"],
            ):
                score_keeper_gems.main()

            # All scored
            with open(csv_path, "w", newline="", encoding="utf-8") as f:
                writer = csv.DictWriter(
                    f, fieldnames=["Bullet Point", "hidden_gem_score"]
                )
                writer.writeheader()
                writer.writerow(
                    {"Bullet Point": "Scored bullet", "hidden_gem_score": "95"}
                )

            with patch("sys.argv", ["score_keeper_gems.py", "--input", str(csv_path)]):
                score_keeper_gems.main()

    @patch("score_keeper_gems.score_bullet")
    @patch("time.sleep")
    def test_main_scoring_loop_and_gems_output(self, mock_sleep, mock_score_bullet):
        """Test main scoring loop, flush logic, and gems-only export."""
        mock_score_bullet.side_effect = [
            {
                "hidden_gem_score": 95,
                "hidden_gem_flag": True,
                "hidden_gem_reason": "Stunning outcome",
            },
            {
                "hidden_gem_score": 80,
                "hidden_gem_flag": False,
                "hidden_gem_reason": "Solid",
            },
            {
                "hidden_gem_score": 50,
                "hidden_gem_flag": False,
                "hidden_gem_reason": "Basic",
            },
            None,  # error case
        ]

        with tempfile.TemporaryDirectory() as tmpdir:
            in_csv = Path(tmpdir) / "input.csv"
            out_csv = Path(tmpdir) / "output.csv"
            gems_csv = Path(tmpdir) / "gems.csv"

            rows = [
                {"Bullet Point": "Gem bullet"},
                {"Bullet Point": "Strong bullet"},
                {"Bullet Point": "Solid bullet"},
                {"Bullet Point": "Error bullet"},
                {"Bullet Point": ""},  # empty bullet
            ]
            with open(in_csv, "w", newline="", encoding="utf-8") as f:
                writer = csv.DictWriter(f, fieldnames=["Bullet Point"])
                writer.writeheader()
                writer.writerows(rows)

            with patch(
                "sys.argv",
                [
                    "score_keeper_gems.py",
                    "--input",
                    str(in_csv),
                    "--output",
                    str(out_csv),
                    "--gems",
                    str(gems_csv),
                    "--limit",
                    "10",
                ],
            ):
                score_keeper_gems.main()

                self.assertTrue(out_csv.exists())
                self.assertTrue(gems_csv.exists())

                with open(gems_csv, newline="", encoding="utf-8") as f:
                    gems = list(csv.DictReader(f))
                    self.assertEqual(len(gems), 1)
                    self.assertEqual(gems[0]["Bullet Point"], "Gem bullet")


if __name__ == "__main__":
    unittest.main()
