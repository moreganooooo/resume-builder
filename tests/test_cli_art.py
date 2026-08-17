import os
import sys
import unittest
from unittest.mock import patch

SCRIPTS_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts"
)
sys.path.insert(0, SCRIPTS_DIR)

import cli_art  # noqa: E402
from rich.console import Console


def _rendered(fn, *args, **kwargs):
    console = Console(record=True, width=100)
    original = cli_art.console
    cli_art.console = console
    try:
        fn(*args, **kwargs)
    finally:
        cli_art.console = original
    return console.export_text()


class TestDisplayError(unittest.TestCase):

    def test_renders_message_in_a_bordered_panel(self):
        output = _rendered(cli_art.display_error, "Evaluation failed.")
        self.assertIn("Evaluation failed.", output)
        self.assertIn(cli_art.theme.ICONS["error"], output)


class TestDisplaySuccess(unittest.TestCase):

    def test_renders_message_with_icon_no_border(self):
        output = _rendered(cli_art.display_success, "Resume built.")
        self.assertIn("Resume built.", output)
        self.assertIn(cli_art.theme.ICONS["success"], output)
        # No panel border characters -- success stays lightweight.
        self.assertNotIn("╭", output)  # ╭ (rounded-panel corner)


class TestLerpHex(unittest.TestCase):

    def test_t_zero_returns_start(self):
        self.assertEqual(cli_art._lerp_hex("#000000", "#ffffff", 0.0), "#000000")

    def test_t_one_returns_end(self):
        self.assertEqual(cli_art._lerp_hex("#000000", "#ffffff", 1.0), "#ffffff")

    def test_t_half_returns_midpoint(self):
        self.assertEqual(cli_art._lerp_hex("#000000", "#ffffff", 0.5), "#808080")


class TestGradientGrid(unittest.TestCase):

    def test_top_left_is_start_color(self):
        grid = cli_art._gradient_grid(["AB", "CD"], "#000000", "#ffffff")
        self.assertEqual(grid[0][0], "#000000")

    def test_bottom_right_is_end_color(self):
        grid = cli_art._gradient_grid(["AB", "CD"], "#000000", "#ffffff")
        self.assertEqual(grid[-1][-1], "#ffffff")

    def test_handles_empty_lines_without_crashing(self):
        grid = cli_art._gradient_grid(["AB", "", "CD"], "#000000", "#ffffff")
        self.assertEqual(grid[1], [])


class TestRevealBanner(unittest.TestCase):

    def test_non_terminal_prints_once_fully_revealed(self):
        console = Console(record=True, width=100, force_terminal=False)
        original = cli_art.console
        cli_art.console = console
        calls = []

        def render_frame(threshold):
            calls.append(threshold)
            return cli_art.Text(f"threshold={threshold}")

        try:
            cli_art._reveal_banner(["AB"], [["#000000", "#111111"]], render_frame)
        finally:
            cli_art.console = original

        self.assertEqual(calls, [None])
        self.assertIn("threshold=None", console.export_text())

    @patch("cli_art.Live")
    def test_terminal_drives_multiple_frames(self, mock_live_cls):
        console = Console(record=True, width=100, force_terminal=True)
        original = cli_art.console
        cli_art.console = console
        mock_live = mock_live_cls.return_value.__enter__.return_value

        def render_frame(threshold):
            return cli_art.Text(f"threshold={threshold}")

        try:
            with patch("cli_art.time.sleep"):
                cli_art._reveal_banner(
                    ["AB", "CD"],
                    [["#000000", "#111111"], ["#222222", "#ffffff"]],
                    render_frame,
                )
        finally:
            cli_art.console = original

        self.assertGreater(mock_live.update.call_count, 1)


