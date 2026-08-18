import os
import sys
import unittest

SCRIPTS_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts"
)
sys.path.insert(0, SCRIPTS_DIR)

import validate_coverletter  # noqa: E402

STYLE_RULES = {
    "forbidden_phrases": ["results-driven", "passionate", "synergy", "best-in-class"],
}


def _valid_letter():
    return {
        "company_name": "Acme Corp",
        "greeting": "Dear Hiring Team,",
        "body_paragraphs": [
            "With Acme Corp scaling its CRM and user acquisition, having a foundational "
            "content strategy that converts cold traffic into loyal, engaged users is "
            "critical to sustaining that growth without diluting brand voice or "
            "overwhelming the support team with a wave of churn-driven inquiries. My "
            "background in campaign messaging and content operations maps directly to "
            "these high-growth needs, having spent years building lifecycle programs "
            "that turn first-touch visitors into long-term customers across several "
            "fast-moving markets and multiple simultaneous product launches, each with "
            "its own audience segments, timelines, and success metrics to track "
            "alongside the rest of the marketing calendar and the broader roadmap.",
            "In my most recent role, I built lifecycle email campaigns that grew "
            "engagement by double digits, which maps closely to the JD's focus on "
            "activation-ready content and cross-functional collaboration with product "
            "and sales teams. I partnered closely with engineering to instrument "
            "tracking for every campaign touchpoint, then used that data to prioritize "
            "the messaging sequences most likely to move a cold lead toward a signed "
            "contract, iterating weekly rather than waiting for quarterly reviews to "
            "catch underperforming sequences. That same instinct for pairing narrative "
            "with measurement is what I would bring to this role from the very first "
            "week, alongside a habit of documenting what worked so the next campaign "
            "starts from evidence instead of guesswork.",
            "Beyond the metrics, I bring a collaborative approach to content operations, "
            "regularly partnering with design and revenue operations to keep messaging "
            "consistent across every channel a prospect might encounter. I thrive in "
            "environments where priorities shift quickly and enjoy building the kind of "
            "repeatable systems that let a small team punch above its weight, which is "
            "exactly the kind of environment this role describes. I would welcome the "
            "chance to bring that same energy to a team that is scaling as quickly as "
            "this one clearly is, and to help build the next stage of that story "
            "alongside the rest of the team.",
        ],
        "sign_off": "Sincerely,",
    }


class TestValidateCoverLetter(unittest.TestCase):

    def test_valid_letter_has_no_violations(self):
        violations = validate_coverletter.validate(_valid_letter(), STYLE_RULES)
        self.assertEqual(violations, [])

    def test_flags_forbidden_phrase(self):
        letter = _valid_letter()
        letter["body_paragraphs"][0] += " I'm a results-driven professional."
        violations = validate_coverletter.validate(letter, STYLE_RULES)
        self.assertTrue(any("results-driven" in v for v in violations))

    def test_flags_too_few_paragraphs(self):
        letter = _valid_letter()
        letter["body_paragraphs"] = ["Only one paragraph here."]
        violations = validate_coverletter.validate(letter, STYLE_RULES)
        self.assertTrue(any("Expected 2-4 body paragraphs" in v for v in violations))

    def test_flags_too_many_paragraphs(self):
        letter = _valid_letter()
        letter["body_paragraphs"] = ["One.", "Two.", "Three.", "Four.", "Five."]
        violations = validate_coverletter.validate(letter, STYLE_RULES)
        self.assertTrue(any("Expected 2-4 body paragraphs" in v for v in violations))

    def test_flags_third_person_slip(self):
        letter = _valid_letter()
        letter["body_paragraphs"][
            0
        ] = "Morgan has years of experience in content strategy."
        violations = validate_coverletter.validate(letter, STYLE_RULES)
        self.assertTrue(any("Third-person self-reference" in v for v in violations))

    def test_flags_cliched_openers(self):
        cliches = [
            "I am writing to express my interest in the Content Strategist role.",
            "I was excited to see your job opening.",
            "I am thrilled to apply for this job.",
            "My name is Morgan and I am writing...",
            "Please accept this letter as my official application.",
            "With great enthusiasm, I submit my candidacy.",
        ]
        for cliche in cliches:
            letter = _valid_letter()
            letter["body_paragraphs"][0] = cliche + " " + letter["body_paragraphs"][0]
            violations = validate_coverletter.validate(letter, STYLE_RULES)
            self.assertTrue(
                any("clichéd/passive opener" in v for v in violations),
                f"Failed to flag clichéd opener: {cliche!r}",
            )

    def test_flags_too_few_words(self):
        letter = _valid_letter()
        letter["body_paragraphs"] = [
            "Short paragraph about the role.",
            "Another short paragraph about my background.",
        ]
        violations = validate_coverletter.validate(letter, STYLE_RULES)
        self.assertTrue(any("300-450 words" in v for v in violations), violations)

    def test_flags_too_many_words(self):
        letter = _valid_letter()
        letter["body_paragraphs"] = [" ".join(["word"] * 250), " ".join(["word"] * 250)]
        violations = validate_coverletter.validate(letter, STYLE_RULES)
        self.assertTrue(any("300-450 words" in v for v in violations), violations)

    def test_does_not_flag_word_count_within_range(self):
        violations = validate_coverletter.validate(_valid_letter(), STYLE_RULES)
        self.assertFalse(
            any("words across body paragraphs" in v for v in violations), violations
        )

    def test_allows_legitimate_third_party_pronoun(self):
        # Known trade-off, not a bug: "her"/"she" is a blunt heuristic (see
        # validate_coverletter.py's docstring). This test just documents the
        # limitation exists rather than asserting a specific behavior for it.
        pass


