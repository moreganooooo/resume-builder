import os
import sys
import unittest

SCRIPTS_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts"
)
sys.path.insert(0, SCRIPTS_DIR)

import orchestrator  # noqa: E402

STYLE_RULES = {
    "bullet_structure": {
        "one_liner_max_chars": 120,
        "two_liner_max_chars": 220,
        "widow_min_words": 5,
    }
}


def _resume_with(company: str, achievements: list) -> dict:
    return {"EXPERIENCE": [{"company": company, "achievements": achievements}]}


class TestShortWidowBullets(unittest.TestCase):

    def test_flags_a_two_line_bullet_with_a_short_widow(self):
        # 115 'A's + " one two three" = 129 chars; chars[120:] = "two three" (2 words)
        widow_bullet = "A" * 115 + " one two three"
        resume = _resume_with("Treering Yearbooks", [widow_bullet])
        result = orchestrator._short_widow_bullets(
            resume, {"Treering Yearbooks"}, STYLE_RULES
        )
        self.assertEqual(result, [widow_bullet])

    def test_does_not_flag_a_two_line_bullet_with_a_full_second_line(self):
        # Well over 120 chars, but the wrapped remainder has 10+ words -- not a widow.
        full_bullet = "D" * 130 + " " + "word " * 10
        resume = _resume_with("Treering Yearbooks", [full_bullet])
        result = orchestrator._short_widow_bullets(
            resume, {"Treering Yearbooks"}, STYLE_RULES
        )
        self.assertEqual(result, [])

    def test_does_not_flag_a_one_line_bullet(self):
        short_bullet = "Short bullet under the one-liner limit."
        resume = _resume_with("Treering Yearbooks", [short_bullet])
        result = orchestrator._short_widow_bullets(
            resume, {"Treering Yearbooks"}, STYLE_RULES
        )
        self.assertEqual(result, [])

    def test_does_not_flag_a_bullet_already_over_the_two_liner_max(self):
        # Already a hard validator violation on its own -- not a widow candidate.
        over_max_bullet = "E" * 225
        resume = _resume_with("Treering Yearbooks", [over_max_bullet])
        result = orchestrator._short_widow_bullets(
            resume, {"Treering Yearbooks"}, STYLE_RULES
        )
        self.assertEqual(result, [])

    def test_ignores_bullets_from_companies_outside_the_target_set(self):
        widow_bullet = "A" * 115 + " one two three"
        resume = _resume_with("Mercor", [widow_bullet])
        result = orchestrator._short_widow_bullets(
            resume, {"Treering Yearbooks", "Inside Sales Team"}, STYLE_RULES
        )
        self.assertEqual(result, [])

    def test_checks_multiple_target_companies(self):
        widow_bullet = "A" * 115 + " one two three"
        resume = {
            "EXPERIENCE": [
                {"company": "Treering Yearbooks", "achievements": [widow_bullet]},
                {"company": "Inside Sales Team", "achievements": [widow_bullet]},
                {"company": "Mercor", "achievements": [widow_bullet]},
            ]
        }
        result = orchestrator._short_widow_bullets(
            resume, {"Treering Yearbooks", "Inside Sales Team"}, STYLE_RULES
        )
        self.assertEqual(result, [widow_bullet, widow_bullet])


class TestWidowTrimInstruction(unittest.TestCase):

    def test_lists_candidate_bullets_when_present(self):
        widow_bullet = "A" * 115 + " one two three"
        resume = _resume_with("Treering Yearbooks", [widow_bullet])
        instruction = orchestrator._widow_trim_instruction(resume, STYLE_RULES)
        self.assertIn(widow_bullet, instruction)
        self.assertIn("Tighten ONLY", instruction)

    def test_says_nothing_to_do_when_no_candidates(self):
        short_bullet = "Short bullet under the one-liner limit."
        resume = _resume_with("Treering Yearbooks", [short_bullet])
        instruction = orchestrator._widow_trim_instruction(resume, STYLE_RULES)
        self.assertIn("change nothing", instruction)
        self.assertNotIn(short_bullet, instruction)

    def test_checks_every_company_actually_present_not_a_hardcoded_pair(self):
        # Regression test: this used to hardcode {"Treering Yearbooks",
        # "Inside Sales Team"} -- a widow bullet from any other company
        # (e.g. a profile with entirely different companies) must still
        # get caught.
        widow_bullet = "A" * 115 + " one two three"
        resume = _resume_with("Some Other Company", [widow_bullet])
        instruction = orchestrator._widow_trim_instruction(resume, STYLE_RULES)
        self.assertIn(widow_bullet, instruction)


class TestBulletRemovalTrimInstruction(unittest.TestCase):
    """
    Regression tests for the last-resort bullet-removal trim step, which
    used to hardcode "Inside Sales Team, then Treering Yearbooks" and a
    specific protected-bullet phrase -- both Morgan-specific and a silent
    no-op for any profile whose companies/protected content differ.
    """

    def test_orders_by_flex_priority_and_names_each_roles_min_bullets(self):
        profile_data = {
            "roles": [
                {"name": "Acme", "min_bullets": 2, "flex_priority": 2},
                {"name": "Beta", "min_bullets": 3, "flex_priority": 1},
            ],
            "protected_bullets": [],
        }
        instruction = orchestrator._bullet_removal_trim_instruction(profile_data)
        self.assertIn("Beta (can go down to 3 bullets total)", instruction)
        self.assertIn("Acme (can go down to 2 bullets total)", instruction)
        self.assertLess(instruction.index("Beta"), instruction.index("Acme"))

    def test_includes_protected_bullets_when_present(self):
        profile_data = {
            "roles": [{"name": "Acme", "min_bullets": 2, "flex_priority": 1}],
            "protected_bullets": ["A signature achievement"],
        }
        instruction = orchestrator._bullet_removal_trim_instruction(profile_data)
        self.assertIn("A signature achievement", instruction)

    def test_falls_back_to_generic_guidance_with_no_roles(self):
        instruction = orchestrator._bullet_removal_trim_instruction({})
        self.assertIn("most distinctive", instruction)


if __name__ == "__main__":
    unittest.main()
