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
        "SUMMARY_TEXT": "<strong>Lifecycle marketer with 8 years in CRM strategy.</strong> Scaled outreach to 50,000+ contacts monthly before returning to full-time work after a caregiving pause.",
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

    def test_flags_forbidden_opener_in_education_bullet(self):
        # EDUCATION bullets used to be invisible to _all_bullets() entirely --
        # 5 EDUCATION bullets got no length/forbidden-phrase/verb-uniqueness/
        # pronoun check at all (B28, phase-9-backlog.md).
        resume = _valid_resume()
        resume["EDUCATION"] = [
            {"institution": "University of Kansas", "bullets": ["Responsible for the school paper"]},
        ]
        violations = validate_resume.validate(resume, STYLE_RULES)
        self.assertTrue(any("forbidden opener" in v.lower() for v in violations))

    def test_flags_pronoun_in_education_bullet(self):
        resume = _valid_resume()
        resume["EDUCATION"] = [
            {"institution": "University of Kansas", "bullets": ["I led the school paper"]},
        ]
        violations = validate_resume.validate(resume, STYLE_RULES)
        self.assertTrue(any("pronoun" in v.lower() for v in violations))

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

    def test_allows_pronoun_inside_career_note(self):
        # career_note is hand-authored fixed content, unconditionally
        # reapplied by normalize_resume.normalize() on every retry pass --
        # flagging it here would make the fix-loop hard-fail every run
        # since the LLM has no power to change it. tailor_resume.md
        # documents it as a second deliberate pronoun exception, alongside
        # Why (see B28, phase-9-backlog.md).
        resume = _valid_resume()
        resume["EXPERIENCE"][0]["career_note"] = (
            "After a fulfilling run here, I took time to support a loved one's health. "
            "I'm excited to return to work with renewed focus."
        )
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


