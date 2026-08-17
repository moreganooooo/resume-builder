import os
import sys
import unittest
from unittest.mock import patch

SCRIPTS_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts")
sys.path.insert(0, SCRIPTS_DIR)

import bootstrap_timeline  # noqa: E402
from bootstrap_extractors import RawAchievement, WorkExperienceEntry  # noqa: E402


class TestBuildTimelineNoConflict(unittest.TestCase):

    def test_linkedin_only(self):
        entries = bootstrap_timeline.build_timeline({
            "linkedin_export": [
                WorkExperienceEntry(company="Acme Corp", title="Manager", start_date="2019", end_date="2022"),
            ],
        })
        self.assertEqual(len(entries), 1)
        self.assertEqual(entries[0].company, "Acme Corp")
        self.assertFalse(entries[0].needs_review)

    def test_resume_and_linkedin_agree(self):
        entries = bootstrap_timeline.build_timeline({
            "linkedin_export": [
                WorkExperienceEntry(company="Acme Corp", title="Manager", start_date="2019", end_date="2022"),
            ],
            "resume": [
                WorkExperienceEntry(company="Acme Corp", title="Manager", start_date="2019", end_date="2022"),
            ],
        })
        self.assertEqual(len(entries), 1)
        self.assertFalse(entries[0].needs_review)

    def test_resume_only_company_included(self):
        entries = bootstrap_timeline.build_timeline({
            "resume": [
                WorkExperienceEntry(company="Beta Inc", title="Analyst", start_date="2015", end_date="2018"),
            ],
        })
        self.assertEqual(len(entries), 1)
        self.assertEqual(entries[0].company, "Beta Inc")

    def test_minor_date_overlap_not_flagged(self):
        entries = bootstrap_timeline.build_timeline({
            "linkedin_export": [
                WorkExperienceEntry(company="Acme Corp", title="Manager", start_date="2019", end_date="2022"),
            ],
            "resume": [
                WorkExperienceEntry(company="Acme Corp", title="Manager", start_date="2020", end_date="2022"),
            ],
        })
        self.assertEqual(len(entries), 1)
        self.assertFalse(entries[0].needs_review)
        self.assertEqual(entries[0].start_date, "2019")


class TestBuildTimelineConflict(unittest.TestCase):

    def test_non_overlapping_ranges_flagged_for_review(self):
        entries = bootstrap_timeline.build_timeline({
            "linkedin_export": [
                WorkExperienceEntry(company="Acme Corp", title="Manager", start_date="2019", end_date="2020"),
            ],
            "resume": [
                WorkExperienceEntry(company="Acme Corp", title="Manager", start_date="2022", end_date="2023"),
            ],
        })
        self.assertEqual(len(entries), 1)
        self.assertTrue(entries[0].needs_review)
        self.assertIsNotNone(entries[0].conflict_note)


