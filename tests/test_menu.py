import os
import sys
import unittest
from unittest.mock import patch

SCRIPTS_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts")
sys.path.insert(0, SCRIPTS_DIR)

import menu  # noqa: E402


class TestChoicesAndHandlers(unittest.TestCase):

    def test_pick_from_list_entries_are_gone(self):
        values = [c.value for c in menu._CHOICES]
        self.assertNotIn("tailor_pick", values)
        self.assertNotIn("coverletter_pick", values)
        self.assertNotIn("tailor_pick", menu._HANDLERS)
        self.assertNotIn("coverletter_pick", menu._HANDLERS)

    def test_choices_have_the_renamed_labels(self):
        labels = {c.value: c.title for c in menu._CHOICES}
        self.assertEqual(labels["scan"], "Scan for New Postings")
        self.assertEqual(labels["liveness"], "Check Posting Liveness")
        self.assertEqual(labels["evaluate_all"], "Evaluate ALL Pending JDs")
        self.assertEqual(labels["evaluate_one"], "Evaluate a Specific JD")
        self.assertEqual(labels["tailor_all"], "Customize Resume for ALL Pending JDs (batch)")
        self.assertEqual(labels["tailor_one"], "Customize Resume for a Specific JD")
        self.assertEqual(labels["coverletter_one"], "Write cover letter for a Specific JD")
        self.assertEqual(labels["polish"], "Polish a resume or cover letter")


class TestHandleScan(unittest.TestCase):

    @patch("menu.scan_module.run_scan", return_value=3)
    def test_returns_true_when_postings_written(self, mock_run):
        self.assertTrue(menu._handle_scan())

    @patch("menu.scan_module.run_scan", return_value=0)
    def test_returns_false_when_nothing_written(self, mock_run):
        self.assertFalse(menu._handle_scan())


class TestHandleLiveness(unittest.TestCase):

    @patch("menu.liveness_module.run_liveness_check")
    def test_returns_true_when_something_checked(self, mock_check):
        mock_check.return_value = {"active": 1, "likely_active": 0, "expired": 0, "uncertain": 0, "skipped": 2, "moved": 0}
        self.assertTrue(menu._handle_liveness())

    @patch("menu.liveness_module.run_liveness_check")
    def test_returns_false_when_nothing_checked(self, mock_check):
        mock_check.return_value = {"active": 0, "likely_active": 0, "expired": 0, "uncertain": 0, "skipped": 5, "moved": 0}
        self.assertFalse(menu._handle_liveness())

    @patch("menu.liveness_module.run_liveness_check")
    def test_returns_false_on_error(self, mock_check):
        mock_check.return_value = {"active": 0, "likely_active": 0, "expired": 0, "uncertain": 0, "skipped": 0, "moved": 0, "error": True}
        self.assertFalse(menu._handle_liveness())


class TestHandleEvaluateAll(unittest.TestCase):

    @patch("menu.jd_manager.get_pending_jds", return_value=[])
    def test_returns_false_when_no_pending(self, mock_pending):
        self.assertFalse(menu._handle_evaluate_all())

    @patch("menu.picker.should_proceed", return_value=False)
    @patch("menu.jd_manager.get_pending_jds", return_value=["jds/a.json"])
    def test_returns_false_when_declined(self, mock_pending, mock_proceed):
        with patch("menu.batch_evaluate.evaluate_all_pending") as mock_eval:
            self.assertFalse(menu._handle_evaluate_all())
        mock_eval.assert_not_called()

    @patch("menu.cli_art.render_fit_table")
    @patch("menu.batch_evaluate.evaluate_all_pending", return_value=[{"error": False}])
    @patch("menu.picker.should_proceed", return_value=True)
    @patch("menu.jd_manager.get_pending_jds", return_value=["jds/a.json"])
    def test_returns_true_when_results_returned(self, mock_pending, mock_proceed, mock_eval, mock_table):
        self.assertTrue(menu._handle_evaluate_all())


