import json
import os
import shutil
import sys
import tempfile
import unittest
from unittest.mock import MagicMock, patch

SCRIPTS_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts"
)
sys.path.insert(0, SCRIPTS_DIR)

import picker  # noqa: E402
import profile_paths  # noqa: E402


class TestTruncate(unittest.TestCase):

    def test_short_text_is_unchanged(self):
        self.assertEqual(picker._truncate("Acme", 20), "Acme")

    def test_long_text_is_ellipsized_to_max_len(self):
        result = picker._truncate("A Very Long Company Name Indeed", 10)
        self.assertEqual(len(result), 10)
        self.assertTrue(result.endswith("..."))

    def test_max_len_at_or_below_three_hard_cuts_without_ellipsis(self):
        self.assertEqual(picker._truncate("Acme", 3), "Acm")
        self.assertEqual(picker._truncate("Acme", 0), "")


class TestPickAndProcessRowWidthClamp(unittest.TestCase):

    def test_long_company_and_title_are_truncated_to_fit_console_width(self):
        long_company = "A" * 80
        long_title = "B" * 80
        mock_question = MagicMock()
        mock_question.ask.return_value = None  # abort after inspecting choices
        with (
            patch("picker.questionary.confirm") as mock_confirm,
            patch(
                "picker.batch_evaluate.evaluate_all_pending",
                return_value=[
                    {
                        "source_file": "jds/a.json",
                        "company_name": long_company,
                        "job_title": long_title,
                        "composite_score": 4.0,
                        "recommendation": "Strong pursue",
                        "error": False,
                    },
                ],
            ),
            patch(
                "picker.questionary.checkbox", return_value=mock_question
            ) as mock_checkbox,
            patch("picker.cli_art.console") as mock_console,
        ):
            mock_console.width = 80
            mock_confirm.return_value.ask.return_value = True
            picker.pick_and_process(["jds/a.json"], lambda path: True, "tailor")
        rendered_title = mock_checkbox.call_args.kwargs["choices"][0].title
        self.assertNotIn(long_company, rendered_title)
        self.assertNotIn(long_title, rendered_title)
        self.assertLess(len(rendered_title), len(long_company) + len(long_title))


class TestShouldProceed(unittest.TestCase):

    def test_defaults_to_evaluate_wording(self):
        # should_proceed() routes through cli_art.confirm() (the huh
        # prompt), which under "unittest" in sys.modules degrades to this
        # same questionary.confirm() -- see cli_art.confirm()'s own
        # test-mode branch. Patched on the shared questionary module
        # object, so it's intercepted regardless of which module's
        # `questionary` name triggered the lookup.
        with patch("picker.questionary.confirm") as mock_confirm:
            mock_confirm.return_value.ask.return_value = True
            picker.should_proceed(5, skip_confirm=False)
        mock_confirm.assert_called_once_with(
            "About to evaluate 5 pending JD(s) -- one real Gemini call each. Continue?",
            default=False,
            style=picker.cli_art.QUESTIONARY_STYLE,
        )

    def test_custom_action_wording(self):
        with patch("picker.questionary.confirm") as mock_confirm:
            mock_confirm.return_value.ask.return_value = True
            picker.should_proceed(5, skip_confirm=False, action="tailor")
        mock_confirm.assert_called_once_with(
            "About to tailor 5 pending JD(s) -- one real Gemini call each. Continue?",
            default=False,
            style=picker.cli_art.QUESTIONARY_STYLE,
        )


