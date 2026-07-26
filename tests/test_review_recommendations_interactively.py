import os
import sys
import unittest
from unittest.mock import patch

SCRIPTS_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts")
sys.path.insert(0, SCRIPTS_DIR)

import orchestrator  # noqa: E402
import jd_manager  # noqa: E402


class TestReviewRecommendationsInteractively(unittest.TestCase):

    def setUp(self):
        self.job_key = "test-gap-fill-review-job"

    def tearDown(self):
        jd_manager.delete_checkpoint(self.job_key)

    def test_only_approved_recommendations_are_returned(self):
        recs = ["Add a Salesforce bullet.", "Tighten the summary wording.", "Add a Tableau bullet."]
        checkpoint = {}
        with patch("builtins.input", side_effect=["y", "n", "yes"]):
            approved = orchestrator._review_recommendations_interactively(recs, checkpoint, self.job_key)
        self.assertEqual(approved, ["Add a Salesforce bullet.", "Add a Tableau bullet."])

    def test_declining_everything_returns_empty_list(self):
        recs = ["Add a Salesforce bullet."]
        with patch("builtins.input", return_value="n"):
            approved = orchestrator._review_recommendations_interactively(recs, {}, self.job_key)
        self.assertEqual(approved, [])

    def test_approval_choices_are_checkpointed(self):
        recs = ["Add a Salesforce bullet.", "Add a Tableau bullet."]
        checkpoint = {}
        with patch("builtins.input", side_effect=["y", "n"]):
            orchestrator._review_recommendations_interactively(recs, checkpoint, self.job_key)
        saved = jd_manager.load_checkpoint(self.job_key)
        self.assertEqual(saved["approved_recommendations"], ["Add a Salesforce bullet."])

    def test_resuming_from_checkpoint_does_not_reprompt(self):
        recs = ["Add a Salesforce bullet.", "Add a Tableau bullet."]
        checkpoint = {"approved_recommendations": ["Add a Tableau bullet."]}
        with patch("builtins.input") as mock_input:
            approved = orchestrator._review_recommendations_interactively(recs, checkpoint, self.job_key)
        mock_input.assert_not_called()
        self.assertEqual(approved, ["Add a Tableau bullet."])


if __name__ == "__main__":
    unittest.main()
