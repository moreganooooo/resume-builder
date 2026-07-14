import json
import os
import shutil
import sys
import tempfile
import unittest
from unittest.mock import patch

SCRIPTS_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts")
sys.path.insert(0, SCRIPTS_DIR)

import bootstrap_bullet_bank  # noqa: E402
import bootstrap_extractors  # noqa: E402
import bootstrap_profile  # noqa: E402


class BootstrapProfileTestCase(unittest.TestCase):
    """Redirects every relevant path constant to a fresh temp dir per test."""

    def setUp(self):
        self.tmp_dir = tempfile.mkdtemp()
        self.bootstrap_dir = os.path.join(self.tmp_dir, "bootstrap")
        bootstrap_bullet_bank.BOOTSTRAP_DIR = self.bootstrap_dir
        bootstrap_bullet_bank.SOURCE_DOCS_DIR = os.path.join(self.bootstrap_dir, "source_documents")
        bootstrap_bullet_bank.TIMELINE_PATH = os.path.join(self.bootstrap_dir, "timeline.json")
        bootstrap_bullet_bank.CHECKPOINT_PATH = os.path.join(self.bootstrap_dir, "checkpoint.json")
        bootstrap_bullet_bank.DRAFT_CSV_PATH = os.path.join(self.bootstrap_dir, "bullet-bank-draft.csv")
        os.makedirs(bootstrap_bullet_bank.SOURCE_DOCS_DIR, exist_ok=True)

        bootstrap_profile.PROFILE_YML_PATH = os.path.join(self.tmp_dir, "profile.yml")
        bootstrap_profile.PORTALS_YML_PATH = os.path.join(self.tmp_dir, "portals.yml")
        bootstrap_profile.CV_MD_PATH = os.path.join(self.tmp_dir, "cv.md")
        bootstrap_profile.BACKGROUND_GUIDE_PATH = os.path.join(self.tmp_dir, "user-background-guide.md")
        bootstrap_profile.VERIFIED_METRICS_PATH = os.path.join(self.tmp_dir, "verified_metrics.json")
        bootstrap_profile.VERIFIED_TOOLS_PATH = os.path.join(self.tmp_dir, "verified_tools.json")
        bootstrap_profile.VERIFIED_PROJECTS_PATH = os.path.join(self.tmp_dir, "verified_projects.json")
        bootstrap_profile.VERIFIED_FACTS_PATH = os.path.join(self.tmp_dir, "verified_facts.json")
        bootstrap_profile.VERIFIED_CLAIMS_PATH = os.path.join(self.tmp_dir, "verified-claims.csv")
        bootstrap_profile.EVIDENCE_GRAPH_PATH = os.path.join(self.tmp_dir, "evidence_graph.json")
        bootstrap_profile.EVIDENCE_GUIDE_PATH = os.path.join(self.tmp_dir, "evidence-guide.csv")
        bootstrap_profile.SCREENSHOT_METRICS_PATH = os.path.join(self.tmp_dir, "extracted-screenshot-metrics.csv")
        bootstrap_profile.RECRUITER_PATTERNS_PATH = os.path.join(self.tmp_dir, "recruiter_memory_patterns.json")

    def tearDown(self):
        shutil.rmtree(self.tmp_dir, ignore_errors=True)

    def _write_checkpoint(self, data: dict) -> None:
        with open(bootstrap_bullet_bank.CHECKPOINT_PATH, "w", encoding="utf-8") as f:
            json.dump(data, f)

    def _write_timeline(self, entries: list) -> None:
        with open(bootstrap_bullet_bank.TIMELINE_PATH, "w", encoding="utf-8") as f:
            json.dump(entries, f)

    def _touch_source(self, filename: str) -> None:
        with open(os.path.join(bootstrap_bullet_bank.SOURCE_DOCS_DIR, filename), "w", encoding="utf-8") as f:
            f.write("placeholder")


class TestGuessContactInfo(BootstrapProfileTestCase):

    @patch("bootstrap_profile.bootstrap_extractors.extract_contact_info")
    def test_finds_info_from_resume_file(self, mock_extract):
        self._touch_source("resume.txt")
        self._write_checkpoint({"resume.txt": {"status": "done", "doc_type": "resume"}})
        mock_extract.return_value = bootstrap_extractors.ContactInfo(full_name="Jamie Rivera", email="jamie@example.com")

        info = bootstrap_profile._guess_contact_info(bootstrap_profile._load_checkpoint())

        self.assertEqual(info.full_name, "Jamie Rivera")

    def test_returns_blank_when_no_resume_file(self):
        self._write_checkpoint({"notes.txt": {"status": "done", "doc_type": "achievement_notes"}})
        info = bootstrap_profile._guess_contact_info(bootstrap_profile._load_checkpoint())
        self.assertIsNone(info.full_name)


class TestGuessPrimaryRoles(unittest.TestCase):

    def test_returns_recent_titles_most_recent_first(self):
        timeline = [
            {"company": "Old Co", "title": "Coordinator", "start_date": "2015", "end_date": "2018"},
            {"company": "Acme Corp", "title": "Marketing Manager", "start_date": "2019", "end_date": "2022"},
        ]
        roles = bootstrap_profile._guess_primary_roles(timeline)
        self.assertEqual(roles[0], "Marketing Manager")


