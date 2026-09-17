import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))

import orchestrator  # noqa: E402

PROFILE = {"target_roles": {"primary": ["Widget Analyst"], "secondary": ["Gadget Writer"]}}


class TestDropTargetRoleTitles(unittest.TestCase):
    def test_removes_titles_from_every_category_case_insensitively(self):
        keywords = {
            "tools": ["Excel", "widget analyst"],
            "hard_skills": ["Forecasting", "Gadget Writer"],
            "core_functions": ["Reporting"],
        }
        result = orchestrator._drop_target_role_titles(keywords, PROFILE)
        self.assertEqual(result["tools"], ["Excel"])
        self.assertEqual(result["hard_skills"], ["Forecasting"])
        self.assertEqual(result["core_functions"], ["Reporting"])
        self.assertIn("widget analyst", keywords["tools"])

    def test_leaves_keywords_alone_without_target_roles(self):
        keywords = {"tools": ["Widget Analyst"]}
        self.assertIs(orchestrator._drop_target_role_titles(keywords, {}), keywords)
        self.assertIsNone(orchestrator._drop_target_role_titles(None, PROFILE))


if __name__ == "__main__":
    unittest.main()
