"""Tests for scripts/find_retroactively_excluded_roles.py."""

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

import find_retroactively_excluded_roles as fre  # noqa: E402
import jd_manager  # noqa: E402
import profile_paths  # noqa: E402


class TestCheckGates(unittest.TestCase):
    """check_gates() re-runs the scan_boards deterministic gates -- these
    tests exercise the pass-through against a stub scan_filters.yml config
    without needing a real profile on disk."""

    def test_no_filters_configured_passes_everything(self):
        with patch.object(fre.scan_boards, "_load_filters", return_value={}):
            self.assertEqual(fre.check_gates({"description": "anything"}), [])

    def test_employment_type_gate_fails_when_configured_and_mismatched(self):
        filters = {"employment_type": ["full_time"]}
        with patch.object(fre.scan_boards, "_load_filters", return_value=filters):
            failed = fre.check_gates({"employment_type": "Contract", "description": ""})
        self.assertIn("employment_type", failed)

    def test_employment_type_gate_passes_when_stated_type_matches(self):
        filters = {"employment_type": ["full_time"]}
        with patch.object(fre.scan_boards, "_load_filters", return_value=filters):
            failed = fre.check_gates(
                {"employment_type": "Full-time", "description": ""}
            )
        self.assertNotIn("employment_type", failed)

    def test_unstated_field_never_fails_a_gate(self):
        filters = {"employment_type": ["full_time"], "location": {}}
        with patch.object(fre.scan_boards, "_load_filters", return_value=filters):
            failed = fre.check_gates({"description": ""})
        self.assertEqual(failed, [])


class TestCheckScore(unittest.TestCase):
    def test_empty_evaluation_never_flags(self):
        self.assertFalse(fre.check_score({}, "", {}))

    def test_recommendation_skip_after_rescore_flags(self):
        evaluation = {
            "fit_subscores": {},
            "interview_odds_subscores": {},
            "practical_pursue_subscores": {},
            "hard_blockers": [
                {"text": "Requires active security clearance", "category": "other"}
            ],
        }
        self.assertTrue(fre.check_score(evaluation, "", {}))

    def test_no_disqualifying_blockers_does_not_flag_on_gates_alone(self):
        evaluation = {
            "fit_subscores": {"role_alignment": 5, "level_plausibility": 5},
            "interview_odds_subscores": {"company_responsiveness": 5},
            "practical_pursue_subscores": {"remote_quality": 5},
            "hard_blockers": [],
        }
        self.assertFalse(fre.check_score(evaluation, "", {}))


class TestFindCandidatesAndApply(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.iso_cm = profile_paths.isolate_for_tests(self.tmp)
        self.iso_cm.__enter__()

        self.profile = "testfre"
        os.environ["RESUME_PROFILE"] = self.profile
        self.profile_dir = profile_paths.profile_root(self.profile)
        os.makedirs(self.profile_dir, exist_ok=True)
        self.jds_dir = profile_paths.jds_dir(self.profile)
        os.makedirs(self.jds_dir, exist_ok=True)

        # jd_manager resolves JDS_DIR/ARCHIVED_DIR/TRACKER_CSV once at
        # import time, so isolate_for_tests alone (which only redirects
        # profile_paths' own module constants) doesn't reach code that
        # already imported jd_manager -- same class of bug as the
        # JDTracker/TRACKER_CSV drift documented in CLAUDE.md. Patch the
        # module attributes directly instead.
        jd_manager_patcher_dir = patch.object(jd_manager, "JDS_DIR", self.jds_dir)
        jd_manager_patcher_dir.start()
        self.addCleanup(jd_manager_patcher_dir.stop)
        jd_manager_patcher_completed = patch.object(
            jd_manager, "COMPLETED_DIR", os.path.join(self.jds_dir, "completed")
        )
        jd_manager_patcher_completed.start()
        self.addCleanup(jd_manager_patcher_completed.stop)
        jd_manager_patcher_archived = patch.object(
            jd_manager, "ARCHIVED_DIR", os.path.join(self.jds_dir, "archived")
        )
        jd_manager_patcher_archived.start()
        self.addCleanup(jd_manager_patcher_archived.stop)
        jd_manager_patcher_tracker = patch.object(
            jd_manager,
            "TRACKER_CSV",
            os.path.join(self.jds_dir, "jd_tracker_log.csv"),
        )
        jd_manager_patcher_tracker.start()
        self.addCleanup(jd_manager_patcher_tracker.stop)

        import db

        self.db_path = os.path.join(self.profile_dir, "data.db")
        import sqlite3

        conn = sqlite3.connect(self.db_path)
        db.init_db(conn)
        conn.commit()
        conn.close()

    def tearDown(self):
        self.iso_cm.__exit__(None, None, None)
        shutil.rmtree(self.tmp, ignore_errors=True)
        os.environ.pop("RESUME_PROFILE", None)

    def _write_pending_jd(self, filename: str, payload: dict) -> str:
        path = os.path.join(self.jds_dir, filename)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(payload, f)
        return path

    def test_find_candidates_flags_gate_and_score_failures_only(self):
        clean = {
            "job_title": "Engineer",
            "company_name": "Acme",
            "description": "Great role.",
            "employment_type": "Full-time",
            "_evaluation": {
                "recommendation": "Pursue",
                "composite_score": 4.2,
                "fit_subscores": {"role_alignment": 5},
                "interview_odds_subscores": {"company_responsiveness": 4},
                "practical_pursue_subscores": {"remote_quality": 5},
                "hard_blockers": [],
            },
        }
        flagged = {
            "job_title": "Contractor",
            "company_name": "Beta",
            "description": "Fixed-term contract role.",
            "employment_type": "Contract",
            "_evaluation": {
                "recommendation": "Pursue",
                "composite_score": 3.8,
                "fit_subscores": {"role_alignment": 4},
                "interview_odds_subscores": {"company_responsiveness": 3},
                "practical_pursue_subscores": {"remote_quality": 4},
                "hard_blockers": [],
            },
        }
        self._write_pending_jd("clean.json", clean)
        self._write_pending_jd("flagged.json", flagged)

        filters = {"employment_type": ["full_time"]}
        with patch.object(fre.scan_boards, "_load_filters", return_value=filters):
            findings = fre.find_candidates(self.profile)

        companies = {f["company"] for f in findings}
        self.assertIn("Beta", companies)
        self.assertNotIn("Acme", companies)

    def test_apply_archive_moves_filename_id_jd_to_archived(self):
        path = self._write_pending_jd(
            "role.json",
            {
                "job_title": "Engineer",
                "company_name": "Acme",
                "description": "",
                "_evaluation": {"recommendation": "Pursue", "composite_score": 4.0},
            },
        )
        findings = [{"identifier": path, "title": "Engineer", "company": "Acme"}]
        fre.apply_archive(findings, self.profile)

        self.assertFalse(os.path.exists(path))
        archived_dir = os.path.join(self.jds_dir, "archived")
        self.assertTrue(
            os.path.exists(os.path.join(archived_dir, os.path.basename(path)))
        )


if __name__ == "__main__":
    unittest.main()
