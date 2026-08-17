"""Tests for collision-safe JD moves and the discovery-date fallback.

Both exist because of the same failure shape: something that silently
produced a wrong result with no error. `shutil.move` overwrote a
same-named JD in expired/, destroying its evaluation and application
history without a word; and a posting with no date signal was invisible
to both the staleness curve and the sweep, so it lived in the queue
forever without anyone being told why.
"""

import datetime
import json
import os
import sys
import tempfile
import unittest
from unittest.mock import patch

SCRIPTS_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts")
sys.path.insert(0, SCRIPTS_DIR)

import db  # noqa: E402
import jd_manager  # noqa: E402
import profile_paths  # noqa: E402
import stale_sweep  # noqa: E402


def _write_jd(path: str, **fields) -> str:
    with open(path, "w", encoding="utf-8") as f:
        json.dump({"job_title": "Analyst", "company_name": "Acme", **fields}, f)
    return path


class TestMoveJdTo(unittest.TestCase):
    """move_jd_to() now also syncs data.db (F4) -- isolate every test in
    this class from the real profile's database so a plain functional
    test of the move itself doesn't write throwaway job rows into
    production data (this bit once already; see docs/review's F4 fix)."""

    def setUp(self):
        self._db_tmpdir = tempfile.mkdtemp()
        patcher = patch("profile_paths.profile_root", return_value=self._db_tmpdir)
        self._profile_root_patch = patcher.start()
        self.addCleanup(patcher.stop)
        self.addCleanup(lambda: __import__("shutil").rmtree(self._db_tmpdir, ignore_errors=True))

    def test_moves_into_destination_keeping_its_basename(self):
        with tempfile.TemporaryDirectory() as d:
            src = _write_jd(os.path.join(d, "job.json"))
            dest_dir = os.path.join(d, "expired")
            result = jd_manager.move_jd_to(src, dest_dir)
            self.assertEqual(os.path.basename(result), "job.json")
            self.assertTrue(os.path.exists(result))
            self.assertFalse(os.path.exists(src))

    def test_colliding_basename_does_not_destroy_the_existing_file(self):
        """The actual bug. Two postings sharing a basename -- ordinary when
        the same role is found via two sources -- meant one silently
        overwrote the other, taking its evaluation and application history
        with it. Nothing raised, so nothing caught it."""
        with tempfile.TemporaryDirectory() as d:
            dest_dir = os.path.join(d, "expired")
            os.makedirs(dest_dir)
            existing = _write_jd(os.path.join(dest_dir, "job.json"), marker="FIRST")
            incoming = _write_jd(os.path.join(d, "job.json"), marker="SECOND")

            result = jd_manager.move_jd_to(incoming, dest_dir)

            self.assertNotEqual(result, existing)
            with open(existing, encoding="utf-8") as f:
                self.assertEqual(json.load(f)["marker"], "FIRST", "existing JD was clobbered")
            with open(result, encoding="utf-8") as f:
                self.assertEqual(json.load(f)["marker"], "SECOND")

    def test_repeated_collisions_keep_suffixing(self):
        with tempfile.TemporaryDirectory() as d:
            dest_dir = os.path.join(d, "expired")
            os.makedirs(dest_dir)
            _write_jd(os.path.join(dest_dir, "job.json"))
            _write_jd(os.path.join(dest_dir, "job_1.json"))
            result = jd_manager.move_jd_to(_write_jd(os.path.join(d, "job.json")), dest_dir)
            self.assertEqual(os.path.basename(result), "job_2.json")
            self.assertEqual(len(os.listdir(dest_dir)), 3)

    def test_creates_the_destination_directory_if_absent(self):
        with tempfile.TemporaryDirectory() as d:
            dest_dir = os.path.join(d, "does", "not", "exist")
            result = jd_manager.move_jd_to(_write_jd(os.path.join(d, "job.json")), dest_dir)
            self.assertTrue(os.path.exists(result))

    def test_moving_to_completed_updates_data_db_status_immediately(self):
        """F4: data.db's status must reflect a JD's new location right
        after the move, not just whenever some other save_* call next
        happens to touch this JD (which may be never)."""
        with tempfile.TemporaryDirectory() as d:
            dest_dir = os.path.join(d, "completed")
            src = _write_jd(os.path.join(d, "job.json"))
            jd_manager.move_jd_to(src, dest_dir)

            rows = db.get_jobs_by_status("completed", profile="irrelevant")
            matches = [r for r in rows if r["company"] == "Acme" and r["title"] == "Analyst"]
            self.assertEqual(len(matches), 1)

    def test_moving_to_archived_updates_data_db_status_immediately(self):
        """Same F4 gap existed in archive_jd(), a second, separate
        function that also physically moves a JD's file."""
        with tempfile.TemporaryDirectory() as d:
            src = _write_jd(os.path.join(d, "job.json"))
            with patch("jd_manager.ARCHIVED_DIR", os.path.join(d, "archived")):
                jd_manager.archive_jd(src)

            rows = db.get_jobs_by_status("archived", profile="irrelevant")
            matches = [r for r in rows if r["company"] == "Acme" and r["title"] == "Analyst"]
            self.assertEqual(len(matches), 1)


