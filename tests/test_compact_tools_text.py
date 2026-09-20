"""The tool ledger reaches prompts as names grouped by employer, not whole
entries -- a large ledger serialized whole put every call over quota."""

import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))

from rewrite_bullets import compact_tools_text  # noqa: E402

TOOLS = [
    {
        "id": "tool_001",
        "name": "Airtable",
        "employer": "Corner Bakery",
        "category": "Ops",
        "confidence": "Expert",
        "use_notes": "long note " * 20,
        "tr_references": ["a.md", "b.md"],
    },
    {"id": "tool_002", "name": "Figma", "employer": "Corner Bakery"},
    {"id": "tool_003", "name": "airtable", "employer": "Corner Bakery"},
    {"id": "tool_004", "name": "Airtable", "employer": "Harbor Books"},
    {"id": "tool_005", "name": "Notion"},
    {"id": "tool_006", "name": "  "},
    "not-a-dict",
]


class TestCompactToolsText(unittest.TestCase):
    def test_groups_names_by_employer(self):
        text = compact_tools_text(TOOLS)
        self.assertIn("Corner Bakery: Airtable, Figma", text)
        self.assertIn("Harbor Books: Airtable", text)
        self.assertIn("Any employer: Notion", text)

    def test_drops_everything_but_the_name(self):
        text = compact_tools_text(TOOLS)
        for noise in ("tool_001", "Expert", "long note", "a.md", "Ops"):
            self.assertNotIn(noise, text)

    def test_dedupes_case_insensitively_within_an_employer(self):
        line = [
            l
            for l in compact_tools_text(TOOLS).splitlines()
            if l.startswith("Corner Bakery")
        ][0]
        self.assertEqual(line.lower().count("airtable"), 1)

    def test_empty_ledger_is_empty_text(self):
        self.assertEqual(compact_tools_text([]), "")
        self.assertEqual(compact_tools_text(None), "")


if __name__ == "__main__":
    unittest.main()
