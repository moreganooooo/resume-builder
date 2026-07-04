import csv
import os
import sys
import tempfile
import unittest

SCRIPTS_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts")
sys.path.insert(0, SCRIPTS_DIR)

import bullet_feedback  # noqa: E402


PASSING_CRITIQUE = {
    "accuracy_score": 95, "believability_score": 90, "clarity_score": 92, "ats_value": 88,
    "manager_test": "PASS", "weaknesses": "None.",
    "hidden_gem_score": 91, "hidden_gem_flag": True, "hidden_gem_reason": "Rare, specific outcome.",
}

FAILING_CRITIQUE = {
    "accuracy_score": 60, "believability_score": 55, "clarity_score": 70, "ats_value": 50,
    "manager_test": "FAIL", "weaknesses": "Vague and unquantified.",
    "hidden_gem_score": 10, "hidden_gem_flag": False, "hidden_gem_reason": "Nothing memorable.",
}


class TestQueueAcceptedRewrite(unittest.TestCase):

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.needs_review = os.path.join(self.tmpdir, "needs-review.csv")
        self.keepers = os.path.join(self.tmpdir, "bullet-bank-keepers.csv")
        self.keepers_audited = os.path.join(self.tmpdir, "bullet-bank-keepers-audited.csv")

        bullet_feedback._seen_bullets = None
        self._orig_keepers = bullet_feedback.KEEPERS
        self._orig_keepers_audited = bullet_feedback.KEEPERS_AUDITED
        bullet_feedback.KEEPERS = self.keepers
        bullet_feedback.KEEPERS_AUDITED = self.keepers_audited

    def tearDown(self):
        bullet_feedback.KEEPERS = self._orig_keepers
        bullet_feedback.KEEPERS_AUDITED = self._orig_keepers_audited
        bullet_feedback._seen_bullets = None

    def _rows(self):
        with open(self.needs_review, newline="", encoding="utf-8") as f:
            return list(csv.DictReader(f))

    def test_queues_rewrite_that_clears_keeper_bar(self):
        queued = bullet_feedback.queue_accepted_rewrite(
            "Managed a team.", "Led a 12-person team to 3x pipeline growth.",
            "Acme", "[sales]", PASSING_CRITIQUE, path=self.needs_review,
        )
        self.assertTrue(queued)
        rows = self._rows()
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["final_bullet"], "Led a 12-person team to 3x pipeline growth.")
        self.assertEqual(rows[0]["Role / Company"], "Acme")
        self.assertEqual(rows[0]["hidden_gem_score"], "91")
        self.assertEqual(rows[0]["hidden_gem_flag"], "True")
        self.assertEqual(rows[0]["rewrite_status"], "", "must stay blank so triage routes it fresh")

    def test_skips_rewrite_that_does_not_clear_keeper_bar(self):
        queued = bullet_feedback.queue_accepted_rewrite(
            "Managed a team.", "Helped manage a team somewhat.",
            "Acme", "[sales]", FAILING_CRITIQUE, path=self.needs_review,
        )
        self.assertFalse(queued)
        self.assertFalse(os.path.exists(self.needs_review))

    def test_skips_duplicate_already_in_queue(self):
        bullet_feedback.queue_accepted_rewrite(
            "Managed a team.", "Led a 12-person team to 3x pipeline growth.",
            "Acme", "[sales]", PASSING_CRITIQUE, path=self.needs_review,
        )
        bullet_feedback._seen_bullets = None  # force a fresh reload from disk
        queued_again = bullet_feedback.queue_accepted_rewrite(
            "Managed a team.", "Led a 12-person team to 3x pipeline growth.",
            "Acme", "[sales]", PASSING_CRITIQUE, path=self.needs_review,
        )
        self.assertFalse(queued_again)
        self.assertEqual(len(self._rows()), 1)

    def test_skips_duplicate_already_in_keeper_bank(self):
        with open(self.keepers, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=["Bullet Point", "Role / Company"])
            writer.writeheader()
            writer.writerow({"Bullet Point": "Led a 12-person team to 3x pipeline growth.", "Role / Company": "Acme"})

        queued = bullet_feedback.queue_accepted_rewrite(
            "Managed a team.", "Led a 12-person team to 3x pipeline growth.",
            "Acme", "[sales]", PASSING_CRITIQUE, path=self.needs_review,
        )
        self.assertFalse(queued)

    def test_migrates_old_schema_file_forward_in_place(self):
        old_fieldnames = [
            "cluster_id", "cluster_size", "is_representative", "next_action",
            "Bullet Point", "Role / Company", "Tags",
            "accuracy_score", "believability_score", "clarity_score", "ats_value",
            "manager_test", "weaknesses",
            "final_bullet", "rewrite_status", "rewrite_attempts",
            "rewrite_reasoning", "context_gaps", "rewrite_date",
        ]
        with open(self.needs_review, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=old_fieldnames)
            writer.writeheader()
            writer.writerow({"Bullet Point": "An old pre-existing row.", "Role / Company": "Legacy Co"})

        bullet_feedback.queue_accepted_rewrite(
            "Managed a team.", "Led a 12-person team to 3x pipeline growth.",
            "Acme", "[sales]", PASSING_CRITIQUE, path=self.needs_review,
        )

        rows = self._rows()
        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[0]["Bullet Point"], "An old pre-existing row.")
        self.assertEqual(rows[0]["hidden_gem_score"], "", "migrated old row should have blank new columns")
        self.assertEqual(rows[1]["final_bullet"], "Led a 12-person team to 3x pipeline growth.")


if __name__ == "__main__":
    unittest.main()
