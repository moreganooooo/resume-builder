"""Tests pinning down skills_menu.py's Ctrl+C/Esc cancellation behavior
(F17, docs/review/master_audit_document.md) -- direct reading confirmed
_add_skill() already guards every questionary...ask() call with an
`is None`/falsy check that returns early, so these tests exist to pin
that correct behavior down against regression, not to fix a bug."""

import os
import shutil
import sys
import tempfile
import unittest
from unittest.mock import patch

SCRIPTS_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts"
)
sys.path.insert(0, SCRIPTS_DIR)

import skills_menu  # noqa: E402


class TestSkillsScreenRobustness(unittest.TestCase):
    def test_null_category_and_name_do_not_crash_the_dashboard(self):
        # A key that is PRESENT but null made sorted() compare None with
        # str and raised TypeError, taking the whole Skills screen down.
        tools = [
            {"id": "tool_001", "name": None, "category": None, "confidence": "Expert"},
            {
                "id": "tool_002",
                "name": "Asana",
                "category": "PM",
                "confidence": "Expert",
            },
        ]
        skills_menu._display_skills_dashboard(tools)

    @patch("skills_menu._pause")
    @patch("skills_menu._load_dismissed_skills", return_value=[])
    def test_empty_dismissed_list_message_pauses(self, _load, mock_pause):
        # The loop redraw erased this message the instant it printed.
        skills_menu._manage_dismissed_skills()
        mock_pause.assert_called_once()


class TestAddSkillCancellation(unittest.TestCase):
    """questionary's convention: .ask() returns None on Ctrl+C/Esc rather
    than raising. Each prompt in _add_skill() must treat that as a clean
    cancel -- nothing partially written to the tools list."""

    def setUp(self):
        # _add_skill() ends by calling _save_verified_tools(), which writes
        # the WHOLE dict it was handed. These tests pass {"tools": []}, so
        # an unredirected save replaced the developer's real
        # verified_tools.json with a single "ChatGPT" entry -- on every
        # full test run. That is literally how the live profile's tools
        # ledger came to hold exactly one tool.
        self._tmpdir = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self._tmpdir, ignore_errors=True)

        patcher = patch.object(
            skills_menu,
            "_get_verified_tools_path",
            return_value=os.path.join(self._tmpdir, "verified_tools.json"),
        )
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_cancel_at_name_prompt_writes_nothing(self):
        with patch("questionary.text") as mock_text:
            mock_text.return_value.ask.return_value = None
            data = {"tools": []}
            skills_menu._add_skill(data)
            self.assertEqual(data["tools"], [])

    def test_cancel_at_category_prompt_writes_nothing(self):
        # Category is now cli_art.text() too (no cli_art/charm_prompt
        # autocomplete equivalent to questionary.autocomplete()) -- it's
        # the second .text().ask() call, right after name.
        with patch("questionary.text") as mock_text:
            mock_text.return_value.ask.side_effect = ["ChatGPT", None]
            data = {"tools": []}
            skills_menu._add_skill(data)
            self.assertEqual(data["tools"], [])

    def test_cancel_at_confidence_prompt_writes_nothing(self):
        with (
            patch("questionary.text") as mock_text,
            patch("questionary.select") as mock_select,
        ):
            mock_text.return_value.ask.side_effect = ["ChatGPT", "AI Tools"]
            mock_select.return_value.ask.return_value = None
            data = {"tools": []}
            skills_menu._add_skill(data)
            self.assertEqual(data["tools"], [])

    def test_cancel_at_evidence_count_prompt_writes_nothing(self):
        with (
            patch("questionary.text") as mock_text,
            patch("questionary.select") as mock_select,
        ):
            mock_select.return_value.ask.return_value = "Expert"
            # name, category, evidence count.
            mock_text.return_value.ask.side_effect = ["ChatGPT", "AI Tools", None]
            data = {"tools": []}
            skills_menu._add_skill(data)
            self.assertEqual(data["tools"], [])

    def test_cancel_at_use_notes_prompt_writes_nothing(self):
        with (
            patch("questionary.text") as mock_text,
            patch("questionary.select") as mock_select,
        ):
            mock_select.return_value.ask.return_value = "Expert"
            # name, category, evidence_count, use_notes
            mock_text.return_value.ask.side_effect = [
                "ChatGPT",
                "AI Tools",
                "3",
                None,
            ]
            data = {"tools": []}
            skills_menu._add_skill(data)
            self.assertEqual(data["tools"], [])

    def test_cancel_at_references_prompt_writes_nothing(self):
        with (
            patch("questionary.text") as mock_text,
            patch("questionary.select") as mock_select,
        ):
            mock_select.return_value.ask.return_value = "Expert"
            # name, category, evidence_count, use_notes, tr_references
            mock_text.return_value.ask.side_effect = [
                "ChatGPT",
                "AI Tools",
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
            patch("questionary.select") as mock_select,
        ):
            mock_select.return_value.ask.return_value = "Expert"
            mock_text.return_value.ask.side_effect = [
                "ChatGPT",
                "AI Tools",
                "3",
                "Used it daily",
                "profile.yml",
            ]
            data = {"tools": []}
            skills_menu._add_skill(data)
            self.assertEqual(len(data["tools"]), 1)
            self.assertEqual(data["tools"][0]["name"], "ChatGPT")


