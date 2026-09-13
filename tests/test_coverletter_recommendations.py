"""Recommendations reach the cover-letter builder (the one consumer of
profile.yml's key_recommendations), and a quoted recommendation naming the
candidate is not flagged as the letter slipping into third person."""

import os
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))

import orchestrator  # noqa: E402
import validate_coverletter  # noqa: E402

RECS = [
    {
        "name": "Dana Referee",
        "title": "Director of Marketing, Example Co",
        "relationship": "managed the candidate directly",
        "date": "2009-04",
        "quote": "She met every deadline I presented her with,\n  and always exceeded my expectations.",
    },
    {"name": "No Quote Person", "title": "CEO"},
    "not a dict",
]


class TestBuildRecommendationsBlock(unittest.TestCase):
    def test_formats_verbatim_quote_with_attribution(self):
        block = orchestrator.build_recommendations_block(RECS)
        self.assertIn("=== RECOMMENDATIONS", block)
        self.assertIn(
            '"She met every deadline I presented her with, and always exceeded my expectations."'
            " -- Dana Referee, Director of Marketing, Example Co (managed the candidate directly, 2009)",
            block,
        )
        self.assertIn("at most ONE", block)
        self.assertNotIn("No Quote Person", block)

    def test_empty_when_there_are_no_usable_recommendations(self):
        self.assertEqual(orchestrator.build_recommendations_block(None), "")
        self.assertEqual(orchestrator.build_recommendations_block([{"name": "X"}]), "")


class TestThirdPersonCheckIgnoresQuotedRecommendations(unittest.TestCase):
    def _violations(self, paragraph):
        with patch(
            "validate_coverletter.profile_paths.profile_yaml",
            return_value={"candidate": {"full_name": "Jordan Example"}},
        ):
            return validate_coverletter._check_third_person_slip(
                {"greeting": "Dear Hiring Team,", "body_paragraphs": [paragraph], "sign_off": ""}
            )

    def test_quoted_reference_naming_the_candidate_passes(self):
        para = 'As my former director put it, "Jordan got it done on every single project."'
        self.assertEqual(self._violations(para), [])
        curly = "As my former director put it, “Jordan got it done on every project.”"
        self.assertEqual(self._violations(curly), [])

    def test_unquoted_self_reference_is_still_flagged(self):
        self.assertTrue(self._violations("Jordan brings eight years of lifecycle work."))


if __name__ == "__main__":
    unittest.main()
