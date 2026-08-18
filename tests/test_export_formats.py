import json
import os
import sys
import unittest

SCRIPTS_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts"
)
sys.path.insert(0, SCRIPTS_DIR)

import export_formats  # noqa: E402


def _sample_resume():
    return {
        "NAME": "Morgan Scott",
        "TAGLINE": "CAMPAIGN & CRM STRATEGIST | LIFECYCLE MARKETING",
        "EMAIL": "morgan@example.com",
        "PHONE": "(555) 123-4567",
        "LOCATION": "San Francisco, CA",
        "LINKEDIN": "linkedin.com/in/morganscott",
        "SUMMARY_TEXT": "<strong>Lifecycle marketer with 8 years in CRM strategy.</strong> Scaled outreach to 50,000+ contacts monthly.",
        "SKILLS": [
            "**Lifecycle Marketing:** Email Automation, Segmentation, Drip Campaigns",
            "**Platforms:** HubSpot, Salesforce, Iterable",
        ],
        "EXPERIENCE": [
            {
                "title": "Lifecycle Marketing Manager",
                "company": "Treering",
                "period": "08/2016 – 08/2024",
                "location": "San Mateo, CA",
                "achievements": [
                    "Recovered $3M in dormant pipeline through CRM audits and reactivation workflows",
                    "Architected the SDR onboarding program used company-wide for three years",
                ],
            }
        ],
        "EDUCATION": [
            {
                "institution": "University of California",
                "degree": "B.A. English",
                "year": "2016",
            }
        ],
    }


class TestExportFormats(unittest.TestCase):

    def test_render_markdown(self):
        data = _sample_resume()
        md = export_formats.render_markdown(data)
        self.assertIn("# Morgan Scott", md)
        self.assertIn("## Professional Summary", md)
        self.assertIn("## Core Competencies & Skills", md)
        self.assertIn("### Lifecycle Marketing Manager — Treering", md)
        self.assertIn("- Recovered $3M in dormant pipeline", md)
        self.assertIn("## Education", md)
        self.assertIn("- **B.A. English** — University of California (2016)", md)

    def test_render_plaintext(self):
        data = _sample_resume()
        text = export_formats.render_plaintext(data)
        self.assertIn("MORGAN SCOTT", text)
        self.assertIn("PROFESSIONAL SUMMARY", text)
        self.assertIn("CORE COMPETENCIES & TECHNICAL SKILLS", text)
        self.assertIn("TREERING | Lifecycle Marketing Manager", text)
        self.assertIn("* Recovered $3M in dormant pipeline", text)
        self.assertIn("EDUCATION", text)
        self.assertIn("* B.A. English - University of California, 2016", text)

    def test_render_json_ld(self):
        data = _sample_resume()
        schema = export_formats.render_json_ld(data)
        self.assertEqual(schema["@context"], "https://schema.org")
        self.assertEqual(schema["@type"], "Person")
        self.assertEqual(schema["name"], "Morgan Scott")
        self.assertEqual(
            schema["jobTitle"], "CAMPAIGN & CRM STRATEGIST | LIFECYCLE MARKETING"
        )
        self.assertIn("Lifecycle marketer with 8 years", schema["description"])
        self.assertEqual(schema["email"], "morgan@example.com")
        self.assertEqual(schema["address"]["addressLocality"], "San Francisco, CA")
        self.assertEqual(len(schema["hasOccupation"]), 1)
        self.assertEqual(schema["hasOccupation"][0]["worksFor"]["name"], "Treering")
        self.assertEqual(len(schema["hasCredential"]), 1)
        self.assertEqual(schema["hasCredential"][0]["name"], "B.A. English")
        self.assertIn("Email Automation", schema["knowsAbout"])

    def test_render_json_ld_string(self):
        data = _sample_resume()
        json_str = export_formats.render_json_ld_string(data)
        parsed = json.loads(json_str)
        self.assertEqual(parsed["name"], "Morgan Scott")


if __name__ == "__main__":
    unittest.main()
