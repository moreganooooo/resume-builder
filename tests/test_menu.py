import os
import re
import sys
import unittest
from unittest.mock import patch

SCRIPTS_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts"
)
sys.path.insert(0, SCRIPTS_DIR)

import menu  # noqa: E402
import questionary  # noqa: E402
import theme  # noqa: E402


def _title_text(title) -> str:
    """Flatten a questionary Choice title -- either a plain string or the
    [(style, text), ...] tuple-list format menu.py uses for colored icons --
    into a plain string for substring assertions."""
    if isinstance(title, str):
        return title
    return "".join(text for _, text in title)


def _icon_glyph(title):
    """Extract just the icon glyph from a _icon_title()-built title (its
    first (style, text) tuple), or None for a plain-string title with no
    icon at all. Distinct from _title_text(), which flattens icon+label
    together and so can't tell two same-icon items apart from two
    different-icon items with visually similar flattened text."""
    if isinstance(title, str):
        return None
    return title[0][1]


class TestChoicesAndHandlers(unittest.TestCase):
    # As of the 2026-08 menu collapse (design-audit-approved 7-item tree),
    # every leaf action except "bullet_bank"/"settings_upkeep" (which open
    # their own self-contained submenu, unchanged) moved out of
    # menu._build_choices() into one of the category submenu builders
    # below. See menu.py's _build_choices() docstring for the full tree.

    def test_main_menu_has_the_approved_seven_item_tree(self):
        # questionary.Separator is (surprisingly) a subclass of Choice, so
        # this excludes it explicitly rather than filtering "isinstance
        # Choice" (a no-op against Separator).
        values = [
            c.value
            for c in menu._build_choices()
            if not isinstance(c, questionary.Separator)
        ]
        self.assertEqual(
            values,
            [
                "bootstrap",
                "find_jobs",
                "build_documents",
                "bullet_bank",
                "track_followup",
                "settings_upkeep",
                "help",
                "exit",
            ],
        )

    def test_tailor_pick_and_coverletter_pick_are_registered(self):
        # Reinstated 2026-07-23 as shortcuts straight into the Browse &
        # Manage Jobs picker (scoped by status) -- discoverability for a
        # first-time user matters more than avoiding a second entry point
        # into the same picker. Now live under Build Documents. See
        # menu.py's _handle_tailor_pick/_handle_coverletter_pick docstrings.
        values = [c.value for c in menu._build_build_documents_choices()]
        self.assertIn("tailor_pick", values)
        self.assertIn("coverletter_pick", values)
        self.assertIn("tailor_pick", menu._HANDLERS)
        self.assertIn("coverletter_pick", menu._HANDLERS)
        self.assertIs(menu._HANDLERS["tailor_pick"], menu._handle_tailor_pick)
        self.assertIs(menu._HANDLERS["coverletter_pick"], menu._handle_coverletter_pick)

    def test_specific_jd_pickers_and_view_applications_are_gone(self):
        # Retired 2026-07-21 in favor of "Browse & Manage Jobs" -- see
        # IDEAS_ARCHIVE.md's browse/multi-select/compare writeup.
        all_values = (
            [c.value for c in menu._build_choices()]
            + [c.value for c in menu._build_find_jobs_choices()]
            + [c.value for c in menu._build_build_documents_choices()]
            + [c.value for c in menu._build_track_followup_choices()]
            + [c.value for c in menu._build_settings_upkeep_choices()]
        )
        for retired in (
            "evaluate_one",
            "tailor_one",
            "coverletter_one",
            "view_applications",
        ):
            self.assertNotIn(retired, all_values)
            self.assertNotIn(retired, menu._HANDLERS)

    def test_find_jobs_submenu_has_the_renamed_labels(self):
        labels = {
            c.value: _title_text(c.title) for c in menu._build_find_jobs_choices()
        }
        self.assertIn("Scan for New Jobs", labels["scan"])
        self.assertIn("Check Job Posting Liveness", labels["liveness"])
        self.assertIn("Evaluate Pending Roles", labels["evaluate_all"])

    def test_build_documents_submenu_has_the_renamed_labels(self):
        labels = {
            c.value: _title_text(c.title) for c in menu._build_build_documents_choices()
        }
        self.assertIn(
            "Customize Resume for All Pending Roles (Batch Run)", labels["tailor_all"]
        )
        self.assertIn("Polish a Resume or Cover Letter With Gemini", labels["polish"])

    def test_browse_jobs_entry_is_registered(self):
        values = [c.value for c in menu._build_track_followup_choices()]
        self.assertIn("browse_jobs", values)
        self.assertIn("browse_jobs", menu._HANDLERS)
        self.assertIs(menu._HANDLERS["browse_jobs"], menu._handle_browse_jobs)

    def test_career_dashboard_entry_is_registered(self):
        values = [c.value for c in menu._build_track_followup_choices()]
        self.assertIn("career_dashboard", values)
        self.assertIn("career_dashboard", menu._HANDLERS)
        self.assertIs(menu._HANDLERS["career_dashboard"], menu._handle_career_dashboard)

    def test_bullet_bank_entry_is_registered(self):
        values = [c.value for c in menu._build_choices()]
        self.assertIn("bullet_bank", values)
        self.assertIn("bullet_bank", menu._HANDLERS)

    def test_settings_upkeep_entry_is_registered(self):
        values = [c.value for c in menu._build_choices()]
        self.assertIn("settings_upkeep", values)
        self.assertIn("settings_upkeep", menu._HANDLERS)
        self.assertIs(menu._HANDLERS["settings_upkeep"], menu._handle_settings_upkeep)
        # "maintenance" was this entry's value before the 2026-08 rename.
        self.assertNotIn("maintenance", values)
        self.assertNotIn("maintenance", menu._HANDLERS)

    def test_help_entry_is_registered(self):
        values = [c.value for c in menu._build_choices()]
        self.assertIn("help", values)
        self.assertIn("help", menu._HANDLERS)
        self.assertIs(menu._HANDLERS["help"], menu._handle_help)

    def test_choices_reflect_icon_set_changes_without_reimport(self):
        # Regression for a bug where the choice list was a module-level
        # constant built once at import time: theme.set_icon_set() (called
        # by _confirm_icon_set() right after the first-launch prompt) is
        # documented to take effect for "the rest of the same session," but
        # the Main Menu itself kept rendering whatever icon set was active
        # at import time regardless. _build_choices() must be rebuilt per
        # call so it reads theme.ICONS fresh every time.
        original = theme.icon_set_name()
        try:
            theme.set_icon_set("nerd")
            nerd_title = _title_text(
                next(c for c in menu._build_choices() if c.value == "bullet_bank").title
            )
            theme.set_icon_set("unicode")
            unicode_title = _title_text(
                next(c for c in menu._build_choices() if c.value == "bullet_bank").title
            )
            self.assertIn(
                theme._UNICODE_ICONS["bullet_bank"], unicode_title
            )  # theme.py's unicode bullet_bank glyph

            self.assertNotEqual(nerd_title, unicode_title)
        finally:
            theme.set_icon_set(original)

    def test_submenu_choices_are_also_rebuilt_fresh(self):
        # Same regression as above, extended to every new category
        # submenu builder -- each must read theme.ICONS fresh per call
        # too, not just the main menu.
        original = theme.icon_set_name()
        try:
            for builder in (
                menu._build_find_jobs_choices,
                menu._build_build_documents_choices,
                menu._build_track_followup_choices,
                menu._build_settings_upkeep_choices,
            ):
                theme.set_icon_set("nerd")
                nerd_title = _title_text(builder()[0].title)
                theme.set_icon_set("unicode")
                unicode_title = _title_text(builder()[0].title)
                self.assertNotEqual(nerd_title, unicode_title, builder.__name__)
        finally:
            theme.set_icon_set(original)

    def test_every_submenu_ends_with_a_back_choice(self):
        for builder in (
            menu._build_find_jobs_choices,
            menu._build_build_documents_choices,
            menu._build_track_followup_choices,
            menu._build_settings_upkeep_choices,
        ):
            choices = [c for c in builder() if isinstance(c, questionary.Choice)]
            self.assertEqual(choices[-1].value, "back", builder.__name__)

    def test_no_two_items_in_the_same_list_share_an_icon(self):
        # Regression for "Exit" and "Settings & Upkeep" both rendering the
        # same wrench glyph in the Main Menu (both used icon="utility") --
        # visually indistinguishable even though they're unrelated actions.
        # Sharing an icon across DIFFERENT lists (e.g. "discovery" used by
        # both "Find Jobs" and its own "Scan for New Jobs" submenu item) is
        # fine and intentional -- the bug is two different items in the
        # SAME visible list looking identical.
        for builder in (
            menu._build_choices,
            menu._build_find_jobs_choices,
            menu._build_build_documents_choices,
            menu._build_track_followup_choices,
            menu._build_settings_upkeep_choices,
        ):
            seen = {}
            for c in builder():
                if not isinstance(c, questionary.Choice):
                    continue
                icon = _icon_glyph(c.title)
                if icon is None:
                    continue
                self.assertNotIn(
                    icon,
                    seen,
                    f"{builder.__name__}: {c.value!r} shares an icon with "
                    f"{seen.get(icon)!r}",
                )
                seen[icon] = c.value


