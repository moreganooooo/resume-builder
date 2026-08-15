import os
import sys
import unittest
from unittest.mock import MagicMock, patch

SCRIPTS_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts")
sys.path.insert(0, SCRIPTS_DIR)

import orchestrator  # noqa: E402
import jd_manager  # noqa: E402


def _confirm_answers(*answers):
    """Builds the side_effect list questionary.confirm(...) needs: each call
    returns a fresh object whose .ask() yields the next answer (True/False/
    None for approve/decline/interrupted), matching the
    @patch("<module>.questionary.confirm") convention used elsewhere in this
    suite (e.g. test_bootstrap_bullet_bank_pipeline.py)."""
    return [MagicMock(ask=MagicMock(return_value=a)) for a in answers]


class TestReviewRecommendationsInteractively(unittest.TestCase):

    def setUp(self):
        self.job_key = "test-gap-fill-review-job"

    def tearDown(self):
        jd_manager.delete_checkpoint(self.job_key)

    @patch("orchestrator.questionary.confirm")
    def test_only_approved_recommendations_are_returned(self, mock_confirm):
        recs = ["Add a Salesforce bullet.", "Tighten the summary wording.", "Add a Tableau bullet."]
        checkpoint = {}
        mock_confirm.side_effect = _confirm_answers(True, False, True)
        approved = orchestrator._review_recommendations_interactively(recs, checkpoint, self.job_key)
        self.assertEqual(approved, ["Add a Salesforce bullet.", "Add a Tableau bullet."])

    @patch("orchestrator.questionary.confirm")
    def test_declining_everything_returns_empty_list(self, mock_confirm):
        recs = ["Add a Salesforce bullet."]
        mock_confirm.side_effect = _confirm_answers(False)
        approved = orchestrator._review_recommendations_interactively(recs, {}, self.job_key)
        self.assertEqual(approved, [])

    @patch("orchestrator.questionary.confirm")
    def test_approval_choices_are_checkpointed(self, mock_confirm):
        recs = ["Add a Salesforce bullet.", "Add a Tableau bullet."]
        checkpoint = {}
        mock_confirm.side_effect = _confirm_answers(True, False)
        orchestrator._review_recommendations_interactively(recs, checkpoint, self.job_key)
        saved = jd_manager.load_checkpoint(self.job_key)
        self.assertEqual(saved["approved_recommendations"], ["Add a Salesforce bullet."])

    @patch("orchestrator.questionary.confirm")
    def test_resuming_from_checkpoint_does_not_reprompt(self, mock_confirm):
        recs = ["Add a Salesforce bullet.", "Add a Tableau bullet."]
        checkpoint = {"approved_recommendations": ["Add a Tableau bullet."]}
        approved = orchestrator._review_recommendations_interactively(recs, checkpoint, self.job_key)
        mock_confirm.assert_not_called()
        self.assertEqual(approved, ["Add a Tableau bullet."])

    @patch("orchestrator.questionary.confirm")
    def test_interrupted_review_declines_remaining_and_keeps_prior_approvals(self, mock_confirm):
        """An interrupted .ask() (Ctrl-D/Ctrl-C -> None) stops the review
        loop instead of raising -- the crash-on-interrupt gap this function
        used to have (unlike its _confirm_continue_without_keywords sibling)
        before it moved off raw input()."""
        recs = ["Add a Salesforce bullet.", "Add a Tableau bullet.", "Add a Snowflake bullet."]
        mock_confirm.side_effect = _confirm_answers(True, None)
        approved = orchestrator._review_recommendations_interactively(recs, {}, self.job_key)
        self.assertEqual(approved, ["Add a Salesforce bullet."])
        self.assertEqual(mock_confirm.call_count, 2)


if __name__ == "__main__":
    unittest.main()
