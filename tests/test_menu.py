import os
import sys
import unittest
from unittest.mock import patch

SCRIPTS_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts")
sys.path.insert(0, SCRIPTS_DIR)

import questionary  # noqa: E402

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
        self.assertIn("Scan for New Postings", labels["scan"])
        self.assertIn("Check Posting Liveness", labels["liveness"])
        self.assertIn("Evaluate ALL Pending Roles", labels["evaluate_all"])
        self.assertIn("Evaluate a Specific Role", labels["evaluate_one"])
        self.assertIn("Customize Resume for ALL Pending Roles (batch)", labels["tailor_all"])
        self.assertIn("Customize Resume for a Specific Role", labels["tailor_one"])
        self.assertIn("Write Cover Letter to Match a Resume", labels["coverletter_one"])
        self.assertIn("Polish a Resume or Cover Letter with Gemini", labels["polish"])

    def test_choices_are_grouped_with_labeled_separators(self):
        separator_lines = [c.line for c in menu._CHOICES if isinstance(c, questionary.Separator)]
        self.assertTrue(any("Discovery" in line for line in separator_lines))
        self.assertTrue(any("Evaluation" in line for line in separator_lines))
        self.assertTrue(any("Build" in line for line in separator_lines))


class TestHandleScan(unittest.TestCase):

    @patch("menu.scan_module.run_scan", return_value=3)
    @patch("menu.questionary.select")
    def test_returns_true_when_postings_written(self, mock_select, mock_run):
        mock_select.return_value.ask.return_value = "both"
        self.assertTrue(menu._handle_scan())

    @patch("menu.scan_module.run_scan", return_value=0)
    @patch("menu.questionary.select")
    def test_returns_false_when_nothing_written(self, mock_select, mock_run):
        mock_select.return_value.ask.return_value = "both"
        self.assertFalse(menu._handle_scan())

    @patch("menu.scan_module.run_scan")
    @patch("menu.questionary.select")
    def test_returns_false_without_scanning_when_cancelled(self, mock_select, mock_run):
        mock_select.return_value.ask.return_value = None
        self.assertFalse(menu._handle_scan())
        mock_run.assert_not_called()

    @patch("menu.scan_module.run_scan", return_value=1)
    @patch("menu.questionary.select")
    def test_both_choice_passes_none_to_run_scan(self, mock_select, mock_run):
        mock_select.return_value.ask.return_value = "both"
        menu._handle_scan()
        mock_run.assert_called_once_with(None)

    @patch("menu.scan_module.run_scan", return_value=1)
    @patch("menu.questionary.select")
    def test_jobright_choice_passes_single_source_list(self, mock_select, mock_run):
        mock_select.return_value.ask.return_value = "jobright"
        menu._handle_scan()
        mock_run.assert_called_once_with(["jobright"])

    @patch("menu.scan_module.run_scan", return_value=1)
    @patch("menu.questionary.select")
    def test_linkedin_choice_passes_single_source_list(self, mock_select, mock_run):
        mock_select.return_value.ask.return_value = "linkedin"
        menu._handle_scan()
        mock_run.assert_called_once_with(["linkedin"])


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

    @patch("menu.cli_art.render_fit_table")
    @patch("menu.batch_evaluate.evaluate_all_pending", return_value=[])
    @patch("menu.picker.should_proceed", return_value=True)
    @patch("menu.batch_evaluate.split_evaluated", return_value=(["jds/a.json"], ["jds/b.json"]))
    @patch("menu.jd_manager.get_pending_jds", return_value=["jds/a.json", "jds/b.json"])
    def test_confirms_against_and_evaluates_only_unscored(
        self, mock_pending, mock_split, mock_proceed, mock_eval, mock_table,
    ):
        menu._handle_evaluate_all()
        mock_proceed.assert_called_once_with(1, skip_confirm=False)
        mock_eval.assert_called_once_with(["jds/b.json"], skip_evaluated=False)

    @patch("menu.batch_evaluate.split_evaluated", return_value=(["jds/a.json"], []))
    @patch("menu.jd_manager.get_pending_jds", return_value=["jds/a.json"])
    def test_nothing_new_to_evaluate_returns_false_without_confirming(self, mock_pending, mock_split):
        with patch("menu.picker.should_proceed") as mock_proceed:
            self.assertFalse(menu._handle_evaluate_all())
        mock_proceed.assert_not_called()