class TestPickAndProcess(unittest.TestCase):

    def test_empty_pending_returns_zero_zero_without_confirming(self):
        with patch("picker.questionary.confirm") as mock_confirm:
            result = picker.pick_and_process([], lambda path: True, "tailor")
        self.assertEqual(result, (0, 0))
        mock_confirm.assert_not_called()

    def test_declined_confirmation_returns_zero_zero_without_evaluating(self):
        with (
            patch("picker.questionary.confirm") as mock_confirm,
            patch("picker.batch_evaluate.evaluate_all_pending") as mock_evaluate,
        ):
            mock_confirm.return_value.ask.return_value = False
            result = picker.pick_and_process(
                ["jds/a.json"], lambda path: True, "tailor"
            )
        self.assertEqual(result, (0, 0))
        mock_evaluate.assert_not_called()

    def test_all_errored_results_returns_zero_zero_without_showing_picker(self):
        with (
            patch("picker.questionary.confirm") as mock_confirm,
            patch(
                "picker.batch_evaluate.evaluate_all_pending",
                return_value=[
                    {
                        "source_file": "jds/a.json",
                        "company_name": "A",
                        "job_title": "Role A",
                        "composite_score": None,
                        "recommendation": None,
                        "error": True,
                    },
                ],
            ),
            patch("picker.questionary.checkbox") as mock_checkbox,
        ):
            mock_confirm.return_value.ask.return_value = True
            result = picker.pick_and_process(
                ["jds/a.json"], lambda path: True, "tailor"
            )
        self.assertEqual(result, (0, 0))
        mock_checkbox.assert_not_called()

    def test_always_evaluates_fresh_not_skip_by_default(self):
        with (
            patch("picker.questionary.confirm") as mock_confirm,
            patch(
                "picker.batch_evaluate.evaluate_all_pending", return_value=[]
            ) as mock_evaluate,
        ):
            mock_confirm.return_value.ask.return_value = True
            picker.pick_and_process(["jds/a.json"], lambda path: True, "tailor")
        mock_evaluate.assert_called_once_with(["jds/a.json"], skip_evaluated=False)

    def test_nothing_selected_returns_zero_zero(self):
        mock_question = MagicMock()
        mock_question.ask.return_value = None
        with (
            patch("picker.questionary.confirm") as mock_confirm,
            patch(
                "picker.batch_evaluate.evaluate_all_pending",
                return_value=[
                    {
                        "source_file": "jds/a.json",
                        "company_name": "A",
                        "job_title": "Role A",
                        "composite_score": 4.0,
                        "recommendation": "Strong pursue",
                        "error": False,
                    },
                ],
            ),
            patch("picker.questionary.checkbox", return_value=mock_question),
        ):
            mock_confirm.return_value.ask.return_value = True
            result = picker.pick_and_process(
                ["jds/a.json"], lambda path: True, "tailor"
            )
        self.assertEqual(result, (0, 0))

    def test_processes_only_selected_paths_and_counts_success_and_failure(self):
        mock_question = MagicMock()
        mock_question.ask.return_value = ["jds/a.json", "jds/b.json"]

        def fake_process(path):
            return path == "jds/a.json"  # a succeeds, b fails

        with (
            patch("picker.questionary.confirm") as mock_confirm,
            patch(
                "picker.batch_evaluate.evaluate_all_pending",
                return_value=[
                    {
                        "source_file": "jds/a.json",
                        "company_name": "A",
                        "job_title": "Role A",
                        "composite_score": 4.0,
                        "recommendation": "Strong pursue",
                        "error": False,
                    },
                    {
                        "source_file": "jds/b.json",
                        "company_name": "B",
                        "job_title": "Role B",
                        "composite_score": 3.0,
                        "recommendation": "Selective pursue",
                        "error": False,
                    },
                ],
            ),
            patch("picker.questionary.checkbox", return_value=mock_question),
        ):
            mock_confirm.return_value.ask.return_value = True
            result = picker.pick_and_process(
                ["jds/a.json", "jds/b.json"], fake_process, "tailor"
            )
        self.assertEqual(result, (1, 1))

    def test_skip_confirm_true_never_calls_questionary_confirm(self):
        mock_question = MagicMock()
        mock_question.ask.return_value = ["jds/a.json"]
        with (
            patch("picker.questionary.confirm") as mock_confirm,
            patch(
                "picker.batch_evaluate.evaluate_all_pending",
                return_value=[
                    {
                        "source_file": "jds/a.json",
                        "company_name": "A",
                        "job_title": "Role A",
                        "composite_score": 4.0,
                        "recommendation": "Strong pursue",
                        "error": False,
                    },
                ],
            ),
            patch("picker.questionary.checkbox", return_value=mock_question),
        ):
            picker.pick_and_process(
                ["jds/a.json"], lambda path: True, "tailor", skip_confirm=True
            )
        mock_confirm.assert_not_called()


