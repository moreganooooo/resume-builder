import os
import sys
import unittest
from unittest.mock import patch

SCRIPTS_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts")
sys.path.insert(0, SCRIPTS_DIR)

import questionary  # noqa: E402

import menu  # noqa: E402


class TestChoicesAndHandlers(unittest.TestCase):

    def test_tailor_pick_and_coverletter_pick_are_registered(self):
        # Reinstated 2026-07-23 as main-menu shortcuts straight into the
        # Browse & Manage Jobs picker (scoped by status) -- discoverability
        # for a first-time user matters more than avoiding a second entry
        # point into the same picker. See menu.py's _handle_tailor_pick/
        # _handle_coverletter_pick docstrings.
        values = [c.value for c in menu._CHOICES]
        self.assertIn("tailor_pick", values)
        self.assertIn("coverletter_pick", values)
        self.assertIn("tailor_pick", menu._HANDLERS)
        self.assertIn("coverletter_pick", menu._HANDLERS)
        self.assertIs(menu._HANDLERS["tailor_pick"], menu._handle_tailor_pick)
        self.assertIs(menu._HANDLERS["coverletter_pick"], menu._handle_coverletter_pick)

    def test_specific_jd_pickers_and_view_applications_are_gone(self):
        # Retired 2026-07-21 in favor of "Browse & Manage Jobs" -- see
        # IDEAS_ARCHIVE.md's browse/multi-select/compare writeup.
        values = [c.value for c in menu._CHOICES]
        for retired in ("evaluate_one", "tailor_one", "coverletter_one", "view_applications"):
            self.assertNotIn(retired, values)
            self.assertNotIn(retired, menu._HANDLERS)

    def test_choices_have_the_renamed_labels(self):
        labels = {c.value: c.title for c in menu._CHOICES}
        self.assertIn("Scan for New Postings", labels["scan"])
        self.assertIn("Check Posting Liveness", labels["liveness"])
        self.assertIn("Evaluate ALL Pending Roles", labels["evaluate_all"])
        self.assertIn("Customize Resume for ALL Pending Roles (Batch Run)", labels["tailor_all"])
        self.assertIn("Polish a Resume or Cover Letter with Gemini", labels["polish"])

    def test_browse_jobs_entry_is_registered(self):
        values = [c.value for c in menu._CHOICES]
        self.assertIn("browse_jobs", values)
        self.assertIn("browse_jobs", menu._HANDLERS)
        self.assertIs(menu._HANDLERS["browse_jobs"], menu._handle_browse_jobs)

    def test_career_dashboard_entry_is_registered(self):
        values = [c.value for c in menu._CHOICES]
        self.assertIn("career_dashboard", values)
        self.assertIn("career_dashboard", menu._HANDLERS)
        self.assertIs(menu._HANDLERS["career_dashboard"], menu._handle_career_dashboard)

    def test_bullet_bank_entry_is_registered(self):
        values = [c.value for c in menu._CHOICES]
        self.assertIn("bullet_bank", values)
        self.assertIn("bullet_bank", menu._HANDLERS)

    def test_maintenance_entry_is_registered(self):
        values = [c.value for c in menu._CHOICES]
        self.assertIn("maintenance", values)
        self.assertIn("maintenance", menu._HANDLERS)
        self.assertIs(menu._HANDLERS["maintenance"], menu._handle_maintenance)

    def test_help_entry_is_registered(self):
        values = [c.value for c in menu._CHOICES]
        self.assertIn("help", values)
        self.assertIn("help", menu._HANDLERS)
        self.assertIs(menu._HANDLERS["help"], menu._handle_help)

    def test_choices_are_grouped_with_labeled_separators(self):
        separator_lines = [c.line for c in menu._CHOICES if isinstance(c, questionary.Separator)]
        self.assertTrue(any("Discovery" in line for line in separator_lines))
        self.assertTrue(any("Evaluation" in line for line in separator_lines))
        self.assertTrue(any("Build" in line for line in separator_lines))
        self.assertTrue(any("Browse" in line for line in separator_lines))


class TestHandleScan(unittest.TestCase):

    @patch("menu.scan_module.run_scan", return_value=3)
    @patch("menu.questionary.select")
    def test_returns_true_when_postings_written(self, mock_select, mock_run):
        mock_select.return_value.ask.return_value = "both"
        self.assertTrue(menu._handle_scan())

    @patch("menu.scan_module.run_scan", return_value=0)
    @patch("menu.questionary.select")
    def test_returns_false_when_nothing_written(self, mock_select, mock_run):
        mock_select.return_value.ask.return_value = "both"
        self.assertFalse(menu._handle_scan())

    @patch("menu.scan_module.run_scan")
    @patch("menu.questionary.select")
    def test_returns_false_without_scanning_when_cancelled(self, mock_select, mock_run):
        mock_select.return_value.ask.return_value = None
        self.assertFalse(menu._handle_scan())
        mock_run.assert_not_called()

    @patch("menu.scan_module.run_scan", return_value=1)
    @patch("menu.questionary.select")
    def test_both_choice_passes_none_to_run_scan(self, mock_select, mock_run):
        mock_select.return_value.ask.return_value = "both"
        menu._handle_scan()
        mock_run.assert_called_once_with(None)

    @patch("menu.scan_module.run_scan", return_value=1)
    @patch("menu.questionary.select")
    def test_jobright_choice_passes_single_source_list(self, mock_select, mock_run):
        mock_select.return_value.ask.return_value = "jobright"
        menu._handle_scan()
        mock_run.assert_called_once_with(["jobright"])

    @patch("menu.scan_module.run_scan", return_value=1)
    @patch("menu.questionary.select")
    def test_linkedin_choice_passes_single_source_list(self, mock_select, mock_run):
        mock_select.return_value.ask.return_value = "linkedin"
        menu._handle_scan()
        mock_run.assert_called_once_with(["linkedin"])


