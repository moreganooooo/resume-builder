import os
import sys
import unittest

SCRIPTS_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts"
)
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
            self.engine.load_yaml(
                self.engine.rules_dir, "this_file_does_not_exist.yaml"
            )

    def test_load_yaml_still_loads_a_real_file(self):
        data = self.engine.load_yaml(self.engine.rules_dir, "style_rules.yaml")
        self.assertIsInstance(data, dict)
        self.assertIn("vague_verbs", data)


class TestKbAllowlistAndAuditPrefix(unittest.TestCase):

    def setUp(self):
        self.engine = orchestrator.ResumeEngine()

    def test_kb_allowlist_includes_new_curated_files(self):
        self.assertIn("voice-anchors.md", orchestrator.KB_ALLOWLIST)
        self.assertIn("detective-findings-trimmed.csv", orchestrator.KB_ALLOWLIST)

    def test_kb_allowlist_excludes_raw_detective_findings(self):
        # The raw file stays on disk as the trim script's source of truth,
        # but must never be wired in directly -- only the trimmed companion.
        self.assertNotIn("detective-findings.csv", orchestrator.KB_ALLOWLIST)

    def test_audit_prefix_default_excludes_evidence_guide(self):
        prefix = self.engine.build_audit_static_prefix()
        self.assertNotIn("EVIDENCE GUIDE", prefix)

    def test_audit_prefix_opt_in_includes_evidence_guide(self):
        prefix = self.engine.build_audit_static_prefix(include_evidence_guide=True)
        self.assertIn("EVIDENCE GUIDE", prefix)

    def test_audit_prefix_always_includes_voice_anchors(self):
        prefix = self.engine.build_audit_static_prefix()
        self.assertIn("VOICE ANCHORS", prefix)

    def test_critique_prompt_has_voice_calibration_reference(self):
        content = self.engine.load_prompt("critique_resume.md")
        self.assertIn("Voice Calibration Reference", content)
        self.assertIn("voice_calibration_example", content)

    def test_critique_prompt_has_distinctive_moments_step(self):
        content = self.engine.load_prompt("critique_resume.md")
        self.assertIn("Identify Distinctive Moments and Flat Sections", content)
        self.assertIn("distinctive_moments", content)
        self.assertIn("flat_sections", content)
        self.assertIn("Voice Calibration Reference", content)


if __name__ == "__main__":
    unittest.main()
