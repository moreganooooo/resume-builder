"""Tests pinning down skills_menu.py's Ctrl+C/Esc cancellation behavior
(F17, docs/review/master_audit_document.md) -- direct reading confirmed
_add_skill() already guards every questionary...ask() call with an
`is None`/falsy check that returns early, so these tests exist to pin
that correct behavior down against regression, not to fix a bug."""

import os
import sys
import unittest
from unittest.mock import patch

SCRIPTS_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts"
)
sys.path.insert(0, SCRIPTS_DIR)

import skills_menu  # noqa: E402


class TestAddSkillCancellation(unittest.TestCase):
    """questionary's convention: .ask() returns None on Ctrl+C/Esc rather
    than raising. Each prompt in _add_skill() must treat that as a clean
    cancel -- nothing partially written to the tools list."""

    def test_cancel_at_name_prompt_writes_nothing(self):
        with patch("questionary.text") as mock_text:
            mock_text.return_value.ask.return_value = None
            data = {"tools": []}
            skills_menu._add_skill(data)
            self.assertEqual(data["tools"], [])

    def test_cancel_at_category_prompt_writes_nothing(self):
        with (
            patch("questionary.text") as mock_text,
            patch("questionary.autocomplete") as mock_autocomplete,
        ):
            mock_text.return_value.ask.return_value = "ChatGPT"
            mock_autocomplete.return_value.ask.return_value = None
            data = {"tools": []}
            skills_menu._add_skill(data)
            self.assertEqual(data["tools"], [])

    def test_cancel_at_confidence_prompt_writes_nothing(self):
        with (
            patch("questionary.text") as mock_text,
            patch("questionary.autocomplete") as mock_autocomplete,
            patch("questionary.select") as mock_select,
        ):
            mock_text.return_value.ask.return_value = "ChatGPT"
            mock_autocomplete.return_value.ask.return_value = "AI Tools"
            mock_select.return_value.ask.return_value = None
            data = {"tools": []}
            skills_menu._add_skill(data)
            self.assertEqual(data["tools"], [])

    def test_cancel_at_evidence_count_prompt_writes_nothing(self):
        with (
            patch("questionary.text") as mock_text,
            patch("questionary.autocomplete") as mock_autocomplete,
            patch("questionary.select") as mock_select,
        ):
            mock_autocomplete.return_value.ask.return_value = "AI Tools"
            mock_select.return_value.ask.return_value = "Expert"
            # First .text().ask() call is the name, second is evidence count.
            mock_text.return_value.ask.side_effect = ["ChatGPT", None]
            data = {"tools": []}
            skills_menu._add_skill(data)
            self.assertEqual(data["tools"], [])

    def test_cancel_at_use_notes_prompt_writes_nothing(self):
        with (
            patch("questionary.text") as mock_text,
            patch("questionary.autocomplete") as mock_autocomplete,
            patch("questionary.select") as mock_select,
        ):
            mock_autocomplete.return_value.ask.return_value = "AI Tools"
            mock_select.return_value.ask.return_value = "Expert"
            # name, evidence_count, use_notes
            mock_text.return_value.ask.side_effect = ["ChatGPT", "3", None]
            data = {"tools": []}
            skills_menu._add_skill(data)
            self.assertEqual(data["tools"], [])

    def test_cancel_at_references_prompt_writes_nothing(self):
        with (
            patch("questionary.text") as mock_text,
            patch("questionary.autocomplete") as mock_autocomplete,
            patch("questionary.select") as mock_select,
        ):
            mock_autocomplete.return_value.ask.return_value = "AI Tools"
            mock_select.return_value.ask.return_value = "Expert"
            # name, evidence_count, use_notes, tr_references
            mock_text.return_value.ask.side_effect = [
                "ChatGPT",
                "3",
                "Used it daily",
                None,
            ]
            data = {"tools": []}
            skills_menu._add_skill(data)
            self.assertEqual(data["tools"], [])

    def test_completing_every_prompt_does_add_a_tool(self):
        """Sanity check the mocking approach itself is correct -- if every
        prompt is answered, a tool really does get appended."""
        with (
            patch("questionary.text") as mock_text,
            patch("questionary.autocomplete") as mock_autocomplete,
            patch("questionary.select") as mock_select,
        ):
            mock_autocomplete.return_value.ask.return_value = "AI Tools"
            mock_select.return_value.ask.return_value = "Expert"
            mock_text.return_value.ask.side_effect = [
                "ChatGPT",
                "3",
                "Used it daily",
                "profile.yml",
            ]
            data = {"tools": []}
            skills_menu._add_skill(data)
            self.assertEqual(len(data["tools"]), 1)
            self.assertEqual(data["tools"][0]["name"], "ChatGPT")


if __name__ == "__main__":
    unittest.main()
