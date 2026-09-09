"""Tests for scripts/clear_stale_skill_matrices.py."""

import json
import os
import shutil
import sys
import tempfile
import unittest
from unittest.mock import patch

SCRIPTS_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts"
)
sys.path.insert(0, SCRIPTS_DIR)

import clear_stale_skill_matrices as csm  # noqa: E402
import jd_manager  # noqa: E402
import profile_paths  # noqa: E402


class TestIsFlat(unittest.TestCase):
    def test_empty_matrix_is_not_flat(self):
        self.assertFalse(csm._is_flat([]))

    def test_all_zero_coverage_is_flat(self):
        self.assertTrue(
            csm._is_flat([{"skill": "a", "coverage": 0}, {"skill": "b", "coverage": 0}])
        )

    def test_any_nonzero_coverage_is_not_flat(self):
        self.assertFalse(
            csm._is_flat(
                [{"skill": "a", "coverage": 0}, {"skill": "b", "coverage": 41.2}]
            )
        )


class TestFindAndClear(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.iso_cm = profile_paths.isolate_for_tests(self.tmp)
        self.iso_cm.__enter__()

        self.profile = "testcsm"
        os.environ["RESUME_PROFILE"] = self.profile
        self.profile_dir = profile_paths.profile_root(self.profile)
        os.makedirs(self.profile_dir, exist_ok=True)
        self.jds_dir = profile_paths.jds_dir(self.profile)
        os.makedirs(self.jds_dir, exist_ok=True)

        # jd_manager resolves these directories once at import time -- see
        # the identical note in test_find_retroactively_excluded_roles.py.
        for attr, value in (
            ("JDS_DIR", self.jds_dir),
            ("COMPLETED_DIR", os.path.join(self.jds_dir, "completed")),
            ("ARCHIVED_DIR", os.path.join(self.jds_dir, "archived")),
            ("TRACKER_CSV", os.path.join(self.jds_dir, "jd_tracker_log.csv")),
        ):
            patcher = patch.object(jd_manager, attr, value)
            patcher.start()
            self.addCleanup(patcher.stop)

    def tearDown(self):
        self.iso_cm.__exit__(None, None, None)
        shutil.rmtree(self.tmp, ignore_errors=True)
        os.environ.pop("RESUME_PROFILE", None)

    def _write_jd(self, filename: str, payload: dict) -> str:
        path = os.path.join(self.jds_dir, filename)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(payload, f)
        return path

    def test_find_flat_matrices_flags_only_flat_ones(self):
        self._write_jd(
            "flat.json",
            {
                "job_title": "Flat Role",
                "company_name": "Acme",
                "_evaluation": {
                    "recommendation": "Pursue",
                    "composite_score": 3.5,
                    "skill_matrix": [{"skill": "Salesforce", "coverage": 0}],
                },
            },
        )
        self._write_jd(
            "healthy.json",
            {
                "job_title": "Healthy Role",
                "company_name": "Beta",
                "_evaluation": {
                    "recommendation": "Pursue",
                    "composite_score": 4.0,
                    "skill_matrix": [{"skill": "SQL", "coverage": 62.0}],
                },
            },
        )
        self._write_jd(
            "no_matrix.json",
            {
                "job_title": "No Matrix Yet",
                "company_name": "Gamma",
                "_evaluation": {
                    "recommendation": "Pursue",
                    "composite_score": 4.0,
                    "skill_matrix": [],
                },
            },
        )

        findings = csm.find_flat_matrices()
        titles = {f["title"] for f in findings}
        self.assertEqual(titles, {"Flat Role"})

    def test_find_all_matrices_flags_any_nonempty_matrix(self):
        self._write_jd(
            "flat.json",
            {
                "job_title": "Flat Role",
                "company_name": "Acme",
                "_evaluation": {
                    "recommendation": "Pursue",
                    "composite_score": 3.5,
                    "skill_matrix": [{"skill": "Salesforce", "coverage": 0}],
                },
            },
        )
        self._write_jd(
            "healthy.json",
            {
                "job_title": "Healthy Role",
                "company_name": "Beta",
                "_evaluation": {
                    "recommendation": "Pursue",
                    "composite_score": 4.0,
                    "skill_matrix": [{"skill": "SQL", "coverage": 62.0}],
                },
            },
        )
        self._write_jd(
            "no_matrix.json",
            {
                "job_title": "No Matrix Yet",
                "company_name": "Gamma",
                "_evaluation": {
                    "recommendation": "Pursue",
                    "composite_score": 4.0,
                    "skill_matrix": [],
                },
            },
        )

        findings = csm.find_all_matrices()
        titles = {f["title"] for f in findings}
        self.assertEqual(titles, {"Flat Role", "Healthy Role"})

    def test_clear_matrix_empties_skill_matrix_field(self):
        path = self._write_jd(
            "flat.json",
            {
                "job_title": "Flat Role",
                "company_name": "Acme",
                "_evaluation": {
                    "recommendation": "Pursue",
                    "composite_score": 3.5,
                    "skill_matrix": [{"skill": "Salesforce", "coverage": 0}],
                },
            },
        )

        csm.clear_matrix(path, self.profile)

        evaluation = jd_manager.read_evaluation(path)
        self.assertEqual(evaluation["skill_matrix"], [])


if __name__ == "__main__":
    unittest.main()
