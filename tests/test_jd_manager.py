import datetime
import hashlib
import json
import os
import sys
import unittest
from unittest.mock import patch

SCRIPTS_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts"
)
sys.path.insert(0, SCRIPTS_DIR)

import jd_manager  # noqa: E402


class TestComputeJobKey(unittest.TestCase):

    def setUp(self):
        self.tmp_dir = os.path.join(os.path.dirname(__file__), "_tmp_jd_manager")
        os.makedirs(self.tmp_dir, exist_ok=True)

    def tearDown(self):
        for name in os.listdir(self.tmp_dir):
            os.remove(os.path.join(self.tmp_dir, name))
        os.rmdir(self.tmp_dir)

    def _write(self, name, content):
        path = os.path.join(self.tmp_dir, name)
        with open(path, "w", encoding="utf-8") as f:
            f.write(content)
        return path

    def test_uses_source_job_id_when_present(self):
        path = self._write(
            "job.json",
            json.dumps(
                {
                    "source_job_id": "abc123",
                    "job_title": "Engineer",
                    "company_name": "Acme",
                }
            ),
        )
        self.assertEqual(jd_manager.compute_job_key(path), "abc123")

    def test_hashes_plain_text_content(self):
        path = self._write("job.txt", "We are hiring a Widget Engineer.")
        expected = hashlib.sha256(b"We are hiring a Widget Engineer.").hexdigest()
        self.assertEqual(jd_manager.compute_job_key(path), expected)

    def test_same_content_same_key(self):
        path_a = self._write("a.txt", "identical posting text")
        path_b = self._write("b.txt", "identical posting text")
        self.assertEqual(
            jd_manager.compute_job_key(path_a), jd_manager.compute_job_key(path_b)
        )

    def test_different_content_different_key(self):
        path_a = self._write("a.txt", "posting one")
        path_b = self._write("b.txt", "posting two")
        self.assertNotEqual(
            jd_manager.compute_job_key(path_a), jd_manager.compute_job_key(path_b)
        )

    def test_json_object_without_source_job_id_falls_back_to_hash(self):
        content = json.dumps({"job_title": "Engineer", "company_name": "Acme"})
        path = self._write("job.json", content)
        expected = hashlib.sha256(content.encode("utf-8")).hexdigest()
        self.assertEqual(jd_manager.compute_job_key(path), expected)


class TestExtractJobMeta(unittest.TestCase):

    def setUp(self):
        self.tmp_dir = os.path.join(os.path.dirname(__file__), "_tmp_jd_manager_meta")
        os.makedirs(self.tmp_dir, exist_ok=True)

    def tearDown(self):
        for name in os.listdir(self.tmp_dir):
            os.remove(os.path.join(self.tmp_dir, name))
        os.rmdir(self.tmp_dir)

    def _write(self, name, content):
        path = os.path.join(self.tmp_dir, name)
        with open(path, "w", encoding="utf-8") as f:
            f.write(content)
        return path

    def test_reads_title_and_company_from_json(self):
        path = self._write(
            "job.json",
            json.dumps(
                {
                    "job_title": "Content Strategist",
                    "company_name": "Abnormal AI",
                }
            ),
        )
        self.assertEqual(
            jd_manager.extract_job_meta(path), ("Content Strategist", "Abnormal AI")
        )

    def test_plain_text_returns_empty_strings(self):
        path = self._write("job.txt", "Just a plain job description with no JSON.")
        self.assertEqual(jd_manager.extract_job_meta(path), ("", ""))


class TestExtractSourceUrl(unittest.TestCase):

    def setUp(self):
        self.tmp_dir = os.path.join(os.path.dirname(__file__), "_tmp_jd_manager_url")
        os.makedirs(self.tmp_dir, exist_ok=True)

    def tearDown(self):
        for name in os.listdir(self.tmp_dir):
            os.remove(os.path.join(self.tmp_dir, name))
        os.rmdir(self.tmp_dir)

    def _write(self, name, content):
        path = os.path.join(self.tmp_dir, name)
        with open(path, "w", encoding="utf-8") as f:
            f.write(content)
        return path

    def test_reads_source_url_from_json(self):
        path = self._write(
            "job.json", json.dumps({"source_url": "https://example.com/job/1"})
        )
        self.assertEqual(
            jd_manager.extract_source_url(path), "https://example.com/job/1"
        )

    def test_missing_source_url_returns_empty_string(self):
        path = self._write("job.json", json.dumps({"job_title": "Role"}))
        self.assertEqual(jd_manager.extract_source_url(path), "")

    def test_plain_text_returns_empty_string(self):
        path = self._write("job.txt", "Just a plain job description with no JSON.")
        self.assertEqual(jd_manager.extract_source_url(path), "")


class TestSplitBatchJds(unittest.TestCase):

    def setUp(self):
        self.tmp_dir = os.path.join(os.path.dirname(__file__), "_tmp_split_batch")
        os.makedirs(self.tmp_dir, exist_ok=True)
        self._real_jds_dir = jd_manager.JDS_DIR
        jd_manager.JDS_DIR = (
            self.tmp_dir
        )  # redirect writes into the temp dir for this test

    def tearDown(self):
        jd_manager.JDS_DIR = self._real_jds_dir
        for name in os.listdir(self.tmp_dir):
            os.remove(os.path.join(self.tmp_dir, name))
        os.rmdir(self.tmp_dir)

    def _write(self, name, content):
        path = os.path.join(self.tmp_dir, name)
        with open(path, "w", encoding="utf-8") as f:
            f.write(content)
        return path

    def test_splits_array_into_one_file_per_job_and_deletes_original(self):
        batch_path = self._write(
            "batch.json",
            json.dumps(
                [
                    {"job_title": "Content Strategist", "company_name": "Abnormal AI"},
                    {
                        "job_title": "Senior Manager, Lifecycle Marketing",
                        "company_name": "Superhuman",
                    },
                ]
            ),
        )

        result_paths = jd_manager.split_batch_jds(batch_path)

        self.assertEqual(len(result_paths), 2)
        self.assertFalse(os.path.exists(batch_path))
        today = datetime.date.today().isoformat()
        for path in result_paths:
            self.assertTrue(os.path.basename(path).startswith(today))
            self.assertTrue(os.path.exists(path))
        with open(result_paths[0], "r", encoding="utf-8") as f:
            self.assertEqual(json.load(f)["company_name"], "Abnormal AI")
        with open(result_paths[1], "r", encoding="utf-8") as f:
            self.assertEqual(json.load(f)["company_name"], "Superhuman")

    def test_single_json_object_passes_through_unchanged(self):
        path = self._write(
            "single.json", json.dumps({"job_title": "Engineer", "company_name": "Acme"})
        )
        result_paths = jd_manager.split_batch_jds(path)
        self.assertEqual(result_paths, [path])
        self.assertTrue(os.path.exists(path))

    def test_plain_text_passes_through_unchanged(self):
        path = self._write("plain.txt", "Not JSON at all.")
        result_paths = jd_manager.split_batch_jds(path)
        self.assertEqual(result_paths, [path])
        self.assertTrue(os.path.exists(path))

    def test_filename_collision_gets_numeric_suffix(self):
        batch_path = self._write(
            "batch2.json",
            json.dumps(
                [
                    {"job_title": "Engineer", "company_name": "Acme"},
                    {"job_title": "Engineer", "company_name": "Acme"},
                ]
            ),
        )
        result_paths = jd_manager.split_batch_jds(batch_path)
        self.assertEqual(len(result_paths), 2)
        self.assertNotEqual(result_paths[0], result_paths[1])


