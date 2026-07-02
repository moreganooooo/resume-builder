import os
import sys
import unittest

SCRIPTS_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts")
sys.path.insert(0, SCRIPTS_DIR)

import orchestrator  # noqa: E402


class TestLoadPromptFailsLoudly(unittest.TestCase):

    def setUp(self):
        self.engine = orchestrator.ResumeEngine()

    def test_missing_prompt_file_raises_instead_of_silent_fallback(self):
        with self.assertRaises(FileNotFoundError):
            self.engine.load_prompt("this_file_does_not_exist.md")

    def test_extract_keywords_prompt_file_exists_and_loads_real_content(self):
        content = self.engine.load_prompt("extract_keywords.md")
        self.assertNotEqual(content.strip(), "Process the text.")
        self.assertIn("tools", content)
        self.assertIn("hard_skills", content)
        self.assertIn("core_functions", content)

    def test_load_yaml_raises_instead_of_silent_empty_dict(self):
        with self.assertRaises(FileNotFoundError):
            self.engine.load_yaml(self.engine.rules_dir, "this_file_does_not_exist.yaml")

    def test_load_yaml_still_loads_a_real_file(self):
        data = self.engine.load_yaml(self.engine.rules_dir, "style_rules.yaml")
        self.assertIsInstance(data, dict)
        self.assertIn("vague_verbs", data)


if __name__ == "__main__":
    unittest.main()
