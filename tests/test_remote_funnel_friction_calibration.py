import json
import os
import sys
import unittest
from unittest.mock import MagicMock, patch

SCRIPTS_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts"
)
sys.path.insert(0, SCRIPTS_DIR)

import orchestrator  # noqa: E402


def _jd_json(location="", is_remote=None, work_model=""):
    return json.dumps(
        {
            "job_title": "Marketing Manager",
            "company_name": "Acme Co",
            "location": location,
            "is_remote": is_remote,
            "work_model": work_model,
            "description": "Full job description text goes here.",
        }
    )


class TestRemoteFunnelFrictionCalibration(unittest.TestCase):
    """Covers the "5b. Remote-vs-Local Candidate Pool Calibration" step in
    orchestrator.evaluate_fit(): a remote posting competes against a much
    larger applicant pool than an onsite one, so funnel_friction is nudged
    the same way the existing prestige-tier calibration nudges it."""

    def setUp(self):
        self.engine = orchestrator.ResumeEngine()
        self.engine.load_yaml = MagicMock(return_value={})
        self.engine.load_prompt = MagicMock()
        self.engine.build_fit_evaluation_context = MagicMock(
            return_value="=== CONTEXT ==="
        )

    def _mock_llm_outputs(self, funnel_friction, prestige_tier="Tier-2"):
        return [
            {
                "archetype": "Lifecycle Marketing Specialist",
                "fit_subscores": {
                    "functional_alignment": 5,
                    "north_star_alignment": 5,
                    "level_plausibility": 5,
                    "work_style_sustainability": 5,
                    "tools_process_overlap": 5,
                },
                "capability_gaps": [],
            },
            {
                "hard_blockers": [],
                "interview_odds_subscores": {
                    "title_continuity": 5,
                    "evidence_match": 5,
                    "domain_credibility": 5,
                    "recruiter_legibility": 5,
                    "narrative_burden": 5,
                    "funnel_friction": funnel_friction,
                },
                "practical_pursue_subscores": {
                    "remote_quality": 5,
                    "compensation_viability": 5,
                    "growth_value": 5,
                    "time_to_offer": 5,
                    "company_reputation": 5,
                    "cultural_signals": 5,
                    "posting_legitimacy_score": 5,
                },
                "prestige_tier": prestige_tier,
                "recommendation": "Strong pursue",
                "why": "Excellent alignment across all variables.",
                "recruiter_read": "Instantly legible.",
                "posting_legitimacy": "High Confidence",
                "posting_legitimacy_notes": "Active posting.",
                "ghost_job_red_flags": [],
            },
        ]

    @patch("orchestrator.GeminiClient.generate")
    @patch("orchestrator.GeminiClient.parse_json")
    @patch("orchestrator.jd_manager.read_jd_text")
    @patch("orchestrator.jd_manager.compute_posting_age_days")
    def test_remote_posting_lowers_funnel_friction(
        self, mock_age, mock_read_jd, mock_parse_json, mock_generate
    ):
        mock_read_jd.return_value = _jd_json(is_remote=True, work_model="remote")
        mock_age.return_value = 0
        mock_generate.side_effect = [("stage1_raw_text", {}), ("stage2_raw_text", {})]
        mock_parse_json.side_effect = self._mock_llm_outputs(funnel_friction=3)

        result = self.engine.evaluate_fit("fake_path.txt")

        self.assertEqual(result["interview_odds_subscores"]["funnel_friction"], 2)

    @patch("orchestrator.GeminiClient.generate")
    @patch("orchestrator.GeminiClient.parse_json")
    @patch("orchestrator.jd_manager.read_jd_text")
    @patch("orchestrator.jd_manager.compute_posting_age_days")
    def test_onsite_posting_raises_funnel_friction(
        self, mock_age, mock_read_jd, mock_parse_json, mock_generate
    ):
        mock_read_jd.return_value = _jd_json(
            location="Buffalo, NY", is_remote=False, work_model="onsite"
        )
        mock_age.return_value = 0
        mock_generate.side_effect = [("stage1_raw_text", {}), ("stage2_raw_text", {})]
        mock_parse_json.side_effect = self._mock_llm_outputs(funnel_friction=3)

        result = self.engine.evaluate_fit("fake_path.txt")

        self.assertEqual(result["interview_odds_subscores"]["funnel_friction"], 4)

    @patch("orchestrator.GeminiClient.generate")
    @patch("orchestrator.GeminiClient.parse_json")
    @patch("orchestrator.jd_manager.read_jd_text")
    @patch("orchestrator.jd_manager.compute_posting_age_days")
    def test_remote_calibration_is_capped_at_floor(
        self, mock_age, mock_read_jd, mock_parse_json, mock_generate
    ):
        mock_read_jd.return_value = _jd_json(is_remote=True, work_model="remote")
        mock_age.return_value = 0
        mock_generate.side_effect = [("stage1_raw_text", {}), ("stage2_raw_text", {})]
        mock_parse_json.side_effect = self._mock_llm_outputs(funnel_friction=1)

        result = self.engine.evaluate_fit("fake_path.txt")

        self.assertEqual(result["interview_odds_subscores"]["funnel_friction"], 1)

    @patch("orchestrator.GeminiClient.generate")
    @patch("orchestrator.GeminiClient.parse_json")
    @patch("orchestrator.jd_manager.read_jd_text")
    @patch("orchestrator.jd_manager.compute_posting_age_days")
    def test_onsite_calibration_is_capped_at_ceiling(
        self, mock_age, mock_read_jd, mock_parse_json, mock_generate
    ):
        mock_read_jd.return_value = _jd_json(
            location="Buffalo, NY", is_remote=False, work_model="onsite"
        )
        mock_age.return_value = 0
        mock_generate.side_effect = [("stage1_raw_text", {}), ("stage2_raw_text", {})]
        mock_parse_json.side_effect = self._mock_llm_outputs(funnel_friction=5)

        result = self.engine.evaluate_fit("fake_path.txt")

        self.assertEqual(result["interview_odds_subscores"]["funnel_friction"], 5)

    @patch("orchestrator.GeminiClient.generate")
    @patch("orchestrator.GeminiClient.parse_json")
    @patch("orchestrator.jd_manager.read_jd_text")
    @patch("orchestrator.jd_manager.compute_posting_age_days")
    def test_unresolvable_workplace_leaves_funnel_friction_untouched(
        self, mock_age, mock_read_jd, mock_parse_json, mock_generate
    ):
        # Plain-text JD (not JSON) -- _parse_jd_data() returns {}, so
        # classify_workplace() has nothing to go on and reports UNKNOWN.
        mock_read_jd.return_value = "some plain-text job posting body"
        mock_age.return_value = 0
        mock_generate.side_effect = [("stage1_raw_text", {}), ("stage2_raw_text", {})]
        mock_parse_json.side_effect = self._mock_llm_outputs(funnel_friction=3)

        result = self.engine.evaluate_fit("fake_path.txt")

        self.assertEqual(result["interview_odds_subscores"]["funnel_friction"], 3)

    @patch("orchestrator.GeminiClient.generate")
    @patch("orchestrator.GeminiClient.parse_json")
    @patch("orchestrator.jd_manager.read_jd_text")
    @patch("orchestrator.jd_manager.compute_posting_age_days")
    def test_remote_and_tier1_prestige_nudges_compound(
        self, mock_age, mock_read_jd, mock_parse_json, mock_generate
    ):
        # Tier-1 caps funnel_friction at 2 first, then the remote nudge
        # subtracts 1 more from whatever the prestige step left behind.
        mock_read_jd.return_value = _jd_json(is_remote=True, work_model="remote")
        mock_age.return_value = 0
        mock_generate.side_effect = [("stage1_raw_text", {}), ("stage2_raw_text", {})]
        mock_parse_json.side_effect = self._mock_llm_outputs(
            funnel_friction=5, prestige_tier="Tier-1"
        )

        result = self.engine.evaluate_fit("fake_path.txt")

        self.assertEqual(result["interview_odds_subscores"]["funnel_friction"], 1)


if __name__ == "__main__":
    unittest.main()
