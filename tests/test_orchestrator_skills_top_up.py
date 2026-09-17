"""_top_up_verified_skills restores JD keywords the candidate is already
verified for but which the finished resume happens not to say.

The interesting assertions are the SKIPS and the verification gate. Match
evidence is deliberately loose -- "S3" is proven by the ledger's "AWS S3" --
and that is only safe because every edit is kept solely on the strength of
the coverage check crediting the keyword afterwards.
"""

import os
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))

import orchestrator  # noqa: E402

# The AWS parenthetical is load-bearing: a naive comma split reads it as
# "AWS (Glue" and "RDS)", which silently denies RDS a category.
CV_TEXT = """# CV

## Core Skills

**Languages & Libraries:** Python, SQL, spaCy, NLTK
**Machine Learning & Statistics:** Regression, supervised & unsupervised learning
**Data Engineering & Cloud:** AWS (Glue, S3, RDS), Git
**Visualization & Communication:** Matplotlib, technical documentation for non-technical stakeholders
**Scientific Computing:** Mathematica, Fortran, signal processing

## Experience
"""

LEDGER = [
    "Python", "SQL", "spaCy", "NLTK", "Mathematica", "Fortran", "Git",
    "Supervised & unsupervised learning", "AWS Glue", "AWS S3", "AWS RDS",
    "Matplotlib", "Signal processing",
    "Technical documentation for cross-functional/non-technical stakeholders",
]


def _resume(skills):
    return {
        "SUMMARY_TEXT": "Data scientist.",
        "SKILLS": list(skills),
        "EXPERIENCE": [{"title": "Data Scientist", "achievements": ["Built models."]}],
    }


