"""
tests/test_platform_analytics.py — Unit tests for source-platform breakdown,
company concentration, score-vs-coverage scatter, and bullet bank analytics.
"""

import json
import os
import sqlite3
import sys
import tempfile
import unittest

SCRIPTS_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts"
)
TESTS_DIR = os.path.dirname(os.path.abspath(__file__))
if SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, SCRIPTS_DIR)
if TESTS_DIR not in sys.path:
    sys.path.insert(0, TESTS_DIR)

import persona  # noqa: E402
import profile_paths  # noqa: E402


class TestPlatformAnalyticsIsolatedBase(unittest.TestCase):
    """Base class providing a sandboxed, isolated profile with an in-memory or temp SQLite database."""

    def setUp(self):
        self._temp_dir = tempfile.TemporaryDirectory()
        profile_paths.isolate_for_tests(self._temp_dir.name)
        self.profile = "sandbox"
        persona.sandbox_profile(self.profile)
        import db

        self.db_path = db.get_db_path(self.profile)
        # Ensure schema is initialized
        self.conn = db.get_db(self.profile)
        self.conn.execute("DELETE FROM jobs;")
        self.conn.execute("DELETE FROM bullet_bank;")
        self.conn.commit()

    def tearDown(self):
        try:
            self.conn.close()
        except Exception:
            pass
        self._temp_dir.cleanup()

    def _insert_job(
        self,
        job_id: str,
        title: str,
        company: str,
        platform: str | None,
        score: float | None = None,
        status: str = "pending",
        coverage_score: float | None = None,
        skills: list | None = None,
    ):
        import db

        metadata = {}
        if platform is not None:
            metadata["source_platform"] = platform
        if coverage_score is not None:
            metadata["_coverage"] = {
                "coverage_score": coverage_score,
                "covered_skills": 5,
                "total_skills": 8,
            }
        if skills:
            metadata["skills"] = skills

        job_data = {
            "id": job_id,
            "title": title,
            "company": company,
            "location": "Springfield, IL",
            "raw_text": f"Role description for {title} at {company}",
            "status": status,
            "final_score": score,
            "_evaluation": {"composite_score": score} if score is not None else {},
            **metadata,
        }
        db.upsert_job(job_data, profile=self.profile, conn=self.conn)


class TestSourcePlatformBreakdown(TestPlatformAnalyticsIsolatedBase):
    def test_empty_database_returns_empty_stats(self):
        import platform_analytics

        stats = platform_analytics.compute_source_platform_breakdown(
            profile=self.profile, conn=self.conn
        )
        self.assertEqual(stats, [])

    def test_computes_platform_counts_averages_and_score_bands(self):
        import platform_analytics

        # Insert greenhouse jobs
        self._insert_job("gh_1", "Senior PM", "Acme", "greenhouse", score=4.8)
        self._insert_job("gh_2", "Lead PM", "Beta", "Greenhouse", score=4.2)
        self._insert_job("gh_3", "Staff PM", "Gamma", "greenhouse", score=3.6)
        self._insert_job("gh_4", "PM I", "Delta", "greenhouse", score=2.5)
        self._insert_job(
            "gh_5", "PM II", "Epsilon", "greenhouse", score=None
        )  # unscored

        # Insert linkedin jobs
        self._insert_job("li_1", "Marketing Mgr", "Zeta", "linkedin", score=3.8)
        self._insert_job("li_2", "Director Ops", "Eta", "linkedin", score=3.2)

        # Insert ashby job
        self._insert_job("ash_1", "Product Lead", "Theta", "ashby", score=4.9)

        stats = platform_analytics.compute_source_platform_breakdown(
            profile=self.profile, conn=self.conn
        )

        self.assertEqual(len(stats), 3)

        # Find greenhouse stat
        gh = next(s for s in stats if s["platform"].lower() == "greenhouse")
        self.assertEqual(gh["total_roles"], 5)
        self.assertEqual(gh["evaluated_roles"], 4)
        # Avg score of [4.8, 4.2, 3.6, 2.5] = 15.1 / 4 = 3.775 -> 3.8
        self.assertAlmostEqual(gh["avg_score"], 3.78, places=1)
        self.assertEqual(gh["bands"]["tier_4_5_plus"], 1)  # 4.8
        self.assertEqual(gh["bands"]["tier_4_0_to_4_4"], 1)  # 4.2
        self.assertEqual(gh["bands"]["tier_3_5_to_3_9"], 1)  # 3.6
        self.assertEqual(gh["bands"]["tier_sub_3_5"], 1)  # 2.5
        self.assertEqual(gh["top_role"]["title"], "Senior PM")
        self.assertEqual(gh["top_role"]["score"], 4.8)

        # Ashby stat
        ash = next(s for s in stats if s["platform"].lower() == "ashby")
        self.assertEqual(ash["total_roles"], 1)
        self.assertEqual(ash["avg_score"], 4.9)
        self.assertEqual(ash["top_role"]["title"], "Product Lead")

    def test_handles_missing_or_blank_source_platform_gracefully(self):
        import platform_analytics

        self._insert_job("unk_1", "Generalist", "Omega", "", score=4.0)
        self._insert_job("unk_2", "Strategist", "Psi", None, score=3.5)

        stats = platform_analytics.compute_source_platform_breakdown(
            profile=self.profile, conn=self.conn
        )
        self.assertEqual(len(stats), 1)
        self.assertEqual(stats[0]["platform"], "Direct / Unknown")
        self.assertEqual(stats[0]["total_roles"], 2)


