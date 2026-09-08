"""Metric Provenance check + repair -- see validate_resume._check_metric_
provenance() and orchestrator's "10. Targeted Metric Provenance Repair"
block.

Covers a real fabrication observed live 2026-09-04: a Callahan Creek bullet
about a self-directed personal JSON project ("Self-Directed JSON Projects:
Built personal projects using JSON for data structuring and dynamic content
mockups...") came back from the tailoring generation step as "Standardized
campaign templates by building JSON-based content mockups, increasing
content scalability across 100+ assets" -- a "100+ assets" figure that
never appeared anywhere in that bullet's source text. It only ever appeared
in a completely unrelated Treering Yearbooks bullet, meaning the model
cross-contaminated two different companies' bullets into one fabricated
claim. No existing guardrail (_check_hallucinated_tools only covers the
SKILLS section) caught this.

Uses synthetic company/bullet data throughout -- not the active profile's
real employers -- per tests/test_no_operator_identity.py's "use synthetic
data, not the operator's own history" rule.
"""

import os
import sys
import unittest
from unittest.mock import patch

SCRIPTS_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts"
)
sys.path.insert(0, SCRIPTS_DIR)

import orchestrator  # noqa: E402
import validate_resume  # noqa: E402


class TestMetricProvenanceCheck(unittest.TestCase):
    def _bullet_tuples(self):
        return [
            (
                "Self-Directed JSON Projects: Built personal projects using "
                "JSON for data structuring and dynamic content mockups.",
                "Widgetco Creative",
                "content",
            ),
            (
                "Architected a sales enablement content library spanning "
                "100+ assets for the field team.",
                "Yearbook Print Co",
                "content",
            ),
        ]

    def _resume(self, bullet):
        return {
            "SUMMARY_TEXT": "Generalist marketer with a track record of measurable growth.",
            "EXPERIENCE": [
                {
                    "title": "Content Marketer",
                    "company": "Widgetco Creative",
                    "period": "Jan 2020 - Present",
                    "location": "Remote",
                    "achievements": [bullet],
                    "career_note": "",
                }
            ],
            "SKILLS": [],
        }

    def test_flags_metric_borrowed_from_a_different_company(self):
        bullet = (
            "Standardized campaign templates by building JSON-based content "
            "mockups, increasing content scalability across 100+ assets"
        )
        resume_data = self._resume(bullet)
        violations = validate_resume._check_metric_provenance(
            resume_data, self._bullet_tuples()
        )
        self.assertTrue(
            any(
                v.startswith("Metric '100+'") and "Widgetco Creative" in v
                for v in violations
            )
        )

    def test_metric_present_in_same_companys_source_is_allowed(self):
        resume_data = self._resume(
            "Architected a sales enablement content library spanning 100+ "
            "assets for the field team"
        )
        bullet_tuples = [
            (
                "Architected a sales enablement content library spanning "
                "100+ assets for the field team.",
                "Widgetco Creative",
                "content",
            ),
        ]
        violations = validate_resume._check_metric_provenance(
            resume_data, bullet_tuples
        )
        self.assertEqual(violations, [])

    def test_no_bullet_tuples_is_inert(self):
        resume_data = self._resume("Did some things with 100+ assets")
        self.assertEqual(
            validate_resume._check_metric_provenance(resume_data, None), []
        )

    def test_bullet_with_no_metric_never_flagged(self):
        resume_data = self._resume(
            "Built personal projects using JSON for data structuring and "
            "dynamic content mockups"
        )
        violations = validate_resume._check_metric_provenance(
            resume_data, self._bullet_tuples()
        )
        self.assertEqual(violations, [])


class TestMetricProvenanceRepair(unittest.TestCase):
    def _bullet_tuples(self):
        return [
            (
                "Built personal projects using JSON for data structuring "
                "and dynamic content mockups.",
                "Widgetco Creative",
                "content",
            ),
        ]

    def _resume(self, bullet):
        return {
            "SUMMARY_TEXT": "Generalist marketer with a track record of measurable growth.",
            "EXPERIENCE": [
                {
                    "title": "Content Marketer",
                    "company": "Widgetco Creative",
                    "period": "Jan 2020 - Present",
                    "location": "Remote",
                    "achievements": [
                        "Standardized campaign templates by building "
                        "JSON-based content mockups, increasing content "
                        "scalability across 100+ assets",
                        "Did other unrelated work.",
                    ],
                    "career_note": "",
                }
            ],
            "SKILLS": [],
        }

    @patch("orchestrator.GeminiClient.generate")
    def test_fabricated_bullet_is_rewritten_from_real_source(self, mock_generate):
        bullet_tuples = self._bullet_tuples()
        resume_data = self._resume(bullet_tuples[0][0])
        violations = validate_resume._check_metric_provenance(
            resume_data, bullet_tuples
        )
        self.assertTrue(len(violations) == 1)

        mock_generate.return_value = (
            "Built personal projects using JSON for data structuring and "
            "dynamic content mockups",
            {},
        )

        fixed, remaining = orchestrator.repair_violations_surgically(
            resume_data, violations, {}, None, None, bullet_tuples
        )

        achievements = fixed["EXPERIENCE"][0]["achievements"]
        self.assertNotIn(
            "Standardized campaign templates by building JSON-based content "
            "mockups, increasing content scalability across 100+ assets",
            achievements,
        )
        self.assertEqual(achievements[1], "Did other unrelated work.")
        self.assertEqual(remaining, [])

    @patch("orchestrator.GeminiClient.generate")
    def test_unparseable_response_leaves_resume_unchanged(self, mock_generate):
        bullet_tuples = self._bullet_tuples()
        resume_data = self._resume(
            "Standardized campaign templates by building JSON-based content "
            "mockups, increasing content scalability across 100+ assets"
        )
        violations = validate_resume._check_metric_provenance(
            resume_data, bullet_tuples
        )

        mock_generate.side_effect = Exception("simulated API failure")

        fixed, remaining = orchestrator.repair_violations_surgically(
            resume_data, violations, {}, None, None, bullet_tuples
        )

        self.assertEqual(
            fixed["EXPERIENCE"][0]["achievements"],
            resume_data["EXPERIENCE"][0]["achievements"],
        )
        self.assertEqual(len(remaining), 1)


if __name__ == "__main__":
    unittest.main()
