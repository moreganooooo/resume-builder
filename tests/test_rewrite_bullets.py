import os
import sys
import unittest

import pandas as pd

SCRIPTS_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts")
sys.path.insert(0, SCRIPTS_DIR)

from rewrite_bullets import (  # noqa: E402
    KnowledgeBase,
    filter_claims_by_tags,
    filter_json_entries_by_tags,
    load_json_entries,
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


if __name__ == "__main__":
    unittest.main()
