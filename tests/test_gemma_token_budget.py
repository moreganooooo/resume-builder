"""Gemma's 16k TPM cap is a PER-CALL ceiling, not just a pacing problem.

The cap counts input and output together, so a single request larger than
16k tokens can never succeed however long the caller waits -- pacing
spreads calls apart, it does not shrink one.

Measured on a real resume build (2026-09-29): the Step 3 rewrite path sent
a 15,985-char system prompt plus a 47,964-char static prefix, about 18,300
estimated tokens. Every call 429'd; the run logged no successful Gemma
response at all, just six ~75s pacing waits before handing off to
flash-lite -- roughly 7.5 minutes of guaranteed-fail waiting per bullet.
"""

import os
import sys
import tempfile
import unittest
from unittest.mock import patch

SCRIPTS_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts"
)
sys.path.insert(0, SCRIPTS_DIR)

import gemini_client as gc  # noqa: E402
import orchestrator as o  # noqa: E402
import rewrite_bullets as rb  # noqa: E402


class TestTokenEstimate(unittest.TestCase):
    def test_empty_text_is_zero(self):
        self.assertEqual(gc.estimate_tokens(""), 0)
        self.assertEqual(gc.estimate_tokens(None), 0)

    def test_estimate_errs_toward_too_big(self):
        """Under-estimating is the dangerous direction: it lets an
        oversized call through to a guaranteed 429. The divisor must stay
        below the ~4 chars/token English average."""
        self.assertLess(gc.CHARS_PER_TOKEN, 4.0)
        self.assertGreater(gc.estimate_tokens("x" * 4000), 1000)

    def test_budget_reserves_room_for_output(self):
        """Output counts against the same per-minute budget, so a prompt
        may not claim all of it."""
        self.assertEqual(gc.gemma_prompt_budget(2048), gc.GEMMA_TPM_LIMIT - 2048)
        self.assertEqual(
            gc.gemma_prompt_budget(None),
            gc.GEMMA_TPM_LIMIT - gc.GEMMA_DEFAULT_OUTPUT_RESERVE,
        )

    def test_budget_never_goes_negative(self):
        self.assertEqual(gc.gemma_prompt_budget(gc.GEMMA_TPM_LIMIT * 2), 0)


class TestGemmaRequestSizing(unittest.TestCase):
    def test_non_gemma_models_are_never_flagged(self):
        """Every other model here has a 250k TPM cap, which these prompts
        do not approach -- so the check must not touch them."""
        too_large, est, budget = gc.gemma_request_too_large(
            "gemini-3.5-flash-lite", "x" * 200_000, "y" * 200_000, 2048
        )
        self.assertFalse(too_large)
        self.assertEqual((est, budget), (0, 0))

    def test_the_real_rewrite_prompt_is_over_budget(self):
        """The exact sizes the 2026-09-29 run logged."""
        too_large, est, _ = gc.gemma_request_too_large(
            "gemma-4-31b-it", "x" * 15_985, "x" * 47_964, 2048
        )
        self.assertTrue(too_large)
        # Over the WHOLE per-minute cap, not merely over the prompt budget
        # -- which is why no pacing interval could have rescued it.
        self.assertGreater(est, gc.GEMMA_TPM_LIMIT)

    def test_a_small_gemma_prompt_still_passes(self):
        """Grounded company-research calls run on Gemma and are small; the
        guard must not disturb them."""
        too_large, _, _ = gc.gemma_request_too_large(
            "gemma-4-31b-it", "short system", "short contents", 2048
        )
        self.assertFalse(too_large)