class TestJDTracker(unittest.TestCase):

    def setUp(self):
        self.tmp_dir = os.path.join(os.path.dirname(__file__), "_tmp_tracker")
        os.makedirs(self.tmp_dir, exist_ok=True)
        self.csv_path = os.path.join(self.tmp_dir, "tracker.csv")

    def tearDown(self):
        for name in os.listdir(self.tmp_dir):
            os.remove(os.path.join(self.tmp_dir, name))
        os.rmdir(self.tmp_dir)

    def test_unknown_job_key_is_not_completed(self):
        tracker = jd_manager.JDTracker(self.csv_path)
        self.assertFalse(tracker.is_completed("nope"))

    def test_mark_completed_then_is_completed(self):
        tracker = jd_manager.JDTracker(self.csv_path)
        tracker.mark_completed(
            "abc123",
            job_title="Engineer",
            company_name="Acme",
            source_file="abc.json",
            output_json="output/json/abc.json",
            output_pdf="output/pdf/abc.pdf",
        )
        self.assertTrue(tracker.is_completed("abc123"))

    def test_mark_failed_does_not_count_as_completed(self):
        tracker = jd_manager.JDTracker(self.csv_path)
        tracker.mark_failed(
            "abc123",
            job_title="Engineer",
            company_name="Acme",
            source_file="abc.json",
            error_message="builder returned empty",
        )
        self.assertFalse(tracker.is_completed("abc123"))

    def test_failed_then_completed_counts_as_completed(self):
        tracker = jd_manager.JDTracker(self.csv_path)
        tracker.mark_failed("abc123", error_message="transient error")
        tracker.mark_completed("abc123", job_title="Engineer")
        self.assertTrue(tracker.is_completed("abc123"))

    def test_rows_persist_across_tracker_instances(self):
        jd_manager.JDTracker(self.csv_path).mark_completed("xyz")
        second_tracker = jd_manager.JDTracker(self.csv_path)
        self.assertTrue(second_tracker.is_completed("xyz"))

    def test_count_completed_on_missing_ledger_is_zero(self):
        self.assertEqual(jd_manager.JDTracker(self.csv_path).count_completed(), 0)

    def test_count_completed_ignores_failed_rows(self):
        tracker = jd_manager.JDTracker(self.csv_path)
        tracker.mark_completed("a")
        tracker.mark_failed("b", error_message="boom")
        tracker.mark_completed("c")
        self.assertEqual(tracker.count_completed(), 2)

    def test_count_completed_counts_rebuilds_of_the_same_job(self):
        """B61: the banner's "All-Time" figure counts resumes produced, and
        rebuilding a role really does produce another resume. Distinct from
        is_completed(), which is a per-job_key question."""
        tracker = jd_manager.JDTracker(self.csv_path)
        tracker.mark_completed("same-job")
        tracker.mark_completed("same-job")
        self.assertEqual(tracker.count_completed(), 2)

    def test_count_completed_never_decreases(self):
        """B61's actual defect: the count used to come from COMPLETED_DIR's file
        count, so archive_jd() -- which moves files *out* of that directory --
        silently decremented an all-time total. A ledger row can't be moved."""
        tracker = jd_manager.JDTracker(self.csv_path)
        tracker.mark_completed("a")
        tracker.mark_completed("b")
        before = tracker.count_completed()
        tracker.mark_failed("c", error_message="later failure")
        self.assertGreaterEqual(tracker.count_completed(), before)


class TestCheckpoints(unittest.TestCase):

    def setUp(self):
        self._real_dir = jd_manager.CHECKPOINTS_DIR
        self.tmp_dir = os.path.join(os.path.dirname(__file__), "_tmp_checkpoints")
        jd_manager.CHECKPOINTS_DIR = self.tmp_dir

    def tearDown(self):
        jd_manager.CHECKPOINTS_DIR = self._real_dir
        if os.path.isdir(self.tmp_dir):
            for name in os.listdir(self.tmp_dir):
                os.remove(os.path.join(self.tmp_dir, name))
            os.rmdir(self.tmp_dir)

    def test_load_checkpoint_missing_returns_empty_dict(self):
        self.assertEqual(jd_manager.load_checkpoint("nope"), {})

    def test_save_then_load_roundtrip(self):
        jd_manager.save_checkpoint("job1", {"jd_keywords": {"skills": ["python"]}})
        self.assertEqual(
            jd_manager.load_checkpoint("job1"), {"jd_keywords": {"skills": ["python"]}}
        )

    def test_save_overwrites_previous_checkpoint(self):
        jd_manager.save_checkpoint("job1", {"jd_keywords": {}})
        jd_manager.save_checkpoint(
            "job1", {"jd_keywords": {}, "bullet_tuples": [["a", "b", "c"]]}
        )
        self.assertIn("bullet_tuples", jd_manager.load_checkpoint("job1"))

    def test_delete_checkpoint_removes_file(self):
        jd_manager.save_checkpoint("job1", {"jd_keywords": {}})
        jd_manager.delete_checkpoint("job1")
        self.assertEqual(jd_manager.load_checkpoint("job1"), {})

    def test_delete_checkpoint_missing_is_a_no_op(self):
        jd_manager.delete_checkpoint("never-existed")  # must not raise

    def test_checkpoint_path_sanitizes_unsafe_job_key(self):
        unsafe_key = "../../evil"
        jd_manager.save_checkpoint(unsafe_key, {"jd_keywords": {}})
        saved_path = jd_manager._checkpoint_path(unsafe_key)
        self.assertEqual(
            os.path.commonpath(
                [os.path.abspath(saved_path), os.path.abspath(self.tmp_dir)]
            ),
            os.path.abspath(self.tmp_dir),
        )
        self.assertEqual(jd_manager.load_checkpoint(unsafe_key), {"jd_keywords": {}})
        jd_manager.delete_checkpoint(unsafe_key)
        self.assertEqual(jd_manager.load_checkpoint(unsafe_key), {})

    def test_save_checkpoint_leaves_previous_content_intact_on_failure(self):
        # atomic_write() writes to a sibling temp file first, so a failure
        # mid-serialization (an unencodable value here) must never truncate
        # the checkpoint that was already on disk.
        jd_manager.save_checkpoint("job1", {"jd_keywords": {"skills": ["python"]}})
        with self.assertRaises(TypeError):
            jd_manager.save_checkpoint("job1", {"bad": object()})
        self.assertEqual(
            jd_manager.load_checkpoint("job1"), {"jd_keywords": {"skills": ["python"]}}
        )
        # No leftover temp file in the checkpoints dir either.
        leftovers = [n for n in os.listdir(self.tmp_dir) if n.endswith(".tmp")]
        self.assertEqual(leftovers, [])

    def test_load_checkpoint_logs_and_falls_back_on_corrupt_json(self):
        path = jd_manager._checkpoint_path("job1")
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            f.write("{not valid json")

        with self.assertLogs(level="ERROR") as logs:
            result = jd_manager.load_checkpoint("job1")

        self.assertEqual(result, {})
        self.assertTrue(
            any("Corrupt checkpoint" in msg and path in msg for msg in logs.output)
        )


