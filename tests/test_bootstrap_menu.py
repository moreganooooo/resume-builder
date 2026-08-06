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
        with patch("bootstrap_menu.bootstrap_profile.PROFILE_YML_PATH", os.path.join(self.tmp_dir, "nope.yml")), \
             patch("bootstrap_menu._phase0_status", return_value=("Up to date", "")):
            status, _ = bootstrap_menu._phase05_status()
        self.assertEqual(status, "Never run")

    def test_profile_yml_without_cv_md_is_in_progress(self):
        profile_yml = os.path.join(self.tmp_dir, "profile.yml")
        with open(profile_yml, "w", encoding="utf-8") as f:
            f.write("x")
        with patch("bootstrap_menu.bootstrap_profile.PROFILE_YML_PATH", profile_yml), \
             patch("bootstrap_menu.bootstrap_profile.CV_MD_PATH", os.path.join(self.tmp_dir, "cv.md")), \
             patch("bootstrap_menu._phase0_status", return_value=("Up to date", "")):
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
             patch("bootstrap_menu.bootstrap_profile.CV_MD_PATH", cv_md), \
             patch("bootstrap_menu._phase0_status", return_value=("Up to date", "")):
            status, _ = bootstrap_menu._phase05_status()
        self.assertEqual(status, "Up to date")

    def test_locked_when_phase0_not_up_to_date(self):
        # B16: even with profile.yml and cv.md already on disk (e.g. a
        # second, newer source document dropped in after the first
        # completed run), Phase 0.5 must not report "Up to date" ahead of
        # Phase 0 actually being complete again.
        profile_yml = os.path.join(self.tmp_dir, "profile.yml")
        cv_md = os.path.join(self.tmp_dir, "cv.md")
        for path in (profile_yml, cv_md):
            with open(path, "w", encoding="utf-8") as f:
                f.write("x")
        with patch("bootstrap_menu.bootstrap_profile.PROFILE_YML_PATH", profile_yml), \
             patch("bootstrap_menu.bootstrap_profile.CV_MD_PATH", cv_md), \
             patch("bootstrap_menu._phase0_status", return_value=("Never run", "no source documents uploaded yet")):
            status, detail = bootstrap_menu._phase05_status()
        self.assertEqual(status, "Locked")
        self.assertIn("Step 0", detail)


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


class TestRunPhase0DeferredKey(unittest.TestCase):
    # B16(b): _collect_secret_now_or_later() lets a user defer the API key
    # ("later") -- collect_secrets() correctly reports that via
    # gemini_key_set=False, but _run_phase0() used to discard it and run
    # run_ingestion() anyway, which is exactly how a 403 got checkpointed
    # as "done" with nothing extracted.

    def setUp(self):
        self.tmp_dir = tempfile.mkdtemp()
        with open(os.path.join(self.tmp_dir, "resume.pdf"), "w", encoding="utf-8") as f:
            f.write("x")

    def tearDown(self):
        shutil.rmtree(self.tmp_dir, ignore_errors=True)

    def test_deferred_key_stops_before_ingestion(self):
        with patch("bootstrap_menu.bootstrap_bullet_bank.SOURCE_DOCS_DIR", self.tmp_dir), \
             patch("bootstrap_menu.bootstrap_profile.collect_secrets",
                   return_value={"gemini_key_set": False, "jobright_cookie_set": False}), \
             patch("bootstrap_menu.bootstrap_bullet_bank.run_ingestion") as mock_ingest:
            result = bootstrap_menu._run_phase0()
        mock_ingest.assert_not_called()
        self.assertFalse(result)

    def test_key_already_set_proceeds_to_ingestion(self):
        with patch("bootstrap_menu.bootstrap_bullet_bank.SOURCE_DOCS_DIR", self.tmp_dir), \
             patch("bootstrap_menu.bootstrap_profile.collect_secrets",
                   return_value={"gemini_key_set": True, "jobright_cookie_set": False}), \
             patch("bootstrap_menu.bootstrap_bullet_bank.run_ingestion",
                   return_value={"extracted": 0, "attributed": 0, "flagged": 0, "certificates": 0, "failed": 0}) as mock_ingest:
            result = bootstrap_menu._run_phase0()
        mock_ingest.assert_called_once()
        self.assertTrue(result)


class TestRunPhase05Gating(unittest.TestCase):
    # B16(b)+(c): Phase 0.5 must not run ahead of Phase 0 (generate_tag_
    # taxonomy() firing against an empty achievements string), and must not
    # proceed past a deferred API key either -- the same discard-the-return-
    # value bug _run_phase0() had.

    def test_blocked_when_phase0_not_complete(self):
        with patch("bootstrap_menu._phase0_status", return_value=("In progress", "1/2 processed (1 pending)")), \
             patch("bootstrap_menu.bootstrap_profile.collect_secrets") as mock_secrets, \
             patch("bootstrap_menu.bootstrap_profile.run_profile_setup") as mock_setup:
            result = bootstrap_menu._run_phase05()
        mock_secrets.assert_not_called()
        mock_setup.assert_not_called()
        self.assertFalse(result)

    def test_blocked_when_key_deferred(self):
        with patch("bootstrap_menu._phase0_status", return_value=("Up to date", "1 document(s) processed")), \
             patch("bootstrap_menu.bootstrap_profile.collect_secrets",
                   return_value={"gemini_key_set": False, "jobright_cookie_set": False}), \
             patch("bootstrap_menu.bootstrap_profile.run_profile_setup") as mock_setup:
            result = bootstrap_menu._run_phase05()
        mock_setup.assert_not_called()
        self.assertFalse(result)

    def test_runs_when_phase0_complete_and_key_set(self):
        with patch("bootstrap_menu._phase0_status", return_value=("Up to date", "1 document(s) processed")), \
             patch("bootstrap_menu.bootstrap_profile.collect_secrets",
                   return_value={"gemini_key_set": True, "jobright_cookie_set": False}), \
             patch("bootstrap_menu.bootstrap_profile.run_profile_setup") as mock_setup:
            result = bootstrap_menu._run_phase05()
        mock_setup.assert_called_once()
        self.assertTrue(result)


if __name__ == "__main__":
    unittest.main()