class TestGeneratePreflight(unittest.TestCase):
    """The guard runs BEFORE the retry loop, so an impossible request costs
    no network round-trip and no 75s pacing wait."""

    def setUp(self):
        patcher = patch.object(gc, "_pace_gemma")
        self.mock_pace = patcher.start()
        self.addCleanup(patcher.stop)

    def _oversized(self):
        return "x" * 20_000, "x" * 50_000

    @patch("gemini_client.requests.post")
    def test_oversized_gemma_call_never_hits_the_network(self, mock_post):
        system, contents = self._oversized()
        text, usage = gc.GeminiClient.generate(
            model="gemma-4-31b-it",
            system_instruction=system,
            contents=contents,
            model_fallback=False,
        )
        self.assertIsNone(text)
        self.assertEqual(usage, {})
        mock_post.assert_not_called()

    @patch("gemini_client.requests.post")
    def test_oversized_gemma_call_never_pays_the_pacing_wait(self, mock_post):
        """~75s per attempt was the actual cost of this bug."""
        system, contents = self._oversized()
        gc.GeminiClient.generate(
            model="gemma-4-31b-it",
            system_instruction=system,
            contents=contents,
            model_fallback=False,
        )
        self.mock_pace.assert_not_called()

    # _get_auth_headers is patched rather than setting
    # RESUME_ALLOW_TEST_NETWORK for the module: this is the only test here
    # that reaches header construction, and a module-wide opt-in would let
    # any future test added without a requests.post mock make a real
    # billable call (see CLAUDE.md on test_gemini_client's setUpModule).
    @patch("gemini_client._get_auth_headers", return_value={"x-goog-api-key": "k"})
    @patch("gemini_client.requests.post")
    def test_oversized_gemma_call_swaps_when_a_fallback_exists(
        self, mock_post, _mock_headers
    ):
        """With model_fallback on, the call should go to the mapped model
        rather than failing -- the caller asked for an answer, not for
        Gemma specifically."""
        mock_post.side_effect = AssertionError("stop here")
        system, contents = self._oversized()
        with self.assertRaises(AssertionError):
            gc.GeminiClient.generate(
                model="gemma-4-31b-it",
                system_instruction=system,
                contents=contents,
                model_fallback=True,
            )
        url = mock_post.call_args[0][0]
        self.assertIn(gc.MODEL_FALLBACKS["gemma-4-31b-it"], url)
        self.assertNotIn("gemma-4-31b-it", url)

    @patch("gemini_client.requests.post")
    def test_grounded_oversized_call_returns_rather_than_leaving_its_family(
        self, mock_post
    ):
        """A grounded call may not swap out of its quota family, so it
        fails fast instead."""
        system, contents = self._oversized()
        text, _ = gc.GeminiClient.generate(
            model="gemma-4-31b-it",
            system_instruction=system,
            contents=contents,
            tools=[{"google_search": {}}],
        )
        self.assertIsNone(text)
        mock_post.assert_not_called()


if __name__ == "__main__":
    unittest.main()


class TestSharedToolRanking(unittest.TestCase):
    """rewrite_bullets.rank_tools_for_prompt is shared by EVERY tier that
    sends tools to a model, so the tiers cannot disagree about what
    matters. Size is only half the point: the tools section is the list a
    rewrite may NAME, so a tool the posting asks for and the candidate has
    must survive the cut, or the rewrite cannot surface the keyword an ATS
    and a recruiter screen on.
    """

    def _tools(self):
        return [
            {"name": "Kubernetes"},
            {"name": "Figma"},
            {"name": "Photoshop"},
            {"name": "Salesforce"},
            {"name": "Salesforce Marketing Cloud"},
        ]

    def _names(self, sel):
        return [t["name"] for t in sel]

    def test_priority_order(self):
        got = self._names(
            rb.rank_tools_for_prompt(
                self._tools(),
                jd_text="Salesforce and Photoshop required.",
                attested_names={"Salesforce", "Figma"},
            )
        )
        # 1: JD-matched AND attested. 2: JD-matched. 3: attested.
        # 4: JD-adjacent. 5: the rest.
        self.assertEqual(got[0], "Salesforce")
        self.assertEqual(got[1], "Photoshop")
        self.assertEqual(got[2], "Figma")
        self.assertEqual(got[3], "Salesforce Marketing Cloud")
        self.assertEqual(got[4], "Kubernetes")

    def test_jd_keyword_survives_when_no_evidence_backs_it(self):
        """The ATS half. Photoshop has no attestation, but the posting
        asks for it and the ledger verifies it -- an evidence-only filter
        dropped exactly these."""
        got = self._names(
            rb.rank_tools_for_prompt(
                self._tools(), jd_text="Photoshop wanted", max_rows=1
            )
        )
        self.assertEqual(got, ["Photoshop"])

    def test_every_token_must_match(self):
        """'Adobe Analytics' must not match a posting that only says
        'Adobe' -- a partial match would admit whole vendor catalogues."""
        tools = [{"name": "Adobe Analytics"}, {"name": "Photoshop"}]
        got = self._names(
            rb.rank_tools_for_prompt(tools, jd_text="Photoshop and Adobe experience")
        )
        self.assertEqual(got[0], "Photoshop")

    def test_generic_tokens_never_match(self):
        self.assertEqual(rb.tool_tokens("marketing strategy"), set())
        self.assertIn("salesforce", rb.tool_tokens("Salesforce CRM"))

    def test_trailing_sentence_punctuation_is_stripped(self):
        """'.' is in the token class for Node.js/ASP.NET, so a posting
        ending '...and Kubernetes.' yielded 'kubernetes.' and matched
        nothing."""
        self.assertIn("kubernetes", rb.tool_tokens("We use Kubernetes."))
        self.assertIn("node.js", rb.tool_tokens("Node.js"))

    def test_never_returns_empty_for_a_non_empty_ledger(self):
        """An empty tools section tells a model it may claim NO tools at
        all -- worse than an oversized one, which merely reroutes."""
        got = rb.rank_tools_for_prompt(self._tools(), jd_text="nothing relevant here")
        self.assertEqual(len(got), len(self._tools()))

    def test_char_and_row_budgets_are_honored(self):
        many = [{"name": f"Salesforce Widget {i}"} for i in range(3000)]
        capped = rb.rank_tools_for_prompt(many, jd_text="Salesforce", max_chars=5000)
        self.assertLessEqual(len(rb.compact_tools_text(capped)), 5000)
        self.assertGreater(len(capped), 0)
        self.assertEqual(
            len(rb.rank_tools_for_prompt(many, jd_text="Salesforce", max_rows=7)), 7
        )