class TestGetPendingJds(unittest.TestCase):

    def setUp(self):
        self.tmp_dir = os.path.join(os.path.dirname(__file__), "_tmp_pending")
        os.makedirs(self.tmp_dir, exist_ok=True)
        os.makedirs(os.path.join(self.tmp_dir, "completed"), exist_ok=True)
        self._real_jds_dir = jd_manager.JDS_DIR
        self._real_completed_dir = jd_manager.COMPLETED_DIR
        # JDTracker resolves its path per instance now, so patching the
        # module constant alone no longer redirects it.
        self._tracker_patch = patch.object(
            jd_manager.profile_paths,
            "tracker_csv_path",
            return_value=os.path.join(self.tmp_dir, "tracker.csv"),
        )
        self._tracker_patch.start()
        self.addCleanup(self._tracker_patch.stop)
        self._real_tracker_csv = jd_manager.TRACKER_CSV
        jd_manager.JDS_DIR = self.tmp_dir
        jd_manager.COMPLETED_DIR = os.path.join(self.tmp_dir, "completed")
        jd_manager.TRACKER_CSV = os.path.join(self.tmp_dir, "tracker.csv")

    def tearDown(self):
        jd_manager.JDS_DIR = self._real_jds_dir
        jd_manager.COMPLETED_DIR = self._real_completed_dir
        jd_manager.TRACKER_CSV = self._real_tracker_csv
        for root, dirs, files in os.walk(self.tmp_dir, topdown=False):
            for name in files:
                os.remove(os.path.join(root, name))
            for name in dirs:
                os.rmdir(os.path.join(root, name))
        os.rmdir(self.tmp_dir)

    def _write(self, name, content):
        path = os.path.join(self.tmp_dir, name)
        with open(path, "w", encoding="utf-8") as f:
            f.write(content)
        return path

    def test_returns_new_plain_text_jd(self):
        self._write("posting.txt", "A plain-text JD.")
        pending = jd_manager.get_pending_jds()
        self.assertEqual(len(pending), 1)

    def test_survives_a_file_vanishing_between_listing_and_opening(self):
        """A concurrent process (batch evaluate archiving a Skip
        recommendation, liveness moving an expired posting, etc.) can
        remove a file between the directory listing and compute_job_key()
        opening it -- this must skip that one file, not crash the whole
        get_pending_jds() call. Observed for real during this session: a
        concurrent `resume evaluate --refresh` run crashed doctor.py's
        banner this exact way."""
        self._write("stays.txt", "A plain-text JD that stays put.")
        vanishing_path = self._write(
            "vanishes.txt", "A plain-text JD that disappears mid-scan."
        )

        real_compute_job_key = jd_manager.compute_job_key

        def flaky_compute_job_key(path):
            if path == vanishing_path:
                os.remove(path)
            return real_compute_job_key(path)

        with patch("jd_manager.compute_job_key", side_effect=flaky_compute_job_key):
            pending = jd_manager.get_pending_jds()

        self.assertEqual([os.path.basename(p) for p in pending], ["stays.txt"])

    def test_ignores_an_archived_tracker_log(self):
        """reset_resume_counter.py archives the tracker by RENAMING it in
        place to "<tracker>.archived-<stamp>", in the same directory
        get_pending_jds() scans. An exact-name exclusion missed that, so
        28 KB of real tracker history sat in the pending list queued to be
        sent to Gemini as if it were a job description."""
        self._write("tracker.csv", "job_key,status\n")
        self._write("tracker.csv.archived-20260820-154754", "job_key,status\n")
        self._write("posting.txt", "A plain-text JD.")

        pending = jd_manager.get_pending_jds()

        self.assertEqual([os.path.basename(p) for p in pending], ["posting.txt"])

    def test_ignores_hidden_files_like_ds_store(self):
        # Real .DS_Store files are binary and not valid UTF-8 -- writing one
        # with invalid bytes here reproduces the actual crash this guards
        # against (get_pending_jds used to try to read it as a JD).
        with open(os.path.join(self.tmp_dir, ".DS_Store"), "wb") as f:
            f.write(b"\x00\x00\x00\x01Bud1\x86not valid utf-8")
        self._write("posting.txt", "A plain-text JD.")
        pending = jd_manager.get_pending_jds()
        self.assertEqual(len(pending), 1)
        self.assertTrue(pending[0].endswith("posting.txt"))

    def test_splits_batch_file_and_returns_both_jobs(self):
        self._write(
            "batch.json",
            json.dumps(
                [
                    {"job_title": "A", "company_name": "X"},
                    {"job_title": "B", "company_name": "Y"},
                ]
            ),
        )
        pending = jd_manager.get_pending_jds()
        self.assertEqual(len(pending), 2)

    def test_already_completed_job_is_excluded(self):
        path = self._write(
            "posting.json", json.dumps({"source_job_id": "done-1", "job_title": "A"})
        )
        jd_manager.JDTracker().mark_completed("done-1")
        pending = jd_manager.get_pending_jds()
        self.assertEqual(pending, [])

    def test_files_in_completed_subfolder_are_ignored(self):
        completed_path = os.path.join(self.tmp_dir, "completed", "old.txt")
        with open(completed_path, "w", encoding="utf-8") as f:
            f.write("already done")
        pending = jd_manager.get_pending_jds()
        self.assertEqual(pending, [])


