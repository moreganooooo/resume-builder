import csv
import os
import sys
import tempfile
import unittest

SCRIPTS_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts")
sys.path.insert(0, SCRIPTS_DIR)

import bullet_bank_menu  # noqa: E402


class TestStageStatusMtime(unittest.TestCase):

    def setUp(self):
        self.tmp_dir = tempfile.mkdtemp()

    def tearDown(self):
        for name in os.listdir(self.tmp_dir):
            os.remove(os.path.join(self.tmp_dir, name))
        os.rmdir(self.tmp_dir)

    def _touch(self, name, mtime_offset=0):
        path = os.path.join(self.tmp_dir, name)
        with open(path, "w", encoding="utf-8") as f:
            f.write("x")
        stat = os.stat(path)
        os.utime(path, (stat.st_atime + mtime_offset, stat.st_mtime + mtime_offset))
        return path

    def test_missing_output_is_never_run(self):
        input_path = self._touch("input.csv")
        stage = {"inputs": [input_path], "output": os.path.join(self.tmp_dir, "missing.csv"), "status_mode": "mtime"}
        status, detail = bullet_bank_menu._stage_status(stage)
        self.assertEqual(status, "Never run")

    def test_output_older_than_input_is_stale(self):
        output_path = self._touch("output.csv", mtime_offset=0)
        input_path = self._touch("input.csv", mtime_offset=10)
        stage = {"inputs": [input_path], "output": output_path, "status_mode": "mtime"}
        status, detail = bullet_bank_menu._stage_status(stage)
        self.assertEqual(status, "Stale")

    def test_output_newer_than_input_is_up_to_date(self):
        input_path = self._touch("input.csv", mtime_offset=0)
        output_path = self._touch("output.csv", mtime_offset=10)
        stage = {"inputs": [input_path], "output": output_path, "status_mode": "mtime"}
        status, detail = bullet_bank_menu._stage_status(stage)
        self.assertEqual(status, "Up to date")
        self.assertIn("as of", detail)

    def test_missing_input_does_not_crash(self):
        output_path = self._touch("output.csv")
        stage = {
            "inputs": [os.path.join(self.tmp_dir, "does_not_exist.csv")],
            "output": output_path, "status_mode": "mtime",
        }
        status, _ = bullet_bank_menu._stage_status(stage)
        self.assertEqual(status, "Up to date")


class TestStageStatusColumns(unittest.TestCase):

    def setUp(self):
        self.tmp_dir = tempfile.mkdtemp()
        self.csv_path = os.path.join(self.tmp_dir, "keepers.csv")

    def tearDown(self):
        for name in os.listdir(self.tmp_dir):
            os.remove(os.path.join(self.tmp_dir, name))
        os.rmdir(self.tmp_dir)

    def _write_csv(self, rows, fieldnames):
        with open(self.csv_path, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(rows)

    def test_missing_file_is_never_run(self):
        stage = {"output": self.csv_path, "status_mode": "columns", "status_columns": ["hidden_gem_score"]}
        status, _ = bullet_bank_menu._stage_status(stage)
        self.assertEqual(status, "Never run")

    def test_missing_column_entirely_is_stale(self):
        self._write_csv([{"Bullet Point": "x"}], ["Bullet Point"])
        stage = {"output": self.csv_path, "status_mode": "columns", "status_columns": ["hidden_gem_score"]}
        status, _ = bullet_bank_menu._stage_status(stage)
        self.assertEqual(status, "Stale")

    def test_blank_value_in_column_is_stale(self):
        self._write_csv(
            [{"Bullet Point": "a", "hidden_gem_score": "90"}, {"Bullet Point": "b", "hidden_gem_score": ""}],
            ["Bullet Point", "hidden_gem_score"],
        )
        stage = {"output": self.csv_path, "status_mode": "columns", "status_columns": ["hidden_gem_score"]}
        status, _ = bullet_bank_menu._stage_status(stage)
        self.assertEqual(status, "Stale")

    def test_fully_populated_column_is_up_to_date(self):
        self._write_csv(
            [{"Bullet Point": "a", "hidden_gem_score": "90"}, {"Bullet Point": "b", "hidden_gem_score": "10"}],
            ["Bullet Point", "hidden_gem_score"],
        )
        stage = {"output": self.csv_path, "status_mode": "columns", "status_columns": ["hidden_gem_score"]}
        status, _ = bullet_bank_menu._stage_status(stage)
        self.assertEqual(status, "Up to date")

    def test_empty_csv_is_never_run(self):
        self._write_csv([], ["Bullet Point", "hidden_gem_score"])
        stage = {"output": self.csv_path, "status_mode": "columns", "status_columns": ["hidden_gem_score"]}
        status, _ = bullet_bank_menu._stage_status(stage)
        self.assertEqual(status, "Never run")


class TestStagesAndMaintenanceDefinitions(unittest.TestCase):

    def test_six_stages_in_pipeline_order(self):
        self.assertEqual([s["key"] for s in bullet_bank_menu.STAGES],
                          ["audit", "cluster", "rewrite", "audit_keepers", "score_gems", "embed"])
        self.assertEqual([s["number"] for s in bullet_bank_menu.STAGES], [1, 2, 3, 4, 5, 6])

    def test_all_stages_cost_api(self):
        self.assertTrue(all(s["api_cost"] for s in bullet_bank_menu.STAGES))

    def test_two_maintenance_scripts(self):
        self.assertEqual([m["key"] for m in bullet_bank_menu.MAINTENANCE], ["triage", "retire"])


class TestMaintenanceStatus(unittest.TestCase):

    def setUp(self):
        self.tmp_dir = tempfile.mkdtemp()
        self.csv_path = os.path.join(self.tmp_dir, "watched.csv")

    def tearDown(self):
        for name in os.listdir(self.tmp_dir):
            os.remove(os.path.join(self.tmp_dir, name))
        os.rmdir(self.tmp_dir)

    def _write_csv(self, rows, fieldnames):
        with open(self.csv_path, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(rows)

    def test_triage_missing_file_is_empty(self):
        entry = {"key": "triage", "watched_file": self.csv_path}
        self.assertEqual(bullet_bank_menu._maintenance_status(entry), "empty -- nothing to triage")

    def test_triage_reports_row_count(self):
        self._write_csv([{"Bullet Point": "a"}, {"Bullet Point": "b"}], ["Bullet Point"])
        entry = {"key": "triage", "watched_file": self.csv_path}
        self.assertEqual(bullet_bank_menu._maintenance_status(entry), "2 row(s) waiting")

    def test_retire_missing_file_is_none_pending(self):
        entry = {"key": "retire", "watched_file": self.csv_path}
        self.assertEqual(bullet_bank_menu._maintenance_status(entry), "none pending")

    def test_retire_counts_only_non_representative_rows(self):
        self._write_csv(
            [{"is_representative": "True"}, {"is_representative": "False"}, {"is_representative": "False"}],
            ["is_representative"],
        )
        entry = {"key": "retire", "watched_file": self.csv_path}
        self.assertEqual(bullet_bank_menu._maintenance_status(entry), "2 bullet(s) pending retirement")

    def test_retire_none_pending_when_all_representative(self):
        self._write_csv([{"is_representative": "True"}], ["is_representative"])
        entry = {"key": "retire", "watched_file": self.csv_path}
        self.assertEqual(bullet_bank_menu._maintenance_status(entry), "none pending")


if __name__ == "__main__":
    unittest.main()
