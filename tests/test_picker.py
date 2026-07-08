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


class TestPickOnePendingJd(unittest.TestCase):

    def test_empty_list_returns_none_without_prompting(self):
        with patch("picker.questionary.select") as mock_select:
            result = picker.pick_one_pending_jd([])
        self.assertIsNone(result)
        mock_select.assert_not_called()

    @patch("picker.jd_manager.extract_job_meta")
    @patch("picker.questionary.select")
    def test_label_uses_company_and_title_when_present(self, mock_select, mock_meta):
        mock_meta.return_value = ("Campaign Manager", "4MINDS")
        mock_select.return_value.ask.return_value = "jds/a.json"

        result = picker.pick_one_pending_jd(["jds/a.json"])

        self.assertEqual(result, "jds/a.json")
        choices = mock_select.call_args.kwargs["choices"]
        self.assertEqual(choices[0].title, "4MINDS - Campaign Manager")
        self.assertEqual(choices[0].value, "jds/a.json")

    @patch("picker.jd_manager.extract_job_meta", return_value=("", ""))
    @patch("picker.questionary.select")
    def test_label_falls_back_to_filename_when_meta_is_empty(self, mock_select, mock_meta):
        mock_select.return_value.ask.return_value = "jds/some_file.json"

        picker.pick_one_pending_jd(["jds/some_file.json"])

        choices = mock_select.call_args.kwargs["choices"]
        self.assertEqual(choices[0].title, "some_file.json")

    @patch("picker.jd_manager.extract_job_meta", return_value=("Title", "Company"))
    @patch("picker.questionary.select")
    def test_returns_the_users_selection(self, mock_select, mock_meta):
        mock_select.return_value.ask.return_value = "jds/b.json"
        result = picker.pick_one_pending_jd(["jds/a.json", "jds/b.json"])
        self.assertEqual(result, "jds/b.json")


class TestPickOneEvaluatedJd(unittest.TestCase):

    def test_empty_list_returns_none_without_prompting(self):
        with patch("picker.questionary.select") as mock_select:
            result = picker.pick_one_evaluated_jd([])
        self.assertIsNone(result)
        mock_select.assert_not_called()

    @patch("picker.jd_manager.read_evaluation", return_value=None)
    def test_no_evaluated_jds_prints_hint_and_returns_none(self, mock_read):
        with patch("picker.questionary.select") as mock_select, \
             patch("picker.cli_art.console.print") as mock_print:
            result = picker.pick_one_evaluated_jd(["jds/a.json"])
        self.assertIsNone(result)
        mock_select.assert_not_called()
        printed = mock_print.call_args[0][0]
        self.assertIn("Hint", printed)

    @patch("picker.jd_manager.extract_job_meta")
    @patch("picker.jd_manager.read_evaluation")
    @patch("picker.questionary.select")
    def test_excludes_jds_with_no_evaluation(self, mock_select, mock_read, mock_meta):
        mock_read.side_effect = lambda path: {
            "jds/a.json": {"composite_score": 4.0, "recommendation": "Strong pursue"},
            "jds/b.json": None,
        }[path]
        mock_meta.return_value = ("Role", "Acme")
        mock_select.return_value.ask.return_value = "jds/a.json"

        picker.pick_one_evaluated_jd(["jds/a.json", "jds/b.json"])

        choices = mock_select.call_args.kwargs["choices"]
        self.assertEqual(len(choices), 1)
        self.assertEqual(choices[0].value, "jds/a.json")

    @patch("picker.jd_manager.extract_job_meta")
    @patch("picker.jd_manager.read_evaluation")
    @patch("picker.questionary.select")
    def test_sorts_best_score_first_regardless_of_input_order(self, mock_select, mock_read, mock_meta):
        mock_read.side_effect = lambda path: {
            "jds/low.json": {"composite_score": 2.5, "recommendation": "Low-priority pursue"},
            "jds/high.json": {"composite_score": 4.8, "recommendation": "Strong pursue"},
        }[path]
        mock_meta.return_value = ("Role", "Company")
        mock_select.return_value.ask.return_value = "jds/high.json"

        picker.pick_one_evaluated_jd(["jds/low.json", "jds/high.json"])

        choices = mock_select.call_args.kwargs["choices"]
        self.assertEqual(choices[0].value, "jds/high.json")
        self.assertEqual(choices[1].value, "jds/low.json")

    @patch("picker.jd_manager.extract_job_meta", return_value=("Content Strategist", "Acme"))
    @patch("picker.jd_manager.read_evaluation", return_value={
        "composite_score": 4.8, "recommendation": "Strong pursue",
    })
    @patch("picker.questionary.select")
    def test_label_includes_score_and_recommendation(self, mock_select, mock_read, mock_meta):
        mock_select.return_value.ask.return_value = "jds/a.json"
        picker.pick_one_evaluated_jd(["jds/a.json"])
        choices = mock_select.call_args.kwargs["choices"]
        combined_text = "".join(part[1] for part in choices[0].title)
        self.assertEqual(combined_text, "4.80/5 | Strong pursue | Acme | Content Strategist")

    @patch("picker.jd_manager.extract_job_meta", return_value=("Content Strategist", "Acme"))
    @patch("picker.jd_manager.read_evaluation", return_value={
        "composite_score": 4.8, "recommendation": "Strong pursue",
    })
    @patch("picker.questionary.select")
    def test_label_colors_the_score_segment_by_recommendation_tier(self, mock_select, mock_read, mock_meta):
        mock_select.return_value.ask.return_value = "jds/a.json"
        picker.pick_one_evaluated_jd(["jds/a.json"])
        choices = mock_select.call_args.kwargs["choices"]
        score_style, score_text = choices[0].title[0]
        self.assertEqual(score_style, "fg:#4caf50 bold")
        self.assertEqual(score_text, "4.80/5 | Strong pursue")
