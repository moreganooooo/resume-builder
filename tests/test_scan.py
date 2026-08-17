import json
import logging
import os
import sys
import unittest
from unittest.mock import ANY, patch

SCRIPTS_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts"
)
sys.path.insert(0, SCRIPTS_DIR)

import jd_manager  # noqa: E402
import scan  # noqa: E402


def _empty_known_jobs_index() -> dict:
    return {"job_keys": set(), "url_company_pairs": set(), "normalized_pairs": set()}


class TestWriteJdFile(unittest.TestCase):

    def setUp(self):
        self.tmp_dir = os.path.join(os.path.dirname(__file__), "_tmp_scan_write")
        os.makedirs(self.tmp_dir, exist_ok=True)
        self._real_jds_dir = jd_manager.JDS_DIR
        jd_manager.JDS_DIR = self.tmp_dir

    def tearDown(self):
        jd_manager.JDS_DIR = self._real_jds_dir
        for name in os.listdir(self.tmp_dir):
            os.remove(os.path.join(self.tmp_dir, name))
        os.rmdir(self.tmp_dir)

    def test_writes_a_real_job_dict_to_a_sanitized_filename(self):
        job = {
            "company_name": "Acme, Inc.",
            "job_title": "Content Strategist!",
            "source_job_id": "123",
        }
        dest = scan._write_jd_file(job)
        self.assertTrue(os.path.exists(dest))
        self.assertIn("AcmeInc", os.path.basename(dest))
        self.assertIn("ContentStrategist", os.path.basename(dest))
        with open(dest, "r", encoding="utf-8") as f:
            self.assertEqual(json.load(f), job)

    def test_appends_a_counter_suffix_on_filename_collision(self):
        job = {"company_name": "Acme", "job_title": "Role"}
        first = scan._write_jd_file(job)
        second = scan._write_jd_file(job)
        self.assertNotEqual(first, second)
        self.assertTrue(os.path.exists(first))
        self.assertTrue(os.path.exists(second))


class TestRunScanDedup(unittest.TestCase):

    def setUp(self):
        patcher = patch(
            "scan.jd_manager.build_known_jobs_index",
            side_effect=_empty_known_jobs_index,
        )
        patcher.start()
        self.addCleanup(patcher.stop)

    @patch("scan.jd_manager.job_key_known", return_value=False)
    @patch("scan.jd_manager.JDTracker")
    def test_passes_job_title_to_dedup_check(self, mock_tracker_cls, mock_known):
        job = {
            "source_job_id": "abc123",
            "company_name": "Acme",
            "job_title": "Content Strategist",
            "source_url": "https://example.com/job/1",
        }
        with (
            patch.dict(
                scan.SOURCE_FETCHERS, {"jobright": lambda **kwargs: [job]}, clear=True
            ),
            patch("scan.scan_jobright.fetch_jobright_jobs"),
            patch.object(scan, "_write_jd_file", return_value="jds/fake.json"),
        ):
            scan.run_scan(["jobright"], verify=False)
        mock_known.assert_called_once_with(
            "abc123",
            tracker=mock_tracker_cls.return_value,
            source_url="https://example.com/job/1",
            company_name="Acme",
            job_title="Content Strategist",
            index=ANY,
        )

    @patch("scan.jd_manager.job_key_known", return_value=False)
    @patch("scan.jd_manager.JDTracker")
    def test_falls_back_to_source_url_for_dedup_when_no_source_job_id(
        self, mock_tracker_cls, mock_known
    ):
        # Board-provider jobs (scan_boards.py) never have a source_job_id,
        # only a URL -- dedup must still run for them, not silently skip.
        job = {
            "company_name": "Acme",
            "job_title": "Content Strategist",
            "source_url": "https://example.com/job/1",
        }
        with (
            patch.dict(
                scan.SOURCE_FETCHERS, {"boards": lambda **kwargs: [job]}, clear=True
            ),
            patch.object(scan, "_write_jd_file", return_value="jds/fake.json"),
        ):
            scan.run_scan(["boards"], verify=False)
        mock_known.assert_called_once_with(
            "https://example.com/job/1",
            tracker=mock_tracker_cls.return_value,
            source_url="https://example.com/job/1",
            company_name="Acme",
            job_title="Content Strategist",
            index=ANY,
        )


