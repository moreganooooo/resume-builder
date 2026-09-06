import contextlib
import json
import os
import sys
import tempfile
import unittest
from unittest.mock import MagicMock, patch

SCRIPTS_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts"
)
sys.path.insert(0, SCRIPTS_DIR)

import skill_gap_scan  # noqa: E402


class TestGatherPendingSkillGaps(unittest.TestCase):
    def test_aggregates_across_multiple_jds_and_dedupes_against_verified(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            job_a = os.path.join(tmpdir, "a.json")
            job_b = os.path.join(tmpdir, "b.json")
            with open(job_a, "w", encoding="utf-8") as f:
                json.dump({"title": "A"}, f)
            with open(job_b, "w", encoding="utf-8") as f:
                # Already has a cached extraction -- should not re-extract.
                json.dump(
                    {
                        "title": "B",
                        "_extracted_keywords": {
                            "tools": ["Asana"],
                            "hard_skills": [],
                            "core_functions": [],
                        },
                    },
                    f,
                )

            @contextlib.contextmanager
            def fake_resolved(identifier):
                yield identifier, False

            with (
                patch(
                    "skill_gap_scan._all_pending_jd_identifiers",
                    return_value=[job_a, job_b],
                ),
                patch("jd_source.resolved_jd", side_effect=fake_resolved),
                patch(
                    "orchestrator.extract_jd_keywords_via_gemini",
                    return_value={
                        "tools": ["HubSpot"],
                        "hard_skills": ["A/B Testing"],
                        "core_functions": [],
                    },
                ) as mock_extract,
                patch(
                    "skills_menu._load_verified_tools",
                    return_value={"tools": [{"name": "HubSpot"}]},
                ),
                patch("profile_paths.profile_yaml", return_value={}),
            ):
                gaps, stats, categories = skill_gap_scan.gather_pending_skill_gaps(
                    max_roles=10
                )

            # job_a had no cache, so it was extracted; job_b's cache was reused.
            mock_extract.assert_called_once()
            self.assertEqual(stats["extracted"], 1)
            self.assertEqual(stats["cached"], 1)
            # HubSpot already verified -- excluded. Asana and A/B Testing are gaps.
            self.assertIn("Asana", gaps)
            self.assertIn("A/B Testing", gaps)
            self.assertNotIn("HubSpot", gaps)
            # Categorized by which extraction bucket produced them.
            self.assertEqual(categories["Asana"], "Tool")
            self.assertEqual(categories["A/B Testing"], "Hard Skill")

    def test_extraction_budget_caps_new_calls(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            jobs = []
            for i in range(3):
                path = os.path.join(tmpdir, f"j{i}.json")
                with open(path, "w", encoding="utf-8") as f:
                    json.dump({"title": f"J{i}"}, f)
                jobs.append(path)

            @contextlib.contextmanager
            def fake_resolved(identifier):
                yield identifier, False

            with (
                patch("skill_gap_scan._all_pending_jd_identifiers", return_value=jobs),
                patch("jd_source.resolved_jd", side_effect=fake_resolved),
                patch(
                    "orchestrator.extract_jd_keywords_via_gemini",
                    return_value={
                        "tools": ["X"],
                        "hard_skills": [],
                        "core_functions": [],
                    },
                ) as mock_extract,
                patch("skills_menu._load_verified_tools", return_value={"tools": []}),
                patch("profile_paths.profile_yaml", return_value={}),
            ):
                _gaps, stats, _categories = skill_gap_scan.gather_pending_skill_gaps(
                    max_roles=1
                )

            self.assertEqual(mock_extract.call_count, 1)
            self.assertEqual(stats["extracted"], 1)
            self.assertEqual(stats["budget_skipped"], 2)

    def test_extraction_failure_is_counted_not_raised(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, "a.json")
            with open(path, "w", encoding="utf-8") as f:
                json.dump({"title": "A"}, f)

            @contextlib.contextmanager
            def fake_resolved(identifier):
                yield identifier, False

            with (
                patch(
                    "skill_gap_scan._all_pending_jd_identifiers", return_value=[path]
                ),
                patch("jd_source.resolved_jd", side_effect=fake_resolved),
                patch("orchestrator.extract_jd_keywords_via_gemini", return_value=None),
                patch("skills_menu._load_verified_tools", return_value={"tools": []}),
                patch("profile_paths.profile_yaml", return_value={}),
            ):
                gaps, stats, _categories = skill_gap_scan.gather_pending_skill_gaps(
                    max_roles=5
                )

            self.assertEqual(gaps, [])
            self.assertEqual(stats["failed"], 1)


class TestCategorizeGaps(unittest.TestCase):
    def test_labels_by_bucket_with_tools_priority(self):
        combined = {
            "tools": ["Salesforce"],
            "hard_skills": ["SEO", "Salesforce"],
            "core_functions": ["Requirements Gathering"],
        }
        gaps = ["Salesforce", "SEO", "Requirements Gathering", "Unmatched"]
        categories = skill_gap_scan._categorize_gaps(gaps, combined)
        self.assertEqual(categories["Salesforce"], "Tool")
        self.assertEqual(categories["SEO"], "Hard Skill")
        self.assertEqual(categories["Requirements Gathering"], "Core Function")
        self.assertEqual(categories["Unmatched"], "Skill")

    def test_category_order_sorts_tools_first(self):
        order = skill_gap_scan._CATEGORY_ORDER
        self.assertLess(order["Tool"], order["Hard Skill"])
        self.assertLess(order["Hard Skill"], order["Core Function"])
        self.assertLess(order["Core Function"], order["Skill"])


class TestRun(unittest.TestCase):
    def test_inert_under_unittest_guard(self):
        # sys.modules contains 'unittest' during a real test run.
        self.assertEqual(skill_gap_scan.run(), 0)

    def test_full_flow_persists_confirmed_skills(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            tools_path = os.path.join(tmpdir, "verified_tools.json")
            with open(tools_path, "w", encoding="utf-8") as f:
                json.dump({"_meta": {}, "tools": []}, f)

            mock_checkbox = MagicMock(return_value=["Claude"])
            modules_no_unittest = {
                k: v for k, v in sys.modules.items() if k != "unittest"
            }

            with (
                patch(
                    "skill_gap_scan.gather_pending_skill_gaps",
                    return_value=(
                        ["Asana", "Claude"],
                        {
                            "total": 2,
                            "cached": 0,
                            "extracted": 2,
                            "failed": 0,
                            "budget_skipped": 0,
                        },
                        {"Asana": "Tool", "Claude": "Tool"},
                    ),
                ),
                patch("skills_menu._get_verified_tools_path", return_value=tools_path),
                patch("sys.stdin.isatty", return_value=True),
                patch.dict("sys.modules", modules_no_unittest, clear=True),
                patch("cli_art.checkbox", mock_checkbox),
            ):
                code = skill_gap_scan.run()

            self.assertEqual(code, 0)
            with open(tools_path, "r", encoding="utf-8") as f:
                saved = json.load(f)
            self.assertEqual(len(saved["tools"]), 1)
            self.assertEqual(saved["tools"][0]["name"], "Claude")
            self.assertEqual(
                saved["tools"][0]["use_notes"],
                "Added via Pending Pipeline Skill Gap Scan",
            )

    def test_no_gaps_found_is_a_no_op(self):
        modules_no_unittest = {k: v for k, v in sys.modules.items() if k != "unittest"}
        with (
            patch(
                "skill_gap_scan.gather_pending_skill_gaps",
                return_value=(
                    [],
                    {
                        "total": 0,
                        "cached": 0,
                        "extracted": 0,
                        "failed": 0,
                        "budget_skipped": 0,
                    },
                    {},
                ),
            ),
            patch("sys.stdin.isatty", return_value=True),
            patch.dict("sys.modules", modules_no_unittest, clear=True),
        ):
            code = skill_gap_scan.run()
        self.assertEqual(code, 0)


if __name__ == "__main__":
    unittest.main()