class TestListAllEvaluatedJds(unittest.TestCase):
    """These tests mock the filesystem JD list. list_all_evaluated_jds()
    now also unions in database-only jobs, which reaches a real data.db
    and drags hundreds of live rows into every assertion here -- so the
    profile is redirected at a temp directory, giving each test an empty
    database of its own."""

    def setUp(self):
        tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, tmp, ignore_errors=True)
        os.makedirs(os.path.join(tmp, "testprofile"), exist_ok=True)

        for patcher in (
            patch.object(profile_paths, "PROFILES_DIR", tmp),
            patch.dict(os.environ, {"RESUME_PROFILE": "testprofile"}),
        ):
            patcher.start()
            self.addCleanup(patcher.stop)

    @patch("picker.jd_manager.extract_job_meta", return_value=("Role", "Acme"))
    @patch("picker.jd_manager.read_liveness", return_value=None)
    @patch("picker.jd_manager.read_evaluation")
    @patch("picker.jd_manager.get_completed_jds", return_value=["jds/completed/c.json"])
    @patch("picker.jd_manager.get_pending_jds", return_value=["jds/p.json"])
    def test_combines_pending_and_completed_with_status_tags(
        self, mock_pending, mock_completed, mock_read, mock_live, mock_meta
    ):
        mock_read.side_effect = lambda path: {
            "jds/p.json": {
                "composite_score": 3.0,
                "recommendation": "Selective pursue",
            },
            "jds/completed/c.json": {
                "composite_score": 4.0,
                "recommendation": "Strong pursue",
            },
        }[path]

        rows = picker.list_all_evaluated_jds()

        statuses = {r["path"]: r["status"] for r in rows}
        self.assertEqual(statuses["jds/p.json"], "Pending")
        self.assertEqual(statuses["jds/completed/c.json"], "Completed")

    @patch("picker.jd_manager.extract_job_meta", return_value=("Role", "Acme"))
    @patch("picker.jd_manager.read_liveness", return_value=None)
    @patch("picker.jd_manager.read_evaluation")
    @patch("picker.jd_manager.get_completed_jds", return_value=[])
    @patch(
        "picker.jd_manager.get_pending_jds", return_value=["jds/a.json", "jds/b.json"]
    )
    def test_excludes_jds_with_no_evaluation(
        self, mock_pending, mock_completed, mock_read, mock_live, mock_meta
    ):
        mock_read.side_effect = lambda path: {
            "jds/a.json": {"composite_score": 4.0, "recommendation": "Strong pursue"},
            "jds/b.json": None,
        }[path]

        rows = picker.list_all_evaluated_jds()

        self.assertEqual([r["path"] for r in rows], ["jds/a.json"])

    @patch("picker.jd_manager.extract_job_meta", return_value=("Role", "Acme"))
    @patch("picker.jd_manager.read_liveness", return_value=None)
    @patch("picker.jd_manager.read_evaluation")
    @patch("picker.jd_manager.get_completed_jds", return_value=[])
    @patch(
        "picker.jd_manager.get_pending_jds",
        return_value=["jds/low.json", "jds/high.json"],
    )
    def test_sorts_best_score_first(
        self, mock_pending, mock_completed, mock_read, mock_live, mock_meta
    ):
        mock_read.side_effect = lambda path: {
            "jds/low.json": {
                "composite_score": 2.5,
                "recommendation": "Low-priority pursue",
            },
            "jds/high.json": {
                "composite_score": 4.8,
                "recommendation": "Strong pursue",
            },
        }[path]

        rows = picker.list_all_evaluated_jds()

        self.assertEqual([r["path"] for r in rows], ["jds/high.json", "jds/low.json"])


