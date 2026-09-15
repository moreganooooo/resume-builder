"""removed-bullets.csv: a bullet removed on purpose must never come back,
through any stage (bullet_bank_state.py)."""

import csv
import os
import shutil
import sys
import tempfile
import unittest
from unittest.mock import patch

import pandas as pd

SCRIPTS_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts"
)
sys.path.insert(0, SCRIPTS_DIR)

import audit_keepers  # noqa: E402
import bullet_bank_menu  # noqa: E402
import bullet_bank_state  # noqa: E402
import remove_bullets  # noqa: E402
import triage_needs_review  # noqa: E402

KEEPER_FIELDS = ["Bullet Point", "Role / Company", "original_bullet", "source_cluster_id"]


def _write(path, rows, fieldnames):
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def _read(path):
    if not os.path.exists(path):
        return []
    with open(path, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


class TmpDirCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.removed_path = os.path.join(self.tmp, "removed-bullets.csv")

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def path(self, name):
        return os.path.join(self.tmp, name)


class TestRemovedList(TmpDirCase):
    def test_normalize_ignores_case_whitespace_and_list_marker(self):
        self.assertEqual(
            bullet_bank_state.normalize("-  Built   the THING "), "built the thing"
        )
        self.assertEqual(bullet_bank_state.normalize(float("nan")), "")

    def test_missing_file_is_empty(self):
        self.assertEqual(len(bullet_bank_state.load_removed(self.removed_path)), 0)

    def test_record_is_append_only_and_skips_repeats(self):
        row = {"Bullet Point": "Cut costs 12%", "original_bullet": "raw cost bullet"}
        self.assertEqual(bullet_bank_state.record_removed(self.removed_path, [row], "dup"), 1)
        self.assertEqual(bullet_bank_state.record_removed(self.removed_path, [row], "dup"), 0)
        removed = bullet_bank_state.load_removed(self.removed_path)
        self.assertEqual(len(removed), 1)
        self.assertTrue(removed.blocks("cut costs 12%"))
        self.assertTrue(removed.settles("- Raw cost bullet"))
        # The raw text settles upstream work but does not block a keeper:
        # a sibling rewritten from the same raw bullet stays allowed.
        self.assertFalse(removed.blocks("raw cost bullet"))

    def test_near_duplicate_needs_same_company(self):
        cands = [("Acme", "Grew email revenue $4,000 per month through segmentation")]
        self.assertIsNotNone(
            bullet_bank_state.near_duplicate_of(
                "Grew monthly email revenue by $4,000 via segmentation", "Acme", cands
            )
        )
        self.assertIsNone(
            bullet_bank_state.near_duplicate_of(
                "Grew monthly email revenue by $4,000 via segmentation", "Other", cands
            )
        )
        self.assertIsNone(
            bullet_bank_state.near_duplicate_of("Hired and trained 6 staff", "Acme", cands)
        )


class TestMergeRespectsRemovals(unittest.TestCase):
    def _df(self, rows):
        return pd.DataFrame(rows, columns=KEEPER_FIELDS)

    def test_removed_bullet_is_not_merged_back(self):
        audited = self._df([["Kept", "Acme", "raw1", "c1"]])
        keepers_in = self._df([["Kept", "Acme", "raw1", "c1"], ["Gone", "Acme", "raw2", "c2"]])
        removed = bullet_bank_state.Removed([{"Bullet Point": "Gone"}])
        merged, n_new = audit_keepers.merge_new_rows_from_keepers_in(
            audited, keepers_in, removed
        )
        self.assertEqual(n_new, 0)
        self.assertNotIn("Gone", merged["Bullet Point"].values)

    def test_new_cluster_id_for_known_raw_bullet_is_not_new(self):
        # Cluster ids hash their members, so reclustering changes them; an
        # older rewrite of a raw bullet already represented is a variant.
        audited = self._df([["Edited wording", "Acme", "raw1", "newhash"]])
        keepers_in = self._df([["Old wording", "Acme", "raw1", "oldhash"]])
        _, n_new = audit_keepers.merge_new_rows_from_keepers_in(audited, keepers_in)
        self.assertEqual(n_new, 0)

    def test_text_match_ignores_case_and_list_marker(self):
        audited = self._df([["- Led the launch", "Acme", "", "c1"]])
        keepers_in = self._df([["led the launch", "Acme", "", "c9"]])
        _, n_new = audit_keepers.merge_new_rows_from_keepers_in(audited, keepers_in)
        self.assertEqual(n_new, 0)

    def test_genuinely_new_keeper_still_merges(self):
        audited = self._df([["Kept", "Acme", "raw1", "c1"]])
        keepers_in = self._df([["Brand new", "Acme", "raw9", "c9"]])
        removed = bullet_bank_state.Removed([{"Bullet Point": "Something else"}])
        _, n_new = audit_keepers.merge_new_rows_from_keepers_in(audited, keepers_in, removed)
        self.assertEqual(n_new, 1)


class TestTriageRespectsRemovalsAndNearDuplicates(TmpDirCase):
    def setUp(self):
        super().setUp()
        self.needs_review = self.path("needs-review.csv")
        self.keepers = self.path("bullet-bank-keepers.csv")
        self.audited = self.path("bullet-bank-keepers-audited.csv")
        for name, value in {
            "NEEDS_REVIEW": self.needs_review,
            "KEEPERS_CSV": self.keepers,
            "KEEPERS_AUDITED": self.audited,
            "REWRITE_QUEUE": self.path("rewrite-queue.csv"),
            "RETIRED_PATH": self.path("retired-bullets.csv"),
            "REMOVED_PATH": self.removed_path,
        }.items():
            p = patch.object(triage_needs_review, name, value)
            p.start()
            self.addCleanup(p.stop)

    def _row(self, text):
        return {
            "Bullet Point": text,
            "Role / Company": "Acme",
            "manager_test": "PASS",
            "believability_score": "90",
        }

    def test_removed_bullet_is_dropped_not_kept(self):
        bullet_bank_state.record_removed(self.removed_path, [{"Bullet Point": "Gone"}], "x")
        _write(self.needs_review, [self._row("Gone")], list(self._row("").keys()))
        triage_needs_review.main()
        self.assertEqual(_read(self.keepers), [])
        self.assertFalse(os.path.exists(self.needs_review))

    def test_near_duplicate_of_audited_keeper_is_left_for_review(self):
        _write(
            self.audited,
            [{"Bullet Point": "Grew email revenue $4,000 per month through segmentation",
              "Role / Company": "Acme"}],
            ["Bullet Point", "Role / Company"],
        )
        _write(
            self.needs_review,
            [self._row("Grew monthly email revenue by $4,000 via segmentation")],
            list(self._row("").keys()),
        )
        triage_needs_review.main()
        self.assertEqual(_read(self.keepers), [])
        left = _read(self.needs_review)
        self.assertEqual(len(left), 1)
        self.assertIn("near-duplicate", left[0]["triage_note"])


class TestMenuCountsRemovalsAsDone(TmpDirCase):
    def setUp(self):
        super().setUp()
        self.raw = self.path("clean.csv")
        self.audited = self.path("audited.csv")
        self.cluster_map = self.path("cluster-map.csv")
        for name, value in {
            "RAW_CSV": self.raw,
            "AUDITED_CSV": self.audited,
            "CLUSTER_MAP_CSV": self.cluster_map,
            "CLUSTER_MAP_OUT_CSV": self.path("cluster-map-updated.csv"),
            "KEEPERS_CSV": self.path("keepers.csv"),
            "REMOVED_CSV": self.removed_path,
        }.items():
            p = patch.object(bullet_bank_menu, name, value)
            p.start()
            self.addCleanup(p.stop)
        _write(self.raw, [{"Bullet Point": t} for t in ("a", "b", "c")], ["Bullet Point"])

    def test_audit_progress(self):
        _write(self.audited, [{"Bullet Point": "a"}], ["Bullet Point"])
        self.assertEqual(bullet_bank_menu._audit_progress(), (1, 3))
        bullet_bank_state.record_removed(
            self.removed_path, [{"Bullet Point": "final b", "original_bullet": "b"}], "x"
        )
        self.assertEqual(bullet_bank_menu._audit_progress(), (2, 3))

    def test_cluster_progress_is_by_content_not_mtime(self):
        _write(self.cluster_map, [{"Bullet Point": "- A"}, {"Bullet Point": "b"}], ["Bullet Point"])
        self.assertEqual(bullet_bank_menu._cluster_progress(), (2, 3))
        bullet_bank_state.record_removed(self.removed_path, [{"Bullet Point": "c"}], "x")
        self.assertEqual(bullet_bank_menu._cluster_progress(), (3, 3))

    def test_rewrite_progress(self):
        _write(
            self.cluster_map,
            [{"Bullet Point": "a", "is_representative": "True", "next_action": "REWRITE"}],
            ["Bullet Point", "is_representative", "next_action"],
        )
        self.assertEqual(bullet_bank_menu._rewrite_progress(), (0, 1))
        bullet_bank_state.record_removed(
            self.removed_path, [{"Bullet Point": "final a", "original_bullet": "a"}], "x"
        )
        self.assertEqual(bullet_bank_menu._rewrite_progress(), (1, 1))

    def test_remove_entry_status(self):
        entry = {"key": "remove", "watched_file": self.removed_path}
        self.assertEqual(bullet_bank_menu._maintenance_status(entry), "none removed yet")
        bullet_bank_state.record_removed(self.removed_path, [{"Bullet Point": "a"}], "x")
        self.assertEqual(bullet_bank_menu._maintenance_status(entry), "1 removed so far")


class TestRemovedBulletNeverReturns(TmpDirCase):
    """End to end: remove a keeper, then walk every stage that used to bring
    it back."""

    def setUp(self):
        super().setUp()
        self.keepers = self.path("bullet-bank-keepers.csv")
        self.audited = self.path("bullet-bank-keepers-audited.csv")
        for name, value in {
            "KB_DIR": self.tmp,
            "KEEPERS_CSV": self.keepers,
            "KEEPERS_AUDITED_CSV": self.audited,
            "REMOVED_CSV": self.removed_path,
        }.items():
            p = patch.object(remove_bullets, name, value)
            p.start()
            self.addCleanup(p.stop)
        rows = [
            {"Bullet Point": "Hit 96% accuracy", "Role / Company": "Acme",
             "original_bullet": "raw accuracy", "source_cluster_id": "c1"},
            {"Bullet Point": "Hit 96% accuracy on audits", "Role / Company": "Acme",
             "original_bullet": "raw accuracy", "source_cluster_id": "c1"},
            {"Bullet Point": "Trained 12 staff", "Role / Company": "Acme",
             "original_bullet": "raw training", "source_cluster_id": "c2"},
        ]
        _write(self.keepers, rows, KEEPER_FIELDS)
        _write(self.audited, rows, KEEPER_FIELDS)

    def test_remove_then_rerun(self):
        self.assertEqual(
            remove_bullets.main(["--text", "Hit 96% accuracy", "--reason", "dup", "--yes"]), 0
        )
        audited = [r["Bullet Point"] for r in _read(self.audited)]
        self.assertEqual(audited, ["Hit 96% accuracy on audits", "Trained 12 staff"])
        self.assertNotIn("Hit 96% accuracy", [r["Bullet Point"] for r in _read(self.keepers)])
        self.assertTrue(os.listdir(os.path.join(self.tmp, "backups")))

        removed = bullet_bank_state.load_removed(self.removed_path)
        # Stage 4: an old copy still sitting in keepers.csv is not merged.
        stale_in = pd.DataFrame(
            [["Hit 96% accuracy", "Acme", "raw accuracy", "c-rehashed"]],
            columns=KEEPER_FIELDS,
        )
        _, n_new = audit_keepers.merge_new_rows_from_keepers_in(
            pd.read_csv(self.audited), stale_in, removed
        )
        self.assertEqual(n_new, 0)
        # Stages 1-3: the raw bullet it came from is settled work.
        self.assertTrue(removed.settles("raw accuracy"))
        self.assertFalse(removed.settles("raw training"))
        # Backfill finds nothing left to re-add.
        self.assertEqual(remove_bullets.backfill_candidates(), [])

    def test_dry_run_writes_nothing(self):
        remove_bullets.main(["--text", "Trained 12 staff"])
        self.assertEqual(len(_read(self.audited)), 3)
        self.assertFalse(os.path.exists(self.removed_path))

    def test_from_review_removes_only_marked_rows(self):
        review = self.path("review.csv")
        _write(
            review,
            [{"Bullet Point": "Hit 96% accuracy", "decision": "keep"},
             {"Bullet Point": "Hit 96% accuracy on audits", "decision": "Remove"}],
            ["Bullet Point", "decision"],
        )
        remove_bullets.main(["--from-review", review, "--yes"])
        self.assertEqual(
            [r["Bullet Point"] for r in _read(self.audited)],
            ["Hit 96% accuracy", "Trained 12 staff"],
        )

    def test_since_backup_records_without_deleting(self):
        os.makedirs(self.path("old"))
        old = os.path.join(self.tmp, "old", "bullet-bank-keepers-audited.csv")
        _write(
            old,
            _read(self.audited) + [{"Bullet Point": "Deleted by hand", "Role / Company": "Acme"}],
            KEEPER_FIELDS,
        )
        remove_bullets.main(["--since-backup", old, "--yes"])
        self.assertTrue(bullet_bank_state.load_removed(self.removed_path).blocks("Deleted by hand"))
        self.assertEqual(len(_read(self.audited)), 3)


if __name__ == "__main__":
    unittest.main()