class TestSkillsMenuFullSuite(unittest.TestCase):
    """Unit tests for helpers and menu actions in skills_menu."""

    def test_generate_next_id(self):
        """Test generating next sequential tool ID."""
        tools = [{"id": "tool_001"}, {"id": "tool_005"}, {"id": "custom_id"}]
        self.assertEqual(skills_menu._generate_next_id(tools), "tool_006")
        self.assertEqual(skills_menu._generate_next_id([]), "tool_001")

    @patch("skills_menu._get_verified_tools_path")
    def test_load_and_save_verified_tools(self, mock_path):
        """Test loading non-existent, corrupt, and valid verified_tools.json."""
        import tempfile

        with tempfile.TemporaryDirectory() as tmpdir:
            file_path = os.path.join(tmpdir, "verified_tools.json")
            mock_path.return_value = file_path

            # Missing file loads default skeleton
            data = skills_menu._load_verified_tools()
            self.assertEqual(data["tools"], [])

            # A corrupt file must RAISE, not degrade to an empty skeleton.
            # The caller edits whatever it gets back and saves it over the
            # same path, so returning {"tools": []} for an unreadable file
            # would silently delete every tool in the ledger.
            with open(file_path, "w", encoding="utf-8") as f:
                f.write("invalid json")
            with self.assertRaises(Exception):
                skills_menu._load_verified_tools()

            # ...and the unreadable file is still on disk, unmodified.
            with open(file_path, encoding="utf-8") as f:
                self.assertEqual(f.read(), "invalid json")

            os.remove(file_path)
            data = skills_menu._load_verified_tools()

            # Saving data writes valid JSON
            data["tools"].append(
                {"id": "tool_001", "name": "Python", "category": "Languages"}
            )
            success = skills_menu._save_verified_tools(data)
            self.assertTrue(success)

            loaded = skills_menu._load_verified_tools()
            self.assertEqual(len(loaded["tools"]), 1)
            self.assertEqual(loaded["tools"][0]["name"], "Python")

    def test_display_skills_dashboard(self):
        """Test dashboard display formatter."""
        tools = [
            {"name": "Python", "category": "Languages", "confidence": "Expert"},
            {"name": "Docker", "category": "DevOps", "confidence": "Advanced"},
            {"name": "Bash", "confidence": "Proficient"},  # Uncategorized
        ]
        skills_menu._display_skills_dashboard(tools)

    @patch("skills_menu._save_verified_tools", return_value=True)
    def test_add_skill_success(self, mock_save):
        """Test successfully adding a skill with all inputs."""
        with (
            patch("questionary.text") as mock_text,
            patch("questionary.select") as mock_select,
        ):
            mock_text.return_value.ask.side_effect = [
                "Tableau",
                "Analytics",
                "5",
                "Built enterprise reports",
                "TR-001, TR-002",
            ]
            mock_select.return_value.ask.return_value = "Advanced"

            data = {"tools": []}
            skills_menu._add_skill(data)
            self.assertEqual(len(data["tools"]), 1)
            self.assertEqual(data["tools"][0]["name"], "Tableau")
            self.assertEqual(data["tools"][0]["category"], "Analytics")
            self.assertEqual(data["tools"][0]["evidence_count"], 5)
            self.assertEqual(data["tools"][0]["tr_references"], ["TR-001", "TR-002"])

    @patch("skills_menu._save_verified_tools", return_value=True)
    def test_edit_skill_success_and_not_found(self, mock_save):
        """Test editing an existing skill and handling non-existent ID."""
        data = {
            "tools": [
                {
                    "id": "tool_001",
                    "name": "OldName",
                    "category": "OldCat",
                    "confidence": "Familiar",
                    "evidence_count": 1,
                    "use_notes": "None",
                    "tr_references": [],
                }
            ]
        }
        # Non-existent ID
        skills_menu._edit_skill(data, "tool_999")

        # Successful edit
        with (
            patch("questionary.text") as mock_text,
            patch("questionary.select") as mock_select,
        ):
            mock_text.return_value.ask.side_effect = [
                "NewName",
                "NewCat",
                "4",
                "Extensive work",
                "TR-003",
            ]
            mock_select.return_value.ask.return_value = "Expert"

            skills_menu._edit_skill(data, "tool_001")
            self.assertEqual(data["tools"][0]["name"], "NewName")
            self.assertEqual(data["tools"][0]["category"], "NewCat")
            self.assertEqual(data["tools"][0]["confidence"], "Expert")

    @patch("skills_menu._save_verified_tools", return_value=True)
    @patch("cli_art.confirm", return_value=True)
    def test_delete_skill(self, mock_confirm, mock_save):
        """Test deleting a skill with confirmation."""
        data = {"tools": [{"id": "tool_001", "name": "Python"}]}
        skills_menu._delete_skill(data, "tool_001")
        self.assertEqual(data["tools"], [])

        # Non-existent ID
        skills_menu._delete_skill(data, "tool_999")

    @patch("cli_art.select")
    @patch("skills_menu._edit_skill")
    @patch("skills_menu._delete_skill")
    @patch("skills_menu._load_verified_tools")
    def test_view_skill_details(self, mock_load, mock_delete, mock_edit, mock_select):
        """Test viewing skill details with edit/delete/back actions."""
        data = {
            "tools": [
                {
                    "id": "tool_001",
                    "name": "Python",
                    "category": "Dev",
                    "confidence": "Expert",
                    "evidence_count": 5,
                    "use_notes": "Notes",
                    "tr_references": ["TR-001"],
                }
            ]
        }
        mock_load.return_value = data

        # Non-existent
        skills_menu._view_skill_details(data, "tool_999")

        # Action: edit then back
        mock_select.side_effect = ["edit", "back"]
        skills_menu._view_skill_details(data, "tool_001")
        mock_edit.assert_called_once()

        # Action: delete
        mock_select.side_effect = ["delete"]
        skills_menu._view_skill_details(data, "tool_001")
        mock_delete.assert_called_once()

    @patch("cli_art.select")
    @patch("skills_menu._load_verified_tools")
    @patch("skills_menu._add_skill")
    @patch("skills_menu._view_skill_details")
    @patch("menu._should_use_alt_screen", return_value=False)
    def test_run_skills_menu_flow(
        self, mock_alt, mock_view, mock_add, mock_load, mock_select
    ):
        """Test full menu loop navigation: add, select, back."""
        data = {
            "tools": [
                {
                    "id": "tool_001",
                    "name": "Python",
                    "category": "Dev",
                    "confidence": "Expert",
                }
            ]
        }
        mock_load.return_value = data

        # Select add_skill, then select_skill, then back
        mock_select.side_effect = ["add_skill", "select_skill", "tool_001", "back"]
        skills_menu.run_skills_menu()
        mock_add.assert_called_once()
        mock_view.assert_called_once_with(data, "tool_001")

    @patch(
        "skills_menu._get_verified_tools_path",
        return_value="/nonexistent/path/dir/file.json",
    )
    def test_save_verified_tools_exception(self, mock_path):
        """Test save_verified_tools handles disk write errors gracefully."""
        res = skills_menu._save_verified_tools({"tools": []})
        self.assertFalse(res)

    def test_edit_skill_validation_and_cancellation(self):
        """Test edit_skill returns early on empty name, empty category, or empty confidence."""
        data = {
            "tools": [
                {
                    "id": "tool_001",
                    "name": "Python",
                    "category": "Dev",
                    "confidence": "Expert",
                }
            ]
        }

        with patch("questionary.text") as mock_text:
            mock_text.return_value.ask.return_value = ""
            skills_menu._edit_skill(data, "tool_001")
            self.assertEqual(data["tools"][0]["name"], "Python")

        # Cancel at category -- now the second .text().ask() call (no
        # cli_art/charm_prompt autocomplete equivalent to
        # questionary.autocomplete(), so category went through cli_art.text()).
        with patch("questionary.text") as mock_text:
            mock_text.return_value.ask.side_effect = ["Python 3", None]
            skills_menu._edit_skill(data, "tool_001")
            self.assertEqual(data["tools"][0]["name"], "Python")

        # Cancel at confidence
        with (
            patch("questionary.text") as mock_text,
            patch("questionary.select") as mock_select,
        ):
            mock_text.return_value.ask.side_effect = ["Python 3", "Dev"]
            mock_select.return_value.ask.return_value = None
            skills_menu._edit_skill(data, "tool_001")
            self.assertEqual(data["tools"][0]["name"], "Python")

        # Cancel at evidence_count
        with (
            patch("questionary.text") as mock_text,
            patch("questionary.select") as mock_select,
        ):
            mock_text.return_value.ask.side_effect = ["Python 3", "Dev", None]
            mock_select.return_value.ask.return_value = "Expert"
            skills_menu._edit_skill(data, "tool_001")
            self.assertEqual(data["tools"][0]["name"], "Python")

        # Cancel at use_notes
        with (
            patch("questionary.text") as mock_text,
            patch("questionary.select") as mock_select,
        ):
            mock_text.return_value.ask.side_effect = ["Python 3", "Dev", "2", None]
            mock_select.return_value.ask.return_value = "Expert"
            skills_menu._edit_skill(data, "tool_001")
            self.assertEqual(data["tools"][0]["name"], "Python")

        # Cancel at tr_references
        with (
            patch("questionary.text") as mock_text,
            patch("questionary.select") as mock_select,
        ):
            mock_text.return_value.ask.side_effect = [
                "Python 3",
                "Dev",
                "2",
                "Notes",
                None,
            ]
            mock_select.return_value.ask.return_value = "Expert"
            skills_menu._edit_skill(data, "tool_001")
            self.assertEqual(data["tools"][0]["name"], "Python")


