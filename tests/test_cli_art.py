import os
import sys
import unittest
from unittest.mock import patch

SCRIPTS_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts")
sys.path.insert(0, SCRIPTS_DIR)

from rich.console import Console

import cli_art  # noqa: E402


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
                cli_art._reveal_banner(["AB", "CD"], [["#000000", "#111111"], ["#222222", "#ffffff"]], render_frame)
        finally:
            cli_art.console = original

        self.assertGreater(mock_live.update.call_count, 1)


class TestDisplayMainBanner(unittest.TestCase):

    @patch("cli_art.jd_manager.get_completed_jds", return_value=["a.json"])
    @patch("cli_art.jd_manager.get_pending_jds", return_value=["b.json", "c.json"])
    def test_runs_without_error_in_non_terminal_mode(self, mock_pending, mock_completed):
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


class TestDisplayStatsLine(unittest.TestCase):

    @patch("cli_art.jd_manager.get_completed_jds", return_value=["a.json", "b.json"])
    @patch("cli_art.jd_manager.get_pending_jds", return_value=["c.json"])
    def test_prints_real_pending_and_tailored_counts(self, mock_pending, mock_completed):
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
        self.assertTrue(any(tip in output for tip in cli_art.TIPS))


class TestShortWhy(unittest.TestCase):

    def test_empty_or_missing_returns_a_dash(self):
        self.assertEqual(cli_art._short_why(""), "-")
        self.assertEqual(cli_art._short_why(None), "-")

    def test_short_text_returned_as_is(self):
        self.assertEqual(cli_art._short_why("Strong tools match."), "Strong tools match")

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
            {"error": False, "composite_score": 4.5, "recommendation": "Strong pursue",
             "company_name": "Acme", "job_title": "Writer", "why": "Great fit on tools and seniority."},
            {"error": True, "composite_score": None, "recommendation": None,
             "company_name": "Bad Co", "job_title": "Unknown"},
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

    def test_shows_count_status_and_liveness_columns(self):
        rows = [
            {"path": "jds/a.json", "status": "Pending", "company": "Acme", "title": "Writer",
             "evaluation": {"composite_score": 4.5, "recommendation": "Strong pursue"},
             "liveness": {"result": "active", "checked_at": "2026-07-21T10:00:00"}},
            {"path": "jds/b.json", "status": "Completed", "company": "Beta", "title": "PM",
             "evaluation": {"composite_score": 3.0, "recommendation": "Selective pursue"},
             "liveness": None},
        ]
        output = _rendered(cli_art.render_pipeline_table, rows)
        self.assertIn("2 evaluated JD(s)", output)
        self.assertIn("Pending", output)
        self.assertIn("Completed", output)
        self.assertIn("active", output)
        self.assertIn("2026-07-21", output)


class TestRenderComparisonTable(unittest.TestCase):

    def test_shows_one_column_per_jd_and_dimension_rows(self):
        rows = [
            {"company": "Acme", "title": "Writer", "evaluation": {
                "composite_score": 4.5, "recommendation": "Strong pursue", "archetype": "Content Lead",
                "dimension_scores": {"cv_profile_match": 5, "remote_quality": 4},
            }},
            {"company": "Beta", "title": "PM", "evaluation": {
                "composite_score": 3.0, "recommendation": "Selective pursue", "archetype": "Ops Generalist",
                "dimension_scores": {"cv_profile_match": 3, "remote_quality": 2},
            }},
        ]
        output = _rendered(cli_art.render_comparison_table, rows)
        self.assertIn("Comparing 2 JD(s)", output)
        self.assertIn("Acme", output)
        self.assertIn("Beta", output)
        self.assertIn("Content Lead", output)
        self.assertIn("CV Match", output)


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
            (1, "Audit Bullet Bank (Score Quality)", "Up to date", "as of 2026-07-15 10:00"),
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


if __name__ == "__main__":
    unittest.main()
