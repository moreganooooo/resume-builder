"""Tests for scripts/discover_local_employers.py.

The subject here is FALSE POSITIVES. The first live run of this script
tracked five employers that did not own the boards it matched them to,
and every one came from a loose slug guess. Attributing a national
company's postings to a local employer is worse than finding nothing, so
most of these assert on what must be REJECTED.

Network is always mocked.
"""

import os
import sys
import tempfile
import unittest
from unittest.mock import MagicMock, patch

sys.path.insert(
    0,
    os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts"
    ),
)

import discover_local_employers as dle  # noqa: E402


class TestSlugCandidates(unittest.TestCase):
    def test_drops_legal_suffixes(self):
        self.assertEqual(dle.slug_candidates("The Hearst Corporation"), ["hearst"])

    def test_compact_and_hyphenated(self):
        self.assertEqual(
            dle.slug_candidates("Rich Products"), ["richproducts", "rich-products"]
        )

    def test_never_guesses_the_first_word_alone(self):
        # This is the bug that produced five wrong matches: "stellar"
        # belongs to some other company entirely.
        for name in ("STELLAR ROOFING", "Evolution Dental Science", "The Barnes Firm"):
            with self.subTest(name=name):
                self.assertNotIn("stellar", dle.slug_candidates(name))
                self.assertNotIn("evolution", dle.slug_candidates(name))
                self.assertNotIn("barnes", dle.slug_candidates(name))

    def test_too_short_is_skipped(self):
        self.assertEqual(dle.slug_candidates("Co"), [])


class TestOwnerMatching(unittest.TestCase):
    def test_exact_match(self):
        self.assertTrue(dle.owner_matches("Duolingo", "Duolingo"))

    def test_filler_words_ignored(self):
        self.assertTrue(dle.owner_matches("The Hearst Corporation", "Hearst"))

    def test_single_shared_word_is_not_a_match(self):
        # The real failure: a SmartRecruiters board named "Evolution"
        # answering for "Evolution Dental Science".
        self.assertFalse(dle.owner_matches("Evolution Dental Science", "Evolution"))
        self.assertFalse(dle.owner_matches("STELLAR ROOFING", "Stellar"))

    def test_multiword_prefix_is_a_match(self):
        self.assertTrue(dle.owner_matches("Rich Products Corporation", "Rich Products"))

    def test_empty_is_never_a_match(self):
        self.assertFalse(dle.owner_matches("Acme", ""))
        self.assertFalse(dle.owner_matches("", "Acme"))


class TestPostingCounts(unittest.TestCase):
    def test_smartrecruiters_zero_is_not_a_board(self):
        # SmartRecruiters answers 200 with totalFound 0 for slugs that do
        # not exist, so a status check alone claims every employer.
        self.assertEqual(dle._count_postings("smartrecruiters", {"totalFound": 0}), 0)

    def test_each_provider_shape(self):
        self.assertEqual(dle._count_postings("greenhouse", {"jobs": [1, 2]}), 2)
        self.assertEqual(dle._count_postings("lever", [1, 2, 3]), 3)
        self.assertEqual(dle._count_postings("ashby", {"jobs": [1]}), 1)
        self.assertEqual(dle._count_postings("recruitee", {"offers": [1, 2]}), 2)
        self.assertEqual(dle._count_postings("smartrecruiters", {"totalFound": 7}), 7)

    def test_unexpected_shapes_are_zero(self):
        self.assertEqual(dle._count_postings("greenhouse", None), 0)
        self.assertEqual(dle._count_postings("greenhouse", "nonsense"), 0)


class TestEmployerFiltering(unittest.TestCase):
    def test_staffing_agencies_rejected(self):
        for name in (
            "Acme Staffing",
            "TalentBridge",
            "Confidential",
            "Robert Recruiters",
        ):
            with self.subTest(name=name):
                self.assertFalse(dle.looks_like_employer(name))

    def test_real_employers_kept(self):
        for name in ("Rich Products", "M&T Bank", "Moog"):
            with self.subTest(name=name):
                self.assertTrue(dle.looks_like_employer(name))


