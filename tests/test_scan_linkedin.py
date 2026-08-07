import os
import sys
import unittest
from unittest.mock import MagicMock, patch

SCRIPTS_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts")
sys.path.insert(0, SCRIPTS_DIR)

import scan_linkedin  # noqa: E402


class TestFetchPersonalizedExtrasPacing(unittest.TestCase):
    """P7F10: _fetch_personalized_extras() carries Morgan's real li_at
    session cookie on every call and used to fire back-to-back with no
    pacing -- the one place in this subsystem with real account-ban risk.
    These tests prove the fix (a time.sleep() matching the scraper's own
    slow_mo) actually fires, without ever making a real network call."""

    def _mock_response(self, status_code=200, text="<html></html>"):
        response = MagicMock()
        response.status_code = status_code
        response.text = text
        return response

    @patch("scan_linkedin.time.sleep")
    @patch("scan_linkedin.requests.Session")
    def test_sleeps_after_a_successful_request(self, mock_session_cls, mock_sleep):
        mock_session_cls.return_value.get.return_value = self._mock_response()

        scan_linkedin._fetch_personalized_extras("https://linkedin.com/jobs/view/1", "cookie-value")

        mock_sleep.assert_called_once_with(scan_linkedin._PERSONALIZED_EXTRAS_DELAY_SECONDS)

    @patch("scan_linkedin.time.sleep")
    @patch("scan_linkedin.requests.Session")
    def test_sleeps_even_when_the_request_raises(self, mock_session_cls, mock_sleep):
        mock_session_cls.return_value.get.side_effect = Exception("timeout")

        scan_linkedin._fetch_personalized_extras("https://linkedin.com/jobs/view/1", "cookie-value")

        mock_sleep.assert_called_once_with(scan_linkedin._PERSONALIZED_EXTRAS_DELAY_SECONDS)

    @patch("scan_linkedin.time.sleep")
    @patch("scan_linkedin.requests.Session")
    def test_does_not_sleep_or_hit_the_network_without_a_job_url(self, mock_session_cls, mock_sleep):
        scan_linkedin._fetch_personalized_extras("", "cookie-value")

        mock_session_cls.assert_not_called()
        mock_sleep.assert_not_called()

    @patch("scan_linkedin.time.sleep")
    @patch("scan_linkedin.requests.Session")
    def test_does_not_sleep_or_hit_the_network_without_a_cookie(self, mock_session_cls, mock_sleep):
        scan_linkedin._fetch_personalized_extras("https://linkedin.com/jobs/view/1", "")

        mock_session_cls.assert_not_called()
        mock_sleep.assert_not_called()

    @patch("scan_linkedin.time.sleep")
    @patch("scan_linkedin.requests.Session")
    def test_still_sleeps_on_a_non_200_response(self, mock_session_cls, mock_sleep):
        mock_session_cls.return_value.get.return_value = self._mock_response(status_code=999)

        scan_linkedin._fetch_personalized_extras("https://linkedin.com/jobs/view/1", "cookie-value")

        mock_sleep.assert_called_once_with(scan_linkedin._PERSONALIZED_EXTRAS_DELAY_SECONDS)


if __name__ == "__main__":
    unittest.main()
