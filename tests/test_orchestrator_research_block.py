import os
import sys
import unittest

SCRIPTS_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts")
sys.path.insert(0, SCRIPTS_DIR)

import orchestrator  # noqa: E402


class TestFormatCompanyResearchBlock(unittest.TestCase):

    BASE = {
        "overall_tone_adjective": "warm and neighborly",
        "tone_register": "conversational",
        "pronoun_framing": "we-centric",
        "sentence_style": "short and punchy",
        "jargon_density": "low",
        "recurring_keywords": ["neighborly", "community"],
        "company_facts": ["Runs 400 neighborhood stores."],
    }

    def test_omits_vocabulary_line_when_field_absent(self):
        block = orchestrator.format_company_research_block(dict(self.BASE))
        self.assertNotIn("Preferred vocabulary", block)

    def test_omits_vocabulary_line_when_field_is_empty(self):
        block = orchestrator.format_company_research_block(
            dict(self.BASE, vocabulary_substitutions=[]))
        self.assertNotIn("Preferred vocabulary", block)

    def test_includes_vocabulary_line_when_pairs_present(self):
        block = orchestrator.format_company_research_block(dict(
            self.BASE,
            vocabulary_substitutions=[
                {"generic_term": "customers", "company_term": "guests"},
                {"generic_term": "employees", "company_term": "team members"},
            ],
        ))
        self.assertIn("Preferred vocabulary", block)
        self.assertIn("customers -> guests", block)
        self.assertIn("employees -> team members", block)

    def test_skips_malformed_pairs_in_the_line(self):
        block = orchestrator.format_company_research_block(dict(
            self.BASE,
            vocabulary_substitutions=[
                {"generic_term": "", "company_term": "guests"},
                {"generic_term": "customers", "company_term": "guests"},
                "not a dict",
            ],
        ))
        vocab_line = block.split("Preferred vocabulary")[1]
        self.assertIn("customers -> guests", vocab_line)
        # Exactly one pair survived -- no separator means no second entry.
        self.assertNotIn(",", vocab_line.split(": ", 1)[1])

    def test_still_renders_the_existing_fields(self):
        block = orchestrator.format_company_research_block(dict(self.BASE))
        self.assertIn("=== COMPANY RESEARCH ===", block)
        self.assertIn("warm and neighborly", block)
        self.assertIn("Runs 400 neighborhood stores.", block)


if __name__ == "__main__":
    unittest.main()
