"""
test_job_compare.py — Unit tests for side-by-side job and package comparison.
"""

import os
import sys
import tempfile
import unittest
from unittest.mock import patch

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPTS_DIR = os.path.join(PROJECT_ROOT, "scripts")
if SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, SCRIPTS_DIR)
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

import db
import job_compare
import profile_paths
from rich.console import Console


class TestJobCompare(unittest.TestCase):
    def test_compare_jobs_and_render(self):
        job_a = {
            "title": "Staff Content Strategist",
            "company": "Acme Corp",
            "fit_score": 92,
            "location": "Remote",
            "work_style": "Remote",
            "salary_raw": "$180,000 - $210,000",
            "platform": "Greenhouse",
            "hard_skills": ["content architecture", "taxonomy", "python", "leadership"],
            "raw_text": "We need a Staff Content Strategist to lead information architecture and taxonomy design.",
        }
        job_b = {
            "title": "Principal Technical Writer",
            "company": "Beta Systems",
            "fit_score": 84,
            "location": "San Francisco, CA",
            "work_style": "Hybrid",
            "salary_raw": "$175,000 - $195,000",
            "platform": "Lever",
            "hard_skills": [
                "documentation",
                "api design",
                "python",
                "developer advocacy",
            ],
            "raw_text": "We need a Principal Technical Writer for developer documentation and API reference guides.",
        }

        with (
            patch(
                "scripts.vector_store.search_bullet_bank",
                return_value=[("Built taxonomy system.", "Acme", "[tag]", 0.9)],
            ),
            patch("scripts.vector_store.GeminiClient.embed", return_value=[0.1] * 768),
        ):
            res = job_compare.compare_jobs(job_a, job_b)
            self.assertEqual(res["score_a"], 92)
            self.assertEqual(res["score_b"], 84)
            self.assertIn("python", res["common_skills"])
            self.assertIn("Acme Corp", res["verdict"])

            c = Console(record=True)
            job_compare.render_job_comparison(res, console=c)
            rendered = c.export_text()
            self.assertIn("SIDE-BY-SIDE JOB & APPLICATION PACKAGE COMPARISON", rendered)
            self.assertIn("Staff Content Strategist", rendered)
            self.assertIn("Principal Technical Writer", rendered)


if __name__ == "__main__":
    unittest.main()
