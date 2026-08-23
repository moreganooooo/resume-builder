"""Most pending jobs live only in data.db, with no JD file. Every
dashboard action took a jd_path, so those jobs were visible and inert.
jd_source resolves an identifier to something the file-oriented pipeline
can use, without writing ~1,200 JD files to a space-constrained disk.
"""

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

import db  # noqa: E402
import jd_manager  # noqa: E402
import jd_source  # noqa: E402
import profile_paths  # noqa: E402

PAYLOAD = {
    "job_title": "Lifecycle Marketing Manager",
    "company_name": "Rula",
    "description": "Own the lifecycle program.",
    "_evaluation": {"composite_score": 4.55},
}


class JDSourceTestCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        profiles_dir = os.path.join(self.tmp, "profiles")
        os.makedirs(os.path.join(profiles_dir, "testprofile"), exist_ok=True)

        # JDS_ROOT/OUTPUT_ROOT/DATA_ROOT as well as PROFILES_DIR: patching
        # jd_manager.JDS_DIR only redirects that one module-level constant,
        # so anything calling profile_paths.jds_dir() fresh still resolved
        # into the real checkout and created jds/testprofile there.
        for patcher in (
            patch.object(profile_paths, "PROFILES_DIR", profiles_dir),
            patch.object(profile_paths, "JDS_ROOT", os.path.join(self.tmp, "jds")),
            patch.object(
                profile_paths, "OUTPUT_ROOT", os.path.join(self.tmp, "output")
            ),
            patch.object(profile_paths, "DATA_ROOT", os.path.join(self.tmp, "data")),
            patch.dict(os.environ, {"RESUME_PROFILE": "testprofile"}),
            patch.object(jd_manager, "JDS_DIR", os.path.join(self.tmp, "jds")),
        ):
            patcher.start()
            self.addCleanup(patcher.stop)

        os.makedirs(jd_manager.JDS_DIR, exist_ok=True)

        conn = db.get_db()
        with conn:
            conn.execute(
                "INSERT INTO jobs (id, title, company, status, raw_text, metadata_json)"
                " VALUES (?, ?, ?, ?, ?, ?)",
                (
                    "abc123hash",
                    "Lifecycle Marketing Manager",
                    "Rula",
                    "pending",
                    "{}",
                    json.dumps(PAYLOAD),
                ),
            )
        conn.close()


class TestResolvedJD(JDSourceTestCase):

    def test_existing_file_resolves_to_itself_untouched(self):
        path = os.path.join(self.tmp, "real.json")
        with open(path, "w", encoding="utf-8") as f:
            json.dump(PAYLOAD, f)

        with jd_source.resolved_jd(path) as (resolved, is_db):
            self.assertEqual(resolved, path)
            self.assertFalse(is_db)

        self.assertTrue(os.path.exists(path), "a real JD must not be deleted")

    def test_database_id_materializes_a_readable_jd(self):
        with jd_source.resolved_jd("abc123hash") as (resolved, is_db):
            self.assertTrue(is_db)
            with open(resolved, encoding="utf-8") as f:
                data = json.load(f)

        self.assertEqual(data["job_title"], "Lifecycle Marketing Manager")
        self.assertEqual(data["company_name"], "Rula")
        self.assertEqual(data["description"], "Own the lifecycle program.")

    def test_temp_file_is_removed_afterwards(self):
        with jd_source.resolved_jd("abc123hash") as (resolved, _):
            temp_path = resolved
            self.assertTrue(os.path.exists(temp_path))

        self.assertFalse(os.path.exists(temp_path), "temp JD leaked onto disk")

    def test_temp_file_is_removed_even_when_the_action_raises(self):
        with self.assertRaises(ValueError):
            with jd_source.resolved_jd("abc123hash") as (resolved, _):
                temp_path = resolved
                raise ValueError("action blew up")

        self.assertFalse(os.path.exists(temp_path))

    def test_unknown_identifier_raises_lookup_error(self):
        with self.assertRaises(LookupError):
            with jd_source.resolved_jd("nope-not-a-job"):
                pass

    def test_changes_are_synced_back_into_the_database(self):
        """Without sync-back, an action's work would be discarded along
        with the temp file."""
        with jd_source.resolved_jd("abc123hash") as (resolved, _):
            jd_manager.save_application_status(resolved, "Applied")

        conn = db.get_db()
        row = conn.execute(
            "SELECT metadata_json FROM jobs WHERE id = 'abc123hash'"
        ).fetchone()
        conn.close()

        self.assertIn("Applied", row[0])

    def test_sync_back_tolerates_a_moved_file(self):
        """run_pipeline moves a JD into completed/ on success, so the temp
        path is legitimately gone by exit time."""
        with jd_source.resolved_jd("abc123hash") as (resolved, _):
            os.remove(resolved)  # simulate the pipeline moving it away
        # Reaching here without raising is the assertion.


class TestMaterializePermanently(JDSourceTestCase):

    def test_writes_a_real_jd_file_into_the_jds_dir(self):
        path = jd_source.materialize_permanently("abc123hash")

        self.assertTrue(os.path.exists(path))
        self.assertEqual(os.path.dirname(path), jd_manager.JDS_DIR)
        with open(path, encoding="utf-8") as f:
            self.assertEqual(json.load(f)["company_name"], "Rula")

    def test_repeated_calls_do_not_clobber(self):
        first = jd_source.materialize_permanently("abc123hash")
        second = jd_source.materialize_permanently("abc123hash")

        self.assertNotEqual(first, second)
        self.assertTrue(os.path.exists(first))

    def test_unknown_id_raises(self):
        with self.assertRaises(LookupError):
            jd_source.materialize_permanently("nope")


class TestSetStatus(JDSourceTestCase):

    def test_status_is_updated_in_place(self):
        jd_source.set_status("abc123hash", "archived")

        conn = db.get_db()
        row = conn.execute("SELECT status FROM jobs WHERE id = 'abc123hash'").fetchone()
        conn.close()

        self.assertEqual(row[0], "archived")

    def test_archiving_a_database_job_writes_no_file(self):
        """Routing this through jd_manager.archive_jd would move a temp
        file into jds/archived/, creating exactly the clutter jd_source
        exists to avoid."""
        before = set(os.listdir(jd_manager.JDS_DIR))

        jd_source.set_status("abc123hash", "archived")

        self.assertEqual(set(os.listdir(jd_manager.JDS_DIR)), before)


if __name__ == "__main__":
    unittest.main()
