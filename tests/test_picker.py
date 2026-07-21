import os
import sys
import unittest
from unittest.mock import patch, MagicMock

SCRIPTS_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts")
sys.path.insert(0, SCRIPTS_DIR)

import picker  # noqa: E402


class TestShouldProceed(unittest.TestCase):

    def test_defaults_to_evaluate_wording(self):
        with patch("picker.click.confirm", return_value=True) as mock_confirm:
            picker.should_proceed(5, skip_confirm=False)
        mock_confirm.assert_called_once_with("About to evaluate 5 pending JD(s) -- one real Gemini call each. Continue?")

    def test_custom_action_wording(self):
        with patch("picker.click.confirm", return_value=True) as mock_confirm:
            picker.should_proceed(5, skip_confirm=False, action="tailor")
        mock_confirm.assert_called_once_with("About to tailor 5 pending JD(s) -- one real Gemini call each. Continue?")


class TestPickAndProcess(unittest.TestCase):

    def test_empty_pending_returns_zero_zero_without_confirming(self):
        with patch("picker.click.confirm") as mock_confirm:
            result = picker.pick_and_process([], lambda path: True, "tailor")
        self.assertEqual(result, (0, 0))
        mock_confirm.assert_not_called()

    def test_declined_confirmation_returns_zero_zero_without_evaluating(self):
        with patch("picker.click.confirm", return_value=False), \
             patch("picker.batch_evaluate.evaluate_all_pending") as mock_evaluate:
            result = picker.pick_and_process(["jds/a.json"], lambda path: True, "tailor")
        self.assertEqual(result, (0, 0))
        mock_evaluate.assert_not_called()

    def test_all_errored_results_returns_zero_zero_without_showing_picker(self):
        with patch("picker.click.confirm", return_value=True), \
             patch("picker.batch_evaluate.evaluate_all_pending", return_value=[
                 {"source_file": "jds/a.json", "company_name": "A", "job_title": "Role A",
                  "composite_score": None, "recommendation": None, "error": True},
             ]), \
             patch("picker.questionary.checkbox") as mock_checkbox:
            result = picker.pick_and_process(["jds/a.json"], lambda path: True, "tailor")
        self.assertEqual(result, (0, 0))
        mock_checkbox.assert_not_called()

    def test_always_evaluates_fresh_not_skip_by_default(self):
        with patch("picker.click.confirm", return_value=True), \
             patch("picker.batch_evaluate.evaluate_all_pending", return_value=[]) as mock_evaluate:
            picker.pick_and_process(["jds/a.json"], lambda path: True, "tailor")
        mock_evaluate.assert_called_once_with(["jds/a.json"], skip_evaluated=False)

    def test_nothing_selected_returns_zero_zero(self):
        mock_question = MagicMock()
        mock_question.ask.return_value = None
        with patch("picker.click.confirm", return_value=True), \
             patch("picker.batch_evaluate.evaluate_all_pending", return_value=[
                 {"source_file": "jds/a.json", "company_name": "A", "job_title": "Role A",
                  "composite_score": 4.0, "recommendation": "Strong pursue", "error": False},
             ]), \
             patch("picker.questionary.checkbox", return_value=mock_question):
            result = picker.pick_and_process(["jds/a.json"], lambda path: True, "tailor")
        self.assertEqual(result, (0, 0))

    def test_processes_only_selected_paths_and_counts_success_and_failure(self):
        mock_question = MagicMock()
        mock_question.ask.return_value = ["jds/a.json", "jds/b.json"]

        def fake_process(path):
            return path == "jds/a.json"  # a succeeds, b fails

        with patch("picker.click.confirm", return_value=True), \
             patch("picker.batch_evaluate.evaluate_all_pending", return_value=[
                 {"source_file": "jds/a.json", "company_name": "A", "job_title": "Role A",
                  "composite_score": 4.0, "recommendation": "Strong pursue", "error": False},
                 {"source_file": "jds/b.json", "company_name": "B", "job_title": "Role B",
                  "composite_score": 3.0, "recommendation": "Selective pursue", "error": False},
             ]), \
             patch("picker.questionary.checkbox", return_value=mock_question):
            result = picker.pick_and_process(["jds/a.json", "jds/b.json"], fake_process, "tailor")
        self.assertEqual(result, (1, 1))

    def test_skip_confirm_true_never_calls_click_confirm(self):
        mock_question = MagicMock()
        mock_question.ask.return_value = ["jds/a.json"]
        with patch("picker.click.confirm") as mock_confirm, \
             patch("picker.batch_evaluate.evaluate_all_pending", return_value=[
                 {"source_file": "jds/a.json", "company_name": "A", "job_title": "Role A",
                  "composite_score": 4.0, "recommendation": "Strong pursue", "error": False},
             ]), \
             patch("picker.questionary.checkbox", return_value=mock_question):
            picker.pick_and_process(["jds/a.json"], lambda path: True, "tailor", skip_confirm=True)
        mock_confirm.assert_not_called()


