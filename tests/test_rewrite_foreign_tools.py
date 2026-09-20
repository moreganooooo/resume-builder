"""A bullet rewrite may not borrow a tool from another employer's work."""

import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))

from rewrite_bullets import build_tool_employer_index, foreign_tools  # noqa: E402

BANK = [
    ("Cleaned 4,000 Salesforce records before a territory handoff", "Harbor Books"),
    ("Recorded Vidyard videos for renewal outreach", "Harbor Books"),
    ("Wrote seasonal menu copy in Canva", "Corner Bakery"),
    ("Tracked data quality issues weekly", "Corner Bakery"),
]


class TestForeignTools(unittest.TestCase):
    def setUp(self):
        self.index = build_tool_employer_index(
            ["Salesforce CRM", "Vidyard", "Canva", "data quality"], BANK
        )

    def test_index_strips_category_suffix_and_skips_concepts(self):
        self.assertEqual(self.index["Salesforce"], {"Harbor Books"})
        self.assertNotIn("data quality", self.index)

    def test_rejects_a_tool_only_another_employer_used(self):
        stray = foreign_tools(
            "Built a Salesforce-synced menu tracker",
            "Wrote menu copy",
            "Corner Bakery",
            self.index,
        )
        self.assertEqual(stray, {"Salesforce"})

    def test_allows_the_employers_own_tools(self):
        self.assertEqual(
            foreign_tools("Scripted Vidyard videos", "", "Harbor Books", self.index),
            set(),
        )

    def test_allows_a_tool_already_in_the_original(self):
        self.assertEqual(
            foreign_tools(
                "Synced Salesforce leads",
                "Logged leads in Salesforce",
                "Corner Bakery",
                self.index,
            ),
            set(),
        )

    def test_matches_employer_name_variants(self):
        self.assertEqual(
            foreign_tools(
                "Designed Canva flyers", "", "Corner Bakery / Cafe", self.index
            ),
            set(),
        )


if __name__ == "__main__":
    unittest.main()
