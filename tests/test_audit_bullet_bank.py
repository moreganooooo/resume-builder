"""Unit tests for scripts/audit_bullet_bank.py."""

import json
import os
import sys
import tempfile
import unittest
from unittest.mock import MagicMock, patch

import pandas as pd

SCRIPTS_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts"
)
if SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, SCRIPTS_DIR)

import audit_bullet_bank  # noqa: E402


class TestAuditBulletBank(unittest.TestCase):
    """Test suite for audit_bullet_bank module."""

    def test_detect_bullet_col(self):
        """Test bullet column detection helper."""
        self.assertEqual(
            audit_bullet_bank.detect_bullet_col(["bullet", "other"]), "bullet"
        )
        self.assertEqual(
            audit_bullet_bank.detect_bullet_col(["achievement", "other"]), "achievement"
        )
        self.assertEqual(
            audit_bullet_bank.detect_bullet_col(["Bullet Point", "other"]),
            "Bullet Point",
        )
        self.assertIsNone(audit_bullet_bank.detect_bullet_col(["unknown", "other"]))

    def test_run_audit_missing_input(self):
        """Test run_audit when input CSV does not exist."""
        results = audit_bullet_bank.run_audit(
            csv_path="/nonexistent/clean.csv", out_path="/tmp/out.csv"
        )
        self.assertEqual(results, [])

    @patch("audit_bullet_bank.GeminiClient.generate")
    @patch("audit_bullet_bank.GeminiClient.parse_json")
    @patch("audit_bullet_bank.ResumeEngine")
    def test_run_audit_success_and_resume(
        self, mock_engine_cls, mock_parse_json, mock_generate
    ):
        """Test successful execution of run_audit including resume from checkpoint."""
        mock_engine = MagicMock()
        mock_engine.load_prompt.return_value = "Critique Prompt"
        mock_engine.load_yaml.return_value = {"rules": "mock"}
        mock_engine.scoring_dir = "/tmp"
        mock_engine.rules_dir = "/tmp"
        mock_engine_cls.return_value = mock_engine

        mock_generate.return_value = ("{}", MagicMock())
        mock_parse_json.return_value = {
            "accuracy_score": 95,
            "believability_score": 90,
            "clarity_score": 92,
            "ats_value": 85,
            "manager_test": "PASS",
            "weaknesses": "None",
        }

        with tempfile.TemporaryDirectory() as tmpdir:
            csv_path = os.path.join(tmpdir, "bullet-bank-clean.csv")
            out_path = os.path.join(tmpdir, "bullet-bank-audited.csv")

            df = pd.DataFrame(
                [
                    {
                        "Bullet Point": "Grew revenue by 35% through SEO campaigns",
                        "Role / Company": "Marketing Lead / TechCorp",
                    },
                    {
                        "Bullet Point": "Led cross-functional team of 10 engineers",
                        "Role / Company": "Engineering Manager / Startup",
                    },
                ]
            )
            df.to_csv(csv_path, index=False)

            results = audit_bullet_bank.run_audit(
                csv_path=csv_path, out_path=out_path, sleep_seconds=0
            )
            self.assertEqual(len(results), 2)
            self.assertEqual(results[0]["manager_test"], "PASS")
            self.assertTrue(os.path.exists(out_path))

            # Test resuming when checkpoint exists
            results_resumed = audit_bullet_bank.run_audit(
                csv_path=csv_path, out_path=out_path, sleep_seconds=0
            )
            self.assertEqual(len(results_resumed), 2)

    @patch("audit_bullet_bank.GeminiClient.generate")
    @patch("audit_bullet_bank.ResumeEngine")
    def test_run_audit_api_error_handling(self, mock_engine_cls, mock_generate):
        """Test audit handles Gemini API exceptions gracefully with ERROR marker."""
        mock_engine = MagicMock()
        mock_engine.load_prompt.return_value = "Critique Prompt"
        mock_engine.load_yaml.return_value = {}
        mock_engine.scoring_dir = "/tmp"
        mock_engine.rules_dir = "/tmp"
        mock_engine_cls.return_value = mock_engine

        mock_generate.side_effect = RuntimeError("API Rate Limit")

        with tempfile.TemporaryDirectory() as tmpdir:
            csv_path = os.path.join(tmpdir, "bullet-bank-clean.csv")
            out_path = os.path.join(tmpdir, "bullet-bank-audited.csv")

            df = pd.DataFrame(
                [
                    {
                        "Bullet Point": "Created dashboard UI",
                        "Role / Company": "Dev / Corp",
                    }
                ]
            )
            df.to_csv(csv_path, index=False)

            results = audit_bullet_bank.run_audit(
                csv_path=csv_path, out_path=out_path, sleep_seconds=0
            )
            self.assertEqual(len(results), 1)
            self.assertEqual(results[0]["manager_test"], "ERROR")
            self.assertIn("[AUDIT_ERROR]", results[0]["weaknesses"])

    @patch("audit_bullet_bank.GeminiClient.generate")
    @patch("audit_bullet_bank.ResumeEngine")
    def test_run_audit_corrupted_checkpoint_warning(
        self, mock_engine_cls, mock_generate
    ):
        """Test checkpoint with missing bullet column triggers warning and proceeds."""
        mock_engine = MagicMock()
        mock_engine.load_prompt.return_value = "Critique Prompt"
        mock_engine.load_yaml.return_value = {}
        mock_engine.scoring_dir = "/tmp"
        mock_engine.rules_dir = "/tmp"
        mock_engine_cls.return_value = mock_engine

        mock_generate.return_value = (
            '{"accuracy_score": 90, "believability_score": 90, "clarity_score": 90, "ats_value": 90, "manager_test": "PASS", "weaknesses": ""}',
            MagicMock(),
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            csv_path = os.path.join(tmpdir, "bullet-bank-clean.csv")
            out_path = os.path.join(tmpdir, "bullet-bank-audited.csv")

            pd.DataFrame([{"bullet": "Built feature X"}]).to_csv(csv_path, index=False)
            # Corrupted checkpoint missing bullet column
            pd.DataFrame([{"invalid_col": 123}]).to_csv(out_path, index=False)

            with patch("time.sleep") as mock_sleep:
                results = audit_bullet_bank.run_audit(
                    csv_path=csv_path, out_path=out_path, sleep_seconds=1
                )
                self.assertEqual(len(results), 1)
                mock_sleep.assert_not_called()  # single item, loop doesn't sleep at end

    @patch("audit_bullet_bank.GeminiClient.generate")
    @patch("audit_bullet_bank.ResumeEngine")
    def test_run_audit_sleep_multiple_items(self, mock_engine_cls, mock_generate):
        """Test time.sleep is called between items when multiple rows exist."""
        mock_engine = MagicMock()
        mock_engine.load_prompt.return_value = "Critique Prompt"
        mock_engine.load_yaml.return_value = {}
        mock_engine.scoring_dir = "/tmp"
        mock_engine.rules_dir = "/tmp"
        mock_engine_cls.return_value = mock_engine

        mock_generate.return_value = ('{"manager_test": "PASS"}', MagicMock())

        with tempfile.TemporaryDirectory() as tmpdir:
            csv_path = os.path.join(tmpdir, "bullet-bank-clean.csv")
            out_path = os.path.join(tmpdir, "bullet-bank-audited.csv")

            pd.DataFrame([{"achievement": "Item 1"}, {"achievement": "Item 2"}]).to_csv(
                csv_path, index=False
            )

            with patch("time.sleep") as mock_sleep:
                results = audit_bullet_bank.run_audit(
                    csv_path=csv_path, out_path=out_path, sleep_seconds=2
                )
                self.assertEqual(len(results), 2)
                mock_sleep.assert_called_once_with(2)

    @patch("audit_bullet_bank.run_audit")
    def test_main(self, mock_run_audit):
        """Test main entrypoint."""
        audit_bullet_bank.main()
        mock_run_audit.assert_called_once()


if __name__ == "__main__":
    unittest.main()