class TestDisplayMainBanner(unittest.TestCase):

    @patch("cli_art.jd_manager.count_completed_resumes", return_value=1)
    @patch("cli_art.jd_manager.get_pending_jds", return_value=["b.json", "c.json"])
    def test_runs_without_error_in_non_terminal_mode(
        self, mock_pending, mock_completed
    ):
        console = Console(record=True, width=100, force_terminal=False)
        original = cli_art.console
        cli_art.console = console
        try:
            cli_art.display_main_banner()
        finally:
            cli_art.console = original
        output = console.export_text()
        # Panel rendering right-pads each line before the border, so the
        # substring's own trailing newline never lines up exactly -- strip
        # it before checking containment.
        self.assertIn(cli_art.SUBTITLE.strip(), output)
        self.assertIn("2 Roles Currently Awaiting Resume Creation", output)
        self.assertIn("1 Resumes Customized All-Time", output)

    @patch("cli_art.jd_manager.count_completed_resumes", return_value=1)
    @patch("cli_art.jd_manager.get_pending_jds", return_value=["b.json"])
    def test_stats_are_computed_once_not_per_frame(self, mock_pending, mock_completed):
        """B2: the stats line is constant for the length of the reveal, but was
        recomputed on all 31 frames -- each call walks the whole JD corpus, which
        turned a 1.6s animation into ~27s. Pin the hoist, since the symptom is
        pure latency and nothing else in the suite would notice a regression."""
        console = Console(record=True, width=100, force_terminal=True)
        original = cli_art.console
        cli_art.console = console
        try:
            with patch("cli_art.time.sleep"):
                cli_art.display_main_banner()
        finally:
            cli_art.console = original
        self.assertEqual(mock_pending.call_count, 1)
        self.assertEqual(mock_completed.call_count, 1)


class TestDisplayStatsLine(unittest.TestCase):

    @patch("cli_art.jd_manager.count_completed_resumes", return_value=2)
    @patch("cli_art.jd_manager.get_pending_jds", return_value=["c.json"])
    def test_prints_real_pending_and_tailored_counts(
        self, mock_pending, mock_completed
    ):
        console = Console(record=True, width=100)
        original = cli_art.console
        cli_art.console = console
        try:
            cli_art.display_stats_line()
        finally:
            cli_art.console = original
        output = console.export_text()
        self.assertIn("1 Roles Currently Awaiting Resume Creation", output)
        self.assertIn("2 Resumes Customized All-Time", output)


class TestDisplayTip(unittest.TestCase):

    def test_prints_one_of_the_known_tips(self):
        console = Console(record=True, width=200)
        original = cli_art.console
        cli_art.console = console
        try:
            cli_art.display_tip()
        finally:
            cli_art.console = original
        output = console.export_text()
        clean_output = "".join(c for c in output if c.isalnum()).lower()
        matched = any(
            "".join(c for c in tip if c.isalnum()).lower() in clean_output
            for tip in cli_art.TIPS
        )
        self.assertTrue(matched)


class TestShortWhy(unittest.TestCase):

    def test_empty_or_missing_returns_a_dash(self):
        self.assertEqual(cli_art._short_why(""), "-")
        self.assertEqual(cli_art._short_why(None), "-")

    def test_short_text_returned_as_is(self):
        self.assertEqual(
            cli_art._short_why("Strong tools match."), "Strong tools match"
        )

    def test_takes_only_the_first_sentence(self):
        why = "Strong tools match. Also remote-friendly. A third sentence that shouldn't show."
        self.assertEqual(cli_art._short_why(why), "Strong tools match")

    def test_truncates_a_long_first_sentence_with_ellipsis(self):
        long_sentence = "This is a very long single sentence that goes on and on well past the short-descriptor limit"
        result = cli_art._short_why(long_sentence, max_len=40)
        self.assertTrue(result.endswith("..."))
        self.assertLessEqual(len(result), 43)


class TestRenderFitTable(unittest.TestCase):

    def test_shows_count_title_and_recommendation_legend(self):
        results = [
            {
                "error": False,
                "composite_score": 4.5,
                "recommendation": "Strong pursue",
                "company_name": "Acme",
                "job_title": "Writer",
                "why": "Great fit on tools and seniority.",
            },
            {
                "error": True,
                "composite_score": None,
                "recommendation": None,
                "company_name": "Bad Co",
                "job_title": "Unknown",
            },
        ]
        console = Console(record=True, width=120)
        original = cli_art.console
        cli_art.console = console
        try:
            cli_art.render_fit_table(results)
        finally:
            cli_art.console = original
        output = console.export_text()
        self.assertIn("2 JD(s) evaluated", output)
        self.assertIn("Strong pursue", output)
        self.assertIn("ERROR", output)
        self.assertIn("Great fit on tools and seniority", output)