class TestGetCompletedJds(unittest.TestCase):

    def setUp(self):
        self.tmp_dir = os.path.join(os.path.dirname(__file__), "_tmp_completed")
        os.makedirs(self.tmp_dir, exist_ok=True)
        os.makedirs(os.path.join(self.tmp_dir, "completed"), exist_ok=True)
        self._real_jds_dir = jd_manager.JDS_DIR
        self._real_completed_dir = jd_manager.COMPLETED_DIR
        # JDTracker resolves its path per instance now, so patching the
        # module constant alone no longer redirects it.
        self._tracker_patch = patch.object(
            jd_manager.profile_paths,
            "tracker_csv_path",
            return_value=os.path.join(self.tmp_dir, "tracker.csv"),
        )
        self._tracker_patch.start()
        self.addCleanup(self._tracker_patch.stop)
        self._real_tracker_csv = jd_manager.TRACKER_CSV
        jd_manager.JDS_DIR = self.tmp_dir
        jd_manager.COMPLETED_DIR = os.path.join(self.tmp_dir, "completed")
        jd_manager.TRACKER_CSV = os.path.join(self.tmp_dir, "tracker.csv")

    def tearDown(self):
        jd_manager.JDS_DIR = self._real_jds_dir
        jd_manager.COMPLETED_DIR = self._real_completed_dir
        jd_manager.TRACKER_CSV = self._real_tracker_csv
        for root, dirs, files in os.walk(self.tmp_dir, topdown=False):
            for name in files:
                os.remove(os.path.join(root, name))
            for name in dirs:
                os.rmdir(os.path.join(root, name))
        os.rmdir(self.tmp_dir)

    def _write_completed(self, name, content):
        path = os.path.join(jd_manager.COMPLETED_DIR, name)
        with open(path, "w", encoding="utf-8") as f:
            f.write(content)
        return path

    def test_returns_files_in_completed_dir(self):
        self._write_completed(
            "done.json", json.dumps({"job_title": "A", "company_name": "X"})
        )
        completed = jd_manager.get_completed_jds()
        self.assertEqual(len(completed), 1)
        self.assertTrue(completed[0].endswith("done.json"))

    def test_ignores_hidden_files(self):
        with open(os.path.join(jd_manager.COMPLETED_DIR, ".DS_Store"), "wb") as f:
            f.write(b"\x00\x00\x00\x01Bud1\x86not valid utf-8")
        self._write_completed("done.json", json.dumps({"job_title": "A"}))
        completed = jd_manager.get_completed_jds()
        self.assertEqual(len(completed), 1)
        self.assertTrue(completed[0].endswith("done.json"))

    def test_empty_when_nothing_completed(self):
        self.assertEqual(jd_manager.get_completed_jds(), [])

    def test_pending_jds_are_not_included(self):
        with open(
            os.path.join(self.tmp_dir, "still_pending.json"), "w", encoding="utf-8"
        ) as f:
            f.write(json.dumps({"job_title": "A"}))
        self._write_completed("done.json", json.dumps({"job_title": "B"}))
        completed = jd_manager.get_completed_jds()
        self.assertEqual(len(completed), 1)
        self.assertTrue(completed[0].endswith("done.json"))


class TestJobKeyKnown(unittest.TestCase):

    def setUp(self):
        self.tmp_dir = os.path.join(os.path.dirname(__file__), "_tmp_job_key_known")
        os.makedirs(self.tmp_dir, exist_ok=True)
        os.makedirs(os.path.join(self.tmp_dir, "completed"), exist_ok=True)
        os.makedirs(os.path.join(self.tmp_dir, "archived"), exist_ok=True)
        os.makedirs(os.path.join(self.tmp_dir, "expired"), exist_ok=True)
        self._real_jds_dir = jd_manager.JDS_DIR
        self._real_completed_dir = jd_manager.COMPLETED_DIR
        self._real_archived_dir = jd_manager.ARCHIVED_DIR
        self._real_expired_dir = jd_manager.EXPIRED_DIR
        # JDTracker resolves its path per instance now, so patching the
        # module constant alone no longer redirects it.
        self._tracker_patch = patch.object(
            jd_manager.profile_paths,
            "tracker_csv_path",
            return_value=os.path.join(self.tmp_dir, "tracker.csv"),
        )
        self._tracker_patch.start()
        self.addCleanup(self._tracker_patch.stop)
        self._real_tracker_csv = jd_manager.TRACKER_CSV
        jd_manager.JDS_DIR = self.tmp_dir
        jd_manager.COMPLETED_DIR = os.path.join(self.tmp_dir, "completed")
        jd_manager.ARCHIVED_DIR = os.path.join(self.tmp_dir, "archived")
        jd_manager.EXPIRED_DIR = os.path.join(self.tmp_dir, "expired")
        jd_manager.TRACKER_CSV = os.path.join(self.tmp_dir, "tracker.csv")

    def tearDown(self):
        jd_manager.JDS_DIR = self._real_jds_dir
        jd_manager.COMPLETED_DIR = self._real_completed_dir
        jd_manager.ARCHIVED_DIR = self._real_archived_dir
        jd_manager.EXPIRED_DIR = self._real_expired_dir
        jd_manager.TRACKER_CSV = self._real_tracker_csv
        for root, dirs, files in os.walk(self.tmp_dir, topdown=False):
            for name in files:
                os.remove(os.path.join(root, name))
            for name in dirs:
                os.rmdir(os.path.join(root, name))
        os.rmdir(self.tmp_dir)

    def _write_pending(self, name, data):
        path = os.path.join(self.tmp_dir, name)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f)
        return path

    def test_true_when_already_completed_in_tracker(self):
        jd_manager.JDTracker().mark_completed("abc123")
        self.assertTrue(jd_manager.job_key_known("abc123"))

    def test_true_when_matching_job_key_file_exists_pending(self):
        self._write_pending(
            "a.json", {"source_job_id": "abc123", "company_name": "Acme"}
        )
        self.assertTrue(jd_manager.job_key_known("abc123"))

    def test_false_when_nothing_matches(self):
        self._write_pending(
            "a.json", {"source_job_id": "other", "company_name": "Acme"}
        )
        self.assertFalse(jd_manager.job_key_known("abc123"))

    def test_true_for_same_source_url_and_company_name_despite_different_job_key(self):
        self._write_pending(
            "a.json",
            {
                "source_job_id": "existing-id",
                "company_name": "Abnormal AI",
                "source_url": "https://boards.greenhouse.io/embed/job_app?token=123",
            },
        )
        result = jd_manager.job_key_known(
            "new-different-id",
            source_url="https://boards.greenhouse.io/embed/job_app?token=123",
            company_name="Abnormal AI",
        )
        self.assertTrue(result)

    def test_false_for_same_source_url_but_different_company_name(self):
        # Sibling brands can share application infrastructure (e.g. the
        # same Workday tenant) without being the same posting.
        self._write_pending(
            "a.json",
            {
                "source_job_id": "existing-id",
                "company_name": "Cambium Assessment",
                "source_url": "https://cambiumlearning.wd1.myworkdayjobs.com/camb/job/REQ-1",
            },
        )
        result = jd_manager.job_key_known(
            "new-different-id",
            source_url="https://cambiumlearning.wd1.myworkdayjobs.com/camb/job/REQ-1",
            company_name="Lexia Learning",
        )
        self.assertFalse(result)

    def test_source_url_check_skipped_when_not_provided(self):
        self._write_pending(
            "a.json",
            {
                "source_job_id": "existing-id",
                "company_name": "Acme",
                "source_url": "https://example.com/job/1",
            },
        )
        result = jd_manager.job_key_known("new-different-id")
        self.assertFalse(result)

    def test_true_for_same_company_and_title_despite_completely_different_source(self):
        # The same real job cross-posted on two different platforms (e.g.
        # JobRight's aggregated ATS URL vs. a separate LinkedIn scrape) has
        # no source_job_id or source_url in common at all.
        self._write_pending(
            "a.json",
            {
                "source_job_id": "gem-abc123",
                "company_name": "Function Health",
                "job_title": "Lifecycle Coordinator -- Acquisition",
                "source_url": "https://jobs.gem.com/function-health/xyz",
            },
        )
        result = jd_manager.job_key_known(
            "linkedin-4408958099",
            source_url="https://www.linkedin.com/jobs/view/4408958099/",
            company_name="Function Health",
            job_title="Lifecycle Coordinator -- Acquisition",
        )
        self.assertTrue(result)

    def test_true_for_same_company_and_title_despite_case_and_punctuation_differences(
        self,
    ):
        self._write_pending(
            "a.json",
            {
                "source_job_id": "existing-id",
                "company_name": "function health",
                "job_title": "Lifecycle Coordinator, Acquisition!",
            },
        )
        result = jd_manager.job_key_known(
            "new-id",
            company_name="FUNCTION HEALTH",
            job_title="lifecycle coordinator acquisition",
        )
        self.assertTrue(result)

    def test_false_for_same_company_but_different_title(self):
        self._write_pending(
            "a.json",
            {
                "source_job_id": "existing-id",
                "company_name": "Acme",
                "job_title": "Content Marketing Manager",
            },
        )
        result = jd_manager.job_key_known(
            "new-id",
            company_name="Acme",
            job_title="Content Marketing Specialist",
        )
        self.assertFalse(result)

    def test_false_for_same_title_but_different_company(self):
        self._write_pending(
            "a.json",
            {
                "source_job_id": "existing-id",
                "company_name": "Acme",
                "job_title": "Content Marketing Manager",
            },
        )
        result = jd_manager.job_key_known(
            "new-id",
            company_name="Widgets Inc",
            job_title="Content Marketing Manager",
        )
        self.assertFalse(result)

    def test_company_and_title_check_skipped_when_not_provided(self):
        self._write_pending(
            "a.json",
            {
                "source_job_id": "existing-id",
                "company_name": "Acme",
                "job_title": "Content Marketing Manager",
            },
        )
        result = jd_manager.job_key_known("new-different-id")
        self.assertFalse(result)

    def test_true_for_a_job_key_match_in_archived_dir(self):
        # Skip-evaluated JDs get auto-archived -- must not be silently
        # rediscovered as "new" on the next scan.
        path = os.path.join(jd_manager.ARCHIVED_DIR, "a.json")
        with open(path, "w", encoding="utf-8") as f:
            json.dump({"source_job_id": "abc123", "company_name": "Acme"}, f)
        self.assertTrue(jd_manager.job_key_known("abc123"))

    def test_true_for_a_job_key_match_in_expired_dir(self):
        path = os.path.join(jd_manager.EXPIRED_DIR, "a.json")
        with open(path, "w", encoding="utf-8") as f:
            json.dump({"source_job_id": "abc123", "company_name": "Acme"}, f)
        self.assertTrue(jd_manager.job_key_known("abc123"))

    def test_true_for_source_url_and_company_match_in_archived_dir(self):
        path = os.path.join(jd_manager.ARCHIVED_DIR, "a.json")
        with open(path, "w", encoding="utf-8") as f:
            json.dump(
                {
                    "source_job_id": "existing-id",
                    "company_name": "Acme",
                    "source_url": "https://x.com/1",
                },
                f,
            )
        result = jd_manager.job_key_known(
            "new-id", source_url="https://x.com/1", company_name="Acme"
        )
        self.assertTrue(result)


