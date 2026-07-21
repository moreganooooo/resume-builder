import os
import sys
import unittest
from unittest.mock import patch, MagicMock

SCRIPTS_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts")
sys.path.insert(0, SCRIPTS_DIR)

import bootstrap_bullet_bank  # noqa: E402


class TestPipelineStages(unittest.TestCase):

    def test_six_stages_in_correct_order(self):
        self.assertEqual(bootstrap_bullet_bank.PIPELINE_STAGES, [
            "audit_bullet_bank.py",
            "cluster_bullet_bank.py",
            "rewrite_bullets.py",
            "audit_keepers.py",
            "score_keeper_gems.py",
            "embed_bullet_bank.py",
        ])


class TestRunStage(unittest.TestCase):

    @patch("bootstrap_bullet_bank.subprocess.run")
    def test_returns_true_on_success(self, mock_run):
        mock_run.return_value = MagicMock(returncode=0)
        self.assertTrue(bootstrap_bullet_bank.run_stage("audit_bullet_bank.py"))

    @patch("bootstrap_bullet_bank.subprocess.run")
    def test_returns_false_on_nonzero_exit(self, mock_run):
        mock_run.return_value = MagicMock(returncode=1)
        self.assertFalse(bootstrap_bullet_bank.run_stage("audit_bullet_bank.py"))

    @patch("bootstrap_bullet_bank.subprocess.run")
    def test_invokes_with_current_interpreter_and_full_script_path(self, mock_run):
        mock_run.return_value = MagicMock(returncode=0)
        bootstrap_bullet_bank.run_stage("audit_bullet_bank.py")
        args, _kwargs = mock_run.call_args
        self.assertEqual(args[0][0], sys.executable)
        self.assertTrue(args[0][1].endswith("audit_bullet_bank.py"))


class TestRunFullPipeline(unittest.TestCase):

    @patch("bootstrap_bullet_bank.questionary.confirm")
    @patch("bootstrap_bullet_bank.run_stage", return_value=True)
    def test_all_stages_run_in_order_when_confirmed(self, mock_run_stage, mock_confirm):
        mock_confirm.return_value.ask.return_value = True
        result = bootstrap_bullet_bank.run_full_pipeline(skip_confirm=False)
        self.assertTrue(result)
        called_scripts = [call.args[0] for call in mock_run_stage.call_args_list]
        self.assertEqual(called_scripts, bootstrap_bullet_bank.PIPELINE_STAGES)

    @patch("bootstrap_bullet_bank.questionary.confirm")
    @patch("bootstrap_bullet_bank.run_stage")
    def test_stops_immediately_on_stage_failure(self, mock_run_stage, mock_confirm):
        mock_confirm.return_value.ask.return_value = True
        mock_run_stage.side_effect = [True, False]  # cluster_bullet_bank.py fails
        result = bootstrap_bullet_bank.run_full_pipeline(skip_confirm=False)
        self.assertFalse(result)
        self.assertEqual(mock_run_stage.call_count, 2)

    @patch("bootstrap_bullet_bank.questionary.confirm")
    @patch("bootstrap_bullet_bank.run_stage", return_value=True)
    def test_yes_flag_skips_all_confirmation_prompts(self, mock_run_stage, mock_confirm):
        result = bootstrap_bullet_bank.run_full_pipeline(skip_confirm=True)
        self.assertTrue(result)
        mock_confirm.assert_not_called()

    @patch("bootstrap_bullet_bank.questionary.confirm")
    @patch("bootstrap_bullet_bank.run_stage", return_value=True)
    def test_declining_first_gate_stops_before_any_stage_runs(self, mock_run_stage, mock_confirm):
        mock_confirm.return_value.ask.return_value = False
        result = bootstrap_bullet_bank.run_full_pipeline(skip_confirm=False)
        self.assertFalse(result)
        mock_run_stage.assert_not_called()

    @patch("bootstrap_bullet_bank.questionary.confirm")
    @patch("bootstrap_bullet_bank.run_stage", return_value=True)
    def test_two_confirmation_gates_total(self, mock_run_stage, mock_confirm):
        mock_confirm.return_value.ask.return_value = True
        bootstrap_bullet_bank.run_full_pipeline(skip_confirm=False)
        self.assertEqual(mock_confirm.call_count, 2)


