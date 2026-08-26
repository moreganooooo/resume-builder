"""
Unit tests for facts_manager.py and D10 Human-in-the-Loop staged_facts.json gate.
"""

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

import bootstrap_extractors  # noqa: E402
import facts_manager  # noqa: E402
import profile_paths  # noqa: E402


class BaseFactsTest(unittest.TestCase):

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self._iso = profile_paths.isolate_for_tests(self._tmp.name)
        self._iso.__enter__()
        self.profile = "testuser"
        os.makedirs(
            os.path.join(profile_paths.PROFILES_DIR, self.profile, "knowledge_base"),
            exist_ok=True,
        )
        self._orig_profile = os.environ.get("RESUME_PROFILE")
        os.environ["RESUME_PROFILE"] = self.profile

    def tearDown(self):
        if self._orig_profile is not None:
            os.environ["RESUME_PROFILE"] = self._orig_profile
        else:
            os.environ.pop("RESUME_PROFILE", None)
        self._iso.__exit__(None, None, None)
        self._tmp.cleanup()


class TestFactsManagerStorage(BaseFactsTest):

    def test_get_paths(self):
        v_path = facts_manager.get_verified_facts_path()
        s_path = facts_manager.get_staged_facts_path()
        self.assertTrue(v_path.endswith("verified_facts.json"))
        self.assertTrue(s_path.endswith("staged_facts.json"))
        self.assertEqual(os.path.dirname(v_path), os.path.dirname(s_path))

    def test_load_verified_facts_empty_starter(self):
        data = facts_manager.load_verified_facts()
        self.assertIn("_meta", data)
        self.assertEqual(data["facts"], [])

    def test_load_verified_facts_raises_on_corrupt_file(self):
        path = facts_manager.get_verified_facts_path()
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w") as f:
            f.write("{corrupt json content")

        with self.assertRaises(Exception):
            facts_manager.load_verified_facts()

    def test_save_verified_facts(self):
        data = {
            "facts": [
                {
                    "id": "fact_001",
                    "label": "Built Platform",
                    "claim": "Built core telemetry pipeline in 2022",
                    "confidence": "High",
                }
            ]
        }
        saved = facts_manager.save_verified_facts(data)
        self.assertTrue(saved)

        loaded = facts_manager.load_verified_facts()
        self.assertEqual(len(loaded["facts"]), 1)
        self.assertEqual(loaded["_meta"]["total_entries"], 1)
        self.assertTrue(loaded["_meta"]["last_updated"])

    def test_load_staged_facts_empty_starter(self):
        data = facts_manager.load_staged_facts()
        self.assertIn("_meta", data)
        self.assertEqual(data["staged_facts"], [])

    def test_load_staged_facts_raises_on_corrupt_file(self):
        path = facts_manager.get_staged_facts_path()
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w") as f:
            f.write("not-valid-json")

        with self.assertRaises(Exception):
            facts_manager.load_staged_facts()

    def test_save_staged_facts(self):
        data = {
            "staged_facts": [
                {
                    "id": "staged_fact_001",
                    "label": "Candidate Claim",
                    "claim": "Led migration of database",
                }
            ]
        }
        saved = facts_manager.save_staged_facts(data)
        self.assertTrue(saved)

        loaded = facts_manager.load_staged_facts()
        self.assertEqual(len(loaded["staged_facts"]), 1)
        self.assertEqual(loaded["_meta"]["total_entries"], 1)


