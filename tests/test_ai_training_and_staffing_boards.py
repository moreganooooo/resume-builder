"""AI-training labeling, staffing-agency board parsing, and the export
fields the dashboard's [i] category filter reads."""

import json
import os
import sys
import unittest
from unittest import mock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))

import ai_training  # noqa: E402
import picker  # noqa: E402
import staffing_boards  # noqa: E402


class TestAiTraining(unittest.TestCase):
    def test_platform_employer_flags(self):
        self.assertIn(
            "platform: micro1", ai_training.classify("Data Analyst", "micro1", "")
        )

    def test_gig_title_flags(self):
        self.assertTrue(ai_training.is_ai_training("AI Trainer - Finance", "Acme", ""))
        self.assertTrue(
            ai_training.is_ai_training("Data Scientist - $75/hour", "Acme", "")
        )

    def test_work_phrase_flags(self):
        body = "You will evaluate AI-generated responses for accuracy."
        self.assertTrue(ai_training.is_ai_training("Analyst", "Acme", body))
        body = "Experts help train their latest language model."
        self.assertTrue(ai_training.is_ai_training("Expert Opportunity", "Acme", body))

    def test_engineering_roles_do_not_flag(self):
        # Skills-shaped mentions and "improve AI" are engineering, not gigs.
        cases = [
            ("ML Engineer", "ElevenLabs", "Experience with RLHF and LLM evaluation."),
            ("Senior Engineer", "Angi", "Build and improve AI voice agents."),
            ("Data Scientist", "Green Key Resources", "Build training data pipelines."),
        ]
        for title, company, body in cases:
            with self.subTest(company=company):
                self.assertEqual(ai_training.classify(title, company, body), [])

    def test_platform_match_is_whole_word(self):
        self.assertEqual(ai_training.classify("Engineer", "Turingly Inc", ""), [])


class TestStaffingBoardParsing(unittest.TestCase):
    BOARD = {"name": "Agency", "url": "https://jobs.example.com/", "type": "jsonld"}

    def test_posting_links_same_host_job_paths_only(self):
        html = (
            '<a href="/jobs/123/analyst">a</a><a href="/jobs/">idx</a>'
            '<a href="https://other.com/jobs/9">x</a><a href="/about">b</a>'
            '<a href="/jobs/123/analyst">dup</a>'
        )
        links = staffing_boards._posting_links(html, self.BOARD["url"], None)
        self.assertEqual(links, ["https://jobs.example.com/jobs/123/analyst"])

    def test_jsonld_job_posting_mapped(self):
        posting = {
            "@type": "JobPosting",
            "title": "Staff Accountant",
            "description": "<p>Close the books.</p>",
            "employmentType": "CONTRACTOR",
            "datePosted": "2026-09-20",
            "jobLocation": {
                "address": {"addressLocality": "Buffalo", "addressRegion": "NY"}
            },
        }
        html = f'<script type="application/ld+json">{json.dumps(posting)}</script>'
        found = staffing_boards._job_posting_from_html(html)
        self.assertIsNotNone(found)
        job = staffing_boards._job_from_jsonld(
            found, "https://jobs.example.com/jobs/1", self.BOARD
        )
        self.assertEqual(job["job_title"], "Staff Accountant")
        self.assertEqual(job["staffing_agency"], "Agency")
        self.assertEqual(job["employment_type"], "Contract")
        self.assertIn("Buffalo", job["location"])

    def test_hmg_post_mapped(self):
        post = {
            "POST_ID": 42,
            "POST_TITLE": "Warehouse Lead",
            "POST_LOCATION": "Buffalo, NY",
            "POST_SALARY": "$20/hr",
            "POST_DESCRIPTION": "<p>Lead a shift.</p>",
            "SEO_PERMALINK": "warehouse-lead",
        }
        board = {"name": "LHT", "url": "https://jobs.lhtservices.com/", "type": "hmg"}
        with mock.patch("scan_boards._html_to_text", side_effect=lambda h: h):
            job = staffing_boards._job_from_hmg(post, board)
        self.assertEqual(
            job["source_url"], "https://jobs.lhtservices.com/jobs/42/warehouse-lead"
        )
        self.assertTrue(job["description"].startswith("Salary: $20/hr"))
        self.assertEqual(job["source_platform"], "staffing_board")

    def test_config_skips_invalid_entries(self):
        raw = [
            {"name": "Good", "url": "https://a.example.com/"},
            {"name": "No url"},
            {"url": "https://b.example.com/", "type": "mystery"},
        ]
        with mock.patch(
            "scan_boards._load_filters", return_value={"staffing_boards": raw}
        ):
            boards = staffing_boards.configured_boards()
        self.assertEqual([b["name"] for b in boards], ["Good"])
        self.assertEqual(boards[0]["type"], "jsonld")

    def test_placeholder_postings_and_network_under_tests(self):
        board = {
            "name": "A",
            "url": "https://a.example.com/",
            "type": "jsonld",
            "link_pattern": None,
        }
        jobs = [
            {"job_title": "Join Our Talent Network!", "location": "Buffalo, NY"},
            {"job_title": "Analyst", "location": "Buffalo, NY"},
        ]
        with mock.patch.object(
            staffing_boards, "configured_boards", return_value=[board]
        ):
            # Under unittest the source is blocked without the opt-in env var.
            with mock.patch.dict(os.environ, {}, clear=False):
                os.environ.pop("RESUME_ALLOW_TEST_NETWORK", None)
                self.assertEqual(staffing_boards.fetch_staffing_board_jobs(), [])
            with (
                mock.patch.dict(os.environ, {"RESUME_ALLOW_TEST_NETWORK": "1"}),
                mock.patch.dict(
                    staffing_boards.ADAPTERS, {"jsonld": lambda b, activity=None: jobs}
                ),
                mock.patch("scan_indeed._admit_indeed_job", return_value=True),
            ):
                kept = staffing_boards.fetch_staffing_board_jobs()
        self.assertEqual([j["job_title"] for j in kept], ["Analyst"])

    def test_registered_as_scan_source(self):
        import scan

        self.assertIn("staffing_boards", scan.SOURCE_FETCHERS)


class TestCategoryExportFields(unittest.TestCase):
    def test_fields_for_ai_gig_and_agency_posting(self):
        fields = picker._category_fields(
            {
                "job_title": "AI Trainer",
                "company_name": "Acme",
                "staffing_agency": "LHT",
            }
        )
        self.assertTrue(fields["ai_training"])
        self.assertTrue(fields["ai_training_evidence"])
        self.assertEqual(fields["staffing_agency"], "LHT")

    def test_fields_default_for_ordinary_posting(self):
        fields = picker._category_fields({"title": "Analyst", "company": "Acme"})
        self.assertEqual(
            fields,
            {"ai_training": False, "ai_training_evidence": [], "staffing_agency": ""},
        )


if __name__ == "__main__":
    unittest.main()
