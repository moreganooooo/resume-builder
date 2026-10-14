import os
import re
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))

import critique_recs

LEDGER = {
    "topics": [("renewals", re.compile(r"\brenewals?\b", re.I), "retention campaigns")],
    "phrases": [],
    "notes": [],
    "anchors": {},
}
RESUME = {
    "SUMMARY_TEXT": "Sales leader who owned 2,900+ school accounts.",
    "EXPERIENCE": [
        {"company": "Treering", "achievements": ["Built outbound sequences."]}
    ],
    "_private": "hidden target",
}


def _sort(recs, **kw):
    return critique_recs.sort_recommendations(recs, RESUME, ledger=LEDGER, **kw)


class SortRecommendationsTest(unittest.TestCase):
    def test_targeted_edit_kept(self):
        rec = {
            "section": "Summary",
            "target_text": "owned 2,900+ school accounts",
            "action": "Rewrite to lead with the number",
            "evidence": "",
        }
        out = _sort([rec])
        self.assertEqual(len(out["recommendations"]), 1)
        self.assertIn("2,900+", out["recommendations"][0])

    def test_missing_target_dropped(self):
        rec = {
            "section": "Summary",
            "target_text": "hidden target",
            "action": "Rewrite it",
            "evidence": "",
        }
        self.assertEqual(len(_sort([rec])["dropped"]), 1)

    def test_targeted_verb_without_target_dropped(self):
        rec = {
            "section": "Summary",
            "target_text": "",
            "action": "Shorten it",
            "evidence": "",
        }
        self.assertEqual(len(_sort([rec])["dropped"]), 1)

    def test_add_without_evidence_is_gap(self):
        rec = {
            "section": "Skills",
            "target_text": "",
            "action": "Add HubSpot",
            "evidence": "",
        }
        self.assertEqual(len(_sort([rec])["gaps"]), 1)

    def test_add_with_evidence_kept(self):
        rec = {
            "section": "Skills",
            "target_text": "",
            "action": "Add Outreach.io",
            "evidence": "Used Outreach.io daily at Treering",
        }
        self.assertEqual(len(_sort([rec])["recommendations"]), 1)

    def test_ledger_hit_is_gap(self):
        self.assertEqual(
            _sort(["Mention renewals in the Summary"])["gaps"],
            ["Mention renewals in the Summary"],
        )

    def test_unsupported_ask_is_gap(self):
        out = _sort(["Add Tableau dashboards"], unsupported_asks=["Tableau"])
        self.assertEqual(len(out["gaps"]), 1)

    def test_interview_advice_is_note(self):
        out = _sort(["Prepare to discuss CRM migrations in the interview"])
        self.assertEqual(len(out["interview_notes"]), 1)

    def test_plain_string_passes_through(self):
        out = _sort(["Tighten the second Treering bullet"])
        self.assertEqual(out["recommendations"], ["Tighten the second Treering bullet"])

    def test_question_action_stays_bare(self):
        rec = {
            "section": "Why",
            "target_text": "",
            "action": "Which campus did you visit?",
            "evidence": "",
        }
        self.assertEqual(critique_recs.to_text(rec), "Which campus did you visit?")


if __name__ == "__main__":
    unittest.main()