class TestHandleLiveness(unittest.TestCase):

    @patch("menu.liveness_module.run_liveness_check")
    def test_returns_true_when_something_checked(self, mock_check):
        mock_check.return_value = {"active": 1, "likely_active": 0, "expired": 0, "uncertain": 0, "skipped": 2, "moved": 0}
        self.assertTrue(menu._handle_liveness())

    @patch("menu.liveness_module.run_liveness_check")
    def test_returns_false_when_nothing_checked(self, mock_check):
        mock_check.return_value = {"active": 0, "likely_active": 0, "expired": 0, "uncertain": 0, "skipped": 5, "moved": 0}
        self.assertFalse(menu._handle_liveness())

    @patch("menu.liveness_module.run_liveness_check")
    def test_returns_false_on_error(self, mock_check):
        mock_check.return_value = {"active": 0, "likely_active": 0, "expired": 0, "uncertain": 0, "skipped": 0, "moved": 0, "error": True}
        self.assertFalse(menu._handle_liveness())


class TestHandleEvaluateAll(unittest.TestCase):

    @patch("menu.jd_manager.get_pending_jds", return_value=[])
    def test_returns_false_when_no_pending(self, mock_pending):
        self.assertFalse(menu._handle_evaluate_all())

    @patch("menu.picker.should_proceed", return_value=False)
    @patch("menu.jd_manager.get_pending_jds", return_value=["jds/a.json"])
    def test_returns_false_when_declined(self, mock_pending, mock_proceed):
        with patch("menu.batch_evaluate.evaluate_all_pending") as mock_eval:
            self.assertFalse(menu._handle_evaluate_all())
        mock_eval.assert_not_called()

    @patch("menu.cli_art.render_fit_table")
    @patch("menu.batch_evaluate.evaluate_all_pending", return_value=[{"error": False}])
    @patch("menu.picker.should_proceed", return_value=True)
    @patch("menu.jd_manager.get_pending_jds", return_value=["jds/a.json"])
    def test_returns_true_when_results_returned(self, mock_pending, mock_proceed, mock_eval, mock_table):
        self.assertTrue(menu._handle_evaluate_all())

    @patch("menu.cli_art.render_fit_table")
    @patch("menu.batch_evaluate.evaluate_all_pending", return_value=[])
    @patch("menu.picker.should_proceed", return_value=True)
    @patch("menu.batch_evaluate.split_evaluated", return_value=(["jds/a.json"], ["jds/b.json"]))
    @patch("menu.jd_manager.get_pending_jds", return_value=["jds/a.json", "jds/b.json"])
    def test_confirms_against_and_evaluates_only_unscored(
        self, mock_pending, mock_split, mock_proceed, mock_eval, mock_table,
    ):
        menu._handle_evaluate_all()
        mock_proceed.assert_called_once_with(1, skip_confirm=False)
        mock_eval.assert_called_once_with(["jds/b.json"], skip_evaluated=False)

    @patch("menu.batch_evaluate.split_evaluated", return_value=(["jds/a.json"], []))
    @patch("menu.jd_manager.get_pending_jds", return_value=["jds/a.json"])
    def test_nothing_new_to_evaluate_returns_false_without_confirming(self, mock_pending, mock_split):
        with patch("menu.picker.should_proceed") as mock_proceed:
            self.assertFalse(menu._handle_evaluate_all())
        mock_proceed.assert_not_called()


class TestHandleTailorAll(unittest.TestCase):

    @patch("menu.jd_manager.get_pending_jds", return_value=[])
    def test_returns_false_when_no_pending(self, mock_pending):
        self.assertFalse(menu._handle_tailor_all())

    @patch("menu.picker.should_proceed", return_value=False)
    @patch("menu.jd_manager.get_pending_jds", return_value=["jds/a.json"])
    def test_returns_false_when_declined(self, mock_pending, mock_proceed):
        with patch("menu.orchestrator.run_pipeline") as mock_run:
            self.assertFalse(menu._handle_tailor_all())
        mock_run.assert_not_called()

    @patch("menu.orchestrator.run_pipeline", return_value=(2, 0))
    @patch("menu.picker.should_proceed", return_value=True)
    @patch("menu.jd_manager.get_pending_jds", return_value=["jds/a.json"])
    def test_returns_true_when_completed_gt_zero(self, mock_pending, mock_proceed, mock_run):
        self.assertTrue(menu._handle_tailor_all())

    @patch("menu.orchestrator.run_pipeline", return_value=(0, 1))
    @patch("menu.picker.should_proceed", return_value=True)
    @patch("menu.jd_manager.get_pending_jds", return_value=["jds/a.json"])
    def test_returns_false_when_completed_zero(self, mock_pending, mock_proceed, mock_run):
        self.assertFalse(menu._handle_tailor_all())


def _row(path="jds/a.json", status="Pending", company="Acme", title="Writer", **eval_kwargs):
    evaluation = {"composite_score": 4.0, "recommendation": "Strong pursue", **eval_kwargs}
    return {"path": path, "status": status, "company": company, "title": title,
            "evaluation": evaluation, "liveness": None}


class TestHandleBrowseJobs(unittest.TestCase):

    @patch("menu.picker.browse_and_select_jds", return_value=[])
    def test_returns_false_when_nothing_selected(self, mock_browse):
        self.assertFalse(menu._handle_browse_jobs())

    @patch("menu._browse_single_action", return_value=True)
    @patch("menu.picker.browse_and_select_jds")
    def test_single_selection_routes_to_single_action(self, mock_browse, mock_single):
        row = _row()
        mock_browse.return_value = [row]
        self.assertTrue(menu._handle_browse_jobs())
        mock_single.assert_called_once_with(row)

    @patch("menu._browse_bulk_action", return_value=True)
    @patch("menu.picker.browse_and_select_jds")
    def test_multi_selection_routes_to_bulk_action(self, mock_browse, mock_bulk):
        rows = [_row(path="jds/a.json"), _row(path="jds/b.json")]
        mock_browse.return_value = rows
        self.assertTrue(menu._handle_browse_jobs())
        mock_bulk.assert_called_once_with(rows)


