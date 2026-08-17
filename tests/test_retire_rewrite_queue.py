"""Unit tests for scripts/retire_rewrite_queue.py."""

import csv
import os
import sys
import tempfile
import unittest
from unittest.mock import patch

SCRIPTS_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts"
)
if SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, SCRIPTS_DIR)

import retire_rewrite_queue  # noqa: E402


class TestRetireRewriteQueue(unittest.TestCase):
    """Test suite for retire_rewrite_queue module."""

    def test_main_missing_queue_file(self):
        """Test main behavior when rewrite-queue.csv is missing."""
        with tempfile.TemporaryDirectory() as tmpdir:
            fake_queue = os.path.join(tmpdir, "rewrite-queue.csv")
            with patch.object(retire_rewrite_queue, "REWRITE_QUEUE", fake_queue):
                retire_rewrite_queue.main()

    def test_main_retires_non_representative_rows(self):
        """Test non-representative rows are moved to retired-bullets.csv and queue updated."""
        with tempfile.TemporaryDirectory() as tmpdir:
            queue_path = os.path.join(tmpdir, "rewrite-queue.csv")
            retired_path = os.path.join(tmpdir, "retired-bullets.csv")

            rows = [
                {
                    "cluster_id": "c1",
                    "cluster_size": "2",
                    "is_representative": "true",
                    "Bullet Point": "Keep this representative bullet",
                    "rewrite_status": "PENDING",
                },
                {
                    "cluster_id": "c1",
                    "cluster_size": "2",
                    "is_representative": "false",
                    "Bullet Point": "Retire this duplicate bullet",
                    "rewrite_status": "PENDING",
                },
                {
                    "cluster_id": "c2",
                    "cluster_size": "1",
                    "is_representative": "false",
                    "Bullet Point": "Already retired row",
                    "rewrite_status": "RETIRED",
                },
            ]

            with open(queue_path, "w", newline="", encoding="utf-8") as f:
                writer = csv.DictWriter(
                    f, fieldnames=retire_rewrite_queue.REWRITE_HEADER
                )
                writer.writeheader()
                writer.writerows(rows)

            with patch.object(retire_rewrite_queue, "REWRITE_QUEUE", queue_path):
                with patch.object(retire_rewrite_queue, "RETIRED_PATH", retired_path):
                    retire_rewrite_queue.main()

                    # Check queue contents
                    with open(queue_path, newline="", encoding="utf-8") as f:
                        active_rows = list(csv.DictReader(f))
                        self.assertEqual(len(active_rows), 2)
                        self.assertEqual(
                            active_rows[0]["Bullet Point"],
                            "Keep this representative bullet",
                        )

                    # Check retired contents
                    with open(retired_path, newline="", encoding="utf-8") as f:
                        retired_rows = list(csv.DictReader(f))
                        self.assertEqual(len(retired_rows), 1)
                        self.assertEqual(
                            retired_rows[0]["Bullet Point"],
                            "Retire this duplicate bullet",
                        )
                        self.assertEqual(retired_rows[0]["rewrite_status"], "RETIRED")
                        self.assertEqual(retired_rows[0]["next_action"], "CLOSED_OUT")

                    # Run again to test idempotency when retired file already exists
                    retire_rewrite_queue.main()


if __name__ == "__main__":
    unittest.main()
