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

    def test_cross_role_repeat_kept_when_natural(self):
        # A verb may open one bullet in each of two roles; swapping it forced
        # object-blind verbs like "Governed strict confidentiality".
        data = {
            "EXPERIENCE": [
                {"company": "A", "achievements": ["Protected client tax records"]},
                {"company": "B", "achievements": ["Protected payroll timecards"]},
            ]
        }
        _fixed, modified = orchestrator.auto_fix_duplicate_opening_verbs(
            data, _style_rules()
        )
        self.assertFalse(modified)

    def test_third_cross_role_use_swapped(self):
        data = {
            "EXPERIENCE": [
                {"company": c, "achievements": [f"Organized {c} filing records"]}
                for c in ("A", "B", "C")
            ]
        }
        fixed, modified = orchestrator.auto_fix_duplicate_opening_verbs(
            data, _style_rules()
        )
        self.assertTrue(modified)
        verbs = [j["achievements"][0].split()[0] for j in fixed["EXPERIENCE"]]
        self.assertEqual(verbs[:2], ["Organized", "Organized"])
        self.assertNotEqual(verbs[2], "Organized")


class PromptRuleTests(unittest.TestCase):
    def test_tailor_prompt_bans_scope_inflation_and_allows_metricless(self):
        with open("resume-engine/prompts/tailor_resume.md", encoding="utf-8") as f:
            prompt = f.read()
        self.assertIn('never becomes "sole manager"', prompt)
        self.assertIn(
            "never drop or downrank a true bullet just because it has no metric", prompt
        )
        self.assertNotIn("no verb may open more than one bullet", prompt)


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
