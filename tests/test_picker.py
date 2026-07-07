import os
import sys
import unittest
from unittest.mock import patch, MagicMock

SCRIPTS_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts")
sys.path.insert(0, SCRIPTS_DIR)

import picker  # noqa: E402


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
