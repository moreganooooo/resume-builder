import json
import os
import shutil
import sys
import unittest
from unittest.mock import patch

import numpy as np
import pandas as pd
import yaml

SCRIPTS_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts"
)
sys.path.insert(0, SCRIPTS_DIR)

import orchestrator  # noqa: E402
import validate_resume  # noqa: E402
from bullet_bank_hash import bullets_sha  # noqa: E402


def _write_matching_meta(tmp_dir: str, rows: list) -> None:
    """B20 (phase-9-backlog.md): mine_bullet_bank() now requires the .npy's
    .meta sidecar to carry a bullets_sha matching the CSV's current content
    -- write one here so these fixtures (built before that check existed)
    still exercise the selection logic these tests are actually about."""
    with open(os.path.join(tmp_dir, "bullet_vectors_ge2_d768.meta"), "w") as f:
        json.dump({"bullets_sha": bullets_sha([r["Bullet Point"] for r in rows])}, f)


def _write_profile_roles(tmp_dir: str, roles: list) -> None:
    """mine_bullet_bank now reads its per-company minimums from
    profile.yml's roles: (min_bullets), not a module constant -- write a
    minimal profile.yml into the test's fake kb_dir to match."""
    with open(os.path.join(tmp_dir, "profile.yml"), "w") as f:
        yaml.safe_dump({"roles": roles}, f)


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
            rows.append(
                {
                    # Distinct opening verbs on purpose. These 5 all began with
                    # "High", which mine_bullet_bank's uniqueness-aware selection
                    # now reads as an opening-verb collision -- it would defer 4 of
                    # them and surface Mercor for a reason that has nothing to do
                    # with the per-company floor these tests are isolating.
                    "Bullet Point": f"{['Achieved', 'Built', 'Created', 'Drove', 'Executed'][i]} relevance bullet {i}",
                    "Role / Company": "Treering Yearbooks",
                    "Tags": "content",
                    "hidden_gem_score": 0,
                    "strength_category": "Solid",
                }
            )
            vec = [0.0] * 6
            vec[0] = 0.6
            vec[i + 1] = 0.8
            vectors.append(vec)
        rows.append(
            {
                "Bullet Point": "Low relevance Mercor bullet",
                "Role / Company": "Mercor",
                "Tags": "content",
                "hidden_gem_score": 0,
                "strength_category": "Solid",
            }
        )
        vectors.append(
            [0.0, 1.0, 0.0, 0.0, 0.0, 0.0]
        )  # orthogonal to the JD axis -- ranks last

        pd.DataFrame(rows).to_csv(
            os.path.join(self.tmp_dir, "bullet-bank-keepers-audited.csv"), index=False
        )
        np.save(
            os.path.join(self.tmp_dir, "bullet_vectors_ge2_d768.npy"),
            np.array(vectors, dtype=np.float32),
        )
        _write_matching_meta(self.tmp_dir, rows)

    def tearDown(self):
        self.engine.kb_dir = self._real_kb_dir
        shutil.rmtree(self.tmp_dir, ignore_errors=True)

    @patch(
        "orchestrator.GeminiClient.embed", return_value=[1.0, 0.0, 0.0, 0.0, 0.0, 0.0]
    )
    @patch("orchestrator.TOP_K_BULLETS", 5)
    def test_guarantees_minimum_bullets_for_a_low_scoring_company(self, mock_embed):
        _write_profile_roles(
            self.tmp_dir,
            [
                {"name": "Mercor", "min_bullets": 1},
                {"name": "Treering Yearbooks", "min_bullets": 1},
            ],
        )
        results = self.engine.mine_bullet_bank("some JD text", {})
        companies = [company for (_, company, _) in results]
        self.assertIn(
            "Mercor",
            companies,
            "Mercor's guaranteed minimum should have surfaced it despite low similarity",
        )

    @patch(
        "orchestrator.GeminiClient.embed", return_value=[1.0, 0.0, 0.0, 0.0, 0.0, 0.0]
    )
    @patch("orchestrator.TOP_K_BULLETS", 5)
    def test_without_guarantee_low_scoring_company_would_be_excluded(self, mock_embed):
        # Only 5 of 6 rows can be selected -- with no guarantee, the lowest-
        # scoring row (Mercor, orthogonal to the JD vector) is the one left out.
        _write_profile_roles(self.tmp_dir, [])
        results = self.engine.mine_bullet_bank("some JD text", {})
        companies = [company for (_, company, _) in results]
        self.assertEqual(len(results), 5)
        self.assertNotIn("Mercor", companies)


