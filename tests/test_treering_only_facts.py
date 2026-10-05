"""Treering-only facts must not sit under any other company in the bullet banks."""

import csv
import os
import unittest

from scripts import profile_paths, validate_resume

TREERING_ONLY = ("Grammarly", "14-category")
BANKS = ("bullet-bank-keepers.csv", "bullet-bank-keepers-audited.csv")


class TreeringOnlyFactsTests(unittest.TestCase):
    def test_no_treering_only_fact_under_another_company(self):
        kb_dir = profile_paths.kb_dir()
        checked = 0
        leaks = []
        for name in BANKS:
            path = os.path.join(kb_dir, name)
            if not os.path.exists(path):
                continue
            with open(path, newline="") as f:
                rows = list(csv.reader(f))
            checked += 1
            header = rows[0]
            b_idx = next(
                i for i, h in enumerate(header) if h in ("Bullet Point", "bullet")
            )
            c_idx = next(
                i
                for i, h in enumerate(header)
                if h.startswith("Role / Company") or h == "company"
            )
            for n, row in enumerate(rows[1:], 2):
                if "Treering" in row[c_idx]:
                    continue
                if any(t in row[b_idx] for t in TREERING_ONLY):
                    leaks.append(f"{name}:{n} [{row[c_idx]}] {row[b_idx][:80]}")
        if not checked:
            self.skipTest("no bullet bank present for this profile")
        self.assertEqual(leaks, [])


if __name__ == "__main__":
    unittest.main()


class SelfTaughtSummaryWhyTests(unittest.TestCase):
    def _violations(self, **fields):
        import json
        import tempfile

        from scripts import validate_resume

        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "verified_tools.json")
            with open(path, "w") as f:
                json.dump(
                    {"tools": [{"name": "HubSpot", "employer": "Self / Profile"}]}, f
                )
            return validate_resume._check_self_taught_claims_in_summary_why(
                fields, path
            )

    def test_paragraph_break_does_not_hide_claim_behind_learning_word(self):
        why = (
            "<p>I expanded access to collaborative learning.</p>"
            "<p>This means leveraging advanced HubSpot automation.</p>"
        )
        self.assertTrue(self._violations(WHY_TEXT=why))

    def test_certified_environments_and_extensive_experience_are_claims(self):
        self.assertTrue(
            self._violations(
                SUMMARY_TEXT="I've owned CRM in HubSpot-certified environments."
            )
        )
        self.assertTrue(
            self._violations(
                SUMMARY_TEXT="Extensive experience building HubSpot workflows."
            )
        )

    def test_learning_framing_still_allowed(self):
        self.assertEqual(
            self._violations(
                SUMMARY_TEXT="Self-taught in HubSpot, with a goal to learn more."
            ),
            [],
        )


class VerbFitAndDuplicateTests(unittest.TestCase):
    def test_migrated_on_documents_is_flagged(self):
        resume = {
            "EXPERIENCE": [
                {
                    "achievements": [
                        "Migrated and corrected CH2M Hill inspection forms to boost data integrity"
                    ]
                }
            ]
        }
        self.assertTrue(validate_resume._check_verb_fit(resume))

    def test_migrated_between_systems_is_allowed(self):
        resume = {
            "EXPERIENCE": [
                {
                    "achievements": [
                        "Migrated 40K contact records from HubSpot into Salesforce"
                    ]
                }
            ]
        }
        self.assertEqual(validate_resume._check_verb_fit(resume), [])

    def test_executed_team_is_flagged(self):
        resume = {"EXPERIENCE": [{"achievements": ["Executed a team of 12 reps"]}]}
        self.assertTrue(validate_resume._check_verb_fit(resume))

    def test_verb_swapped_duplicate_is_caught(self):
        resume = {
            "EXPERIENCE": [
                {
                    "company": "KU",
                    "achievements": [
                        "Answered confidential telephone support inquiries from university employees for payroll questions",
                        "Fielded telephone support for payroll questions from university employees",
                    ],
                }
            ]
        }
        self.assertTrue(validate_resume._check_near_duplicate_bullets(resume))
