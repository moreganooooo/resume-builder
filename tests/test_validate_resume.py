import os
import sys
import unittest

SCRIPTS_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts")
sys.path.insert(0, SCRIPTS_DIR)

import validate_resume  # noqa: E402

STYLE_RULES = {
    "forbidden_phrases": ["results-driven", "passionate", "synergy", "best-in-class"],
    "forbidden_openers": ["responsible for", "helped with", "worked on", "assisted with", "participated in"],
    "bullet_structure": {"one_liner_max_chars": 120, "two_liner_max_chars": 220, "max_printed_lines": 2},
    "skills_section": {"line_max_chars": 110},
}


def _valid_resume():
    return {
        "SUMMARY_TEXT": "<strong>Lifecycle marketer with 8 years in CRM strategy.</strong> Returning to full-time work after a caregiving pause.",
        "SKILLS": ["**Lifecycle & Retention Marketing:** Email Automation, Segmentation, Drip Campaigns"],
        "EXPERIENCE": [
            {"title": "Lifecycle Marketing Manager", "company": "Treering", "period": "08/2016 – 08/2024", "achievements": [
                "Recovered 3M in dormant pipeline through CRM audits and reactivation workflows",
                "Architected the SDR onboarding program used company-wide for three years",
            ]},
        ],
        "WHY_TEXT": "",
    }


