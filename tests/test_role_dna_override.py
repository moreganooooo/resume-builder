"""A profile's own role_dna.yaml replaces the shared (marketing) library in
the evaluator's context -- a data-science profile's evaluations were being
told to pick from marketing archetypes."""

import os
import shutil
import sys
import tempfile
import unittest
from unittest.mock import patch

import yaml

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))

import orchestrator  # noqa: E402


class TestRoleDnaOverride(unittest.TestCase):
    def setUp(self):
        self.kb = tempfile.mkdtemp()
        self.shared = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.kb, True)
        self.addCleanup(shutil.rmtree, self.shared, True)
        with open(os.path.join(self.shared, "role_dna.yaml"), "w") as f:
            yaml.safe_dump(
                {"archetypes": {"shared_marketing_archetype": {"label": "M"}}}, f
            )
        self.engine = orchestrator.ResumeEngine.__new__(orchestrator.ResumeEngine)
        self.engine.kb_dir = self.kb
        self.engine.scoring_dir = self.shared

    def _context(self):
        with (
            patch("skills_menu._load_verified_tools", return_value={"tools": []}),
            patch("profile_paths.profile_yaml", return_value={}),
        ):
            return self.engine.build_fit_evaluation_context("A data science posting.")

    def test_shared_library_is_used_without_a_profile_override(self):
        self.assertIn("shared_marketing_archetype", self._context())

    def test_profile_library_replaces_the_shared_one(self):
        with open(os.path.join(self.kb, "role_dna.yaml"), "w") as f:
            yaml.safe_dump(
                {"archetypes": {"data_scientist_modeling": {"label": "DS"}}}, f
            )
        context = self._context()
        self.assertIn("data_scientist_modeling", context)
        self.assertNotIn("shared_marketing_archetype", context)


if __name__ == "__main__":
    unittest.main()