class TestBuildDocumentsEmptyStateBreadcrumb(unittest.TestCase):
    """The "never get stuck" prompt shown when there are no roles to build
    from. Both of its options dispatch through _run_with_chain, which does
    a bare `_HANDLERS[value]()` -- an unrecognised value is a KeyError in
    the user's face, not a no-op, and nothing else in the suite would catch
    a typo'd action name."""

    def test_every_breadcrumb_choice_maps_to_a_real_handler(self):
        import inspect

        src = inspect.getsource(menu._handle_build_documents)
        values = re.findall(r'value="([a-z_]+)"', src)
        self.assertTrue(
            values, "breadcrumb choices not found -- did the empty state move?"
        )
        for value in values:
            if value == "back":
                continue
            self.assertIn(
                value,
                menu._HANDLERS,
                f"_handle_build_documents offers {value!r}, which is not a "
                f"_HANDLERS key -- _run_with_chain would raise KeyError. "
                f"Valid keys include 'scan' and 'add_manual_jd'.",
            )


class TestHandleScan(unittest.TestCase):

    @patch("menu.scan_module.run_scan", return_value=3)
    @patch("menu.questionary.select")
    def test_returns_true_when_postings_written(self, mock_select, mock_run):
        mock_select.return_value.ask.return_value = "all"
        self.assertTrue(menu._handle_scan())

    @patch("menu.scan_module.run_scan", return_value=0)
    @patch("menu.questionary.select")
    def test_returns_false_when_nothing_written(self, mock_select, mock_run):
        mock_select.return_value.ask.return_value = "all"
        self.assertFalse(menu._handle_scan())

    @patch("menu.scan_module.run_scan")
    @patch("menu.questionary.select")
    def test_returns_false_without_scanning_when_cancelled(self, mock_select, mock_run):
        mock_select.return_value.ask.return_value = None
        self.assertFalse(menu._handle_scan())
        mock_run.assert_not_called()

    @patch("menu.scan_module.run_scan", return_value=1)
    @patch("menu.questionary.select")
    def test_all_choice_passes_none_to_run_scan(self, mock_select, mock_run):
        mock_select.return_value.ask.return_value = "all"
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
        mock_check.return_value = {
            "active": 1,
            "likely_active": 0,
            "expired": 0,
            "uncertain": 0,
            "skipped": 2,
            "moved": 0,
        }
        self.assertTrue(menu._handle_liveness())

    @patch("menu.liveness_module.run_liveness_check")
    def test_returns_false_when_nothing_checked(self, mock_check):
        mock_check.return_value = {
            "active": 0,
            "likely_active": 0,
            "expired": 0,
            "uncertain": 0,
            "skipped": 5,
            "moved": 0,
        }
        self.assertFalse(menu._handle_liveness())

    @patch("menu.liveness_module.run_liveness_check")
    def test_returns_false_on_error(self, mock_check):
        mock_check.return_value = {
            "active": 0,
            "likely_active": 0,
            "expired": 0,
            "uncertain": 0,
            "skipped": 0,
            "moved": 0,
            "error": True,
        }
        self.assertFalse(menu._handle_liveness())


