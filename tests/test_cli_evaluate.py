import os
import sys
import unittest
from unittest.mock import patch

SCRIPTS_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts"
)
sys.path.insert(0, SCRIPTS_DIR)

import cli  # noqa: E402
from click.testing import CliRunner  # noqa: E402


class TestEvaluateBatchMode(unittest.TestCase):

    def test_no_pending_jds_exits_cleanly(self):
        runner = CliRunner()
        with patch("cli.jd_manager.get_pending_jds", return_value=[]):
            result = runner.invoke(cli.cli, ["evaluate"])
        self.assertEqual(result.exit_code, 0)
        self.assertIn("Nothing to evaluate", result.output)

    def test_declined_confirmation_aborts_without_evaluating(self):
        runner = CliRunner()
        with (
            patch("cli.jd_manager.get_pending_jds", return_value=["jds/a.json"]),
            patch("cli_art.questionary.confirm") as mock_confirm,
            patch("cli.batch_evaluate.evaluate_all_pending") as mock_evaluate,
        ):
            mock_confirm.return_value.ask.return_value = False
            result = runner.invoke(cli.cli, ["evaluate"])
        self.assertEqual(result.exit_code, 0)
        self.assertIn("Aborted", result.output)
        mock_evaluate.assert_not_called()

    def test_default_confirms_and_evaluates_only_unscored(self):
        runner = CliRunner()
        with (
            patch(
                "cli.jd_manager.get_pending_jds",
                return_value=["jds/a.json", "jds/b.json"],
            ),
            patch(
                "cli.picker.unevaluated_roles",
                return_value=(["jds/b.json"], []),
            ),
            patch("cli_art.questionary.confirm") as mock_confirm,
            patch(
                "cli.batch_evaluate.evaluate_all_pending", return_value=[]
            ) as mock_evaluate,
        ):
            mock_confirm.return_value.ask.return_value = True
            result = runner.invoke(cli.cli, ["evaluate"])
        # Confirms against the real, post-filter count (1), not the raw pending count (2).
        self.assertIn("About to evaluate 1 pending", mock_confirm.call_args[0][0])
        mock_evaluate.assert_called_once_with(["jds/b.json"], skip_evaluated=False)
        self.assertIn("1 already-evaluated JD(s) will be skipped", result.output)

    def test_nothing_new_to_evaluate_exits_cleanly_without_confirming(self):
        runner = CliRunner()
        with (
            patch("cli.jd_manager.get_pending_jds", return_value=["jds/a.json"]),
            patch("cli.picker.unevaluated_roles", return_value=([], [])),
            patch("cli_art.questionary.confirm") as mock_confirm,
            patch("cli.batch_evaluate.evaluate_all_pending") as mock_evaluate,
        ):
            result = runner.invoke(cli.cli, ["evaluate"])
        self.assertEqual(result.exit_code, 0)
        self.assertIn("Nothing new to evaluate", result.output)
        mock_confirm.assert_not_called()
        mock_evaluate.assert_not_called()

    def test_database_only_roles_are_evaluated_too(self):
        """Most pending jobs are database-only scan rows with no JD file.
        Building the work list from get_pending_jds() alone counted them
        in the banner and then skipped them here."""
        runner = CliRunner()
        with (
            patch("cli.jd_manager.get_pending_jds", return_value=["jds/b.json"]),
            patch(
                "cli.picker.unevaluated_roles",
                return_value=(["jds/b.json"], ["hash-only-row"]),
            ),
            patch("cli_art.questionary.confirm") as mock_confirm,
            patch(
                "cli.batch_evaluate.evaluate_all_pending", return_value=[]
            ) as mock_evaluate,
        ):
            mock_confirm.return_value.ask.return_value = True
            runner.invoke(cli.cli, ["evaluate"])
        mock_evaluate.assert_called_once_with(
            ["jds/b.json", "hash-only-row"], skip_evaluated=False
        )

    def test_refresh_flag_forces_reevaluation(self):
        runner = CliRunner()
        with (
            patch("cli.jd_manager.get_pending_jds", return_value=["jds/a.json"]),
            patch("cli.batch_evaluate.split_evaluated") as mock_split,
            patch("cli_art.questionary.confirm") as mock_confirm,
            patch(
                "cli.batch_evaluate.evaluate_all_pending", return_value=[]
            ) as mock_evaluate,
        ):
            mock_confirm.return_value.ask.return_value = True
            runner.invoke(cli.cli, ["evaluate", "--refresh"])
        mock_split.assert_not_called()
        mock_evaluate.assert_called_once_with(["jds/a.json"], skip_evaluated=False)

    def test_yes_flag_skips_confirmation(self):
        runner = CliRunner()
        with (
            patch("cli.jd_manager.get_pending_jds", return_value=["jds/a.json"]),
            patch("cli_art.questionary.confirm") as mock_confirm,
            patch("cli.batch_evaluate.evaluate_all_pending", return_value=[]),
        ):
            runner.invoke(cli.cli, ["evaluate", "--yes"])
        mock_confirm.assert_not_called()


