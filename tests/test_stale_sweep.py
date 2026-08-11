import os
import sys
import tempfile
import unittest
from unittest.mock import patch

SCRIPTS_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts")
sys.path.insert(0, SCRIPTS_DIR)

import stale_sweep  # noqa: E402


def _row(path, company="Acme", title="Engineer", application=None):
    """Builds a picker.list_all_evaluated_jds()-shaped row. Age isn't
    carried on the row (matching the real interface, where age is
    derived via jd_manager.compute_posting_age_days(), not stored) --
    each test patches that function directly instead."""
    return {
        "path": path, "status": "Pending", "evaluation": {}, "liveness": None,
        "application": application, "title": title, "company": company,
    }


class TestPreviewSweepClassification(unittest.TestCase):
    """preview_sweep()'s selection logic, entirely mocked -- no real
    files touched by this class."""

    def _preview(self, rows, ages, threshold_days=30):
        with patch("stale_sweep.picker.list_all_evaluated_jds", return_value=rows), \
             patch("stale_sweep.jd_manager.compute_posting_age_days", side_effect=lambda p: ages[p]):
            return stale_sweep.preview_sweep(threshold_days=threshold_days)

    def test_older_than_threshold_is_selected(self):
        result = self._preview([_row("/jds/old.json")], {"/jds/old.json": 31}, threshold_days=30)
        self.assertEqual([i["path"] for i in result["to_archive"]], ["/jds/old.json"])
        self.assertEqual(result["to_archive"][0]["age_days"], 31)
        self.assertEqual(result["to_keep_count"], 0)

    def test_younger_than_threshold_is_not_selected(self):
        result = self._preview([_row("/jds/new.json")], {"/jds/new.json": 5}, threshold_days=30)
        self.assertEqual(result["to_archive"], [])
        self.assertEqual(result["to_keep_count"], 1)
        self.assertEqual(result["oldest_kept_days"], 5)

    def test_exactly_at_threshold_is_archived_boundary_is_inclusive(self):
        # Pinned choice: "archive postings 30+ days old" reads as
        # inclusive, so age_days == threshold_days must archive -- see
        # stale_sweep._classify()'s docstring for why this differs from
        # orchestrator.fit_composite_score()'s strict ">" penalty cutoff.
        result = self._preview([_row("/jds/edge.json")], {"/jds/edge.json": 30}, threshold_days=30)
        self.assertEqual([i["path"] for i in result["to_archive"]], ["/jds/edge.json"])
        self.assertEqual(result["to_keep_count"], 0)

    def test_one_day_under_threshold_is_kept(self):
        result = self._preview([_row("/jds/almost.json")], {"/jds/almost.json": 29}, threshold_days=30)
        self.assertEqual(result["to_archive"], [])
        self.assertEqual(result["to_keep_count"], 1)

    def test_age_none_is_skipped_and_counted_never_archived(self):
        result = self._preview([_row("/jds/unknown.json")], {"/jds/unknown.json": None}, threshold_days=30)
        self.assertEqual(result["to_archive"], [])
        self.assertEqual(result["to_keep_count"], 0)
        self.assertEqual(result["skipped_no_age_count"], 1)

    def test_already_applied_never_archived_even_when_ancient(self):
        applied = {"status": "Applied", "applied_at": "2020-01-01T00:00:00"}
        result = self._preview(
            [_row("/jds/applied.json", application=applied)],
            {"/jds/applied.json": 9999}, threshold_days=30,
        )
        self.assertEqual(result["to_archive"], [])
        self.assertEqual(result["to_keep_count"], 1)
        self.assertEqual(result["oldest_kept_days"], 9999)

    def test_already_applied_and_since_rejected_still_never_archived(self):
        # Presence of an _application record is the gate, not which
        # status it holds -- a "Rejected" application is still a real,
        # already-acted-on lead, not fair game for silent deletion.
        rejected = {"status": "Rejected", "applied_at": "2020-01-01T00:00:00"}
        result = self._preview(
            [_row("/jds/rejected.json", application=rejected)],
            {"/jds/rejected.json": 500}, threshold_days=30,
        )
        self.assertEqual(result["to_archive"], [])

    def test_preview_sweep_writes_nothing(self):
        rows = [_row("/jds/old.json")]
        with patch("stale_sweep.picker.list_all_evaluated_jds", return_value=rows), \
             patch("stale_sweep.jd_manager.compute_posting_age_days", return_value=999), \
             patch("stale_sweep.shutil.move") as mock_shutil_move, \
             patch("stale_sweep._move_to_expired") as mock_move_to_expired:
            stale_sweep.preview_sweep(threshold_days=30)
        mock_shutil_move.assert_not_called()
        mock_move_to_expired.assert_not_called()


