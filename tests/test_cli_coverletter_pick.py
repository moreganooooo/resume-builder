import os
import sys
import unittest
from unittest.mock import patch, MagicMock

SCRIPTS_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts")
sys.path.insert(0, SCRIPTS_DIR)

from click.testing import CliRunner  # noqa: E402
import cli  # noqa: E402


class TestCoverletterPickValidation(unittest.TestCase):

    def test_file_and_pick_together_is_an_error(self):
        runner = CliRunner()
        result = runner.invoke(cli.cli, ["coverletter", "--pick", "README.md"])
        self.assertEqual(result.exit_code, 1)

    def test_neither_file_nor_pick_is_an_error(self):
        runner = CliRunner()
        result = runner.invoke(cli.cli, ["coverletter"])
        self.assertEqual(result.exit_code, 1)

    def test_pick_with_no_pending_jds_exits_cleanly(self):
        runner = CliRunner()
        with patch("cli.jd_manager.get_pending_jds", return_value=[]):
            result = runner.invoke(cli.cli, ["coverletter", "--pick"])
        self.assertEqual(result.exit_code, 0)
        self.assertIn("Nothing to pick from", result.output)

    def test_pick_declined_confirmation_aborts_without_evaluating(self):
        runner = CliRunner()
        with patch("cli.jd_manager.get_pending_jds", return_value=["jds/a.json", "jds/b.json"]), \
             patch("picker.questionary.confirm") as mock_confirm, \
             patch("cli.batch_evaluate.evaluate_all_pending") as mock_evaluate:
            mock_confirm.return_value.ask.return_value = False
            result = runner.invoke(cli.cli, ["coverletter", "--pick"])
        self.assertEqual(result.exit_code, 0)
        self.assertIn("Aborted", result.output)
        mock_evaluate.assert_not_called()

    def test_pick_generates_only_for_selected_jd(self):
        mock_question = MagicMock()
        mock_question.ask.return_value = ["jds/b.json"]

        with patch("cli.jd_manager.get_pending_jds", return_value=["jds/a.json", "jds/b.json"]), \
             patch("cli.batch_evaluate.evaluate_all_pending", return_value=[
                 {"source_file": "jds/a.json", "company_name": "A", "job_title": "Role A",
                  "composite_score": 4.0, "recommendation": "Strong pursue", "error": False},
                 {"source_file": "jds/b.json", "company_name": "B", "job_title": "Role B",
                  "composite_score": 3.0, "recommendation": "Selective pursue", "error": False},
             ]), \
             patch("cli_art.questionary.checkbox", return_value=mock_question), \
             patch("cli.orchestrator.ResumeEngine") as mock_engine_cls:
            mock_engine = MagicMock()
            mock_engine.build_tailored_coverletter.return_value = {"ok": True}
            mock_engine_cls.return_value = mock_engine

            runner = CliRunner()
            result = runner.invoke(cli.cli, ["coverletter", "--pick", "--yes"])

        self.assertEqual(result.exit_code, 0)
        mock_engine.build_tailored_coverletter.assert_called_once_with("jds/b.json")
        self.assertIn("1 completed, 0 failed", result.output)