class TestFactsManagerStaging(BaseFactsTest):

    def test_stage_facts_creates_staged_entries(self):
        candidates = [
            {
                "label": "Built ETL Pipeline",
                "claim": "Designed daily ETL batch processing 50M records.",
                "source": "cv.md",
                "confidence": "High",
                "category": "platform_ops",
            },
            {
                "label": "Trained SDR Pod",
                "claim": "Ran onboarding workshops for 12 new hires.",
                "source": "interview_notes.docx",
                "confidence": "Medium",
                "category": "enablement",
            },
        ]

        count = facts_manager.stage_facts(candidates, source="document_ingestion")
        self.assertEqual(count, 2)

        staged_data = facts_manager.load_staged_facts()
        self.assertEqual(len(staged_data["staged_facts"]), 2)
        self.assertEqual(staged_data["staged_facts"][0]["id"], "staged_fact_001")
        self.assertEqual(staged_data["staged_facts"][0]["status"], "staged")
        self.assertEqual(staged_data["staged_facts"][1]["id"], "staged_fact_002")

        # Crucial verification: verified_facts.json must NOT have been created or modified
        v_path = facts_manager.get_verified_facts_path()
        self.assertFalse(os.path.exists(v_path))

    def test_stage_facts_deduplicates_against_existing(self):
        # Seed an existing verified fact
        initial_verified = {
            "facts": [
                {
                    "id": "fact_001",
                    "label": "Built ETL Pipeline",
                    "claim": "Designed daily ETL batch processing 50M records.",
                    "category": "platform_ops",
                }
            ]
        }
        facts_manager.save_verified_facts(initial_verified)

        candidates = [
            # Exact duplicate of verified fact (different casing/spacing)
            {
                "label": "built etl pipeline",
                "claim": "Designed daily ETL batch processing 50M records.",
            },
            # Genuinely new candidate
            {
                "label": "Authored Architecture Guide",
                "claim": "Wrote comprehensive 40-page system design guide.",
            },
        ]

        count = facts_manager.stage_facts(candidates)
        self.assertEqual(count, 1)

        staged_data = facts_manager.load_staged_facts()
        self.assertEqual(len(staged_data["staged_facts"]), 1)
        self.assertEqual(
            staged_data["staged_facts"][0]["label"], "Authored Architecture Guide"
        )


class TestFactsManagerPromotionAndRejection(BaseFactsTest):

    def setUp(self):
        super().setUp()
        # Seed 1 verified fact and 2 staged facts
        facts_manager.save_verified_facts(
            {
                "facts": [
                    {
                        "id": "fact_001",
                        "label": "Existing Verified Fact",
                        "claim": "Existing verified claim.",
                        "confidence": "High",
                    }
                ]
            }
        )
        facts_manager.stage_facts(
            [
                {
                    "label": "Candidate One",
                    "claim": "Candidate claim 1.",
                    "confidence": "High",
                },
                {
                    "label": "Candidate Two",
                    "claim": "Candidate claim 2.",
                    "confidence": "Medium",
                },
            ]
        )

    def test_promote_fact_single(self):
        promoted = facts_manager.promote_fact("staged_fact_001")
        self.assertIsNotNone(promoted)
        self.assertEqual(promoted["id"], "fact_002")
        self.assertEqual(promoted["label"], "Candidate One")
        self.assertNotIn("staged_at", promoted)
        self.assertNotIn("status", promoted)

        # Verify staged facts now only has 1 item
        staged_data = facts_manager.load_staged_facts()
        self.assertEqual(len(staged_data["staged_facts"]), 1)
        self.assertEqual(staged_data["staged_facts"][0]["id"], "staged_fact_002")

        # Verify verified facts now has 2 items (preserving original fact_001)
        verified_data = facts_manager.load_verified_facts()
        self.assertEqual(len(verified_data["facts"]), 2)
        self.assertEqual(verified_data["facts"][0]["id"], "fact_001")
        self.assertEqual(verified_data["facts"][1]["id"], "fact_002")
        self.assertEqual(verified_data["_meta"]["total_entries"], 2)

    def test_promote_fact_with_edits(self):
        edited_payload = {
            "label": "Refined Label",
            "claim": "Refined and quantified claim text.",
            "source": "meeting_notes.pdf",
            "confidence": "High",
            "use_in_resume": True,
            "caveat": "Co-authored with director",
            "category": "leadership",
        }
        promoted = facts_manager.promote_fact(
            "staged_fact_001", edited_fact=edited_payload
        )
        self.assertIsNotNone(promoted)
        self.assertEqual(promoted["id"], "fact_002")
        self.assertEqual(promoted["label"], "Refined Label")
        self.assertEqual(promoted["caveat"], "Co-authored with director")

    def test_reject_fact(self):
        rejected = facts_manager.reject_fact("staged_fact_001")
        self.assertTrue(rejected)

        staged_data = facts_manager.load_staged_facts()
        self.assertEqual(len(staged_data["staged_facts"]), 1)
        self.assertEqual(staged_data["staged_facts"][0]["id"], "staged_fact_002")

        # Verified facts untouched
        verified_data = facts_manager.load_verified_facts()
        self.assertEqual(len(verified_data["facts"]), 1)

    def test_promote_all_staged(self):
        count = facts_manager.promote_all_staged()
        self.assertEqual(count, 2)

        staged_data = facts_manager.load_staged_facts()
        self.assertEqual(len(staged_data["staged_facts"]), 0)

        verified_data = facts_manager.load_verified_facts()
        self.assertEqual(len(verified_data["facts"]), 3)

    def test_reject_all_staged(self):
        count = facts_manager.reject_all_staged()
        self.assertEqual(count, 2)

        staged_data = facts_manager.load_staged_facts()
        self.assertEqual(len(staged_data["staged_facts"]), 0)

        verified_data = facts_manager.load_verified_facts()
        self.assertEqual(len(verified_data["facts"]), 1)