class TestRunSweep(unittest.TestCase):
    """run_sweep() actually moving files -- uses real temp dirs standing
    in for jds/<profile>/ and jds/<profile>/expired/, never the user's
    real jds/ data."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.jds_dir = os.path.join(self._tmp.name, "jds")
        self.expired_dir = os.path.join(self._tmp.name, "expired")
        os.makedirs(self.jds_dir)
        patcher = patch("stale_sweep.jd_manager.EXPIRED_DIR", self.expired_dir)
        patcher.start()
        self.addCleanup(patcher.stop)

    def _make_jd(self, name):
        path = os.path.join(self.jds_dir, name)
        with open(path, "w", encoding="utf-8") as f:
            f.write("{}")
        return path

    def test_run_sweep_moves_stale_postings_into_expired_dir(self):
        path = self._make_jd("old.json")
        rows = [_row(path)]
        with patch("stale_sweep.picker.list_all_evaluated_jds", return_value=rows), \
             patch("stale_sweep.jd_manager.compute_posting_age_days", return_value=45):
            result = stale_sweep.run_sweep(threshold_days=30)

        self.assertEqual(result["archived_count"], 1)
        self.assertEqual(result["errors"], [])
        self.assertFalse(os.path.exists(path))
        self.assertTrue(os.path.exists(os.path.join(self.expired_dir, "old.json")))

    def test_run_sweep_never_moves_an_already_applied_posting(self):
        path = self._make_jd("applied.json")
        applied = {"status": "Applied", "applied_at": "2020-01-01T00:00:00"}
        rows = [_row(path, application=applied)]
        with patch("stale_sweep.picker.list_all_evaluated_jds", return_value=rows), \
             patch("stale_sweep.jd_manager.compute_posting_age_days", return_value=9999):
            result = stale_sweep.run_sweep(threshold_days=30)

        self.assertEqual(result["archived_count"], 0)
        self.assertTrue(os.path.exists(path))

    def test_run_sweep_continues_past_a_failing_move_and_reports_it(self):
        good_path = self._make_jd("good.json")
        # Never created on disk, so its move raises FileNotFoundError --
        # simulates a file that vanished/was already moved out from
        # under the sweep between preview and run.
        bad_path = os.path.join(self.jds_dir, "missing.json")
        rows = [_row(bad_path), _row(good_path)]

        with patch("stale_sweep.picker.list_all_evaluated_jds", return_value=rows), \
             patch("stale_sweep.jd_manager.compute_posting_age_days", return_value=40), \
             patch("stale_sweep.cli_art.friendly_warning") as mock_warning:
            result = stale_sweep.run_sweep(threshold_days=30)

        self.assertEqual(result["archived_count"], 1)
        self.assertEqual(len(result["errors"]), 1)
        self.assertEqual(result["errors"][0]["path"], bad_path)
        self.assertTrue(os.path.exists(os.path.join(self.expired_dir, "good.json")))
        mock_warning.assert_called_once()

    def test_run_sweep_avoids_clobbering_an_existing_same_named_file(self):
        # A prior expired-move (e.g. from liveness.py) could already have
        # left a same-named file in EXPIRED_DIR -- _move_to_expired must
        # not silently overwrite it.
        os.makedirs(self.expired_dir, exist_ok=True)
        with open(os.path.join(self.expired_dir, "dup.json"), "w", encoding="utf-8") as f:
            f.write('{"marker": "pre-existing"}')

        path = self._make_jd("dup.json")
        rows = [_row(path)]
        with patch("stale_sweep.picker.list_all_evaluated_jds", return_value=rows), \
             patch("stale_sweep.jd_manager.compute_posting_age_days", return_value=45):
            result = stale_sweep.run_sweep(threshold_days=30)

        self.assertEqual(result["archived_count"], 1)
        with open(os.path.join(self.expired_dir, "dup.json"), encoding="utf-8") as f:
            self.assertIn("pre-existing", f.read())
        self.assertTrue(os.path.exists(os.path.join(self.expired_dir, "dup_1.json")))


if __name__ == "__main__":
    unittest.main()
