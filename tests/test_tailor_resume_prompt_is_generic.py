import os
import sys
import unittest

import yaml

sys.path.insert(
    0,
    os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts"
    ),
)

PROMPT_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "resume-engine",
    "prompts",
    "tailor_resume.md",
)

STYLE_RULES_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "resume-engine",
    "rules",
    "style_rules.yaml",
)

BANNED_STRINGS = [
    "Mercor",
    "Treering Yearbooks",
    "Element 8",
    "Strategy LLC",
    "VML",
    "Callahan Creek",
    "Inside Sales Team",
    "Humane Society of Greater Kansas City",
    "Unisource Document Products",
    "Kansas Colloquies",
    "KU Payroll Office",
    "DeJoy, Knauff & Blood",
    "USitek",
    "University of Kansas",
    "Kansas City Kansas Community College",
    "Johnson County Community College",
    "HubSpot",
    "Vidyard",
    "Bernstein Rein",
    "testprofile",
]


class TestTailorResumePromptIsGeneric(unittest.TestCase):

    def setUp(self):
        with open(PROMPT_PATH, "r") as f:
            self.text = f.read()

    def test_contains_no_hardcoded_company_or_personal_names(self):
        found = [s for s in BANNED_STRINGS if s in self.text]
        self.assertEqual(
            found,
            [],
            f"tailor_resume.md still contains profile-specific strings: {found}",
        )

    def test_still_references_role_rules_block(self):
        self.assertIn("ROLE RULES", self.text)


class TestStyleRulesYamlIsGeneric(unittest.TestCase):

    def setUp(self):
        with open(STYLE_RULES_PATH, "r") as f:
            self.text = f.read()
            f.seek(0)
            self.data = yaml.safe_load(f)

    def test_contains_no_hardcoded_company_names(self):
        banned = [
            "Mercor",
            "Treering",
            "Element 8",
            "Strategy LLC",
            "VML",
            "Callahan Creek",
            "IST",
        ]
        found = [s for s in banned if s in self.text]
        self.assertEqual(found, [])

    def test_page_assignment_is_still_valid_yaml(self):
        self.assertIn("page_1", self.data["layout_rules"])
        self.assertIn("page_2", self.data["layout_rules"])


PROMPTS_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "resume-engine",
    "prompts",
)
SMALLER_PROMPT_FILES = [
    "evaluate_fit.md",
    "critique_bullet.md",
    "critique_resume.md",
    "polish_resume.md",
    "polish_coverletter.md",
    "tailor_coverletter.md",
]


class TestSmallerPromptFilesAreGeneric(unittest.TestCase):

    def test_no_prompt_file_names_the_operator(self):
        """Prompt templates must be generic: the candidate's identity comes
        from their profile at build time, never baked into the prompt.

        Checks the ACTIVE profile's own name rather than a hardcoded one,
        so this keeps working for whoever set the repo up. (The literal it
        used to search for was the previous author's name, which a
        depersonalisation sweep would happily "fix" into meaninglessness.)
        """
        import profile_paths

        candidate = (profile_paths.profile_yaml() or {}).get("candidate") or {}
        full_name = (candidate.get("full_name") or "").strip()
        if not full_name:
            self.skipTest("No configured profile name to check against.")

        needles = [full_name] + [p for p in full_name.split() if len(p) >= 5]
        offenders = []
        for filename in SMALLER_PROMPT_FILES:
            with open(os.path.join(PROMPTS_DIR, filename), "r") as f:
                text = f.read()
            for needle in needles:
                if needle.lower() in text.lower():
                    offenders.append(f"{filename} mentions {needle!r}")
        self.assertEqual(offenders, [], "\n".join(offenders))


if __name__ == "__main__":
    unittest.main()