class TestMineBulletBankUniqueness(unittest.TestCase):
    """Whole-CV uniqueness (duplicate metrics, duplicate opening verbs) is
    enforced at selection rather than left to the builder's validator-retry
    loop: a pool mined to exactly each role's minimum has no slack, so the
    model can only reword pre-audited bullets, which burns all 4 attempts.
    Measured on the real 844-bullet bank, this took a 30-bullet pool from
    21 excess collisions to 0."""

    def setUp(self):
        self.engine = orchestrator.ResumeEngine()
        self.tmp_dir = os.path.join(os.path.dirname(__file__), "_tmp_bullet_bank_uniq")
        os.makedirs(self.tmp_dir, exist_ok=True)
        self._real_kb_dir = self.engine.kb_dir
        self.engine.kb_dir = self.tmp_dir

        # Two colliding pairs plus clean alternates, all for one company and
        # all mutually distinct in embedding space (so the near-duplicate
        # filter stays out of it and only uniqueness decides).
        rows = [
            {"Bullet Point": "Drove 41% reply rates across the PTA sequence rebuild"},
            {"Bullet Point": "Sustained 41% reply rates on the PTA sequence program"},
            {"Bullet Point": "Drove pipeline hygiene across the district CRM records"},
            {"Bullet Point": "Rebuilt onboarding docs for the regional support team"},
        ]
        vectors = []
        for i, r in enumerate(rows):
            r.update(
                {
                    "Role / Company": "Treering Yearbooks",
                    "Tags": "ops",
                    "hidden_gem_score": 0,
                    "strength_category": "Solid",
                }
            )
            vec = [0.0] * 6
            vec[0], vec[i + 1] = 0.6, 0.8
            vectors.append(vec)

        pd.DataFrame(rows).to_csv(
            os.path.join(self.tmp_dir, "bullet-bank-keepers-audited.csv"), index=False
        )
        np.save(
            os.path.join(self.tmp_dir, "bullet_vectors_ge2_d768.npy"),
            np.array(vectors, dtype=np.float32),
        )
        _write_matching_meta(self.tmp_dir, rows)
        _write_profile_roles(self.tmp_dir, [])

    def tearDown(self):
        self.engine.kb_dir = self._real_kb_dir
        shutil.rmtree(self.tmp_dir, ignore_errors=True)

    @patch(
        "orchestrator.GeminiClient.embed", return_value=[1.0, 0.0, 0.0, 0.0, 0.0, 0.0]
    )
    @patch("orchestrator.TOP_K_BULLETS", 2)
    def test_prefers_a_collision_free_pair(self, mock_embed):
        picked = [b for (b, _c, _t) in self.engine.mine_bullet_bank("jd", {})]
        sigs, verbs = [], []
        for b in picked:
            s, v = validate_resume.uniqueness_keys(b)
            sigs.extend(s)
            verbs.append(v)
        self.assertEqual(len(sigs), len(set(sigs)), f"duplicate metric across {picked}")
        self.assertEqual(
            len(verbs), len(set(verbs)), f"duplicate opening verb across {picked}"
        )

    @patch(
        "orchestrator.GeminiClient.embed", return_value=[1.0, 0.0, 0.0, 0.0, 0.0, 0.0]
    )
    @patch("orchestrator.TOP_K_BULLETS", 4)
    def test_still_fills_the_pool_when_collisions_are_unavoidable(self, mock_embed):
        # Uniqueness is best-effort: starving the builder of material is worse
        # than a duplicate the retry loop still gets a shot at.
        self.assertEqual(len(self.engine.mine_bullet_bank("jd", {})), 4)


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
            {
                "Bullet Point": "Recovered $3M in pipeline via CRM audit",
                "Role / Company": "Treering Yearbooks",
                "Tags": "ops",
                "hidden_gem_score": 0,
                "strength_category": "Solid",
            },
            {
                "Bullet Point": "Recovered $3M in dormant pipeline through a CRM data audit",
                "Role / Company": "Treering Yearbooks",
                "Tags": "ops",
                "hidden_gem_score": 0,
                "strength_category": "Solid",
            },
            {
                "Bullet Point": "Founded the Content Committee to govern brand voice",
                "Role / Company": "Treering Yearbooks",
                "Tags": "mgmt",
                "hidden_gem_score": 0,
                "strength_category": "Solid",
            },
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

        pd.DataFrame(rows).to_csv(
            os.path.join(self.tmp_dir, "bullet-bank-keepers-audited.csv"), index=False
        )
        np.save(
            os.path.join(self.tmp_dir, "bullet_vectors_ge2_d768.npy"),
            np.array(vectors, dtype=np.float32),
        )
        _write_matching_meta(self.tmp_dir, rows)

    def tearDown(self):
        self.engine.kb_dir = self._real_kb_dir
        shutil.rmtree(self.tmp_dir, ignore_errors=True)

    @patch("orchestrator.GeminiClient.embed", return_value=[1.0, 0.0, 0.0])
    def test_guaranteed_minimum_does_not_fill_with_near_duplicates(self, mock_embed):
        _write_profile_roles(
            self.tmp_dir, [{"name": "Treering Yearbooks", "min_bullets": 2}]
        )
        results = self.engine.mine_bullet_bank("some JD text", {})
        bullets = [b for (b, _, _) in results]
        self.assertIn("Recovered $3M in pipeline via CRM audit", bullets)
        self.assertIn("Founded the Content Committee to govern brand voice", bullets)
        self.assertNotIn(
            "Recovered $3M in dormant pipeline through a CRM data audit", bullets
        )


