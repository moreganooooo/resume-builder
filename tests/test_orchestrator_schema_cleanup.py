import os
import sys
import unittest

SCRIPTS_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts")
sys.path.insert(0, SCRIPTS_DIR)

import orchestrator  # noqa: E402
from gemini_client import GeminiClient  # noqa: E402


class TestSchemaCleanup(unittest.TestCase):

    def test_project_item_model_no_longer_exists(self):
        self.assertFalse(hasattr(orchestrator, "ProjectItem"))

    def test_skills_relevance_score_description_has_no_stale_competencies_reference(self):
        field = orchestrator.ResumeCritiqueSchema.model_fields["skills_relevance_score"]
        self.assertNotIn("Competencies", field.description)

    def test_achievement_key_fields_survive_sanitize_schema_as_enums(self):
        """
        Regression test: KU_ACHIEVEMENT_KEY and KCKCC_ACHIEVEMENT_KEY must be
        typed so the model actually learns the valid option strings. Plain
        `str` fields only carry that information in `description`, which
        GeminiClient.sanitize_schema() strips before the schema ever reaches
        Gemini's responseSchema -- silently defeating archetype selection.
        Literal[...] fields serialize to an `enum` key, which sanitize_schema
        does NOT strip, so the constraint survives to the model.
        """
        raw_schema = orchestrator.TemplateSchema.model_json_schema()
        sanitized = GeminiClient.sanitize_schema(raw_schema)
        props = sanitized["properties"]

        ku_field = props["KU_ACHIEVEMENT_KEY"]
        self.assertIn("enum", ku_field)
        self.assertEqual(set(ku_field["enum"]), {"content_generalist", "email_ops", "content"})

        kckcc_field = props["KCKCC_ACHIEVEMENT_KEY"]
        self.assertIn("enum", kckcc_field)
        self.assertEqual(set(kckcc_field["enum"]), {"writing_content", "enablement_mgmt", "generalist"})


if __name__ == "__main__":
    unittest.main()