class TestSaveAndReadEvaluation(unittest.TestCase):

    def setUp(self):
        self.tmp_dir = os.path.join(os.path.dirname(__file__), "_tmp_evaluation")
        os.makedirs(self.tmp_dir, exist_ok=True)

    def tearDown(self):
        for name in os.listdir(self.tmp_dir):
            os.remove(os.path.join(self.tmp_dir, name))
        os.rmdir(self.tmp_dir)

    def _write(self, name, content):
        path = os.path.join(self.tmp_dir, name)
        with open(path, "w", encoding="utf-8") as f:
            f.write(content)
        return path

    def test_save_then_read_round_trips_score_and_recommendation(self):
        path = self._write(
            "a.json", json.dumps({"job_title": "Role", "company_name": "Acme"})
        )
        jd_manager.save_evaluation(
            path,
            {
                "composite_score": 4.2,
                "recommendation": "Strong pursue",
                "hard_blockers": [],
            },
        )
        result = jd_manager.read_evaluation(path)
        self.assertEqual(result["composite_score"], 4.2)
        self.assertEqual(result["recommendation"], "Strong pursue")
        self.assertIn("evaluated_at", result)

    def test_save_preserves_the_rest_of_the_jd_content(self):
        path = self._write(
            "a.json", json.dumps({"job_title": "Role", "company_name": "Acme"})
        )
        jd_manager.save_evaluation(
            path, {"composite_score": 3.0, "recommendation": "Selective pursue"}
        )
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        self.assertEqual(data["job_title"], "Role")
        self.assertEqual(data["company_name"], "Acme")

    def test_save_on_plain_text_jd_does_not_raise_and_leaves_file_unchanged(self):
        path = self._write("dummy.txt", "Just a plain text job posting, not JSON.")
        jd_manager.save_evaluation(
            path, {"composite_score": 4.0, "recommendation": "Strong pursue"}
        )
        with open(path, "r", encoding="utf-8") as f:
            content = f.read()
        self.assertEqual(content, "Just a plain text job posting, not JSON.")

    def test_read_evaluation_returns_none_when_never_evaluated(self):
        path = self._write("a.json", json.dumps({"job_title": "Role"}))
        self.assertIsNone(jd_manager.read_evaluation(path))

    def test_save_then_read_round_trips_why(self):
        # Regression test: `why` (evaluate_fit()'s plain-language rationale)
        # used to be computed and immediately discarded -- never reaching
        # disk, so there was no way to see why a role scored the way it did
        # without re-running the evaluation.
        path = self._write(
            "a.json", json.dumps({"job_title": "Role", "company_name": "Acme"})
        )
        jd_manager.save_evaluation(
            path,
            {
                "composite_score": 4.2,
                "recommendation": "Strong pursue",
                "why": "Strong tools match, but the role skews more senior than usual.",
            },
        )
        result = jd_manager.read_evaluation(path)
        self.assertEqual(
            result["why"],
            "Strong tools match, but the role skews more senior than usual.",
        )

    def test_missing_why_persists_as_empty_string_not_missing_key(self):
        path = self._write("a.json", json.dumps({"job_title": "Role"}))
        jd_manager.save_evaluation(
            path, {"composite_score": 3.0, "recommendation": "Selective pursue"}
        )
        result = jd_manager.read_evaluation(path)
        self.assertEqual(result["why"], "")

    def test_read_evaluation_returns_none_for_plain_text_jd(self):
        path = self._write("dummy.txt", "Just plain text.")
        self.assertIsNone(jd_manager.read_evaluation(path))

    def test_save_then_read_round_trips_archetype_and_subscores(self):
        # Regression test: subscores/archetype used to be computed
        # and immediately discarded, same as `why` used to be -- needed
        # for the "List Jobs" browse view's per-JD drill-in detail.
        path = self._write("a.json", json.dumps({"job_title": "Role"}))
        jd_manager.save_evaluation(
            path,
            {
                "composite_score": 4.2,
                "recommendation": "Strong pursue",
                "archetype": "Lifecycle Marketing Manager",
                "fit_subscores": {"functional_alignment": 5, "north_star_alignment": 4},
                "interview_odds_subscores": {"title_continuity": 4},
                "practical_pursue_subscores": {"remote_quality": 4},
            },
        )
        result = jd_manager.read_evaluation(path)
        self.assertEqual(result["archetype"], "Lifecycle Marketing Manager")
        self.assertEqual(
            result["fit_subscores"],
            {"functional_alignment": 5, "north_star_alignment": 4},
        )
        self.assertEqual(result["interview_odds_subscores"], {"title_continuity": 4})
        self.assertEqual(result["practical_pursue_subscores"], {"remote_quality": 4})

    def test_missing_archetype_and_subscores_persist_as_empty(self):
        path = self._write("a.json", json.dumps({"job_title": "Role"}))
        jd_manager.save_evaluation(
            path, {"composite_score": 3.0, "recommendation": "Selective pursue"}
        )
        result = jd_manager.read_evaluation(path)
        self.assertEqual(result["archetype"], "")
        self.assertEqual(result["fit_subscores"], {})
        self.assertEqual(result["interview_odds_subscores"], {})
        self.assertEqual(result["practical_pursue_subscores"], {})


