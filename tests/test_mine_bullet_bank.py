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
        # never make a pure top-K cut on similarity alone. The 5 Treering
        # vectors each share a 0.6 JD-aligned component (so all outrank
        # Mercor's orthogonal vector) but point in 5 different orthogonal
        # directions otherwise (pairwise cosine similarity 0.36, well under
        # DEDUP_SIMILARITY_THRESHOLD) -- distinct bullets shouldn't collide
        # with the dedup logic tested separately below.
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
            vec = [0.0] * 6
            vec[0] = 0.6
            vec[i + 1] = 0.8
            vectors.append(vec)
        rows.append({
            "Bullet Point": "Low relevance Mercor bullet",
            "Role / Company": "Mercor",
            "Tags": "content",
            "hidden_gem_score": 0,
            "strength_category": "Solid",
        })
        vectors.append([0.0, 1.0, 0.0, 0.0, 0.0, 0.0])  # orthogonal to the JD axis -- ranks last

        pd.DataFrame(rows).to_csv(os.path.join(self.tmp_dir, "bullet-bank-keepers-audited.csv"), index=False)
        np.save(os.path.join(self.tmp_dir, "bullet_vectors_ge2_d768.npy"), np.array(vectors, dtype=np.float32))

    def tearDown(self):
        self.engine.kb_dir = self._real_kb_dir
        shutil.rmtree(self.tmp_dir, ignore_errors=True)

    @patch("orchestrator.GeminiClient.embed", return_value=[1.0, 0.0, 0.0, 0.0, 0.0, 0.0])
    @patch("orchestrator.TOP_K_BULLETS", 5)
    def test_guarantees_minimum_bullets_for_a_low_scoring_company(self, mock_embed):
        with patch.dict(orchestrator.COMPANY_MIN_BULLETS, {"Mercor": 1, "Treering Yearbooks": 1}, clear=True):
            results = self.engine.mine_bullet_bank("some JD text", {})
        companies = [company for (_, company, _) in results]
        self.assertIn("Mercor", companies, "Mercor's guaranteed minimum should have surfaced it despite low similarity")

    @patch("orchestrator.GeminiClient.embed", return_value=[1.0, 0.0, 0.0, 0.0, 0.0, 0.0])
    @patch("orchestrator.TOP_K_BULLETS", 5)
    def test_without_guarantee_low_scoring_company_would_be_excluded(self, mock_embed):
        # Only 5 of 6 rows can be selected -- with no guarantee, the lowest-
        # scoring row (Mercor, orthogonal to the JD vector) is the one left out.
        with patch.dict(orchestrator.COMPANY_MIN_BULLETS, {}, clear=True):
            results = self.engine.mine_bullet_bank("some JD text", {})
        companies = [company for (_, company, _) in results]
        self.assertEqual(len(results), 5)
        self.assertNotIn("Mercor", companies)


class TestMineBulletBankDeduplication(unittest.TestCase):
    """
    A real run's Skills-guaranteed selection pulled several near-identical
    bullets about the same underlying achievement (e.g. multiple reworded
    "audited CRM data, recovered $3M" variants) into one company's slots.
    These tests build a fake bank with two near-duplicate high-scoring
    bullets plus one genuinely distinct bullet, and confirm mining picks
    at most one of the near-duplicates.
    """

    def setUp(self):
        self.engine = orchestrator.ResumeEngine()
        self.tmp_dir = os.path.join(os.path.dirname(__file__), "_tmp_bullet_bank_dedup")
        os.makedirs(self.tmp_dir, exist_ok=True)
        self._real_kb_dir = self.engine.kb_dir
        self.engine.kb_dir = self.tmp_dir

        rows = [
            {"Bullet Point": "Recovered $3M in pipeline via CRM audit", "Role / Company": "Treering Yearbooks",
             "Tags": "ops", "hidden_gem_score": 0, "strength_category": "Solid"},
            {"Bullet Point": "Recovered $3M in dormant pipeline through a CRM data audit", "Role / Company": "Treering Yearbooks",
             "Tags": "ops", "hidden_gem_score": 0, "strength_category": "Solid"},
            {"Bullet Point": "Founded the Content Committee to govern brand voice", "Role / Company": "Treering Yearbooks",
             "Tags": "mgmt", "hidden_gem_score": 0, "strength_category": "Solid"},
        ]
        # Rows 0 and 1 are near-duplicate vectors (cosine similarity > 0.99);
        # row 2 is orthogonal (genuinely distinct). The JD vector below is
        # aligned with row 0, so on pure relevance both near-duplicates would
        # outrank row 2.
        vectors = [
            [1.0, 0.0, 0.0],
            [1.0, 0.05, 0.0],
            [0.0, 1.0, 0.0],
        ]

        pd.DataFrame(rows).to_csv(os.path.join(self.tmp_dir, "bullet-bank-keepers-audited.csv"), index=False)
        np.save(os.path.join(self.tmp_dir, "bullet_vectors_ge2_d768.npy"), np.array(vectors, dtype=np.float32))

    def tearDown(self):
        self.engine.kb_dir = self._real_kb_dir
        shutil.rmtree(self.tmp_dir, ignore_errors=True)

    @patch("orchestrator.GeminiClient.embed", return_value=[1.0, 0.0, 0.0])
    def test_guaranteed_minimum_does_not_fill_with_near_duplicates(self, mock_embed):
        with patch.dict(orchestrator.COMPANY_MIN_BULLETS, {"Treering Yearbooks": 2}, clear=True):
            results = self.engine.mine_bullet_bank("some JD text", {})
        bullets = [b for (b, _, _) in results]
        self.assertIn("Recovered $3M in pipeline via CRM audit", bullets)
        self.assertIn("Founded the Content Committee to govern brand voice", bullets)
        self.assertNotIn("Recovered $3M in dormant pipeline through a CRM data audit", bullets)


if __name__ == "__main__":
    unittest.main()
