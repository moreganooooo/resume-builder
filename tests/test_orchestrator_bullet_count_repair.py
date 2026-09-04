"""Deterministic Bullet Count repair -- see repair_violations_surgically's
"8. Deterministic Bullet Count Repair" block.

validate_resume._check_bullet_counts()'s own docstring names this exact
failure mode as "observed live" (VML / Callahan Creek shipping 2 bullets
against a declared min_bullets of 3), but until now no repair existed for
it at all -- the LLM full-resume retry loop restated its instruction on
every attempt and it survived all 4, failing the whole build (fatal per
partition_violations). Confirmed live 2026-09-04: after the metric-dedup
and keyword-density repairs (and the temperature-forcing fix) resolved
everything else, this violation alone still survived to the end.

Uses synthetic company/bullet data throughout -- not the active profile's
real employers -- per tests/test_no_operator_identity.py's "use synthetic
data, not the operator's own history" rule.
"""

import os
import sys
import unittest

SCRIPTS_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts"
)
sys.path.insert(0, SCRIPTS_DIR)

import orchestrator  # noqa: E402
import validate_resume  # noqa: E402


class TestBulletCountRepair(unittest.TestCase):

    def _resume(self):
        return {
            "SUMMARY_TEXT": "Generalist marketer with a track record of measurable growth.",
            "EXPERIENCE": [
                {
                    "title": "Widget Marketer",
                    "company": "Widgetco",
                    "period": "Jan 2020 - Present",
                    "location": "Remote",
                    "achievements": [
                        "Grew territory revenue by 40%.",
                        "Launched a new outbound sequence library.",
                    ],
                    "career_note": "",
                }
            ],
            "SKILLS": [],
        }

    def _bullet_tuples(self):
        return [
            ("Grew territory revenue by 40%.", "Widgetco", "growth"),
            ("Launched a new outbound sequence library.", "Widgetco", "content"),
            ("Trained 3 new hires on the outbound playbook.", "Widgetco", "leadership"),
            ("Standardized reporting across 4 regional teams.", "Widgetco", "ops"),
        ]

    def test_pulls_additional_bullets_up_to_minimum(self):
        resume_data = self._resume()
        role_bullet_minimums = {"Widgetco": 3}
        violations = validate_resume._check_bullet_counts(
            resume_data, role_bullet_minimums
        )
        self.assertTrue(any(v.startswith("Bullet count:") for v in violations))

        fixed, remaining = orchestrator.repair_violations_surgically(
            resume_data,
            violations,
            {},
            role_bullet_minimums=role_bullet_minimums,
            bullet_tuples=self._bullet_tuples(),
        )

        achievements = fixed["EXPERIENCE"][0]["achievements"]
        self.assertEqual(len(achievements), 3)
        self.assertIn("Trained 3 new hires on the outbound playbook.", achievements)
        self.assertFalse(any(v.startswith("Bullet count:") for v in remaining))

    def test_stops_at_declared_maximum(self):
        resume_data = self._resume()
        role_bullet_minimums = {"Widgetco": 3}
        role_bullet_maximums = {"Widgetco": 2}
        violations = validate_resume._check_bullet_counts(
            resume_data, role_bullet_minimums, role_bullet_maximums
        )

        fixed, _remaining = orchestrator.repair_violations_surgically(
            resume_data,
            violations,
            {},
            role_bullet_minimums=role_bullet_minimums,
            bullet_tuples=self._bullet_tuples(),
            role_bullet_maximums=role_bullet_maximums,
        )

        # A declared ceiling below the floor is a contradictory config --
        # the repair must not add bullets past the ceiling even though the
        # minimum was never reached.
        self.assertEqual(len(fixed["EXPERIENCE"][0]["achievements"]), 2)

    def test_no_spare_bullets_leaves_violation_for_llm_loop(self):
        resume_data = self._resume()
        role_bullet_minimums = {"Widgetco": 3}
        violations = validate_resume._check_bullet_counts(
            resume_data, role_bullet_minimums
        )

        # Bank only knows about the two bullets already present.
        bullet_tuples = [
            ("Grew territory revenue by 40%.", "Widgetco", "growth"),
            ("Launched a new outbound sequence library.", "Widgetco", "content"),
        ]

        fixed, remaining = orchestrator.repair_violations_surgically(
            resume_data,
            violations,
            {},
            role_bullet_minimums=role_bullet_minimums,
            bullet_tuples=bullet_tuples,
        )

        self.assertEqual(
            fixed["EXPERIENCE"][0]["achievements"],
            resume_data["EXPERIENCE"][0]["achievements"],
        )
        self.assertTrue(any(v.startswith("Bullet count:") for v in remaining))


if __name__ == "__main__":
    unittest.main()
