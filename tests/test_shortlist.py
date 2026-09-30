"""Shortlist ("favorite") persistence and export.

The mark follows the same JD-JSON metadata convention as _evaluation /
_liveness / _application: an underscore-prefixed key on the JD's own file,
with a save/read pair. These tests pin the two properties the dashboard
depends on -- that the mark round-trips, and that read_jd_text() still
strips it before a JD reaches a prompt.
"""

import json
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))

import jd_manager  # noqa: E402
import picker  # noqa: E402
import profile_paths  # noqa: E402


class TestFavoriteRoundTrip(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = os.path.join(self.tmp.name, "job.json")
        with open(self.path, "w", encoding="utf-8") as f:
            json.dump(
                {"job_title": "Designer", "company_name": "Acme", "description": "x"},
                f,
            )

    def test_unmarked_jd_is_not_favorited(self):
        self.assertFalse(jd_manager.read_favorite(self.path))

    def test_save_and_read_round_trip(self):
        jd_manager.save_favorite(self.path, True)
        self.assertTrue(jd_manager.read_favorite(self.path))
        jd_manager.save_favorite(self.path, False)
        self.assertFalse(jd_manager.read_favorite(self.path))

    def test_unfavoriting_records_rather_than_deletes(self):
        """An explicit False keeps marked_at, so "looked at and passed
        over" stays distinguishable from "never considered"."""
        jd_manager.save_favorite(self.path, True)
        jd_manager.save_favorite(self.path, False)
        with open(self.path, encoding="utf-8") as f:
            data = json.load(f)
        self.assertIn("_favorite", data)
        self.assertFalse(data["_favorite"]["favorited"])
        self.assertTrue(data["_favorite"]["marked_at"])

    def test_toggle_returns_the_new_state(self):
        self.assertTrue(jd_manager.toggle_favorite(self.path))
        self.assertFalse(jd_manager.toggle_favorite(self.path))

    def test_saving_preserves_the_rest_of_the_jd(self):
        jd_manager.save_favorite(self.path, True)
        with open(self.path, encoding="utf-8") as f:
            data = json.load(f)
        self.assertEqual(data["job_title"], "Designer")
        self.assertEqual(data["company_name"], "Acme")

    def test_favorite_never_reaches_a_prompt(self):
        """read_jd_text() strips underscore-prefixed keys generically, so
        _favorite must not leak into a Gemini call as JD content."""
        jd_manager.save_favorite(self.path, True)
        self.assertNotIn("_favorite", jd_manager.read_jd_text(self.path))

    def test_non_dict_jd_is_a_silent_no_op(self):
        """Matches save_liveness/save_evaluation: a plain-text JD is not an
        error, it just has nowhere to put the mark."""
        text_path = os.path.join(self.tmp.name, "plain.txt")
        with open(text_path, "w", encoding="utf-8") as f:
            f.write("a plain text job description")
        jd_manager.save_favorite(text_path, True)  # must not raise
        self.assertFalse(jd_manager.read_favorite(text_path))

    def test_missing_file_reads_false(self):
        self.assertFalse(
            jd_manager.read_favorite(os.path.join(self.tmp.name, "nope.json"))
        )


if __name__ == "__main__":
    unittest.main()


class TestPickerExport(unittest.TestCase):
    """list_all_evaluated_jds() now exports two things it used to withhold:
    expired JDs, and roles the evaluator recommended skipping. Both are
    flagged rather than hidden -- the dashboard decides visibility (expired
    and skip sit behind the Pipeline's [d] toggle), so nothing is
    unreachable."""

    def setUp(self):
        from unittest.mock import patch

        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)

        self.iso = profile_paths.isolate_for_tests(self.tmp.name)
        self.iso.__enter__()
        self.addCleanup(lambda: self.iso.__exit__(None, None, None))

        self.jds = os.path.join(self.tmp.name, "jds", "testfav")
        for sub in ("", "completed", "archived", "expired"):
            os.makedirs(os.path.join(self.jds, sub), exist_ok=True)

        for attr, value in (
            ("JDS_DIR", self.jds),
            ("COMPLETED_DIR", os.path.join(self.jds, "completed")),
            ("ARCHIVED_DIR", os.path.join(self.jds, "archived")),
            ("EXPIRED_DIR", os.path.join(self.jds, "expired")),
        ):
            patcher = patch.object(jd_manager, attr, value)
            patcher.start()
            self.addCleanup(patcher.stop)

    def _write(self, subdir, name, recommendation="Pursue", favorited=None):
        payload = {
            "job_title": name,
            "company_name": "Acme",
            "_evaluation": {"recommendation": recommendation, "composite_score": 4.2},
        }
        if favorited is not None:
            payload["_favorite"] = {"favorited": favorited, "marked_at": "2026-09-29"}
        path = os.path.join(self.jds, subdir, f"{name}.json")
        with open(path, "w", encoding="utf-8") as f:
            json.dump(payload, f)
        return path

    def _rows_by_title(self):
        return {r["title"]: r for r in picker.list_all_evaluated_jds()}

    def test_expired_jds_are_exported(self):
        self._write("", "Pending Role")
        self._write("expired", "Expired Role")
        rows = self._rows_by_title()
        self.assertIn("Expired Role", rows)
        self.assertEqual(rows["Expired Role"]["status"], "Expired")

    def test_expired_can_be_excluded_by_the_statuses_argument(self):
        self._write("expired", "Expired Role")
        rows = picker.list_all_evaluated_jds(statuses=["Pending"])
        self.assertEqual(rows, [])

    def test_skip_recommended_roles_are_exported_and_flagged(self):
        """They used to be dropped here, which made them unreachable from
        every dashboard surface."""
        self._write("", "Skipped Role", recommendation="Skip")
        rows = self._rows_by_title()
        self.assertIn("Skipped Role", rows)
        self.assertTrue(rows["Skipped Role"]["skip_recommended"])

    def test_skip_recommended_keeps_its_real_status(self):
        """The Skip verdict is a display concern; the row's status stays
        the one its directory implies."""
        self._write("", "Skipped Role", recommendation="Skip")
        self.assertEqual(self._rows_by_title()["Skipped Role"]["status"], "Pending")

    def test_pursue_roles_are_not_flagged_as_skip(self):
        self._write("", "Good Role")
        self.assertFalse(self._rows_by_title()["Good Role"]["skip_recommended"])

    def test_favorite_is_exported(self):
        self._write("", "Starred Role", favorited=True)
        self._write("", "Plain Role")
        rows = self._rows_by_title()
        self.assertTrue(rows["Starred Role"]["favorite"])
        self.assertFalse(rows["Plain Role"]["favorite"])
