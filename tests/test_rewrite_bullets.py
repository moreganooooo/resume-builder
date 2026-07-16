import os
import sys
import unittest
from unittest.mock import patch

import pandas as pd

SCRIPTS_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts")
sys.path.insert(0, SCRIPTS_DIR)

from rewrite_bullets import (  # noqa: E402
    KnowledgeBase,
    filter_claims_by_tags,
    filter_json_entries_by_tags,
    load_json_entries,
    process_bullet,
)


def _claims_df():
    return pd.DataFrame({
        "Claim / Finding": [
            "Built 62+ email sequences",
            "Managed Salesforce CRM data hygiene",
            "Led content committee governance",
            "Sourced $1M+ in revenue",
            "Designed brand identity for Element 8",
        ],
        "Metric(s)": ["62 sequences", "2000+ accounts", "100+ assets", "$1M+", "N/A"],
        "Confidence": ["High", "High", "High", "High", "High"],
        "Evidence / Detail": ["", "", "", "", ""],
    })


class TestFilterClaimsByTagsMaxRows(unittest.TestCase):

    def test_default_max_rows_matches_existing_constant(self):
        df = pd.concat([_claims_df()] * 5, ignore_index=True)  # 25 rows, all [email]-matchable
        filtered = filter_claims_by_tags(df, "[email]")
        self.assertLessEqual(len(filtered), 12)  # MAX_CLAIMS_ROWS default unchanged

    def test_custom_max_rows_caps_tighter(self):
        df = pd.concat([_claims_df()] * 5, ignore_index=True)
        filtered = filter_claims_by_tags(df, "[email]", max_rows=5)
        self.assertLessEqual(len(filtered), 5)


def _metric_entries():
    return [
        {"id": "m1", "category": "campaign_performance", "label": "Email open rate", "context": "PTA sequence, 74% open"},
        {"id": "m2", "category": "campaign_performance", "label": "Email reply rate", "context": "Hot Zone sequence, 39% reply"},
        {"id": "m3", "category": "ops", "label": "CRM pipeline scrub", "context": "Uncovered $3M+ in stale Salesforce pipeline"},
        {"id": "m4", "category": "design", "label": "Brand flyer", "context": "COVID response flyer, Illustrator"},
    ]


class TestFilterJsonEntriesByTags(unittest.TestCase):

    def test_keyword_match_filters_to_relevant_entries(self):
        filtered = filter_json_entries_by_tags(_metric_entries(), "[email]", max_rows=5)
        ids = {e["id"] for e in filtered}
        self.assertIn("m1", ids)
        self.assertIn("m2", ids)

    def test_respects_max_rows_cap(self):
        entries = _metric_entries() * 3  # 12 entries, all [ops]-matchable via "salesforce"/"crm"
        filtered = filter_json_entries_by_tags(entries, "[ops]", max_rows=3)
        self.assertLessEqual(len(filtered), 3)

    def test_too_few_matches_falls_back_to_head(self):
        # "[generalist]" has no keywords in CLAIM_TAG_KEYWORDS -> include_all -> head(max_rows)
        filtered = filter_json_entries_by_tags(_metric_entries(), "[generalist]", max_rows=2)
        self.assertEqual(len(filtered), 2)

    def test_load_json_entries_reads_list_under_key(self):
        entries = load_json_entries(
            os.path.join(SCRIPTS_DIR, "..", "resume-engine", "knowledge_base", "verified_metrics.json"),
            "metrics",
        )
        self.assertIsInstance(entries, list)
        self.assertGreater(len(entries), 0)
        self.assertIn("category", entries[0])