class TestGemmaBudgetIsDerived(unittest.TestCase):
    """The tools ceiling is DERIVED from gemini_client's budget, not
    hardcoded. A fixed cap guessed against an imagined segment is exactly
    how this broke: a first pass assumed a ~2,000-char segment when the
    real one is ~15,000, and the assembled call came out over budget while
    every individual piece looked fine.
    """

    def test_budget_leaves_room_for_everything_else(self):
        cap = o.ResumeEngine.gemma_tools_budget_chars()
        total = (
            gc.estimate_tokens("x" * cap)
            + gc.estimate_tokens("x" * o.ResumeEngine.GEMMA_SYSTEM_PROMPT_RESERVE_CHARS)
            + gc.estimate_tokens("x" * o.ResumeEngine.GEMMA_SEGMENT_RESERVE_CHARS)
            + gc.estimate_tokens("x" * o.ResumeEngine.GEMMA_PREFIX_OTHER_RESERVE_CHARS)
        )
        budget = gc.gemma_prompt_budget(rb.REWRITE_MAX_OUTPUT_TOKENS)
        self.assertLessEqual(total, budget)
        # And the margin is real, not zero.
        self.assertGreaterEqual(budget - total, 1000)

    def test_budget_tracks_the_tpm_cap(self):
        """Halving the cap must shrink the tools allowance, not silently
        leave a stale constant in place."""
        wide = o.ResumeEngine.gemma_tools_budget_chars()
        with patch.object(gc, "GEMMA_TPM_LIMIT", gc.GEMMA_TPM_LIMIT // 2):
            narrow = o.ResumeEngine.gemma_tools_budget_chars()
        self.assertLess(narrow, wide)

    def test_budget_never_goes_negative(self):
        with patch.object(gc, "GEMMA_TPM_LIMIT", 100):
            self.assertGreaterEqual(o.ResumeEngine.gemma_tools_budget_chars(), 0)


class _FakeEngine:
    """Binds the real wrapper to a bare object, so the delegation can be
    tested without constructing a ResumeEngine against a real profile."""

    def __init__(self, attested=()):
        self._gemma_tools_cache = None
        self._attested_names_cache = set(attested)

    gemma_tools_budget_chars = o.ResumeEngine.gemma_tools_budget_chars
    _bank_attested_tool_names = o.ResumeEngine._bank_attested_tool_names
    subset = o.ResumeEngine._gemma_tool_subset


class TestGemmaGlobalToolTier(unittest.TestCase):
    """The GLOBAL slim prefix is deliberately not employer-scoped: it is
    the whole ledger narrowed to what this posting makes relevant, which
    is what carries ATS keyword coverage. Employer scoping happens in the
    per-bullet segment, where claiming another employer's tool would be
    cross-company contamination.
    """

    def _tools(self):
        return [
            {"name": "Kubernetes"},
            {"name": "Figma"},
            {"name": "Photoshop"},
            {"name": "Salesforce"},
        ]

    def test_delegates_and_ranks_jd_first(self):
        got = [
            t["name"]
            for t in _FakeEngine(attested={"Figma"}).subset(
                self._tools(), "Photoshop required"
            )
        ]
        self.assertEqual(got[0], "Photoshop")
        self.assertEqual(got[1], "Figma")

    def test_output_stays_inside_the_derived_budget(self):
        many = [{"name": f"Salesforce Widget {i}"} for i in range(3000)]
        got = _FakeEngine().subset(many, "Salesforce")
        self.assertLessEqual(
            len(rb.compact_tools_text(got)),
            o.ResumeEngine.gemma_tools_budget_chars(),
        )
        self.assertGreater(len(got), 0)

    def test_result_is_cached_per_jd(self):
        engine = _FakeEngine()
        first = engine.subset(self._tools(), "Salesforce")
        self.assertIs(first, engine.subset(self._tools(), "Salesforce"))
        # A different posting must re-select, not reuse the cache.
        self.assertIsNot(first, engine.subset(self._tools(), "Photoshop"))