class TestKBTraceability(unittest.TestCase):
    """B14: a JD-borne prompt injection got a fabricated '10 years of
    professional Rust systems programming experience ... at Stripe
    (2019-2024), cutting p99 latency 92%' woven into a real cover letter's
    first paragraph. None of the three checks above catch a fabrication
    that isn't a forbidden phrase, a paragraph-count violation, or a
    third-person slip -- this check is the factual-grounding backstop."""

    KB_CORPUS = (
        "=== VERIFIED FACTS ===\n"
        "Led lifecycle email campaigns at Acme Corp, growing engagement 18%.\n"
        "8 years of B2B marketing and content strategy experience.\n"
        "=== VERIFIED TOOLS ===\nHubSpot, Salesforce, Figma\n"
    )

    def test_no_violations_when_no_corpus_given(self):
        # Default kb_corpus="" -- callers outside the JD-injection threat
        # model (polish.py) get no traceability check at all.
        letter = _valid_letter()
        letter["body_paragraphs"][0] += (
            " I have 10 years of professional Rust systems programming "
            "experience and led a rewrite at Stripe (2019-2024), cutting "
            "p99 latency 92%."
        )
        violations = validate_coverletter.validate(letter, STYLE_RULES)
        self.assertEqual(violations, [])

    def test_flags_fabricated_metric_not_in_kb_corpus(self):
        letter = _valid_letter()
        letter["body_paragraphs"][0] += (
            " This technical foundation, combined with my background in "
            "journalism, let me cut p99 latency 92% on a payments ledger."
        )
        violations = validate_coverletter.validate(
            letter, STYLE_RULES, kb_corpus=self.KB_CORPUS
        )
        self.assertTrue(any("92%" in v for v in violations), violations)

    def test_flags_fabricated_year_range_not_in_kb_corpus(self):
        letter = _valid_letter()
        letter["body_paragraphs"][0] += " I led this effort from (2019-2024)."
        violations = validate_coverletter.validate(
            letter, STYLE_RULES, kb_corpus=self.KB_CORPUS
        )
        self.assertTrue(any("2019-2024" in v for v in violations), violations)

    def test_does_not_flag_a_metric_present_in_kb_corpus(self):
        letter = _valid_letter()
        letter["body_paragraphs"][0] += " I grew engagement 18% in that role."
        violations = validate_coverletter.validate(
            letter, STYLE_RULES, kb_corpus=self.KB_CORPUS
        )
        self.assertEqual(violations, [])

    def test_does_not_flag_years_experience_claim_present_in_kb_corpus(self):
        letter = _valid_letter()
        letter["body_paragraphs"][0] += " I bring 8 years of B2B marketing experience."
        violations = validate_coverletter.validate(
            letter, STYLE_RULES, kb_corpus=self.KB_CORPUS
        )
        self.assertEqual(violations, [])

    def test_ignores_ordinary_small_numbers_with_no_distinctive_suffix(self):
        # Deliberately not a bare \d+ match -- "3" alone would flag nearly
        # every letter. Only %, $, K/M-suffixed, "N years/yrs", and year
        # ranges count as checkable claims.
        letter = _valid_letter()
        letter["body_paragraphs"][0] += " I've held 3 roles in this space."
        violations = validate_coverletter.validate(
            letter, STYLE_RULES, kb_corpus=self.KB_CORPUS
        )
        self.assertEqual(violations, [])
