import os
import unittest
import yaml

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RULES_DIR = os.path.join(PROJECT_ROOT, "resume-engine", "rules")


def _load(filename):
    with open(os.path.join(RULES_DIR, filename), "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


class TestVerbRuleConsistency(unittest.TestCase):

    def setUp(self):
        self.style_rules = _load("style_rules.yaml")
        self.language_quality = _load("language_quality.yaml")
        self.verb_taxonomy = _load("verb_taxonomy.yaml")
        self.verb_intent_mapping = _load("verb_intent_mapping.yaml")
        self.vague_verbs = set(self.style_rules["vague_verbs"])

    def test_no_vague_verb_recommended_as_an_upgrade_in_language_quality(self):
        for weak_verb, entry in self.language_quality["weak_verbs"].items():
            for suggestion in entry.get("preferred", []):
                self.assertNotIn(
                    suggestion, self.vague_verbs,
                    f"language_quality.yaml recommends vague verb '{suggestion}' as an upgrade for '{weak_verb}'"
                )

    def test_no_vague_verb_in_language_quality_elite_verbs(self):
        for v in self.language_quality["elite_verbs"]:
            self.assertNotIn(v, self.vague_verbs)

    def test_leverage_and_utilized_are_medium_risk_not_high_in_language_quality(self):
        # Reversed from an earlier decision that hard-banned these via
        # style_rules.yaml's forbidden_phrases: a real run showed the hard
        # gate discarding an otherwise-good, specific bullet ("Leveraged
        # Claude to draft...") purely for containing "leveraged". Unlike the
        # cliches elsewhere in high_risk/forbidden_phrases, these are real
        # verbs that can be the clearest way to name actual tool usage, so
        # they're a softer nudge (medium_risk) rather than an unconditional
        # hard gate -- not absent from guidance entirely.
        buzzwords = self.language_quality["buzzwords"]
        self.assertNotIn("leverage", buzzwords.get("high_risk", []))
        self.assertNotIn("utilized", buzzwords.get("high_risk", []))
        self.assertIn("leverage", buzzwords.get("medium_risk", []))
        self.assertIn("utilized", buzzwords.get("medium_risk", []))
        self.assertNotIn("leverage", self.style_rules["forbidden_phrases"])
        self.assertNotIn("utilized", self.style_rules["forbidden_phrases"])

    def test_no_vague_verb_in_verb_taxonomy_positive_tiers(self):
        positive_tiers = (
            self.verb_taxonomy["universal"]
            + self.verb_taxonomy["priority_tiers"]["elite"]
            + self.verb_taxonomy["priority_tiers"]["strong"]
            + self.verb_taxonomy["priority_tiers"]["acceptable"]
        )
        for v in positive_tiers:
            self.assertNotIn(v, self.vague_verbs)

    def test_no_vague_verb_in_verb_intent_mapping_preferred_verbs(self):
        for intent, config in self.verb_intent_mapping["intent_categories"].items():
            preferred = config.get("preferred_verbs", {})
            for tier_name, verbs in preferred.items():
                for v in verbs:
                    self.assertNotIn(
                        v, self.vague_verbs,
                        f"verb_intent_mapping.yaml's '{intent}.{tier_name}' recommends vague verb '{v}'"
                    )

    def test_style_rules_recommended_verbs_list_has_no_self_contradiction(self):
        recommended_dict = next(
            (r for r in self.style_rules["verb_rules"] if isinstance(r, dict) and "Recommended verbs" in r),
            None
        )
        self.assertIsNotNone(recommended_dict, "Could not find Recommended verbs in verb_rules")
        recommended_line = recommended_dict["Recommended verbs"]
        recommended = {v.strip() for v in recommended_line.split(",")}
        overlap = {v for v in recommended if v.lower() in self.vague_verbs}
        self.assertEqual(overlap, set(), f"style_rules.yaml's own Recommended verbs list contains vague verbs: {overlap}")


if __name__ == "__main__":
    unittest.main()
