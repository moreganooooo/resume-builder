"""Deterministic repairs must survive bullets pulled in by later repair steps."""

import os
import sys
import unittest

import yaml

SCRIPTS_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts"
)
sys.path.insert(0, SCRIPTS_DIR)

import orchestrator  # noqa: E402


def _style_rules() -> dict:
    with open("resume-engine/rules/style_rules.yaml", encoding="utf-8") as f:
        return yaml.safe_load(f)


class DuplicateVerbFallbackTests(unittest.TestCase):
    def test_verb_without_synonyms_still_swapped(self):
        data = {
            "EXPERIENCE": [
                {
                    "company": "A",
                    "achievements": [
                        "Secured 8-10 first meetings weekly by combining outreach",
                        "Secured confidential client records and managed retention",
                    ],
                }
            ]
        }
        fixed, modified = orchestrator.auto_fix_duplicate_opening_verbs(
            data, _style_rules()
        )
        self.assertTrue(modified)
        verbs = [b.split()[0].lower() for b in fixed["EXPERIENCE"][0]["achievements"]]
        self.assertEqual(len(set(verbs)), 2)


class LatePassTests(unittest.TestCase):
    def test_trailing_period_stripped_by_final_pass(self):
        data = {
            "EXPERIENCE": [
                {
                    "company": "A",
                    "achievements": [
                        "Managed a large territory portfolio using Salesforce dashboards."
                    ],
                }
            ]
        }
        fixed, _ = orchestrator._repair_strip_trailing_punctuation(
            data, ["Bullet ends with trailing punctuation"]
        )
        self.assertFalse(fixed["EXPERIENCE"][0]["achievements"][0].endswith("."))


if __name__ == "__main__":
    unittest.main()
