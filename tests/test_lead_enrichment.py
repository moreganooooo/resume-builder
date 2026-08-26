"""Unit tests for lead_enrichment.py."""

import os
import sqlite3
import sys
import tempfile
import unittest

SCRIPTS_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts"
)
if SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, SCRIPTS_DIR)

import db
from lead_enrichment import create_lead_placeholder, generate_outreach_dorks


class TestLeadEnrichment(unittest.TestCase):

    def setUp(self):
        self.tmp_dir = tempfile.TemporaryDirectory()
        self.db_path = os.path.join(self.tmp_dir.name, "data.db")
        self.conn = sqlite3.connect(self.db_path)
        self.conn.row_factory = sqlite3.Row
        db.init_db(self.conn)

    def tearDown(self):
        self.conn.close()
        self.tmp_dir.cleanup()

    def test_generate_outreach_dorks(self):
        dorks = generate_outreach_dorks("Stripe", "Staff Backend Engineer")
        self.assertIn("google.com/search", dorks["hiring_manager_search_url"])
        self.assertIn("Engineering Manager", dorks["hiring_manager_query"])
        self.assertIn("Technical Recruiter", dorks["recruiter_query"])
        self.assertIn("Staff Backend Engineer", dorks["peer_query"])

    def test_create_lead_placeholder(self):
        contact_id = create_lead_placeholder(
            company="Airbnb",
            role_type="Engineering Manager",
            name="Jane Doe",
            conn=self.conn,
        )
        self.assertTrue(bool(contact_id))
        contacts = db.get_contacts(conn=self.conn)
        self.assertEqual(len(contacts), 1)
        self.assertEqual(contacts[0]["company"], "Airbnb")
        self.assertEqual(contacts[0]["name"], "Jane Doe")


if __name__ == "__main__":
    unittest.main()