class TestArchiveJd(unittest.TestCase):

    def setUp(self):
        self.tmp_dir = os.path.join(os.path.dirname(__file__), "_tmp_archive_jd")
        os.makedirs(self.tmp_dir, exist_ok=True)
        self._real_jds_dir = jd_manager.JDS_DIR
        self._real_archived_dir = jd_manager.ARCHIVED_DIR
        jd_manager.JDS_DIR = self.tmp_dir
        jd_manager.ARCHIVED_DIR = os.path.join(self.tmp_dir, "archived")

    def tearDown(self):
        jd_manager.JDS_DIR = self._real_jds_dir
        jd_manager.ARCHIVED_DIR = self._real_archived_dir
        for root, dirs, files in os.walk(self.tmp_dir, topdown=False):
            for name in files:
                os.remove(os.path.join(root, name))
            for name in dirs:
                os.rmdir(os.path.join(root, name))
        if os.path.exists(self.tmp_dir):
            os.rmdir(self.tmp_dir)

    def test_moves_file_into_archived_dir(self):
        src = os.path.join(self.tmp_dir, "a.json")
        with open(src, "w", encoding="utf-8") as f:
            json.dump({"job_title": "Role"}, f)

        dest = jd_manager.archive_jd(src)

        self.assertFalse(os.path.exists(src))
        self.assertTrue(os.path.exists(dest))
        self.assertEqual(os.path.dirname(dest), jd_manager.ARCHIVED_DIR)

    def test_preserves_file_content(self):
        src = os.path.join(self.tmp_dir, "a.json")
        with open(src, "w", encoding="utf-8") as f:
            json.dump({"job_title": "Role", "company_name": "Acme"}, f)

        dest = jd_manager.archive_jd(src)

        with open(dest, "r", encoding="utf-8") as f:
            data = json.load(f)
        self.assertEqual(data["company_name"], "Acme")


class TestSaveAndReadLiveness(unittest.TestCase):

    def setUp(self):
        self.tmp_dir = os.path.join(os.path.dirname(__file__), "_tmp_liveness_persist")
        os.makedirs(self.tmp_dir, exist_ok=True)

    def tearDown(self):
        for name in os.listdir(self.tmp_dir):
            os.remove(os.path.join(self.tmp_dir, name))
        os.rmdir(self.tmp_dir)

    def _write(self, name, content):
        path = os.path.join(self.tmp_dir, name)
        with open(path, "w", encoding="utf-8") as f:
            f.write(content)
        return path

    def test_save_then_read_round_trips_result_reason_and_checked_at(self):
        path = self._write(
            "a.json", json.dumps({"job_title": "Role", "source_url": "https://x"})
        )
        jd_manager.save_liveness(path, "active", "apply button found")
        result = jd_manager.read_liveness(path)
        self.assertEqual(result["result"], "active")
        self.assertEqual(result["reason"], "apply button found")
        self.assertIn("checked_at", result)

    def test_save_preserves_the_rest_of_the_jd_content(self):
        path = self._write(
            "a.json", json.dumps({"job_title": "Role", "company_name": "Acme"})
        )
        jd_manager.save_liveness(path, "expired", "404")
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        self.assertEqual(data["job_title"], "Role")
        self.assertEqual(data["company_name"], "Acme")

    def test_read_liveness_returns_none_when_never_checked(self):
        path = self._write("a.json", json.dumps({"job_title": "Role"}))
        self.assertIsNone(jd_manager.read_liveness(path))

    def test_save_on_plain_text_jd_does_not_raise_and_leaves_file_unchanged(self):
        path = self._write("dummy.txt", "Just a plain text job posting, not JSON.")
        jd_manager.save_liveness(path, "active", "n/a")
        with open(path, "r", encoding="utf-8") as f:
            content = f.read()
        self.assertEqual(content, "Just a plain text job posting, not JSON.")


