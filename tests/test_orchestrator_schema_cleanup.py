import os
import sys
import unittest

SCRIPTS_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts"
)
sys.path.insert(0, SCRIPTS_DIR)
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import orchestrator  # noqa: E402
from gemini_client import GeminiClient  # noqa: E402


class TestSchemaCleanup(unittest.TestCase):

    def test_project_item_model_no_longer_exists(self):
        self.assertFalse(hasattr(orchestrator, "ProjectItem"))

    def test_skills_relevance_score_description_has_no_stale_competencies_reference(
        self,
    ):
        field = orchestrator.ResumeCritiqueSchema.model_fields["skills_relevance_score"]
        self.assertNotIn("Competencies", field.description)

    def test_education_achievement_schema_fields_survive_sanitize_schema_as_enums(self):
        """
        Regression test (successor to the old KU_ACHIEVEMENT_KEY/
        KCKCC_ACHIEVEMENT_KEY version, removed 2026-07-17 when those became
        per-profile EDU_ACHIEVEMENT_KEY_<n> fields instead of hardcoded
        Literal fields on TemplateSchema -- see
        ResumeEngine.build_education_achievement_schema_fields()). These
        fields must be typed so the model actually learns the valid option
        strings. Plain `str` fields only carry that information in
        `description`, which GeminiClient.sanitize_schema() strips before
        the schema ever reaches Gemini's responseSchema -- silently
        defeating archetype selection. An actual `enum` key survives
        sanitize_schema, so the constraint reaches the model.
        """
        # Sandboxed: the slot count comes from the ACTIVE profile's
        # fixed_credentials.education, so on a freshly bootstrapped profile
        # there are zero slots and this asserted nothing.
        import persona

        with persona.sandbox_profile():
            engine = orchestrator.ResumeEngine()
            properties, required = engine.build_education_achievement_schema_fields()
        self.assertEqual(required, ["EDU_ACHIEVEMENT_KEY_1", "EDU_ACHIEVEMENT_KEY_2"])

        raw_schema = orchestrator.TemplateSchema.model_json_schema()
        raw_schema["properties"] = {**raw_schema["properties"], **properties}
        raw_schema["required"] = list(raw_schema["required"]) + required
        sanitized = GeminiClient.sanitize_schema(raw_schema)
        props = sanitized["properties"]

        # Expected option keys come from the persona profile the schema was
        # built against, rather than being restated here -- restating them
        # meant the test encoded one person's education choices and had to
        # be edited whenever those changed.
        education = persona.fixed_credentials()["education"]
        slots = [e for e in education if e.get("achievement_options")]

        first = props["EDU_ACHIEVEMENT_KEY_1"]
        self.assertIn("enum", first)
        self.assertEqual(set(first["enum"]), set(slots[0]["achievement_options"]))

        second = props["EDU_ACHIEVEMENT_KEY_2"]
        self.assertIn("enum", second)
        self.assertEqual(set(second["enum"]), set(slots[1]["achievement_options"]))

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
        self.assertIn(
            "$defs",
            raw_schema,
            "test setup check: Pydantic should still emit $defs for a nested model",
        )

        resolved = GeminiClient.resolve_refs(raw_schema)
        sanitized = GeminiClient.sanitize_schema(resolved)

        self.assertNotIn("$defs", sanitized)
        exp_items = sanitized["properties"]["EXPERIENCE"]["items"]
        self.assertNotIn("$ref", exp_items)
        self.assertEqual(
            set(exp_items["required"]), {"title", "company", "period", "achievements"}
        )
        self.assertEqual(exp_items["properties"]["achievements"]["type"], "array")
        # Every required property must actually still exist in "properties" --
        # this is the exact invariant sanitize_schema violated when it treated
        # the "title" *property name* (job title) as the UNSUPPORTED $schema
        # "title" keyword and deleted it, leaving "required" pointing at a
        # property that no longer existed (Gemini rejected this with
        # "property is not defined").
        for required_field in exp_items["required"]:
            self.assertIn(
                required_field,
                exp_items["properties"],
                f"{required_field!r} is required but missing from properties",
            )

    def test_resolve_refs_raises_on_unresolvable_ref(self):
        with self.assertRaises(ValueError):
            GeminiClient.resolve_refs(
                {"properties": {"x": {"$ref": "#/$defs/Missing"}}}
            )

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

    def test_resume_critique_schema_has_sparkle_fields(self):
        fields = orchestrator.ResumeCritiqueSchema.model_fields
        self.assertIn("distinctive_moments", fields)
        self.assertIn("flat_sections", fields)

    def test_recommendation_apply_schema_has_needs_personal_input(self):
        fields = orchestrator.RecommendationApplySchema.model_fields
        self.assertIn("needs_personal_input", fields)


class TestSanitizeNoneForPrompt(unittest.TestCase):
    """
    A real run's Why section rendered the literal word "null" instead of
    being dropped: a stray Python None in WHY_TEXT got json.dumps()'d into
    a *later* trim prompt as the unquoted JSON token null, and the model
    echoed that back as the literal string "null". Stripping None before
    every re-dump means the model never sees a raw null to mis-copy.
    """

    def test_replaces_top_level_none_with_empty_string(self):
        result = orchestrator._sanitize_none_for_prompt(
            {"WHY_TEXT": None, "TAGLINE": "Real value"}
        )
        self.assertEqual(result, {"WHY_TEXT": "", "TAGLINE": "Real value"})

    def test_replaces_none_nested_in_lists_and_dicts(self):
        result = orchestrator._sanitize_none_for_prompt(
            {
                "EXPERIENCE": [{"title": "X", "career_note": None}],
            }
        )
        self.assertEqual(result["EXPERIENCE"][0]["career_note"], "")

    def test_does_not_mutate_the_input(self):
        original = {"WHY_TEXT": None}
        orchestrator._sanitize_none_for_prompt(original)
        self.assertIsNone(original["WHY_TEXT"])


if __name__ == "__main__":
    unittest.main()
