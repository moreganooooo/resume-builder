"""Tests for build_verified_skills_context() -- the block that grounds
evaluate_capability.md's tools_process_overlap/capability_gaps scoring in
the candidate's actual verified_tools.json/profile.yml skills, instead of
letting the model infer tool familiarity purely from narrative prose.
"""

import os
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))

import orchestrator  # noqa: E402


class TestBuildVerifiedSkillsContext(unittest.TestCase):
    def test_merges_verified_tools_and_profile_skills(self):
        with (
            patch(
                "skills_menu._load_verified_tools",
                return_value={"tools": [{"name": "Salesforce"}, {"name": "HubSpot"}]},
            ),
            patch(
                "profile_paths.profile_yaml",
                return_value={"skills": {"Marketing": ["SEO", "HubSpot"]}},
            ),
        ):
            block = orchestrator.build_verified_skills_context()

        self.assertIn("=== VERIFIED SKILLS & TOOLS", block)
        self.assertIn("Salesforce", block)
        self.assertIn("HubSpot", block)
        self.assertIn("SEO", block)
        # Deduped, not listed twice.
        self.assertEqual(block.count("HubSpot"), 1)

    def test_empty_when_nothing_verified(self):
        with (
            patch("skills_menu._load_verified_tools", return_value={"tools": []}),
            patch("profile_paths.profile_yaml", return_value={}),
        ):
            block = orchestrator.build_verified_skills_context()
        self.assertEqual(block, "")

    def test_degrades_on_load_failure(self):
        with (
            patch("skills_menu._load_verified_tools", side_effect=Exception("boom")),
            patch("profile_paths.profile_yaml", return_value={}),
        ):
            block = orchestrator.build_verified_skills_context()
        self.assertEqual(block, "")


class TestBlockReachesFitContext(unittest.TestCase):
    def test_the_block_reaches_the_fit_context(self):
        engine = orchestrator.ResumeEngine.__new__(orchestrator.ResumeEngine)
        engine.kb_dir = "/nonexistent"
        engine.scoring_dir = "/nonexistent"
        with (
            patch(
                "skills_menu._load_verified_tools",
                return_value={"tools": [{"name": "Salesforce"}]},
            ),
            patch("profile_paths.profile_yaml", return_value={}),
        ):
            context = orchestrator.ResumeEngine.build_fit_evaluation_context(
                engine, "We need someone who knows Salesforce."
            )
        self.assertIn("=== VERIFIED SKILLS & TOOLS", context)
        self.assertIn("Salesforce", context)

    def test_scoring_version_moved_with_this_change(self):
        """A scoring-context change the version doesn't track leaves every
        stale score looking current."""
        import jd_manager

        self.assertGreaterEqual(jd_manager.SCORING_VERSION, 6)

    def test_prompt_references_the_new_block(self):
        prompt_path = os.path.join(
            os.path.dirname(__file__),
            "..",
            "resume-engine",
            "prompts",
            "evaluate_capability.md",
        )
        with open(prompt_path, encoding="utf-8") as f:
            prompt = f.read()
        self.assertIn("VERIFIED SKILLS & TOOLS", prompt)
        self.assertIn("capability_gaps", prompt)


class TestRecruiterPromptReferencesVerifiedSkills(unittest.TestCase):
    """evaluate_recruiter.md's Stage-2 call receives the same fit_context
    (and therefore the same VERIFIED SKILLS & TOOLS block) as Stage-1 --
    both GeminiClient.generate() calls in evaluate_fit() pass
    contents=fit_context. This only confirms the prompt's own text
    actually instructs the model to use it, not that the block reaches
    the call (that's covered by TestBlockReachesFitContext plus
    orchestrator.evaluate_fit()'s shared fit_context)."""

    def setUp(self):
        prompt_path = os.path.join(
            os.path.dirname(__file__),
            "..",
            "resume-engine",
            "prompts",
            "evaluate_recruiter.md",
        )
        with open(prompt_path, encoding="utf-8") as f:
            self.prompt = f.read()

    def test_prompt_references_the_verified_skills_block(self):
        self.assertIn("VERIFIED SKILLS & TOOLS", self.prompt)

    def test_hard_blockers_instructed_to_exclude_verified_skills(self):
        self.assertIn("never list it here", self.prompt)

    def test_evidence_match_instructed_to_check_verified_skills(self):
        self.assertIn(
            "the `=== VERIFIED SKILLS & TOOLS ===` block, can prove", self.prompt
        )