class TestHandleTailorPick(unittest.TestCase):

    @patch("menu.picker.browse_and_select_jds", return_value=[])
    def test_returns_false_when_nothing_selected(self, mock_browse):
        self.assertFalse(menu._handle_tailor_pick())

    @patch("menu.orchestrator.run_pipeline")
    @patch("menu.picker.browse_and_select_jds")
    def test_scopes_picker_to_pending_and_tailors_each_selection(self, mock_browse, mock_run):
        rows = [_row(path="jds/a.json"), _row(path="jds/b.json")]
        mock_browse.return_value = rows
        mock_run.side_effect = [(1, 0), (0, 1)]
        self.assertTrue(menu._handle_tailor_pick())
        mock_browse.assert_called_once_with(statuses=["Pending"])
        self.assertEqual(mock_run.call_count, 2)

    @patch("menu.orchestrator.run_pipeline", return_value=(0, 1))
    @patch("menu.picker.browse_and_select_jds")
    def test_returns_false_when_nothing_completed(self, mock_browse, mock_run):
        mock_browse.return_value = [_row()]
        self.assertFalse(menu._handle_tailor_pick())


class TestHandleCoverletterPick(unittest.TestCase):

    @patch("menu.picker.browse_and_select_jds", return_value=[])
    def test_returns_false_when_nothing_selected(self, mock_browse):
        self.assertFalse(menu._handle_coverletter_pick())

    @patch("menu.orchestrator.ResumeEngine")
    @patch("menu.picker.browse_and_select_jds")
    def test_scopes_picker_to_completed_and_writes_each_cover_letter(self, mock_browse, mock_engine_cls):
        rows = [_row(path="jds/a.json", status="Completed"), _row(path="jds/b.json", status="Completed")]
        mock_browse.return_value = rows
        mock_engine_cls.return_value.build_tailored_coverletter.side_effect = [True, False]
        self.assertTrue(menu._handle_coverletter_pick())
        mock_browse.assert_called_once_with(statuses=["Completed"])
        self.assertEqual(mock_engine_cls.return_value.build_tailored_coverletter.call_count, 2)


class TestBrowseSingleAction(unittest.TestCase):

    @patch("menu.questionary.select")
    def test_back_returns_false(self, mock_select):
        mock_select.return_value.ask.return_value = "back"
        self.assertFalse(menu._browse_single_action(_row()))

    @patch("menu.questionary.select")
    def test_cancelled_prompt_returns_false(self, mock_select):
        mock_select.return_value.ask.return_value = None
        self.assertFalse(menu._browse_single_action(_row()))

    @patch("menu._print_evaluation_detail")
    @patch("menu.questionary.select")
    def test_view_details_loops_back_to_the_action_menu(self, mock_select, mock_print_detail):
        mock_select.return_value.ask.side_effect = ["details", "back"]
        self.assertFalse(menu._browse_single_action(_row()))
        mock_print_detail.assert_called_once()
        self.assertEqual(mock_select.call_count, 2)

    @patch("menu.orchestrator.run_pipeline", return_value=(1, 0))
    @patch("menu.questionary.select")
    def test_tailor_action_on_pending_jd(self, mock_select, mock_run):
        mock_select.return_value.ask.return_value = "tailor"
        row = _row(status="Pending", path="jds/a.json")
        self.assertTrue(menu._browse_single_action(row))
        mock_run.assert_called_once_with(jd_path="jds/a.json")

    @patch("menu.questionary.select")
    def test_pending_jd_offers_tailor_not_coverletter(self, mock_select):
        mock_select.return_value.ask.return_value = "back"
        menu._browse_single_action(_row(status="Pending"))
        choices = mock_select.call_args.kwargs["choices"]
        values = [c.value for c in choices]
        self.assertIn("tailor", values)
        self.assertNotIn("coverletter", values)

    @patch("menu.questionary.select")
    def test_completed_jd_offers_coverletter_not_tailor(self, mock_select):
        mock_select.return_value.ask.return_value = "back"
        menu._browse_single_action(_row(status="Completed"))
        choices = mock_select.call_args.kwargs["choices"]
        values = [c.value for c in choices]
        self.assertIn("coverletter", values)
        self.assertNotIn("tailor", values)

    @patch("menu.orchestrator.ResumeEngine")
    @patch("menu.questionary.select")
    def test_coverletter_action_on_completed_jd(self, mock_select, mock_engine_cls):
        mock_select.return_value.ask.return_value = "coverletter"
        mock_engine_cls.return_value.build_tailored_coverletter.return_value = {"company_name": "Acme"}
        row = _row(status="Completed", path="jds/a.json")
        self.assertTrue(menu._browse_single_action(row))
        mock_engine_cls.return_value.build_tailored_coverletter.assert_called_once_with("jds/a.json")

    @patch("menu.jd_manager.archive_jd")
    @patch("menu.questionary.select")
    def test_archive_action_moves_the_file_and_returns_true(self, mock_select, mock_archive):
        mock_select.return_value.ask.return_value = "archive"
        row = _row(path="jds/a.json")
        self.assertTrue(menu._browse_single_action(row))
        mock_archive.assert_called_once_with("jds/a.json")

    @patch("menu.questionary.select")
    def test_update_status_only_offered_for_completed(self, mock_select):
        mock_select.return_value.ask.return_value = "back"
        menu._browse_single_action(_row(status="Pending"))
        values = [c.value for c in mock_select.call_args.kwargs["choices"]]
        self.assertNotIn("update_status", values)

        menu._browse_single_action(_row(status="Completed"))
        values = [c.value for c in mock_select.call_args.kwargs["choices"]]
        self.assertIn("update_status", values)

    @patch("menu.questionary.select")
    def test_log_followup_only_offered_once_an_application_exists(self, mock_select):
        mock_select.return_value.ask.return_value = "back"
        row = _row(status="Completed")
        row["application"] = None
        menu._browse_single_action(row)
        values = [c.value for c in mock_select.call_args.kwargs["choices"]]
        self.assertNotIn("log_followup", values)

        row["application"] = {"status": "Applied"}
        menu._browse_single_action(row)
        values = [c.value for c in mock_select.call_args.kwargs["choices"]]
        self.assertIn("log_followup", values)

    @patch("menu.followup.compute_urgency")
    @patch("menu.questionary.select")
    def test_draft_followup_only_offered_when_overdue(self, mock_select, mock_urgency):
        mock_select.return_value.ask.return_value = "back"
        row = _row(status="Completed")
        row["application"] = {"status": "Applied"}

        mock_urgency.return_value = "waiting"
        menu._browse_single_action(row)
        values = [c.value for c in mock_select.call_args.kwargs["choices"]]
        self.assertNotIn("draft_followup", values)

        mock_urgency.return_value = "overdue"
        menu._browse_single_action(row)
        values = [c.value for c in mock_select.call_args.kwargs["choices"]]
        self.assertIn("draft_followup", values)

    @patch("menu.followup.compute_urgency", return_value="overdue")
    @patch("menu.questionary.select")
    def test_draft_followup_not_offered_without_an_application(self, mock_select, mock_urgency):
        mock_select.return_value.ask.return_value = "back"
        row = _row(status="Completed")
        row["application"] = None
        menu._browse_single_action(row)
        values = [c.value for c in mock_select.call_args.kwargs["choices"]]
        self.assertNotIn("draft_followup", values)

    @patch("menu.questionary.select")
    def test_outreach_offered_regardless_of_status(self, mock_select):
        mock_select.return_value.ask.return_value = "back"
        for status in ("Pending", "Completed"):
            menu._browse_single_action(_row(status=status))
            values = [c.value for c in mock_select.call_args.kwargs["choices"]]
            self.assertIn("outreach", values)

    @patch("menu._handle_update_application_status")
    @patch("menu.questionary.select")
    def test_update_status_action_loops_back(self, mock_select, mock_handler):
        mock_select.return_value.ask.side_effect = ["update_status", "back"]
        self.assertFalse(menu._browse_single_action(_row(status="Completed")))
        mock_handler.assert_called_once()

    @patch("menu._handle_log_followup")
    @patch("menu.questionary.select")
    def test_log_followup_action_loops_back(self, mock_select, mock_handler):
        row = _row(status="Completed")
        row["application"] = {"status": "Applied"}
        mock_select.return_value.ask.side_effect = ["log_followup", "back"]
        self.assertFalse(menu._browse_single_action(row))
        mock_handler.assert_called_once()

    @patch("menu._handle_draft_outreach")
    @patch("menu.questionary.select")
    def test_outreach_action_loops_back(self, mock_select, mock_handler):
        mock_select.return_value.ask.side_effect = ["outreach", "back"]
        self.assertFalse(menu._browse_single_action(_row()))
        mock_handler.assert_called_once()

    @patch("menu._handle_draft_followup")
    @patch("menu.followup.compute_urgency", return_value="overdue")
    @patch("menu.questionary.select")
    def test_draft_followup_action_loops_back(self, mock_select, mock_urgency, mock_handler):
        row = _row(status="Completed")
        row["application"] = {"status": "Applied"}
        mock_select.return_value.ask.side_effect = ["draft_followup", "back"]
        self.assertFalse(menu._browse_single_action(row))
        mock_handler.assert_called_once()


