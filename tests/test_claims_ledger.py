import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))

import claims_ledger  # noqa: E402

PROFILE = {
    "claims_ledger": {
        "banned_topics": [
            {
                "name": "renewals",
                "pattern": r"\brenewals?\b",
                "instead": "retention campaigns",
            },
            {"name": "Iterable", "pattern": r"\biterable\b"},
            {"name": "broken", "pattern": "("},
            {"pattern": "missing name"},
        ],
        "banned_phrases": [
            {"text": "resonates deeply", "pattern": r"\bresonates? deeply\b"}
        ],
        "notes": ["No manager framing."],
        "anchors": {"clerical": "2,900+ accounts"},
    }
}


class ClaimsLedgerTest(unittest.TestCase):
    def setUp(self):
        self.ledger = claims_ledger.load(PROFILE)

    def test_load_skips_malformed_entries(self):
        self.assertEqual(
            [t[0] for t in self.ledger["topics"]], ["renewals", "Iterable"]
        )
        self.assertEqual(self.ledger["anchors"], {"clerical": "2,900+ accounts"})

    def test_empty_profile_is_empty_ledger(self):
        ledger = claims_ledger.load({})
        self.assertEqual(claims_ledger.prompt_block(ledger), "")
        self.assertEqual(
            claims_ledger.check_resume({"SUMMARY_TEXT": "renewals"}, ledger), []
        )

    def test_prompt_block_lists_topics_substitutes_phrases_notes(self):
        block = claims_ledger.prompt_block(self.ledger)
        self.assertIn("- renewals -> instead: retention campaigns", block)
        self.assertIn('"resonates deeply"', block)
        self.assertIn("No manager framing.", block)

    def test_retention_is_not_a_hit(self):
        self.assertEqual(
            claims_ledger.find_in_text("Ran retention campaigns", self.ledger), []
        )

    def test_check_resume_covers_every_section(self):
        data = {
            "SUMMARY_TEXT": "Drove renewals.",
            "WHY_TEXT": "Your mission resonates deeply with me.",
            "EXPERIENCE": [
                {"company": "Treering", "achievements": ["Built Iterable flows"]}
            ],
            "SKILLS": [{"Tools": "Salesforce, Iterable"}],
        }
        violations = claims_ledger.check_resume(data, self.ledger)
        self.assertEqual(len(violations), 4)
        self.assertTrue(all(v.startswith("Claims ledger:") for v in violations))
        self.assertIn("Use retention campaigns instead", violations[0])
        self.assertIn("Treering bullet", violations[2])

    def test_filter_texts_splits_clean_and_dropped(self):
        clean, dropped = claims_ledger.filter_texts(
            ["Add renewal metrics", "Lead with 2,900+ accounts"], self.ledger
        )
        self.assertEqual(clean, ["Lead with 2,900+ accounts"])
        self.assertEqual(dropped, ["Add renewal metrics"])

    def test_ledger_violation_is_soft(self):
        import orchestrator

        fatal, soft = orchestrator.partition_violations(
            ["Claims ledger: Summary claims 'renewals'"]
        )
        self.assertEqual(fatal, [])
        self.assertEqual(len(soft), 1)

    def test_anchor_for_picks_track(self):
        self.assertEqual(claims_ledger.anchor_for(self.ledger, True), "2,900+ accounts")
        self.assertEqual(claims_ledger.anchor_for(self.ledger, False), "")
        self.assertEqual(claims_ledger.anchor_block(""), "")

    def test_check_anchor_needs_a_number_in_summary(self):
        data = {
            "_summary_anchor": "Owned 2,900+ accounts",
            "SUMMARY_TEXT": "Generic opener.",
        }
        self.assertTrue(
            claims_ledger.check_anchor(data)[0].startswith("Summary anchor:")
        )
        data["SUMMARY_TEXT"] = "Owned <b>2,900</b>+ school accounts."
        self.assertEqual(claims_ledger.check_anchor(data), [])
        self.assertEqual(claims_ledger.check_anchor({"SUMMARY_TEXT": "x"}), [])
        data = {
            "_summary_anchor": "Generated $1M+, beating target by 17%",
            "SUMMARY_TEXT": "Leader with 10+ years.",
        }
        self.assertEqual(len(claims_ledger.check_anchor(data)), 1)

    def test_insert_anchor_after_first_sentence(self):
        data = {
            "_summary_anchor": "Generated $1M+, beating target by 17%",
            "SUMMARY_TEXT": "<strong>Leader with 10+ years.</strong> Builds sequences.",
        }
        self.assertTrue(claims_ledger.insert_anchor(data))
        self.assertEqual(
            data["SUMMARY_TEXT"],
            "<strong>Leader with 10+ years.</strong> "
            "Generated $1M+, beating target by 17%. Builds sequences.",
        )
        self.assertEqual(claims_ledger.check_anchor(data), [])
        self.assertFalse(claims_ledger.insert_anchor(data))

    def test_insert_anchor_replaces_numberless_rewording(self):
        data = {
            "_summary_anchor": "First outbound hire to generate $1M+",
            "SUMMARY_TEXT": "Leader. First outbound hire to beat goals. Builds sequences.",
        }
        claims_ledger.insert_anchor(data)
        self.assertEqual(
            data["SUMMARY_TEXT"],
            "Leader. First outbound hire to generate $1M+. Builds sequences.",
        )

    def test_insert_anchor_replaces_reworded_subject(self):
        data = {
            "_summary_anchor": "First outbound hire to generate $1M+",
            "SUMMARY_TEXT": "Leader. As the inaugural outbound hire, I beat goals. Builds.",
        }
        claims_ledger.insert_anchor(data)
        self.assertEqual(
            data["SUMMARY_TEXT"],
            "Leader. First outbound hire to generate $1M+. Builds.",
        )

    def test_anchor_violation_is_soft(self):
        import orchestrator

        hard, soft = orchestrator.partition_violations(["Summary anchor: missing"])
        self.assertEqual((hard, len(soft)), ([], 1))

    def test_unsupported_asks_names_jd_gaps(self):
        asks = claims_ledger.unsupported_asks(
            "Own renewals and expansion.", self.ledger
        )
        self.assertEqual(asks, [("renewals", "retention campaigns")])
        block = claims_ledger.asks_block(asks)
        self.assertIn("- renewals: use retention campaigns instead", block)
        self.assertEqual(claims_ledger.asks_block([]), "")


if __name__ == "__main__":
    unittest.main()