class TestHandleEvaluateOne(unittest.TestCase):

    @patch("menu.picker.pick_one_pending_jd", return_value=None)
    def test_returns_false_when_no_path(self, mock_pick):
        self.assertFalse(menu._handle_evaluate_one())

    @patch("menu.orchestrator.ResumeEngine")
    @patch("menu.picker.pick_one_pending_jd", return_value="jds/a.json")
    def test_returns_false_when_result_falsy(self, mock_pick, mock_engine_cls):
        mock_engine_cls.return_value.evaluate_fit.return_value = {}
        self.assertFalse(menu._handle_evaluate_one())

    @patch("menu.orchestrator.ResumeEngine")
    @patch("menu.picker.pick_one_pending_jd", return_value="jds/a.json")
    def test_returns_true_when_result_truthy(self, mock_pick, mock_engine_cls):
        mock_engine_cls.return_value.evaluate_fit.return_value = {
            "archetype": "x", "composite_score": 4.0, "recommendation": "Strong pursue",
        }
        self.assertTrue(menu._handle_evaluate_one())

    @patch("menu.jd_manager.save_evaluation")
    @patch("menu.orchestrator.ResumeEngine")
    @patch("menu.picker.pick_one_pending_jd", return_value="jds/a.json")
    def test_persists_evaluation_on_success(self, mock_pick, mock_engine_cls, mock_save):
        result = {"archetype": "x", "composite_score": 4.0, "recommendation": "Strong pursue"}
        mock_engine_cls.return_value.evaluate_fit.return_value = result
        menu._handle_evaluate_one()
        mock_save.assert_called_once_with("jds/a.json", result)


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

    @patch("menu.picker.pick_one_evaluated_jd", return_value=None)
    def test_returns_false_when_no_path_picked(self, mock_pick):
        self.assertFalse(menu._handle_tailor_one())

    @patch("menu.orchestrator.run_pipeline", return_value=(1, 0))
    @patch("menu.picker.pick_one_evaluated_jd", return_value="jds/a.json")
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

    @patch("menu.picker.pick_one_pending_jd", return_value=None)
    @patch("menu.jd_manager.get_completed_jds", return_value=["jds/completed/a.json"])
    @patch("menu.jd_manager.get_pending_jds", return_value=["jds/still_pending.json"])
    def test_picks_from_completed_jds_not_pending(self, mock_pending, mock_completed, mock_pick):
        menu._handle_coverletter_one()
        mock_pick.assert_called_once_with(["jds/completed/a.json"])
        mock_pending.assert_not_called()


class TestHandlePolish(unittest.TestCase):

    @patch("menu.polish_module.run")
    def test_always_returns_false(self, mock_run):
        self.assertFalse(menu._handle_polish())


class TestChainContent(unittest.TestCase):

    def test_chain_matches_the_designed_pipeline_order(self):
        self.assertEqual(menu._CHAIN["scan"], [("Check Liveness", "liveness")])
        self.assertEqual(menu._CHAIN["liveness"], [("Evaluate All JDs", "evaluate_all")])
        self.assertEqual(menu._CHAIN["evaluate_all"], [("Customize Resume", "tailor_all")])
        self.assertEqual(menu._CHAIN["evaluate_one"], [("Customize Resume", "tailor_all")])
        self.assertEqual(
            menu._CHAIN["tailor_all"],
            [("Write Cover Letter", "coverletter_one"), ("Polish with Gemini", "polish")],
        )
        self.assertEqual(
            menu._CHAIN["tailor_one"],
            [("Write Cover Letter", "coverletter_one"), ("Polish with Gemini", "polish")],
        )
        self.assertEqual(menu._CHAIN["coverletter_one"], [("Polish with Gemini", "polish")])

    def test_polish_has_no_chain_entry(self):
        self.assertNotIn("polish", menu._CHAIN)