class TestFactsManagerInteractiveReview(BaseFactsTest):

    def setUp(self):
        super().setUp()
        facts_manager.stage_facts(
            [
                {"label": "Initiative A", "claim": "Ran initiative A."},
                {"label": "Initiative B", "claim": "Ran initiative B."},
            ]
        )

    @patch("questionary.select")
    def test_review_interactive_accept_and_exit(self, mock_select):
        mock_select.return_value.ask.side_effect = [
            "✓ Accept & Verify (Promote to verified_facts.json)",
            "⏹ Exit Review",
        ]
        tally = facts_manager.review_staged_facts_interactive()
        self.assertEqual(tally["accepted"], 1)

        verified_data = facts_manager.load_verified_facts()
        self.assertEqual(len(verified_data["facts"]), 1)

    @patch("questionary.text")
    @patch("questionary.select")
    def test_review_interactive_edit_and_accept(self, mock_select, mock_text):
        mock_select.return_value.ask.side_effect = [
            "✎ Edit & Accept (Refine claim text before promoting)",
            "⏹ Exit Review",
        ]
        mock_text.return_value.ask.side_effect = [
            "Initiative A Edited",
            "Detailed claim for A",
            "No caveat",
            "leadership",
        ]
        tally = facts_manager.review_staged_facts_interactive()
        self.assertEqual(tally["edited"], 1)

        verified_data = facts_manager.load_verified_facts()
        self.assertEqual(verified_data["facts"][0]["label"], "Initiative A Edited")


class TestExtractAndStageFacts(BaseFactsTest):

    @patch("bootstrap_extractors.GeminiClient.generate")
    @patch("bootstrap_extractors.GeminiClient.parse_json")
    def test_extract_and_stage_facts_end_to_end(self, mock_parse, mock_gen):
        mock_gen.return_value = ("raw json", 100)
        mock_parse.return_value = {
            "facts": [
                {
                    "label": "Scaled Team",
                    "claim": "Scaled engineering team from 3 to 15 engineers.",
                    "source": "interview.md",
                    "confidence": "High",
                    "category": "leadership",
                }
            ]
        }

        staged_count = bootstrap_extractors.extract_and_stage_facts(
            text="Some resume text detailing leadership...",
            source="resume_ingest",
        )
        self.assertEqual(staged_count, 1)

        # Staged facts file has candidate
        staged_data = facts_manager.load_staged_facts()
        self.assertEqual(len(staged_data["staged_facts"]), 1)
        self.assertEqual(staged_data["staged_facts"][0]["label"], "Scaled Team")

        # Verified facts remains empty / untouched
        v_path = facts_manager.get_verified_facts_path()
        self.assertFalse(os.path.exists(v_path))


if __name__ == "__main__":
    unittest.main()
