"""_top_up_verified_skills restores JD keywords the candidate is already
verified for but whose name the finished resume happens not to say.

The interesting assertions are the SKIPS: this step is only safe because it
refuses to place a skill it cannot place correctly. A resume silent about
spaCy is a small loss; one listing spaCy under "Visualization &
Communication" because that line had room is a wrong resume.
"""

import os
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))

import orchestrator  # noqa: E402

CV_TEXT = """# CV

## Core Skills

**Languages & Libraries:** Python, SQL, spaCy, NLTK
**Machine Learning & Statistics:** Regression, supervised & unsupervised learning
**Scientific Computing:** Mathematica, Fortran

## Experience
"""

LEDGER = ["Python", "SQL", "spaCy", "NLTK", "Mathematica", "Fortran",
          "Supervised & unsupervised learning"]


def _resume(skills):
    return {
        "SUMMARY_TEXT": "Data scientist.",
        "SKILLS": list(skills),
        "EXPERIENCE": [{"title": "Data Scientist", "achievements": ["Built models."]}],
    }


class TestTopUpVerifiedSkills(unittest.TestCase):
    def setUp(self):
        # The candidate's real ledger is the active profile's, which the
        # suite must not depend on -- this step's own guard is what is
        # under test, not the profile it happens to run against.
        patcher = patch.object(
            orchestrator.validate_resume,
            "_check_hallucinated_tools",
            return_value=[],
        )
        patcher.start()
        self.addCleanup(patcher.stop)

    def _run(self, resume, keywords, cv_text=CV_TEXT, ledger=None):
        return orchestrator._top_up_verified_skills(
            resume, keywords, {}, cv_text, LEDGER if ledger is None else ledger
        )

    def test_appends_verified_keyword_to_its_own_cv_category(self):
        resume = _resume(["**Languages & Frameworks:** Python, SQL"])
        result, added = self._run(resume, {"tools": ["spaCy"]})
        self.assertEqual(added, ["spaCy"])
        self.assertEqual(
            result["SKILLS"][0], "**Languages & Frameworks:** Python, SQL, spaCy"
        )

    def test_title_cases_the_appended_name_not_the_jd_keywords_casing(self):
        # Skills lines are Title Case by style rule and the validator
        # reports lowercase words on them -- appending the ledger's
        # "Supervised & unsupervised learning" verbatim would fix a
        # coverage miss by introducing a style violation.
        resume = _resume(["**Machine Learning & Statistics:** Regression"])
        result, added = self._run(
            resume, {"hard_skills": ["supervised & unsupervised learning"]}
        )
        self.assertEqual(added, ["Supervised & Unsupervised Learning"])
        self.assertTrue(result["SKILLS"][0].endswith("Supervised & Unsupervised Learning"))

    def test_preserves_a_name_that_carries_its_own_capitals(self):
        self.assertEqual(orchestrator._title_case_skill("spaCy"), "spaCy")
        self.assertEqual(orchestrator._title_case_skill("NLTK"), "NLTK")
        self.assertEqual(
            orchestrator._title_case_skill("time-series modeling"),
            "Time-series Modeling",
        )

    def test_never_mutates_the_input(self):
        resume = _resume(["**Languages & Frameworks:** Python, SQL"])
        original = list(resume["SKILLS"])
        result, added = self._run(resume, {"tools": ["spaCy"]})
        self.assertTrue(added)
        self.assertEqual(resume["SKILLS"], original)
        self.assertIsNot(result["SKILLS"], resume["SKILLS"])

    def test_skips_a_keyword_that_is_not_verified(self):
        resume = _resume(["**Languages & Frameworks:** Python, SQL"])
        result, added = self._run(resume, {"tools": ["Snowflake"]}, ledger=["Python"])
        self.assertEqual(added, [])
        self.assertEqual(result, resume)

    def test_skips_when_no_rendered_line_matches_the_cv_category(self):
        # Mathematica is grouped under "Scientific Computing", which has no
        # home on this page -- the Visualization line has room, and that is
        # exactly the placement this must refuse to make.
        resume = _resume(["**Visualization & Communication:** Matplotlib, Tableau"])
        result, added = self._run(resume, {"tools": ["Mathematica"]})
        self.assertEqual(added, [])
        self.assertNotIn("Mathematica", result["SKILLS"][0])

    def test_skips_when_two_lines_match_the_category(self):
        resume = _resume([
            "**Languages & Libraries:** Python",
            "**Languages & Frameworks:** SQL",
        ])
        _, added = self._run(resume, {"tools": ["spaCy"]})
        self.assertEqual(added, [])

    def test_skips_an_append_that_lands_in_the_widow_dead_band(self):
        line = "**Languages & Frameworks:** " + ", ".join(["Python"] * 10)
        self.assertEqual(len(line), 106)
        resume = _resume([line])
        _, added = self._run(resume, {"tools": ["spaCy"]})
        # 106 + ", spaCy" = 113, inside the illegal 111-134 dead band, so
        # the append would trade a missing keyword for a layout violation.
        self.assertEqual(added, [])

    def test_skips_a_keyword_cv_md_does_not_group(self):
        resume = _resume(["**Languages & Frameworks:** Python, SQL"])
        _, added = self._run(
            resume, {"tools": ["NLTK"]}, cv_text="## Core Skills\n\nno groups here\n"
        )
        self.assertEqual(added, [])

    def test_no_op_when_nothing_is_missing(self):
        resume = _resume(["**Languages & Frameworks:** Python, spaCy"])
        result, added = self._run(resume, {"tools": ["spaCy"]})
        self.assertEqual(added, [])
        self.assertIs(result, resume)


class TestParseCvSkillGroups(unittest.TestCase):
    def test_only_reads_the_core_skills_block(self):
        groups = orchestrator._parse_cv_skill_groups(CV_TEXT)
        self.assertEqual(groups["spacy"], "Languages & Libraries")
        self.assertEqual(groups["fortran"], "Scientific Computing")

    def test_ignores_bold_lines_outside_core_skills(self):
        cv = "## Experience\n\n**Tools Used:** Excel, Word\n"
        self.assertEqual(orchestrator._parse_cv_skill_groups(cv), {})


if __name__ == "__main__":
    unittest.main()