class TestRunWithChain(unittest.TestCase):

    @patch("menu.questionary.select")
    def test_no_op_handler_skips_the_prompt(self, mock_select):
        with patch.dict(menu._HANDLERS, {"fake": lambda: False}, clear=False), \
             patch.dict(menu._CHAIN, {"fake": [("Next", "somewhere")]}, clear=False):
            menu._run_with_chain("fake", {})
        mock_select.assert_not_called()

    @patch("menu.questionary.select")
    def test_handler_with_no_chain_entry_skips_the_prompt(self, mock_select):
        with patch.dict(menu._HANDLERS, {"fake": lambda: True}, clear=False):
            menu._run_with_chain("fake", {})
        mock_select.assert_not_called()

    @patch("menu.questionary.select")
    def test_chain_prompt_appends_back_to_menu_choice(self, mock_select):
        mock_select.return_value.ask.return_value = "__back__"
        with patch.dict(menu._HANDLERS, {"fake": lambda: True}, clear=False), \
             patch.dict(menu._CHAIN, {"fake": [("Next", "somewhere")]}, clear=False):
            menu._run_with_chain("fake", {})
        choices = mock_select.call_args.kwargs["choices"]
        self.assertEqual([c.title for c in choices], ["Next", "Back to Menu"])
        self.assertEqual([c.value for c in choices], ["somewhere", "__back__"])

    @patch("menu.questionary.select")
    def test_back_to_menu_stops_recursion(self, mock_select):
        calls = []
        mock_select.return_value.ask.return_value = "__back__"
        with patch.dict(menu._HANDLERS, {"fake": lambda: calls.append("fake") or True}, clear=False), \
             patch.dict(menu._CHAIN, {"fake": [("Next", "somewhere")]}, clear=False):
            menu._run_with_chain("fake", {})
        self.assertEqual(calls, ["fake"])

    @patch("menu.questionary.select")
    def test_cancelled_prompt_stops_recursion(self, mock_select):
        calls = []
        mock_select.return_value.ask.return_value = None
        with patch.dict(menu._HANDLERS, {"fake": lambda: calls.append("fake") or True}, clear=False), \
             patch.dict(menu._CHAIN, {"fake": [("Next", "somewhere")]}, clear=False):
            menu._run_with_chain("fake", {})
        self.assertEqual(calls, ["fake"])

    @patch("menu.questionary.select")
    def test_picking_a_next_step_recurses_into_it(self, mock_select):
        calls = []
        mock_select.return_value.ask.return_value = "second"
        with patch.dict(
            menu._HANDLERS,
            {
                "first": lambda: calls.append("first") or True,
                "second": lambda: calls.append("second") or False,
            },
            clear=False,
        ), patch.dict(menu._CHAIN, {"first": [("Do Second", "second")]}, clear=False):
            menu._run_with_chain("first", {})
        self.assertEqual(calls, ["first", "second"])


class TestSessionSummary(unittest.TestCase):

    @patch("menu.questionary.select")
    def test_successful_action_increments_its_labeled_count(self, mock_select):
        session_stats = {}
        with patch.dict(menu._HANDLERS, {"tailor_all": lambda: True}, clear=False), \
             patch.dict(menu._CHAIN, {}, clear=True):
            menu._run_with_chain("tailor_all", session_stats)
        self.assertEqual(session_stats, {"resumes tailored": 1})

    @patch("menu.questionary.select")
    def test_no_op_action_does_not_increment(self, mock_select):
        session_stats = {}
        with patch.dict(menu._HANDLERS, {"tailor_all": lambda: False}, clear=False):
            menu._run_with_chain("tailor_all", session_stats)
        self.assertEqual(session_stats, {})

    @patch("menu.questionary.select")
    def test_unlabeled_action_does_not_increment(self, mock_select):
        session_stats = {}
        with patch.dict(menu._HANDLERS, {"polish": lambda: True}, clear=False):
            menu._run_with_chain("polish", session_stats)
        self.assertEqual(session_stats, {})

    def test_empty_summary_string(self):
        self.assertEqual(menu._session_summary({}), "No actions taken this session.")

    def test_summary_joins_multiple_labels(self):
        summary = menu._session_summary({"resumes tailored": 3, "cover letters written": 2})
        self.assertIn("3 resumes tailored", summary)
        self.assertIn("2 cover letters written", summary)
        self.assertIn("Nice work.", summary)


class TestHandleViewApplications(unittest.TestCase):

    def setUp(self):
        self.tmp_dir = os.path.join(os.path.dirname(__file__), "_tmp_view_applications")
        os.makedirs(self.tmp_dir, exist_ok=True)
        self.path = os.path.join(self.tmp_dir, "applications.md")
        self._real_applications_md = menu.jd_manager.APPLICATIONS_MD
        menu.jd_manager.APPLICATIONS_MD = self.path

    def tearDown(self):
        menu.jd_manager.APPLICATIONS_MD = self._real_applications_md
        for name in os.listdir(self.tmp_dir):
            os.remove(os.path.join(self.tmp_dir, name))
        os.rmdir(self.tmp_dir)

    def test_returns_false_when_no_tracker_file_exists(self):
        with patch("menu.cli_art.display_applications_tracker") as mock_display:
            result = menu._handle_view_applications()
        self.assertFalse(result)
        mock_display.assert_not_called()

    def test_displays_content_and_returns_true_when_file_exists(self):
        with open(self.path, "w", encoding="utf-8") as f:
            f.write("# Applications Tracker\n\n| # | Company |\n|---|---------|\n| 1 | Acme |\n")
        with patch("menu.cli_art.display_applications_tracker") as mock_display:
            result = menu._handle_view_applications()
        self.assertTrue(result)
        mock_display.assert_called_once_with("# Applications Tracker\n\n| # | Company |\n|---|---------|\n| 1 | Acme |\n")


if __name__ == "__main__":
    unittest.main()
