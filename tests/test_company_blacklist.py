"""Unit tests for company_blacklist.py."""

import json
import os
import tempfile
import unittest

from scripts import company_blacklist


class TestCompanyBlacklist(unittest.TestCase):
    def test_default_blacklisted_companies(self):
        is_bl, reason = company_blacklist.is_blacklisted("Revature Inc.")
        self.assertTrue(is_bl)
        self.assertIn("lock-in", reason.lower())

        is_bl, reason = company_blacklist.is_blacklisted("Crossover for Work LLC")
        self.assertTrue(is_bl)

        is_bl, reason = company_blacklist.is_blacklisted("Google LLC")
        self.assertFalse(is_bl)
        self.assertIsNone(reason)

    def test_custom_blacklist_json_dict(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump({"Acme Scam Co": "Fake recruiter spam"}, f)
            temp_path = f.name

        try:
            is_bl, reason = company_blacklist.is_blacklisted(
                "Acme Scam Co", custom_path=temp_path
            )
            self.assertTrue(is_bl)
            self.assertEqual(reason, "Fake recruiter spam")
        finally:
            if os.path.exists(temp_path):
                os.remove(temp_path)

    def test_custom_blacklist_json_list(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump(["SpamCorp", "BogusJobs Inc"], f)
            temp_path = f.name

        try:
            is_bl, reason = company_blacklist.is_blacklisted(
                "SpamCorp LLC", custom_path=temp_path
            )
            self.assertTrue(is_bl)
            self.assertEqual(reason, "User blacklisted")
        finally:
            if os.path.exists(temp_path):
                os.remove(temp_path)

    def test_empty_or_none_company(self):
        is_bl, reason = company_blacklist.is_blacklisted("")
        self.assertFalse(is_bl)
        self.assertIsNone(reason)


if __name__ == "__main__":
    unittest.main()
