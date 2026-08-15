import os
import unittest

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PROMPT_PATH = os.path.join(PROJECT_ROOT, "resume-engine", "prompts", "tailor_resume.md")


class TestTailorPromptVocabularyRules(unittest.TestCase):
    """Guards the 2026-08-11 vocabulary-mirroring instructions against
    silent removal during future prompt edits."""

    @classmethod
    def setUpClass(cls):
        with open(PROMPT_PATH, "r", encoding="utf-8") as f:
            cls.prompt = f.read()

    def test_summary_and_why_rules_reference_the_vocabulary_field(self):
        # "Preferred vocabulary" rather than the schema's own
        # `vocabulary_substitutions` name: the rendered COMPANY RESEARCH
        # block is all the model ever sees, and that's the label
        # format_company_research_block() emits. Two occurrences = the
        # Summary rule and the Why rule.
        self.assertGreaterEqual(self.prompt.count("Preferred vocabulary"), 2)

    def test_bullet_rules_forbid_model_side_rewording_for_vocabulary(self):
        bullet_section = self.prompt.split("# Bullet Rules")[1].split("\n#")[0]
        self.assertIn("vocabulary_substitutions", bullet_section)
        self.assertIn("Do not reword", bullet_section)

    def test_drops_the_stale_no_research_block_fallbacks(self):
        # A COMPANY RESEARCH block is now effectively always present, so
        # "skip if absent" instructions would misfire.
        self.assertNotIn("skip tone-mirroring entirely", self.prompt)
        self.assertNotIn("do not include this Why section at all", self.prompt)


if __name__ == "__main__":
    unittest.main()
