import datetime
import hashlib
import json
import os
import sys
import unittest

SCRIPTS_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts")
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
        path = self._write("job.json", json.dumps({
            "source_job_id": "abc123",
            "job_title": "Engineer",
            "company_name": "Acme",
        }))
        self.assertEqual(jd_manager.compute_job_key(path), "abc123")

    def test_hashes_plain_text_content(self):
        path = self._write("job.txt", "We are hiring a Widget Engineer.")
        expected = hashlib.sha256(b"We are hiring a Widget Engineer.").hexdigest()
        self.assertEqual(jd_manager.compute_job_key(path), expected)

    def test_same_content_same_key(self):
        path_a = self._write("a.txt", "identical posting text")
        path_b = self._write("b.txt", "identical posting text")
        self.assertEqual(jd_manager.compute_job_key(path_a), jd_manager.compute_job_key(path_b))

    def test_different_content_different_key(self):
        path_a = self._write("a.txt", "posting one")
        path_b = self._write("b.txt", "posting two")
        self.assertNotEqual(jd_manager.compute_job_key(path_a), jd_manager.compute_job_key(path_b))

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
        path = self._write("job.json", json.dumps({
            "job_title": "Content Strategist",
            "company_name": "Abnormal AI",
        }))
        self.assertEqual(jd_manager.extract_job_meta(path), ("Content Strategist", "Abnormal AI"))

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
        path = self._write("job.json", json.dumps({"source_url": "https://example.com/job/1"}))
        self.assertEqual(jd_manager.extract_source_url(path), "https://example.com/job/1")

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
        jd_manager.JDS_DIR = self.tmp_dir  # redirect writes into the temp dir for this test

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
        batch_path = self._write("batch.json", json.dumps([
            {"job_title": "Content Strategist", "company_name": "Abnormal AI"},
            {"job_title": "Senior Manager, Lifecycle Marketing", "company_name": "Superhuman"},
        ]))

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
        path = self._write("single.json", json.dumps({"job_title": "Engineer", "company_name": "Acme"}))
        result_paths = jd_manager.split_batch_jds(path)
        self.assertEqual(result_paths, [path])
        self.assertTrue(os.path.exists(path))

    def test_plain_text_passes_through_unchanged(self):
        path = self._write("plain.txt", "Not JSON at all.")
        result_paths = jd_manager.split_batch_jds(path)
        self.assertEqual(result_paths, [path])
        self.assertTrue(os.path.exists(path))

    def test_filename_collision_gets_numeric_suffix(self):
        batch_path = self._write("batch2.json", json.dumps([
            {"job_title": "Engineer", "company_name": "Acme"},
            {"job_title": "Engineer", "company_name": "Acme"},
        ]))
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
        tracker.mark_completed("abc123", job_title="Engineer", company_name="Acme",
                                source_file="abc.json", output_json="output/json/abc.json",
                                output_pdf="output/pdf/abc.pdf")
        self.assertTrue(tracker.is_completed("abc123"))

    def test_mark_failed_does_not_count_as_completed(self):
        tracker = jd_manager.JDTracker(self.csv_path)
        tracker.mark_failed("abc123", job_title="Engineer", company_name="Acme",
                             source_file="abc.json", error_message="builder returned empty")
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
        self.assertEqual(jd_manager.load_checkpoint("job1"), {"jd_keywords": {"skills": ["python"]}})

    def test_save_overwrites_previous_checkpoint(self):
        jd_manager.save_checkpoint("job1", {"jd_keywords": {}})
        jd_manager.save_checkpoint("job1", {"jd_keywords": {}, "bullet_tuples": [["a", "b", "c"]]})
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
            os.path.commonpath([os.path.abspath(saved_path), os.path.abspath(self.tmp_dir)]),
            os.path.abspath(self.tmp_dir),
        )
        self.assertEqual(jd_manager.load_checkpoint(unsafe_key), {"jd_keywords": {}})
        jd_manager.delete_checkpoint(unsafe_key)
        self.assertEqual(jd_manager.load_checkpoint(unsafe_key), {})


