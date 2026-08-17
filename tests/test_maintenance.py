import os
import sys
import unittest
from unittest.mock import patch

SCRIPTS_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts"
)
sys.path.insert(0, SCRIPTS_DIR)

import maintenance  # noqa: E402


class TestRecordAndGetLastRun(unittest.TestCase):

    def setUp(self):
        self.tmp_dir = os.path.join(os.path.dirname(__file__), "_tmp_maintenance_log")
        os.makedirs(self.tmp_dir, exist_ok=True)
        self.log_path = os.path.join(self.tmp_dir, "maintenance_log.json")
        self._patcher = patch(
            "maintenance.profile_paths.maintenance_log_path", return_value=self.log_path
        )
        self._patcher.start()

    def tearDown(self):
        self._patcher.stop()
        for name in os.listdir(self.tmp_dir):
            os.remove(os.path.join(self.tmp_dir, name))
        os.rmdir(self.tmp_dir)

    def test_get_last_run_returns_none_when_never_recorded(self):
        self.assertIsNone(maintenance.get_last_run("doctor"))

    def test_record_then_get_round_trips(self):
        maintenance.record_run("doctor")
        result = maintenance.get_last_run("doctor")
        self.assertIsNotNone(result)

    def test_multiple_tasks_tracked_independently(self):
        maintenance.record_run("doctor")
        self.assertIsNone(maintenance.get_last_run("bullet_bank_triage"))
        maintenance.record_run("bullet_bank_triage")
        self.assertIsNotNone(maintenance.get_last_run("doctor"))
        self.assertIsNotNone(maintenance.get_last_run("bullet_bank_triage"))

    def test_second_record_updates_the_timestamp(self):
        maintenance.record_run("doctor")
        first = maintenance.get_last_run("doctor")
        maintenance.record_run("doctor")
        second = maintenance.get_last_run("doctor")
        self.assertGreaterEqual(second, first)

    def test_corrupt_log_file_does_not_raise(self):
        with open(self.log_path, "w", encoding="utf-8") as f:
            f.write("not valid json{{{")
        self.assertIsNone(maintenance.get_last_run("doctor"))
        maintenance.record_run(
            "doctor"
        )  # should not raise, overwrites the corrupt file
        self.assertIsNotNone(maintenance.get_last_run("doctor"))


if __name__ == "__main__":
    unittest.main()