class TestRenderPipelineTable(unittest.TestCase):

    def _rendered_at_width(self, width, *args, **kwargs):
        console = Console(record=True, width=width)
        original = cli_art.console
        cli_art.console = console
        try:
            cli_art.render_pipeline_table(*args, **kwargs)
        finally:
            cli_art.console = original
        return console.export_text()

    def test_shows_count_status_and_liveness_columns(self):
        rows = [
            {
                "path": "jds/a.json",
                "status": "Pending",
                "company": "Acme",
                "title": "Writer",
                "evaluation": {
                    "composite_score": 4.5,
                    "recommendation": "Strong pursue",
                },
                "liveness": {"result": "active", "checked_at": "2026-07-21T10:00:00"},
            },
            {
                "path": "jds/b.json",
                "status": "Completed",
                "company": "Beta",
                "title": "PM",
                "evaluation": {
                    "composite_score": 3.0,
                    "recommendation": "Selective pursue",
                },
                "liveness": None,
            },
        ]
        # Wide enough (>= B22's ~110-column threshold) that Last
        # Liveness/Follow-up stay in the table.
        output = self._rendered_at_width(140, rows)
        self.assertIn("2 evaluated JD(s)", output)
        self.assertIn("Pending", output)
        self.assertIn("Completed", output)
        self.assertIn("active", output)
        self.assertIn("2026-07-21", output)

    def test_drops_liveness_and_followup_columns_below_110_columns(self):
        # B22: rather than shrinking every column past legibility, the two
        # least-essential-at-a-glance columns disappear entirely below the
        # narrow threshold, and headers never truncate.
        rows = [
            {
                "path": "jds/a.json",
                "status": "Pending",
                "company": "Acme",
                "title": "Writer",
                "evaluation": {
                    "composite_score": 4.5,
                    "recommendation": "Strong pursue",
                },
                "liveness": {"result": "active", "checked_at": "2026-07-21T10:00:00"},
            },
        ]
        output = self._rendered_at_width(80, rows)
        # The hint subtitle legitimately names both dropped columns, so
        # check for absence of their actual data instead of their names.
        self.assertNotIn("active", output)
        self.assertIn("widen your terminal", output)
        self.assertIn("Recommendation", output)
        self.assertIn("Company", output)
        self.assertIn("Pending", output)

    def test_headers_are_never_truncated_at_80_or_100_columns(self):
        rows = [
            {
                "path": "jds/a.json",
                "status": "Pending",
                "company": "Acme",
                "title": "Writer",
                "evaluation": {
                    "composite_score": 4.5,
                    "recommendation": "Strong pursue",
                },
            },
        ]
        for width in (80, 100):
            output = self._rendered_at_width(width, rows)
            self.assertIn(
                "Recommendation", output, f"header truncated at width={width}"
            )
            self.assertIn("Company", output, f"header truncated at width={width}")
            self.assertIn("Status", output, f"header truncated at width={width}")

    def test_shows_followup_status_and_urgency(self):
        import datetime

        overdue_at = (datetime.datetime.now() - datetime.timedelta(days=10)).isoformat(
            timespec="seconds"
        )
        rows = [
            {
                "path": "jds/a.json",
                "status": "Completed",
                "company": "Acme",
                "title": "Writer",
                "evaluation": {
                    "composite_score": 4.5,
                    "recommendation": "Strong pursue",
                },
                "liveness": None,
                "application": {
                    "status": "Applied",
                    "status_changed_at": overdue_at,
                    "follow_up_count": 0,
                },
            },
        ]
        output = self._rendered_at_width(140, rows)
        self.assertIn("Applied", output)
        self.assertIn("overdue", output)

    def test_start_index_numbers_the_hash_column_from_an_offset(self):
        rows = [
            {
                "path": "jds/a.json",
                "status": "Pending",
                "company": "Acme",
                "title": "Writer",
                "evaluation": {
                    "composite_score": 4.5,
                    "recommendation": "Strong pursue",
                },
            },
        ]
        output = _rendered(cli_art.render_pipeline_table, rows, start_index=51)
        self.assertIn("51", output)

    def test_title_override_replaces_the_default_count_title(self):
        rows = [
            {
                "path": "jds/a.json",
                "status": "Pending",
                "company": "Acme",
                "title": "Writer",
                "evaluation": {
                    "composite_score": 4.5,
                    "recommendation": "Strong pursue",
                },
            },
        ]
        output = _rendered(
            cli_art.render_pipeline_table, rows, title="Page 2/3 -- rows 51-52 of 120"
        )
        self.assertIn("Page 2/3 -- rows 51-52 of 120", output)
        self.assertNotIn("1 evaluated JD(s)", output)


