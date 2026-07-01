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


if __name__ == "__main__":
    unittest.main()
