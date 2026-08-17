import os
import sys
import unittest
from unittest.mock import MagicMock, patch

SCRIPTS_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts"
)
sys.path.insert(0, SCRIPTS_DIR)

import scan_jobright  # noqa: E402


class TestFetchJobrightJobsActivity(unittest.TestCase):

    @patch.dict(os.environ, {"JOBRIGHT_COOKIE_STRING": "fake-cookie"})
    @patch("scan_jobright.requests.get")
    def test_steps_through_activity_when_given(self, mock_get):
        response = MagicMock()
        response.status_code = 200
        response.json.return_value = {
            "result": {
                "jobList": [
                    {
                        "jobResult": {
                            "jobId": "1",
                            "jobTitle": "Data Engineer",
                            "originalUrl": "https://x.com/1",
                        },
                        "companyResult": {"companyName": "Acme"},
                        "displayScore": 80,
                    },
                ]
            }
        }
        mock_get.return_value = response

        activity = MagicMock()
        jobs = scan_jobright.fetch_jobright_jobs(max_position=0, activity=activity)

        self.assertEqual(len(jobs), 1)
        activity.step.assert_called_with(
            "success",
            "JobRight",
            '[dim]Found[/dim] "[#12C78F]Data Engineer[/#12C78F]" @ [dim]Acme[/dim]',
            preserve_markup=True,
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

    @patch.dict(os.environ, {}, clear=True)
    def test_missing_cookie_string_returns_empty_list(self):
        jobs = scan_jobright.fetch_jobright_jobs()
        self.assertEqual(jobs, [])

    @patch.dict(os.environ, {"JOBRIGHT_COOKIE_STRING": "fake-cookie"})
    @patch("scan_jobright.time.sleep")
    @patch("scan_jobright.requests.get")
    def test_http_500_skips_page(self, mock_get, mock_sleep):
        resp_500 = MagicMock(status_code=500)
        resp_200 = MagicMock(
            status_code=200,
            json=lambda: {"result": {"jobList": []}},
        )
        mock_get.side_effect = [resp_500, resp_200]
        jobs = scan_jobright.fetch_jobright_jobs(max_position=10)
        self.assertEqual(jobs, [])
        mock_sleep.assert_called()

    @patch.dict(os.environ, {"JOBRIGHT_COOKIE_STRING": "fake-cookie"})
    @patch("scan_jobright.requests.get")
    def test_http_401_auth_error_breaks(self, mock_get):
        import requests

        resp = MagicMock(status_code=401)
        http_err = requests.exceptions.HTTPError(response=resp)
        mock_get.side_effect = http_err
        jobs = scan_jobright.fetch_jobright_jobs(max_position=20)
        self.assertEqual(jobs, [])

    @patch.dict(os.environ, {"JOBRIGHT_COOKIE_STRING": "fake-cookie"})
    @patch("scan_jobright.requests.get")
    def test_request_exception_breaks(self, mock_get):
        import requests

        mock_get.side_effect = requests.exceptions.ConnectionError("Network down")
        jobs = scan_jobright.fetch_jobright_jobs(max_position=20)
        self.assertEqual(jobs, [])

    @patch.dict(os.environ, {"JOBRIGHT_COOKIE_STRING": "fake-cookie"})
    @patch("scan_jobright.time.sleep")
    @patch("scan_jobright.requests.get")
    def test_item_filtering_and_parsing_variations(self, mock_get, mock_sleep):
        response = MagicMock(status_code=200)
        response.json.return_value = {
            "result": {
                "jobList": [
                    # Missing jobResult
                    {"displayScore": 85},
                    # Match score below MIN_MATCH_SCORE (70)
                    {
                        "jobResult": {"jobTitle": "Low Score", "jobId": "2"},
                        "companyResult": {"companyName": "Acme"},
                        "displayScore": 50,
                    },
                    # Missing company name
                    {
                        "jobResult": {"jobTitle": "No Company", "jobId": "3"},
                        "companyResult": {},
                        "displayScore": 85,
                    },
                    # Valid with coreResponsibilities as list and applyLink
                    {
                        "jobResult": {
                            "jobId": "4",
                            "jobTitle": "Full Stack",
                            "jobSummary": "Summary text",
                            "coreResponsibilities": ["Resp 1", "Resp 2"],
                            "applyLink": "https://apply.com",
                            "originalUrl": "https://orig.com",
                        },
                        "companyResult": {"companyName": "TechCo"},
                        "displayScore": 90,
                    },
                    # Valid with coreResponsibilities as str
                    {
                        "jobResult": {
                            "jobId": "5",
                            "jobTitle": "Designer",
                            "coreResponsibilities": "Single responsibility string",
                        },
                        "companyResult": {"companyName": "DesignCo"},
                        "matchScore": 75,
                    },
                ]
            }
        }
        mock_get.return_value = response
        jobs = scan_jobright.fetch_jobright_jobs(max_position=0)
        self.assertEqual(len(jobs), 2)
        self.assertEqual(jobs[0]["job_title"], "Full Stack")
        self.assertEqual(jobs[0]["application_type"], "external")
        self.assertIn("Summary text\n\nResp 1\n\nResp 2", jobs[0]["description"])
        self.assertEqual(jobs[1]["job_title"], "Designer")
        self.assertEqual(jobs[1]["application_type"], "unknown")
        self.assertEqual(jobs[1]["description"], "Single responsibility string")


if __name__ == "__main__":
    unittest.main()
