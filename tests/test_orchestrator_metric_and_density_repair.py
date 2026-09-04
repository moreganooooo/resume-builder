"""Targeted Metric Deduplication / ATS Keyword Density repair -- see
orchestrator._micro_dedupe_metric / _micro_trim_keyword_density /
repair_violations_surgically's "6. Targeted Metric Deduplication Repair"
and "7. Targeted ATS Keyword Density Repair" blocks.

Covers a real failure mode observed live 2026-09-03: the LLM full-resume
retry loop returned the exact same "Metric '100+' should appear only
once ... Summary and a bullet" and "Keyword 'content' appears 16 times
(3.8%)" violations across all 4 fix attempts, failing the whole build
(both are fatal per partition_violations). Root cause turned out to be
gemini_client.GeminiClient.generate() silently forcing temperature to
0.0 whenever response_schema was set, defeating the fix loop's own
stall-escalation -- fixed alongside these targeted repairs.

Uses synthetic resume content throughout -- not the active profile's
real employers/bullets -- per tests/test_no_operator_identity.py's "use
synthetic data, not the operator's own history" rule.
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


class TestMetricDedupeSummaryVsBullet(unittest.TestCase):

    def _resume(self):
        return {
            "SUMMARY_TEXT": (
                "Marketing generalist known for scaling a sequence "
                "library of 100+ assets and driving growth."
            ),
            "EXPERIENCE": [
                {
                    "title": "Widget Marketer",
                    "company": "Acme Robotics",
                    "period": "Jan 2020 - Present",
                    "location": "Remote",
                    "achievements": [
                        "Built a sequence library of 100+ assets for outbound.",
                        "Did other unrelated work.",
                    ],
                    "career_note": "",
                }
            ],
            "SKILLS": [],
        }

    @patch("orchestrator.GeminiClient.generate")
    def test_summary_occurrence_is_rewritten_bullet_is_untouched(self, mock_generate):
        resume_data = self._resume()
        violations = validate_resume._check_metric_uniqueness(resume_data)
        self.assertTrue(any(v.startswith("Metric '100+'") for v in violations))

        mock_generate.return_value = (
            "Marketing generalist known for scaling a large, reusable asset "
            "library and driving growth.",
            {},
        )

        fixed, remaining = orchestrator.repair_violations_surgically(
            resume_data, violations, {}, None, None, []
        )

        self.assertNotIn("100+", fixed["SUMMARY_TEXT"])
        self.assertIn(
            "Built a sequence library of 100+ assets for outbound.",
            fixed["EXPERIENCE"][0]["achievements"],
        )
        self.assertFalse(any(v.startswith("Metric '100+'") for v in remaining))

    @patch("orchestrator.GeminiClient.generate")
    def test_unparseable_response_leaves_resume_unchanged(self, mock_generate):
        resume_data = self._resume()
        violations = validate_resume._check_metric_uniqueness(resume_data)

        mock_generate.side_effect = Exception("simulated API failure")

        fixed, remaining = orchestrator.repair_violations_surgically(
            resume_data, violations, {}, None, None, []
        )

        self.assertEqual(fixed["SUMMARY_TEXT"], resume_data["SUMMARY_TEXT"])
        self.assertTrue(any(v.startswith("Metric '100+'") for v in remaining))


class TestMetricDedupeBulletVsBullet(unittest.TestCase):

    @patch("orchestrator.GeminiClient.generate")
    def test_later_bullet_is_rewritten_first_bullet_is_untouched(self, mock_generate):
        resume_data = {
            "SUMMARY_TEXT": "Generalist marketer with a track record of measurable growth.",
            "EXPERIENCE": [
                {
                    "title": "Widget Marketer",
                    "company": "Acme Robotics",
                    "period": "Jan 2020 - Present",
                    "location": "Remote",
                    "achievements": [
                        "Grew a territory to 100+ districts across the region.",
                        "Expanded coverage to over 100+ districts in year two.",
                    ],
                    "career_note": "",
                }
            ],
            "SKILLS": [],
        }
        violations = validate_resume._check_metric_uniqueness(resume_data)
        self.assertTrue(any(v.startswith("Metric '100+'") for v in violations))

        mock_generate.return_value = (
            "Expanded coverage across a much larger footprint in year two.",
            {},
        )

        fixed, remaining = orchestrator.repair_violations_surgically(
            resume_data, violations, {}, None, None, []
        )

        achievements = fixed["EXPERIENCE"][0]["achievements"]
        self.assertEqual(
            achievements[0], "Grew a territory to 100+ districts across the region."
        )
        self.assertNotIn("100+", achievements[1])
        self.assertFalse(any(v.startswith("Metric '100+'") for v in remaining))


class TestKeywordDensityTrim(unittest.TestCase):

    def _resume_with_dense_keyword(self):
        # 'content' appears 5 times across ~40 corpus words -> well past a
        # 10% ceiling, so a single micro-repair call is exercised without
        # needing a large synthetic corpus.
        return {
            "SUMMARY_TEXT": "Content strategist who builds content systems for content teams.",
            "WHY_TEXT": "",
            "EXPERIENCE": [
                {
                    "title": "Content Lead",
                    "company": "Acme Robotics",
                    "period": "Jan 2020 - Present",
                    "location": "Remote",
                    "achievements": [
                        "Led content production and content review cycles for the team.",
                    ],
                    "career_note": "",
                }
            ],
            "SKILLS": ["**Tools:** Figma, Asana, Slack"],
        }

    def test_violation_parses_and_reduce_by_is_computed(self):
        resume_data = self._resume_with_dense_keyword()
        violations = validate_resume._check_keyword_density_ceiling(
            resume_data, max_density=0.10
        )
        content_violation = next(v for v in violations if "'content'" in v.lower())
        match = orchestrator.re.match(
            r"^ATS Keyword Density Ceiling: Keyword '([^']+)' appears (\d+) times "
            r"\([\d.]+% of (\d+) words\), exceeding the ([\d.]+)% natural density limit\.",
            content_violation,
        )
        self.assertIsNotNone(match)
        word, count, total_words, max_density_pct = match.groups()
        self.assertEqual(word, "content")
        self.assertGreater(int(count), float(max_density_pct) / 100 * int(total_words))

    @patch("orchestrator.GeminiClient.generate")
    def test_trim_rewrites_fields_and_skips_skills_section(self, mock_generate):
        resume_data = self._resume_with_dense_keyword()
        violations = validate_resume._check_keyword_density_ceiling(
            resume_data, max_density=0.10
        )

        hits = orchestrator._fields_containing_word(resume_data, "content")
        # SKILLS is never a candidate field.
        self.assertTrue(all(field != "SKILLS" for field, _, _, _ in hits))

        rewritten = [
            text.replace("content", "creative", 1) if "content" in text else text
            for _field, _j, _b, text in hits
        ]
        mock_generate.return_value = (orchestrator.json.dumps(rewritten), {})

        fixed, remaining = orchestrator.repair_violations_surgically(
            resume_data, violations, {"forced_style": {}}, None, None, []
        )

        self.assertEqual(fixed["SKILLS"], resume_data["SKILLS"])
        self.assertNotEqual(fixed["SUMMARY_TEXT"], resume_data["SUMMARY_TEXT"])
        self.assertFalse(any("Keyword 'content'" in v for v in remaining))

    @patch("orchestrator.GeminiClient.generate")
    def test_wrong_length_response_leaves_resume_unchanged(self, mock_generate):
        resume_data = self._resume_with_dense_keyword()
        violations = validate_resume._check_keyword_density_ceiling(
            resume_data, max_density=0.10
        )

        mock_generate.return_value = (orchestrator.json.dumps(["only one field"]), {})

        fixed, remaining = orchestrator.repair_violations_surgically(
            resume_data, violations, {}, None, None, []
        )

        self.assertEqual(fixed["SUMMARY_TEXT"], resume_data["SUMMARY_TEXT"])
        self.assertTrue(any("Keyword 'content'" in v for v in remaining))


if __name__ == "__main__":
    unittest.main()
