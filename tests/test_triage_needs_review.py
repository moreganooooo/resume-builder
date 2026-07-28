import csv
import os
import sys
import tempfile
import unittest

SCRIPTS_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts")
sys.path.insert(0, SCRIPTS_DIR)

import triage_needs_review  # noqa: E402


class TriageTestCase(unittest.TestCase):
    """Redirects every triage path constant to a fresh temp dir per test."""

    def setUp(self):
        self.tmp_dir = tempfile.mkdtemp()
        self.needs_review = os.path.join(self.tmp_dir, "needs-review.csv")
        self.keepers = os.path.join(self.tmp_dir, "bullet-bank-keepers.csv")
        self.rewrite_queue = os.path.join(self.tmp_dir, "rewrite-queue.csv")
        self.retired = os.path.join(self.tmp_dir, "retired-bullets.csv")
        triage_needs_review.NEEDS_REVIEW = self.needs_review
        triage_needs_review.KEEPERS_CSV = self.keepers
        triage_needs_review.REWRITE_QUEUE = self.rewrite_queue
        triage_needs_review.RETIRED_PATH = self.retired

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmp_dir, ignore_errors=True)

    def _write_needs_review(self, rows):
        fieldnames = ["Bullet Point", "Role / Company", "Tags", "manager_test",
                      "believability_score", "rewrite_attempts", "rewrite_status"]
        with open(self.needs_review, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(rows)

    def _write_existing_keepers(self, bullets):
        with open(self.keepers, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=["Bullet Point", "Role / Company"])
            writer.writeheader()
            for b in bullets:
                writer.writerow({"Bullet Point": b, "Role / Company": "Acme"})

    def _read_keepers(self):
        if not os.path.exists(self.keepers):
            return []
        with open(self.keepers, newline="", encoding="utf-8") as f:
            return list(csv.DictReader(f))

    def _keep_row(self, bullet, company="Acme"):
        return {"Bullet Point": bullet, "Role / Company": company, "Tags": "[content]",
                "manager_test": "PASS", "believability_score": "90",
                "rewrite_attempts": "0", "rewrite_status": ""}


class TestDuplicateSkipping(TriageTestCase):
    # Regression coverage: the same achievement can independently trigger
    # needs-review.csv entries from more than one real resume-build
    # session -- this script used to append every KEEP row unconditionally,
    # so the exact same bullet could enter bullet-bank-keepers.csv twice
    # (or more), contributing to the duplicate-row accumulation this
    # session traced through the whole downstream pipeline.

    def test_bullet_already_in_keepers_is_not_reappended(self):
        self._write_existing_keepers(["Built a complete brand identity from scratch"])
        self._write_needs_review([self._keep_row("Built a complete brand identity from scratch")])

        triage_needs_review.main()

        rows = self._read_keepers()
        self.assertEqual(len(rows), 1)  # still just the one original row
        # And it's cleared out of needs-review.csv, not left behind.
        self.assertFalse(os.path.exists(self.needs_review))

    def test_two_identical_rows_in_the_same_batch_only_add_one(self):
        self._write_needs_review([
            self._keep_row("A brand new achievement."),
            self._keep_row("A brand new achievement."),
        ])

        triage_needs_review.main()

        rows = self._read_keepers()
        self.assertEqual(len(rows), 1)

    def test_genuinely_new_bullet_is_still_appended(self):
        self._write_existing_keepers(["An existing bullet."])
        self._write_needs_review([self._keep_row("A genuinely different bullet.")])

        triage_needs_review.main()

        rows = self._read_keepers()
        self.assertEqual(len(rows), 2)
        bullets = {r["Bullet Point"] for r in rows}
        self.assertEqual(bullets, {"An existing bullet.", "A genuinely different bullet."})

    def test_no_existing_keepers_file_is_not_treated_as_duplicate(self):
        # First-ever triage run for a profile: bullet-bank-keepers.csv
        # doesn't exist yet at all.
        self._write_needs_review([self._keep_row("First bullet ever.")])

        triage_needs_review.main()

        rows = self._read_keepers()
        self.assertEqual(len(rows), 1)


if __name__ == "__main__":
    unittest.main()
