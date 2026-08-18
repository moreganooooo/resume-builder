import os
import sys
import unittest
from unittest.mock import patch

import pandas as pd

SCRIPTS_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts"
)
sys.path.insert(0, SCRIPTS_DIR)

from rewrite_bullets import (  # noqa: E402
    KB_DIR,
    RULES_DIR,
    SCORING_DIR,
    KnowledgeBase,
    RulesBundle,
    filter_claims_by_tags,
    filter_json_entries_by_tags,
    filter_projects_by_employer,
    load_json_entries,
    process_bullet,
    score_bullet,
)


def _claims_df():
    return pd.DataFrame(
        {
            "Claim / Finding": [
                "Built 62+ email sequences",
                "Managed Salesforce CRM data hygiene",
                "Led content committee governance",
                "Sourced $1M+ in revenue",
                "Designed brand identity for Element 8",
            ],
            "Metric(s)": [
                "62 sequences",
                "2000+ accounts",
                "100+ assets",
                "$1M+",
                "N/A",
            ],
            "Confidence": ["High", "High", "High", "High", "High"],
            "Evidence / Detail": ["", "", "", "", ""],
        }
    )


class TestFilterClaimsByTagsMaxRows(unittest.TestCase):

    def test_default_max_rows_matches_existing_constant(self):
        df = pd.concat(
            [_claims_df()] * 5, ignore_index=True
        )  # 25 rows, all [email]-matchable
        filtered = filter_claims_by_tags(df, "[email]")
        self.assertLessEqual(len(filtered), 12)  # MAX_CLAIMS_ROWS default unchanged

    def test_custom_max_rows_caps_tighter(self):
        df = pd.concat([_claims_df()] * 5, ignore_index=True)
        filtered = filter_claims_by_tags(df, "[email]", max_rows=5)
        self.assertLessEqual(len(filtered), 5)


def _metric_entries():
    return [
        {
            "id": "m1",
            "category": "campaign_performance",
            "label": "Email open rate",
            "context": "PTA sequence, 74% open",
        },
        {
            "id": "m2",
            "category": "campaign_performance",
            "label": "Email reply rate",
            "context": "Hot Zone sequence, 39% reply",
        },
        {
            "id": "m3",
            "category": "ops",
            "label": "CRM pipeline scrub",
            "context": "Uncovered $3M+ in stale Salesforce pipeline",
        },
        {
            "id": "m4",
            "category": "design",
            "label": "Brand flyer",
            "context": "COVID response flyer, Illustrator",
        },
    ]


class TestFilterJsonEntriesByTags(unittest.TestCase):

    def test_keyword_match_filters_to_relevant_entries(self):
        filtered = filter_json_entries_by_tags(_metric_entries(), "[email]", max_rows=5)
        ids = {e["id"] for e in filtered}
        self.assertIn("m1", ids)
        self.assertIn("m2", ids)

    def test_respects_max_rows_cap(self):
        entries = (
            _metric_entries() * 3
        )  # 12 entries, all [ops]-matchable via "salesforce"/"crm"
        filtered = filter_json_entries_by_tags(entries, "[ops]", max_rows=3)
        self.assertLessEqual(len(filtered), 3)

    def test_too_few_matches_falls_back_to_head(self):
        # "[generalist]" has no keywords in profile.yml's tags: -> include_all -> head(max_rows)
        filtered = filter_json_entries_by_tags(
            _metric_entries(), "[generalist]", max_rows=2
        )
        self.assertEqual(len(filtered), 2)

    def test_load_json_entries_reads_list_under_key(self):
        path = os.path.join(KB_DIR, "verified_metrics.json")
        if not os.path.exists(path):
            import tempfile

            with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as f:
                json.dump(
                    {"metrics": [{"category": "email", "metric": "74% open rate"}]}, f
                )
                temp_path = f.name
            try:
                entries = load_json_entries(temp_path, "metrics")
                self.assertIsInstance(entries, list)
                self.assertGreater(len(entries), 0)
                self.assertIn("category", entries[0])
            finally:
                if os.path.exists(temp_path):
                    os.remove(temp_path)
        else:
            entries = load_json_entries(path, "metrics")
            self.assertIsInstance(entries, list)
            self.assertGreater(len(entries), 0)
            self.assertIn("category", entries[0])