class TestMainDryRun(unittest.TestCase):
    """--dry-run threads through to run_ingestion() (which mocks/skips every
    Gemini call per Tasks 3-5) and must never invoke the real six-stage
    pipeline -- running those scripts for real would defeat the point of a
    dry run."""

    @patch("bootstrap_bullet_bank.bootstrap_profile.collect_secrets")
    @patch("bootstrap_bullet_bank.bootstrap_profile.run_profile_setup")
    @patch("bootstrap_bullet_bank.run_full_pipeline")
    @patch("bootstrap_bullet_bank.run_ingestion")
    @patch("sys.argv", ["bootstrap_bullet_bank.py", "--dry-run"])
    def test_dry_run_skips_full_pipeline(self, mock_run_ingestion, mock_run_full_pipeline, mock_profile_setup, mock_collect_secrets):
        mock_run_ingestion.return_value = {"extracted": 0, "attributed": 0, "flagged": 0, "certificates": 0}
        mock_profile_setup.return_value = {"full_name": "", "primary_roles": 0, "secondary_roles": 0, "recommendations_found": 0}
        bootstrap_bullet_bank.main()
        mock_run_ingestion.assert_called_once_with(dry_run=True)
        mock_run_full_pipeline.assert_not_called()

    @patch("bootstrap_bullet_bank.bootstrap_profile.collect_secrets")
    @patch("bootstrap_bullet_bank.bootstrap_profile.run_profile_setup")
    @patch("bootstrap_bullet_bank.run_full_pipeline", return_value=True)
    @patch("bootstrap_bullet_bank.run_ingestion")
    @patch("sys.argv", ["bootstrap_bullet_bank.py"])
    def test_without_dry_run_calls_full_pipeline(self, mock_run_ingestion, mock_run_full_pipeline, mock_profile_setup, mock_collect_secrets):
        mock_run_ingestion.return_value = {"extracted": 0, "attributed": 0, "flagged": 0, "certificates": 0}
        mock_profile_setup.return_value = {"full_name": "", "primary_roles": 0, "secondary_roles": 0, "recommendations_found": 0}
        bootstrap_bullet_bank.main()
        mock_run_ingestion.assert_called_once_with(dry_run=False)
        mock_run_full_pipeline.assert_called_once()


class TestMainCallsProfileSetup(unittest.TestCase):

    @patch("bootstrap_bullet_bank.bootstrap_profile.collect_secrets")
    @patch("bootstrap_bullet_bank.bootstrap_profile.run_profile_setup")
    @patch("bootstrap_bullet_bank.run_full_pipeline")
    @patch("bootstrap_bullet_bank.run_ingestion")
    @patch("sys.argv", ["bootstrap_bullet_bank.py"])
    def test_profile_setup_runs_between_ingestion_and_pipeline(
        self, mock_run_ingestion, mock_run_full_pipeline, mock_profile_setup, mock_collect_secrets,
    ):
        mock_run_ingestion.return_value = {"extracted": 0, "attributed": 0, "flagged": 0, "certificates": 0}
        mock_profile_setup.return_value = {"full_name": "", "primary_roles": 0, "secondary_roles": 0, "recommendations_found": 0}

        bootstrap_bullet_bank.main()

        mock_profile_setup.assert_called_once_with(dry_run=False)
        mock_run_ingestion.assert_called_once()
        mock_run_full_pipeline.assert_called_once()

    @patch("bootstrap_bullet_bank.bootstrap_profile.collect_secrets")
    @patch("bootstrap_bullet_bank.bootstrap_profile.run_profile_setup")
    @patch("bootstrap_bullet_bank.run_full_pipeline")
    @patch("bootstrap_bullet_bank.run_ingestion")
    @patch("sys.argv", ["bootstrap_bullet_bank.py", "--dry-run"])
    def test_profile_setup_receives_dry_run_flag(
        self, mock_run_ingestion, mock_run_full_pipeline, mock_profile_setup, mock_collect_secrets,
    ):
        mock_run_ingestion.return_value = {"extracted": 0, "attributed": 0, "flagged": 0, "certificates": 0}
        mock_profile_setup.return_value = {"full_name": "", "primary_roles": 0, "secondary_roles": 0, "recommendations_found": 0}

        bootstrap_bullet_bank.main()

        mock_profile_setup.assert_called_once_with(dry_run=True)
        mock_run_full_pipeline.assert_not_called()