class TestHandleEvaluateAll(unittest.TestCase):

    @patch("menu.picker.unevaluated_roles", return_value=([], []))
    @patch("menu.jd_manager.get_pending_jds", return_value=[])
    def test_returns_false_when_no_pending(self, mock_pending, mock_unevaluated):
        self.assertFalse(menu._handle_evaluate_all())

    @patch("menu.picker.should_proceed", return_value=False)
    @patch("menu.picker.unevaluated_roles", return_value=(["jds/a.json"], []))
    @patch("menu.jd_manager.get_pending_jds", return_value=["jds/a.json"])
    def test_returns_false_when_declined(
        self, mock_pending, mock_unevaluated, mock_proceed
    ):
        with patch("menu.batch_evaluate.evaluate_all_pending") as mock_eval:
            self.assertFalse(menu._handle_evaluate_all())
        mock_eval.assert_not_called()

    @patch("menu.cli_art.render_fit_table")
    @patch("menu.batch_evaluate.evaluate_all_pending", return_value=[{"error": False}])
    @patch("menu.picker.should_proceed", return_value=True)
    @patch("menu.picker.unevaluated_roles", return_value=(["jds/a.json"], []))
    @patch("menu.jd_manager.get_pending_jds", return_value=["jds/a.json"])
    def test_returns_true_when_results_returned(
        self, mock_pending, mock_unevaluated, mock_proceed, mock_eval, mock_table
    ):
        self.assertTrue(menu._handle_evaluate_all())

    @patch("menu.cli_art.render_fit_table")
    @patch("menu.batch_evaluate.evaluate_all_pending", return_value=[])
    @patch("menu.picker.should_proceed", return_value=True)
    @patch("menu.picker.unevaluated_roles", return_value=(["jds/b.json"], []))
    @patch("menu.jd_manager.get_pending_jds", return_value=["jds/a.json", "jds/b.json"])
    def test_confirms_against_and_evaluates_only_unscored(
        self,
        mock_pending,
        mock_unevaluated,
        mock_proceed,
        mock_eval,
        mock_table,
    ):
        menu._handle_evaluate_all()
        mock_proceed.assert_called_once_with(1, skip_confirm=False)
        mock_eval.assert_called_once_with(["jds/b.json"], skip_evaluated=False)

    @patch("menu.cli_art.render_fit_table")
    @patch("menu.batch_evaluate.evaluate_all_pending", return_value=[])
    @patch("menu.picker.should_proceed", return_value=True)
    @patch(
        "menu.picker.unevaluated_roles",
        return_value=(["jds/b.json"], ["hash-only-row"]),
    )
    @patch("menu.jd_manager.get_pending_jds", return_value=["jds/b.json"])
    def test_evaluates_database_only_roles_too(
        self,
        mock_pending,
        mock_unevaluated,
        mock_proceed,
        mock_eval,
        mock_table,
    ):
        """Most pending jobs are database-only scan rows with no JD file.
        Building the work list from get_pending_jds() counted them in the
        banner and then silently skipped them here -- 627 of a 1,337
        backlog for this profile."""
        menu._handle_evaluate_all()
        mock_proceed.assert_called_once_with(2, skip_confirm=False)
        mock_eval.assert_called_once_with(
            ["jds/b.json", "hash-only-row"], skip_evaluated=False
        )

    @patch("menu.picker.unevaluated_roles", return_value=([], []))
    @patch("menu.jd_manager.get_pending_jds", return_value=["jds/a.json"])
    def test_nothing_new_to_evaluate_returns_false_without_confirming(
        self, mock_pending, mock_unevaluated
    ):
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
    def test_returns_true_when_completed_gt_zero(
        self, mock_pending, mock_proceed, mock_run
    ):
        self.assertTrue(menu._handle_tailor_all())

    @patch("menu.orchestrator.run_pipeline", return_value=(0, 1))
    @patch("menu.picker.should_proceed", return_value=True)
    @patch("menu.jd_manager.get_pending_jds", return_value=["jds/a.json"])
    def test_returns_false_when_completed_zero(
        self, mock_pending, mock_proceed, mock_run
    ):
        self.assertFalse(menu._handle_tailor_all())


def _row(
    path="jds/a.json", status="Pending", company="Acme", title="Writer", **eval_kwargs
):
    evaluation = {
        "composite_score": 4.0,
        "recommendation": "Strong pursue",
        **eval_kwargs,
    }
    return {
        "path": path,
        "status": status,
        "company": company,
        "title": title,
        "evaluation": evaluation,
        "liveness": None,
    }


class TestHandleBrowseJobs(unittest.TestCase):

    @patch("menu.dashboard_module.run", return_value=(False, "No applications found"))
    def test_returns_false_when_dashboard_fails(self, mock_dashboard):
        self.assertFalse(menu._handle_browse_jobs())

    @patch("menu.dashboard_module.run", return_value=(True, ""))
    def test_returns_true_when_dashboard_succeeds(self, mock_dashboard):
        self.assertTrue(menu._handle_browse_jobs())
        mock_dashboard.assert_called_once()


class TestHandleTailorPick(unittest.TestCase):

    @patch("menu.picker.browse_and_select_jds", return_value=[])
    def test_returns_false_when_nothing_selected(self, mock_browse):
        self.assertFalse(menu._handle_tailor_pick())

    @patch("menu.orchestrator.run_pipeline")
    @patch("menu.picker.browse_and_select_jds")
    def test_scopes_picker_to_pending_and_tailors_each_selection(
        self, mock_browse, mock_run
    ):
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
    def test_scopes_picker_to_completed_and_writes_each_cover_letter(
        self, mock_browse, mock_engine_cls
    ):
        rows = [
            _row(path="jds/a.json", status="Completed"),
            _row(path="jds/b.json", status="Completed"),
        ]
        mock_browse.return_value = rows
        mock_engine_cls.return_value.build_tailored_coverletter.side_effect = [
            True,
            False,
        ]
        self.assertTrue(menu._handle_coverletter_pick())
        mock_browse.assert_called_once_with(statuses=["Completed"])
        self.assertEqual(
            mock_engine_cls.return_value.build_tailored_coverletter.call_count, 2
        )


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
    def test_view_details_loops_back_to_the_action_menu(
        self, mock_select, mock_print_detail
    ):
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

    @patch("menu._prompt_for_referral_if_unset")
    @patch("menu.orchestrator.ResumeEngine")
    @patch("menu.questionary.select")
    def test_coverletter_action_on_completed_jd(
        self, mock_select, mock_engine_cls, mock_prompt_referral
    ):
        mock_select.return_value.ask.return_value = "coverletter"
        mock_engine_cls.return_value.build_tailored_coverletter.return_value = {
            "company_name": "Acme"
        }
        row = _row(status="Completed", path="jds/a.json")
        self.assertTrue(menu._browse_single_action(row))
        mock_engine_cls.return_value.build_tailored_coverletter.assert_called_once_with(
            "jds/a.json"
        )
        mock_prompt_referral.assert_called_once_with("jds/a.json")

    @patch("menu.cli_art.confirm_destructive", return_value=True)
    @patch("menu.jd_manager.archive_jd")
    @patch("menu.questionary.select")
    def test_archive_action_moves_the_file_and_returns_true(
        self, mock_select, mock_archive, mock_confirm
    ):
        mock_select.return_value.ask.return_value = "archive"
        row = _row(path="jds/a.json")
        self.assertTrue(menu._browse_single_action(row))
        mock_archive.assert_called_once_with("jds/a.json")
        mock_confirm.assert_called_once_with("Archive", "Acme")

    @patch("menu.cli_art.confirm_destructive", return_value=False)
    @patch("menu.jd_manager.archive_jd")
    @patch("menu.questionary.select")
    def test_declining_archive_confirmation_does_not_archive(
        self, mock_select, mock_archive, mock_confirm
    ):
        mock_select.return_value.ask.side_effect = ["archive", "back"]
        row = _row(path="jds/a.json")
        self.assertFalse(menu._browse_single_action(row))
        mock_archive.assert_not_called()

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
    def test_draft_followup_not_offered_without_an_application(
        self, mock_select, mock_urgency
    ):
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
    def test_draft_followup_action_loops_back(
        self, mock_select, mock_urgency, mock_handler
    ):
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

    @patch(
        "menu.jd_manager.read_application_status", return_value={"status": "Applied"}
    )
    @patch("menu.jd_manager.save_application_status")
    def test_defaults_to_applied_when_no_prior_status(self, mock_save, mock_read):
        row = _row(path="jds/a.json")
        row["application"] = None
        menu._handle_log_followup(row)
        mock_save.assert_called_once_with("jds/a.json", "Applied", log_followup=True)


