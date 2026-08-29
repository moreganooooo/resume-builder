import json
import os
import sys
import tempfile
import unittest
from unittest.mock import MagicMock, patch

SCRIPTS_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts"
)
sys.path.insert(0, SCRIPTS_DIR)

import orchestrator  # noqa: E402
import skills_menu  # noqa: E402


class TestInteractiveSkillsGap(unittest.TestCase):
    def test_find_unverified_jd_skill_gaps_identifies_missing(self):
        jd_keywords = {
            "tools": ["HubSpot", "Claude", "Asana"],
            "hard_skills": ["CRM Architecture", "Cybersecurity"],
        }
        verified_tools_data = {
            "tools": [
                {"name": "HubSpot", "employer": "Mercor"},
                {"name": "Salesforce", "employer": "Mercor"},
            ]
        }
        profile_data = {
            "skills": {
                "CRM": ["CRM Architecture"],
            }
        }
        gaps = orchestrator.find_unverified_jd_skill_gaps(
            jd_keywords, verified_tools_data, profile_data
        )
        self.assertIn("Claude", gaps)
        self.assertIn("Asana", gaps)
        self.assertIn("Cybersecurity", gaps)
        self.assertNotIn("HubSpot", gaps)
        self.assertNotIn("CRM Architecture", gaps)

    def test_find_unverified_jd_skill_gaps_case_insensitive(self):
        jd_keywords = {"tools": ["hubspot", "SALESFORCE"]}
        verified_tools_data = {
            "tools": [
                {"name": "HubSpot"},
                {"name": "Salesforce CRM"},
            ]
        }
        gaps = orchestrator.find_unverified_jd_skill_gaps(
            jd_keywords, verified_tools_data, {}
        )
        self.assertEqual(len(gaps), 0)

    def test_confirm_jd_skill_gaps_is_inert_under_unittest_guard(self):
        jd_keywords = {"tools": ["Claude", "Asana"]}
        checkpoint = {}
        # In unit tests, sys.modules contains 'unittest', so it must short-circuit without prompting
        result = orchestrator.confirm_jd_skill_gaps_interactively(
            jd_keywords, checkpoint=checkpoint, job_key="test_job"
        )
        self.assertEqual(result, [])
        self.assertEqual(checkpoint.get("confirmed_skill_gaps"), [])

    def test_confirm_jd_skill_gaps_resumes_from_checkpoint(self):
        jd_keywords = {"tools": ["Claude", "Asana"]}
        checkpoint = {"confirmed_skill_gaps": ["Claude"]}
        # When resuming, it must return the checkpointed list directly
        result = orchestrator.confirm_jd_skill_gaps_interactively(
            jd_keywords, checkpoint=checkpoint, job_key="test_job"
        )
        self.assertEqual(result, ["Claude"])

    def test_confirm_jd_skill_gaps_atomic_write_path(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            tools_path = os.path.join(tmpdir, "verified_tools.json")
            initial_data = {
                "_meta": {"total_entries": 1},
                "tools": [{"id": "tool_001", "name": "HubSpot"}],
            }
            with open(tools_path, "w", encoding="utf-8") as f:
                json.dump(initial_data, f)

            jd_keywords = {"tools": ["Claude", "Asana"]}
            checkpoint = {}

            mock_checkbox = MagicMock()
            mock_checkbox.ask.return_value = ["Claude"]

            modules_no_unittest = {
                k: v for k, v in sys.modules.items() if k != "unittest"
            }

            with (
                patch("skills_menu._get_verified_tools_path", return_value=tools_path),
                patch("sys.stdin.isatty", return_value=True),
                patch.dict("sys.modules", modules_no_unittest, clear=True),
                patch("questionary.checkbox", return_value=mock_checkbox),
                patch("orchestrator.jd_manager.save_checkpoint") as mock_save_cp,
            ):

                added = orchestrator.confirm_jd_skill_gaps_interactively(
                    jd_keywords, checkpoint=checkpoint, job_key="test_job"
                )

                self.assertEqual(added, ["Claude"])
                self.assertEqual(checkpoint["confirmed_skill_gaps"], ["Claude"])
                mock_save_cp.assert_called_once()

                # Verify written JSON file
                with open(tools_path, "r", encoding="utf-8") as f:
                    updated_data = json.load(f)

                self.assertEqual(len(updated_data["tools"]), 2)
                self.assertEqual(updated_data["tools"][1]["name"], "Claude")
                self.assertEqual(updated_data["tools"][1]["id"], "tool_002")


if __name__ == "__main__":
    unittest.main()
