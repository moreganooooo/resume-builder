import os
import shutil
import sys
import unittest
from unittest.mock import patch

SCRIPTS_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts"
)
sys.path.insert(0, SCRIPTS_DIR)

import kb_snapshot  # noqa: E402


class TestSnapshotKb(unittest.TestCase):

    def setUp(self):
        self.tmp_dir = os.path.join(os.path.dirname(__file__), "_tmp_kb_snapshot")
        self.kb_dir = os.path.join(self.tmp_dir, "knowledge_base")
        self.snapshot_root = os.path.join(self.tmp_dir, "kb_snapshots")
        os.makedirs(self.kb_dir, exist_ok=True)
        self._kb_patcher = patch(
            "kb_snapshot.profile_paths.kb_dir", return_value=self.kb_dir
        )
        self._snap_patcher = patch(
            "kb_snapshot.profile_paths.kb_snapshot_dir", return_value=self.snapshot_root
        )
        self._kb_patcher.start()
        self._snap_patcher.start()

    def tearDown(self):
        self._kb_patcher.stop()
        self._snap_patcher.stop()
        if os.path.isdir(self.tmp_dir):
            shutil.rmtree(self.tmp_dir)

    def _write_kb_file(self, name, content="content"):
        with open(os.path.join(self.kb_dir, name), "w", encoding="utf-8") as f:
            f.write(content)

    def test_returns_none_when_kb_dir_missing(self):
        shutil.rmtree(self.kb_dir)
        self.assertIsNone(kb_snapshot.snapshot_kb())

    def test_copies_top_level_files_into_a_new_snapshot(self):
        self._write_kb_file("bullet-bank.md", "the bank")
        self._write_kb_file("profile.yml", "the profile")

        dest = kb_snapshot.snapshot_kb()

        self.assertTrue(os.path.isdir(dest))
        with open(os.path.join(dest, "bullet-bank.md"), encoding="utf-8") as f:
            self.assertEqual(f.read(), "the bank")
        with open(os.path.join(dest, "profile.yml"), encoding="utf-8") as f:
            self.assertEqual(f.read(), "the profile")

    def test_does_not_recurse_into_subdirectories(self):
        self._write_kb_file("bullet-bank.md")
        os.makedirs(os.path.join(self.kb_dir, "archive"), exist_ok=True)
        with open(
            os.path.join(self.kb_dir, "archive", "old.md"), "w", encoding="utf-8"
        ) as f:
            f.write("archived")

        dest = kb_snapshot.snapshot_kb()

        self.assertIn("bullet-bank.md", os.listdir(dest))
        self.assertNotIn("archive", os.listdir(dest))

    def test_rotation_keeps_only_the_newest_n_snapshots(self):
        self._write_kb_file("bullet-bank.md")
        names = [
            "20260801-000000",
            "20260802-000000",
            "20260803-000000",
            "20260804-000000",
        ]
        with patch("kb_snapshot.time.strftime", side_effect=names):
            for _ in range(4):
                kb_snapshot.snapshot_kb(keep=2)

        remaining = sorted(os.listdir(self.snapshot_root))
        self.assertEqual(remaining, names[-2:])


if __name__ == "__main__":
    unittest.main()