class TestTopUpVerifiedSkills(unittest.TestCase):
    def setUp(self):
        # The real ledger is the active profile's, which the suite must not
        # depend on -- this step's own guard is under test, not the profile
        # it happens to run against.
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
        # reports lowercase words on them, so appending the ledger's
        # "Supervised & unsupervised learning" verbatim would fix a
        # coverage miss by introducing a style violation.
        resume = _resume(["**Machine Learning & Statistics:** Regression"])
        result, added = self._run(
            resume, {"hard_skills": ["supervised & unsupervised learning"]}
        )
        self.assertEqual(added, ["Supervised & Unsupervised Learning"])
        self.assertTrue(
            result["SKILLS"][0].endswith("Supervised & Unsupervised Learning")
        )

    def test_preserves_a_name_that_carries_its_own_capitals(self):
        self.assertEqual(orchestrator._title_case_skill("spaCy"), "spaCy")
        self.assertEqual(orchestrator._title_case_skill("NLTK"), "NLTK")
        self.assertEqual(orchestrator._title_case_skill("AWS S3"), "AWS S3")

    def test_never_mutates_the_input(self):
        resume = _resume(["**Languages & Frameworks:** Python, SQL"])
        original = list(resume["SKILLS"])
        result, added = self._run(resume, {"tools": ["spaCy"]})
        self.assertTrue(added)
        self.assertEqual(resume["SKILLS"], original)
        self.assertIsNot(result["SKILLS"], resume["SKILLS"])

    # --- evidence widened beyond an exact ledger name ---

    def test_a_ledger_superset_name_proves_a_bare_keyword(self):
        resume = _resume(["**Data Engineering & Cloud:** AWS Glue"])
        result, added = self._run(resume, {"tools": ["S3"]})
        self.assertEqual(added, ["AWS S3"])
        self.assertIn("AWS S3", result["SKILLS"][0])

    def test_a_parenthesised_cv_group_still_places_its_skills(self):
        # RDS only looked structurally unplaceable because "RDS)" never
        # matched anything -- a parsing bug, not a missing skill.
        resume = _resume(["**Data Engineering & Cloud:** AWS Glue"])
        _, added = self._run(resume, {"tools": ["RDS"]})
        self.assertEqual(added, ["AWS RDS"])

    def test_falls_back_to_the_concise_form_when_the_ledger_spells_a_sentence(self):
        resume = _resume(["**Visualization & Communication:** Matplotlib"])
        result, added = self._run(resume, {"hard_skills": ["technical documentation"]})
        self.assertEqual(added, ["Technical Documentation"])
        self.assertNotIn("cross-functional", result["SKILLS"][0])

    # --- the verification gate ---

    def test_keeps_nothing_the_coverage_check_does_not_credit(self):
        resume = _resume(["**Languages & Frameworks:** Python, SQL"])
        with patch.object(
            orchestrator.validate_resume,
            "check_keyword_coverage",
            return_value={"missing": ["spaCy"], "matched": [], "score": 0, "band": "x"},
        ):
            result, added = self._run(resume, {"tools": ["spaCy"]})
        self.assertEqual(added, [])
        self.assertEqual(result, resume)

    # --- creating a home for a group that has none ---

    def test_creates_a_line_for_a_group_with_no_home_and_brings_its_items_back(self):
        resume = _resume([
            "**Visualization & Communication:** Matplotlib, Signal Processing",
        ])
        result, added = self._run(resume, {"tools": ["Mathematica"]})
        self.assertEqual(added, ["Mathematica"])
        self.assertEqual(
            result["SKILLS"][0], "**Visualization & Communication:** Matplotlib"
        )
        self.assertEqual(
            result["SKILLS"][1],
            "**Scientific Computing:** Signal Processing, Mathematica",
        )

    def test_never_empties_an_existing_line_to_fill_a_new_one(self):
        resume = _resume(["**Visualization & Communication:** Signal Processing"])
        result, added = self._run(resume, {"tools": ["Fortran"]})
        self.assertEqual(added, ["Fortran"])
        self.assertEqual(
            result["SKILLS"][0], "**Visualization & Communication:** Signal Processing"
        )
        self.assertEqual(result["SKILLS"][1], "**Scientific Computing:** Fortran")

    # --- rows that need company to wrap ---

    def test_several_items_together_fill_a_second_line_one_alone_cannot(self):
        # 105 printed: any single append lands in the 111-134 dead band,
        # but three together reach a legal two-line row.
        line = "**Scientific Computing:** " + ", ".join(["Fortran"] * 9) + ", Fo"
        self.assertEqual(len(orchestrator._plain_skills_line(line)), 105)
        ledger = LEDGER + ["Numerical Methods", "Finite Element Modeling"]
        cv = CV_TEXT.replace(
            "signal processing", "signal processing, numerical methods, finite element modeling"
        )
        _, added = self._run(
            _resume([line]),
            {"tools": ["Mathematica", "Numerical Methods", "Finite Element Modeling"]},
            cv_text=cv, ledger=ledger,
        )
        self.assertEqual(len(added), 3)

    def test_only_one_row_may_newly_wrap_per_build(self):
        a = "**Scientific Computing:** " + ", ".join(["Fortran"] * 9) + ", Fo"
        b = "**Languages & Libraries:** " + ", ".join(["Python"] * 11)
        b = b[: len(b) - (len(orchestrator._plain_skills_line(b)) - 105)]
        ledger = LEDGER + ["Numerical Methods", "Finite Element Modeling",
                           "Pandas Profiling", "Scikit Learn Pipelines"]
        cv = CV_TEXT.replace(
            "signal processing", "signal processing, numerical methods, finite element modeling"
        ).replace("spaCy, NLTK", "spaCy, NLTK, pandas profiling, scikit learn pipelines")
        result, _ = self._run(
            _resume([a, b]),
            {"tools": ["Mathematica", "Numerical Methods", "Finite Element Modeling",
                       "spaCy", "Pandas Profiling", "Scikit Learn Pipelines"]},
            cv_text=cv, ledger=ledger,
        )
        wrapped = [l for l in result["SKILLS"]
                   if len(orchestrator._plain_skills_line(l)) > 110]
        self.assertEqual(len(wrapped), 1)

    def test_the_row_holding_the_groups_skills_wins_over_a_shared_label_word(self):
        resume = _resume([
            "**Scientific Computing Tools:** Matplotlib",
            "**Research Stack:** Fortran, Signal Processing",
        ])
        result, added = self._run(resume, {"tools": ["Mathematica"]})
        self.assertEqual(added, ["Mathematica"])
        self.assertEqual(result["SKILLS"][1], "**Research Stack:** Fortran, Signal Processing, Mathematica")

    # --- skills cv.md never grouped ---

    def test_model_assigned_row_places_a_verified_ungrouped_skill(self):
        resume = _resume(["**Languages & Frameworks:** Python, SQL"])
        calls = []

        def assign(keywords, labels):
            calls.append((keywords, labels))
            return {"Pandas": "Languages & Frameworks"}

        result, added = orchestrator._top_up_verified_skills(
            resume, {"tools": ["Pandas"]}, {}, CV_TEXT, LEDGER + ["Pandas"],
            assign_groups=assign,
        )
        self.assertEqual(calls, [(["Pandas"], ["Languages & Frameworks"])])
        self.assertEqual(added, ["Pandas"])

    def test_model_never_asked_about_an_unverified_skill_or_trusted_off_list(self):
        resume = _resume(["**Languages & Frameworks:** Python, SQL"])
        seen = []

        def assign(keywords, labels):
            seen.extend(keywords)
            return {"Pandas": "Invented Row"}

        _, added = orchestrator._top_up_verified_skills(
            resume, {"tools": ["Pandas", "Snowflake"]}, {}, CV_TEXT,
            LEDGER + ["Pandas"], assign_groups=assign,
        )
        self.assertEqual(seen, ["Pandas"])
        self.assertEqual(added, [])

    # --- refusals ---

    def test_skips_a_keyword_with_no_evidence_at_all(self):
        resume = _resume(["**Languages & Frameworks:** Python, SQL"])
        result, added = self._run(
            resume, {"tools": ["Snowflake"]}, ledger=["Python"]
        )
        self.assertEqual(added, [])
        self.assertEqual(result, resume)

    def test_skips_when_two_lines_match_the_category_equally(self):
        resume = _resume([
            "**Languages & Tools:** Python",
            "**Languages & Frameworks:** SQL",
        ])
        _, added = self._run(resume, {"tools": ["spaCy"]})
        self.assertEqual(added, [])

    def test_the_exact_category_line_wins_over_a_partial_match(self):
        resume = _resume([
            "**Languages & Libraries:** Python",
            "**Languages & Frameworks:** SQL",
        ])
        result, added = self._run(resume, {"tools": ["spaCy"]})
        self.assertEqual(added, ["spaCy"])
        self.assertEqual(result["SKILLS"][0], "**Languages & Libraries:** Python, spaCy")

    def test_measures_the_printed_width_not_the_bold_markup(self):
        # The label's four asterisks are not rendered. Counting them made
        # every line read 4 chars too long, so an append could be refused
        # for crossing a limit the printed line never reaches. This line
        # prints at 102, so ", spaCy" lands at 109 of an allowed 110.
        line = "**Languages & Frameworks:** " + ", ".join(["Python"] * 10)
        self.assertEqual(len(line), 106)
        self.assertEqual(len(orchestrator._plain_skills_line(line)), 102)
        resume = _resume([line])
        _, added = self._run(resume, {"tools": ["spaCy"]})
        self.assertEqual(added, ["spaCy"])

    def test_skips_an_append_that_lands_in_the_widow_dead_band(self):
        line = "**Languages & Frameworks:** " + ", ".join(["Python"] * 11)
        self.assertEqual(len(orchestrator._plain_skills_line(line)), 110)
        resume = _resume([line])
        _, added = self._run(resume, {"tools": ["spaCy"]})
        # 110 printed + ", spaCy" = 117, inside the illegal 111-134 dead
        # band, so the append would trade a missing keyword for a layout
        # violation.
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

    def test_splits_a_parenthesised_vendor_group_into_its_skills(self):
        groups = orchestrator._parse_cv_skill_groups(CV_TEXT)
        # The vendor prefix stays attached to the first item, which is what
        # makes it "AWS Glue" rather than a bare, meaningless "Glue".
        for key in ("s3", "rds", "aws glue"):
            self.assertEqual(groups[key], "Data Engineering & Cloud", key)

    def test_ignores_bold_lines_outside_core_skills(self):
        cv = "## Experience\n\n**Tools Used:** Excel, Word\n"
        self.assertEqual(orchestrator._parse_cv_skill_groups(cv), {})


if __name__ == "__main__":
    unittest.main()
