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

    def test_both_missing_falls_back_to_the_jd_basename(self):
        """Still no invented placeholder -- but the bare name is not a safe
        fallback either, because it is the SAME name for every meta-less
        JD. The JD's own filename is already distinctive, so it separates
        them without making anything up."""
        with patch("orchestrator.jd_manager.extract_job_meta", return_value=("", "")):
            stem = orchestrator._build_output_stem("jds/some_file.json")
        self.assertEqual(stem, f"{self.stem_prefix}_somefile")
        self.assertNotIn("Unknown", stem)

    def test_two_meta_less_jds_do_not_share_one_stem(self):
        """The real bug this guards: a bare stem meant each meta-less build
        silently overwrote the previous one's rendered PDF -- and the
        recruiter resume's, which deliberately uses the bare name."""
        with patch("orchestrator.jd_manager.extract_job_meta", return_value=("", "")):
            first = orchestrator._build_output_stem("jds/2026-09-15_Acme_Analyst.json")
            second = orchestrator._build_output_stem("jds/2026-09-16_Globex_Eng.json")
        self.assertNotEqual(first, second)
        # ...and neither may claim the recruiter resume's plain name.
        self.assertNotEqual(first, self.stem_prefix)
        self.assertNotEqual(second, self.stem_prefix)
