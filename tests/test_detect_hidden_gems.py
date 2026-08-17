"""Unit tests for scripts/detect_hidden_gems.py."""

import os
import sys
import tempfile
import unittest
from unittest.mock import patch

import pandas as pd

SCRIPTS_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts"
)
if SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, SCRIPTS_DIR)

import detect_hidden_gems  # noqa: E402


class TestDetectHiddenGems(unittest.TestCase):
    """Test suite for detect_hidden_gems module."""

    def test_main_keepers_csv_not_found(self):
        """Test main behavior when KEEPERS_CSV does not exist."""
        with tempfile.TemporaryDirectory() as tmpdir:
            fake_keepers = os.path.join(tmpdir, "bullet-bank-keepers.csv")
            with patch.object(detect_hidden_gems, "KEEPERS_CSV", fake_keepers):
                detect_hidden_gems.main()

    def test_main_no_gems_found(self):
        """Test main behavior when keeper bullets exist but none qualify as gems."""
        with tempfile.TemporaryDirectory() as tmpdir:
            keepers_csv = os.path.join(tmpdir, "bullet-bank-keepers.csv")
            gems_csv = os.path.join(tmpdir, "hidden-gems.csv")

            df = pd.DataFrame(
                [
                    {
                        "Bullet Point": "Basic routine task",
                        "hidden_gem_score": 60,
                        "hidden_gem_flag": False,
                        "accuracy_score": 70,
                        "believability_score": 75,
                    }
                ]
            )
            df.to_csv(keepers_csv, index=False)

            with patch.object(detect_hidden_gems, "KEEPERS_CSV", keepers_csv):
                with patch.object(detect_hidden_gems, "GEMS_CSV", gems_csv):
                    detect_hidden_gems.main()
                    self.assertFalse(os.path.exists(gems_csv))

    def test_main_gem_detection_criteria(self):
        """Test gem filtering across score >= 90, flag == True, and high accuracy+believability."""
        with tempfile.TemporaryDirectory() as tmpdir:
            keepers_csv = os.path.join(tmpdir, "bullet-bank-keepers.csv")
            gems_csv = os.path.join(tmpdir, "hidden-gems.csv")

            df = pd.DataFrame(
                [
                    {
                        "CustomText": "Gem via high score",
                        "hidden_gem_score": 95,
                        "hidden_gem_flag": False,
                        "hidden_gem_reason": "Exceptional leadership metric",
                        "accuracy_score": 80,
                        "believability_score": 80,
                    },
                    {
                        "CustomText": "Gem via flag",
                        "hidden_gem_score": 85,
                        "hidden_gem_flag": "True",
                        "hidden_gem_reason": "High impact initiative",
                        "accuracy_score": 80,
                        "believability_score": 80,
                    },
                    {
                        "CustomText": "Gem via dual high accuracy + believability",
                        "hidden_gem_score": 80,
                        "hidden_gem_flag": False,
                        "hidden_gem_reason": "",
                        "accuracy_score": 95,
                        "believability_score": 92,
                    },
                    {
                        "CustomText": "Non-gem bullet",
                        "hidden_gem_score": 70,
                        "hidden_gem_flag": False,
                        "hidden_gem_reason": "",
                        "accuracy_score": 85,
                        "believability_score": 85,
                    },
                ]
            )
            df.to_csv(keepers_csv, index=False)

            with patch.object(detect_hidden_gems, "KEEPERS_CSV", keepers_csv):
                with patch.object(detect_hidden_gems, "GEMS_CSV", gems_csv):
                    detect_hidden_gems.main()
                    self.assertTrue(os.path.exists(gems_csv))
                    result_df = pd.read_csv(gems_csv)
                    self.assertEqual(len(result_df), 3)


if __name__ == "__main__":
    unittest.main()