class TestMatchToTimeline(unittest.TestCase):

    def setUp(self):
        self.timeline = [
            bootstrap_timeline.TimelineEntry(company="Acme Corp", title="Sales Manager", start_date="2019", end_date="2022"),
            bootstrap_timeline.TimelineEntry(company="Beta Inc", title="Analyst", start_date="2015", end_date="2018"),
        ]

    def test_matches_by_company_hint(self):
        achievement = RawAchievement(raw_text="Did a thing", company_hint="Acme Corp", date_hint=None, title_hint=None, confidence="high")
        company, confidence = bootstrap_timeline.match_to_timeline(achievement, self.timeline)
        self.assertEqual(company, "Acme Corp")
        self.assertEqual(confidence, "high")

    def test_matches_by_date_hint_when_unambiguous(self):
        achievement = RawAchievement(raw_text="Did a thing", company_hint=None, date_hint="2016", title_hint=None, confidence="medium")
        company, confidence = bootstrap_timeline.match_to_timeline(achievement, self.timeline)
        self.assertEqual(company, "Beta Inc")
        self.assertEqual(confidence, "medium")

    def test_matches_by_title_hint(self):
        achievement = RawAchievement(raw_text="Did a thing", company_hint=None, date_hint=None, title_hint="Sales Manager", confidence="medium")
        company, confidence = bootstrap_timeline.match_to_timeline(achievement, self.timeline)
        self.assertEqual(company, "Acme Corp")

    @patch("bootstrap_timeline._llm_match", return_value=None)
    def test_falls_back_to_misc_when_nothing_matches(self, mock_llm_match):
        achievement = RawAchievement(raw_text="did outbound sales work somewhere", company_hint=None, date_hint=None, title_hint=None, confidence="low")
        company, confidence = bootstrap_timeline.match_to_timeline(achievement, self.timeline)
        self.assertEqual(company, "Misc. / Unassigned")
        self.assertEqual(confidence, "low")

    @patch("bootstrap_timeline._llm_match", return_value="Acme Corp")
    def test_llm_fallback_used_when_hints_dont_match(self, mock_llm_match):
        achievement = RawAchievement(raw_text="while doing outbound sales", company_hint=None, date_hint=None, title_hint=None, confidence="low")
        company, confidence = bootstrap_timeline.match_to_timeline(achievement, self.timeline)
        self.assertEqual(company, "Acme Corp")
        self.assertEqual(confidence, "medium")

    def test_dry_run_skips_llm_fallback(self):
        achievement = RawAchievement(raw_text="ambiguous text", company_hint=None, date_hint=None, title_hint=None, confidence="low")
        with patch("bootstrap_timeline._llm_match") as mock_llm_match:
            company, confidence = bootstrap_timeline.match_to_timeline(achievement, self.timeline, dry_run=True)
            mock_llm_match.assert_not_called()
            self.assertEqual(company, "Misc. / Unassigned")


class TestLlmMatch(unittest.TestCase):
    # _llm_match() used to trust the model's matched_company string as-is;
    # since it's free text (not constrained to the options it was given),
    # a hallucinated or reworded company name would flow straight through
    # match_to_timeline() as a confident "medium" match. These lock in the
    # validation-against-the-real-timeline fix.

    def setUp(self):
        self.timeline = [
            bootstrap_timeline.TimelineEntry(company="Acme Corp", title="Sales Manager", start_date="2019", end_date="2022"),
        ]

    @patch("bootstrap_timeline.GeminiClient.generate")
    @patch("bootstrap_timeline.GeminiClient.parse_json")
    def test_exact_match_returns_canonical_company(self, mock_parse, mock_generate):
        mock_generate.return_value = ("{}", {})
        mock_parse.return_value = {"matched_company": "Acme Corp"}
        self.assertEqual(bootstrap_timeline._llm_match("did a thing", self.timeline), "Acme Corp")

    @patch("bootstrap_timeline.GeminiClient.generate")
    @patch("bootstrap_timeline.GeminiClient.parse_json")
    def test_fuzzy_spelling_still_resolves_to_canonical_company(self, mock_parse, mock_generate):
        # Same normalization used elsewhere in this file (case/punctuation-
        # insensitive) -- a reworded but real match should still count.
        mock_generate.return_value = ("{}", {})
        mock_parse.return_value = {"matched_company": "acme corp."}
        self.assertEqual(bootstrap_timeline._llm_match("did a thing", self.timeline), "Acme Corp")

    @patch("bootstrap_timeline.GeminiClient.generate")
    @patch("bootstrap_timeline.GeminiClient.parse_json")
    def test_hallucinated_company_not_in_timeline_is_rejected(self, mock_parse, mock_generate):
        mock_generate.return_value = ("{}", {})
        mock_parse.return_value = {"matched_company": "Some Other Company That Was Never Offered"}
        self.assertIsNone(bootstrap_timeline._llm_match("did a thing", self.timeline))

    @patch("bootstrap_timeline.GeminiClient.generate")
    @patch("bootstrap_timeline.GeminiClient.parse_json")
    def test_null_match_returns_none(self, mock_parse, mock_generate):
        mock_generate.return_value = ("{}", {})
        mock_parse.return_value = {"matched_company": None}
        self.assertIsNone(bootstrap_timeline._llm_match("did a thing", self.timeline))


if __name__ == "__main__":
    unittest.main()