class TestHandleUpdateApplicationStatus(unittest.TestCase):

    @patch("menu.jd_manager.read_application_status")
    @patch("menu.jd_manager.save_application_status")
    @patch("menu.questionary.select")
    def test_saves_the_selected_status(self, mock_select, mock_save, mock_read):
        mock_select.return_value.ask.return_value = "Applied"
        mock_read.return_value = {"status": "Applied"}
        row = _row(path="jds/a.json", status="Completed")

        menu._handle_update_application_status(row)

        mock_save.assert_called_once_with("jds/a.json", "Applied")
        self.assertEqual(row["application"], {"status": "Applied"})

    @patch("menu.jd_manager.save_application_status")
    @patch("menu.questionary.select")
    def test_cancelled_prompt_saves_nothing(self, mock_select, mock_save):
        mock_select.return_value.ask.return_value = None
        menu._handle_update_application_status(_row())
        mock_save.assert_not_called()


class TestHandleLogFollowup(unittest.TestCase):

    @patch("menu.jd_manager.read_application_status")
    @patch("menu.jd_manager.save_application_status")
    def test_logs_a_followup_against_the_current_status(self, mock_save, mock_read):
        mock_read.return_value = {"status": "Applied", "follow_up_count": 1}
        row = _row(path="jds/a.json")
        row["application"] = {"status": "Applied"}

        menu._handle_log_followup(row)

        mock_save.assert_called_once_with("jds/a.json", "Applied", log_followup=True)

    @patch("menu.jd_manager.read_application_status", return_value={"status": "Applied"})
    @patch("menu.jd_manager.save_application_status")
    def test_defaults_to_applied_when_no_prior_status(self, mock_save, mock_read):
        row = _row(path="jds/a.json")
        row["application"] = None
        menu._handle_log_followup(row)
        mock_save.assert_called_once_with("jds/a.json", "Applied", log_followup=True)