class TestMineBulletBankStaleEmbeddingsGuard(unittest.TestCase):
    """B20 (phase-9-backlog.md): a same-length row-count check can't catch a
    bank whose content changed since embedding (e.g. edited during a
    rate-limit pause) -- only a content hash in the .meta sidecar can. These
    confirm mine_bullet_bank() enforces it at read time."""

    def setUp(self):
        self.engine = orchestrator.ResumeEngine()
        self.tmp_dir = os.path.join(os.path.dirname(__file__), "_tmp_bullet_bank_stale")
        os.makedirs(self.tmp_dir, exist_ok=True)
        self._real_kb_dir = self.engine.kb_dir
        self.engine.kb_dir = self.tmp_dir

        self.rows = [
            {
                "Bullet Point": "Recovered $3M in pipeline via CRM audit",
                "Role / Company": "Treering Yearbooks",
                "Tags": "ops",
                "hidden_gem_score": 0,
                "strength_category": "Solid",
            },
            {
                "Bullet Point": "Founded the Content Committee to govern brand voice",
                "Role / Company": "Treering Yearbooks",
                "Tags": "mgmt",
                "hidden_gem_score": 0,
                "strength_category": "Solid",
            },
        ]
        vectors = [[1.0, 0.0], [0.0, 1.0]]
        pd.DataFrame(self.rows).to_csv(
            os.path.join(self.tmp_dir, "bullet-bank-keepers-audited.csv"), index=False
        )
        np.save(
            os.path.join(self.tmp_dir, "bullet_vectors_ge2_d768.npy"),
            np.array(vectors, dtype=np.float32),
        )
        _write_profile_roles(self.tmp_dir, [])

    def tearDown(self):
        self.engine.kb_dir = self._real_kb_dir
        shutil.rmtree(self.tmp_dir, ignore_errors=True)

    @patch("orchestrator.GeminiClient.embed", return_value=[1.0, 0.0])
    def test_missing_meta_skips_mining_rather_than_using_unverified_embeddings(
        self, mock_embed
    ):
        # No .meta sidecar written at all -- same class of risk as a stale
        # one: the .npy's alignment with the CSV can't be verified.
        results = self.engine.mine_bullet_bank("some JD text", {})
        self.assertEqual(results, [])

    @patch("orchestrator.GeminiClient.embed", return_value=[1.0, 0.0])
    def test_meta_hash_mismatch_skips_mining_even_with_matching_row_count(
        self, mock_embed
    ):
        # Same row count as when embedded, but the bullet text itself
        # changed since -- the row-count check alone would miss this.
        with open(os.path.join(self.tmp_dir, "bullet_vectors_ge2_d768.meta"), "w") as f:
            json.dump(
                {"bullets_sha": "stale-hash-from-a-previous-version-of-the-bank"}, f
            )
        results = self.engine.mine_bullet_bank("some JD text", {})
        self.assertEqual(results, [])

    @patch("orchestrator.GeminiClient.embed", return_value=[1.0, 0.0])
    def test_matching_meta_hash_allows_mining(self, mock_embed):
        _write_matching_meta(self.tmp_dir, self.rows)
        results = self.engine.mine_bullet_bank("some JD text", {})
        self.assertEqual(len(results), 2)


if __name__ == "__main__":
    unittest.main()