class TestSaveAndReadReferral(unittest.TestCase):

    def setUp(self):
        self.tmp_dir = os.path.join(os.path.dirname(__file__), "_tmp_referral_persist")
        os.makedirs(self.tmp_dir, exist_ok=True)

    def tearDown(self):
        for name in os.listdir(self.tmp_dir):
            os.remove(os.path.join(self.tmp_dir, name))
        os.rmdir(self.tmp_dir)

    def _write(self, name, content):
        path = os.path.join(self.tmp_dir, name)
        with open(path, "w", encoding="utf-8") as f:
            f.write(content)
        return path

    def test_save_then_read_round_trips_text_and_saved_at(self):
        path = self._write(
            "a.json", json.dumps({"job_title": "Role", "source_url": "https://x"})
        )
        jd_manager.save_referral(path, "Jane Doe, former coworker")
        result = jd_manager.read_referral(path)
        self.assertEqual(result["text"], "Jane Doe, former coworker")
        self.assertIn("saved_at", result)

    def test_save_preserves_the_rest_of_the_jd_content(self):
        path = self._write(
            "a.json", json.dumps({"job_title": "Role", "company_name": "Acme"})
        )
        jd_manager.save_referral(path, "Jane Doe")
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        self.assertEqual(data["job_title"], "Role")
        self.assertEqual(data["company_name"], "Acme")

    def test_read_referral_returns_none_when_never_saved(self):
        path = self._write("a.json", json.dumps({"job_title": "Role"}))
        self.assertIsNone(jd_manager.read_referral(path))

    def test_save_on_plain_text_jd_does_not_raise_and_leaves_file_unchanged(self):
        path = self._write("dummy.txt", "Just a plain text job posting, not JSON.")
        jd_manager.save_referral(path, "Jane Doe")
        with open(path, "r", encoding="utf-8") as f:
            content = f.read()
        self.assertEqual(content, "Just a plain text job posting, not JSON.")


class TestSaveAndReadAtsClassification(unittest.TestCase):

    def setUp(self):
        self.tmp_dir = os.path.join(
            os.path.dirname(__file__), "_tmp_ats_classification_persist"
        )
        os.makedirs(self.tmp_dir, exist_ok=True)

    def tearDown(self):
        for name in os.listdir(self.tmp_dir):
            os.remove(os.path.join(self.tmp_dir, name))
        os.rmdir(self.tmp_dir)

    def _write(self, name, content):
        path = os.path.join(self.tmp_dir, name)
        with open(path, "w", encoding="utf-8") as f:
            f.write(content)
        return path

    def test_save_then_read_round_trips_provider_and_tier(self):
        path = self._write("a.json", json.dumps({"job_title": "Role"}))
        jd_manager.save_ats_classification(
            path, {"provider_id": "workday", "weight_tier": "enterprise_high"}
        )
        result = jd_manager.read_ats_classification(path)
        self.assertEqual(result["provider_id"], "workday")
        self.assertEqual(result["weight_tier"], "enterprise_high")
        self.assertIn("classified_at", result)

    def test_save_preserves_the_rest_of_the_jd_content(self):
        path = self._write(
            "a.json", json.dumps({"job_title": "Role", "company_name": "Acme"})
        )
        jd_manager.save_ats_classification(
            path, {"provider_id": "greenhouse", "weight_tier": "startup_zero"}
        )
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        self.assertEqual(data["job_title"], "Role")
        self.assertEqual(data["company_name"], "Acme")

    def test_read_ats_classification_returns_none_when_never_saved(self):
        path = self._write("a.json", json.dumps({"job_title": "Role"}))
        self.assertIsNone(jd_manager.read_ats_classification(path))

    def test_save_on_plain_text_jd_does_not_raise_and_leaves_file_unchanged(self):
        path = self._write("dummy.txt", "Just a plain text job posting, not JSON.")
        jd_manager.save_ats_classification(
            path, {"provider_id": "workday", "weight_tier": "enterprise_high"}
        )
        with open(path, "r", encoding="utf-8") as f:
            content = f.read()
        self.assertEqual(content, "Just a plain text job posting, not JSON.")


class TestComputePostingAgeDays(unittest.TestCase):

    def setUp(self):
        self.tmp_dir = os.path.join(os.path.dirname(__file__), "_tmp_posting_age")
        os.makedirs(self.tmp_dir, exist_ok=True)

    def tearDown(self):
        for name in os.listdir(self.tmp_dir):
            os.remove(os.path.join(self.tmp_dir, name))
        os.rmdir(self.tmp_dir)

    def _write(self, name, data):
        path = os.path.join(self.tmp_dir, name)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f)
        return path

    def test_iso_posted_at_ten_days_ago(self):
        ten_days_ago = (
            datetime.datetime.now() - datetime.timedelta(days=10)
        ).isoformat()
        path = self._write("a.json", {"posted_at": ten_days_ago})
        self.assertEqual(jd_manager.compute_posting_age_days(path), 10)

    def test_unix_ms_publish_time(self):
        ten_days_ago_ms = int(
            (datetime.datetime.now() - datetime.timedelta(days=10)).timestamp() * 1000
        )
        path = self._write("a.json", {"publish_time": ten_days_ago_ms})
        self.assertEqual(jd_manager.compute_posting_age_days(path), 10)

    def test_unix_seconds_publish_time(self):
        ten_days_ago_s = (
            datetime.datetime.now() - datetime.timedelta(days=10)
        ).timestamp()
        path = self._write("a.json", {"publish_time": ten_days_ago_s})
        self.assertEqual(jd_manager.compute_posting_age_days(path), 10)

    def test_falls_back_to_scan_confirmed_liveness_timestamp(self):
        ten_days_ago = (
            datetime.datetime.now() - datetime.timedelta(days=10)
        ).isoformat(timespec="seconds")
        path = self._write(
            "a.json",
            {
                "_liveness": {
                    "result": "active",
                    "reason": "confirmed to exist by scan",
                    "checked_at": ten_days_ago,
                }
            },
        )
        self.assertEqual(jd_manager.compute_posting_age_days(path), 10)

    def test_does_not_use_a_liveness_recheck_that_isnt_the_scan_seed(self):
        # A later liveness recheck's checked_at isn't "when this posting
        # was found" -- only the original scan-time seed counts.
        recent = datetime.datetime.now().isoformat(timespec="seconds")
        path = self._write(
            "a.json",
            {
                "_liveness": {
                    "result": "active",
                    "reason": "visible apply control detected",
                    "checked_at": recent,
                }
            },
        )
        self.assertIsNone(jd_manager.compute_posting_age_days(path))

    def test_no_date_signal_at_all_returns_none(self):
        path = self._write("a.json", {"job_title": "Role"})
        self.assertIsNone(jd_manager.compute_posting_age_days(path))

    def test_unparseable_date_string_returns_none(self):
        path = self._write("a.json", {"posted_at": "not a date"})
        self.assertIsNone(jd_manager.compute_posting_age_days(path))

    def test_missing_file_returns_none(self):
        self.assertIsNone(
            jd_manager.compute_posting_age_days(os.path.join(self.tmp_dir, "nope.json"))
        )


