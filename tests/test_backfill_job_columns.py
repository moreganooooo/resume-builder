"""Covers the repair for the migration that left jobs rows at
"Untitled Role"/"Unknown Company"/NULL score with the real values sitting
in metadata_json -- both the one-time backfill and the db.upsert_job key
handling that let it happen."""

import json
import os
import sqlite3
import sys
import tempfile
import unittest
from unittest.mock import patch

SCRIPTS_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts"
)
sys.path.insert(0, SCRIPTS_DIR)

import backfill_job_columns as bjc  # noqa: E402
import db  # noqa: E402


def _make_db(path: str) -> sqlite3.Connection:
    """Builds a real schema via db.init_db rather than a hand-copied
    CREATE TABLE -- the first version of this test hard-coded the columns
    and broke the moment db.py grew dedup_hash."""
    conn = sqlite3.connect(path)
    db.init_db(conn)
    return conn


EVALUATED_JD = {
    "job_title": "Lifecycle Marketing Manager",
    "company_name": "Rula",
    "location": "Remote - United States",
    "_evaluation": {
        "composite_score": 4.55,
        "fit_score": 4.2,
        "interview_odds_score": 3.9,
    },
}


class BackfillTestCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.db_path = os.path.join(self.tmp, "data.db")
        _make_db(self.db_path).close()

    def _insert(self, job_id, **columns):
        payload = columns.pop("payload", None)
        row = {
            "id": job_id,
            "title": "Untitled Role",
            "company": "Unknown Company",
            "location": "",
            "raw_text": "",
            "status": "pending",
            "capability_score": None,
            "recruiter_score": None,
            "final_score": None,
            "metadata_json": json.dumps(payload) if payload is not None else None,
        }
        row.update(columns)
        conn = sqlite3.connect(self.db_path)
        with conn:
            conn.execute(
                "INSERT INTO jobs (id, title, company, location, raw_text, status,"
                " capability_score, recruiter_score, final_score, metadata_json)"
                " VALUES (:id, :title, :company, :location, :raw_text, :status,"
                " :capability_score, :recruiter_score, :final_score, :metadata_json)",
                row,
            )
        conn.close()

    def _fetch(self, job_id):
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        row = conn.execute("SELECT * FROM jobs WHERE id = ?", (job_id,)).fetchone()
        conn.close()
        return row


class TestDeriveFixes(BackfillTestCase):

    def test_recovers_title_company_and_scores_from_metadata(self):
        self._insert("a", payload=EVALUATED_JD)
        bjc.backfill(self.db_path, apply_changes=True)

        row = self._fetch("a")
        self.assertEqual(row["title"], "Lifecycle Marketing Manager")
        self.assertEqual(row["company"], "Rula")
        self.assertEqual(row["location"], "Remote - United States")
        self.assertAlmostEqual(row["final_score"], 4.55)
        self.assertAlmostEqual(row["capability_score"], 4.2)
        self.assertAlmostEqual(row["recruiter_score"], 3.9)

    def test_falls_back_to_raw_text_when_metadata_json_is_missing(self):
        self._insert("a", metadata_json=None, raw_text=json.dumps(EVALUATED_JD))
        bjc.backfill(self.db_path, apply_changes=True)
        self.assertEqual(self._fetch("a")["title"], "Lifecycle Marketing Manager")

    def test_never_overwrites_a_real_existing_value(self):
        """A row corrected by hand must survive a later re-run."""
        self._insert(
            "a",
            title="Hand-Corrected Title",
            company="Hand-Corrected Co",
            final_score=1.0,
            payload=EVALUATED_JD,
        )
        bjc.backfill(self.db_path, apply_changes=True)

        row = self._fetch("a")
        self.assertEqual(row["title"], "Hand-Corrected Title")
        self.assertEqual(row["company"], "Hand-Corrected Co")
        self.assertAlmostEqual(row["final_score"], 1.0)

    def test_a_real_zero_score_is_backfilled_and_not_re_backfilled(self):
        """0.0 is a legitimate evaluation result. Truthiness testing would
        both skip writing it and then rewrite it on every later run."""
        payload = {
            "job_title": "Role A",
            "company_name": "Co",
            "_evaluation": {"composite_score": 0.0},
        }
        self._insert("a", payload=payload)
        bjc.backfill(self.db_path, apply_changes=True)
        self.assertEqual(self._fetch("a")["final_score"], 0.0)

        second = bjc.backfill(self.db_path, apply_changes=True)
        self.assertEqual(second["repaired"], 0)

    def test_dry_run_writes_nothing(self):
        self._insert("a", payload=EVALUATED_JD)
        stats = bjc.backfill(self.db_path, apply_changes=False)

        self.assertEqual(stats["repaired"], 1)
        self.assertEqual(self._fetch("a")["title"], "Untitled Role")

    def test_contentless_stub_rows_are_reported_unrecoverable_not_repaired(self):
        """The 1,776 rows carrying only {"job_title": "Role"} have nothing
        to re-derive from -- they must be counted, not silently skipped."""
        self._insert("a", title="Role", payload={"job_title": "Role"})
        stats = bjc.backfill(self.db_path, apply_changes=True)

        self.assertEqual(stats["repaired"], 0)
        self.assertEqual(stats["unrecoverable"], 1)

    def test_unparseable_json_does_not_crash_the_run(self):
        self._insert("a", metadata_json="{not json", raw_text="also not json")
        self._insert("b", payload=EVALUATED_JD)
        stats = bjc.backfill(self.db_path, apply_changes=True)

        self.assertEqual(stats["repaired"], 1)
        self.assertEqual(self._fetch("b")["title"], "Lifecycle Marketing Manager")

    def test_healthy_rows_are_left_entirely_alone(self):
        self._insert("a", title="Real Title", company="Real Co", final_score=3.0)
        stats = bjc.backfill(self.db_path, apply_changes=True)

        self.assertEqual(stats["repaired"], 0)
        self.assertEqual(stats["unrecoverable"], 0)


