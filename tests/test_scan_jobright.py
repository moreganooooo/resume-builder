import os
import sys
import unittest
from unittest.mock import MagicMock, patch

SCRIPTS_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts")
sys.path.insert(0, SCRIPTS_DIR)

import scan_jobright  # noqa: E402


class TestFetchJobrightJobsActivity(unittest.TestCase):

    @patch.dict(os.environ, {"JOBRIGHT_COOKIE_STRING": "fake-cookie"})
    @patch("scan_jobright.requests.get")
    def test_steps_through_activity_when_given(self, mock_get):
        response = MagicMock()
        response.status_code = 200
        response.json.return_value = {"result": {"jobList": [
            {"jobResult": {"jobId": "1", "jobTitle": "Data Engineer", "originalUrl": "https://x.com/1"},
             "companyResult": {"companyName": "Acme"}, "displayScore": 80},
        ]}}
        mock_get.return_value = response

        activity = MagicMock()
        jobs = scan_jobright.fetch_jobright_jobs(max_position=0, activity=activity)

        self.assertEqual(len(jobs), 1)
        activity.step.assert_called_with(
            "success", "JobRight", 'Found "Data Engineer" @ Acme',
        )

    @patch.dict(os.environ, {"JOBRIGHT_COOKIE_STRING": "fake-cookie"})
    @patch("scan_jobright.requests.get")
    def test_works_with_no_activity_given(self, mock_get):
        response = MagicMock()
        response.status_code = 200
        response.json.return_value = {"result": {"jobList": []}}
        mock_get.return_value = response

        jobs = scan_jobright.fetch_jobright_jobs(max_position=0)
        self.assertEqual(jobs, [])


if __name__ == "__main__":
    unittest.main()