class TestValidateResume(unittest.TestCase):

    def test_valid_resume_has_no_violations(self):
        violations = validate_resume.validate(_valid_resume(), STYLE_RULES)
        self.assertEqual(violations, [])

    def test_flags_tagline_that_would_wrap_to_a_2nd_line(self):
        resume = _valid_resume()
        # A real 65-char tagline that wrapped to a 2nd line despite fitting
        # the previous (wrong) "70-80 char" guidance.
        resume["TAGLINE"] = "CAMPAIGN CRM STRATEGIST | CAMPAIGN STRATEGY & LIFECYCLE MARKETING"
        violations = validate_resume.validate(resume, STYLE_RULES)
        self.assertTrue(any("tagline" in v.lower() for v in violations))

    def test_allows_condensed_tagline_that_fits(self):
        resume = _valid_resume()
        resume["TAGLINE"] = "CAMPAIGN & CRM STRATEGIST | LIFECYCLE MARKETING"
        violations = validate_resume.validate(resume, STYLE_RULES)
        self.assertFalse(any("tagline" in v.lower() for v in violations))

    def test_flags_empty_experience_entries(self):
        resume = _valid_resume()
        resume["EXPERIENCE"] = [{}, {}, {}]
        violations = validate_resume.validate(resume, STYLE_RULES)
        self.assertEqual(len(violations), 6)  # 3 missing-fields + 3 no-achievements, one pair per empty entry

    def test_flags_experience_entry_missing_achievements_only(self):
        resume = _valid_resume()
        resume["EXPERIENCE"] = [{"title": "Content Strategist", "company": "Acme", "period": "01/2020 – 01/2022", "achievements": []}]
        violations = validate_resume.validate(resume, STYLE_RULES)
        self.assertEqual(len(violations), 1)
        self.assertIn("no achievement bullets", violations[0])

    def test_flags_forbidden_phrase_in_summary(self):
        resume = _valid_resume()
        resume["SUMMARY_TEXT"] = "<strong>A results-driven lifecycle marketer.</strong>"
        violations = validate_resume.validate(resume, STYLE_RULES)
        self.assertTrue(any("results-driven" in v for v in violations))

    def test_forbidden_phrase_matches_whole_word_not_a_substring(self):
        # A plain substring check made "leverage" flag "leveraged"/"leveraging"
        # too, even though those inflected forms are a separate, softer
        # (non-blocking) vague_verbs concern -- not this hard gate's job.
        style_rules = {**STYLE_RULES, "forbidden_phrases": ["leverage"]}
        resume = _valid_resume()
        resume["EXPERIENCE"][0]["achievements"].append(
            "Leveraged Claude to draft and iterate on high-conversion email copy"
        )
        violations = validate_resume.validate(resume, style_rules)
        self.assertFalse(any("leverage" in v.lower() for v in violations),
                          "must not flag 'leveraged' via the 'leverage' forbidden phrase")

        resume["EXPERIENCE"][0]["achievements"][-1] = "Built a plan to leverage AI tools org-wide"
        violations = validate_resume.validate(resume, style_rules)
        self.assertTrue(any("leverage" in v.lower() for v in violations),
                         "must still flag the exact word 'leverage' itself")

    def test_flags_forbidden_opener_in_bullet(self):
        resume = _valid_resume()
        resume["EXPERIENCE"][0]["achievements"].append("Responsible for CRM data hygiene")
        violations = validate_resume.validate(resume, STYLE_RULES)
        self.assertTrue(any("forbidden opener" in v.lower() for v in violations))

    def test_flags_duplicate_opening_verb_across_bullets(self):
        resume = _valid_resume()
        resume["EXPERIENCE"][0]["achievements"] = [
            "Architected the SDR onboarding program used company-wide for three years",
            "Architected the CRM data model powering territory reporting",
        ]
        violations = validate_resume.validate(resume, STYLE_RULES)
        self.assertTrue(any("architected" in v.lower() and "unique" in v.lower() for v in violations))

    def test_flags_bullet_exceeding_two_liner_max_chars(self):
        resume = _valid_resume()
        resume["EXPERIENCE"][0]["achievements"].append("X" * 221)
        violations = validate_resume.validate(resume, STYLE_RULES)
        self.assertTrue(any("exceeds" in v.lower() and "220" in v for v in violations))

    def test_flags_skills_line_exceeding_max_chars(self):
        resume = _valid_resume()
        resume["SKILLS"] = ["**Category:** " + ", ".join(["Item"] * 40)]
        violations = validate_resume.validate(resume, STYLE_RULES)
        self.assertTrue(any("110" in v for v in violations))

    def test_allows_skills_line_that_wraps_cleanly_to_a_full_second_line(self):
        # Wrapping onto a second line is normal, unremarkable text wrapping --
        # only a short widow (or a 3rd-line-length overflow) is a defect.
        resume = _valid_resume()
        resume["SKILLS"] = ["**Cat:** " + "X" * 155]  # plain length 160, remainder 50 -- a full 2nd line
        violations = validate_resume.validate(resume, STYLE_RULES)
        self.assertFalse(any("skills line" in v.lower() for v in violations))

    def test_flags_skills_line_that_leaves_a_short_widow(self):
        resume = _valid_resume()
        resume["SKILLS"] = ["**Cat:** " + "X" * 110]  # plain length 115, remainder 5 -- a stray scrap
        violations = validate_resume.validate(resume, STYLE_RULES)
        self.assertTrue(any("widow" in v.lower() for v in violations))

    def test_flags_pronoun_outside_why_section(self):
        resume = _valid_resume()
        resume["SUMMARY_TEXT"] = "<strong>I am a lifecycle marketer.</strong>"
        violations = validate_resume.validate(resume, STYLE_RULES)
        self.assertTrue(any("pronoun" in v.lower() for v in violations))

    def test_flags_third_person_pronoun_in_summary(self):
        # The Summary should read as positioning, not third-person biography --
        # "She specializes in..." is as much a violation as "I specialize in...".
        resume = _valid_resume()
        resume["SUMMARY_TEXT"] = "<strong>Morgan is a lifecycle marketer.</strong> She leads CRM strategy."
        violations = validate_resume.validate(resume, STYLE_RULES)
        self.assertTrue(any("pronoun" in v.lower() for v in violations))

    def test_allows_pronoun_inside_why_section(self):
        resume = _valid_resume()
        resume["WHY_TEXT"] = "<p><em>I built the SDR Process Map at Treering for exactly this reason.</em></p>"
        violations = validate_resume.validate(resume, STYLE_RULES)
        self.assertEqual(violations, [])

    def test_flags_duplicate_metric_across_summary_and_bullets(self):
        resume = _valid_resume()
        resume["SUMMARY_TEXT"] = "<strong>Recovered 3M in dormant pipeline as a lifecycle marketer.</strong>"
        # _valid_resume() already has "Recovered 3M" in a bullet -- now it's in both places.
        violations = validate_resume.validate(resume, STYLE_RULES)
        self.assertTrue(any("3m" in v.lower() and ("once" in v.lower() or "duplicate" in v.lower()) for v in violations))

    def test_does_not_flag_k12_as_a_duplicate_of_an_unrelated_12(self):
        resume = _valid_resume()
        resume["EXPERIENCE"][0]["achievements"] = [
            "Authored niche email sequences for K-12 segments in Outreach.io, achieving a 95% open rate",
            "Promoted to sole manager of a 12-member team within six months",
        ]
        violations = validate_resume.validate(resume, STYLE_RULES)
        self.assertFalse(any("metric" in v.lower() for v in violations))

    def test_does_not_flag_k12_with_en_dash_either(self):
        resume = _valid_resume()
        resume["EXPERIENCE"][0]["achievements"] = [
            "Mapped reference personas across the K–12 buying unit to accelerate first calls",
            "Promoted to sole manager of a 12-member team within six months",
        ]
        violations = validate_resume.validate(resume, STYLE_RULES)
        self.assertFalse(any("metric" in v.lower() for v in violations))

    def test_does_not_flag_same_number_in_different_contexts(self):
        resume = _valid_resume()
        resume["EXPERIENCE"][0]["achievements"] = [
            "Recovered 3M in dormant pipeline through CRM audits and reactivation workflows",
            "Ranked as a Top 10 Performer for two consecutive months",
        ]
        resume["SUMMARY_TEXT"] = "<strong>Lifecycle marketer with 10+ years of experience.</strong>"
        violations = validate_resume.validate(resume, STYLE_RULES)
        self.assertFalse(any("metric '10'" in v.lower() for v in violations))

    def test_still_flags_same_number_and_context_repeated(self):
        resume = _valid_resume()
        resume["EXPERIENCE"][0]["achievements"] = [
            "Managed a 12-member cross-functional team across three regions",
            "Onboarded a 12-member team within the first quarter",
        ]
        violations = validate_resume.validate(resume, STYLE_RULES)
        self.assertTrue(any("12" in v and "metric" in v.lower() for v in violations))

    def test_does_not_flag_numeral_led_bullets_as_duplicate_opening_verbs(self):
        resume = _valid_resume()
        resume["EXPERIENCE"][0]["achievements"] = [
            "3M in pipeline recovered through targeted reactivation campaigns",
            "3 new territories launched under the revised go-to-market plan",
        ]
        violations = validate_resume.validate(resume, STYLE_RULES)
        self.assertFalse(any("opening verb" in v.lower() for v in violations))

    def test_flags_duplicate_opening_verb_even_with_leading_quote(self):
        resume = _valid_resume()
        resume["EXPERIENCE"][0]["achievements"] = [
            '"Innovated new onboarding flow adopted company-wide within a quarter"',
            "Innovated a new pricing model that increased average deal size",
        ]
        violations = validate_resume.validate(resume, STYLE_RULES)
        self.assertTrue(any("innovated" in v.lower() and "unique" in v.lower() for v in violations))

    def test_flags_skills_item_not_in_title_case(self):
        resume = _valid_resume()
        resume["SKILLS"] = ["**AI & Workflow Tools:** ChatGPT, Claude, AI-assisted workflows, Asana, CMS platforms"]
        violations = validate_resume.validate(resume, STYLE_RULES)
        self.assertTrue(any("title case" in v.lower() for v in violations))

    def test_flags_skills_category_label_not_in_title_case(self):
        resume = _valid_resume()
        resume["SKILLS"] = ["**CRM and revenue operations:** Salesforce, Reporting"]
        violations = validate_resume.validate(resume, STYLE_RULES)
        self.assertTrue(any("title case" in v.lower() for v in violations))

    def test_allows_title_case_skills_with_ampersand_and_acronyms(self):
        resume = _valid_resume()
        resume["SKILLS"] = ["**CRM & Revenue Operations:** Salesforce Administration, AI-Assisted Workflows, CMS Platforms"]
        violations = validate_resume.validate(resume, STYLE_RULES)
        self.assertFalse(any("title case" in v.lower() for v in violations))

    def test_flags_forbidden_phrase_in_skills_or_why_section(self):
        resume = _valid_resume()
        resume["SKILLS"] = ["**Marketing:** results-driven campaign management"]
        violations = validate_resume.validate(resume, STYLE_RULES)
        self.assertTrue(any("results-driven" in v for v in violations))

        resume2 = _valid_resume()
        resume2["WHY_TEXT"] = "<p><em>I bring a results-driven approach to this role.</em></p>"
        violations2 = validate_resume.validate(resume2, STYLE_RULES)
        self.assertTrue(any("results-driven" in v for v in violations2))


if __name__ == "__main__":
    unittest.main()
