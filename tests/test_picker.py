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
