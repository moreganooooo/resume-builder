"""Unit tests for negotiate.py."""

import os
import tempfile
import unittest

from scripts import negotiate


class TestNegotiate(unittest.TestCase):
    def test_build_negotiation_strategy_close_gap(self):
        res = negotiate.build_negotiation_strategy(
            offer_base=160000,
            target_base=180000,
            company="Airbnb",
            role="Staff Designer",
            competing_offers=1,
        )
        self.assertEqual(res["company"], "Airbnb")
        self.assertEqual(res["initial_offer"], 160000)
        self.assertEqual(res["target_base"], 180000)
        self.assertGreaterEqual(res["recommended_counter"], 180000)
        self.assertIn("competing", res["strategy"])
        self.assertIn("185,000", res["email_script"])

    def test_generate_and_write_negotiation_guide(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".md", delete=False) as f:
            temp_path = f.name

        try:
            strategy = negotiate.build_negotiation_strategy(
                offer_base=200000,
                target_base=200000,
                company="Netflix",
                role="Senior SRE",
            )
            out_file = negotiate.write_negotiation_playbook(strategy, temp_path)
            self.assertEqual(out_file, temp_path)
            self.assertTrue(os.path.exists(temp_path))
            with open(temp_path, "r", encoding="utf-8") as f:
                content = f.read()
                self.assertIn("Compensation Negotiation Playbook", content)
                self.assertIn("Netflix", content)
        finally:
            if os.path.exists(temp_path):
                os.remove(temp_path)


if __name__ == "__main__":
    unittest.main()