class TestCountUnevaluatedRoles(unittest.TestCase):
    """The backlog counter. Same temp-profile redirection as
    TestListAllEvaluatedJds: without it the real data.db's ~1,300 pending
    rows land in every assertion."""

    def setUp(self):
        tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, tmp, ignore_errors=True)
        os.makedirs(os.path.join(tmp, "testprofile"), exist_ok=True)

        for patcher in (
            patch.object(profile_paths, "PROFILES_DIR", tmp),
            patch.dict(os.environ, {"RESUME_PROFILE": "testprofile"}),
        ):
            patcher.start()
            self.addCleanup(patcher.stop)

    @patch("picker.jd_manager.compute_job_key", side_effect=OSError)
    @patch("picker.jd_manager.read_evaluation")
    @patch(
        "picker.jd_manager.get_pending_jds",
        return_value=["jds/done.json", "jds/todo.json", "jds/todo2.json"],
    )
    def test_counts_only_pending_files_without_an_evaluation(
        self, mock_pending, mock_read, mock_key
    ):
        mock_read.side_effect = lambda path: (
            {"composite_score": 4.0} if path == "jds/done.json" else None
        )

        self.assertEqual(picker.count_unevaluated_roles(), 2)

    @patch("picker.jd_manager.compute_job_key", side_effect=OSError)
    @patch("picker.jd_manager.read_evaluation", return_value=None)
    @patch("picker.jd_manager.get_pending_jds", return_value=[])
    def test_counts_database_only_rows_and_skips_evaluated_ones(
        self, mock_pending, mock_read, mock_key
    ):
        import db

        conn = db.get_db()
        try:
            conn.execute(
                "INSERT INTO jobs (id, title, company, status, raw_text, metadata_json)"
                " VALUES (?, ?, ?, 'pending', '', ?)",
                ("hash-unevaluated", "Role", "Acme", "{}"),
            )
            conn.execute(
                "INSERT INTO jobs (id, title, company, status, raw_text, metadata_json)"
                " VALUES (?, ?, ?, 'pending', '', ?)",
                (
                    "hash-evaluated",
                    "Role",
                    "Acme",
                    '{"_evaluation": {"composite_score": 4.0}}',
                ),
            )
            conn.commit()
        finally:
            conn.close()

        self.assertEqual(picker.count_unevaluated_roles(), 1)

    @patch("picker.jd_manager.compute_job_key", return_value="hash-dupe")
    @patch("picker.jd_manager.read_evaluation", return_value=None)
    @patch("picker.jd_manager.get_pending_jds", return_value=["jds/dupe.json"])
    def test_does_not_double_count_a_row_that_has_a_file(
        self, mock_pending, mock_read, mock_key
    ):
        """A database row and its file-backed twin are one role. Counting
        both is exactly the kind of inflated number this line exists to
        stop producing."""
        import db

        conn = db.get_db()
        try:
            conn.execute(
                "INSERT INTO jobs (id, title, company, status, raw_text, metadata_json)"
                " VALUES (?, ?, ?, 'pending', '', ?)",
                ("hash-dupe", "Role", "Acme", "{}"),
            )
            conn.commit()
        finally:
            conn.close()

        self.assertEqual(picker.count_unevaluated_roles(), 1)


def _row(path, score, recommendation, status="Pending", title=None, company=None):
    return {
        "path": path,
        "status": status,
        "title": title or path,
        "company": company or "Acme",
        "evaluation": {"composite_score": score, "recommendation": recommendation},
    }


