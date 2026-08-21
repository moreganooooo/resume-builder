"""Tests for scripts/websearch_ddg.py and the sweep loop's backend choice.

Network is always mocked. The behavior that matters most here is that a
failing search backend costs one sweep its results rather than aborting
the whole scan.
"""

import os
import sys
import unittest
from unittest.mock import MagicMock, patch

sys.path.insert(
    0,
    os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts"
    ),
)

import websearch_ddg  # noqa: E402

ROWS = [
    {
        "href": "https://boards.greenhouse.io/acme/jobs/1",
        "title": "Lifecycle Marketing Manager",
        "body": "Own the email program.",
    },
    {"href": "", "title": "No URL", "body": "dropped"},
    {"href": "https://x.com/2", "title": "", "body": "dropped"},
]


def fake_ddgs(rows):
    """Stands in for the ddgs module, whose DDGS().text() yields rows."""
    instance = MagicMock()
    instance.text.return_value = iter(rows)
    module = MagicMock()
    module.DDGS.return_value = instance
    return module


class TestSearch(unittest.TestCase):
    """Opts out of the no-network guard PER TEST.

    Set at module import this leaked into every other test module in the
    same process and sent their sweep loops at the real backend.
    """

    def setUp(self):
        patcher = patch.dict(
            os.environ, {websearch_ddg._TEST_NETWORK_ENV: "1"}, clear=False
        )
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_maps_ddgs_fields_to_the_brave_shape(self):
        # websearch.mjs reads `description`; ddgs calls it `body`.
        with patch.dict("sys.modules", {"ddgs": fake_ddgs(ROWS)}):
            results = websearch_ddg.search("marketing")
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["url"], "https://boards.greenhouse.io/acme/jobs/1")
        self.assertEqual(results[0]["title"], "Lifecycle Marketing Manager")
        self.assertEqual(results[0]["description"], "Own the email program.")

    def test_rows_missing_a_url_or_title_are_dropped(self):
        with patch.dict("sys.modules", {"ddgs": fake_ddgs(ROWS)}):
            self.assertEqual(len(websearch_ddg.search("marketing")), 1)

    def test_empty_query_short_circuits(self):
        self.assertEqual(websearch_ddg.search(""), [])
        self.assertEqual(websearch_ddg.search("   "), [])

    def test_backend_failure_returns_empty_not_raise(self):
        # A rate-limited or offline backend must cost this sweep its
        # results, never abort the scan run around it.
        module = MagicMock()
        module.DDGS.return_value.text.side_effect = RuntimeError("rate limited")
        with patch.dict("sys.modules", {"ddgs": module}):
            self.assertEqual(websearch_ddg.search("marketing"), [])

    def test_missing_library_returns_empty(self):
        with patch.dict("sys.modules", {"ddgs": None}):
            self.assertEqual(websearch_ddg.search("marketing"), [])


class TestSweepBackendChoice(unittest.TestCase):
    """Brave when a key exists, DuckDuckGo otherwise."""

    def setUp(self):
        import scan_ats

        self.scan_ats = scan_ats

    def _run(self, env, ddg_results):
        with (
            patch.dict(os.environ, env, clear=False),
            patch.object(self.scan_ats, "_load_tracked_companies", return_value=[]),
            patch.object(
                self.scan_ats,
                "_load_search_queries",
                return_value=[{"name": "sweep", "query": "marketing", "enabled": True}],
            ),
            patch.object(
                self.scan_ats.websearch_ddg, "search", return_value=ddg_results
            ) as ddg,
            patch.object(
                self.scan_ats.scan_boards, "_run_node_provider", return_value=[]
            ) as node,
        ):
            self.scan_ats.fetch_ats_jobs()
        return ddg, node

    def test_without_brave_key_results_are_supplied_to_node(self):
        results = [{"url": "https://x.com/1", "title": "T", "description": "d"}]
        env = dict(os.environ)
        env.pop("BRAVE_API_KEY", None)
        with patch.dict(os.environ, env, clear=True):
            ddg, node = self._run({}, results)
        ddg.assert_called_once()
        entry = node.call_args[0][1]
        self.assertEqual(entry["_results"], results)

    def test_with_brave_key_the_ddg_backend_is_not_used(self):
        ddg, node = self._run({"BRAVE_API_KEY": "key"}, [])
        ddg.assert_not_called()
        self.assertNotIn("_results", node.call_args[0][1])

    def test_empty_results_still_reach_node(self):
        # Skipping the call would also skip this loop's pacing and error
        # reporting; websearch.mjs maps an empty list to an empty result.
        env = dict(os.environ)
        env.pop("BRAVE_API_KEY", None)
        with patch.dict(os.environ, env, clear=True):
            _, node = self._run({}, [])
        node.assert_called_once()
        self.assertEqual(node.call_args[0][1]["_results"], [])


if __name__ == "__main__":
    unittest.main()
