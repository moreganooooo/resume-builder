import json
import os
import sys
import unittest

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


if __name__ == "__main__":
    unittest.main()