class TestHandleDraftOutreach(unittest.TestCase):

    def setUp(self):
        self.tmp_dir = os.path.join(os.path.dirname(__file__), "_tmp_draft_outreach")
        os.makedirs(self.tmp_dir, exist_ok=True)

    def tearDown(self):
        for name in os.listdir(self.tmp_dir):
            os.remove(os.path.join(self.tmp_dir, name))
        os.rmdir(self.tmp_dir)

    def _write_jd(self, name, data):
        import json as json_module
        path = os.path.join(self.tmp_dir, name)
        with open(path, "w", encoding="utf-8") as f:
            json_module.dump(data, f)
        return path

    @patch("menu.orchestrator.find_jd_contacts", return_value=[])
    @patch("menu.cli_art.console.print")
    def test_prints_message_and_returns_when_no_contacts(self, mock_print, mock_find):
        path = self._write_jd("a.json", {"company_name": "Acme"})
        menu._handle_draft_outreach(_row(path=path))
        printed = mock_print.call_args[0][0]
        self.assertIn("No real contacts found", printed)

    @patch("menu.orchestrator.ResumeEngine")
    @patch("menu.orchestrator.find_jd_contacts")
    def test_single_contact_drafts_without_a_selection_prompt(self, mock_find, mock_engine_cls):
        path = self._write_jd("a.json", {"social_connections": [{"fullName": "Jen Dudik"}]})
        contact = {"name": "Jen Dudik", "title": "Director", "connection_type": "JobRight match", "linkedin_url": ""}
        mock_find.return_value = [contact]
        mock_engine_cls.return_value.draft_outreach_message.return_value = "Hi Jen, ..."

        with patch("menu.questionary.select") as mock_select:
            menu._handle_draft_outreach(_row(path=path))
            mock_select.assert_not_called()

        mock_engine_cls.return_value.draft_outreach_message.assert_called_once_with(path, contact)

    @patch("menu.orchestrator.ResumeEngine")
    @patch("menu.orchestrator.find_jd_contacts")
    def test_multiple_contacts_prompts_for_a_choice(self, mock_find, mock_engine_cls):
        path = self._write_jd("a.json", {"social_connections": []})
        contacts = [
            {"name": "Jen Dudik", "title": "Director", "connection_type": "JobRight match", "linkedin_url": ""},
            {"name": "Alex Chen", "title": "PM", "connection_type": "Personal company connection", "linkedin_url": ""},
        ]
        mock_find.return_value = contacts
        mock_engine_cls.return_value.draft_outreach_message.return_value = "Hi Alex, ..."

        with patch("menu.questionary.select") as mock_select:
            mock_select.return_value.ask.return_value = 1
            menu._handle_draft_outreach(_row(path=path))

        mock_engine_cls.return_value.draft_outreach_message.assert_called_once_with(path, contacts[1])

    @patch("menu.orchestrator.ResumeEngine")
    @patch("menu.orchestrator.find_jd_contacts")
    @patch("menu.cli_art.display_error")
    def test_shows_error_when_draft_fails(self, mock_error, mock_find, mock_engine_cls):
        path = self._write_jd("a.json", {"social_connections": [{"fullName": "Jen Dudik"}]})
        mock_find.return_value = [{"name": "Jen Dudik", "title": "", "connection_type": "JobRight match", "linkedin_url": ""}]
        mock_engine_cls.return_value.draft_outreach_message.return_value = None

        menu._handle_draft_outreach(_row(path=path))

        mock_error.assert_called_once()


class TestHandleDraftFollowup(unittest.TestCase):

    def setUp(self):
        self.tmp_dir = os.path.join(os.path.dirname(__file__), "_tmp_draft_followup")
        os.makedirs(self.tmp_dir, exist_ok=True)

    def tearDown(self):
        for name in os.listdir(self.tmp_dir):
            os.remove(os.path.join(self.tmp_dir, name))
        os.rmdir(self.tmp_dir)

    def _write_jd(self, name, data):
        import json as json_module
        path = os.path.join(self.tmp_dir, name)
        with open(path, "w", encoding="utf-8") as f:
            json_module.dump(data, f)
        return path

    @patch("menu.orchestrator.ResumeEngine")
    @patch("menu.orchestrator.find_jd_contacts", return_value=[])
    @patch("menu.questionary.confirm")
    def test_no_contacts_drafts_a_generic_message_without_a_prompt(self, mock_confirm, mock_find, mock_engine_cls):
        path = self._write_jd("a.json", {"company_name": "Acme"})
        mock_confirm.return_value.ask.return_value = False
        mock_engine_cls.return_value.draft_followup_message.return_value = "Hi there, ..."
        row = _row(path=path)
        row["application"] = {"status": "Applied", "follow_up_count": 0}

        with patch("menu.questionary.select") as mock_select:
            menu._handle_draft_followup(row)
            mock_select.assert_not_called()

        mock_engine_cls.return_value.draft_followup_message.assert_called_once_with(path, 0, None)

    @patch("menu.orchestrator.ResumeEngine")
    @patch("menu.orchestrator.find_jd_contacts")
    @patch("menu.questionary.confirm")
    def test_single_contact_drafts_without_a_selection_prompt(self, mock_confirm, mock_find, mock_engine_cls):
        path = self._write_jd("a.json", {"social_connections": [{"fullName": "Jen Dudik"}]})
        contact = {"name": "Jen Dudik", "title": "Director", "connection_type": "JobRight match", "linkedin_url": ""}
        mock_find.return_value = [contact]
        mock_confirm.return_value.ask.return_value = False
        mock_engine_cls.return_value.draft_followup_message.return_value = "Hi Jen, ..."
        row = _row(path=path)
        row["application"] = {"status": "Applied", "follow_up_count": 1}

        with patch("menu.questionary.select") as mock_select:
            menu._handle_draft_followup(row)
            mock_select.assert_not_called()

        mock_engine_cls.return_value.draft_followup_message.assert_called_once_with(path, 1, contact)

    @patch("menu.orchestrator.ResumeEngine")
    @patch("menu.orchestrator.find_jd_contacts")
    @patch("menu.questionary.confirm")
    def test_multiple_contacts_prompts_and_allows_generic_address(self, mock_confirm, mock_find, mock_engine_cls):
        path = self._write_jd("a.json", {"social_connections": []})
        contacts = [
            {"name": "Jen Dudik", "title": "Director", "connection_type": "JobRight match", "linkedin_url": ""},
            {"name": "Alex Chen", "title": "PM", "connection_type": "Personal company connection", "linkedin_url": ""},
        ]
        mock_find.return_value = contacts
        mock_confirm.return_value.ask.return_value = False
        mock_engine_cls.return_value.draft_followup_message.return_value = "Hi there, ..."
        row = _row(path=path)
        row["application"] = {"status": "Applied", "follow_up_count": 0}

        with patch("menu.questionary.select") as mock_select:
            mock_select.return_value.ask.return_value = -1
            menu._handle_draft_followup(row)

        mock_engine_cls.return_value.draft_followup_message.assert_called_once_with(path, 0, None)

    @patch("menu.orchestrator.ResumeEngine")
    @patch("menu.orchestrator.find_jd_contacts", return_value=[])
    @patch("menu.cli_art.display_error")
    def test_shows_error_when_draft_fails(self, mock_error, mock_find, mock_engine_cls):
        path = self._write_jd("a.json", {})
        mock_engine_cls.return_value.draft_followup_message.return_value = None
        row = _row(path=path)
        row["application"] = {"status": "Applied", "follow_up_count": 0}

        menu._handle_draft_followup(row)

        mock_error.assert_called_once()

    @patch("menu._handle_log_followup")
    @patch("menu.orchestrator.ResumeEngine")
    @patch("menu.orchestrator.find_jd_contacts", return_value=[])
    @patch("menu.questionary.confirm")
    def test_confirming_sent_logs_the_followup(self, mock_confirm, mock_find, mock_engine_cls, mock_log):
        path = self._write_jd("a.json", {})
        mock_confirm.return_value.ask.return_value = True
        mock_engine_cls.return_value.draft_followup_message.return_value = "Hi there, ..."
        row = _row(path=path)
        row["application"] = {"status": "Applied", "follow_up_count": 0}

        menu._handle_draft_followup(row)

        mock_log.assert_called_once_with(row)

    @patch("menu._handle_log_followup")
    @patch("menu.orchestrator.ResumeEngine")
    @patch("menu.orchestrator.find_jd_contacts", return_value=[])
    @patch("menu.questionary.confirm")
    def test_declining_sent_does_not_log_the_followup(self, mock_confirm, mock_find, mock_engine_cls, mock_log):
        path = self._write_jd("a.json", {})
        mock_confirm.return_value.ask.return_value = False
        mock_engine_cls.return_value.draft_followup_message.return_value = "Hi there, ..."
        row = _row(path=path)
        row["application"] = {"status": "Applied", "follow_up_count": 0}

        menu._handle_draft_followup(row)

        mock_log.assert_not_called()