class TestDismissedSkills(unittest.TestCase):
    """skill_gap_scan.py's negative selector: skills marked "not my
    background" persist here so they never re-appear as gaps."""

    def setUp(self):
        self._tmpdir = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self._tmpdir, ignore_errors=True)

        patcher = patch.object(
            skills_menu,
            "_get_dismissed_skills_path",
            return_value=os.path.join(self._tmpdir, "dismissed_skills.json"),
        )
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_load_returns_empty_list_when_file_missing(self):
        self.assertEqual(skills_menu._load_dismissed_skills(), [])

    def test_save_then_load_round_trips_sorted_case_insensitively(self):
        self.assertTrue(skills_menu._save_dismissed_skills(["Kubernetes", "ansible"]))
        self.assertEqual(
            skills_menu._load_dismissed_skills(), ["ansible", "Kubernetes"]
        )

    def test_save_dedupes_and_drops_blank_entries(self):
        skills_menu._save_dismissed_skills(["Docker", "Docker", "  ", ""])
        self.assertEqual(skills_menu._load_dismissed_skills(), ["Docker"])

    def test_manage_dismissed_with_none_is_a_no_op(self):
        # Nothing dismissed yet -- should just report that and return,
        # never call the checkbox prompt.
        with patch("questionary.Choice") as mock_choice:
            skills_menu._manage_dismissed_skills()
            mock_choice.assert_not_called()

    def test_manage_dismissed_restores_selected_entries(self):
        skills_menu._save_dismissed_skills(["Docker", "Kubernetes"])
        with patch("cli_art.checkbox", return_value=["Docker"]):
            skills_menu._manage_dismissed_skills()
        self.assertEqual(skills_menu._load_dismissed_skills(), ["Kubernetes"])

    def test_manage_dismissed_cancel_leaves_list_untouched(self):
        skills_menu._save_dismissed_skills(["Docker"])
        with patch("cli_art.checkbox", return_value=None):
            skills_menu._manage_dismissed_skills()
        self.assertEqual(skills_menu._load_dismissed_skills(), ["Docker"])


