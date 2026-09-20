"""Tagline descriptors come from the active profile's archetype library, not
from one marketing profile's list hardcoded in tailor_resume.md."""

import os
import sys
import unittest

import yaml

ROOT = os.path.join(os.path.dirname(__file__), "..")
sys.path.insert(0, os.path.join(ROOT, "scripts"))

import orchestrator  # noqa: E402


class TestTaglineDescriptors(unittest.TestCase):
    def test_block_lists_each_archetype_descriptor(self):
        block = orchestrator.build_tagline_descriptor_block(
            {
                "archetypes": {
                    "a": {
                        "label": "Analyst",
                        "tagline_descriptor": "Reporting & Insight",
                    },
                    "b": {"label": "No descriptor"},
                }
            }
        )
        self.assertIn("=== TAGLINE DESCRIPTORS ===", block)
        self.assertIn('Analyst -> "Reporting & Insight"', block)
        self.assertNotIn("No descriptor", block)

    def test_no_descriptors_means_no_block(self):
        self.assertEqual(
            orchestrator.build_tagline_descriptor_block(
                {"archetypes": {"a": {"label": "X"}}}
            ),
            "",
        )
        self.assertEqual(orchestrator.build_tagline_descriptor_block(None), "")

    def test_prompt_hardcodes_no_field_specific_descriptors(self):
        with open(
            os.path.join(ROOT, "resume-engine", "prompts", "tailor_resume.md")
        ) as f:
            prompt = f.read()
        with open(os.path.join(ROOT, "resume-engine", "scoring", "role_dna.yaml")) as f:
            shared = yaml.safe_load(f)["archetypes"]
        for cfg in shared.values():
            self.assertTrue(cfg.get("tagline_descriptor"), cfg.get("label"))
            self.assertNotIn(cfg["tagline_descriptor"], prompt)


if __name__ == "__main__":
    unittest.main()
