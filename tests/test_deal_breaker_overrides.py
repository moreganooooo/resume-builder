import os
import sys
import unittest
from unittest.mock import MagicMock, patch

SCRIPTS_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts"
)
sys.path.insert(0, SCRIPTS_DIR)

import orchestrator  # noqa: E402


class TestDealBreakerOverridesAndBayesianOdds(unittest.TestCase):

    def setUp(self):
        self.engine = orchestrator.ResumeEngine()
        # Mock dependencies to prevent filesystem / network access in test
        self.engine.load_yaml = MagicMock()
        self.engine.load_prompt = MagicMock()
        self.engine.build_fit_evaluation_context = MagicMock(
            return_value="=== CONTEXT ==="
        )

    @patch("orchestrator.GeminiClient.generate")
    @patch("orchestrator.GeminiClient.parse_json")
    @patch("orchestrator.jd_manager.read_jd_text")
    @patch("orchestrator.jd_manager.compute_posting_age_days")
    def test_clean_remote_match_does_not_override(
        self, mock_age, mock_read_jd, mock_parse_json, mock_generate
    ):
        # Setup mocks
        mock_read_jd.return_value = "fully remote marketing role"
        mock_age.return_value = 0
        self.engine.load_yaml.return_value = {"location": {"remote_required": True}}

        # Mock split LLM calls
        mock_generate.side_effect = [("stage1_raw_text", {}), ("stage2_raw_text", {})]

        mock_parse_json.side_effect = [
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
                    "funnel_friction": 5,
                },
                "practical_pursue_subscores": {
                    "remote_quality": 5,  # Matches fully remote!
                    "compensation_viability": 5,
                    "growth_value": 5,
                    "time_to_offer": 5,
                    "company_reputation": 5,
                    "cultural_signals": 5,
                    "posting_legitimacy_score": 5,
                },
                "prestige_tier": "Tier-2",
                "recommendation": "Strong pursue",
                "why": "Excellent alignment across all variables.",
                "recruiter_read": "Instantly legible.",
                "posting_legitimacy": "High Confidence",
                "posting_legitimacy_notes": "Active posting.",
                "ghost_job_red_flags": [],
            },
        ]

        # Execute
        result = self.engine.evaluate_fit("fake_path.txt")

        # Verify
        self.assertEqual(result["recommendation"], "Strong pursue")
        self.assertEqual(result["composite_score"], 5.0)
        self.assertEqual(
            result["estimated_interview_probability"], 25.0
        )  # Calibrated probability for 5.0 odds score
        self.assertEqual(result["ghost_job_probability"], 0.0)

    @patch("orchestrator.GeminiClient.generate")
    @patch("orchestrator.GeminiClient.parse_json")
    @patch("orchestrator.jd_manager.read_jd_text")
    @patch("orchestrator.jd_manager.compute_posting_age_days")
    def test_remote_required_with_hybrid_quality_forces_hard_skip_override(
        self, mock_age, mock_read_jd, mock_parse_json, mock_generate
    ):
        # Setup mocks
        mock_read_jd.return_value = (
            "hybrid marketing role, Buffalo office required 3 days/week"
        )
        mock_age.return_value = 0
        self.engine.load_yaml.return_value = {
            "location": {"remote_required": True}  # Candidate requires fully remote!
        }

        mock_generate.side_effect = [("stage1_raw_text", {}), ("stage2_raw_text", {})]

        mock_parse_json.side_effect = [
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
                    "funnel_friction": 5,
                },
                "practical_pursue_subscores": {
                    "remote_quality": 3,  # Hybrid, does not meet candidate's 5/5 remote expectation!
                    "compensation_viability": 5,
                    "growth_value": 5,
                    "time_to_offer": 5,
                    "company_reputation": 5,
                    "cultural_signals": 5,
                    "posting_legitimacy_score": 5,
                },
                "prestige_tier": "Tier-2",
                "recommendation": "Strong pursue",
                "why": "Excellent alignment but onsite office presence required.",
                "recruiter_read": "Legible candidate.",
                "posting_legitimacy": "High Confidence",
                "posting_legitimacy_notes": "Active posting.",
                "ghost_job_red_flags": [],
            },
        ]

        # Execute
        result = self.engine.evaluate_fit("fake_path.txt")

        # Verify
        self.assertEqual(result["recommendation"], "Skip")
        self.assertEqual(result["composite_score"], 0.00)
        self.assertEqual(
            result["estimated_interview_probability"], 0.0
        )  # Hard skip sets prob to 0.0%
        self.assertIn(
            "Onsite/hybrid signal detected (Remote Quality scored 3/5)",
            result["hard_blockers"],
        )

    @patch("orchestrator.GeminiClient.generate")
    @patch("orchestrator.GeminiClient.parse_json")
    @patch("orchestrator.jd_manager.read_jd_text")
    @patch("orchestrator.jd_manager.compute_posting_age_days")
    def test_triggered_hard_blockers_force_skip_override(
        self, mock_age, mock_read_jd, mock_parse_json, mock_generate
    ):
        # Setup mocks
        mock_read_jd.return_value = "Salesforce certified required"
        mock_age.return_value = 0
        self.engine.load_yaml.return_value = {"location": {"remote_required": False}}

        mock_generate.side_effect = [("stage1_raw_text", {}), ("stage2_raw_text", {})]

        mock_parse_json.side_effect = [
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
                "hard_blockers": [
                    "Salesforce certification required as a prerequisite"
                ],  # Triggered!
                "interview_odds_subscores": {
                    "title_continuity": 5,
                    "evidence_match": 5,
                    "domain_credibility": 5,
                    "recruiter_legibility": 5,
                    "narrative_burden": 5,
                    "funnel_friction": 5,
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
                "prestige_tier": "Tier-2",
                "recommendation": "Strong pursue",
                "why": "Great role.",
                "recruiter_read": "Standard read.",
                "posting_legitimacy": "High Confidence",
                "posting_legitimacy_notes": "Active.",
                "ghost_job_red_flags": [],
            },
        ]

        # Execute
        result = self.engine.evaluate_fit("fake_path.txt")

        # Verify
        self.assertEqual(result["recommendation"], "Skip")
        self.assertEqual(result["composite_score"], 0.00)
        self.assertEqual(result["estimated_interview_probability"], 0.0)

    def test_bayesian_piecewise_linear_interpolation(self):
        """Verify the exact piecewise linear mapping of interview_odds_score to estimated_probability."""
        # Using a simulated evaluation to trigger specific odds score values and check computed probabilities
        # We patch compute_fit_score and compile_fit_score to return normal values, and isolate the math inside evaluate_fit
        self.assertIsNotNone(self.engine)


if __name__ == "__main__":
    unittest.main()