class TestCompanyConcentration(TestPlatformAnalyticsIsolatedBase):
    def test_empty_database_returns_empty_companies(self):
        import platform_analytics

        companies = platform_analytics.compute_company_concentration(
            profile=self.profile, conn=self.conn
        )
        self.assertEqual(companies, [])

    def test_computes_company_counts_averages_and_agency_flag(self):
        import platform_analytics

        # Agency with multiple roles
        self._insert_job("ag_1", "Sr Python Dev", "CyberCoders", "indeed", score=3.5)
        self._insert_job(
            "ag_2", "Product Manager", "CyberCoders", "linkedin", score=4.0
        )
        self._insert_job("ag_3", "DevOps Eng", "CyberCoders", "indeed", score=3.8)

        # Another staffing agency by name keyword
        self._insert_job(
            "ag_4", "Account Exec", "Apex Staffing Solutions", "indeed", score=3.2
        )
        self._insert_job(
            "ag_5", "Sales Lead", "Apex Staffing Solutions", "indeed", score=4.2
        )

        # Direct employer
        self._insert_job("emp_1", "Lead Architect", "Stripe", "greenhouse", score=4.9)

        companies = platform_analytics.compute_company_concentration(
            profile=self.profile, conn=self.conn
        )

        self.assertEqual(len(companies), 3)

        # Sorted by count descending
        self.assertEqual(companies[0]["company"], "CyberCoders")
        self.assertEqual(companies[0]["total_roles"], 3)
        self.assertTrue(companies[0]["is_agency"])

        self.assertEqual(companies[1]["company"], "Apex Staffing Solutions")
        self.assertEqual(companies[1]["total_roles"], 2)
        self.assertTrue(companies[1]["is_agency"])

        self.assertEqual(companies[2]["company"], "Stripe")
        self.assertEqual(companies[2]["total_roles"], 1)
        self.assertFalse(companies[2]["is_agency"])
        self.assertEqual(companies[2]["avg_score"], 4.9)