class TestPromptForReferralIfUnset(unittest.TestCase):

    @patch(
        "menu.jd_manager.read_referral",
        return_value={"text": "Jane Doe", "saved_at": "2026-08-17T00:00:00"},
    )
    @patch("menu.questionary.text")
    @patch("menu.jd_manager.save_referral")
    def test_skips_prompt_when_referral_already_saved(
        self, mock_save, mock_text, mock_read
    ):
        menu._prompt_for_referral_if_unset("jds/a.json")
        mock_text.assert_not_called()
        mock_save.assert_not_called()

    @patch("menu.jd_manager.read_referral", return_value=None)
    @patch("menu.questionary.text")
    @patch("menu.jd_manager.save_referral")
    def test_saves_answer_when_provided(self, mock_save, mock_text, mock_read):
        mock_text.return_value.ask.return_value = "Jane Doe, former coworker"
        menu._prompt_for_referral_if_unset("jds/a.json")
        mock_save.assert_called_once_with("jds/a.json", "Jane Doe, former coworker")

    @patch("menu.jd_manager.read_referral", return_value=None)
    @patch("menu.questionary.text")
    @patch("menu.jd_manager.save_referral")
    def test_skipping_the_prompt_saves_nothing(self, mock_save, mock_text, mock_read):
        mock_text.return_value.ask.return_value = ""
        menu._prompt_for_referral_if_unset("jds/a.json")
        mock_save.assert_not_called()


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
    def test_single_contact_drafts_without_a_selection_prompt(
        self, mock_find, mock_engine_cls
    ):
        path = self._write_jd(
            "a.json", {"social_connections": [{"fullName": "Jen Dudik"}]}
        )
        contact = {
            "name": "Jen Dudik",
            "title": "Director",
            "connection_type": "JobRight match",
            "linkedin_url": "",
        }
        mock_find.return_value = [contact]
        mock_engine_cls.return_value.draft_outreach_message.return_value = "Hi Jen, ..."

        with patch("menu.questionary.select") as mock_select:
            menu._handle_draft_outreach(_row(path=path))
            mock_select.assert_not_called()

        mock_engine_cls.return_value.draft_outreach_message.assert_called_once_with(
            path, contact
        )

    @patch("menu.orchestrator.ResumeEngine")
    @patch("menu.orchestrator.find_jd_contacts")
    def test_multiple_contacts_prompts_for_a_choice(self, mock_find, mock_engine_cls):
        path = self._write_jd("a.json", {"social_connections": []})
        contacts = [
            {
                "name": "Jen Dudik",
                "title": "Director",
                "connection_type": "JobRight match",
                "linkedin_url": "",
            },
            {
                "name": "Alex Chen",
                "title": "PM",
                "connection_type": "Personal company connection",
                "linkedin_url": "",
            },
        ]
        mock_find.return_value = contacts
        mock_engine_cls.return_value.draft_outreach_message.return_value = (
            "Hi Alex, ..."
        )

        with patch("menu.questionary.select") as mock_select:
            mock_select.return_value.ask.return_value = 1
            menu._handle_draft_outreach(_row(path=path))

        mock_engine_cls.return_value.draft_outreach_message.assert_called_once_with(
            path, contacts[1]
        )

    @patch("menu.orchestrator.ResumeEngine")
    @patch("menu.orchestrator.find_jd_contacts")
    @patch("menu.cli_art.display_error")
    def test_shows_error_when_draft_fails(self, mock_error, mock_find, mock_engine_cls):
        path = self._write_jd(
            "a.json", {"social_connections": [{"fullName": "Jen Dudik"}]}
        )
        mock_find.return_value = [
            {
                "name": "Jen Dudik",
                "title": "",
                "connection_type": "JobRight match",
                "linkedin_url": "",
            }
        ]
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
    @patch("menu.charm_prompt.confirm")
    def test_no_contacts_drafts_a_generic_message_without_a_prompt(
        self, mock_confirm, mock_find, mock_engine_cls
    ):
        path = self._write_jd("a.json", {"company_name": "Acme"})
        mock_confirm.return_value = False
        mock_engine_cls.return_value.draft_followup_message.return_value = (
            "Hi there, ..."
        )
        row = _row(path=path)
        row["application"] = {"status": "Applied", "follow_up_count": 0}

        with patch("menu.questionary.select") as mock_select:
            menu._handle_draft_followup(row)
            mock_select.assert_not_called()

        mock_engine_cls.return_value.draft_followup_message.assert_called_once_with(
            path, 0, None
        )

    @patch("menu.orchestrator.ResumeEngine")
    @patch("menu.orchestrator.find_jd_contacts")
    @patch("menu.charm_prompt.confirm")
    def test_single_contact_drafts_without_a_selection_prompt(
        self, mock_confirm, mock_find, mock_engine_cls
    ):
        path = self._write_jd(
            "a.json", {"social_connections": [{"fullName": "Jen Dudik"}]}
        )
        contact = {
            "name": "Jen Dudik",
            "title": "Director",
            "connection_type": "JobRight match",
            "linkedin_url": "",
        }
        mock_find.return_value = [contact]
        mock_confirm.return_value = False
        mock_engine_cls.return_value.draft_followup_message.return_value = "Hi Jen, ..."
        row = _row(path=path)
        row["application"] = {"status": "Applied", "follow_up_count": 1}

        with patch("menu.questionary.select") as mock_select:
            menu._handle_draft_followup(row)
            mock_select.assert_not_called()

        mock_engine_cls.return_value.draft_followup_message.assert_called_once_with(
            path, 1, contact
        )

    @patch("menu.orchestrator.ResumeEngine")
    @patch("menu.orchestrator.find_jd_contacts")
    @patch("menu.charm_prompt.confirm")
    def test_multiple_contacts_prompts_and_allows_generic_address(
        self, mock_confirm, mock_find, mock_engine_cls
    ):
        path = self._write_jd("a.json", {"social_connections": []})
        contacts = [
            {
                "name": "Jen Dudik",
                "title": "Director",
                "connection_type": "JobRight match",
                "linkedin_url": "",
            },
            {
                "name": "Alex Chen",
                "title": "PM",
                "connection_type": "Personal company connection",
                "linkedin_url": "",
            },
        ]
        mock_find.return_value = contacts
        mock_confirm.return_value = False
        mock_engine_cls.return_value.draft_followup_message.return_value = (
            "Hi there, ..."
        )
        row = _row(path=path)
        row["application"] = {"status": "Applied", "follow_up_count": 0}

        with patch("menu.questionary.select") as mock_select:
            mock_select.return_value.ask.return_value = -1
            menu._handle_draft_followup(row)

        mock_engine_cls.return_value.draft_followup_message.assert_called_once_with(
            path, 0, None
        )

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
    @patch("menu.charm_prompt.confirm")
    def test_confirming_sent_logs_the_followup(
        self, mock_confirm, mock_find, mock_engine_cls, mock_log
    ):
        path = self._write_jd("a.json", {})
        mock_confirm.return_value = True
        mock_engine_cls.return_value.draft_followup_message.return_value = (
            "Hi there, ..."
        )
        row = _row(path=path)
        row["application"] = {"status": "Applied", "follow_up_count": 0}

        menu._handle_draft_followup(row)

        mock_log.assert_called_once_with(row)

    @patch("menu._handle_log_followup")
    @patch("menu.orchestrator.ResumeEngine")
    @patch("menu.orchestrator.find_jd_contacts", return_value=[])
    @patch("menu.charm_prompt.confirm")
    def test_declining_sent_does_not_log_the_followup(
        self, mock_confirm, mock_find, mock_engine_cls, mock_log
    ):
        path = self._write_jd("a.json", {})
        mock_confirm.return_value = False
        mock_engine_cls.return_value.draft_followup_message.return_value = (
            "Hi there, ..."
        )
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
    def test_compare_action_renders_the_comparison_table(
        self, mock_select, mock_render
    ):
        mock_select.return_value.ask.return_value = "compare"
        rows = [_row(path="jds/a.json"), _row(path="jds/b.json")]
        self.assertTrue(menu._browse_bulk_action(rows))
        mock_render.assert_called_once_with(rows)

    @patch("menu.orchestrator.run_pipeline", return_value=(1, 0))
    @patch("menu.questionary.select")
    def test_tailor_action_skips_completed_rows(self, mock_select, mock_run):
        mock_select.return_value.ask.return_value = "tailor"
        rows = [
            _row(path="jds/a.json", status="Pending"),
            _row(path="jds/b.json", status="Completed"),
        ]
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
    def test_coverletter_option_present_only_when_all_selected_are_completed(
        self, mock_select
    ):
        mock_select.return_value.ask.return_value = "back"
        rows = [_row(status="Pending"), _row(status="Completed")]
        menu._browse_bulk_action(rows)
        choices = mock_select.call_args.kwargs["choices"]
        self.assertNotIn("coverletter", [c.value for c in choices])

    @patch("menu.cli_art.confirm_destructive", return_value=True)
    @patch("menu.jd_manager.archive_jd")
    @patch("menu.questionary.select")
    def test_archive_action_archives_every_selected_row(
        self, mock_select, mock_archive, mock_confirm
    ):
        mock_select.return_value.ask.return_value = "archive"
        rows = [_row(path="jds/a.json"), _row(path="jds/b.json")]
        self.assertTrue(menu._browse_bulk_action(rows))
        self.assertEqual(mock_archive.call_count, 2)

    @patch("menu.cli_art.confirm_destructive", return_value=False)
    @patch("menu.jd_manager.archive_jd")
    @patch("menu.questionary.select")
    def test_declining_archive_confirmation_archives_nothing(
        self, mock_select, mock_archive, mock_confirm
    ):
        mock_select.return_value.ask.return_value = "archive"
        rows = [_row(path="jds/a.json"), _row(path="jds/b.json")]
        self.assertFalse(menu._browse_bulk_action(rows))
        mock_archive.assert_not_called()


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
    @patch(
        "menu.doctor.run_checks",
        return_value=[{"name": "x", "passed": True, "detail": "", "fix": ""}],
    )
    @patch("menu.charm_prompt.confirm")
    def test_runs_test_suite_when_confirmed(
        self, mock_confirm, mock_checks, mock_tests, mock_render, mock_record
    ):
        mock_confirm.return_value = True
        menu._handle_run_doctor()
        mock_tests.assert_called_once()
        mock_render.assert_called_once_with(mock_checks.return_value, (True, "OK"))
        mock_record.assert_called_once_with("doctor")

    @patch("menu.maintenance.record_run")
    @patch("menu.cli_art.render_doctor_report")
    @patch("menu.doctor.run_test_suite")
    @patch("menu.doctor.run_checks", return_value=[])
    @patch("menu.charm_prompt.confirm")
    def test_skips_test_suite_when_declined(
        self, mock_confirm, mock_checks, mock_tests, mock_render, mock_record
    ):
        mock_confirm.return_value = False
        menu._handle_run_doctor()
        mock_tests.assert_not_called()
        mock_render.assert_called_once_with([], None)


