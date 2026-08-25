"""test_strategy_radar.py — Unit tests for strategy_radar.py."""

import unittest

from scripts import strategy_radar


class TestStrategyRadar(unittest.TestCase):
    def test_detect_ats_platform(self):
        # Workday
        res = strategy_radar.detect_ats_platform(
            "https://acme.myworkdayjobs.com/careers/job1"
        )
        self.assertEqual(res["platform_key"], "workday")
        self.assertIn("DOCX", res["recommended_format"])

        # Greenhouse
        res = strategy_radar.detect_ats_platform(
            "https://boards.greenhouse.io/stripe/jobs/12345"
        )
        self.assertEqual(res["platform_key"], "greenhouse")
        self.assertEqual(res["parsing_risk"], "Low (Modern OCR & HTML preview)")

        # Lever
        res = strategy_radar.detect_ats_platform("https://jobs.lever.co/figma/67890")
        self.assertEqual(res["platform_key"], "lever")

        # Ashby
        res = strategy_radar.detect_ats_platform("https://jobs.ashbyhq.com/openai/1122")
        self.assertEqual(res["platform_key"], "ashby")

        # Fallback / Direct
        res = strategy_radar.detect_ats_platform("https://example.com/careers/apply")
        self.assertEqual(res["platform_key"], "direct")

    def test_classify_role_archetype_and_seniority(self):
        # Senior CRM Manager
        arch, seniority = strategy_radar.classify_role_archetype(
            "Senior Lifecycle & CRM Marketing Manager",
            "Drive customer retention, email campaigns, Salesforce and Braze automation.",
        )
        self.assertEqual(arch, "CRM & Lifecycle Marketing")
        self.assertEqual(seniority, "Lead / Manager")

        # Content Strategist IC
        arch, seniority = strategy_radar.classify_role_archetype(
            "Content Strategist & Copywriter",
            "Own brand voice, editorial calendar, and high-converting storytelling.",
        )
        self.assertEqual(arch, "Content & Brand Strategy")
        self.assertEqual(seniority, "Individual Contributor (IC)")

        # Enablement Lead
        arch, seniority = strategy_radar.classify_role_archetype(
            "Sales Enablement & GTM Lead",
            "Design SDR playbooks, Outreach.io sequence optimization, and rep coaching.",
        )
        self.assertEqual(arch, "GTM & Sales Enablement")
        self.assertEqual(seniority, "Lead / Manager")

    def test_select_situation_playbooks(self):
        # Manager level -> Overqualification / IC Preference
        playbooks = strategy_radar.select_situation_playbooks(
            title="Marketing Operations Lead",
            jd_text="Manage team workflow and reporting metrics.",
            seniority="Lead / Manager",
            is_agency=False,
        )
        titles = [p["title"] for p in playbooks]
        self.assertIn("Tactical Playbook: Hands-On IC Refocus", titles)
        self.assertIn("Tactical Playbook: Direct Brand Alignment & Culture Fit", titles)

        # Agency -> Staffing Agency Navigation
        agency_playbooks = strategy_radar.select_situation_playbooks(
            title="Email Marketing Specialist",
            jd_text="Fast-paced client delivery.",
            seniority="Individual Contributor (IC)",
            is_agency=True,
        )
        agency_titles = [p["title"] for p in agency_playbooks]
        self.assertIn(
            "Tactical Playbook: High-Volume Staffing Agency Navigation", agency_titles
        )

    def test_analyze_job_strategy_end_to_end(self):
        job = {
            "title": "Senior Lifecycle Marketing Manager",
            "company": "Stripe",
            "url": "https://boards.greenhouse.io/stripe/jobs/999",
            "description": "Looking for a CRM specialist to drive retention, Salesforce reporting, and email copy.",
        }
        report = strategy_radar.analyze_job_strategy(job)
        self.assertEqual(report["title"], "Senior Lifecycle Marketing Manager")
        self.assertEqual(report["company"], "Stripe")
        self.assertEqual(report["ats"]["platform_key"], "greenhouse")
        self.assertFalse(report["is_agency"])
        self.assertIsInstance(report["playbooks"], list)
        self.assertGreater(len(report["playbooks"]), 0)


if __name__ == "__main__":
    unittest.main()