if __name__ == "__main__":
    unittest.main()


class TestSkillsMaintenanceViews(unittest.TestCase):
    """The maintenance screens read a ledger with thousands of entries, so
    they summarize and group rather than printing it."""

    TOOLS = [
        {"id": "tool_001", "name": "Salesforce CRM", "category": "CRM"},
        {"id": "tool_002", "name": "salesforce crm", "category": "CRM"},
        {"id": "tool_003", "name": "Figma", "category": "Design"},
        {"id": "tool_004", "name": None, "category": None},
    ]

    def test_duplicate_names_are_case_insensitive(self):
        self.assertEqual(skills_menu._duplicate_names(self.TOOLS), ["salesforce crm"])

    def test_blank_names_are_never_counted_as_duplicates(self):
        self.assertEqual(
            skills_menu._duplicate_names([{"name": ""}, {"name": None}]), []
        )

    def test_null_category_groups_under_uncategorized(self):
        self.assertEqual(
            sorted(skills_menu._by_category(self.TOOLS)),
            ["CRM", "Design", "Uncategorized"],
        )

    def test_dashboard_summarizes_instead_of_listing_every_skill(self):
        with patch.object(skills_menu.cli_art.console, "print") as mock_print:
            skills_menu._display_skills_dashboard(self.TOOLS)
        out = "\n".join(str(c.args[0]) for c in mock_print.call_args_list if c.args)
        self.assertIn("4", out)  # the total
        self.assertIn("Remove Skills in Bulk", out)  # the duplicate hint
        self.assertNotIn("Figma", out)  # no per-skill rows

    def test_skill_label_marks_duplicates(self):
        dupes = set(skills_menu._duplicate_names(self.TOOLS))
        self.assertTrue(skills_menu._skill_label(self.TOOLS[0], dupes).startswith("⧉ "))
        self.assertFalse(
            skills_menu._skill_label(self.TOOLS[2], dupes).startswith("⧉ ")
        )

    @patch("skills_menu._pause")
    @patch("skills_menu._save_verified_tools", return_value=True)
    def test_bulk_remove_deletes_only_confirmed_selection(self, mock_save, _pause):
        data = {"tools": list(self.TOOLS)}
        with (
            patch.object(skills_menu.cli_art, "checkbox", return_value=["tool_002"]),
            patch.object(skills_menu.cli_art, "confirm", return_value=True),
        ):
            skills_menu._bulk_remove_skills(data)
        self.assertEqual(
            [t["id"] for t in data["tools"]], ["tool_001", "tool_003", "tool_004"]
        )
        mock_save.assert_called_once()

    @patch("skills_menu._pause")
    @patch("skills_menu._save_verified_tools", return_value=True)
    def test_bulk_remove_declined_confirmation_writes_nothing(self, mock_save, _pause):
        data = {"tools": list(self.TOOLS)}
        with (
            patch.object(skills_menu.cli_art, "checkbox", return_value=["tool_002"]),
            patch.object(skills_menu.cli_art, "confirm", return_value=False),
        ):
            skills_menu._bulk_remove_skills(data)
        self.assertEqual(len(data["tools"]), 4)
        mock_save.assert_not_called()

    @patch("skills_menu._save_verified_tools", return_value=True)
    def test_bulk_remove_cancelled_picker_writes_nothing(self, mock_save):
        data = {"tools": list(self.TOOLS)}
        with patch.object(skills_menu.cli_art, "checkbox", return_value=None):
            skills_menu._bulk_remove_skills(data)
        self.assertEqual(len(data["tools"]), 4)
        mock_save.assert_not_called()