class TestWarmJdKeywordCache(unittest.TestCase):
    def test_extracts_and_caches_when_nothing_present(self):
        import json
        import tempfile

        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump({"title": "A", "description": "..."}, f)
            path = f.name
        self.addCleanup(os.remove, path)

        with patch(
            "orchestrator.get_or_extract_jd_keywords",
            return_value={"tools": ["X"], "hard_skills": [], "core_functions": []},
        ) as mock_extract:
            orchestrator.warm_jd_keyword_cache(path)

        mock_extract.assert_called_once_with(path)

    def test_skips_when_already_cached(self):
        import json
        import tempfile

        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump(
                {
                    "title": "A",
                    "_extracted_keywords": {
                        "tools": [],
                        "hard_skills": [],
                        "core_functions": [],
                    },
                },
                f,
            )
            path = f.name
        self.addCleanup(os.remove, path)

        with patch("orchestrator.get_or_extract_jd_keywords") as mock_extract:
            orchestrator.warm_jd_keyword_cache(path)

        mock_extract.assert_not_called()

    def test_skips_when_scan_already_provided_skills(self):
        import json
        import tempfile

        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump({"title": "A", "skills": [{"skill": "Salesforce"}]}, f)
            path = f.name
        self.addCleanup(os.remove, path)

        with patch("orchestrator.get_or_extract_jd_keywords") as mock_extract:
            orchestrator.warm_jd_keyword_cache(path)

        mock_extract.assert_not_called()

    def test_missing_file_is_a_silent_noop(self):
        with patch("orchestrator.get_or_extract_jd_keywords") as mock_extract:
            orchestrator.warm_jd_keyword_cache("/nonexistent/fake_path.txt")
        mock_extract.assert_not_called()

    def test_extraction_failure_never_raises(self):
        import json
        import tempfile

        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump({"title": "A"}, f)
            path = f.name
        self.addCleanup(os.remove, path)

        with patch(
            "orchestrator.get_or_extract_jd_keywords", side_effect=Exception("boom")
        ):
            orchestrator.warm_jd_keyword_cache(path)  # must not raise


class TestEvaluateFitWarmsTheCache(unittest.TestCase):
    @patch("orchestrator.warm_jd_keyword_cache")
    @patch("orchestrator.GeminiClient.parse_json", return_value={})
    @patch("orchestrator.GeminiClient.generate")
    @patch("orchestrator.jd_manager.read_jd_text", return_value="A job description.")
    def test_evaluate_fit_pairs_extraction_with_evaluation(
        self, mock_read_jd_text, mock_generate, mock_parse_json, mock_warm
    ):
        from unittest.mock import MagicMock

        mock_generate.side_effect = [("stage1", {}), ("stage2", {})]
        engine = orchestrator.ResumeEngine()
        engine.load_yaml = MagicMock(return_value={})
        engine.load_prompt = MagicMock()
        engine.build_fit_evaluation_context = MagicMock(return_value="=== CONTEXT ===")
        with patch("orchestrator.profile_paths.profile_yaml", return_value={}):
            engine.evaluate_fit("fake_path.txt")
        mock_warm.assert_called_once_with("fake_path.txt")


class TestGatherJdSkillNames(unittest.TestCase):
    def test_prefers_scan_provided_skills(self):
        import json
        import tempfile

        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump({"skills": [{"skill": "Python"}, {"skill": "Go"}]}, f)
            path = f.name
        self.addCleanup(os.remove, path)

        with patch("orchestrator.get_or_extract_jd_keywords") as mock_extract:
            names = orchestrator.gather_jd_skill_names(path)

        self.assertEqual(names, ["Python", "Go"])
        mock_extract.assert_not_called()

    def test_falls_back_to_extracted_keywords_deduped(self):
        import json
        import tempfile

        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump({"title": "A"}, f)
            path = f.name
        self.addCleanup(os.remove, path)

        with patch(
            "orchestrator.get_or_extract_jd_keywords",
            return_value={
                "tools": ["Salesforce", "salesforce"],
                "hard_skills": ["SEO"],
                "core_functions": [],
            },
        ):
            names = orchestrator.gather_jd_skill_names(path)

        self.assertEqual(names, ["Salesforce", "SEO"])

    def test_missing_file_returns_empty(self):
        names = orchestrator.gather_jd_skill_names("/nonexistent/fake.json")
        self.assertEqual(names, [])


