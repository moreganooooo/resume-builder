import io
import os
import sys
import unittest
from unittest.mock import patch

sys.path.insert(
    0,
    os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts"
    ),
)

import cli_art


class TestPackageHUD(unittest.TestCase):

    def test_render_application_package_hud_completed(self):
        result = {
            "status": "completed",
            "company_name": "Spotify",
            "job_title": "Senior Content Strategist",
            "evaluation": {"composite_score": 4.5, "recommendation": "Strong Pursue"},
            "ats_classification": {
                "provider_id": "workday",
                "weight_tier": "enterprise_high",
            },
            "output_paths": {
                "resume_pdf": "output/testprofile/pdf/AlexRivera_Spotify_Resume.pdf",
                "resume_docx": "output/testprofile/docx/AlexRivera_Spotify_Resume.docx",
                "coverletter_pdf": "output/testprofile/pdf/AlexRivera_Spotify_CoverLetter.pdf",
                "coverletter_docx": "output/testprofile/docx/AlexRivera_Spotify_CoverLetter.docx",
            },
        }
        with patch.object(cli_art.console, "print") as mock_print:
            cli_art.render_application_package_hud(result)
            mock_print.assert_called()

    def test_render_application_package_hud_graceful_missing_fields(self):
        result = {
            "status": "completed",
            "output_paths": {},
        }
        with patch.object(cli_art.console, "print") as mock_print:
            cli_art.render_application_package_hud(result)
            mock_print.assert_called()


if __name__ == "__main__":
    unittest.main()
