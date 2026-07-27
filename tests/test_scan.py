import json
import os
import sys
import unittest
from unittest.mock import patch

SCRIPTS_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts")
sys.path.insert(0, SCRIPTS_DIR)

import jd_manager  # noqa: E402
import scan  # noqa: E402


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
        job = {"company_name": "Acme, Inc.", "job_title": "Content Strategist!", "source_job_id": "123"}
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

    @patch("scan.jd_manager.job_key_known", return_value=False)
    @patch("scan.jd_manager.JDTracker")
    def test_passes_job_title_to_dedup_check(self, mock_tracker_cls, mock_known):
        job = {
            "source_job_id": "abc123", "company_name": "Acme",
            "job_title": "Content Strategist", "source_url": "https://example.com/job/1",
        }
        with patch.dict(scan.SOURCE_FETCHERS, {"jobright": lambda: [job]}, clear=True), \
             patch("scan.scan_jobright.fetch_jobright_jobs"), \
             patch.object(scan, "_write_jd_file", return_value="jds/fake.json"):
            scan.run_scan(["jobright"], verify=False)
        mock_known.assert_called_once_with(
            "abc123", tracker=mock_tracker_cls.return_value,
            source_url="https://example.com/job/1", company_name="Acme",
            job_title="Content Strategist",
        )

    @patch("scan.jd_manager.job_key_known", return_value=False)
    @patch("scan.jd_manager.JDTracker")
    def test_falls_back_to_source_url_for_dedup_when_no_source_job_id(self, mock_tracker_cls, mock_known):
        # Board-provider jobs (scan_boards.py) never have a source_job_id,
        # only a URL -- dedup must still run for them, not silently skip.
        job = {
            "company_name": "Acme", "job_title": "Content Strategist",
            "source_url": "https://example.com/job/1",
        }
        with patch.dict(scan.SOURCE_FETCHERS, {"boards": lambda: [job]}, clear=True), \
             patch.object(scan, "_write_jd_file", return_value="jds/fake.json"):
            scan.run_scan(["boards"], verify=False)
        mock_known.assert_called_once_with(
            "https://example.com/job/1", tracker=mock_tracker_cls.return_value,
            source_url="https://example.com/job/1", company_name="Acme",
            job_title="Content Strategist",
        )


class TestRunScanVerify(unittest.TestCase):

    @patch("scan.jd_manager.job_key_known", return_value=False)
    @patch("scan.jd_manager.JDTracker")
    def test_verify_runs_by_default_on_newly_written_paths(self, mock_tracker_cls, mock_known):
        job = {"company_name": "Acme", "job_title": "Content Strategist", "source_url": "https://x.com/1"}
        with patch.dict(scan.SOURCE_FETCHERS, {"boards": lambda: [job]}, clear=True), \
             patch.object(scan, "_write_jd_file", return_value="/tmp/fake.json"), \
             patch("scan.liveness.verify_jd_paths", return_value={"expired_paths": []}) as mock_verify:
            scan.run_scan(["boards"])
        mock_verify.assert_called_once_with(["/tmp/fake.json"])

    @patch("scan.jd_manager.job_key_known", return_value=False)
    @patch("scan.jd_manager.JDTracker")
    def test_verify_false_skips_the_liveness_pass_entirely(self, mock_tracker_cls, mock_known):
        job = {"company_name": "Acme", "job_title": "Content Strategist", "source_url": "https://x.com/1"}
        with patch.dict(scan.SOURCE_FETCHERS, {"boards": lambda: [job]}, clear=True), \
             patch.object(scan, "_write_jd_file", return_value="/tmp/fake.json"), \
             patch("scan.liveness.verify_jd_paths") as mock_verify:
            scan.run_scan(["boards"], verify=False)
        mock_verify.assert_not_called()

    @patch("scan.jd_manager.job_key_known", return_value=False)
    @patch("scan.jd_manager.JDTracker")
    def test_a_posting_verify_finds_expired_is_dropped_from_written_count_and_report(self, mock_tracker_cls, mock_known):
        jobs = [
            {"company_name": "Acme", "job_title": "Still Open", "source_url": "https://x.com/1"},
            {"company_name": "Ghost Co", "job_title": "Already Gone", "source_url": "https://x.com/2"},
        ]
        paths = iter(["/tmp/still-open.json", "/tmp/already-gone.json"])
        with patch.dict(scan.SOURCE_FETCHERS, {"boards": lambda: jobs}, clear=True), \
             patch.object(scan, "_write_jd_file", side_effect=lambda job: next(paths)), \
             patch("scan.liveness.verify_jd_paths", return_value={"expired_paths": ["/tmp/already-gone.json"]}), \
             patch("scan.cli_art.render_scan_report") as mock_report:
            written = scan.run_scan(["boards"])

        self.assertEqual(written, 1)
        source_results, total_written = mock_report.call_args[0]
        self.assertEqual(total_written, 1)
        boards_result = source_results[0]
        self.assertEqual(boards_result["written"], 1)
        self.assertEqual(boards_result["dropped_expired"], 1)
        self.assertEqual(boards_result["new_jobs"], [{"company": "Acme", "title": "Still Open"}])


if __name__ == "__main__":
    unittest.main()