class TestRenderComparisonTable(unittest.TestCase):

    def test_shows_one_column_per_jd_and_dimension_rows(self):
        rows = [
            {
                "company": "Acme",
                "title": "Writer",
                "evaluation": {
                    "composite_score": 4.5,
                    "recommendation": "Strong pursue",
                    "archetype": "Content Lead",
                    "fit_subscores": {
                        "functional_alignment": 5,
                        "north_star_alignment": 4,
                    },
                    "interview_odds_subscores": {"title_continuity": 4},
                    "practical_pursue_subscores": {"remote_quality": 4},
                },
            },
            {
                "company": "Beta",
                "title": "PM",
                "evaluation": {
                    "composite_score": 3.0,
                    "recommendation": "Selective pursue",
                    "archetype": "Ops Generalist",
                    "fit_subscores": {
                        "functional_alignment": 3,
                        "north_star_alignment": 2,
                    },
                    "interview_odds_subscores": {"title_continuity": 2},
                    "practical_pursue_subscores": {"remote_quality": 2},
                },
            },
        ]
        output = _rendered(cli_art.render_comparison_table, rows)
        self.assertIn("Comparing 2 JD(s)", output)
        self.assertIn("Acme", output)
        self.assertIn("Beta", output)
        self.assertIn("Content Lead", output)
        self.assertIn("Functional", output)


class TestRenderDoctorReport(unittest.TestCase):

    def test_all_passed_shows_success_summary_no_fixes(self):
        checks = [
            {"name": "Python version", "passed": True, "detail": "3.13.0", "fix": ""},
            {
                "name": "Node.js",
                "passed": True,
                "detail": "/usr/local/bin/node",
                "fix": "",
            },
        ]
        output = _rendered(cli_art.render_doctor_report, checks)
        self.assertIn("All checks passed", output)
        self.assertNotIn("problem(s) found", output)

    def test_failures_show_count_and_one_line_fix_each(self):
        checks = [
            {"name": "Python version", "passed": True, "detail": "3.13.0", "fix": ""},
            {
                "name": "Node.js",
                "passed": False,
                "detail": "not found on PATH",
                "fix": "Install Node.js",
            },
        ]
        output = _rendered(cli_art.render_doctor_report, checks)
        self.assertIn("1 problem(s) found", output)
        self.assertIn("Install Node.js", output)

    def test_test_result_summary_included_when_provided(self):
        checks = [
            {"name": "Python version", "passed": True, "detail": "3.13.0", "fix": ""}
        ]
        output = _rendered(
            cli_art.render_doctor_report,
            checks,
            test_result=(True, "Ran 5 tests in 0.01s\nOK"),
        )
        self.assertIn("Test suite", output)
        self.assertIn("Ran 5 tests", output)

    def test_no_test_result_line_when_none(self):
        checks = [
            {"name": "Python version", "passed": True, "detail": "3.13.0", "fix": ""}
        ]
        output = _rendered(cli_art.render_doctor_report, checks, None)
        self.assertNotIn("Test suite", output)


class TestDisplayBreadcrumb(unittest.TestCase):

    def test_prints_a_one_line_rule_not_a_full_panel(self):
        console = Console(record=True, width=100)
        original = cli_art.console
        cli_art.console = console
        try:
            cli_art.display_breadcrumb()
        finally:
            cli_art.console = original
        output = console.export_text()
        self.assertIn("resume-builder", output)
        # A breadcrumb rule is one line of dashes + text -- a full banner
        # box would include multiple '=' or '═' (double-line) rows.
        self.assertNotIn("═", output)