class TestHandleSettingsUpkeep(unittest.TestCase):
    # Renamed from TestHandleMaintenance/_handle_maintenance in the 2026-08
    # menu collapse -- same function (_handle_settings_upkeep), same
    # loop-until-Back shape. Choice titles are now icon-paired
    # ([(style, text), ...] tuple-lists, see _icon_title()) rather than
    # plain strings, so assertions flatten them via _title_text() first.

    @patch("menu.maintenance.get_last_run", return_value=None)
    @patch("menu.questionary.select")
    def test_back_returns_false(self, mock_select, mock_last_run):
        mock_select.return_value.ask.return_value = "back"
        self.assertFalse(menu._handle_settings_upkeep())

    @patch("menu.maintenance.get_last_run", return_value=None)
    @patch("menu.questionary.select")
    def test_cancelled_prompt_returns_false(self, mock_select, mock_last_run):
        mock_select.return_value.ask.return_value = None
        self.assertFalse(menu._handle_settings_upkeep())

    @patch("menu.maintenance.get_last_run", return_value=None)
    @patch("menu.questionary.select")
    def test_never_run_label_when_no_prior_run(self, mock_select, mock_last_run):
        mock_select.return_value.ask.return_value = "back"
        menu._handle_settings_upkeep()
        choices = mock_select.call_args.kwargs["choices"]
        self.assertIn("never run", _title_text(choices[0].title))

    @patch("menu.maintenance.get_last_run", return_value="2026-07-22T10:00:00")
    @patch("menu.questionary.select")
    def test_last_run_date_shown_when_recorded(self, mock_select, mock_last_run):
        mock_select.return_value.ask.return_value = "back"
        menu._handle_settings_upkeep()
        choices = mock_select.call_args.kwargs["choices"]
        self.assertIn("2026-07-22", _title_text(choices[0].title))

    @patch("menu._handle_run_doctor")
    @patch("menu.maintenance.get_last_run", return_value=None)
    @patch("menu.questionary.select")
    def test_doctor_choice_loops_back_to_the_submenu(
        self, mock_select, mock_last_run, mock_run_doctor
    ):
        mock_select.return_value.ask.side_effect = ["doctor", "back"]
        self.assertFalse(menu._handle_settings_upkeep())
        mock_run_doctor.assert_called_once()
        self.assertEqual(mock_select.call_count, 2)

    @patch("menu._handle_check_updates")
    @patch("menu.maintenance.get_last_run", return_value=None)
    @patch("menu.questionary.select")
    def test_check_updates_choice_loops_back_to_the_submenu(
        self, mock_select, mock_last_run, mock_check_updates
    ):
        mock_select.return_value.ask.side_effect = ["check_updates", "back"]
        self.assertFalse(menu._handle_settings_upkeep())
        mock_check_updates.assert_called_once()
        self.assertEqual(mock_select.call_count, 2)