class TestUpsertJobReadsBothKeySpellings(unittest.TestCase):
    """The writer-side fix. Reading only title/company/final_score is what
    produced the damage the backfill above repairs."""

    def test_scraped_jd_keys_populate_the_top_level_columns(self):
        with tempfile.TemporaryDirectory() as tmp:
            db_path = os.path.join(tmp, "data.db")
            conn = _make_db(db_path)

            db.upsert_job(dict(EVALUATED_JD, id="a"), conn=conn)

            conn.row_factory = sqlite3.Row
            row = conn.execute("SELECT * FROM jobs WHERE id = 'a'").fetchone()
            conn.close()

        self.assertEqual(row["title"], "Lifecycle Marketing Manager")
        self.assertEqual(row["company"], "Rula")
        self.assertAlmostEqual(row["final_score"], 4.55)
        self.assertAlmostEqual(row["capability_score"], 4.2)
        self.assertAlmostEqual(row["recruiter_score"], 3.9)

    def test_normalized_keys_still_win_over_the_scraped_spelling(self):
        with tempfile.TemporaryDirectory() as tmp:
            db_path = os.path.join(tmp, "data.db")
            conn = _make_db(db_path)

            db.upsert_job(
                {
                    "id": "a",
                    "title": "Normalized",
                    "job_title": "Scraped",
                    "company": "NormalizedCo",
                    "company_name": "ScrapedCo",
                },
                conn=conn,
            )

            conn.row_factory = sqlite3.Row
            row = conn.execute("SELECT * FROM jobs WHERE id = 'a'").fetchone()
            conn.close()

        self.assertEqual(row["title"], "Normalized")
        self.assertEqual(row["company"], "NormalizedCo")


class TestRealProfileWriteGuard(unittest.TestCase):
    """Dozens of tests reach upsert_job incidentally and none assert on the
    row, so unguarded they appended "Test"/"Role" @ "Acme Corp" rows to the
    developer's own data.db on every run. The guard drops those writes."""

    def test_write_into_the_real_profiles_dir_is_dropped_under_test(self):
        import profile_paths

        real_root = os.path.join(profile_paths.PROFILES_DIR, "testprofile")
        with patch.object(profile_paths, "profile_root", return_value=real_root):
            self.assertTrue(db._is_unisolated_test_write())
            # No connection is opened at all, so this cannot touch the file.
            self.assertIsNone(db.upsert_job({"id": "guard", "job_title": "Test"}))

    def test_write_into_an_isolated_temp_profile_is_allowed(self):
        import profile_paths

        with tempfile.TemporaryDirectory() as tmp:
            with patch.object(profile_paths, "profile_root", return_value=tmp):
                self.assertFalse(db._is_unisolated_test_write())
                db.upsert_job({"id": "ok", "job_title": "Real", "company_name": "Co"})

                conn = sqlite3.connect(os.path.join(tmp, "data.db"))
                conn.row_factory = sqlite3.Row
                row = conn.execute("SELECT * FROM jobs WHERE id='ok'").fetchone()
                conn.close()

        self.assertEqual(row["title"], "Real")

    def test_an_explicit_connection_still_writes(self):
        """Callers that pass their own conn -- including the backfill and
        migration paths -- are already pointed at a specific database and
        must not be silently no-opped."""
        import profile_paths

        real_root = os.path.join(profile_paths.PROFILES_DIR, "testprofile")
        with tempfile.TemporaryDirectory() as tmp:
            conn = _make_db(os.path.join(tmp, "data.db"))
            with patch.object(profile_paths, "profile_root", return_value=real_root):
                db.upsert_job({"id": "x", "job_title": "Kept"}, conn=conn)

            conn.row_factory = sqlite3.Row
            row = conn.execute("SELECT * FROM jobs WHERE id='x'").fetchone()
            conn.close()

        self.assertEqual(row["title"], "Kept")


if __name__ == "__main__":
    unittest.main()
