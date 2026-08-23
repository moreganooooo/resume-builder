import os
import sys
import unittest
from unittest.mock import patch

SCRIPTS_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts"
)
sys.path.insert(0, SCRIPTS_DIR)
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import orchestrator  # noqa: E402


class TestBuildOutputStem(unittest.TestCase):
    """The stem's name prefix comes from the ACTIVE profile's
    candidate.full_name, so these used to hardcode the repo author's name
    and only passed on that machine."""

    def setUp(self):
        import persona

        self._sandbox = persona.sandbox_profile()
        self._sandbox.__enter__()
        self.stem_prefix = persona.FULL_NAME.replace(" ", "")

    def tearDown(self):
        self._sandbox.__exit__(None, None, None)

    def test_both_title_and_company_known(self):
        with patch(
            "orchestrator.jd_manager.extract_job_meta",
            return_value=("Campaign Manager", "4MINDS"),
        ):
            stem = orchestrator._build_output_stem("jds/some_file.json")
        self.assertEqual(stem, f"{self.stem_prefix}_CampaignManager_4MINDS")

    def test_company_missing_omits_that_segment_not_a_placeholder(self):
        with patch(
            "orchestrator.jd_manager.extract_job_meta",
            return_value=("Campaign Manager", ""),
        ):
            stem = orchestrator._build_output_stem("jds/some_file.json")
        self.assertEqual(stem, f"{self.stem_prefix}_CampaignManager")
        self.assertNotIn("Unknown", stem)

    def test_title_missing_omits_that_segment_not_a_placeholder(self):
        with patch(
            "orchestrator.jd_manager.extract_job_meta", return_value=("", "4MINDS")
        ):
            stem = orchestrator._build_output_stem("jds/some_file.json")
        self.assertEqual(stem, f"{self.stem_prefix}_4MINDS")
        self.assertNotIn("Unknown", stem)

    def test_both_missing_falls_back_to_just_the_name(self):
        with patch("orchestrator.jd_manager.extract_job_meta", return_value=("", "")):
            stem = orchestrator._build_output_stem("jds/some_file.json")
        self.assertEqual(stem, self.stem_prefix)