class TestPromptForUpdate(unittest.TestCase):

    @patch("menu.git_update.check_for_updates")
    @patch("menu.git_update.has_uncommitted_changes", return_value=True)
    def test_skips_the_check_entirely_when_dirty(self, mock_dirty, mock_check):
        menu._prompt_for_update()
        mock_check.assert_not_called()

    @patch(
        "menu.git_update.check_for_updates", return_value=(False, "Already up to date")
    )
    @patch("menu.git_update.has_uncommitted_changes", return_value=False)
    def test_says_nothing_when_already_up_to_date(self, mock_dirty, mock_check):
        with patch("menu.cli_art.console.print") as mock_print:
            menu._prompt_for_update()
            mock_print.assert_not_called()

    @patch("menu.git_update.pull_updates")
    @patch(
        "menu.git_update.check_for_updates",
        return_value=(True, "2 new commit(s) available"),
    )
    @patch("menu.git_update.has_uncommitted_changes", return_value=False)
    @patch("menu.charm_prompt.confirm")
    def test_pulls_when_confirmed(
        self, mock_confirm, mock_dirty, mock_check, mock_pull
    ):
        mock_confirm.return_value = True
        mock_pull.return_value = (True, "Updated")
        menu._prompt_for_update()
        mock_pull.assert_called_once()

    @patch("menu.git_update.pull_updates")
    @patch(
        "menu.git_update.check_for_updates",
        return_value=(True, "2 new commit(s) available"),
    )
    @patch("menu.git_update.has_uncommitted_changes", return_value=False)
    @patch("menu.charm_prompt.confirm")
    def test_does_not_pull_when_declined(
        self, mock_confirm, mock_dirty, mock_check, mock_pull
    ):
        mock_confirm.return_value = False
        menu._prompt_for_update()
        mock_pull.assert_not_called()


class TestHandleCheckUpdates(unittest.TestCase):

    @patch("menu.git_update.check_for_updates")
    @patch("menu.git_update.has_uncommitted_changes", return_value=True)
    def test_returns_false_and_skips_the_check_when_dirty(self, mock_dirty, mock_check):
        self.assertFalse(menu._handle_check_updates())
        mock_check.assert_not_called()

    @patch(
        "menu.git_update.check_for_updates", return_value=(False, "Already up to date")
    )
    @patch("menu.git_update.has_uncommitted_changes", return_value=False)
    def test_returns_false_when_already_up_to_date(self, mock_dirty, mock_check):
        self.assertFalse(menu._handle_check_updates())

    @patch("menu.git_update.pull_updates", return_value=(True, "Updated"))
    @patch(
        "menu.git_update.check_for_updates",
        return_value=(True, "1 new commit(s) available"),
    )
    @patch("menu.git_update.has_uncommitted_changes", return_value=False)
    @patch("menu.charm_prompt.confirm")
    def test_returns_true_on_confirmed_successful_pull(
        self, mock_confirm, mock_dirty, mock_check, mock_pull
    ):
        mock_confirm.return_value = True
        self.assertTrue(menu._handle_check_updates())

    @patch(
        "menu.git_update.pull_updates", return_value=(False, "Pull failed: conflict")
    )
    @patch(
        "menu.git_update.check_for_updates",
        return_value=(True, "1 new commit(s) available"),
    )
    @patch("menu.git_update.has_uncommitted_changes", return_value=False)
    @patch("menu.charm_prompt.confirm")
    def test_returns_false_on_failed_pull(
        self, mock_confirm, mock_dirty, mock_check, mock_pull
    ):
        mock_confirm.return_value = True
        self.assertFalse(menu._handle_check_updates())

    @patch("menu.git_update.pull_updates")
    @patch(
        "menu.git_update.check_for_updates",
        return_value=(True, "1 new commit(s) available"),
    )
    @patch("menu.git_update.has_uncommitted_changes", return_value=False)
    @patch("menu.charm_prompt.confirm")
    def test_does_not_pull_when_declined(
        self, mock_confirm, mock_dirty, mock_check, mock_pull
    ):
        mock_confirm.return_value = False
        menu._handle_check_updates()
        mock_pull.assert_not_called()


class TestHandleHelp(unittest.TestCase):

    @patch("menu.cli_art.display_help")
    def test_always_returns_false(self, mock_display):
        self.assertFalse(menu._handle_help())
        mock_display.assert_called_once()