class TestRoleRoster(unittest.TestCase):
    """B60: profile.yml declared six roles and the shipped resume contained
    three -- Element 8 / Strategy LLC, VML and Callahan Creek, the whole
    page-2 work history, silently absent. Nothing at any layer required one
    EXPERIENCE entry per declared company: the rule lived only in a schema
    `description`, which sanitize_schema() strips before the API call, and
    _check_experience_completeness() can only see entries that are present."""

    def _resume(self, companies):
        return {"EXPERIENCE": [
            {"title": "Some Title", "company": c, "period": "2020-2024",
             "achievements": ["Did a thing."]}
            for c in companies
        ]}

    def test_missing_company_is_a_violation_that_names_it(self):
        violations = validate_resume._check_role_roster(
            self._resume(["Acme", "Globex"]), ["Acme", "Globex", "Callahan Creek"],
        )
        self.assertEqual(len(violations), 1)
        self.assertIn("Callahan Creek", violations[0])

    def test_every_missing_company_is_reported_not_just_the_first(self):
        violations = validate_resume._check_role_roster(
            self._resume(["Acme"]), ["Acme", "VML", "Callahan Creek", "Element 8"],
        )
        self.assertEqual(len(violations), 3)

    def test_complete_roster_produces_no_violation(self):
        self.assertEqual(
            validate_resume._check_role_roster(
                self._resume(["Acme", "Globex"]), ["Acme", "Globex"],
            ), [],
        )

    def test_an_annotated_company_name_still_counts_as_present(self):
        """Caught by the first real `resume sample` run after this check
        landed: profile.yml says "Inside Sales Team", the document says
        "Inside Sales Team (Now Alleyoop)". Not a missing employer -- and each
        false positive eats one of the validator's 4 fix attempts that a
        genuinely absent employer needs."""
        self.assertEqual(
            validate_resume._check_role_roster(
                self._resume(["Inside Sales Team (Now Alleyoop)"]), ["Inside Sales Team"],
            ), [],
        )

    def test_a_shortened_company_name_still_counts_as_present(self):
        self.assertEqual(
            validate_resume._check_role_roster(
                self._resume(["Callahan"]), ["Callahan Creek"],
            ), [],
        )

    def test_a_genuinely_absent_company_is_still_caught(self):
        violations = validate_resume._check_role_roster(
            self._resume(["Mercor", "Treering Yearbooks"]),
            ["Mercor", "Treering Yearbooks", "Callahan Creek"],
        )
        self.assertEqual(len(violations), 1)
        self.assertIn("Callahan Creek", violations[0])

    def test_punctuation_drift_between_kb_and_profile_is_not_a_missing_company(self):
        """The live failure this check kept reporting for three runs:
        profile.yml says "Element 8 / Strategy LLC", cv.md says "Element 8 +
        Strategy, LLC", and the builder writes the work history from the KB --
        so it emits the KB spelling and the roster check called it missing.
        VML and Callahan Creek are spelled identically in both sources, which
        is exactly why they were the only two that ever got 'fixed'."""
        self.assertEqual(
            validate_resume._check_role_roster(
                self._resume(["Element 8 + Strategy, LLC"]), ["Element 8 / Strategy LLC"],
            ), [],
        )

    def test_matching_ignores_case_and_surrounding_whitespace(self):
        self.assertEqual(
            validate_resume._check_role_roster(
                self._resume(["  acme  ", "GLOBEX"]), ["Acme", "Globex"],
            ), [],
        )

    def test_extra_companies_beyond_the_roster_are_allowed(self):
        # A situational role that fired is a legitimate extra entry.
        self.assertEqual(
            validate_resume._check_role_roster(
                self._resume(["Acme", "Situational Co"]), ["Acme"],
            ), [],
        )

    def test_empty_roster_skips_the_check(self):
        self.assertEqual(validate_resume._check_role_roster(self._resume([]), []), [])

    def test_validate_omitting_the_roster_does_not_raise_or_flag(self):
        # polish.py validates partial documents and supplies no roster.
        violations = validate_resume.validate(self._resume(["Acme"]), {})
        self.assertFalse([v for v in violations if "Role roster" in v])

    def test_validate_threads_the_roster_through(self):
        violations = validate_resume.validate(self._resume(["Acme"]), {}, ["Acme", "VML"])
        self.assertTrue(any("VML" in v for v in violations))


ATS_MATCH_RULES = {
    "thresholds": {"excellent_match": 85, "good_match": 70, "weak_match": 50},
}


class TestCheckKeywordCoverage(unittest.TestCase):
    """B18 (phase-9-backlog.md): deterministic JD-keyword coverage check."""

    def test_all_keywords_present_scores_100_and_excellent(self):
        jd_keywords = {
            "tools": [],
            "hard_skills": ["CRM Strategy", "Segmentation"],
            "core_functions": [],
        }
        report = validate_resume.check_keyword_coverage(_valid_resume(), jd_keywords, ATS_MATCH_RULES)
        self.assertEqual(report["score"], 100)
        self.assertEqual(report["band"], "excellent_match")
        self.assertEqual(report["missing"], [])

    def test_missing_keywords_are_reported_not_invented(self):
        jd_keywords = {
            "tools": ["Salesforce"],
            "hard_skills": ["Segmentation"],
            "core_functions": [],
        }
        report = validate_resume.check_keyword_coverage(_valid_resume(), jd_keywords, ATS_MATCH_RULES)
        self.assertEqual(report["missing"], ["Salesforce"])
        self.assertEqual(report["matched"], ["Segmentation"])
        self.assertEqual(report["score"], 50)
        self.assertEqual(report["band"], "weak_match")

    def test_no_keywords_extracted_scores_100_rather_than_dividing_by_zero(self):
        jd_keywords = {"tools": [], "hard_skills": [], "core_functions": []}
        report = validate_resume.check_keyword_coverage(_valid_resume(), jd_keywords, ATS_MATCH_RULES)
        self.assertEqual(report["score"], 100)
        self.assertEqual(report["missing"], [])

    def test_matching_is_case_insensitive_and_word_bounded(self):
        # "CRM" alone must not spuriously match inside an unrelated word,
        # and casing in the JD keyword must not matter.
        jd_keywords = {"tools": [], "hard_skills": ["crm strategy"], "core_functions": []}
        report = validate_resume.check_keyword_coverage(_valid_resume(), jd_keywords, ATS_MATCH_RULES)
        self.assertEqual(report["matched"], ["crm strategy"])

    def test_below_weak_threshold_is_poor_match(self):
        jd_keywords = {"tools": ["Salesforce", "HubSpot", "Marketo"], "hard_skills": [], "core_functions": []}
        report = validate_resume.check_keyword_coverage(_valid_resume(), jd_keywords, ATS_MATCH_RULES)
        self.assertEqual(report["band"], "poor_match")