class TestMainScope(unittest.TestCase):
    """--scope is "Update My Knowledge"'s way of running only part of the
    flow after a shared Phase 0 ingestion -- default "both" preserves the
    original cold-start behavior exactly (both prior test classes above
    already cover that implicitly by omitting --scope)."""

    @patch("bootstrap_bullet_bank.bootstrap_profile.collect_secrets")
    @patch("bootstrap_bullet_bank.bootstrap_profile.run_profile_setup")
    @patch("bootstrap_bullet_bank.run_full_pipeline")
    @patch("bootstrap_bullet_bank.run_ingestion")
    @patch("sys.argv", ["bootstrap_bullet_bank.py", "--scope", "bullets"])
    def test_scope_bullets_skips_profile_setup_but_still_ingests(
        self, mock_run_ingestion, mock_run_full_pipeline, mock_profile_setup, mock_collect_secrets,
    ):
        mock_run_ingestion.return_value = {"extracted": 0, "attributed": 0, "flagged": 0, "certificates": 0}
        bootstrap_bullet_bank.main()
        mock_run_ingestion.assert_called_once()
        mock_profile_setup.assert_not_called()
        mock_run_full_pipeline.assert_called_once()

    @patch("bootstrap_bullet_bank.bootstrap_profile.collect_secrets")
    @patch("bootstrap_bullet_bank.bootstrap_profile.run_profile_setup")
    @patch("bootstrap_bullet_bank.run_full_pipeline")
    @patch("bootstrap_bullet_bank.run_ingestion")
    @patch("sys.argv", ["bootstrap_bullet_bank.py", "--scope", "profile"])
    def test_scope_profile_skips_pipeline_but_still_ingests(
        self, mock_run_ingestion, mock_run_full_pipeline, mock_profile_setup, mock_collect_secrets,
    ):
        mock_run_ingestion.return_value = {"extracted": 0, "attributed": 0, "flagged": 0, "certificates": 0}
        mock_profile_setup.return_value = {"full_name": "", "primary_roles": 0, "secondary_roles": 0, "recommendations_found": 0}
        bootstrap_bullet_bank.main()
        mock_run_ingestion.assert_called_once()
        mock_profile_setup.assert_called_once()
        mock_run_full_pipeline.assert_not_called()

    @patch("bootstrap_bullet_bank.bootstrap_profile.collect_secrets")
    @patch("bootstrap_bullet_bank.bootstrap_profile.run_profile_setup")
    @patch("bootstrap_bullet_bank.run_full_pipeline")
    @patch("bootstrap_bullet_bank.run_ingestion")
    @patch("sys.argv", ["bootstrap_bullet_bank.py"])
    def test_default_scope_runs_both(
        self, mock_run_ingestion, mock_run_full_pipeline, mock_profile_setup, mock_collect_secrets,
    ):
        mock_run_ingestion.return_value = {"extracted": 0, "attributed": 0, "flagged": 0, "certificates": 0}
        mock_profile_setup.return_value = {"full_name": "", "primary_roles": 0, "secondary_roles": 0, "recommendations_found": 0}
        bootstrap_bullet_bank.main()
        mock_profile_setup.assert_called_once()
        mock_run_full_pipeline.assert_called_once()


if __name__ == "__main__":
    unittest.main()