class TestRunScanVerify(unittest.TestCase):

    def setUp(self):
        patcher = patch(
            "scan.jd_manager.build_known_jobs_index",
            side_effect=_empty_known_jobs_index,
        )
        patcher.start()
        self.addCleanup(patcher.stop)

    @patch("scan.jd_manager.job_key_known", return_value=False)
    @patch("scan.jd_manager.JDTracker")
    def test_verify_runs_by_default_on_newly_written_paths(
        self, mock_tracker_cls, mock_known
    ):
        job = {
            "company_name": "Acme",
            "job_title": "Content Strategist",
            "source_url": "https://x.com/1",
        }
        with (
            patch.dict(
                scan.SOURCE_FETCHERS, {"boards": lambda **kwargs: [job]}, clear=True
            ),
            patch.object(scan, "_write_jd_file", return_value="/tmp/fake.json"),
            patch(
                "scan.liveness.verify_jd_paths",
                return_value={"expired_source_paths": []},
            ) as mock_verify,
        ):
            scan.run_scan(["boards"])
        mock_verify.assert_called_once_with(["/tmp/fake.json"], activity=ANY)

    @patch("scan.jd_manager.job_key_known", return_value=False)
    @patch("scan.jd_manager.JDTracker")
    def test_verify_false_skips_the_liveness_pass_entirely(
        self, mock_tracker_cls, mock_known
    ):
        job = {
            "company_name": "Acme",
            "job_title": "Content Strategist",
            "source_url": "https://x.com/1",
        }
        with (
            patch.dict(
                scan.SOURCE_FETCHERS, {"boards": lambda **kwargs: [job]}, clear=True
            ),
            patch.object(scan, "_write_jd_file", return_value="/tmp/fake.json"),
            patch("scan.liveness.verify_jd_paths") as mock_verify,
        ):
            scan.run_scan(["boards"], verify=False)
        mock_verify.assert_not_called()

    @patch("scan.jd_manager.job_key_known", return_value=False)
    @patch("scan.jd_manager.JDTracker")
    def test_a_posting_verify_finds_expired_is_dropped_from_written_count_and_report(
        self, mock_tracker_cls, mock_known
    ):
        jobs = [
            {
                "company_name": "Acme",
                "job_title": "Still Open",
                "source_url": "https://x.com/1",
            },
            {
                "company_name": "Ghost Co",
                "job_title": "Already Gone",
                "source_url": "https://x.com/2",
            },
        ]
        paths = iter(["/tmp/still-open.json", "/tmp/already-gone.json"])
        with (
            patch.dict(
                scan.SOURCE_FETCHERS, {"boards": lambda **kwargs: jobs}, clear=True
            ),
            patch.object(scan, "_write_jd_file", side_effect=lambda job: next(paths)),
            patch(
                "scan.liveness.verify_jd_paths",
                return_value={"expired_source_paths": ["/tmp/already-gone.json"]},
            ),
            patch("scan.cli_art.render_scan_report") as mock_report,
        ):
            written = scan.run_scan(["boards"])

        self.assertEqual(written, 1)
        source_results, total_written = mock_report.call_args[0]
        self.assertEqual(total_written, 1)
        boards_result = source_results[0]
        self.assertEqual(boards_result["written"], 1)
        self.assertEqual(boards_result["dropped_expired"], 1)
        self.assertEqual(
            boards_result["new_jobs"], [{"company": "Acme", "title": "Still Open"}]
        )


