"""Vague size words standing in for a number are flagged in the Summary and
bullets -- as a soft warning (fix attempt, never a failed build)."""

import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))

import orchestrator  # noqa: E402
import validate_resume  # noqa: E402


def flags(summary="", bullets=()):
    data = {
        "SUMMARY_TEXT": summary,
        "EXPERIENCE": [{"company": "Acme", "achievements": list(bullets)}],
    }
    return validate_resume._check_vague_magnitudes(data)


class TestVagueMagnitudes(unittest.TestCase):
    def test_summary_vague_word_is_flagged(self):
        v = flags("<strong>Analyst.</strong> Drove significant accuracy improvements.")
        self.assertEqual(len(v), 1)
        self.assertIn("'significant'", v[0])

    def test_bullet_vague_adverb_is_flagged(self):
        self.assertEqual(len(flags(bullets=["Reduced processing time substantially"])), 1)

    def test_statistical_significance_is_not_flagged(self):
        self.assertEqual(flags(bullets=["Ran A/B tests to statistically significant results"]), [])
        self.assertEqual(flags(bullets=["Tested significance of 12 features"]), [])

    def test_specific_figures_pass(self):
        self.assertEqual(flags("Improved accuracy by 15%.", ["Cut processing time 40%"]), [])

    def test_it_is_a_soft_warning(self):
        fatal, soft = orchestrator.partition_violations(flags("Delivered greatly improved results."))
        self.assertEqual(fatal, [])
        self.assertEqual(len(soft), 1)


if __name__ == "__main__":
    unittest.main()
