"""Unit tests for scripts/tune_rubrics.py."""

import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

SCRIPTS_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts"
)
if SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, SCRIPTS_DIR)

import tune_rubrics  # noqa: E402


class TestTuneRubrics(unittest.TestCase):
    """Test suite for tune_rubrics module."""

    def test_load_applications(self):
        """Test parsing of markdown table applications."""
        with tempfile.TemporaryDirectory() as tmpdir:
            md_path = Path(tmpdir) / "applications.md"
            self.assertEqual(tune_rubrics.load_applications(md_path), [])

            content = """# Applications
| # | Date | Company | Role | Score | Status | PDF | Link | Report | Notes |
|---|---|---|---|---|---|---|---|---|---|
| 1 | 2026-08-01 | Acme Corp | Lead Strategist | 4.5/5 | Interview | [PDF](a.pdf) | [Link](x.com) | [Rep](r.md) | None |
| 2 | 2026-08-02 | Beta Tech | Content Writer | 2.5/5 | Rejected | [PDF](b.pdf) | [Link](y.com) | [Rep](r.md) | Passed |
| 3 | 2026-08-03 | Gamma Inc | Manager | NA | Applied | [PDF](c.pdf) | [Link](z.com) | [Rep](r.md) | |
"""
            md_path.write_text(content, encoding="utf-8")
            apps = tune_rubrics.load_applications(md_path)
            self.assertEqual(len(apps), 3)
            self.assertEqual(apps[0]["company"], "Acme Corp")
            self.assertEqual(apps[0]["score"], 4.5)
            self.assertEqual(apps[0]["status"], "Interview")
            self.assertIsNone(apps[2]["score"])

    def test_find_jd_payload(self):
        """Test find_jd_payload matches job json files by normalized company and role."""
        with tempfile.TemporaryDirectory() as tmpdir:
            jds_dir = Path(tmpdir)
            jd_file = jds_dir / "acme.json"
            jd_file.write_text(
                '{"company": "Acme Corp", "role": "Lead Strategist"}', encoding="utf-8"
            )

            match = tune_rubrics.find_jd_payload(
                jds_dir, "Acme Corp", "Lead Strategist"
            )
            self.assertIsNotNone(match)
            self.assertEqual(match.get("company"), "Acme Corp")

            no_match = tune_rubrics.find_jd_payload(jds_dir, "Unknown Corp", "Engineer")
            self.assertIsNone(no_match)

    def test_calculate_optimal_thresholds(self):
        """Test threshold calculation with and without success/unsuccess data."""
        # Empty list
        rec = tune_rubrics.calculate_optimal_thresholds([])
        self.assertEqual(rec["excellent_match"], 85)

        # With success and unsuccess apps
        apps = [
            {"score": 4.5, "status": "interview"},  # 90
            {"score": 4.0, "status": "offer"},  # 80
            {"score": 2.5, "status": "rejected"},  # 50
        ]
        rec = tune_rubrics.calculate_optimal_thresholds(apps)
        self.assertEqual(rec["success_count"], 2)
        self.assertEqual(rec["unsuccess_count"], 1)
        self.assertTrue(rec["excellent_match"] > rec["good_match"] > rec["weak_match"])

        # Unsuccess only
        apps_unsuccess = [{"score": 3.0, "status": "rejected"}]
        rec_u = tune_rubrics.calculate_optimal_thresholds(apps_unsuccess)
        self.assertEqual(rec_u["success_count"], 0)
        self.assertEqual(rec_u["unsuccess_count"], 1)

    def test_update_ats_match_yaml(self):
        """Test YAML file update preserving structure and comments."""
        with tempfile.TemporaryDirectory() as tmpdir:
            yaml_path = Path(tmpdir) / "ats_match.yaml"
            self.assertFalse(tune_rubrics.update_ats_match_yaml(yaml_path, {}))

            content = """thresholds:
  excellent_match: 85  # Ready
  good_match: 70       # Tailor
  weak_match: 50       # Missing
"""
            yaml_path.write_text(content, encoding="utf-8")
            thresholds = {"excellent_match": 90, "good_match": 75, "weak_match": 55}
            success = tune_rubrics.update_ats_match_yaml(yaml_path, thresholds)
            self.assertTrue(success)

            updated = yaml_path.read_text(encoding="utf-8")
            self.assertIn("excellent_match: 90", updated)
            self.assertIn("good_match: 75", updated)
            self.assertIn("weak_match: 55", updated)

            # Re-run with same thresholds (no adjustments needed)
            self.assertTrue(tune_rubrics.update_ats_match_yaml(yaml_path, thresholds))

    def test_load_applications_exceptions(self):
        """Test load_applications with non-float scores and read exceptions."""
        with tempfile.TemporaryDirectory() as tmpdir:
            md_path = Path(tmpdir) / "corrupt.md"
            md_path.write_text(
                "| 1 | 2026-08-01 | A | B | invalid/5 | status | p | l | r | n |\n| too | short |\n",
                encoding="utf-8",
            )
            apps = tune_rubrics.load_applications(md_path)
            self.assertEqual(len(apps), 1)
            self.assertIsNone(apps[0]["score"])

            with patch.object(Path, "open", side_effect=IOError("Read error")):
                res = tune_rubrics.load_applications(md_path)
                self.assertEqual(res, [])

    def test_find_jd_payload_corrupted_json(self):
        """Test find_jd_payload skips invalid JSON files cleanly."""
        with tempfile.TemporaryDirectory() as tmpdir:
            jds_dir = Path(tmpdir)
            (jds_dir / "bad.json").write_text("invalid json content", encoding="utf-8")
            self.assertIsNone(tune_rubrics.find_jd_payload(jds_dir, "Acme", "Dev"))

    def test_main_no_apply_flag_and_corrupt_yaml(self):
        """Test main without --apply flag and with corrupted yaml."""
        with tempfile.TemporaryDirectory() as tmpdir:
            data_dir = Path(tmpdir) / "data" / "morgan"
            data_dir.mkdir(parents=True)
            scoring_dir = Path(tmpdir) / "resume-engine" / "scoring"
            scoring_dir.mkdir(parents=True)

            yaml_file = scoring_dir / "ats_match.yaml"
            yaml_file.write_text("invalid: yaml: [", encoding="utf-8")
            md_path = data_dir / "applications.md"
            md_path.write_text(
                "| 1 | 2026-08-01 | Acme | Dev | 4.8/5 | Offer | a.pdf | l | r | n |\n",
                encoding="utf-8",
            )

            with patch.object(tune_rubrics, "PROJECT_ROOT", Path(tmpdir)):
                with patch("sys.argv", ["tune_rubrics.py"]):
                    tune_rubrics.main()

    def test_main_scenarios(self):
        """Test main across missing applications, empty applications, and valid telemetry."""
        with tempfile.TemporaryDirectory() as tmpdir:
            data_dir = Path(tmpdir) / "data" / "morgan"
            data_dir.mkdir(parents=True)
            scoring_dir = Path(tmpdir) / "resume-engine" / "scoring"
            scoring_dir.mkdir(parents=True)

            yaml_file = scoring_dir / "ats_match.yaml"
            yaml_file.write_text(
                "thresholds:\n  excellent_match: 85\n  good_match: 70\n  weak_match: 50\n",
                encoding="utf-8",
            )

            with patch.object(tune_rubrics, "PROJECT_ROOT", Path(tmpdir)):
                # Scenario 1: missing applications.md
                with patch("sys.argv", ["tune_rubrics.py"]):
                    with self.assertRaises(SystemExit):
                        tune_rubrics.main()

                # Scenario 2: empty applications.md
                md_path = data_dir / "applications.md"
                md_path.write_text("# Empty table\n", encoding="utf-8")
                with patch("sys.argv", ["tune_rubrics.py"]):
                    with self.assertRaises(SystemExit):
                        tune_rubrics.main()

                # Scenario 3: valid data with --apply
                md_path.write_text(
                    """# Applications
| # | Date | Company | Role | Score | Status | PDF | Link | Report | Notes |
|---|---|---|---|---|---|---|---|---|---|
| 1 | 2026-08-01 | Acme | Dev | 4.8/5 | Offer | a.pdf | l | r | n |
""",
                    encoding="utf-8",
                )

                with patch("sys.argv", ["tune_rubrics.py", "--apply"]):
                    tune_rubrics.main()
                    updated = yaml_file.read_text(encoding="utf-8")
                    self.assertIn("excellent_match:", updated)


if __name__ == "__main__":
    unittest.main()