class TestBrowseBulkAction(unittest.TestCase):

    @patch("menu.questionary.select")
    def test_back_returns_false(self, mock_select):
        mock_select.return_value.ask.return_value = "back"
        self.assertFalse(menu._browse_bulk_action([_row(), _row()]))

    @patch("menu.cli_art.render_comparison_table")
    @patch("menu.questionary.select")
    def test_compare_action_renders_the_comparison_table(self, mock_select, mock_render):
        mock_select.return_value.ask.return_value = "compare"
        rows = [_row(path="jds/a.json"), _row(path="jds/b.json")]
        self.assertTrue(menu._browse_bulk_action(rows))
        mock_render.assert_called_once_with(rows)

    @patch("menu.orchestrator.run_pipeline", return_value=(1, 0))
    @patch("menu.questionary.select")
    def test_tailor_action_skips_completed_rows(self, mock_select, mock_run):
        mock_select.return_value.ask.return_value = "tailor"
        rows = [_row(path="jds/a.json", status="Pending"), _row(path="jds/b.json", status="Completed")]
        self.assertTrue(menu._browse_bulk_action(rows))
        mock_run.assert_called_once_with(jd_path="jds/a.json")

    @patch("menu.questionary.select")
    def test_tailor_option_absent_when_all_selected_are_completed(self, mock_select):
        mock_select.return_value.ask.return_value = "back"
        rows = [_row(status="Completed"), _row(status="Completed")]
        menu._browse_bulk_action(rows)
        choices = mock_select.call_args.kwargs["choices"]
        self.assertNotIn("tailor", [c.value for c in choices])

    @patch("menu.questionary.select")
    def test_coverletter_option_present_only_when_all_selected_are_completed(self, mock_select):
        mock_select.return_value.ask.return_value = "back"
        rows = [_row(status="Pending"), _row(status="Completed")]
        menu._browse_bulk_action(rows)
        choices = mock_select.call_args.kwargs["choices"]
        self.assertNotIn("coverletter", [c.value for c in choices])

    @patch("menu.jd_manager.archive_jd")
    @patch("menu.questionary.select")
    def test_archive_action_archives_every_selected_row(self, mock_select, mock_archive):
        mock_select.return_value.ask.return_value = "archive"
        rows = [_row(path="jds/a.json"), _row(path="jds/b.json")]
        self.assertTrue(menu._browse_bulk_action(rows))
        self.assertEqual(mock_archive.call_count, 2)


class TestHandleCareerDashboard(unittest.TestCase):

    @patch("menu.dashboard_module.run", return_value=(True, ""))
    def test_always_returns_false(self, mock_run):
        self.assertFalse(menu._handle_career_dashboard())
        mock_run.assert_called_once()

    @patch("menu.cli_art.display_error")
    @patch("menu.dashboard_module.run", return_value=(False, "Go isn't installed"))
    def test_shows_error_on_failure(self, mock_run, mock_error):
        menu._handle_career_dashboard()
        mock_error.assert_called_once_with("Go isn't installed")


class TestHandlePolish(unittest.TestCase):

    @patch("menu.polish_module.run")
    def test_always_returns_false(self, mock_run):
        self.assertFalse(menu._handle_polish())


class TestHandleBulletBank(unittest.TestCase):

    @patch("menu.bullet_bank_menu.run_bullet_bank_menu")
    def test_always_returns_false(self, mock_run):
        self.assertFalse(menu._handle_bullet_bank())
        mock_run.assert_called_once()


class TestHandleRunDoctor(unittest.TestCase):

    @patch("menu.maintenance.record_run")
    @patch("menu.cli_art.render_doctor_report")
    @patch("menu.doctor.run_test_suite", return_value=(True, "OK"))
    @patch("menu.doctor.run_checks", return_value=[{"name": "x", "passed": True, "detail": "", "fix": ""}])
    @patch("menu.questionary.confirm")
    def test_runs_test_suite_when_confirmed(self, mock_confirm, mock_checks, mock_tests, mock_render, mock_record):
        mock_confirm.return_value.ask.return_value = True
        menu._handle_run_doctor()
        mock_tests.assert_called_once()
        mock_render.assert_called_once_with(mock_checks.return_value, (True, "OK"))
        mock_record.assert_called_once_with("doctor")

    @patch("menu.maintenance.record_run")
    @patch("menu.cli_art.render_doctor_report")
    @patch("menu.doctor.run_test_suite")
    @patch("menu.doctor.run_checks", return_value=[])
    @patch("menu.questionary.confirm")
    def test_skips_test_suite_when_declined(self, mock_confirm, mock_checks, mock_tests, mock_render, mock_record):
        mock_confirm.return_value.ask.return_value = False
        menu._handle_run_doctor()
        mock_tests.assert_not_called()
        mock_render.assert_called_once_with([], None)