class TestBrowseAndSelectJds(unittest.TestCase):

    @patch("picker.list_all_evaluated_jds", return_value=[])
    def test_empty_list_prints_hint_and_returns_empty(self, mock_list):
        with (
            patch("picker.questionary.checkbox") as mock_checkbox,
            patch("picker.cli_art.console.print") as mock_print,
        ):
            result = picker.browse_and_select_jds()
        self.assertEqual(result, [])
        mock_checkbox.assert_not_called()
        printed = mock_print.call_args[0][0]
        self.assertIn("Hint", printed)

    @patch("picker.cli_art.render_picker_header")
    @patch("picker.list_all_evaluated_jds")
    def test_renders_the_header_for_the_current_page_only(self, mock_list, mock_render):
        rows = [
            _row(f"jds/{i}.json", 5.0 - i * 0.01, "Strong pursue") for i in range(5)
        ]
        mock_list.return_value = rows
        mock_question = MagicMock()
        mock_question.ask.return_value = [picker._NAV_DONE]
        with patch("picker.questionary.checkbox", return_value=mock_question):
            picker.browse_and_select_jds(page_size=3)
        mock_render.assert_called_once()
        kwargs = mock_render.call_args.kwargs
        self.assertIn("Page 1/2", kwargs["title"])
        # #, Score, Recommendation, Company, Title, Posted, Status
        self.assertEqual(len(kwargs["columns"]), 7)

    @patch("picker.cli_art.render_picker_header")
    @patch("picker.list_all_evaluated_jds")
    def test_nothing_checked_returns_empty(self, mock_list, mock_render):
        mock_list.return_value = [_row("jds/a.json", 4.0, "Strong pursue")]
        mock_question = MagicMock()
        mock_question.ask.return_value = [picker._NAV_DONE]
        with patch("picker.questionary.checkbox", return_value=mock_question):
            result = picker.browse_and_select_jds()
        self.assertEqual(result, [])

    @patch("picker.cli_art.render_picker_header")
    @patch("picker.list_all_evaluated_jds")
    def test_ctrl_c_aborts_and_returns_empty(self, mock_list, mock_render):
        mock_list.return_value = [_row("jds/a.json", 4.0, "Strong pursue")]
        mock_question = MagicMock()
        mock_question.ask.return_value = None
        with patch("picker.questionary.checkbox", return_value=mock_question):
            result = picker.browse_and_select_jds()
        self.assertEqual(result, [])

    @patch("picker.cli_art.render_picker_header")
    @patch("picker.list_all_evaluated_jds")
    def test_returns_the_selected_rows_not_just_paths(self, mock_list, mock_render):
        rows = [
            _row(
                "jds/a.json",
                4.0,
                "Strong pursue",
                status="Pending",
                title="Role A",
                company="Acme",
            ),
            _row(
                "jds/b.json",
                3.0,
                "Selective pursue",
                status="Completed",
                title="Role B",
                company="Beta",
            ),
        ]
        mock_list.return_value = rows
        mock_question = MagicMock()
        mock_question.ask.return_value = ["jds/b.json", picker._NAV_DONE]
        with patch("picker.questionary.checkbox", return_value=mock_question):
            result = picker.browse_and_select_jds()
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["path"], "jds/b.json")
        self.assertEqual(result[0]["status"], "Completed")

    @patch("picker.cli_art.render_picker_header")
    @patch("picker.list_all_evaluated_jds")
    def test_result_order_matches_best_score_first_regardless_of_selection_order(
        self, mock_list, mock_render
    ):
        rows = [
            _row("jds/high.json", 4.8, "Strong pursue"),
            _row("jds/low.json", 2.5, "Low-priority pursue"),
        ]
        mock_list.return_value = rows
        mock_question = MagicMock()
        # Selected in reverse order -- result should still come back high first.
        mock_question.ask.return_value = [
            "jds/low.json",
            "jds/high.json",
            picker._NAV_DONE,
        ]
        with patch("picker.questionary.checkbox", return_value=mock_question):
            result = picker.browse_and_select_jds()
        self.assertEqual([r["path"] for r in result], ["jds/high.json", "jds/low.json"])

    @patch("picker.cli_art.render_picker_header")
    @patch("picker.list_all_evaluated_jds")
    def test_paginates_at_page_size_and_persists_selection_across_pages(
        self, mock_list, mock_render
    ):
        rows = [
            _row(f"jds/{i}.json", 5.0 - i * 0.01, "Strong pursue") for i in range(5)
        ]
        mock_list.return_value = rows

        page1 = MagicMock()
        page1.ask.return_value = ["jds/0.json", picker._NAV_NEXT]
        page2 = MagicMock()
        page2.ask.return_value = [picker._NAV_DONE]
        with patch(
            "picker.questionary.checkbox", side_effect=[page1, page2]
        ) as mock_checkbox:
            result = picker.browse_and_select_jds(page_size=3)

        self.assertEqual(mock_checkbox.call_count, 2)
        first_call_choices = mock_checkbox.call_args_list[0].kwargs["choices"]
        # 3 real rows + Separator + "Next page" + "Done" on page 1 of 2.
        self.assertEqual(len(first_call_choices), 6)
        self.assertEqual([r["path"] for r in result], ["jds/0.json"])

    @patch("picker.cli_art.render_picker_header")
    @patch("picker.list_all_evaluated_jds")
    def test_unchecking_a_row_on_a_revisited_page_drops_it(
        self, mock_list, mock_render
    ):
        rows = [
            _row(f"jds/{i}.json", 5.0 - i * 0.01, "Strong pursue") for i in range(2)
        ]
        mock_list.return_value = rows

        visit_page0_select = MagicMock()
        visit_page0_select.ask.return_value = ["jds/0.json", picker._NAV_NEXT]
        visit_page1_back = MagicMock()
        visit_page1_back.ask.return_value = [picker._NAV_PREV]
        visit_page0_uncheck = MagicMock()
        visit_page0_uncheck.ask.return_value = [
            picker._NAV_NEXT
        ]  # jds/0.json left unchecked this time
        visit_page1_done = MagicMock()
        visit_page1_done.ask.return_value = [picker._NAV_DONE]

        with patch(
            "picker.questionary.checkbox",
            side_effect=[
                visit_page0_select,
                visit_page1_back,
                visit_page0_uncheck,
                visit_page1_done,
            ],
        ):
            result = picker.browse_and_select_jds(page_size=1)
        self.assertEqual(result, [])