class TestFindAtsBoard(unittest.TestCase):
    def _response(self, status=200, payload=None):
        response = MagicMock()
        response.status_code = status
        response.json.return_value = payload if payload is not None else {}
        return response

    def test_rejects_a_board_owned_by_someone_else(self):
        hit = self._response(
            200, {"content": [{"company": {"name": "Evolution"}}], "totalFound": 304}
        )
        with patch.object(dle.requests, "get", return_value=hit):
            self.assertIsNone(dle.find_ats_board("Evolution Dental Science"))

    def test_accepts_a_board_whose_owner_matches(self):
        def fake_get(url, **_):
            if "/boards/hearst/jobs" in url:
                return self._response(200, {"jobs": [{}, {}]})
            if url.endswith("/boards/hearst"):
                return self._response(200, {"name": "Hearst"})
            return self._response(404)

        with patch.object(dle.requests, "get", side_effect=fake_get):
            hit = dle.find_ats_board("The Hearst Corporation")
        self.assertIsNotNone(hit)
        self.assertEqual(hit["provider"], "greenhouse")
        self.assertEqual(hit["owner"], "Hearst")

    def test_accepts_when_the_provider_discloses_no_owner(self):
        # Ashby exposes no company name, so the strict slug is the only
        # evidence there is.
        def fake_get(url, **_):
            if "ashbyhq.com" in url:
                return self._response(200, {"jobs": [{}]})
            return self._response(404)

        with patch.object(dle.requests, "get", side_effect=fake_get):
            hit = dle.find_ats_board("Rich Products")
        self.assertIsNotNone(hit)
        self.assertEqual(hit["provider"], "ashby")

    def test_no_board_returns_none(self):
        with patch.object(dle.requests, "get", return_value=self._response(404)):
            self.assertIsNone(dle.find_ats_board("Nowhere Corp"))


class TestAppendEntries(unittest.TestCase):
    SAMPLE = """# Vendored from career-ops -- load-bearing comment.

tracked_companies:
- name: Duolingo
  careers_url: https://boards.greenhouse.io/duolingo
  api: https://boards-api.greenhouse.io/v1/boards/duolingo/jobs
  enabled: true
"""

    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.dir.cleanup)
        self.path = os.path.join(self.dir.name, "tracked_companies.yml")
        with open(self.path, "w", encoding="utf-8") as handle:
            handle.write(self.SAMPLE)

    def test_appends_and_preserves_comments(self):
        import yaml

        hits = [
            {
                "name": "Hearst",
                "careers_url": "https://boards.greenhouse.io/hearst",
                "api": "https://boards-api.greenhouse.io/v1/boards/hearst/jobs",
                "provider": "greenhouse",
                "postings": 18,
            }
        ]
        dle.append_entries(hits, self.path)
        with open(self.path, "r", encoding="utf-8") as handle:
            body = handle.read()
        self.assertIn("load-bearing comment", body)
        data = yaml.safe_load(body)
        names = [e["name"] for e in data["tracked_companies"]]
        self.assertEqual(names, ["Duolingo", "Hearst"])

    def test_backs_up_before_writing(self):
        backup = dle.append_entries(
            [
                {
                    "name": "Hearst",
                    "careers_url": "u",
                    "api": "a",
                    "provider": "greenhouse",
                    "postings": 1,
                }
            ],
            self.path,
        )
        self.assertTrue(os.path.exists(backup))
        with open(backup, "r", encoding="utf-8") as handle:
            self.assertEqual(handle.read(), self.SAMPLE)

    def test_existing_names_are_detected(self):
        keys = dle.existing_company_keys(self.path)
        self.assertIn("duolingo", keys)


if __name__ == "__main__":
    unittest.main()
