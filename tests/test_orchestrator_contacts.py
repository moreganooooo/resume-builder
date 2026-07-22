import os
import sys
import unittest
from unittest.mock import patch

SCRIPTS_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts")
sys.path.insert(0, SCRIPTS_DIR)

import orchestrator  # noqa: E402


class TestFindJdContacts(unittest.TestCase):

    def test_returns_empty_list_when_no_connections_data(self):
        self.assertEqual(orchestrator.find_jd_contacts({}), [])
        self.assertEqual(orchestrator.find_jd_contacts({"social_connections": None}), [])

    def test_flattens_a_real_social_connections_entry(self):
        jd_data = {
            "social_connections": [
                {"fullName": "Jen Dudik, CPTD", "companyName": "Teachstone",
                 "jobTitle": "Director of Talent Development",
                 "linkedinUrl": "https://www.linkedin.com/in/jen-dudik/"},
            ],
        }
        contacts = orchestrator.find_jd_contacts(jd_data)
        self.assertEqual(len(contacts), 1)
        self.assertEqual(contacts[0]["name"], "Jen Dudik, CPTD")
        self.assertEqual(contacts[0]["title"], "Director of Talent Development")
        self.assertEqual(contacts[0]["company"], "Teachstone")
        self.assertEqual(contacts[0]["linkedin_url"], "https://www.linkedin.com/in/jen-dudik/")
        self.assertEqual(contacts[0]["connection_type"], "JobRight match")

    def test_flattens_personal_company_and_school_connections(self):
        jd_data = {
            "personal_social_connections": {
                "company": [{"fullName": "Alex Chen", "jobTitle": "PM", "companyName": "Acme"}],
                "school": [{"fullName": "Sam Rivera", "jobTitle": "Eng", "companyName": "Acme"}],
            },
        }
        contacts = orchestrator.find_jd_contacts(jd_data)
        types = {c["name"]: c["connection_type"] for c in contacts}
        self.assertEqual(types["Alex Chen"], "Personal company connection")
        self.assertEqual(types["Sam Rivera"], "Personal school connection")

    def test_skips_entries_with_no_name(self):
        jd_data = {"social_connections": [{"jobTitle": "Recruiter", "companyName": "Acme"}]}
        self.assertEqual(orchestrator.find_jd_contacts(jd_data), [])

    def test_combines_both_sources(self):
        jd_data = {
            "social_connections": [{"fullName": "Jen Dudik"}],
            "personal_social_connections": {"company": [{"fullName": "Alex Chen"}], "school": []},
        }
        contacts = orchestrator.find_jd_contacts(jd_data)
        self.assertEqual({c["name"] for c in contacts}, {"Jen Dudik", "Alex Chen"})


class TestDraftOutreachMessage(unittest.TestCase):

    def setUp(self):
        self.engine = orchestrator.ResumeEngine()
        self.contact = {"name": "Jen Dudik", "title": "Director of Talent Development",
                         "company": "Teachstone", "connection_type": "JobRight match"}

    @patch("orchestrator.GeminiClient.generate")
    @patch("orchestrator.jd_manager.read_jd_text", return_value="=== JD text ===")
    def test_returns_stripped_message_text(self, mock_read_text, mock_generate):
        mock_generate.return_value = ("  Hi Jen, ...  \n", {})
        result = self.engine.draft_outreach_message("jds/a.json", self.contact)
        self.assertEqual(result, "Hi Jen, ...")

    @patch("orchestrator.jd_manager.read_jd_text", side_effect=FileNotFoundError)
    def test_returns_none_when_jd_not_found(self, mock_read_text):
        result = self.engine.draft_outreach_message("jds/missing.json", self.contact)
        self.assertIsNone(result)

    @patch("orchestrator.GeminiClient.generate", return_value=("", {}))
    @patch("orchestrator.jd_manager.read_jd_text", return_value="=== JD text ===")
    def test_returns_none_on_empty_model_response(self, mock_read_text, mock_generate):
        result = self.engine.draft_outreach_message("jds/a.json", self.contact)
        self.assertIsNone(result)

    @patch("orchestrator.GeminiClient.generate")
    @patch("orchestrator.jd_manager.read_jd_text", return_value="=== JD text ===")
    def test_contact_details_reach_the_prompt_contents(self, mock_read_text, mock_generate):
        mock_generate.return_value = ("Hi Jen", {})
        self.engine.draft_outreach_message("jds/a.json", self.contact)
        contents = mock_generate.call_args.kwargs["contents"]
        self.assertIn("Jen Dudik", contents)
        self.assertIn("Director of Talent Development", contents)
        self.assertIn("JobRight match", contents)


if __name__ == "__main__":
    unittest.main()
