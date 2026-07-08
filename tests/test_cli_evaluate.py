import os
import sys
import unittest
from unittest.mock import patch, MagicMock

SCRIPTS_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts")
sys.path.insert(0, SCRIPTS_DIR)

from click.testing import CliRunner  # noqa: E402
import cli  # noqa: E402


class TestEvaluateBatchMode(unittest.TestCase):

    def test_no_pending_jds_exits_cleanly(self):
        runner = CliRunner()
        with patch("cli.jd_manager.get_pending_jds", return_value=[]):
            result = runner.invoke(cli.cli, ["evaluate"])
        self.assertEqual(result.exit_code, 0)
        self.assertIn("Nothing to evaluate", result.output)

    def test_declined_confirmation_aborts_without_evaluating(self):
        runner = CliRunner()
        with patch("cli.jd_manager.get_pending_jds", return_value=["jds/a.json"]), \
             patch("cli.click.confirm", return_value=False), \
             patch("cli.batch_evaluate.evaluate_all_pending") as mock_evaluate:
            result = runner.invoke(cli.cli, ["evaluate"])
        self.assertEqual(result.exit_code, 0)
        self.assertIn("Aborted", result.output)
        mock_evaluate.assert_not_called()

    def test_default_skips_already_evaluated(self):
        runner = CliRunner()
        with patch("cli.jd_manager.get_pending_jds", return_value=["jds/a.json"]), \
             patch("cli.click.confirm", return_value=True), \
             patch("cli.batch_evaluate.evaluate_all_pending", return_value=[]) as mock_evaluate:
            runner.invoke(cli.cli, ["evaluate"])
        mock_evaluate.assert_called_once_with(["jds/a.json"], skip_evaluated=True)

    def test_refresh_flag_forces_reevaluation(self):
        runner = CliRunner()
        with patch("cli.jd_manager.get_pending_jds", return_value=["jds/a.json"]), \
             patch("cli.click.confirm", return_value=True), \
             patch("cli.batch_evaluate.evaluate_all_pending", return_value=[]) as mock_evaluate:
            runner.invoke(cli.cli, ["evaluate", "--refresh"])
        mock_evaluate.assert_called_once_with(["jds/a.json"], skip_evaluated=False)

    def test_yes_flag_skips_confirmation(self):
        runner = CliRunner()
        with patch("cli.jd_manager.get_pending_jds", return_value=["jds/a.json"]), \
             patch("cli.click.confirm") as mock_confirm, \
             patch("cli.batch_evaluate.evaluate_all_pending", return_value=[]):
            runner.invoke(cli.cli, ["evaluate", "--yes"])
        mock_confirm.assert_not_called()


class TestEvaluateSingleFile(unittest.TestCase):

    def test_persists_evaluation_on_success(self):
        runner = CliRunner()
        result_dict = {
            "archetype": "x", "composite_score": 4.0, "recommendation": "Strong pursue",
            "dimension_scores": {},
        }
        with patch("cli.orchestrator.ResumeEngine") as mock_engine_cls, \
             patch("cli.jd_manager.save_evaluation") as mock_save:
            mock_engine_cls.return_value.evaluate_fit.return_value = result_dict
            result = runner.invoke(cli.cli, ["evaluate", "README.md"])
        self.assertEqual(result.exit_code, 0)
        mock_save.assert_called_once_with("README.md", result_dict)

    def test_failed_evaluation_does_not_persist(self):
        runner = CliRunner()
        with patch("cli.orchestrator.ResumeEngine") as mock_engine_cls, \
             patch("cli.jd_manager.save_evaluation") as mock_save:
            mock_engine_cls.return_value.evaluate_fit.return_value = {}
            result = runner.invoke(cli.cli, ["evaluate", "README.md"])
        self.assertEqual(result.exit_code, 1)
        mock_save.assert_not_called()


if __name__ == "__main__":
    unittest.main()