class TestScanWarningCollection(unittest.TestCase):
    """scan._ScanWarningCollector / _summarize_warnings -- warnings
    scan_boards.py/scan_ats.py log via _scan_warning() (posting-text
    fetch failures, provider failures) get grouped and attached to the
    themed report instead of dumping as a raw wall of WARNING:root:
    lines."""

    def setUp(self):
        patcher = patch(
            "scan.jd_manager.build_known_jobs_index",
            side_effect=_empty_known_jobs_index,
        )
        patcher.start()
        self.addCleanup(patcher.stop)

    @patch("scan.jd_manager.job_key_known", return_value=False)
    @patch("scan.jd_manager.JDTracker")
    def test_warnings_are_grouped_by_provider_kind_and_reason(
        self, mock_tracker_cls, mock_known
    ):
        def fake_fetch(**kwargs):
            for _ in range(3):
                logging.warning(
                    "boom",
                    extra={
                        "scan_warning": True,
                        "kind": "posting_text_failed",
                        "provider_id": "workday",
                        "reason": "HTTP 404",
                    },
                )
            logging.warning(
                "boom2",
                extra={
                    "scan_warning": True,
                    "kind": "provider_failed",
                    "provider_id": "greenhouse",
                    "reason": "HTTP 404",
                },
            )
            return []

        with (
            patch.dict(scan.SOURCE_FETCHERS, {"ats": fake_fetch}, clear=True),
            patch("scan.cli_art.render_scan_report") as mock_report,
        ):
            scan.run_scan(["ats"], verify=False)

        source_results, _ = mock_report.call_args[0]
        warnings = source_results[0]["warnings"]
        self.assertEqual(
            warnings[0],
            {
                "provider_id": "workday",
                "kind": "posting_text_failed",
                "reason": "HTTP 404",
                "count": 3,
            },
        )
        self.assertEqual(
            warnings[1],
            {
                "provider_id": "greenhouse",
                "kind": "provider_failed",
                "reason": "HTTP 404",
                "count": 1,
            },
        )

    @patch("scan.jd_manager.job_key_known", return_value=False)
    @patch("scan.jd_manager.JDTracker")
    def test_warnings_without_the_scan_warning_marker_are_ignored(
        self, mock_tracker_cls, mock_known
    ):
        def fake_fetch(**kwargs):
            logging.warning("some unrelated warning from somewhere else entirely")
            return []

        with (
            patch.dict(scan.SOURCE_FETCHERS, {"ats": fake_fetch}, clear=True),
            patch("scan.cli_art.render_scan_report") as mock_report,
        ):
            scan.run_scan(["ats"], verify=False)

        source_results, _ = mock_report.call_args[0]
        self.assertEqual(source_results[0]["warnings"], [])

    @patch("scan.jd_manager.job_key_known", return_value=False)
    @patch("scan.jd_manager.JDTracker")
    def test_warnings_are_scoped_to_the_source_that_produced_them(
        self, mock_tracker_cls, mock_known
    ):
        def boards_fetch(**kwargs):
            logging.warning(
                "boom",
                extra={
                    "scan_warning": True,
                    "kind": "provider_failed",
                    "provider_id": "himalayas",
                    "reason": "HTTP 403",
                },
            )
            return []

        def ats_fetch(**kwargs):
            return []

        with (
            patch.dict(
                scan.SOURCE_FETCHERS,
                {"boards": boards_fetch, "ats": ats_fetch},
                clear=True,
            ),
            patch("scan.cli_art.render_scan_report") as mock_report,
        ):
            scan.run_scan(["boards", "ats"], verify=False)

        source_results, _ = mock_report.call_args[0]
        boards_result = next(r for r in source_results if r["source"] == "boards")
        ats_result = next(r for r in source_results if r["source"] == "ats")
        self.assertEqual(len(boards_result["warnings"]), 1)
        self.assertEqual(ats_result["warnings"], [])

    def test_removes_the_handler_after_run_so_it_never_accumulates(self):
        root_logger = logging.getLogger()
        handlers_before = len(root_logger.handlers)
        with (
            patch.dict(scan.SOURCE_FETCHERS, {"ats": lambda **kwargs: []}, clear=True),
            patch("scan.jd_manager.job_key_known", return_value=False),
            patch("scan.jd_manager.JDTracker"),
            patch("scan.cli_art.render_scan_report"),
        ):
            scan.run_scan(["ats"], verify=False)
        self.assertEqual(len(root_logger.handlers), handlers_before)


if __name__ == "__main__":
    unittest.main()
