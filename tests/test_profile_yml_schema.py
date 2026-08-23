"""Schema validation for the ACTIVE profile's knowledge_base/profile.yml.

Rewritten 2026-08-23. This module used to read one specific person's
profile.yml and assert their six employers by name ("Mercor floor is 2",
"Inside Sales Team must fit page 1", "exactly three certifications"). Two
problems with that:

1. It only meant anything on that person's machine. For anyone else who
   clones this repo the assertions are false by construction, and the
   module's fallback branch called profile_paths._make_fallback_profile_yaml(),
   which no longer exists (the hardcoded-identity fallback was deleted).
2. Those are facts about a resume, not invariants of the format. If that
   person takes a new job, a *schema* test should not fail.

What is actually worth enforcing is the SHAPE the pipeline depends on:
orchestrator.build_role_rules_block() indexes role["name"]/["min_bullets"]/
["target_bullets"]/["page"]/["flex_priority"] and
credentials["certifications"][i]["issuer"] directly, so a profile.yml
missing any of them is a KeyError at build time rather than a clear error.

Skips cleanly when there is no profile.yml to validate (a fresh clone).
"""

import os
import sys
import unittest

import yaml

SCRIPTS_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts"
)
sys.path.insert(0, SCRIPTS_DIR)
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import profile_paths  # noqa: E402

# Fields orchestrator.build_role_rules_block() reads by direct subscript.
_REQUIRED_ROLE_FIELDS = (
    "name",
    "min_bullets",
    "target_bullets",
    "page",
    "flex_priority",
)
_REQUIRED_CERT_FIELDS = ("name", "issuer", "year")


def _active_profile_yaml():
    try:
        path = os.path.join(profile_paths.kb_dir(), "profile.yml")
    except ValueError:
        return None
    if not os.path.exists(path):
        return None
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


class TestActiveProfileYmlSchema(unittest.TestCase):
    """Validates whoever's profile is configured, not a fixed person's."""

    def setUp(self):
        self.data = _active_profile_yaml()
        if self.data is None:
            self.skipTest("No profile.yml to validate (profile not bootstrapped).")

    def test_roles_entries_carry_every_field_the_builder_indexes(self):
        roles = self.data.get("roles") or []
        if not roles:
            self.skipTest("Profile declares no roles yet.")
        for role in roles:
            for field in _REQUIRED_ROLE_FIELDS:
                self.assertIn(
                    field,
                    role,
                    f"role {role.get('name', '<unnamed>')!r} is missing {field!r} -- "
                    "build_role_rules_block() reads it by direct subscript",
                )

    def test_role_names_are_unique(self):
        """Roles are indexed by name in build_role_rules_block() and in
        mine_bullet_bank()'s per-company minimums; a duplicate silently
        wins over the other."""
        names = [r.get("name") for r in (self.data.get("roles") or [])]
        self.assertEqual(len(names), len(set(names)), f"duplicate role names: {names}")

    def test_role_page_and_bullet_counts_are_sane(self):
        for role in self.data.get("roles") or []:
            with self.subTest(role=role.get("name")):
                self.assertGreaterEqual(role.get("min_bullets", 0), 0)
                self.assertGreaterEqual(
                    role.get("target_bullets", 0), role.get("min_bullets", 0)
                )
                self.assertIn(role.get("page"), (1, 2))

    def test_certifications_carry_every_field_the_builder_indexes(self):
        creds = self.data.get("fixed_credentials") or {}
        for cert in creds.get("certifications") or []:
            for field in _REQUIRED_CERT_FIELDS:
                self.assertIn(
                    field,
                    cert,
                    f"certification {cert!r} is missing {field!r} -- "
                    "build_role_rules_block() reads it by direct subscript",
                )

    def test_education_entries_declare_an_institution_and_bullet_count(self):
        creds = self.data.get("fixed_credentials") or {}
        for entry in creds.get("education") or []:
            with self.subTest(entry=entry.get("institution")):
                self.assertTrue(entry.get("institution"))
                self.assertIsInstance(entry.get("bullet_count", 0), int)

    def test_protected_bullets_are_prose_not_urls(self):
        """These are bullet descriptions the builder must never drop, e.g.
        "Outreach.io full platform ownership...". A URL here means someone
        pasted a link where prose was expected, and the match that consumes
        them is a word-boundary search over text."""
        for bullet in self.data.get("protected_bullets") or []:
            self.assertIsInstance(bullet, str)
            self.assertFalse(
                bullet.strip().startswith(("http://", "https://")),
                f"protected_bullets entry looks like a URL: {bullet!r}",
            )


class TestPersonaProfileYmlIsValid(unittest.TestCase):
    """The test persona must itself satisfy the schema -- otherwise every
    sandboxed test is exercising a profile shape that could never exist."""

    def test_candidate_block_has_the_contact_fields_renderers_require(self):
        import persona

        candidate = persona.candidate_block()
        for field in ("full_name", "email", "phone", "location", "linkedin"):
            self.assertTrue(candidate.get(field), f"persona missing {field}")


if __name__ == "__main__":
    unittest.main()