class TestComputeSkillCoverageMatrix(unittest.TestCase):
    def test_no_skills_returns_empty(self):
        self.assertEqual(orchestrator.compute_skill_coverage_matrix([]), [])

    def test_missing_embeddings_file_returns_empty(self):
        with patch("os.path.exists", return_value=False):
            result = orchestrator.compute_skill_coverage_matrix(["Python"])
        self.assertEqual(result, [])

    def test_embedding_failure_returns_empty_not_raise(self):
        with (
            patch("os.path.exists", return_value=True),
            patch("numpy.load", side_effect=Exception("boom")),
        ):
            result = orchestrator.compute_skill_coverage_matrix(["Python"])
        self.assertEqual(result, [])

    def test_computes_and_sorts_by_coverage(self):
        import numpy as np

        with (
            patch("os.path.exists", return_value=True),
            patch("numpy.load", return_value=np.ones((2, 768), dtype=np.float32)),
            patch(
                "embed_bullet_bank.embed_batch",
                return_value=[np.ones(768, dtype=np.float32).tolist()],
            ),
        ):
            result = orchestrator.compute_skill_coverage_matrix(["Python"])

        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["skill"], "Python")
        self.assertIn("coverage", result[0])


class TestEvaluateFitPopulatesSkillMatrix(unittest.TestCase):
    @patch("orchestrator.compute_skill_coverage_matrix")
    @patch("orchestrator.gather_jd_skill_names", return_value=["Python"])
    @patch("orchestrator.warm_jd_keyword_cache")
    @patch("orchestrator.GeminiClient.parse_json", return_value={})
    @patch("orchestrator.GeminiClient.generate")
    @patch("orchestrator.jd_manager.read_jd_text", return_value="A job description.")
    def test_skill_matrix_is_attached_to_the_evaluation(
        self,
        mock_read_jd_text,
        mock_generate,
        mock_parse_json,
        mock_warm,
        mock_gather,
        mock_compute,
    ):
        from unittest.mock import MagicMock

        mock_generate.side_effect = [("stage1", {}), ("stage2", {})]
        mock_compute.return_value = [{"skill": "Python", "coverage": 80.0}]
        engine = orchestrator.ResumeEngine()
        engine.load_yaml = MagicMock(return_value={})
        engine.load_prompt = MagicMock()
        engine.build_fit_evaluation_context = MagicMock(return_value="=== CONTEXT ===")
        with patch("orchestrator.profile_paths.profile_yaml", return_value={}):
            result = engine.evaluate_fit("fake_path.txt")
        mock_compute.assert_called_once_with(["Python"])
        self.assertEqual(
            result["skill_matrix"], [{"skill": "Python", "coverage": 80.0}]
        )

    @patch("orchestrator.compute_skill_coverage_matrix", side_effect=Exception("boom"))
    @patch("orchestrator.gather_jd_skill_names", return_value=["Python"])
    @patch("orchestrator.warm_jd_keyword_cache")
    @patch("orchestrator.GeminiClient.parse_json", return_value={})
    @patch("orchestrator.GeminiClient.generate")
    @patch("orchestrator.jd_manager.read_jd_text", return_value="A job description.")
    def test_matrix_failure_does_not_break_evaluation(
        self,
        mock_read_jd_text,
        mock_generate,
        mock_parse_json,
        mock_warm,
        mock_gather,
        mock_compute,
    ):
        from unittest.mock import MagicMock

        mock_generate.side_effect = [("stage1", {}), ("stage2", {})]
        engine = orchestrator.ResumeEngine()
        engine.load_yaml = MagicMock(return_value={})
        engine.load_prompt = MagicMock()
        engine.build_fit_evaluation_context = MagicMock(return_value="=== CONTEXT ===")
        with patch("orchestrator.profile_paths.profile_yaml", return_value={}):
            result = engine.evaluate_fit("fake_path.txt")
        self.assertNotIn("skill_matrix", result)


if __name__ == "__main__":
    unittest.main()
