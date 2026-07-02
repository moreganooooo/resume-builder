import os
import sys
import unittest

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RULES_DIR = os.path.join(PROJECT_ROOT, "resume-engine", "rules")
SCRIPTS_DIR = os.path.join(PROJECT_ROOT, "scripts")
sys.path.insert(0, SCRIPTS_DIR)

import orchestrator  # noqa: E402


class TestRetiredRuleFiles(unittest.TestCase):

    def test_formatting_rules_yaml_no_longer_exists(self):
        self.assertFalse(os.path.exists(os.path.join(RULES_DIR, "formatting_rules.yaml")))

    def test_ats_rules_yaml_no_longer_exists(self):
        self.assertFalse(os.path.exists(os.path.join(RULES_DIR, "ats_rules.yaml")))

    def test_bullet_audit_static_prefix_has_no_dedicated_ats_rules_block(self):
        engine = orchestrator.ResumeEngine()
        critique_system = engine.build_bullet_critique_system()
        self.assertNotIn("ATS RULES:", critique_system)
        self.assertIn("STYLE RULES", critique_system.upper())  # style_rules.yaml's ats_rules: section still covers this


if __name__ == "__main__":
    unittest.main()
