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

    def test_experience_entry_required_fields_survive_ref_resolution_and_sanitize(self):
        """
        Regression test: EXPERIENCE used to be List[dict], which has no
        required sub-properties at all, so an empty {} is fully valid
        against what Gemini actually receives -- a real run got EXPERIENCE
        back as several empty objects. EXPERIENCE is now List[ExperienceEntry],
        a nested Pydantic model, which Pydantic serializes as
        items: {"$ref": "#/$defs/ExperienceEntry"}. sanitize_schema() deletes
        $defs unconditionally, so resolve_refs() must inline the ref *before*
        sanitize_schema runs, or the schema sent to Gemini would have a
        dangling $ref (the likely actual cause of the "nested $defs caused a
        400" this schema used to avoid).
        """
        raw_schema = orchestrator.TemplateSchema.model_json_schema()
        self.assertIn("$defs", raw_schema, "test setup check: Pydantic should still emit $defs for a nested model")

        resolved = GeminiClient.resolve_refs(raw_schema)
        sanitized = GeminiClient.sanitize_schema(resolved)

        self.assertNotIn("$defs", sanitized)
        exp_items = sanitized["properties"]["EXPERIENCE"]["items"]
        self.assertNotIn("$ref", exp_items)
        self.assertEqual(set(exp_items["required"]), {"title", "company", "period", "achievements"})
        self.assertEqual(exp_items["properties"]["achievements"]["type"], "array")
        # Every required property must actually still exist in "properties" --
        # this is the exact invariant sanitize_schema violated when it treated
        # the "title" *property name* (job title) as the UNSUPPORTED $schema
        # "title" keyword and deleted it, leaving "required" pointing at a
        # property that no longer existed (Gemini rejected this with
        # "property is not defined").
        for required_field in exp_items["required"]:
            self.assertIn(required_field, exp_items["properties"],
                          f"{required_field!r} is required but missing from properties")

    def test_resolve_refs_raises_on_unresolvable_ref(self):
        with self.assertRaises(ValueError):
            GeminiClient.resolve_refs({"properties": {"x": {"$ref": "#/$defs/Missing"}}})

    def test_sanitize_schema_preserves_property_named_title(self):
        """
        Regression test: a field literally named "title" (ExperienceEntry's
        job title) collides with the UNSUPPORTED "title" $schema metadata
        keyword. sanitize_schema() must only strip "title" as metadata, never
        as a key inside "properties" (where keys are field names).
        """
        schema = {
            "type": "object",
            "properties": {
                "title": {"title": "Title", "type": "string"},
                "company": {"title": "Company", "type": "string"},
            },
            "required": ["title", "company"],
        }
        sanitized = GeminiClient.sanitize_schema(schema)
        self.assertIn("title", sanitized["properties"])
        self.assertEqual(sanitized["properties"]["title"], {"type": "string"})


if __name__ == "__main__":
    unittest.main()