class TestCheckSummarySpecificity(unittest.TestCase):
    """B29 (phase-9-backlog.md): flags a Summary whose sentences after the
    opening years-of-experience line never earn their place with a real
    proof point. Deliberately NOT part of validate()'s blocking checks --
    an earlier, blocking version of this check caused a real `resume
    sample` build to fail outright, oscillating between "no metric" and
    "duplicate metric" (metrics_rules' own uniqueness check) with no way
    out inside the retry loop's limited context. Same non-blocking,
    report-not-gate precedent as check_keyword_coverage above."""

    def test_flags_summary_with_no_metric_beyond_years_of_experience(self):
        # A real shipped resume had zero metrics in sentences 2-5 -- four
        # consecutive sentences of "[Verb]s [abstract noun] to [abstract
        # outcome]", interchangeable with any competent candidate's.
        resume = _valid_resume()
        resume["SUMMARY_TEXT"] = (
            "<strong>Lifecycle marketer with 8 years in CRM strategy.</strong> "
            "Specializes in building systems that scale. Transforms scattered "
            "data into a coherent revenue engine."
        )
        report = validate_resume.check_summary_specificity(resume)
        self.assertTrue(any("no concrete metric" in v.lower() for v in report))

    def test_allows_summary_with_metric_beyond_years_of_experience(self):
        resume = _valid_resume()
        resume["SUMMARY_TEXT"] = (
            "<strong>Lifecycle marketer with 8 years in CRM strategy.</strong> "
            "Recovered $3M in dormant pipeline through systematic CRM audits."
        )
        report = validate_resume.check_summary_specificity(resume)
        self.assertEqual(report, [])

    def test_does_not_credit_a_metric_inside_the_first_sentence_itself(self):
        # The years-of-experience figure lives inside the <strong> tag --
        # it shouldn't satisfy the rule on its own even if it's the only
        # number in the whole Summary.
        resume = _valid_resume()
        resume["SUMMARY_TEXT"] = "<strong>Lifecycle marketer with 8 years in CRM strategy.</strong> Builds durable revenue systems."
        report = validate_resume.check_summary_specificity(resume)
        self.assertTrue(any("no concrete metric" in v.lower() for v in report))

    def test_a_bare_one_sentence_summary_is_not_flagged(self):
        # No "remaining sentences" at all is a different, narrower problem
        # than this check targets -- see the check's own docstring.
        resume = _valid_resume()
        resume["SUMMARY_TEXT"] = "<strong>Lifecycle marketer with 8 years in CRM strategy.</strong>"
        report = validate_resume.check_summary_specificity(resume)
        self.assertEqual(report, [])

    def test_not_part_of_validates_blocking_violations(self):
        resume = _valid_resume()
        resume["SUMMARY_TEXT"] = (
            "<strong>Lifecycle marketer with 8 years in CRM strategy.</strong> "
            "Specializes in building systems that scale."
        )
        violations = validate_resume.validate(resume, STYLE_RULES)
        self.assertFalse(any("no concrete metric" in v.lower() for v in violations))


if __name__ == "__main__":
    unittest.main()