class TestRenderBulletBankStatus(unittest.TestCase):

    def test_shows_stage_numbers_labels_status_and_maintenance_rows(self):
        stage_rows = [
            (
                1,
                "Audit Bullet Bank (Score Quality)",
                "Up to date",
                "as of 2026-07-15 10:00",
            ),
            (2, "Cluster & Classify Bullets", "Stale", ""),
            (3, "Rewrite Weak Bullets", "Never run", ""),
        ]
        maintenance_rows = [("Triage Needs-Review Queue", "3 row(s) waiting")]

        console = Console(record=True, width=120)
        original = cli_art.console
        cli_art.console = console
        try:
            cli_art.render_bullet_bank_status(stage_rows, maintenance_rows)
        finally:
            cli_art.console = original
        output = console.export_text()
        self.assertIn("Audit Bullet Bank (Score Quality)", output)
        self.assertIn("Up to date", output)
        self.assertIn("Stale", output)
        self.assertIn("Never run", output)
        self.assertIn("Triage Needs-Review Queue", output)
        self.assertIn("3 row(s) waiting", output)


class TestDisplayHelp(unittest.TestCase):

    def test_renders_every_command_and_description(self):
        output = _rendered(cli_art.display_help)
        for command, description in cli_art.HELP_ENTRIES:
            self.assertIn(command, output)
        self.assertIn("launch the interactive menu", output)


class TestScanActivity(unittest.TestCase):

    def test_step_prints_themed_line_with_icon_and_source(self):
        activity = cli_art.new_scan_activity()
        with activity:
            with patch("cli_art.console.print") as mock_print:
                activity.step(
                    "success", "JobRight", "Found Senior Data Engineer @ Acme"
                )
        mock_print.assert_called_once_with(
            f"  {cli_art.theme.colorize_icon('success')} [bold]JobRight[/bold] "
            "Found Senior Data Engineer @ Acme",
            soft_wrap=True,
        )

    def test_step_has_no_eta_before_start_source(self):
        activity = cli_art.new_scan_activity()
        with activity:
            with patch("cli_art.console.print") as mock_print:
                activity.step("success", "Boards", "checked remoteok")
        printed = mock_print.call_args[0][0]
        self.assertNotIn("remaining)", printed)

    def test_step_shows_eta_from_second_call_after_start_source(self):
        activity = cli_art.new_scan_activity()
        with activity:
            activity.start_source(3, label="Checking")
            with patch("cli_art.console.print") as mock_print:
                activity.step("success", "ATS", "first item")
                activity.step("success", "ATS", "second item")
        first_printed = mock_print.call_args_list[0].args[0]
        second_printed = mock_print.call_args_list[1].args[0]
        self.assertNotIn("remaining)", first_printed)
        self.assertIn("remaining)", second_printed)

    def test_tally_updates_pinned_task_description(self):
        activity = cli_art.new_scan_activity()
        with activity:
            activity.tally(fetched=12, written=9, skipped=3, errors=0)
            task = next(
                t for t in activity._progress.tasks if t.id == activity._task_id
            )
        self.assertIn("Fetched 12", task.description)
        self.assertIn("Written 9", task.description)
        self.assertIn("Skipped 3", task.description)
        self.assertIn("Errors 0", task.description)

    def test_tally_is_cumulative_across_calls(self):
        activity = cli_art.new_scan_activity()
        with activity:
            activity.tally(fetched=5)
            activity.tally(written=2)
            task = next(
                t for t in activity._progress.tasks if t.id == activity._task_id
            )
        self.assertIn("Fetched 5", task.description)
        self.assertIn("Written 2", task.description)