class TestChainContent(unittest.TestCase):

    def test_chain_matches_the_designed_pipeline_order(self):
        # Not "Check Liveness" -- scan.run_scan() already verifies
        # liveness by default on exactly the postings it just found.
        self.assertEqual(menu._CHAIN["scan"], [("Evaluate All JDs", "evaluate_all")])
        self.assertEqual(
            menu._CHAIN["liveness"], [("Evaluate All JDs", "evaluate_all")]
        )
        self.assertEqual(
            menu._CHAIN["evaluate_all"],
            [
                ("Customize Resume", "tailor_all"),
                ("Browse & Manage Jobs", "browse_jobs"),
            ],
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
        with (
            patch.dict(menu._HANDLERS, {"fake": lambda: False}, clear=False),
            patch.dict(menu._CHAIN, {"fake": [("Next", "somewhere")]}, clear=False),
        ):
            menu._run_with_chain("fake", {})
        mock_select.assert_not_called()

    @patch("menu.questionary.select")
    def test_handler_with_no_chain_entry_skips_the_prompt(self, mock_select):
        with patch.dict(menu._HANDLERS, {"fake": lambda: True}, clear=False):
            menu._run_with_chain("fake", {})
        mock_select.assert_not_called()

    @patch(
        "menu.cli_art.console"
    )  # is_terminal must read truthy for the prompt to show at all
    @patch("menu.questionary.select")
    def test_chain_prompt_appends_back_to_menu_choice(self, mock_select, mock_console):
        mock_select.return_value.ask.return_value = "__back__"
        with (
            patch.dict(menu._HANDLERS, {"fake": lambda: True}, clear=False),
            patch.dict(menu._CHAIN, {"fake": [("Next", "somewhere")]}, clear=False),
        ):
            menu._run_with_chain("fake", {})
        choices = mock_select.call_args.kwargs["choices"]
        # "somewhere" has no _CHAIN_ICONS entry -> falls back to plain
        # label; "__back__" always gets the utility icon.
        self.assertEqual(
            [c.title for c in choices],
            ["Next", menu._icon_title("utility", "Back to Menu")],
        )
        self.assertEqual([c.value for c in choices], ["somewhere", "__back__"])

    @patch("menu.questionary.select")
    def test_back_to_menu_stops_recursion(self, mock_select):
        calls = []
        mock_select.return_value.ask.return_value = "__back__"
        with (
            patch.dict(
                menu._HANDLERS,
                {"fake": lambda: calls.append("fake") or True},
                clear=False,
            ),
            patch.dict(menu._CHAIN, {"fake": [("Next", "somewhere")]}, clear=False),
        ):
            menu._run_with_chain("fake", {})
        self.assertEqual(calls, ["fake"])

    @patch("menu.questionary.select")
    def test_cancelled_prompt_stops_recursion(self, mock_select):
        calls = []
        mock_select.return_value.ask.return_value = None
        with (
            patch.dict(
                menu._HANDLERS,
                {"fake": lambda: calls.append("fake") or True},
                clear=False,
            ),
            patch.dict(menu._CHAIN, {"fake": [("Next", "somewhere")]}, clear=False),
        ):
            menu._run_with_chain("fake", {})
        self.assertEqual(calls, ["fake"])

    @patch(
        "menu.cli_art.console"
    )  # is_terminal must read truthy for the prompt to show at all
    @patch("menu.questionary.select")
    def test_picking_a_next_step_recurses_into_it(self, mock_select, mock_console):
        calls = []
        mock_select.return_value.ask.return_value = "second"
        with (
            patch.dict(
                menu._HANDLERS,
                {
                    "first": lambda: calls.append("first") or True,
                    "second": lambda: calls.append("second") or False,
                },
                clear=False,
            ),
            patch.dict(menu._CHAIN, {"first": [("Do Second", "second")]}, clear=False),
        ):
            menu._run_with_chain("first", {})
        self.assertEqual(calls, ["first", "second"])

    # Both scroll-region tests below force _should_use_alt_screen() to
    # False -- that's the fallback path (small terminal, or
    # RESUME_ALT_SCREEN=0) where the DECSTBM clamp is still the only
    # pinned-footer mechanism available and the tailor_pick/coverletter_pick
    # skip-set still matters. When alt-screen IS active (the common case),
    # _run_with_chain() suspends it instead of clamping -- see
    # TestBatchActionsSuspendAltScreen below.
    @patch("menu._should_use_alt_screen", return_value=False)
    @patch("menu.cli_art.display_execution_footer")
    @patch("menu.cli_art.display_compact_banner")
    @patch("menu.sys.stdout")
    def test_tailor_pick_and_coverletter_pick_skip_the_scroll_region_clamp(
        self, mock_stdout, mock_banner, mock_footer, mock_use_alt
    ):
        # Regression: menu.py's _run_with_chain() sets a DECSTBM scroll
        # region (\x1b[5;{rows-1}r) around every leaf action's banner --
        # fine for actions whose prompts route through the Charm/huh
        # binary, but tailor_pick/coverletter_pick's picker still renders
        # its multi-select checkbox via raw questionary
        # (picker.browse_and_select_jds -> _paginated_checkbox), which
        # renders nothing at all under a clamped scroll region. These two
        # must skip the clamp -- everything else (banner, footer) still
        # runs.
        for value in ("tailor_pick", "coverletter_pick"):
            mock_stdout.reset_mock()
            with patch.dict(menu._HANDLERS, {value: lambda: False}, clear=False):
                menu._run_with_chain(value, {})
            writes = "".join(c.args[0] for c in mock_stdout.write.call_args_list)
            self.assertNotIn(
                "\x1b[5;", writes, f"{value}: scroll region was set despite skip-set"
            )
            mock_banner.assert_called()

    @patch("menu._should_use_alt_screen", return_value=False)
    @patch("menu.cli_art.display_execution_footer")
    @patch("menu.cli_art.display_compact_banner")
    @patch("menu.sys.stdout")
    def test_other_scroll_region_actions_are_unaffected(
        self, mock_stdout, mock_banner, mock_footer, mock_use_alt
    ):
        with patch.dict(menu._HANDLERS, {"evaluate_all": lambda: False}, clear=False):
            menu._run_with_chain("evaluate_all", {})
        writes = "".join(c.args[0] for c in mock_stdout.write.call_args_list)
        self.assertIn("\x1b[5;", writes)


class TestBatchActionsSuspendAltScreen(unittest.TestCase):
    """The alternate screen buffer (entered once for the whole menu session)
    has no real scrollback in virtually any terminal emulator, so a
    log-heavy batch action (tailor_all, scan, evaluate_all, ...) running
    inside it loses anything that scrolls past the top of the viewport.
    _run_with_chain() now drops to the primary screen buffer for the
    duration of these handlers -- real scrollback -- and re-enters
    alt-screen right after, before the "what's next" prompt, so menu
    navigation keeps its existing full-screen look. Regression covering
    the 2026-08-22 fix."""

    @patch("menu._should_use_alt_screen", return_value=True)
    @patch("menu.cli_art.display_execution_footer")
    @patch("menu.cli_art.display_compact_banner")
    @patch("menu.sys.stdout")
    def test_evaluate_all_suspends_and_restores_alt_screen(
        self, mock_stdout, mock_banner, mock_footer, mock_use_alt
    ):
        with patch.dict(menu._HANDLERS, {"evaluate_all": lambda: False}, clear=False):
            menu._run_with_chain("evaluate_all", {})
        writes = "".join(c.args[0] for c in mock_stdout.write.call_args_list)
        self.assertIn(
            "\x1b[?1049l", writes, "did not exit alt-screen for the batch action"
        )
        self.assertIn("\x1b[?1049h", writes, "did not re-enter alt-screen afterward")
        self.assertLess(
            writes.index("\x1b[?1049l"),
            writes.index("\x1b[?1049h"),
            "exit must happen before the handler, re-entry after",
        )
        self.assertNotIn(
            "\x1b[5;",
            writes,
            "scroll region clamp would break the real scrollback we just enabled",
        )
        mock_footer.assert_not_called()

    @patch("menu._should_use_alt_screen", return_value=True)
    @patch("menu.cli_art.display_execution_footer")
    @patch("menu.cli_art.display_compact_banner")
    @patch("menu.sys.stdout")
    def test_tailor_pick_also_suspends_alt_screen(
        self, mock_stdout, mock_banner, mock_footer, mock_use_alt
    ):
        with patch.dict(menu._HANDLERS, {"tailor_pick": lambda: False}, clear=False):
            menu._run_with_chain("tailor_pick", {})
        writes = "".join(c.args[0] for c in mock_stdout.write.call_args_list)
        self.assertIn("\x1b[?1049l", writes)
        self.assertIn("\x1b[?1049h", writes)

    @patch("menu._should_use_alt_screen", return_value=True)
    @patch("menu.cli_art.display_execution_footer")
    @patch("menu.cli_art.display_compact_banner")
    @patch("menu.sys.stdout")
    def test_interactive_actions_do_not_touch_alt_screen(
        self, mock_stdout, mock_banner, mock_footer, mock_use_alt
    ):
        # career_dashboard etc. are single-screen pickers that already ran
        # entirely inside alt-screen before this fix -- they must keep
        # doing so, since they never produce scrolling log output.
        with patch.dict(
            menu._HANDLERS, {"career_dashboard": lambda: False}, clear=False
        ):
            menu._run_with_chain("career_dashboard", {})
        writes = "".join(c.args[0] for c in mock_stdout.write.call_args_list)
        self.assertNotIn("\x1b[?1049l", writes)
        self.assertNotIn("\x1b[?1049h", writes)


class TestRunInteractiveMenuClearsProfilePickerLeftovers(unittest.TestCase):
    # Regression: the profile picker ("Who's using resume-builder?", a
    # huh/Bubbletea prompt drawn directly to the terminal) doesn't erase
    # itself on exit, so it stayed on screen as scrollback underneath the
    # banner/tip/menu that render right after it -- confirmed in a real
    # screenshot showing all three stacked at once. run_interactive_menu()
    # now clears and redraws a static banner once profile confirmation
    # succeeds, but only inside the alt-screen buffer (use_alt=True) --
    # clearing real terminal scrollback (use_alt=False) would be a much
    # more aggressive, unwanted change of behavior.

    def _run_one_pass_and_exit(self):
        # Drives run_interactive_menu() through exactly one real loop
        # iteration (choice="exit") so it returns instead of blocking.
        menu.run_interactive_menu()

    @patch("menu._should_use_alt_screen", return_value=True)
    @patch("menu._alternate_screen")
    @patch("menu.cli_art.display_main_banner")
    @patch("menu._confirm_active_profile", return_value=True)
    @patch("menu._confirm_icon_set")
    @patch("menu._prompt_for_update")
    @patch("menu.cli_art.display_tip")
    @patch("menu.cli_art.select", return_value="exit")
    @patch("menu.sys.stdout")
    def test_clears_and_redraws_banner_when_alt_screen_is_active(
        self,
        mock_stdout,
        mock_select,
        mock_tip,
        mock_update,
        mock_icons,
        mock_confirm_profile,
        mock_banner,
        mock_alt_screen,
        mock_use_alt,
    ):
        self._run_one_pass_and_exit()

        writes = "".join(c.args[0] for c in mock_stdout.write.call_args_list)
        self.assertIn("\x1b[2J\x1b[H", writes)
        # First call is the real animated reveal (no reveal kwarg forced
        # False); the redraw immediately after profile confirmation must
        # be reveal=False, a static redraw, not a second intro animation.
        self.assertEqual(mock_banner.call_args_list[1].kwargs, {"reveal": False})

    @patch("menu._should_use_alt_screen", return_value=False)
    @patch("menu.cli_art.display_main_banner")
    @patch("menu._confirm_active_profile", return_value=True)
    @patch("menu._confirm_icon_set")
    @patch("menu._prompt_for_update")
    @patch("menu.cli_art.display_tip")
    @patch("menu.cli_art.select", return_value="exit")
    @patch("menu.sys.stdout")
    def test_does_not_clear_when_alt_screen_is_off(
        self,
        mock_stdout,
        mock_select,
        mock_tip,
        mock_update,
        mock_icons,
        mock_confirm_profile,
        mock_banner,
        mock_use_alt,
    ):
        self._run_one_pass_and_exit()
        writes = "".join(c.args[0] for c in mock_stdout.write.call_args_list)
        self.assertNotIn("\x1b[2J\x1b[H", writes)
        self.assertEqual(mock_banner.call_count, 1)


class TestSessionSummary(unittest.TestCase):

    @patch("menu.questionary.select")
    def test_successful_action_increments_its_labeled_count(self, mock_select):
        session_stats = {}
        with (
            patch.dict(menu._HANDLERS, {"tailor_all": lambda: True}, clear=False),
            patch.dict(menu._CHAIN, {}, clear=True),
        ):
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
        summary = menu._session_summary(
            {"resumes tailored": 3, "cover letters written": 2}
        )
        self.assertIn("3 resumes tailored", summary)
        self.assertIn("2 cover letters written", summary)
        self.assertIn("Nice work.", summary)


class TestAltScreenMode(unittest.TestCase):

    @patch("shutil.get_terminal_size")
    @patch.dict(os.environ, {}, clear=True)
    def test_should_use_alt_screen_defaults(self, mock_terminal_size):
        # By default, if terminal height >= 24, it should return True
        mock_terminal_size.return_value = (80, 40)
        self.assertTrue(menu._should_use_alt_screen())

        # If height < 24, it should return False
        mock_terminal_size.return_value = (80, 20)
        self.assertFalse(menu._should_use_alt_screen())

    @patch.dict(os.environ, {"RESUME_ALT_SCREEN": "1"})
    def test_should_use_alt_screen_env_override_on(self):
        self.assertTrue(menu._should_use_alt_screen())

    @patch.dict(os.environ, {"RESUME_ALT_SCREEN": "0"})
    def test_should_use_alt_screen_env_override_off(self):
        self.assertFalse(menu._should_use_alt_screen())

    @patch("sys.stdout.isatty")
    @patch("sys.stdout.write")
    @patch("sys.stdout.flush")
    @patch.dict(os.environ, {}, clear=True)
    def test_alternate_screen_interactive(self, mock_flush, mock_write, mock_isatty):
        mock_isatty.return_value = True
        with menu._alternate_screen():
            pass
        # Should have written \x1b[?1049h\x1b[H to enter and \x1b[?1049l to exit
        mock_write.assert_any_call("\x1b[?1049h\x1b[H")
        mock_write.assert_any_call("\x1b[?1049l")
        self.assertEqual(mock_flush.call_count, 2)

    @patch("sys.stdout.isatty")
    @patch("sys.stdout.write")
    @patch("sys.stdout.flush")
    def test_alternate_screen_non_interactive(
        self, mock_flush, mock_write, mock_isatty
    ):
        mock_isatty.return_value = False
        with menu._alternate_screen():
            pass
        mock_write.assert_not_called()


if __name__ == "__main__":
    unittest.main()