class TestSaveAndReadApplicationStatus(unittest.TestCase):

    def setUp(self):
        self.tmp_dir = os.path.join(
            os.path.dirname(__file__), "_tmp_application_status"
        )
        os.makedirs(self.tmp_dir, exist_ok=True)

    def tearDown(self):
        for name in os.listdir(self.tmp_dir):
            os.remove(os.path.join(self.tmp_dir, name))
        os.rmdir(self.tmp_dir)

    def _write(self, name, content):
        path = os.path.join(self.tmp_dir, name)
        with open(path, "w", encoding="utf-8") as f:
            f.write(content)
        return path

    def test_save_then_read_round_trips_status(self):
        path = self._write("a.json", json.dumps({"job_title": "Role"}))
        jd_manager.save_application_status(path, "Applied")
        result = jd_manager.read_application_status(path)
        self.assertEqual(result["status"], "Applied")
        self.assertIn("applied_at", result)
        self.assertIn("status_changed_at", result)
        self.assertEqual(result["follow_up_count"], 0)

    def test_applied_at_is_set_once_and_not_overwritten_by_later_status_changes(self):
        path = self._write("a.json", json.dumps({"job_title": "Role"}))
        jd_manager.save_application_status(path, "Applied")
        first = jd_manager.read_application_status(path)["applied_at"]

        jd_manager.save_application_status(path, "Responded")
        second = jd_manager.read_application_status(path)

        self.assertEqual(second["applied_at"], first)
        self.assertEqual(second["status"], "Responded")

    def test_log_followup_increments_count_and_stamps_last_followup_at(self):
        path = self._write("a.json", json.dumps({"job_title": "Role"}))
        jd_manager.save_application_status(path, "Applied")
        jd_manager.save_application_status(path, "Applied", log_followup=True)
        result = jd_manager.read_application_status(path)
        self.assertEqual(result["follow_up_count"], 1)
        self.assertIsNotNone(result["last_followup_at"])

        jd_manager.save_application_status(path, "Applied", log_followup=True)
        result = jd_manager.read_application_status(path)
        self.assertEqual(result["follow_up_count"], 2)

    def test_status_change_without_followup_does_not_increment_count(self):
        path = self._write("a.json", json.dumps({"job_title": "Role"}))
        jd_manager.save_application_status(path, "Applied", log_followup=True)
        jd_manager.save_application_status(path, "Responded")
        result = jd_manager.read_application_status(path)
        self.assertEqual(result["follow_up_count"], 1)

    def test_save_preserves_the_rest_of_the_jd_content(self):
        path = self._write(
            "a.json", json.dumps({"job_title": "Role", "company_name": "Acme"})
        )
        jd_manager.save_application_status(path, "Applied")
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        self.assertEqual(data["company_name"], "Acme")

    def test_read_returns_none_when_never_set(self):
        path = self._write("a.json", json.dumps({"job_title": "Role"}))
        self.assertIsNone(jd_manager.read_application_status(path))

    def test_save_on_plain_text_jd_does_not_raise_and_leaves_file_unchanged(self):
        path = self._write("dummy.txt", "Just a plain text job posting, not JSON.")
        jd_manager.save_application_status(path, "Applied")
        with open(path, "r", encoding="utf-8") as f:
            content = f.read()
        self.assertEqual(content, "Just a plain text job posting, not JSON.")


class TestReadJdTextStripsAnyUnderscoreKey(unittest.TestCase):
    """Regression coverage for read_jd_text() generalizing from a
    hardcoded _evaluation-only strip to any underscore-prefixed key --
    added alongside _liveness so a persisted liveness result can never
    leak into a Gemini prompt as job-description content."""

    def setUp(self):
        self.tmp_dir = os.path.join(
            os.path.dirname(__file__), "_tmp_read_jd_text_liveness"
        )
        os.makedirs(self.tmp_dir, exist_ok=True)

    def tearDown(self):
        for name in os.listdir(self.tmp_dir):
            os.remove(os.path.join(self.tmp_dir, name))
        os.rmdir(self.tmp_dir)

    def test_strips_liveness_block_from_prompt_text(self):
        path = os.path.join(self.tmp_dir, "a.json")
        with open(path, "w", encoding="utf-8") as f:
            json.dump(
                {
                    "job_title": "Role",
                    "_liveness": {
                        "result": "active",
                        "reason": "x",
                        "checked_at": "2026-07-21T00:00:00",
                    },
                },
                f,
            )
        text = jd_manager.read_jd_text(path)
        self.assertNotIn("_liveness", text)
        self.assertIn("Role", text)


class TestReadJdText(unittest.TestCase):

    def setUp(self):
        self.tmp_dir = os.path.join(os.path.dirname(__file__), "_tmp_read_jd_text")
        os.makedirs(self.tmp_dir, exist_ok=True)

    def tearDown(self):
        for name in os.listdir(self.tmp_dir):
            os.remove(os.path.join(self.tmp_dir, name))
        os.rmdir(self.tmp_dir)

    def _write(self, name, content):
        path = os.path.join(self.tmp_dir, name)
        with open(path, "w", encoding="utf-8") as f:
            f.write(content)
        return path

    def test_jd_without_evaluation_returns_raw_text_unchanged(self):
        raw = json.dumps({"job_title": "Role", "company_name": "Acme"})
        path = self._write("a.json", raw)
        self.assertEqual(jd_manager.read_jd_text(path), raw)

    def test_jd_with_evaluation_strips_only_that_key(self):
        path = self._write(
            "a.json",
            json.dumps(
                {
                    "job_title": "Role",
                    "company_name": "Acme",
                    "_evaluation": {
                        "composite_score": 4.0,
                        "recommendation": "Strong pursue",
                    },
                }
            ),
        )
        result = jd_manager.read_jd_text(path)
        parsed = json.loads(result)
        self.assertNotIn("_evaluation", parsed)
        self.assertEqual(parsed["job_title"], "Role")
        self.assertEqual(parsed["company_name"], "Acme")

    def test_plain_text_jd_returns_raw_text_unchanged(self):
        path = self._write("dummy.txt", "Just a plain text job posting.")
        self.assertEqual(
            jd_manager.read_jd_text(path), "Just a plain text job posting."
        )

    def test_missing_file_raises_file_not_found_error(self):
        with self.assertRaises(FileNotFoundError):
            jd_manager.read_jd_text(os.path.join(self.tmp_dir, "does_not_exist.json"))


class TestProfileScopedPaths(unittest.TestCase):

    def setUp(self):
        self._orig = os.environ.get("RESUME_PROFILE")
        os.environ["RESUME_PROFILE"] = "morgan"

    def tearDown(self):
        if self._orig is None:
            os.environ.pop("RESUME_PROFILE", None)
        else:
            os.environ["RESUME_PROFILE"] = self._orig

    def test_jds_dir_is_profile_scoped(self):
        import importlib

        importlib.reload(jd_manager)
        self.assertTrue(jd_manager.JDS_DIR.endswith(os.path.join("jds", "morgan")))

    def test_applications_md_is_profile_scoped(self):
        import importlib

        importlib.reload(jd_manager)
        self.assertTrue(
            jd_manager.APPLICATIONS_MD.endswith(
                os.path.join("data", "morgan", "applications.md")
            )
        )

    def test_tracker_csv_is_profile_scoped(self):
        import importlib

        importlib.reload(jd_manager)
        self.assertTrue(
            jd_manager.TRACKER_CSV.endswith(
                os.path.join("jds", "morgan", "jd_tracker_log.csv")
            )
        )


if __name__ == "__main__":
    unittest.main()
