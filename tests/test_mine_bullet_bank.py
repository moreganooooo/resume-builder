import os
import shutil
import sys
import unittest
from unittest.mock import patch

import numpy as np
import pandas as pd

SCRIPTS_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts")
sys.path.insert(0, SCRIPTS_DIR)

import orchestrator  # noqa: E402


class TestMineBulletBankCompanyFloor(unittest.TestCase):
    """
    A real run mined 30 bullets and got 0 for Mercor and 0 for Callahan Creek,
    because pure global top-K ranking has no per-company floor. These tests
    build a small fake bank where one company's bullets all score low, and
    confirm the guaranteed-minimum logic still surfaces them.
    """

    def setUp(self):
        self.engine = orchestrator.ResumeEngine()
        self.tmp_dir = os.path.join(os.path.dirname(__file__), "_tmp_bullet_bank")
        os.makedirs(self.tmp_dir, exist_ok=True)
        self._real_kb_dir = self.engine.kb_dir
        self.engine.kb_dir = self.tmp_dir

        # 6 rows: 5 for a "high scoring" company, 1 for "Mercor" that would
        # never make a pure top-K cut on similarity alone.
        rows = []
        vectors = []
        for i in range(5):
            rows.append({
                "Bullet Point": f"High relevance bullet {i}",
                "Role / Company": "Treering Yearbooks",
                "Tags": "content",
                "hidden_gem_score": 0,
                "strength_category": "Solid",
            })
            vectors.append([1.0, 0.0])  # perfectly aligned with the JD vector below
        rows.append({
            "Bullet Point": "Low relevance Mercor bullet",
            "Role / Company": "Mercor",
            "Tags": "content",
            "hidden_gem_score": 0,
            "strength_category": "Solid",
        })
        vectors.append([0.0, 1.0])  # orthogonal -- would rank last on pure similarity

        pd.DataFrame(rows).to_csv(os.path.join(self.tmp_dir, "bullet-bank-keepers-audited.csv"), index=False)
        np.save(os.path.join(self.tmp_dir, "bullet_vectors_ge2_d768.npy"), np.array(vectors, dtype=np.float32))

    def tearDown(self):
        self.engine.kb_dir = self._real_kb_dir
        shutil.rmtree(self.tmp_dir, ignore_errors=True)

    @patch("orchestrator.GeminiClient.embed", return_value=[1.0, 0.0])
    @patch("orchestrator.TOP_K_BULLETS", 5)
    def test_guarantees_minimum_bullets_for_a_low_scoring_company(self, mock_embed):
        with patch.dict(orchestrator.COMPANY_MIN_BULLETS, {"Mercor": 1, "Treering Yearbooks": 1}, clear=True):
            results = self.engine.mine_bullet_bank("some JD text", {})
        companies = [company for (_, company, _) in results]
        self.assertIn("Mercor", companies, "Mercor's guaranteed minimum should have surfaced it despite low similarity")

    @patch("orchestrator.GeminiClient.embed", return_value=[1.0, 0.0])
    @patch("orchestrator.TOP_K_BULLETS", 5)
    def test_without_guarantee_low_scoring_company_would_be_excluded(self, mock_embed):
        # Only 5 of 6 rows can be selected -- with no guarantee, the lowest-
        # scoring row (Mercor, orthogonal to the JD vector) is the one left out.
        with patch.dict(orchestrator.COMPANY_MIN_BULLETS, {}, clear=True):
            results = self.engine.mine_bullet_bank("some JD text", {})
        companies = [company for (_, company, _) in results]
        self.assertEqual(len(results), 5)
        self.assertNotIn("Mercor", companies)


if __name__ == "__main__":
    unittest.main()
