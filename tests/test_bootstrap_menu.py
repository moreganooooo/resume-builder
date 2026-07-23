import os
import shutil
import sys
import tempfile
import unittest
from unittest.mock import patch

import questionary

SCRIPTS_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts")
sys.path.insert(0, SCRIPTS_DIR)

import bootstrap_menu  # noqa: E402


class TestPhase0Status(unittest.TestCase):

    def setUp(self):
        self.tmp_dir = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.tmp_dir, ignore_errors=True)

    def test_missing_dir_is_never_run(self):
        with patch("bootstrap_menu.bootstrap_bullet_bank.SOURCE_DOCS_DIR", os.path.join(self.tmp_dir, "nope")):
            status, _ = bootstrap_menu._phase0_status()
        self.assertEqual(status, "Never run")

    def test_empty_dir_is_never_run(self):
        with patch("bootstrap_menu.bootstrap_bullet_bank.SOURCE_DOCS_DIR", self.tmp_dir):
            status, _ = bootstrap_menu._phase0_status()
        self.assertEqual(status, "Never run")

    def test_partial_checkpoint_is_in_progress(self):
        for name in ("a.pdf", "b.pdf"):
            with open(os.path.join(self.tmp_dir, name), "w", encoding="utf-8") as f:
                f.write("x")
        with patch("bootstrap_menu.bootstrap_bullet_bank.SOURCE_DOCS_DIR", self.tmp_dir), \
             patch("bootstrap_menu.bootstrap_bullet_bank._load_checkpoint",
                   return_value={"a.pdf": {"status": "done"}}):
            status, detail = bootstrap_menu._phase0_status()
        self.assertEqual(status, "In progress")
        self.assertEqual(detail, "1/2 processed (1 pending)")

    def test_all_done_is_up_to_date(self):
        with open(os.path.join(self.tmp_dir, "a.pdf"), "w", encoding="utf-8") as f:
            f.write("x")
        with patch("bootstrap_menu.bootstrap_bullet_bank.SOURCE_DOCS_DIR", self.tmp_dir), \
             patch("bootstrap_menu.bootstrap_bullet_bank._load_checkpoint",
                   return_value={"a.pdf": {"status": "done"}}):
            status, _ = bootstrap_menu._phase0_status()
        self.assertEqual(status, "Up to date")


class TestPhase05Status(unittest.TestCase):

    def setUp(self):
        self.tmp_dir = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.tmp_dir, ignore_errors=True)

    def test_missing_profile_yml_is_never_run(self):
        with patch("bootstrap_menu.bootstrap_profile.PROFILE_YML_PATH", os.path.join(self.tmp_dir, "nope.yml")):
            status, _ = bootstrap_menu._phase05_status()
        self.assertEqual(status, "Never run")

    def test_profile_yml_without_cv_md_is_in_progress(self):
        profile_yml = os.path.join(self.tmp_dir, "profile.yml")
        with open(profile_yml, "w", encoding="utf-8") as f:
            f.write("x")
        with patch("bootstrap_menu.bootstrap_profile.PROFILE_YML_PATH", profile_yml), \
             patch("bootstrap_menu.bootstrap_profile.CV_MD_PATH", os.path.join(self.tmp_dir, "cv.md")):
            status, detail = bootstrap_menu._phase05_status()
        self.assertEqual(status, "In progress")
        self.assertIn("cv.md", detail)

    def test_both_present_is_up_to_date(self):
        profile_yml = os.path.join(self.tmp_dir, "profile.yml")
        cv_md = os.path.join(self.tmp_dir, "cv.md")
        for path in (profile_yml, cv_md):
            with open(path, "w", encoding="utf-8") as f:
                f.write("x")
        with patch("bootstrap_menu.bootstrap_profile.PROFILE_YML_PATH", profile_yml), \
             patch("bootstrap_menu.bootstrap_profile.CV_MD_PATH", cv_md):
            status, _ = bootstrap_menu._phase05_status()
        self.assertEqual(status, "Up to date")


class TestBuildChoices(unittest.TestCase):

    def test_phase0_and_phase05_come_before_the_six_stages(self):
        choices = [c for c in bootstrap_menu._build_choices() if isinstance(c, questionary.Choice)]
        keys = [c.value for c in choices]
        self.assertEqual(keys[0], "phase0")
        self.assertEqual(keys[1], "phase05")
        self.assertEqual(keys[2:8], ["audit", "cluster", "rewrite", "audit_keepers", "score_gems", "embed"])
        self.assertEqual(keys[-1], "__back__")


class TestRunBootstrapMenu(unittest.TestCase):

    @patch("bootstrap_menu.cli_art.render_bullet_bank_status")
    @patch("bootstrap_menu.questionary.select")
    def test_back_returns_false(self, mock_select, mock_render):
        mock_select.return_value.ask.return_value = "__back__"
        self.assertFalse(bootstrap_menu.run_bootstrap_menu())

    @patch("bootstrap_menu.cli_art.render_bullet_bank_status")
    @patch("bootstrap_menu.questionary.select")
    def test_cancelled_prompt_returns_false(self, mock_select, mock_render):
        mock_select.return_value.ask.return_value = None
        self.assertFalse(bootstrap_menu.run_bootstrap_menu())

    @patch("bootstrap_menu.cli_art.render_bullet_bank_status")
    @patch("bootstrap_menu.questionary.select")
    def test_running_phase0_then_back_returns_true(self, mock_select, mock_render):
        mock_select.return_value.ask.side_effect = ["phase0", "__back__"]
        with patch("bootstrap_menu._run_phase0") as mock_run:
            result = bootstrap_menu.run_bootstrap_menu()
        mock_run.assert_called_once()
        self.assertTrue(result)

    @patch("bootstrap_menu.cli_art.render_bullet_bank_status")
    @patch("bootstrap_menu.questionary.select")
    def test_running_phase05_then_back_returns_true(self, mock_select, mock_render):
        mock_select.return_value.ask.side_effect = ["phase05", "__back__"]
        with patch("bootstrap_menu._run_phase05") as mock_run:
            result = bootstrap_menu.run_bootstrap_menu()
        mock_run.assert_called_once()
        self.assertTrue(result)

    @patch("bootstrap_menu.cli_art.render_bullet_bank_status")
    @patch("bootstrap_menu.questionary.select")
    def test_choosing_a_pipeline_stage_dispatches_to_bullet_bank_menu(self, mock_select, mock_render):
        mock_select.return_value.ask.side_effect = ["audit", "__back__"]
        with patch("bootstrap_menu.bullet_bank_menu._handle_choice") as mock_handle:
            result = bootstrap_menu.run_bootstrap_menu()
        mock_handle.assert_called_once_with("audit")
        self.assertTrue(result)


class TestRunPhase0EmptyFolder(unittest.TestCase):

    def setUp(self):
        self.tmp_dir = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.tmp_dir, ignore_errors=True)

    def test_empty_folder_prints_instructions_and_does_not_ingest(self):
        with patch("bootstrap_menu.bootstrap_bullet_bank.SOURCE_DOCS_DIR", self.tmp_dir), \
             patch("bootstrap_menu.bootstrap_bullet_bank.run_ingestion") as mock_ingest, \
             patch("menu._print_source_docs_instructions") as mock_instructions:
            bootstrap_menu._run_phase0()
        mock_ingest.assert_not_called()
        mock_instructions.assert_called_once_with(self.tmp_dir)


if __name__ == "__main__":
    unittest.main()
