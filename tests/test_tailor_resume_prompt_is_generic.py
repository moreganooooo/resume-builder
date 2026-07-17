import os
import unittest

PROMPT_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "resume-engine", "prompts", "tailor_resume.md",
)

BANNED_STRINGS = [
    "Mercor", "Treering Yearbooks", "Element 8", "Strategy LLC", "VML",
    "Callahan Creek", "Inside Sales Team", "Humane Society of Greater Kansas City",
    "Unisource Document Products", "Kansas Colloquies", "KU Payroll Office",
    "DeJoy, Knauff & Blood", "USitek", "University of Kansas",
    "Kansas City Kansas Community College", "Johnson County Community College",
    "HubSpot", "Vidyard", "Bernstein Rein", "Morgan",
]


class TestTailorResumePromptIsGeneric(unittest.TestCase):

    def setUp(self):
        with open(PROMPT_PATH, "r") as f:
            self.text = f.read()

    def test_contains_no_hardcoded_company_or_personal_names(self):
        found = [s for s in BANNED_STRINGS if s in self.text]
        self.assertEqual(found, [], f"tailor_resume.md still contains profile-specific strings: {found}")

    def test_still_references_role_rules_block(self):
        self.assertIn("ROLE RULES", self.text)


if __name__ == "__main__":
    unittest.main()