class TestGuessRecommendations(BootstrapProfileTestCase):

    @patch("bootstrap_profile.bootstrap_extractors.extract_recommendation_quote")
    def test_collects_quotes_from_recommendation_letters(self, mock_extract):
        self._touch_source("letter.txt")
        self._write_checkpoint({"letter.txt": {"status": "done", "doc_type": "recommendation_letter"}})
        mock_extract.return_value = bootstrap_extractors.RecommendationQuote(
            name="Alex Chen", title="VP Marketing", quote="Excellent writer."
        )

        quotes = bootstrap_profile._guess_recommendations(bootstrap_profile._load_checkpoint())

        self.assertEqual(len(quotes), 1)
        self.assertEqual(quotes[0].name, "Alex Chen")

    def test_returns_empty_list_when_no_recommendation_letters(self):
        self._write_checkpoint({"resume.txt": {"status": "done", "doc_type": "resume"}})
        quotes = bootstrap_profile._guess_recommendations(bootstrap_profile._load_checkpoint())
        self.assertEqual(quotes, [])


class TestCollectIdentityDryRun(BootstrapProfileTestCase):

    def test_dry_run_returns_guesses_without_prompting(self):
        self._write_timeline([{"company": "Acme Corp", "title": "Marketing Manager", "start_date": "2019", "end_date": "2022"}])
        self._write_checkpoint({})

        with patch("bootstrap_profile.questionary.text") as mock_text, \
             patch("bootstrap_profile.questionary.checkbox") as mock_checkbox, \
             patch("bootstrap_profile.questionary.confirm") as mock_confirm:
            identity = bootstrap_profile.collect_identity(dry_run=True)
            mock_text.assert_not_called()
            mock_checkbox.assert_not_called()
            mock_confirm.assert_not_called()

        self.assertEqual(identity["primary_roles"], ["Marketing Manager"])
        self.assertEqual(identity["secondary_roles"], [])


class TestWriteProfileYml(BootstrapProfileTestCase):

    def test_writes_candidate_and_target_roles(self):
        import yaml
        identity = {
            "full_name": "Jamie Rivera", "email": "jamie@example.com", "phone": "555-0100",
            "location": "Austin, TX", "linkedin_url": "linkedin.com/in/jamierivera",
            "portfolio_url": "", "extra_link": "", "primary_roles": ["Marketing Manager"],
            "secondary_roles": ["Customer Education Specialist"], "remote_preference": True,
        }

        bootstrap_profile.write_profile_yml(identity, recommendations=[])

        with open(bootstrap_profile.PROFILE_YML_PATH, encoding="utf-8") as f:
            data = yaml.safe_load(f)
        self.assertEqual(data["candidate"]["full_name"], "Jamie Rivera")
        self.assertEqual(data["target_roles"]["primary"], ["Marketing Manager"])
        self.assertEqual(data["target_roles"]["secondary"], ["Customer Education Specialist"])
        self.assertEqual(data["location"]["remote_required"], True)

    def test_auto_fills_key_recommendations_when_present(self):
        import yaml
        identity = {
            "full_name": "Jamie Rivera", "email": "", "phone": "", "location": "", "linkedin_url": "",
            "portfolio_url": "", "extra_link": "", "primary_roles": [], "secondary_roles": [],
            "remote_preference": False,
        }
        recs = [bootstrap_extractors.RecommendationQuote(name="Alex Chen", title="VP Marketing", quote="Excellent writer.")]

        bootstrap_profile.write_profile_yml(identity, recommendations=recs)

        with open(bootstrap_profile.PROFILE_YML_PATH, encoding="utf-8") as f:
            data = yaml.safe_load(f)
        self.assertEqual(data["key_recommendations"][0]["name"], "Alex Chen")
        self.assertEqual(data["key_recommendations"][0]["quote"], "Excellent writer.")

    def test_scaffolds_deep_sections_empty(self):
        import yaml
        identity = {
            "full_name": "", "email": "", "phone": "", "location": "", "linkedin_url": "",
            "portfolio_url": "", "extra_link": "", "primary_roles": [], "secondary_roles": [],
            "remote_preference": False,
        }
        bootstrap_profile.write_profile_yml(identity, recommendations=[])
        with open(bootstrap_profile.PROFILE_YML_PATH, encoding="utf-8") as f:
            data = yaml.safe_load(f)
        self.assertEqual(data["narrative"]["headline"], "")
        self.assertEqual(data["deal_breakers"], [""])
        self.assertEqual(data["management_evidence"], [])


class TestWritePortalsYml(BootstrapProfileTestCase):

    def test_seeds_title_filter_from_target_roles(self):
        import yaml
        identity = {
            "full_name": "", "email": "", "phone": "", "location": "", "linkedin_url": "",
            "portfolio_url": "", "extra_link": "",
            "primary_roles": ["Marketing Manager"], "secondary_roles": ["Customer Education Specialist"],
            "remote_preference": True,
        }

        bootstrap_profile.write_portals_yml(identity)

        with open(bootstrap_profile.PORTALS_YML_PATH, encoding="utf-8") as f:
            data = yaml.safe_load(f)
        self.assertIn("Marketing Manager", data["title_filter"]["positive"])
        self.assertIn("Customer Education Specialist", data["title_filter"]["positive"])
        self.assertIn("Remote", data["location_filter"]["always_allow"])

    def test_scaffolds_block_and_seniority_boost_empty(self):
        import yaml
        identity = {
            "full_name": "", "email": "", "phone": "", "location": "", "linkedin_url": "",
            "portfolio_url": "", "extra_link": "", "primary_roles": [], "secondary_roles": [],
            "remote_preference": False,
        }
        bootstrap_profile.write_portals_yml(identity)
        with open(bootstrap_profile.PORTALS_YML_PATH, encoding="utf-8") as f:
            data = yaml.safe_load(f)
        self.assertEqual(data["seniority_boost"], [])


if __name__ == "__main__":
    unittest.main()
