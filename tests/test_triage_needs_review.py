import csv
import os
import sys
import tempfile
import unittest

SCRIPTS_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts"
)
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
        fieldnames = [
            "Bullet Point",
            "Role / Company",
            "Tags",
            "manager_test",
            "believability_score",
            "rewrite_attempts",
            "rewrite_status",
        ]
        with open(self.needs_review, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(rows)

    # The real bullet-bank-keepers.csv header. Worth spelling out in full: the
    # fixture used to be just ["Bullet Point", "Role / Company"], and that
    # 2-column stand-in is precisely why the column-shift bug shipped -- it
    # can't diverge from KEEP_FIELDS, so it could never reproduce a divergence.
    REAL_KEEPERS_HEADER = [
        "Bullet Point",
        "Role / Company",
        "Tags",
        "accuracy_score",
        "believability_score",
        "clarity_score",
        "ats_value",
        "manager_test",
        "weaknesses",
        "source",
        "rewrite_attempts",
        "rewrite_reasoning",
        "context_gaps",
        "rewrite_date",
        "source_cluster_id",
        "audit_status",
    ]

    def _write_existing_keepers(self, bullets, header=None):
        with open(self.keepers, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=header or self.REAL_KEEPERS_HEADER)
            writer.writeheader()
            for b in bullets:
                writer.writerow({"Bullet Point": b, "Role / Company": "Acme"})

    def _read_keepers(self):
        if not os.path.exists(self.keepers):
            return []
        with open(self.keepers, newline="", encoding="utf-8") as f:
            return list(csv.DictReader(f))

    def _keep_row(self, bullet, company="Acme"):
        return {
            "Bullet Point": bullet,
            "Role / Company": company,
            "Tags": "[content]",
            "manager_test": "PASS",
            "believability_score": "90",
            "rewrite_attempts": "0",
            "rewrite_status": "",
        }


class TestDuplicateSkipping(TriageTestCase):
    # Regression coverage: the same achievement can independently trigger
    # needs-review.csv entries from more than one real resume-build
    # session -- this script used to append every KEEP row unconditionally,
    # so the exact same bullet could enter bullet-bank-keepers.csv twice
    # (or more), contributing to the duplicate-row accumulation this
    # session traced through the whole downstream pipeline.

    def test_bullet_already_in_keepers_is_not_reappended(self):
        self._write_existing_keepers(["Built a complete brand identity from scratch"])
        self._write_needs_review(
            [self._keep_row("Built a complete brand identity from scratch")]
        )

        triage_needs_review.main()

        rows = self._read_keepers()
        self.assertEqual(len(rows), 1)  # still just the one original row
        # And it's cleared out of needs-review.csv, not left behind.
        self.assertFalse(os.path.exists(self.needs_review))

    def test_two_identical_rows_in_the_same_batch_only_add_one(self):
        self._write_needs_review(
            [
                self._keep_row("A brand new achievement."),
                self._keep_row("A brand new achievement."),
            ]
        )

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
        self.assertEqual(
            bullets, {"An existing bullet.", "A genuinely different bullet."}
        )

    def test_no_existing_keepers_file_is_not_treated_as_duplicate(self):
        # First-ever triage run for a profile: bullet-bank-keepers.csv
        # doesn't exist yet at all.
        self._write_needs_review([self._keep_row("First bullet ever.")])

        triage_needs_review.main()

        rows = self._read_keepers()
        self.assertEqual(len(rows), 1)


class TestHeaderAwareAppend(unittest.TestCase):
    """B8: append_rows used to trust the caller's field list and write the
    header only when the file was absent. Against a file whose header differs,
    DictWriter emits values positionally -- no exception, still well-formed
    CSV, wrong from the first differing column on. The real divergence is at
    index 9: KEEP_FIELDS has hidden_gem_score there, disk has source."""

    def setUp(self):
        self.tmp_dir = tempfile.mkdtemp()
        self.path = os.path.join(self.tmp_dir, "target.csv")

    def tearDown(self):
        import shutil

        shutil.rmtree(self.tmp_dir, ignore_errors=True)

    def _write_header(self, header, rows=()):
        with open(self.path, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=header)
            writer.writeheader()
            writer.writerows(rows)

    def _read(self):
        with open(self.path, newline="", encoding="utf-8") as f:
            return list(csv.DictReader(f))

    def test_values_land_under_their_own_column_not_positionally(self):
        self._write_header(TriageTestCase.REAL_KEEPERS_HEADER)
        triage_needs_review.append_rows(
            self.path,
            [
                {
                    "Bullet Point": "A bullet.",
                    "Role / Company": "Acme",
                    "accuracy_score": "77",
                    "rewrite_status": "KEEPER",
                }
            ],
            triage_needs_review.KEEP_FIELDS,
        )
        row = self._read()[0]
        self.assertEqual(row["accuracy_score"], "77")
        # The exact corruption observed on the live file: 77 under source,
        # KEEPER under rewrite_date.
        self.assertEqual(row["source"], "")
        self.assertEqual(row["rewrite_date"], "")

    def test_columns_absent_from_disk_are_dropped_not_shifted(self):
        self._write_header(TriageTestCase.REAL_KEEPERS_HEADER)
        triage_needs_review.append_rows(
            self.path,
            [
                {
                    "Bullet Point": "B.",
                    "Role / Company": "Acme",
                    "hidden_gem_score": "9",
                    "weaknesses": "none",
                }
            ],
            triage_needs_review.KEEP_FIELDS,
        )
        row = self._read()[0]
        self.assertEqual(row["weaknesses"], "none")
        self.assertNotIn("hidden_gem_score", row)

    def test_missing_required_column_raises_rather_than_corrupting(self):
        self._write_header(["Tags", "accuracy_score"])
        with self.assertRaises(ValueError):
            triage_needs_review.append_rows(
                self.path,
                [{"Bullet Point": "C.", "Role / Company": "Acme"}],
                triage_needs_review.KEEP_FIELDS,
            )

    def test_absent_file_still_gets_the_callers_header(self):
        triage_needs_review.append_rows(
            self.path,
            [{"Bullet Point": "D.", "Role / Company": "Acme"}],
            triage_needs_review.KEEP_FIELDS,
        )
        with open(self.path, newline="", encoding="utf-8") as f:
            self.assertEqual(next(csv.reader(f)), triage_needs_review.KEEP_FIELDS)

    def test_existing_rows_are_preserved(self):
        self._write_header(
            TriageTestCase.REAL_KEEPERS_HEADER,
            [
                {
                    "Bullet Point": "Original.",
                    "Role / Company": "Acme",
                    "source": "manual",
                }
            ],
        )
        triage_needs_review.append_rows(
            self.path,
            [{"Bullet Point": "New.", "Role / Company": "Acme"}],
            triage_needs_review.KEEP_FIELDS,
        )
        rows = self._read()
        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[0]["source"], "manual")


if __name__ == "__main__":
    unittest.main()