class TestMarkupEscaping(unittest.TestCase):

    def test_cli_warning_does_not_swallow_bracketed_dynamic_text(self):
        output = _rendered(
            cli_art.cli_warning, "[NEEDS_REWRITE] Led team to grow revenue"
        )
        self.assertIn("[NEEDS_REWRITE]", output)

    def test_cli_error_does_not_swallow_bracketed_dynamic_text(self):
        output = _rendered(cli_art.cli_error, "[LinkedIn ON_ERROR] timeout")
        self.assertIn("[LinkedIn ON_ERROR]", output)

    def test_cli_info_does_not_swallow_bracketed_dynamic_text(self):
        output = _rendered(cli_art.cli_info, "Loaded [workday] 42 bullets")
        self.assertIn("[workday]", output)

    def test_cli_success_does_not_swallow_bracketed_dynamic_text(self):
        output = _rendered(cli_art.cli_success, "Wrote [42] rows")
        self.assertIn("[42]", output)


class TestScanActivityMarkupEscaping(unittest.TestCase):

    def test_step_message_with_brackets_is_not_swallowed(self):
        activity = cli_art.new_scan_activity()
        with activity:
            with patch("cli_art.console.print") as mock_print:
                activity.step("success", "ATS", "Found [Series B startup] listing")
        printed = mock_print.call_args[0][0]
        self.assertIn("[Series B startup]", printed)


class TestRenderRewriteQueueTable(unittest.TestCase):

    def test_renders_rank_source_composite_manager_test_and_bullet(self):
        rows = [
            {
                "rank": 1,
                "source": "keeper_audit",
                "composite": 42.0,
                "manager_test": "FAIL",
                "bullet": "Led [Series B] growth",
            },
        ]
        output = _rendered(cli_art.render_rewrite_queue_table, rows, "Top 10 Worst")
        self.assertIn("keeper_audit", output)
        self.assertIn("FAIL", output)
        self.assertIn("Led [Series B] growth", output)
        self.assertIn("Top 10 Worst", output)


class TestRenderTriageSummaryTable(unittest.TestCase):

    def test_renders_all_five_counts(self):
        output = _rendered(
            cli_art.render_triage_summary_table,
            {
                "keep": 3,
                "rewrite": 1,
                "retire": 0,
                "duplicate": 2,
                "leftover": 5,
            },
        )
        self.assertIn("3", output)
        self.assertIn("KEEP", output)
        self.assertIn("REWRITE", output)
        self.assertIn("RETIRE", output)
        self.assertIn("DUPLICATE", output)
        self.assertIn("Leftover", output)


class TestThinkingStatus(unittest.TestCase):

    def test_thinking_status_runs_and_cleans_up(self):
        import time

        with cli_art.thinking_status("Analyzing job posting..."):
            time.sleep(0.05)
        # Successfully entered and exited context manager without error


class TestThemeTokens(unittest.TestCase):

    def test_catppuccin_thinking_tokens_defined_in_theme(self):
        import theme

        self.assertTrue(hasattr(theme, "PEACH"))
        self.assertTrue(hasattr(theme, "PINK"))
        self.assertTrue(hasattr(theme, "MAUVE"))
        self.assertTrue(hasattr(theme, "LAVENDER"))
        self.assertTrue(hasattr(theme, "BLUE"))
        self.assertTrue(hasattr(theme, "SKY"))
        self.assertTrue(hasattr(theme, "THINKING_GRADIENT_COLORS"))
        self.assertEqual(len(theme.THINKING_GRADIENT_COLORS), 6)


class TestSparkleBannerAndCelebration(unittest.TestCase):

    def test_sparkle_banner_renders(self):
        output = _rendered(cli_art.sparkle_banner, "Job Search Playbook", "Step 1 of 3")
        self.assertIn("Job Search Playbook", output)
        self.assertIn("Step 1 of 3", output)
        self.assertIn("✦", output)

    def test_render_sparkle_celebration_renders(self):
        output = _rendered(
            cli_art.render_sparkle_celebration,
            "Resume Tailored Successfully!",
            "Your new application is ready.",
            ["Review in dashboard", "Apply to job"],
        )
        self.assertIn("Resume Tailored Successfully!", output)
        self.assertIn("What to do next:", output)
        self.assertIn("Review in dashboard", output)
        self.assertIn("Apply to job", output)


if __name__ == "__main__":
    unittest.main()