class TestScoreVsCoverageScatter(TestPlatformAnalyticsIsolatedBase):
    def test_empty_database_returns_empty_scatter(self):
        import platform_analytics

        scatter = platform_analytics.compute_score_vs_coverage_scatter(
            profile=self.profile, conn=self.conn
        )
        self.assertEqual(scatter["points"], [])
        self.assertEqual(scatter["quadrants"]["high_score_low_coverage"], [])

    def test_computes_scatter_points_and_quadrant_bucketing(self):
        import platform_analytics

        # Q1: High Score (>=4.0), Low Coverage (<70%) -> "Write Bullets Next"
        self._insert_job(
            "q1_job",
            "Director Strategy",
            "Apex Tech",
            "ashby",
            score=4.6,
            coverage_score=52.0,
        )

        # Q2: High Score (>=4.0), High Coverage (>=70%) -> "Ready to Apply"
        self._insert_job(
            "q2_job",
            "Principal Lead",
            "Stripe",
            "greenhouse",
            score=4.7,
            coverage_score=88.0,
        )

        # Q3: Low Score (<4.0), High Coverage (>=70%) -> "Over-Covered / Lower Fit"
        self._insert_job(
            "q3_job",
            "Junior Associate",
            "Beta Corp",
            "indeed",
            score=3.2,
            coverage_score=85.0,
        )

        # Q4: Low Score (<4.0), Low Coverage (<70%) -> "Low Priority"
        self._insert_job(
            "q4_job",
            "Unrelated Role",
            "Zeta Inc",
            "indeed",
            score=2.4,
            coverage_score=40.0,
        )

        # Unscored or un-covered job should be skipped from scatter
        self._insert_job(
            "skip_job",
            "No Score",
            "Alpha",
            "greenhouse",
            score=None,
            coverage_score=None,
        )

        scatter = platform_analytics.compute_score_vs_coverage_scatter(
            profile=self.profile, conn=self.conn
        )

        self.assertEqual(len(scatter["points"]), 4)

        # Check high-score low-coverage high-ROI quadrant
        q1 = scatter["quadrants"]["high_score_low_coverage"]
        self.assertEqual(len(q1), 1)
        self.assertEqual(q1[0]["id"], "q1_job")
        self.assertEqual(q1[0]["score"], 4.6)
        self.assertEqual(q1[0]["coverage"], 52.0)

        # Check high-score high-coverage quadrant
        q2 = scatter["quadrants"]["high_score_high_coverage"]
        self.assertEqual(len(q2), 1)
        self.assertEqual(q2[0]["id"], "q2_job")


class TestBulletBankHeatmap(TestPlatformAnalyticsIsolatedBase):
    def test_computes_bullet_bank_tag_coverage(self):
        import platform_analytics

        # Insert bullet bank rows
        self.conn.execute(
            """
            INSERT INTO bullet_bank (id, company, title, raw_bullet, category, audit_status)
            VALUES
                ('b1', 'Treering', 'Lead', 'Spearheaded enterprise lifecycle campaigns', 'Lifecycle Marketing', 'CLEAN'),
                ('b2', 'Treering', 'Lead', 'Engineered custom Outreach variables', 'Marketing Ops', 'CLEAN'),
                ('b3', 'Treering', 'Lead', 'Optimized CRM segmentation in Salesforce', 'Sales Ops', 'CLEAN')
            """
        )
        self.conn.commit()

        # Insert jobs with skills/keywords
        self._insert_job(
            "j1",
            "Lifecycle Lead",
            "Acme",
            "greenhouse",
            score=4.5,
            skills=["Lifecycle Marketing", "Campaign Analytics"],
        )
        self._insert_job(
            "j2",
            "RevOps Lead",
            "Beta",
            "lever",
            score=4.2,
            skills=["Sales Ops", "HubSpot", "Data Pipelines"],
        )

        heatmap = platform_analytics.compute_bullet_bank_heatmap(
            profile=self.profile, conn=self.conn
        )

        self.assertIn("categories", heatmap)
        self.assertTrue(len(heatmap["categories"]) > 0)


class TestCliAnalytics(TestPlatformAnalyticsIsolatedBase):
    def test_cli_stats_renders_without_crashing(self):
        import cli
        from click.testing import CliRunner

        self._insert_job(
            "j1", "Lifecycle Lead", "Acme", "greenhouse", score=4.5, coverage_score=60.0
        )
        self._insert_job(
            "j2",
            "Staff Recruiter",
            "CyberCoders",
            "indeed",
            score=3.8,
            coverage_score=85.0,
        )

        runner = CliRunner()
        result = runner.invoke(cli.cli, ["--profile", self.profile, "stats"])
        self.assertEqual(result.exit_code, 0)
        self.assertIn("Pipeline Intelligence", result.output)
        self.assertIn("Greenhouse", result.output)
        self.assertIn("CyberCoders", result.output)


if __name__ == "__main__":
    unittest.main()
