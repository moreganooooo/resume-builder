import os
import sys
import unittest

SCRIPTS_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts")
sys.path.insert(0, SCRIPTS_DIR)

import jd_manager  # noqa: E402


class TestAppendApplicationRow(unittest.TestCase):

    def setUp(self):
        self.tmp_dir = os.path.join(os.path.dirname(__file__), "_tmp_applications_md")
        os.makedirs(self.tmp_dir, exist_ok=True)
        self.path = os.path.join(self.tmp_dir, "applications.md")

    def tearDown(self):
        for name in os.listdir(self.tmp_dir):
            os.remove(os.path.join(self.tmp_dir, name))
        os.rmdir(self.tmp_dir)

    def test_creates_the_file_with_a_header_including_a_link_column(self):
        jd_manager.append_application_row("Acme", "Role", True, path=self.path)
        with open(self.path, "r", encoding="utf-8") as f:
            content = f.read()
        self.assertIn("| # | Date | Company | Role | Score | Status | PDF | Link | Report | Notes |", content)

    def test_row_includes_a_clickable_link_when_source_url_given(self):
        jd_manager.append_application_row(
            "Acme", "Content Strategist", True, source_url="https://example.com/job/1", path=self.path,
        )
        with open(self.path, "r", encoding="utf-8") as f:
            content = f.read()
        self.assertIn("[Apply](https://example.com/job/1)", content)

    def test_row_shows_placeholder_when_no_source_url(self):
        jd_manager.append_application_row("Acme", "Role", True, path=self.path)
        with open(self.path, "r", encoding="utf-8") as f:
            lines = f.readlines()
        data_row = lines[-1]
        self.assertIn("| — |", data_row)
        self.assertNotIn("[Apply]", data_row)

    def test_unknown_company_and_title_fall_back_to_unknown(self):
        jd_manager.append_application_row("", "", False, path=self.path)
        with open(self.path, "r", encoding="utf-8") as f:
            content = f.read()
        self.assertIn("| unknown | unknown |", content)

    def test_row_numbers_increment_across_multiple_appends(self):
        jd_manager.append_application_row("Acme", "Role A", True, path=self.path)
        jd_manager.append_application_row("Acme", "Role B", True, path=self.path)
        with open(self.path, "r", encoding="utf-8") as f:
            lines = [line for line in f if line.startswith("| ") and not line.startswith("| #")]
        self.assertTrue(lines[0].startswith("| 1 |"))
        self.assertTrue(lines[1].startswith("| 2 |"))


if __name__ == "__main__":
    unittest.main()
