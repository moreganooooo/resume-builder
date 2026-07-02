import os
import sys
import unittest

SCRIPTS_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts")
sys.path.insert(0, SCRIPTS_DIR)

import orchestrator  # noqa: E402


class TestSchemaCleanup(unittest.TestCase):

    def test_project_item_model_no_longer_exists(self):
        self.assertFalse(hasattr(orchestrator, "ProjectItem"))

    def test_skills_relevance_score_description_has_no_stale_competencies_reference(self):
        field = orchestrator.ResumeCritiqueSchema.model_fields["skills_relevance_score"]
        self.assertNotIn("Competencies", field.description)


if __name__ == "__main__":
    unittest.main()