class TestHandleMaintenance(unittest.TestCase):

    @patch("menu.maintenance.get_last_run", return_value=None)
    @patch("menu.questionary.select")
    def test_back_returns_false(self, mock_select, mock_last_run):
        mock_select.return_value.ask.return_value = "back"
        self.assertFalse(menu._handle_maintenance())

    @patch("menu.maintenance.get_last_run", return_value=None)
    @patch("menu.questionary.select")
    def test_cancelled_prompt_returns_false(self, mock_select, mock_last_run):
        mock_select.return_value.ask.return_value = None
        self.assertFalse(menu._handle_maintenance())

    @patch("menu.maintenance.get_last_run", return_value=None)
    @patch("menu.questionary.select")
    def test_never_run_label_when_no_prior_run(self, mock_select, mock_last_run):
        mock_select.return_value.ask.return_value = "back"
        menu._handle_maintenance()
        choices = mock_select.call_args.kwargs["choices"]
        self.assertIn("never run", choices[0].title)

    @patch("menu.maintenance.get_last_run", return_value="2026-07-22T10:00:00")
    @patch("menu.questionary.select")
    def test_last_run_date_shown_when_recorded(self, mock_select, mock_last_run):
        mock_select.return_value.ask.return_value = "back"
        menu._handle_maintenance()
        choices = mock_select.call_args.kwargs["choices"]
        self.assertIn("2026-07-22", choices[0].title)

    @patch("menu._handle_run_doctor")
    @patch("menu.maintenance.get_last_run", return_value=None)
    @patch("menu.questionary.select")
    def test_doctor_choice_loops_back_to_the_submenu(self, mock_select, mock_last_run, mock_run_doctor):
        mock_select.return_value.ask.side_effect = ["doctor", "back"]
        self.assertFalse(menu._handle_maintenance())
        mock_run_doctor.assert_called_once()
        self.assertEqual(mock_select.call_count, 2)

    @patch("menu._handle_check_updates")
    @patch("menu.maintenance.get_last_run", return_value=None)
    @patch("menu.questionary.select")
    def test_check_updates_choice_loops_back_to_the_submenu(self, mock_select, mock_last_run, mock_check_updates):
        mock_select.return_value.ask.side_effect = ["check_updates", "back"]
        self.assertFalse(menu._handle_maintenance())
        mock_check_updates.assert_called_once()
        self.assertEqual(mock_select.call_count, 2)


class TestPromptForUpdate(unittest.TestCase):

    @patch("menu.git_update.check_for_updates")
    @patch("menu.git_update.has_uncommitted_changes", return_value=True)
    def test_skips_the_check_entirely_when_dirty(self, mock_dirty, mock_check):
        menu._prompt_for_update()
        mock_check.assert_not_called()

    @patch("menu.git_update.check_for_updates", return_value=(False, "Already up to date"))
    @patch("menu.git_update.has_uncommitted_changes", return_value=False)
    def test_says_nothing_when_already_up_to_date(self, mock_dirty, mock_check):
        with patch("menu.cli_art.console.print") as mock_print:
            menu._prompt_for_update()
            mock_print.assert_not_called()

    @patch("menu.git_update.pull_updates")
    @patch("menu.git_update.check_for_updates", return_value=(True, "2 new commit(s) available"))
    @patch("menu.git_update.has_uncommitted_changes", return_value=False)
    @patch("menu.questionary.confirm")
    def test_pulls_when_confirmed(self, mock_confirm, mock_dirty, mock_check, mock_pull):
        mock_confirm.return_value.ask.return_value = True
        mock_pull.return_value = (True, "Updated")
        menu._prompt_for_update()
        mock_pull.assert_called_once()

    @patch("menu.git_update.pull_updates")
    @patch("menu.git_update.check_for_updates", return_value=(True, "2 new commit(s) available"))
    @patch("menu.git_update.has_uncommitted_changes", return_value=False)
    @patch("menu.questionary.confirm")
    def test_does_not_pull_when_declined(self, mock_confirm, mock_dirty, mock_check, mock_pull):
        mock_confirm.return_value.ask.return_value = False
        menu._prompt_for_update()
        mock_pull.assert_not_called()


class TestHandleCheckUpdates(unittest.TestCase):

    @patch("menu.git_update.check_for_updates")
    @patch("menu.git_update.has_uncommitted_changes", return_value=True)
    def test_returns_false_and_skips_the_check_when_dirty(self, mock_dirty, mock_check):
        self.assertFalse(menu._handle_check_updates())
        mock_check.assert_not_called()

    @patch("menu.git_update.check_for_updates", return_value=(False, "Already up to date"))
    @patch("menu.git_update.has_uncommitted_changes", return_value=False)
    def test_returns_false_when_already_up_to_date(self, mock_dirty, mock_check):
        self.assertFalse(menu._handle_check_updates())

    @patch("menu.git_update.pull_updates", return_value=(True, "Updated"))
    @patch("menu.git_update.check_for_updates", return_value=(True, "1 new commit(s) available"))
    @patch("menu.git_update.has_uncommitted_changes", return_value=False)
    @patch("menu.questionary.confirm")
    def test_returns_true_on_confirmed_successful_pull(self, mock_confirm, mock_dirty, mock_check, mock_pull):
        mock_confirm.return_value.ask.return_value = True
        self.assertTrue(menu._handle_check_updates())

    @patch("menu.git_update.pull_updates", return_value=(False, "Pull failed: conflict"))
    @patch("menu.git_update.check_for_updates", return_value=(True, "1 new commit(s) available"))
    @patch("menu.git_update.has_uncommitted_changes", return_value=False)
    @patch("menu.questionary.confirm")
    def test_returns_false_on_failed_pull(self, mock_confirm, mock_dirty, mock_check, mock_pull):
        mock_confirm.return_value.ask.return_value = True
        self.assertFalse(menu._handle_check_updates())

    @patch("menu.git_update.pull_updates")
    @patch("menu.git_update.check_for_updates", return_value=(True, "1 new commit(s) available"))
    @patch("menu.git_update.has_uncommitted_changes", return_value=False)
    @patch("menu.questionary.confirm")
    def test_does_not_pull_when_declined(self, mock_confirm, mock_dirty, mock_check, mock_pull):
        mock_confirm.return_value.ask.return_value = False
        menu._handle_check_updates()
        mock_pull.assert_not_called()