class TestListAllEvaluatedJds(unittest.TestCase):

    @patch("picker.jd_manager.extract_job_meta", return_value=("Role", "Acme"))
    @patch("picker.jd_manager.read_liveness", return_value=None)
    @patch("picker.jd_manager.read_evaluation")
    @patch("picker.jd_manager.get_completed_jds", return_value=["jds/completed/c.json"])
    @patch("picker.jd_manager.get_pending_jds", return_value=["jds/p.json"])
    def test_combines_pending_and_completed_with_status_tags(self, mock_pending, mock_completed, mock_read, mock_live, mock_meta):
        mock_read.side_effect = lambda path: {
            "jds/p.json": {"composite_score": 3.0, "recommendation": "Selective pursue"},
            "jds/completed/c.json": {"composite_score": 4.0, "recommendation": "Strong pursue"},
        }[path]

        rows = picker.list_all_evaluated_jds()

        statuses = {r["path"]: r["status"] for r in rows}
        self.assertEqual(statuses["jds/p.json"], "Pending")
        self.assertEqual(statuses["jds/completed/c.json"], "Completed")

    @patch("picker.jd_manager.extract_job_meta", return_value=("Role", "Acme"))
    @patch("picker.jd_manager.read_liveness", return_value=None)
    @patch("picker.jd_manager.read_evaluation")
    @patch("picker.jd_manager.get_completed_jds", return_value=[])
    @patch("picker.jd_manager.get_pending_jds", return_value=["jds/a.json", "jds/b.json"])
    def test_excludes_jds_with_no_evaluation(self, mock_pending, mock_completed, mock_read, mock_live, mock_meta):
        mock_read.side_effect = lambda path: {
            "jds/a.json": {"composite_score": 4.0, "recommendation": "Strong pursue"},
            "jds/b.json": None,
        }[path]

        rows = picker.list_all_evaluated_jds()

        self.assertEqual([r["path"] for r in rows], ["jds/a.json"])

    @patch("picker.jd_manager.extract_job_meta", return_value=("Role", "Acme"))
    @patch("picker.jd_manager.read_liveness", return_value=None)
    @patch("picker.jd_manager.read_evaluation")
    @patch("picker.jd_manager.get_completed_jds", return_value=[])
    @patch("picker.jd_manager.get_pending_jds", return_value=["jds/low.json", "jds/high.json"])
    def test_sorts_best_score_first(self, mock_pending, mock_completed, mock_read, mock_live, mock_meta):
        mock_read.side_effect = lambda path: {
            "jds/low.json": {"composite_score": 2.5, "recommendation": "Low-priority pursue"},
            "jds/high.json": {"composite_score": 4.8, "recommendation": "Strong pursue"},
        }[path]

        rows = picker.list_all_evaluated_jds()

        self.assertEqual([r["path"] for r in rows], ["jds/high.json", "jds/low.json"])


class TestBrowseAndSelectJds(unittest.TestCase):

    @patch("picker.list_all_evaluated_jds", return_value=[])
    def test_empty_list_prints_hint_and_returns_empty(self, mock_list):
        with patch("picker.questionary.checkbox") as mock_checkbox, \
             patch("picker.cli_art.console.print") as mock_print:
            result = picker.browse_and_select_jds()
        self.assertEqual(result, [])
        mock_checkbox.assert_not_called()
        printed = mock_print.call_args[0][0]
        self.assertIn("Hint", printed)

    @patch("picker.cli_art.render_pipeline_table")
    @patch("picker.list_all_evaluated_jds")
    def test_nothing_checked_returns_empty(self, mock_list, mock_render):
        mock_list.return_value = [
            {"path": "jds/a.json", "status": "Pending", "title": "Role", "company": "Acme",
             "evaluation": {"composite_score": 4.0, "recommendation": "Strong pursue"}},
        ]
        mock_question = MagicMock()
        mock_question.ask.return_value = None
        with patch("picker.questionary.checkbox", return_value=mock_question):
            result = picker.browse_and_select_jds()
        self.assertEqual(result, [])

    @patch("picker.cli_art.render_pipeline_table")
    @patch("picker.list_all_evaluated_jds")
    def test_returns_the_selected_rows_not_just_paths(self, mock_list, mock_render):
        rows = [
            {"path": "jds/a.json", "status": "Pending", "title": "Role A", "company": "Acme",
             "evaluation": {"composite_score": 4.0, "recommendation": "Strong pursue"}},
            {"path": "jds/b.json", "status": "Completed", "title": "Role B", "company": "Beta",
             "evaluation": {"composite_score": 3.0, "recommendation": "Selective pursue"}},
        ]
        mock_list.return_value = rows
        mock_question = MagicMock()
        mock_question.ask.return_value = ["jds/b.json"]
        with patch("picker.questionary.checkbox", return_value=mock_question):
            result = picker.browse_and_select_jds()
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["path"], "jds/b.json")
        self.assertEqual(result[0]["status"], "Completed")
