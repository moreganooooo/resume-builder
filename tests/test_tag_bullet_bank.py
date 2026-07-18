import os
import sys
import unittest

SCRIPTS_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts")
sys.path.insert(0, SCRIPTS_DIR)

import tag_bullet_bank  # noqa: E402


class TestTagBulletBankReadsProfileYaml(unittest.TestCase):
    """
    Regression tests: TAG_KEYWORDS/FALLBACK_TAG used to be hardcoded module
    constants here, duplicating (and, by 2026-07-17, already drifted from)
    orchestrator.py's/rewrite_bullets.py's own separate copies of the same
    marketing-specific taxonomy. Both tag_keywords() and fallback_tag() now
    read profile.yml's tags: instead -- these confirm the real (Morgan)
    profile still produces sane, unbroken tagging.
    """

    def test_assigns_a_confident_single_tag_on_a_unique_keyword_hit(self):
        tag_str, needs_review = tag_bullet_bank.assign_tags(
            "Owned Outreach.io as primary admin, led Salesforce integration and territory reporting."
        )
        self.assertEqual(tag_str, "[ops]")
        self.assertFalse(needs_review)

    def test_falls_back_to_the_catch_all_tag_when_nothing_matches(self):
        tag_str, needs_review = tag_bullet_bank.assign_tags("Completely unrelated text with zero keyword hits.")
        self.assertEqual(tag_str, tag_bullet_bank.fallback_tag())
        self.assertFalse(needs_review)

    def test_fallback_tag_has_empty_keywords_in_the_real_taxonomy(self):
        keywords_by_tag = tag_bullet_bank.tag_keywords()
        self.assertEqual(keywords_by_tag[tag_bullet_bank.fallback_tag()], [])

    def test_score_bullet_accepts_an_explicit_taxonomy_without_reloading_profile_yaml(self):
        fake_taxonomy = {"[widgets]": ["widget", "gadget"], "[generalist]": []}
        scores = tag_bullet_bank.score_bullet("Built and shipped a new widget pipeline.", fake_taxonomy)
        self.assertIn("[widgets]", scores)
        self.assertNotIn("[generalist]", scores)


if __name__ == "__main__":
    unittest.main()
