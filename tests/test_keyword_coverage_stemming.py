import os
import sys
import unittest

SCRIPTS_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts"
)
sys.path.insert(0, SCRIPTS_DIR)

import validate_resume  # noqa: E402


class TestKeywordCoverageStemming(unittest.TestCase):
    def setUp(self):
        self.ats_rules = {
            "thresholds": {
                "excellent_match": 85,
                "good_match": 70,
                "weak_match": 50,
            }
        }

    def test_verbatim_match(self):
        resume = {
            "SUMMARY_TEXT": "Experienced CRM strategist with expertise in HubSpot and Salesforce.",
            "SKILLS": ["Tools: HubSpot, Salesforce CRM"],
            "EXPERIENCE": [],
        }
        jd_keywords = {"tools": ["HubSpot", "Salesforce CRM"], "hard_skills": []}
        report = validate_resume.check_keyword_coverage(
            resume, jd_keywords, self.ats_rules
        )
        self.assertEqual(report["score"], 100)
        self.assertIn("HubSpot", report["matched"])
        self.assertIn("Salesforce CRM", report["matched"])

    def test_plural_and_singular_inflection(self):
        resume = {
            "SUMMARY_TEXT": "Built multi-touch campaign sequences and improved customer workflows.",
            "SKILLS": [],
            "EXPERIENCE": [],
        }
        # Singular keywords in JD matching plural in resume
        jd_keywords = {"hard_skills": ["campaign sequence", "workflow"]}
        report = validate_resume.check_keyword_coverage(
            resume, jd_keywords, self.ats_rules
        )
        self.assertEqual(report["score"], 100)
        self.assertIn("campaign sequence", report["matched"])
        self.assertIn("workflow", report["matched"])

    def test_slash_and_hyphen_normalization(self):
        resume = {
            "SUMMARY_TEXT": "10+ years directing B2B SaaS growth initiatives.",
            "SKILLS": [],
            "EXPERIENCE": [],
        }
        jd_keywords = {"hard_skills": ["B2B/SaaS"]}
        report = validate_resume.check_keyword_coverage(
            resume, jd_keywords, self.ats_rules
        )
        self.assertEqual(report["score"], 100)
        self.assertIn("B2B/SaaS", report["matched"])

    def test_gerund_and_multiword_stemming(self):
        resume = {
            "SUMMARY_TEXT": "Leading cross-functional teams in distributing content across global channels.",
            "SKILLS": [],
            "EXPERIENCE": [],
        }
        jd_keywords = {"hard_skills": ["Content Distribution"]}
        report = validate_resume.check_keyword_coverage(
            resume, jd_keywords, self.ats_rules
        )
        self.assertEqual(report["score"], 100)
        self.assertIn("Content Distribution", report["matched"])

    def test_unrelated_word_does_not_false_positive(self):
        resume = {
            "SUMMARY_TEXT": "Smart analytical thinker.",
            "SKILLS": [],
            "EXPERIENCE": [],
        }
        jd_keywords = {"hard_skills": ["Art"]}
        report = validate_resume.check_keyword_coverage(
            resume, jd_keywords, self.ats_rules
        )
        self.assertEqual(report["score"], 0)
        self.assertIn("Art", report["missing"])


if __name__ == "__main__":
    unittest.main()