class TestGetPendingJds(unittest.TestCase):

    def setUp(self):
        self.tmp_dir = os.path.join(os.path.dirname(__file__), "_tmp_pending")
        os.makedirs(self.tmp_dir, exist_ok=True)
        os.makedirs(os.path.join(self.tmp_dir, "completed"), exist_ok=True)
        self._real_jds_dir = jd_manager.JDS_DIR
        self._real_completed_dir = jd_manager.COMPLETED_DIR
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
        self._write("batch.json", json.dumps([
            {"job_title": "A", "company_name": "X"},
            {"job_title": "B", "company_name": "Y"},
        ]))
        pending = jd_manager.get_pending_jds()
        self.assertEqual(len(pending), 2)

    def test_already_completed_job_is_excluded(self):
        path = self._write("posting.json", json.dumps({"source_job_id": "done-1", "job_title": "A"}))
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
        self._write_completed("done.json", json.dumps({"job_title": "A", "company_name": "X"}))
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
        with open(os.path.join(self.tmp_dir, "still_pending.json"), "w", encoding="utf-8") as f:
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
        self._real_jds_dir = jd_manager.JDS_DIR
        self._real_completed_dir = jd_manager.COMPLETED_DIR
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

    def _write_pending(self, name, data):
        path = os.path.join(self.tmp_dir, name)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f)
        return path

    def test_true_when_already_completed_in_tracker(self):
        jd_manager.JDTracker().mark_completed("abc123")
        self.assertTrue(jd_manager.job_key_known("abc123"))

    def test_true_when_matching_job_key_file_exists_pending(self):
        self._write_pending("a.json", {"source_job_id": "abc123", "company_name": "Acme"})
        self.assertTrue(jd_manager.job_key_known("abc123"))

    def test_false_when_nothing_matches(self):
        self._write_pending("a.json", {"source_job_id": "other", "company_name": "Acme"})
        self.assertFalse(jd_manager.job_key_known("abc123"))

    def test_true_for_same_source_url_and_company_name_despite_different_job_key(self):
        self._write_pending("a.json", {
            "source_job_id": "existing-id", "company_name": "Abnormal AI",
            "source_url": "https://boards.greenhouse.io/embed/job_app?token=123",
        })
        result = jd_manager.job_key_known(
            "new-different-id",
            source_url="https://boards.greenhouse.io/embed/job_app?token=123",
            company_name="Abnormal AI",
        )
        self.assertTrue(result)

    def test_false_for_same_source_url_but_different_company_name(self):
        # Sibling brands can share application infrastructure (e.g. the
        # same Workday tenant) without being the same posting.
        self._write_pending("a.json", {
            "source_job_id": "existing-id", "company_name": "Cambium Assessment",
            "source_url": "https://cambiumlearning.wd1.myworkdayjobs.com/camb/job/REQ-1",
        })
        result = jd_manager.job_key_known(
            "new-different-id",
            source_url="https://cambiumlearning.wd1.myworkdayjobs.com/camb/job/REQ-1",
            company_name="Lexia Learning",
        )
        self.assertFalse(result)

    def test_source_url_check_skipped_when_not_provided(self):
        self._write_pending("a.json", {
            "source_job_id": "existing-id", "company_name": "Acme",
            "source_url": "https://example.com/job/1",
        })
        result = jd_manager.job_key_known("new-different-id")
        self.assertFalse(result)

    def test_true_for_same_company_and_title_despite_completely_different_source(self):
        # The same real job cross-posted on two different platforms (e.g.
        # JobRight's aggregated ATS URL vs. a separate LinkedIn scrape) has
        # no source_job_id or source_url in common at all.
        self._write_pending("a.json", {
            "source_job_id": "gem-abc123", "company_name": "Function Health",
            "job_title": "Lifecycle Coordinator -- Acquisition",
            "source_url": "https://jobs.gem.com/function-health/xyz",
        })
        result = jd_manager.job_key_known(
            "linkedin-4408958099",
            source_url="https://www.linkedin.com/jobs/view/4408958099/",
            company_name="Function Health",
            job_title="Lifecycle Coordinator -- Acquisition",
        )
        self.assertTrue(result)

    def test_true_for_same_company_and_title_despite_case_and_punctuation_differences(self):
        self._write_pending("a.json", {
            "source_job_id": "existing-id", "company_name": "function health",
            "job_title": "Lifecycle Coordinator, Acquisition!",
        })
        result = jd_manager.job_key_known(
            "new-id", company_name="FUNCTION HEALTH", job_title="lifecycle coordinator acquisition",
        )
        self.assertTrue(result)

    def test_false_for_same_company_but_different_title(self):
        self._write_pending("a.json", {
            "source_job_id": "existing-id", "company_name": "Acme",
            "job_title": "Content Marketing Manager",
        })
        result = jd_manager.job_key_known(
            "new-id", company_name="Acme", job_title="Content Marketing Specialist",
        )
        self.assertFalse(result)

    def test_false_for_same_title_but_different_company(self):
        self._write_pending("a.json", {
            "source_job_id": "existing-id", "company_name": "Acme",
            "job_title": "Content Marketing Manager",
        })
        result = jd_manager.job_key_known(
            "new-id", company_name="Widgets Inc", job_title="Content Marketing Manager",
        )
        self.assertFalse(result)

    def test_company_and_title_check_skipped_when_not_provided(self):
        self._write_pending("a.json", {
            "source_job_id": "existing-id", "company_name": "Acme",
            "job_title": "Content Marketing Manager",
        })
        result = jd_manager.job_key_known("new-different-id")
        self.assertFalse(result)


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
        path = self._write("a.json", json.dumps({"job_title": "Role", "company_name": "Acme"}))
        jd_manager.save_evaluation(path, {
            "composite_score": 4.2, "recommendation": "Strong pursue", "hard_blockers": [],
        })
        result = jd_manager.read_evaluation(path)
        self.assertEqual(result["composite_score"], 4.2)
        self.assertEqual(result["recommendation"], "Strong pursue")
        self.assertIn("evaluated_at", result)

    def test_save_preserves_the_rest_of_the_jd_content(self):
        path = self._write("a.json", json.dumps({"job_title": "Role", "company_name": "Acme"}))
        jd_manager.save_evaluation(path, {"composite_score": 3.0, "recommendation": "Selective pursue"})
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        self.assertEqual(data["job_title"], "Role")
        self.assertEqual(data["company_name"], "Acme")

    def test_save_on_plain_text_jd_does_not_raise_and_leaves_file_unchanged(self):
        path = self._write("dummy.txt", "Just a plain text job posting, not JSON.")
        jd_manager.save_evaluation(path, {"composite_score": 4.0, "recommendation": "Strong pursue"})
        with open(path, "r", encoding="utf-8") as f:
            content = f.read()
        self.assertEqual(content, "Just a plain text job posting, not JSON.")

    def test_read_evaluation_returns_none_when_never_evaluated(self):
        path = self._write("a.json", json.dumps({"job_title": "Role"}))
        self.assertIsNone(jd_manager.read_evaluation(path))

    def test_read_evaluation_returns_none_for_plain_text_jd(self):
        path = self._write("dummy.txt", "Just plain text.")
        self.assertIsNone(jd_manager.read_evaluation(path))


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
        path = self._write("a.json", json.dumps({
            "job_title": "Role", "company_name": "Acme",
            "_evaluation": {"composite_score": 4.0, "recommendation": "Strong pursue"},
        }))
        result = jd_manager.read_jd_text(path)
        parsed = json.loads(result)
        self.assertNotIn("_evaluation", parsed)
        self.assertEqual(parsed["job_title"], "Role")
        self.assertEqual(parsed["company_name"], "Acme")

    def test_plain_text_jd_returns_raw_text_unchanged(self):
        path = self._write("dummy.txt", "Just a plain text job posting.")
        self.assertEqual(jd_manager.read_jd_text(path), "Just a plain text job posting.")

    def test_missing_file_raises_file_not_found_error(self):
        with self.assertRaises(FileNotFoundError):
            jd_manager.read_jd_text(os.path.join(self.tmp_dir, "does_not_exist.json"))


if __name__ == "__main__":
    unittest.main()