class TestEvaluateSingleFile(unittest.TestCase):

    def test_persists_evaluation_on_success(self):
        runner = CliRunner()
        result_dict = {
            "archetype": "x",
            "composite_score": 4.0,
            "recommendation": "Strong pursue",
            "fit_subscores": {},
            "interview_odds_subscores": {},
            "practical_pursue_subscores": {},
        }
        with (
            patch("cli.orchestrator.ResumeEngine") as mock_engine_cls,
            patch("cli.jd_manager.save_evaluation") as mock_save,
        ):
            mock_engine_cls.return_value.evaluate_fit.return_value = result_dict
            result = runner.invoke(cli.cli, ["evaluate", "README.md"])
        self.assertEqual(result.exit_code, 0)
        mock_save.assert_called_once_with("README.md", result_dict)

    def test_failed_evaluation_does_not_persist(self):
        runner = CliRunner()
        with (
            patch("cli.orchestrator.ResumeEngine") as mock_engine_cls,
            patch("cli.jd_manager.save_evaluation") as mock_save,
        ):
            mock_engine_cls.return_value.evaluate_fit.return_value = {}
            result = runner.invoke(cli.cli, ["evaluate", "README.md"])
        self.assertEqual(result.exit_code, 1)
        mock_save.assert_not_called()

    def test_skip_recommendation_gets_auto_archived(self):
        runner = CliRunner()
        result_dict = {
            "archetype": "x",
            "composite_score": 1.2,
            "recommendation": "Skip",
            "fit_subscores": {},
            "interview_odds_subscores": {},
            "practical_pursue_subscores": {},
        }
        with (
            patch("cli.orchestrator.ResumeEngine") as mock_engine_cls,
            patch("cli.jd_manager.save_evaluation"),
            patch(
                "cli.jd_manager.archive_jd", return_value="jds/archived/README.md"
            ) as mock_archive,
        ):
            mock_engine_cls.return_value.evaluate_fit.return_value = result_dict
            result = runner.invoke(cli.cli, ["evaluate", "README.md"])
        self.assertEqual(result.exit_code, 0)
        mock_archive.assert_called_once_with("README.md")

    def test_non_skip_recommendation_is_not_archived(self):
        runner = CliRunner()
        result_dict = {
            "archetype": "x",
            "composite_score": 4.5,
            "recommendation": "Strong pursue",
            "fit_subscores": {},
            "interview_odds_subscores": {},
            "practical_pursue_subscores": {},
        }
        with (
            patch("cli.orchestrator.ResumeEngine") as mock_engine_cls,
            patch("cli.jd_manager.save_evaluation"),
            patch("cli.jd_manager.archive_jd") as mock_archive,
        ):
            mock_engine_cls.return_value.evaluate_fit.return_value = result_dict
            runner.invoke(cli.cli, ["evaluate", "README.md"])
        mock_archive.assert_not_called()


if __name__ == "__main__":
    unittest.main()