class TestKnowledgeBaseGemmaTier(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.kb = KnowledgeBase()

    def test_gemma_static_prefix_excludes_profile(self):
        # profile.yml is dropped entirely from Gemma's tier -- its trimmed
        # content includes "target_roles:" per trim_profile_yml's KEEP_SECTIONS.
        if self.kb.profile:
            self.assertNotIn(self.kb.profile, self.kb.gemma_static_prefix)

    def test_gemma_static_prefix_includes_guardrails_and_voice(self):
        if self.kb.verified_facts:
            self.assertIn("VERIFIED FACTS", self.kb.gemma_static_prefix)
        if self.kb.verified_tools:
            self.assertIn("VERIFIED TOOLS", self.kb.gemma_static_prefix)
        if self.kb.voice_anchors:
            self.assertIn("VOICE ANCHORS", self.kb.gemma_static_prefix)

    def test_gemma_static_prefix_smaller_than_full(self):
        self.assertLess(len(self.kb.gemma_static_prefix), len(self.kb.static_prefix))

    def test_gemma_segment_excludes_projects_for_non_treering_bullets(self):
        # verified_projects.json is 10/12 Treering-employer entries --
        # tag-only filtering (no company check) let Treering project
        # detail leak into non-Treering bullets on keyword overlap alone.
        # Gemma's segment for a non-Treering company must never include
        # the "VERIFIED PROJECTS" section at all.
        df = pd.DataFrame({
            "Role / Company": ["Inside Sales Team"],
            "Tags": ["[email]"],
        })
        self.kb.warm_segment_cache(df)
        gemma_block = self.kb.context_block_for_bullet_gemma("Inside Sales Team", "[email]")
        self.assertNotIn("VERIFIED PROJECTS", gemma_block)

    def test_context_block_for_bullet_gemma_returns_slim_segment(self):
        df = pd.DataFrame({
            "Role / Company": ["Treering Yearbooks"],
            "Tags": ["[email]"],
        })
        self.kb.warm_segment_cache(df)
        gemma_block = self.kb.context_block_for_bullet_gemma("Treering Yearbooks", "[email]")
        full_block = self.kb.context_block_for_bullet("Treering Yearbooks", "[email]")
        self.assertIsInstance(gemma_block, str)
        self.assertLessEqual(len(gemma_block), len(full_block))


class TestProcessBulletGemmaHandoff(unittest.TestCase):

    def setUp(self):
        self.kb = KnowledgeBase()
        df = pd.DataFrame({
            "Role / Company": ["Acme Corp"],
            "Tags": ["[content]"],
        })
        self.kb.warm_segment_cache(df)
        self.row = pd.Series({
            "Bullet Point": "Wrote content for a team.",
            "Role / Company": "Acme Corp",
            "Tags": "[content]",
            "weaknesses": "",
            "accuracy_score": None, "believability_score": None,
            "clarity_score": None, "ats_value": None, "manager_test": None,
        })

    @patch("rewrite_bullets.time.sleep", lambda *a, **kw: None)
    @patch("rewrite_bullets.score_bullet")
    @patch("rewrite_bullets.GeminiClient.generate")
    def test_gemma_exhaustion_falls_back_to_flash_lite_with_full_context(self, mock_generate, mock_score):
        # First call (Gemma) exhausts and returns None; second call
        # (flash-lite) succeeds. Assert: exactly 2 generate() calls, the
        # first targets gemma-4-31b-it with model_fallback=False, the
        # second targets gemini-3.1-flash-lite with the FULL context
        # (longer than Gemma's slim one).
        mock_generate.side_effect = [
            (None, {}),
            ('{"rewritten_bullet": "Authored content for a cross-functional team.", "reasoning": "", "context_gaps": ""}', {}),
        ]
        mock_score.return_value = {
            "accuracy_score": 95, "believability_score": 95, "clarity_score": 95,
            "ats_value": 90, "manager_test": "PASS", "weaknesses": "",
        }

        result = process_bullet(
            self.row, self.kb,
            rewrite_system="sys", rewrite_system_gemma="sys-gemma",
            score_system="score-sys", dry_run=False,
        )

        self.assertEqual(mock_generate.call_count, 2)
        first_call_kwargs = mock_generate.call_args_list[0].kwargs
        second_call_kwargs = mock_generate.call_args_list[1].kwargs

        self.assertEqual(first_call_kwargs["model"], "gemma-4-31b-it")
        self.assertEqual(first_call_kwargs["model_fallback"], False)
        # Gemma must get the slim system prompt, not the full one -- see
        # rewrite_rules_block_gemma in RulesBundle.
        self.assertEqual(first_call_kwargs["system_instruction"], "sys-gemma")
        # Gemma's own retry ladder must stay short -- model_fallback=False
        # means GeminiClient.generate() won't internally bail early after 2
        # consecutive failures anymore, so process_bullet() must cap
        # max_retries itself or a still-oversized bullet burns the full
        # 6-attempt backoff ladder (~5 minutes) before handing off.
        self.assertEqual(first_call_kwargs["max_retries"], 2)

        self.assertEqual(second_call_kwargs["model"], "gemini-3.1-flash-lite")
        # MODEL_FALLBACKS is bidirectional -- flash-lite must never be
        # allowed to internally bounce back to Gemma with the full context.
        self.assertEqual(second_call_kwargs["model_fallback"], False)
        self.assertEqual(second_call_kwargs["system_instruction"], "sys")
        self.assertGreater(
            len(second_call_kwargs["contents"]), len(first_call_kwargs["contents"])
        )
        self.assertEqual(result["rewrite_status"], "KEEP")


if __name__ == "__main__":
    unittest.main()