class TestLocationFields(unittest.TestCase):
    """The location/workplace/distance columns added to the export."""

    SETTINGS = {
        "city": "Getzville",
        "state": "NY",
        "zip": "14068",
        "radius_miles": 25,
        "workplace_mode": "any",
    }

    def test_nearby_onsite_gets_a_distance(self):
        fields = picker._location_fields({"location": "Buffalo, NY"}, self.SETTINGS)
        self.assertEqual(fields["location"], "Buffalo, NY")
        self.assertIsNotNone(fields["distance_miles"])
        self.assertLess(fields["distance_miles"], 25)

    def test_remote_is_classified_without_a_distance(self):
        fields = picker._location_fields({"location": "Remote (US)"}, self.SETTINGS)
        self.assertEqual(fields["workplace"], "remote")
        self.assertIsNone(fields["distance_miles"])

    def test_unresolvable_location_has_no_distance(self):
        # None, never 0 -- the Go side sorts on this, and a zero would
        # place an unknown location at the top of a nearest-first sort.
        fields = picker._location_fields(
            {"location": "Greater Austin Area"}, self.SETTINGS
        )
        self.assertIsNone(fields["distance_miles"])

    def test_missing_location_is_empty_not_none(self):
        fields = picker._location_fields({}, self.SETTINGS)
        self.assertEqual(fields["location"], "")
        self.assertIsNone(fields["distance_miles"])

    def test_structured_hints_are_used(self):
        fields = picker._location_fields(
            {"location": "Austin, TX", "work_model": "Hybrid"}, self.SETTINGS
        )
        self.assertEqual(fields["workplace"], "hybrid")

    def test_unconfigured_profile_yields_no_distance(self):
        # With no location: block, distance is not computed at all --
        # every row still exports the columns, just empty.
        fields = picker._location_fields({"location": "Buffalo, NY"}, {})
        self.assertIsNone(fields["distance_miles"])
        self.assertEqual(fields["location"], "Buffalo, NY")

    def test_reader_degrades_to_empty_on_failure(self):
        with patch.dict("sys.modules", {"location_settings": None}):
            self.assertEqual(picker._read_location_settings(), {})

    def test_enriched_location_overrides_display_and_distance(self):
        jd_data = {
            "location": "Buffalo, NY",
            "_location_enrichment": {
                "status": "resolved",
                "resolved_address": "500 Audubon Pkwy, Amherst, NY 14228",
                "lat": 42.996,
                "lon": -78.788,
                "source": "jd_text_override",
            },
        }
        fields = picker._location_fields(jd_data, self.SETTINGS)
        self.assertEqual(fields["location"], "500 Audubon Pkwy, Amherst, NY 14228")
        self.assertIsNotNone(fields["distance_miles"])
        self.assertLess(fields["distance_miles"], 3.0)

    def test_database_rows_with_enrichment(self):
        # Verify picker database rows with _location_enrichment parse correctly
        db_meta = {
            "_evaluation": {"composite_score": 4.5},
            "location": "Buffalo, NY",
            "_location_enrichment": {
                "status": "resolved",
                "resolved_address": "Williamsville, NY 14221",
                "lat": 42.964,
                "lon": -78.737,
                "source": "osm_nominatim",
            },
        }
        fields = picker._location_fields(db_meta, self.SETTINGS)
        self.assertEqual(fields["location"], "Williamsville, NY 14221")
        self.assertIsNotNone(fields["distance_miles"])

    def test_file_based_row_loads_persisted_enrichment_from_disk(self):
        # Create a real temp JD JSON file on disk with _location_enrichment and _evaluation
        tmp_dir = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, tmp_dir, ignore_errors=True)
        file_path = os.path.join(tmp_dir, "job.json")
        data = {
            "title": "Software Engineer",
            "company": "Local Tech",
            "location": "Buffalo, NY",
            "_evaluation": {"composite_score": 4.5, "recommendation": "Strong pursue"},
            "_location_enrichment": {
                "status": "resolved",
                "resolved_address": "500 Audubon Pkwy, Amherst, NY 14228",
                "lat": 42.996,
                "lon": -78.788,
                "source": "jd_text_override",
            },
        }
        with open(file_path, "w", encoding="utf-8") as f:
            json.dump(data, f)

        with (
            patch("picker.jd_manager.get_pending_jds", return_value=[file_path]),
            patch("picker.jd_manager.get_completed_jds", return_value=[]),
            patch("picker._database_only_rows", return_value=[]),
            patch("picker._read_location_settings", return_value=self.SETTINGS),
        ):
            rows = picker.list_all_evaluated_jds(statuses=["Pending"])
            self.assertEqual(len(rows), 1)
            row = rows[0]
            self.assertEqual(row["location"], "500 Audubon Pkwy, Amherst, NY 14228")
            self.assertIsNotNone(row["distance_miles"])
            self.assertLess(row["distance_miles"], 3.0)
            self.assertIsNotNone(row.get("location_enrichment"))
            self.assertEqual(row["location_enrichment"]["source"], "jd_text_override")
