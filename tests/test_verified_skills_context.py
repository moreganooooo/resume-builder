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


class TestSkillsFilteredToThePosting(unittest.TestCase):
    """A ledger only grows, so above SKILLS_CONTEXT_FILTER_MIN names only the
    skills a posting mentions reach the evaluator (a 1,407-name ledger cost
    ~7,500 tokens on every evaluation)."""

    def setUp(self):
        # The filter ships disabled (SKILLS_CONTEXT_FILTER_ENABLED) pending a
        # passing A/B; these tests exercise the matching itself.
        patcher = patch("orchestrator.SKILLS_CONTEXT_FILTER_ENABLED", True)
        patcher.start()
        self.addCleanup(patcher.stop)

    def _ledger(self, extra):
        filler = [{"name": f"Filler Skill {i} Marketing"} for i in range(150)]
        return {"tools": filler + [{"name": n} for n in extra]}

    def test_semantic_matches_join_the_block_under_a_neutral_header(self):
        with patch(
            "orchestrator.semantic_skill_matches",
            return_value=["Customer Journey Mapping"],
        ):
            with (
                patch(
                    "skills_menu._load_verified_tools",
                    return_value=self._ledger(["Customer Journey Mapping", "Figma"]),
                ),
                patch("profile_paths.profile_yaml", return_value={}),
            ):
                block = orchestrator.build_verified_skills_context(
                    "Own lifecycle programs.", ["lifecycle mapping"]
                )
        self.assertIn("Customer Journey Mapping", block)
        self.assertNotIn("Figma", block)
        self.assertNotIn(" of the candidate's", block)  # no "N of M" framing

    def test_disabled_filter_sends_the_whole_ledger(self):
        with patch("orchestrator.SKILLS_CONTEXT_FILTER_ENABLED", False):
            block = self._block(["Figma"], "Needs Salesforce.")
        self.assertIn("Figma", block)
        self.assertIn("Filler Skill 3 Marketing", block)
        self.assertNotIn("relevant to this posting", block)

    def _block(self, extra, jd):
        with (
            patch("skills_menu._load_verified_tools", return_value=self._ledger(extra)),
            patch("profile_paths.profile_yaml", return_value={}),
        ):
            return orchestrator.build_verified_skills_context(jd)

    def test_small_ledger_is_sent_whole(self):
        with (
            patch(
                "skills_menu._load_verified_tools",
                return_value={"tools": [{"name": "Salesforce"}, {"name": "Figma"}]},
            ),
            patch("profile_paths.profile_yaml", return_value={}),
        ):
            block = orchestrator.build_verified_skills_context("Needs Salesforce.")
        self.assertIn("Figma", block)

    def test_large_ledger_keeps_only_what_the_posting_names(self):
        block = self._block(
            [
                "Salesforce CRM",
                "Customer relationship management (CRM) systems",
                "Outreach.io",
                "Figma",
            ],
            "You'll own our Salesforce instance and Outreach.io sequences. CRM experience a plus.",
        )
        self.assertIn("relevant to this posting", block)
        self.assertIn("Salesforce CRM", block)  # distinctive token
        self.assertIn("Customer relationship management (CRM) systems", block)  # alias
        self.assertIn("Outreach.io", block)  # dotted name, sentence-final dot
        self.assertNotIn("Figma", block)
        self.assertNotIn("Filler Skill", block)

    def test_a_generic_word_never_matches_on_its_own(self):
        # "marketing" is shared by 150 ledger names; a posting saying it must
        # not pull all of them in.
        block = self._block([], "A marketing role.")
        self.assertNotIn("Filler Skill", block)
        self.assertIn("none of the confirmed skills", block)

    def test_no_posting_text_falls_back_to_the_whole_ledger(self):
        block = self._block(["Figma"], "")
        self.assertIn("Figma", block)
        self.assertIn("Filler Skill 3 Marketing", block)


class TestSemanticSkillMatches(unittest.TestCase):
    def setUp(self):
        import json
        import tempfile

        import embed_verified_skills as evs
        import numpy as np

        self.tmp = tempfile.mkdtemp()
        self.addCleanup(__import__("shutil").rmtree, self.tmp, True)
        self.names = ["Figma", "Lifecycle Marketing", "Salesforce"]
        npy, meta = os.path.join(self.tmp, "v.npy"), os.path.join(self.tmp, "v.meta")
        np.save(npy, np.array([[0.0, 1.0], [0.7, 0.7], [1.0, 0.0]], dtype=np.float32))
        with open(meta, "w") as f:
            json.dump({"names_sha": evs._names_sha(self.names)}, f)
        for attr, value in (
            ("NPY_PATH", npy),
            ("META_PATH", meta),
            ("load_verified_skill_names", lambda: list(self.names)),
        ):
            p = patch.object(evs, attr, value)
            p.start()
            self.addCleanup(p.stop)

    def test_close_meaning_matches_and_distant_ones_do_not(self):
        with patch("embed_bullet_bank.embed_batch", return_value=[[1.0, 0.0]]):
            # Salesforce: 1.0 (kept); Lifecycle Marketing: 0.71 (below 0.82)
            self.assertEqual(
                orchestrator.semantic_skill_matches(["CRM platform"]), ["Salesforce"]
            )

    def test_vectors_built_from_another_ledger_are_never_used(self):
        import embed_verified_skills as evs

        with (
            patch.object(
                evs,
                "load_verified_skill_names",
                lambda: ["Salesforce", "Something New"],
            ),
            patch("embed_bullet_bank.embed_batch") as mock_embed,
        ):
            self.assertEqual(orchestrator.semantic_skill_matches(["CRM platform"]), [])
        mock_embed.assert_not_called()


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

    def test_rate_limited_primary_falls_back_to_backup_model(self):
        import embed_bullet_bank
        import numpy as np

        def fake_embed(batch, model=None, max_retries=None):
            if model == embed_bullet_bank.EMBED_MODEL:
                raise RuntimeError("embed_batch failed after 2 retries.")
            return [np.ones(768, dtype=np.float32).tolist() for _ in batch]

        with (
            patch("os.path.exists", return_value=True),
            patch("numpy.load", return_value=np.ones((2, 768), dtype=np.float32)),
            patch(
                "embed_bullet_bank.embed_batch", side_effect=fake_embed
            ) as mock_embed,
        ):
            result = orchestrator.compute_skill_coverage_matrix(["Python"])

        self.assertEqual([r["skill"] for r in result], ["Python"])
        models = [c.kwargs.get("model") for c in mock_embed.call_args_list]
        self.assertEqual(
            models,
            [embed_bullet_bank.EMBED_MODEL, embed_bullet_bank.BACKUP_EMBED_MODEL],
        )
        # Short ladder: the backup exists, so the primary never waits ~150s.
        self.assertTrue(
            all(c.kwargs.get("max_retries") == 2 for c in mock_embed.call_args_list)
        )


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