class TestHandleEvaluateOne(unittest.TestCase):

    @patch("menu.questionary.path")
    def test_returns_false_when_no_path(self, mock_path):
        mock_path.return_value.ask.return_value = None
        self.assertFalse(menu._handle_evaluate_one())

    @patch("menu.orchestrator.ResumeEngine")
    @patch("menu.questionary.path")
    def test_returns_false_when_result_falsy(self, mock_path, mock_engine_cls):
        mock_path.return_value.ask.return_value = "jds/a.json"
        mock_engine_cls.return_value.evaluate_fit.return_value = {}
        self.assertFalse(menu._handle_evaluate_one())

    @patch("menu.orchestrator.ResumeEngine")
    @patch("menu.questionary.path")
    def test_returns_true_when_result_truthy(self, mock_path, mock_engine_cls):
        mock_path.return_value.ask.return_value = "jds/a.json"
        mock_engine_cls.return_value.evaluate_fit.return_value = {
            "archetype": "x", "composite_score": 4.0, "recommendation": "Strong pursue",
        }
        self.assertTrue(menu._handle_evaluate_one())


class TestHandleTailorAll(unittest.TestCase):

    @patch("menu.jd_manager.get_pending_jds", return_value=[])
    def test_returns_false_when_no_pending(self, mock_pending):
        self.assertFalse(menu._handle_tailor_all())

    @patch("menu.picker.should_proceed", return_value=False)
    @patch("menu.jd_manager.get_pending_jds", return_value=["jds/a.json"])
    def test_returns_false_when_declined(self, mock_pending, mock_proceed):
        with patch("menu.orchestrator.run_pipeline") as mock_run:
            self.assertFalse(menu._handle_tailor_all())
        mock_run.assert_not_called()

    @patch("menu.orchestrator.run_pipeline", return_value=(2, 0))
    @patch("menu.picker.should_proceed", return_value=True)
    @patch("menu.jd_manager.get_pending_jds", return_value=["jds/a.json"])
    def test_returns_true_when_completed_gt_zero(self, mock_pending, mock_proceed, mock_run):
        self.assertTrue(menu._handle_tailor_all())

    @patch("menu.orchestrator.run_pipeline", return_value=(0, 1))
    @patch("menu.picker.should_proceed", return_value=True)
    @patch("menu.jd_manager.get_pending_jds", return_value=["jds/a.json"])
    def test_returns_false_when_completed_zero(self, mock_pending, mock_proceed, mock_run):
        self.assertFalse(menu._handle_tailor_all())


class TestHandleTailorOne(unittest.TestCase):

    @patch("menu.picker.pick_one_pending_jd", return_value=None)
    def test_returns_false_when_no_path_picked(self, mock_pick):
        self.assertFalse(menu._handle_tailor_one())

    @patch("menu.orchestrator.run_pipeline", return_value=(1, 0))
    @patch("menu.picker.pick_one_pending_jd", return_value="jds/a.json")
    def test_returns_true_when_completed(self, mock_pick, mock_run):
        self.assertTrue(menu._handle_tailor_one())
        mock_run.assert_called_once_with(jd_path="jds/a.json")


class TestHandleCoverletterOne(unittest.TestCase):

    @patch("menu.picker.pick_one_pending_jd", return_value=None)
    def test_returns_false_when_no_path_picked(self, mock_pick):
        self.assertFalse(menu._handle_coverletter_one())

    @patch("menu.orchestrator.ResumeEngine")
    @patch("menu.picker.pick_one_pending_jd", return_value="jds/a.json")
    def test_returns_true_when_letter_built(self, mock_pick, mock_engine_cls):
        mock_engine_cls.return_value.build_tailored_coverletter.return_value = {"company_name": "Acme"}
        self.assertTrue(menu._handle_coverletter_one())

    @patch("menu.orchestrator.ResumeEngine")
    @patch("menu.picker.pick_one_pending_jd", return_value="jds/a.json")
    def test_returns_false_when_build_fails(self, mock_pick, mock_engine_cls):
        mock_engine_cls.return_value.build_tailored_coverletter.return_value = {}
        self.assertFalse(menu._handle_coverletter_one())


class TestHandlePolish(unittest.TestCase):

    @patch("menu.polish_module.run")
    def test_always_returns_false(self, mock_run):
        self.assertFalse(menu._handle_polish())


if __name__ == "__main__":
    unittest.main()
