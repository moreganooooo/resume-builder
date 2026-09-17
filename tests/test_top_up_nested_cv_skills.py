"""cv.md skill groups written as a heading with nested sub-rows still place
their skills, and a shared category word is not treated as a tie."""

import os
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))

import orchestrator  # noqa: E402

CV = """## Core Skills

**Baking & Pastry Operations**
*   **Stack:** Ovenly, Doughbot
*   **Methods:** Laminated Dough

**Cafe & Pastry Marketing:** Menu Copy, Instagram

## Experience
"""


class TestNestedCvSkillGroups(unittest.TestCase):
    def test_nested_rows_belong_to_their_heading(self):
        groups = orchestrator._parse_cv_skill_groups(CV)
        self.assertEqual(groups["doughbot"], "Baking & Pastry Operations")
        self.assertEqual(groups["laminated dough"], "Baking & Pastry Operations")
        self.assertEqual(groups["instagram"], "Cafe & Pastry Marketing")

    def test_best_label_overlap_wins_over_a_shared_word(self):
        resume = {
            "SUMMARY_TEXT": "Baker.",
            "SKILLS": [
                "**Baking & Pastry Operations:** Ovenly",
                "**Cafe & Pastry Marketing:** Menu Copy",
            ],
            "EXPERIENCE": [{"title": "Baker", "achievements": ["Baked."]}],
        }
        with patch.object(
            orchestrator.validate_resume, "_check_hallucinated_tools", return_value=[]
        ):
            result, added = orchestrator._top_up_verified_skills(
                resume, {"tools": ["Doughbot"]}, {}, CV, ["Ovenly", "Doughbot"]
            )
        self.assertEqual(added, ["Doughbot"])
        self.assertTrue(result["SKILLS"][0].endswith("Ovenly, Doughbot"))


if __name__ == "__main__":
    unittest.main()