class TestDiscoveredAt(unittest.TestCase):

    def test_save_then_read_round_trips(self):
        with tempfile.TemporaryDirectory() as d:
            p = _write_jd(os.path.join(d, "job.json"))
            jd_manager.save_discovered_at(p, when="2026-01-15T09:00:00", source="scan")
            stamp = jd_manager.read_discovered_at(p)
            self.assertEqual(stamp["date"], "2026-01-15T09:00:00")
            self.assertEqual(stamp["source"], "scan")

    def test_never_overwrites_an_existing_stamp(self):
        """First sighting is the one that counts. Re-stamping on every scan
        would keep resetting a posting's age and make it permanently young
        -- exactly the bug this whole mechanism exists to fix."""
        with tempfile.TemporaryDirectory() as d:
            p = _write_jd(os.path.join(d, "job.json"))
            jd_manager.save_discovered_at(p, when="2026-01-01T00:00:00", source="scan")
            jd_manager.save_discovered_at(p, when="2026-06-01T00:00:00", source="scan")
            self.assertEqual(jd_manager.read_discovered_at(p)["date"], "2026-01-01T00:00:00")

    def test_read_returns_none_when_never_stamped(self):
        with tempfile.TemporaryDirectory() as d:
            self.assertIsNone(jd_manager.read_discovered_at(_write_jd(os.path.join(d, "j.json"))))

    def test_age_falls_back_to_discovery_date(self):
        with tempfile.TemporaryDirectory() as d:
            p = _write_jd(os.path.join(d, "job.json"))
            ten_days_ago = (datetime.datetime.now() - datetime.timedelta(days=10)).isoformat(timespec="seconds")
            self.assertIsNone(jd_manager.compute_posting_age_days(p))
            jd_manager.save_discovered_at(p, when=ten_days_ago)
            self.assertEqual(jd_manager.compute_posting_age_days(p), 10)

    def test_a_real_posted_date_wins_over_a_discovery_stamp(self):
        """A published date is strictly better information. Discovery is a
        lower bound -- the posting may have been open well before a scan
        first saw it -- so it must never displace source truth."""
        with tempfile.TemporaryDirectory() as d:
            posted = (datetime.datetime.now() - datetime.timedelta(days=40)).isoformat(timespec="seconds")
            discovered = (datetime.datetime.now() - datetime.timedelta(days=2)).isoformat(timespec="seconds")
            p = _write_jd(os.path.join(d, "job.json"), posted_at=posted)
            jd_manager.save_discovered_at(p, when=discovered)
            self.assertEqual(jd_manager.compute_posting_age_days(p), 40)


class TestBackfillDiscoveryDates(unittest.TestCase):

    def _row(self, path):
        return {"path": path, "company": "Acme", "title": "Analyst",
                "status": "Pending", "evaluation": {}, "liveness": None, "application": None}

    def test_dry_run_reports_candidates_and_writes_nothing(self):
        with tempfile.TemporaryDirectory() as d:
            p = _write_jd(os.path.join(d, "job.json"))
            with patch.object(stale_sweep.picker, "list_all_evaluated_jds", return_value=[self._row(p)]):
                result = stale_sweep.backfill_discovery_dates(dry_run=True)
            self.assertEqual(result["candidate_count"], 1)
            self.assertEqual(result["stamped_count"], 0)
            self.assertIsNone(jd_manager.read_discovered_at(p))

    def test_stamps_undated_postings_from_file_mtime(self):
        with tempfile.TemporaryDirectory() as d:
            p = _write_jd(os.path.join(d, "job.json"))
            with patch.object(stale_sweep.picker, "list_all_evaluated_jds", return_value=[self._row(p)]):
                result = stale_sweep.backfill_discovery_dates(dry_run=False)
            self.assertEqual(result["stamped_count"], 1)
            stamp = jd_manager.read_discovered_at(p)
            self.assertEqual(stamp["source"], "backfill-mtime")
            # Inferred, not observed -- the distinction must survive.
            self.assertIsNotNone(jd_manager.compute_posting_age_days(p))

    def test_never_redates_a_posting_that_already_has_an_age(self):
        """Re-dating something that already resolves an age would make it
        younger than it is and let it escape the sweep permanently."""
        with tempfile.TemporaryDirectory() as d:
            posted = (datetime.datetime.now() - datetime.timedelta(days=50)).isoformat(timespec="seconds")
            p = _write_jd(os.path.join(d, "job.json"), posted_at=posted)
            with patch.object(stale_sweep.picker, "list_all_evaluated_jds", return_value=[self._row(p)]):
                result = stale_sweep.backfill_discovery_dates(dry_run=False)
            self.assertEqual(result["candidate_count"], 0)
            self.assertIsNone(jd_manager.read_discovered_at(p))
            self.assertEqual(jd_manager.compute_posting_age_days(p), 50)


if __name__ == "__main__":
    unittest.main()