class TestKnowledgeBaseGemmaTier(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.kb = KnowledgeBase()
        if not cls.kb.static_prefix:
            cls.kb.static_prefix = "STATIC PREFIX " * 20
            cls.kb.gemma_static_prefix = "GEMMA PREFIX"
        if not cls.kb.projects_entries:
            cls.kb.projects_entries = [
                {
                    "employer": "Treering Yearbooks",
                    "name": "Outreach.io Platform Rollout",
                },
                {
                    "employer": "Element 8 / Strategy LLC",
                    "name": "Strategy LLC Brand Identity",
                },
            ]

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
        df = pd.DataFrame(
            {
                "Role / Company": ["Inside Sales Team"],
                "Tags": ["[email]"],
            }
        )
        self.kb.warm_segment_cache(df)
        gemma_block = self.kb.context_block_for_bullet_gemma(
            "Inside Sales Team", "[email]"
        )
        self.assertNotIn("VERIFIED PROJECTS", gemma_block)

    def test_context_block_for_bullet_gemma_returns_slim_segment(self):
        df = pd.DataFrame(
            {
                "Role / Company": ["Treering Yearbooks"],
                "Tags": ["[email]"],
            }
        )
        self.kb.warm_segment_cache(df)
        gemma_block = self.kb.context_block_for_bullet_gemma(
            "Treering Yearbooks", "[email]"
        )
        full_block = self.kb.context_block_for_bullet("Treering Yearbooks", "[email]")
        self.assertIsInstance(gemma_block, str)
        self.assertLessEqual(len(gemma_block), len(full_block))

    def test_static_prefix_never_includes_verified_projects(self):
        # Regression test: verified_projects.json mixes multiple employers
        # (Treering, VML, Element 8/Strategy LLC). It used to live in the
        # static prefix, which is shared byte-for-byte across every bullet
        # rewrite regardless of company -- the actual root cause of a
        # Treering bullet's rewrite borrowing the Strategy LLC brand-identity
        # project. Project detail must only ever reach a rewrite prompt via
        # the per-bullet, employer-filtered segment bundle.
        self.assertNotIn("VERIFIED PROJECTS", self.kb.static_prefix)
        self.assertNotIn("VERIFIED PROJECTS", self.kb.gemma_static_prefix)

    def test_full_tier_segment_scopes_projects_to_own_employer(self):
        df = pd.DataFrame(
            {
                "Role / Company": [
                    "Treering Yearbooks",
                    "Element 8 / Strategy LLC",
                    "Inside Sales Team",
                ],
                "Tags": ["[email]", "[brand]", "[email]"],
            }
        )
        self.kb.warm_segment_cache(df)

        treering_block = self.kb.context_block_for_bullet(
            "Treering Yearbooks", "[email]"
        )
        self.assertIn("VERIFIED PROJECTS (Treering Yearbooks only)", treering_block)
        self.assertNotIn("Strategy LLC Brand Identity", treering_block)

        strategy_block = self.kb.context_block_for_bullet(
            "Element 8 / Strategy LLC", "[brand]"
        )
        self.assertIn("Strategy LLC Brand Identity", strategy_block)
        self.assertNotIn(
            "Outreach.io Platform Rollout", strategy_block
        )  # a Treering project

        ist_block = self.kb.context_block_for_bullet("Inside Sales Team", "[email]")
        self.assertNotIn("VERIFIED PROJECTS", ist_block)


class TestRulesBundleIncludesRedundancyRules(unittest.TestCase):
    # Regression coverage: style_rules.yaml gaining a new top-level key
    # (redundancy_rules) only reaches the FULL rewrite tier automatically
    # -- the Gemma tier (gemma-4-31b-it, this pipeline's primary/highest-
    # volume rewrite model per this file's own docstring) gets a
    # hand-picked subset of keys, so a new rule that isn't explicitly
    # added to that subset would silently never reach the model doing
    # most of the actual rewriting. This is exactly the class of gap that
    # let a rewrite reintroduce a bullet's own employer name into its own
    # text after the bullet bank had already been manually cleaned of it.

    @classmethod
    def setUpClass(cls):
        cls.rules = RulesBundle(RULES_DIR, SCORING_DIR)

    def test_redundancy_rules_reach_the_full_tier(self):
        self.assertIn("redundancy_rules", self.rules.rewrite_rules_block)
        self.assertIn("own_employer_name", self.rules.rewrite_rules_block)
        self.assertIn("unneeded_calendar_dates", self.rules.rewrite_rules_block)

    def test_redundancy_rules_reach_the_gemma_slim_tier(self):
        self.assertIn("redundancy_rules", self.rules.rewrite_rules_block_gemma)
        self.assertIn("own_employer_name", self.rules.rewrite_rules_block_gemma)
        self.assertIn("unneeded_calendar_dates", self.rules.rewrite_rules_block_gemma)

    def test_redundancy_rules_reach_the_score_block_too(self):
        # Scoring (which decides whether a bullet needs a rewrite at all,
        # not just what a rewrite should avoid) must see this rule too --
        # otherwise a bullet that already restates its own employer name
        # (e.g. straight out of bootstrap extraction, before any rewrite
        # ever touches it) would score fine and never get flagged.
        self.assertIn("REDUNDANCY", self.rules.score_rules_block)
        self.assertIn("own_employer_name", self.rules.score_rules_block)
        self.assertIn("unneeded_calendar_dates", self.rules.score_rules_block)


class TestScoreBulletSendsRoleCompanyContext(unittest.TestCase):
    # Regression coverage: score_bullet() used to send only the bullet
    # text and a tag-derived persona -- with no company context at all,
    # the scoring model had no way to know a bullet was restating its own
    # employer's name, even with the redundancy rule now in its prompt.

    @patch("rewrite_bullets.GeminiClient.generate")
    def test_role_company_appears_in_the_scoring_payload(self, mock_generate):
        mock_generate.return_value = (
            '{"accuracy_score": 90, "believability_score": 90, '
            '"clarity_score": 90, "ats_value": 90, "manager_test": "PASS", '
            '"weaknesses": "None"}',
            {},
        )
        score_bullet(
            "Built a complete brand identity from scratch.",
            tags="[brand]",
            score_system="system prompt",
            role_company="Acme Corp",
        )
        sent_contents = mock_generate.call_args.kwargs["contents"]
        self.assertIn("Acme Corp", sent_contents)

    @patch("rewrite_bullets.GeminiClient.generate")
    def test_missing_role_company_defaults_to_empty_not_a_crash(self, mock_generate):
        mock_generate.return_value = (
            '{"accuracy_score": 90, "believability_score": 90, '
            '"clarity_score": 90, "ats_value": 90, "manager_test": "PASS", '
            '"weaknesses": "None"}',
            {},
        )
        score_bullet("A bullet.", tags="[brand]", score_system="system prompt")
        mock_generate.assert_called_once()


class TestFilterProjectsByEmployer(unittest.TestCase):

    PROJECTS = [
        {
            "id": "proj_treering",
            "name": "Outreach.io Platform Rollout",
            "employer": "Treering Yearbooks",
        },
        {
            "id": "proj_vml",
            "name": "VML Carlson Hotels Digital Strategy Report",
            "employer": "VML (agency internship)",
        },
        {
            "id": "proj_strategy",
            "name": "Strategy LLC Brand Identity System",
            "employer": "Element 8 → Strategy LLC",
        },
    ]

    def test_matches_only_the_bullets_own_employer(self):
        result = filter_projects_by_employer(self.PROJECTS, "Treering Yearbooks")
        self.assertEqual([p["id"] for p in result], ["proj_treering"])

    def test_handles_differing_separator_conventions(self):
        # CSV uses "/" ("Element 8 / Strategy LLC"); verified_projects.json
        # uses "→" ("Element 8 → Strategy LLC") -- must still match.
        result = filter_projects_by_employer(self.PROJECTS, "Element 8 / Strategy LLC")
        self.assertEqual([p["id"] for p in result], ["proj_strategy"])

    def test_matches_despite_parenthetical_suffix(self):
        result = filter_projects_by_employer(self.PROJECTS, "VML")
        self.assertEqual([p["id"] for p in result], ["proj_vml"])

    def test_unrelated_company_gets_no_projects(self):
        result = filter_projects_by_employer(self.PROJECTS, "Inside Sales Team")
        self.assertEqual(result, [])

    def test_empty_role_company_gets_no_projects(self):
        self.assertEqual(filter_projects_by_employer(self.PROJECTS, ""), [])


class TestProcessBulletGemmaHandoff(unittest.TestCase):

    def setUp(self):
        self.kb = KnowledgeBase()
        self.kb.static_prefix = "FULL STATIC PREFIX WITH EXTRA CONTEXT " * 10
        self.kb.gemma_static_prefix = "GEMMA PREFIX"
        self.kb.context_block_for_bullet = (
            lambda *a: "FULL CONTEXT BLOCK WITH EXTRA INFORMATION " * 10
        )
        self.kb.context_block_for_bullet_gemma = lambda *a: "GEMMA SLIM BLOCK"
        df = pd.DataFrame(
            {
                "Role / Company": ["Acme Corp"],
                "Tags": ["[content]"],
            }
        )
        self.kb.warm_segment_cache(df)
        self.row = pd.Series(
            {
                "Bullet Point": "Wrote content for a team.",
                "Role / Company": "Acme Corp",
                "Tags": "[content]",
                "weaknesses": "",
                "accuracy_score": None,
                "believability_score": None,
                "clarity_score": None,
                "ats_value": None,
                "manager_test": None,
            }
        )

    @patch("rewrite_bullets.time.sleep", lambda *a, **kw: None)
    @patch("rewrite_bullets.score_bullet")
    @patch("rewrite_bullets.GeminiClient.generate")
    def test_gemma_exhaustion_falls_back_to_flash_lite_with_full_context(
        self, mock_generate, mock_score
    ):
        # First call (Gemma) exhausts and returns None; second call
        # (flash-lite) succeeds. Assert: exactly 2 generate() calls, the
        # first targets gemma-4-31b-it with model_fallback=False, the
        # second targets gemini-3.1-flash-lite with the FULL context
        # (longer than Gemma's slim one).
        mock_generate.side_effect = [
            (None, {}),
            (
                '{"rewritten_bullet": "Authored content for a cross-functional team.", "reasoning": "", "context_gaps": ""}',
                {},
            ),
        ]
        mock_score.return_value = {
            "accuracy_score": 95,
            "believability_score": 95,
            "clarity_score": 95,
            "ats_value": 90,
            "manager_test": "PASS",
            "weaknesses": "",
        }

        result = process_bullet(
            self.row,
            self.kb,
            rewrite_system="sys",
            rewrite_system_gemma="sys-gemma",
            score_system="score-sys",
            dry_run=False,
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

    @patch("rewrite_bullets.time.sleep", lambda *a, **kw: None)
    @patch("rewrite_bullets.score_bullet")
    @patch("rewrite_bullets.GeminiClient.generate")
    def test_start_model_skips_gemma_entirely(self, mock_generate, mock_score):
        # audit_keepers.py's --auto-rewrite passes start_model=REWRITE_FALLBACK_MODEL
        # for bullets that already failed a first Gemma-led pass -- confirm
        # the very first attempt targets that model directly, with no Gemma
        # attempt (and therefore no slim-context system prompt) at all.
        mock_generate.return_value = (
            '{"rewritten_bullet": "Authored content for a cross-functional team.", "reasoning": "", "context_gaps": ""}',
            {},
        )
        mock_score.return_value = {
            "accuracy_score": 95,
            "believability_score": 95,
            "clarity_score": 95,
            "ats_value": 90,
            "manager_test": "PASS",
            "weaknesses": "",
        }

        result = process_bullet(
            self.row,
            self.kb,
            rewrite_system="sys",
            rewrite_system_gemma="sys-gemma",
            score_system="score-sys",
            dry_run=False,
            start_model="gemini-3.1-flash-lite",
        )

        self.assertEqual(mock_generate.call_count, 1)
        call_kwargs = mock_generate.call_args.kwargs
        self.assertEqual(call_kwargs["model"], "gemini-3.1-flash-lite")
        self.assertEqual(call_kwargs["system_instruction"], "sys")
        self.assertEqual(result["rewrite_status"], "KEEP")


if __name__ == "__main__":
    unittest.main()