class TestHandleHelp(unittest.TestCase):

    @patch("menu.cli_art.display_help")
    def test_always_returns_false(self, mock_display):
        self.assertFalse(menu._handle_help())
        mock_display.assert_called_once()


class TestChainContent(unittest.TestCase):

    def test_chain_matches_the_designed_pipeline_order(self):
        self.assertEqual(menu._CHAIN["scan"], [("Check Liveness", "liveness")])
        self.assertEqual(menu._CHAIN["liveness"], [("Evaluate All JDs", "evaluate_all")])
        self.assertEqual(
            menu._CHAIN["evaluate_all"],
            [("Customize Resume", "tailor_all"), ("Browse & Manage Jobs", "browse_jobs")],
        )
        self.assertEqual(
            menu._CHAIN["tailor_all"],
            [("Browse & Manage Jobs", "browse_jobs"), ("Polish with Gemini", "polish")],
        )

    def test_polish_has_no_chain_entry(self):
        self.assertNotIn("polish", menu._CHAIN)

    def test_browse_jobs_has_no_chain_entry(self):
        self.assertNotIn("browse_jobs", menu._CHAIN)


class TestRunWithChain(unittest.TestCase):

    @patch("menu.questionary.select")
    def test_no_op_handler_skips_the_prompt(self, mock_select):
        with patch.dict(menu._HANDLERS, {"fake": lambda: False}, clear=False), \
             patch.dict(menu._CHAIN, {"fake": [("Next", "somewhere")]}, clear=False):
            menu._run_with_chain("fake", {})
        mock_select.assert_not_called()

    @patch("menu.questionary.select")
    def test_handler_with_no_chain_entry_skips_the_prompt(self, mock_select):
        with patch.dict(menu._HANDLERS, {"fake": lambda: True}, clear=False):
            menu._run_with_chain("fake", {})
        mock_select.assert_not_called()

    @patch("menu.questionary.select")
    def test_chain_prompt_appends_back_to_menu_choice(self, mock_select):
        mock_select.return_value.ask.return_value = "__back__"
        with patch.dict(menu._HANDLERS, {"fake": lambda: True}, clear=False), \
             patch.dict(menu._CHAIN, {"fake": [("Next", "somewhere")]}, clear=False):
            menu._run_with_chain("fake", {})
        choices = mock_select.call_args.kwargs["choices"]
        # "somewhere" has no _CHAIN_ICONS entry -> falls back to plain
        # label; "__back__" always gets the utility icon.
        self.assertEqual([c.title for c in choices], ["Next", f"{menu.theme.ICONS['utility']}  Back to Menu"])
        self.assertEqual([c.value for c in choices], ["somewhere", "__back__"])

    @patch("menu.questionary.select")
    def test_back_to_menu_stops_recursion(self, mock_select):
        calls = []
        mock_select.return_value.ask.return_value = "__back__"
        with patch.dict(menu._HANDLERS, {"fake": lambda: calls.append("fake") or True}, clear=False), \
             patch.dict(menu._CHAIN, {"fake": [("Next", "somewhere")]}, clear=False):
            menu._run_with_chain("fake", {})
        self.assertEqual(calls, ["fake"])

    @patch("menu.questionary.select")
    def test_cancelled_prompt_stops_recursion(self, mock_select):
        calls = []
        mock_select.return_value.ask.return_value = None
        with patch.dict(menu._HANDLERS, {"fake": lambda: calls.append("fake") or True}, clear=False), \
             patch.dict(menu._CHAIN, {"fake": [("Next", "somewhere")]}, clear=False):
            menu._run_with_chain("fake", {})
        self.assertEqual(calls, ["fake"])

    @patch("menu.questionary.select")
    def test_picking_a_next_step_recurses_into_it(self, mock_select):
        calls = []
        mock_select.return_value.ask.return_value = "second"
        with patch.dict(
            menu._HANDLERS,
            {
                "first": lambda: calls.append("first") or True,
                "second": lambda: calls.append("second") or False,
            },
            clear=False,
        ), patch.dict(menu._CHAIN, {"first": [("Do Second", "second")]}, clear=False):
            menu._run_with_chain("first", {})
        self.assertEqual(calls, ["first", "second"])


class TestSessionSummary(unittest.TestCase):

    @patch("menu.questionary.select")
    def test_successful_action_increments_its_labeled_count(self, mock_select):
        session_stats = {}
        with patch.dict(menu._HANDLERS, {"tailor_all": lambda: True}, clear=False), \
             patch.dict(menu._CHAIN, {}, clear=True):
            menu._run_with_chain("tailor_all", session_stats)
        self.assertEqual(session_stats, {"resumes tailored": 1})

    @patch("menu.questionary.select")
    def test_no_op_action_does_not_increment(self, mock_select):
        session_stats = {}
        with patch.dict(menu._HANDLERS, {"tailor_all": lambda: False}, clear=False):
            menu._run_with_chain("tailor_all", session_stats)
        self.assertEqual(session_stats, {})

    @patch("menu.questionary.select")
    def test_unlabeled_action_does_not_increment(self, mock_select):
        session_stats = {}
        with patch.dict(menu._HANDLERS, {"polish": lambda: True}, clear=False):
            menu._run_with_chain("polish", session_stats)
        self.assertEqual(session_stats, {})

    def test_empty_summary_string(self):
        self.assertEqual(menu._session_summary({}), "No actions taken this session.")

    def test_summary_joins_multiple_labels(self):
        summary = menu._session_summary({"resumes tailored": 3, "cover letters written": 2})
        self.assertIn("3 resumes tailored", summary)
        self.assertIn("2 cover letters written", summary)
        self.assertIn("Nice work.", summary)


if __name__ == "__main__":
    unittest.main()
