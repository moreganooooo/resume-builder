import os
import sys
import unittest

SCRIPTS_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts"
)
sys.path.insert(0, SCRIPTS_DIR)

import validate_resume  # noqa: E402

STYLE_RULES = {
    "forbidden_phrases": ["results-driven", "passionate", "synergy", "best-in-class"],
    "forbidden_openers": [
        "responsible for",
        "helped with",
        "worked on",
        "assisted with",
        "participated in",
    ],
    "bullet_structure": {
        "one_liner_max_chars": 120,
        "two_liner_max_chars": 220,
        "max_printed_lines": 2,
    },
    "skills_section": {"line_max_chars": 110},
}


def _valid_resume():
    return {
        "SUMMARY_TEXT": "<strong>Lifecycle marketer with 8 years in CRM strategy.</strong> Scaled outreach to 50,000+ contacts monthly before returning to full-time work after a caregiving pause.",
        "SKILLS": [
            "**Lifecycle & Retention Marketing:** Email Automation, Segmentation, Drip Campaigns"
        ],
        "EXPERIENCE": [
            {
                "title": "Lifecycle Marketing Manager",
                "company": "Treering",
                "period": "08/2016 – 08/2024",
                "achievements": [
                    "Recovered 3M in dormant pipeline through CRM audits and reactivation workflows",
                    "Architected the SDR onboarding program used company-wide for three years",
                ],
            },
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
        resume["TAGLINE"] = (
            "CAMPAIGN CRM STRATEGIST | CAMPAIGN STRATEGY & LIFECYCLE MARKETING"
        )
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
        self.assertEqual(
            len(violations), 6
        )  # 3 missing-fields + 3 no-achievements, one pair per empty entry

    def test_flags_experience_entry_missing_achievements_only(self):
        resume = _valid_resume()
        resume["EXPERIENCE"] = [
            {
                "title": "Content Strategist",
                "company": "Acme",
                "period": "01/2020 – 01/2022",
                "achievements": [],
            }
        ]
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
        self.assertFalse(
            any("leverage" in v.lower() for v in violations),
            "must not flag 'leveraged' via the 'leverage' forbidden phrase",
        )

        resume["EXPERIENCE"][0]["achievements"][
            -1
        ] = "Built a plan to leverage AI tools org-wide"
        violations = validate_resume.validate(resume, style_rules)
        self.assertTrue(
            any("leverage" in v.lower() for v in violations),
            "must still flag the exact word 'leverage' itself",
        )

    def test_flags_forbidden_opener_in_bullet(self):
        resume = _valid_resume()
        resume["EXPERIENCE"][0]["achievements"].append(
            "Responsible for CRM data hygiene"
        )
        violations = validate_resume.validate(resume, STYLE_RULES)
        self.assertTrue(any("forbidden opener" in v.lower() for v in violations))

    def test_flags_duplicate_opening_verb_across_bullets(self):
        resume = _valid_resume()
        resume["EXPERIENCE"][0]["achievements"] = [
            "Architected the SDR onboarding program used company-wide for three years",
            "Architected the CRM data model powering territory reporting",
        ]
        violations = validate_resume.validate(resume, STYLE_RULES)
        self.assertTrue(
            any(
                "architected" in v.lower() and "unique" in v.lower() for v in violations
            )
        )

    def test_flags_forbidden_opener_in_education_bullet(self):
        # EDUCATION bullets used to be invisible to _all_bullets() entirely --
        # 5 EDUCATION bullets got no length/forbidden-phrase/verb-uniqueness/
        # pronoun check at all (B28, phase-9-backlog.md).
        resume = _valid_resume()
        resume["EDUCATION"] = [
            {
                "institution": "University of Kansas",
                "bullets": ["Responsible for the school paper"],
            },
        ]
        violations = validate_resume.validate(resume, STYLE_RULES)
        self.assertTrue(any("forbidden opener" in v.lower() for v in violations))

    def test_flags_pronoun_in_education_bullet(self):
        resume = _valid_resume()
        resume["EDUCATION"] = [
            {
                "institution": "University of Kansas",
                "bullets": ["I led the school paper"],
            },
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
        resume["SKILLS"] = [
            "**Cat:** " + "X" * 155
        ]  # plain length 160, remainder 50 -- a full 2nd line
        violations = validate_resume.validate(resume, STYLE_RULES)
        self.assertFalse(any("skills line" in v.lower() for v in violations))

    def test_flags_skills_line_that_leaves_a_short_widow(self):
        resume = _valid_resume()
        resume["SKILLS"] = [
            "**Cat:** " + "X" * 110
        ]  # plain length 115, remainder 5 -- a stray scrap
        violations = validate_resume.validate(resume, STYLE_RULES)
        self.assertTrue(any("widow" in v.lower() for v in violations))

    def test_skills_widow_message_names_both_legal_targets(self):
        # Regression guard for a build that burned all 4 validator retries:
        # the old message named only the 110-char limit, so the model kept
        # landing in the 111-134 dead band where no legal length exists.
        # Both edges of the legal zone have to be in the message text.
        resume = _valid_resume()
        resume["SKILLS"] = ["**Cat:** " + "X" * 110]
        violations = validate_resume.validate(resume, STYLE_RULES)
        message = next(v for v in violations if "widow" in v.lower())
        self.assertIn("110", message)  # upper edge of the short-and-legal zone
        self.assertIn("135", message)  # lower edge of the wrapped-and-legal zone
        self.assertIn("111-134", message)  # the dead band, named explicitly

    def test_skills_widow_message_computes_targets_from_the_rules(self):
        # The two targets must be derived, not hardcoded, or they silently
        # go stale the moment either rule is re-tuned.
        rules = {"skills_section": {"line_max_chars": 60, "widow_min_chars": 10}}
        resume = {"SKILLS": ["X" * 65]}
        message = validate_resume._check_skills_line_lengths(resume, rules)[0]
        self.assertIn("60", message)
        self.assertIn("70", message)
        self.assertIn("61-69", message)

    def test_single_bullet_is_never_reported_against_itself(self):
        # One bullet legitimately citing 22% twice (own result vs industry
        # benchmark) used to self-collide, producing "in both X and X" --
        # which shows the model the same string twice and is unactionable.
        bullet = (
            "Generated 62 niche sequences across 4 audience segments, achieving 74% open "
            "and 22% reply rates on PTA campaigns, exceeding the 22% nonprofit industry average"
        )
        violations = validate_resume._check_metric_uniqueness(
            {"EXPERIENCE": [{"achievements": [bullet]}]}
        )
        self.assertEqual(violations, [])

    def test_percentages_are_disambiguated_by_their_context_word(self):
        # '%' is not a word char, so the old pattern backtracked off it and
        # the context lookup then failed -- every percentage collapsed to a
        # context-free signature and same-digit percentages cross-reported.
        resume = {
            "EXPERIENCE": [
                {
                    "achievements": [
                        "Maintained 100% on-time delivery across all print cycles for the student newspaper",
                        "Authored 100+ multi-touch email campaigns for niche K-12 district segments",
                        "Standardized templates across a sequence library of 100+ assets for the team",
                    ]
                }
            ]
        }
        self.assertEqual(validate_resume._check_metric_uniqueness(resume), [])

    def test_still_flags_a_genuinely_repeated_metric(self):
        resume = {
            "EXPERIENCE": [
                {
                    "achievements": [
                        "Drove 41% reply rates across the PTA sequence rebuild program",
                        "Sustained 41% reply rates on the same PTA sequence rebuild program",
                    ]
                }
            ]
        }
        violations = validate_resume._check_metric_uniqueness(resume)
        self.assertTrue(any("41" in v for v in violations))

    def test_allows_first_person_pronoun_in_summary(self):
        # 2026-09-17: the Summary is the one generated section where this
        # candidate's own favorite resumes all speak as "I" (see the
        # profile's voice-favorites.md). It is a PER-PROFILE opt-in --
        # profile.yml's voice_preferences.summary_first_person, carried to
        # the validator on the style_rules dict (same pattern as
        # enforce_star) -- not a universal style change. Bullets, skills,
        # and education keep the strict ban under both settings.
        opted_in = {**STYLE_RULES, "summary_first_person": True}
        resume = _valid_resume()
        resume["SUMMARY_TEXT"] = (
            "<strong>I'm a lifecycle marketer with 10+ years of experience.</strong> "
            "I've owned full-funnel messaging across channels."
        )
        violations = validate_resume.validate(resume, opted_in)
        self.assertFalse(any("pronoun" in v.lower() for v in violations))

    def test_first_person_summary_stays_flagged_without_the_opt_in(self):
        # Default (no voice_preferences.summary_first_person): the shared
        # pronoun-free rule still applies to the Summary. This keeps the
        # test operator-independent -- it must not depend on whose profile
        # happens to be active on the machine running the suite.
        resume = _valid_resume()
        resume["SUMMARY_TEXT"] = (
            "<strong>I'm a lifecycle marketer with 10+ years of experience.</strong>"
        )
        violations = validate_resume.validate(resume, STYLE_RULES)
        self.assertTrue(any("pronoun" in v.lower() for v in violations))

    def test_flags_pronoun_outside_why_section(self):
        resume = _valid_resume()
        resume["EXPERIENCE"][0]["achievements"] = [
            "I led the lifecycle marketing team to record open rates",
        ]
        violations = validate_resume.validate(resume, STYLE_RULES)
        self.assertTrue(any("pronoun" in v.lower() for v in violations))

    def test_flags_third_person_pronoun_in_summary(self):
        # The Summary should read as the candidate's own voice, not a
        # third-person biography -- "She specializes in..." is a violation
        # even for a profile that opted into first-person Summaries.
        opted_in = {**STYLE_RULES, "summary_first_person": True}
        resume = _valid_resume()
        resume["SUMMARY_TEXT"] = (
            "<strong>Alex is a lifecycle marketer.</strong> She leads CRM strategy."
        )
        violations = validate_resume.validate(resume, opted_in)
        self.assertTrue(any("pronoun" in v.lower() for v in violations))

    def test_flags_third_person_pronoun_hiding_in_first_person_summary(self):
        # First person doesn't grant a blanket exemption: a summary that is
        # mostly "I" but slips in a "her"/"she" is still flagged.
        opted_in = {**STYLE_RULES, "summary_first_person": True}
        resume = _valid_resume()
        resume["SUMMARY_TEXT"] = (
            "<strong>I'm a lifecycle marketer.</strong> "
            "My teams trusted her judgment on segmentation."
        )
        violations = validate_resume.validate(resume, opted_in)
        self.assertTrue(any("pronoun" in v.lower() for v in violations))

    def test_allows_pronoun_inside_why_section(self):
        resume = _valid_resume()
        resume["WHY_TEXT"] = (
            "<p><em>I built the SDR Process Map at Treering for exactly this reason.</em></p>"
        )
        violations = validate_resume.validate(resume, STYLE_RULES)
        self.assertEqual(violations, [])

    def test_flags_count_standin_that_replaced_a_verified_figure(self):
        # 2026-09-17 sample build: "1,578 schools" in the bank became
        # "thousands of schools" in the generated bullet -- the rewrite
        # swapped the verified figure for a vague count. Soft violation,
        # but the fix loop is told exactly which figure to restore.
        resume = _valid_resume()
        resume["EXPERIENCE"][0]["achievements"] = [
            "Managed a $15.1M portfolio of thousands of schools across 100+ districts",
        ]
        bullet_tuples = [
            (
                "Managed a $15.1M portfolio of 1,578 schools across 100+ districts",
                "Treering",
                "[mgmt]",
            ),
        ]
        violations = validate_resume._check_vague_magnitudes(resume, bullet_tuples)
        self.assertTrue(any("thousands of schools" in v.lower() for v in violations))
        self.assertTrue(any("1,578" in v for v in violations))

    def test_allows_count_standin_when_no_source_figure_exists(self):
        # "hundreds of conferences" with no number anywhere in the
        # company's own source bullets is legitimate vagueness about a
        # genuinely uncounted fact -- nothing to restore, nothing to flag.
        resume = _valid_resume()
        resume["EXPERIENCE"][0]["achievements"] = [
            "Spoke at hundreds of conferences about lifecycle marketing strategy",
        ]
        bullet_tuples = [
            (
                "Represented the lifecycle marketing team at industry events",
                "Treering",
                "[generalist]",
            ),
        ]
        violations = validate_resume._check_vague_magnitudes(resume, bullet_tuples)
        self.assertFalse(any("hundreds" in v.lower() for v in violations))

    def test_allows_count_standin_when_the_figure_is_already_stated(self):
        resume = _valid_resume()
        resume["EXPERIENCE"][0]["achievements"] = [
            "Managed a $15.1M portfolio of thousands of schools, including 1,578 active accounts",
        ]
        bullet_tuples = [
            (
                "Managed a $15.1M portfolio of 1,578 schools across 100+ districts",
                "Treering",
                "[mgmt]",
            ),
        ]
        violations = validate_resume._check_vague_magnitudes(resume, bullet_tuples)
        self.assertFalse(any("thousands of schools" in v.lower() for v in violations))

    def test_count_standin_match_requires_the_same_noun(self):
        # "thousands of emails" must not be "fixed" with the verified
        # figure about schools -- the count attaches to a different noun.
        resume = _valid_resume()
        resume["EXPERIENCE"][0]["achievements"] = [
            "Sent thousands of emails from a $15.1M portfolio of accounts",
        ]
        bullet_tuples = [
            (
                "Managed a $15.1M portfolio of 1,578 schools across 100+ districts",
                "Treering",
                "[mgmt]",
            ),
        ]
        violations = validate_resume._check_vague_magnitudes(resume, bullet_tuples)
        self.assertFalse(any("thousands of emails" in v.lower() for v in violations))

    def test_flags_bullet_ending_with_trailing_punctuation(self):
        # 2026-09-17 sample build: a builder-produced bullet shipped ending
        # in a period. The Step 3 critique enforces the rule on bank
        # bullets, but nothing on the builder path re-checked it.
        resume = _valid_resume()
        resume["EXPERIENCE"][0]["achievements"].append(
            "Coached a remote pod of SDRs on messaging, beating company reply rate benchmarks."
        )
        violations = validate_resume.validate(resume, STYLE_RULES)
        self.assertTrue(any("trailing punctuation" in v.lower() for v in violations))

    def test_flags_trailing_punctuation_in_education_bullet(self):
        resume = _valid_resume()
        resume["EDUCATION"] = [
            {
                "institution": "University of Kansas",
                "bullets": ["Produced editorial content across channels."],
            },
        ]
        violations = validate_resume.validate(resume, STYLE_RULES)
        self.assertTrue(any("trailing punctuation" in v.lower() for v in violations))

    def test_allows_bullet_with_internal_punctuation(self):
        # Only the END matters -- periods inside abbreviations or
        # sentence-internal structure are fine.
        resume = _valid_resume()
        resume["EXPERIENCE"][0]["achievements"].append(
            "Led weekly QA for U.S. and U.K. sends across 30+ campaigns"
        )
        violations = validate_resume.validate(resume, STYLE_RULES)
        self.assertFalse(any("trailing punctuation" in v.lower() for v in violations))

    def test_flags_bare_fragment_item_in_skills_line(self):
        # 2026-09-17 sample build shipped "...Content Operations, Assets" --
        # a bare generic noun the hallucination check passed because the
        # verified ledger holds compound names bearing the word.
        resume = _valid_resume()
        resume["SKILLS"] = [
            "**Content Strategy:** Content Marketing, Campaign Messaging, Content Operations, Assets",
        ]
        violations = validate_resume.validate(resume, STYLE_RULES)
        self.assertTrue(any("fragment item" in v.lower() for v in violations))

    def test_allows_qualified_compound_items_in_skills_line(self):
        # The same word inside a qualified compound ("Brand Assets") or a
        # real skill is fine -- only a BARE generic noun is a fragment.
        resume = _valid_resume()
        resume["SKILLS"] = [
            "**Creative & Content:** Brand Assets, Asset Management, Copywriting, CMS Platforms",
        ]
        violations = validate_resume.validate(resume, STYLE_RULES)
        self.assertFalse(any("fragment item" in v.lower() for v in violations))

    def test_flags_monotonous_prose_rhythm_in_why_section(self):
        # 2026-09-17: the generated Why section was five near-identically
        # paced sentences -- the "AI-beige" cadence voice_metrics.py
        # already measures for cover letters. Soft violation (nudge only).
        resume = _valid_resume()
        resume["WHY_TEXT"] = (
            "<p>I believe this company builds meaningful products for people. "
            "I have built meaningful systems for teams over ten years. "
            "I want to bring meaningful strategy to your mission. "
            "I care deeply about meaningful communication with customers. "
            "I would be excited to contribute meaningful work here.</p>"
        )
        violations = validate_resume.validate(resume, STYLE_RULES)
        self.assertTrue(any("Prose rhythm" in v for v in violations))

    def test_prose_rhythm_skips_short_prose(self):
        # A 5-line Summary is 3-4 sentences; burstiness stats on samples
        # that small are noise, so the check stays quiet.
        resume = _valid_resume()
        resume["SUMMARY_TEXT"] = (
            "<strong>Lifecycle marketer.</strong> I build things. "
            "I have built other things too. Scaled campaigns."
        )
        violations = validate_resume.validate(resume, STYLE_RULES)
        self.assertFalse(any("Prose rhythm" in v for v in violations))

    def test_varied_prose_rhythm_passes(self):
        resume = _valid_resume()
        resume["WHY_TEXT"] = (
            "<p>Your mission matters to me. Across ten years I have built content systems, "
            "campaign operations, and training programs that turned scattered messaging into "
            "something coherent, measurable, and genuinely useful for the people receiving it. "
            "That is the work I want to keep doing. Your platform is where I would do it.</p>"
        )
        violations = validate_resume.validate(resume, STYLE_RULES)
        self.assertFalse(any("Prose rhythm" in v for v in violations))

    def test_advisory_word_downgrades_to_soft_in_prose_for_opted_profile(self):
        # 2026-09-17: the candidate's own favorite summaries use
        # "passionate" as a grounded first-person adjective (the Rula
        # sample). The per-profile prose_advisory_words opt-in downgrades
        # the single word to a soft advisory in Summary/Why only.
        opted_in = {
            **STYLE_RULES,
            "prose_advisory_words": ["passionate", "driven", "dynamic"],
        }
        resume = _valid_resume()
        resume["SUMMARY_TEXT"] = (
            "<strong>Lifecycle marketer with 8 years in CRM strategy.</strong> "
            "I'm passionate about communication that meets people where they are."
        )
        violations = validate_resume.validate(resume, opted_in)
        self.assertTrue(any(v.startswith("Advisory word 'passionate'") for v in violations))
        self.assertFalse(
            any(v.startswith("Forbidden phrase 'passionate'") for v in violations)
        )

    def test_advisory_word_stays_hard_without_the_opt_in(self):
        resume = _valid_resume()
        resume["SUMMARY_TEXT"] = (
            "<strong>Lifecycle marketer with 8 years in CRM strategy.</strong> "
            "I'm passionate about communication that meets people where they are."
        )
        violations = validate_resume.validate(resume, STYLE_RULES)
        self.assertTrue(any(v.startswith("Forbidden phrase 'passionate'") for v in violations))

    def test_advisory_word_stays_hard_in_bullets_and_multiword_phrases(self):
        # The downgrade covers single words in Summary/Why ONLY: bullets
        # and multi-word clichés ("results-driven professional") keep the
        # hard ban even for an opted-in profile.
        opted_in = {
            **STYLE_RULES,
            "prose_advisory_words": ["passionate", "driven", "dynamic"],
        }
        resume = _valid_resume()
        resume["EXPERIENCE"][0]["achievements"] = [
            "Passionate about CRM hygiene, led quarterly list-cleanup audits",
        ]
        resume["SUMMARY_TEXT"] = (
            "<strong>Results-driven professional with 8 years in CRM strategy.</strong>"
        )
        violations = validate_resume.validate(resume, opted_in)
        self.assertTrue(any(v.startswith("Forbidden phrase 'passionate'") for v in violations))
        # "results-driven professional" trips several entries of the list
        # ("results-driven", "results-driven professional", "driven
        # professional"); any hard hit proves the multi-word cliché was
        # not downgraded.
        self.assertTrue(
            any(
                v.startswith("Forbidden phrase 'results-driven")
                or v.startswith("Forbidden phrase 'driven professional'")
                for v in violations
            )
        )

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
        resume["SUMMARY_TEXT"] = (
            "<strong>Recovered 3M in dormant pipeline as a lifecycle marketer.</strong>"
        )
        # _valid_resume() already has "Recovered 3M" in a bullet -- now it's in both places.
        violations = validate_resume.validate(resume, STYLE_RULES)
        self.assertTrue(
            any(
                "3m" in v.lower() and ("once" in v.lower() or "duplicate" in v.lower())
                for v in violations
            )
        )

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
        resume["SUMMARY_TEXT"] = (
            "<strong>Lifecycle marketer with 10+ years of experience.</strong>"
        )
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
        self.assertTrue(
            any("innovated" in v.lower() and "unique" in v.lower() for v in violations)
        )

    def test_flags_skills_item_not_in_title_case(self):
        resume = _valid_resume()
        resume["SKILLS"] = [
            "**AI & Workflow Tools:** ChatGPT, Claude, AI-assisted workflows, Asana, CMS platforms"
        ]
        violations = validate_resume.validate(resume, STYLE_RULES)
        self.assertTrue(any("title case" in v.lower() for v in violations))

    def test_flags_skills_category_label_not_in_title_case(self):
        resume = _valid_resume()
        resume["SKILLS"] = ["**CRM and revenue operations:** Salesforce, Reporting"]
        violations = validate_resume.validate(resume, STYLE_RULES)
        self.assertTrue(any("title case" in v.lower() for v in violations))

    def test_allows_title_case_skills_with_ampersand_and_acronyms(self):
        resume = _valid_resume()
        resume["SKILLS"] = [
            "**CRM & Revenue Operations:** Salesforce Administration, AI-Assisted Workflows, CMS Platforms"
        ]
        violations = validate_resume.validate(resume, STYLE_RULES)
        self.assertFalse(any("title case" in v.lower() for v in violations))

    def test_flags_forbidden_phrase_in_skills_or_why_section(self):
        resume = _valid_resume()
        resume["SKILLS"] = ["**Marketing:** results-driven campaign management"]
        violations = validate_resume.validate(resume, STYLE_RULES)
        self.assertTrue(any("results-driven" in v for v in violations))

        resume2 = _valid_resume()
        resume2["WHY_TEXT"] = (
            "<p><em>I bring a results-driven approach to this role.</em></p>"
        )
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
        return {
            "EXPERIENCE": [
                {
                    "title": "Some Title",
                    "company": c,
                    "period": "2020-2024",
                    "achievements": ["Did a thing."],
                }
                for c in companies
            ]
        }

    def test_missing_company_is_a_violation_that_names_it(self):
        violations = validate_resume._check_role_roster(
            self._resume(["Acme", "Globex"]),
            ["Acme", "Globex", "Callahan Creek"],
        )
        self.assertEqual(len(violations), 1)
        self.assertIn("Callahan Creek", violations[0])

    def test_every_missing_company_is_reported_not_just_the_first(self):
        violations = validate_resume._check_role_roster(
            self._resume(["Acme"]),
            ["Acme", "VML", "Callahan Creek", "Element 8"],
        )
        self.assertEqual(len(violations), 3)

    def test_complete_roster_produces_no_violation(self):
        self.assertEqual(
            validate_resume._check_role_roster(
                self._resume(["Acme", "Globex"]),
                ["Acme", "Globex"],
            ),
            [],
        )

    def test_an_annotated_company_name_still_counts_as_present(self):
        """Caught by the first real `resume sample` run after this check
        landed: profile.yml says "Inside Sales Team", the document says
        "Inside Sales Team (Now Alleyoop)". Not a missing employer -- and each
        false positive eats one of the validator's 4 fix attempts that a
        genuinely absent employer needs."""
        self.assertEqual(
            validate_resume._check_role_roster(
                self._resume(["Inside Sales Team (Now Alleyoop)"]),
                ["Inside Sales Team"],
            ),
            [],
        )

    def test_a_shortened_company_name_still_counts_as_present(self):
        self.assertEqual(
            validate_resume._check_role_roster(
                self._resume(["Callahan"]),
                ["Callahan Creek"],
            ),
            [],
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
                self._resume(["Element 8 + Strategy, LLC"]),
                ["Element 8 / Strategy LLC"],
            ),
            [],
        )

    def test_matching_ignores_case_and_surrounding_whitespace(self):
        self.assertEqual(
            validate_resume._check_role_roster(
                self._resume(["  acme  ", "GLOBEX"]),
                ["Acme", "Globex"],
            ),
            [],
        )

    def test_extra_companies_beyond_the_roster_are_allowed(self):
        # A situational role that fired is a legitimate extra entry.
        self.assertEqual(
            validate_resume._check_role_roster(
                self._resume(["Acme", "Situational Co"]),
                ["Acme"],
            ),
            [],
        )

    def test_empty_roster_skips_the_check(self):
        self.assertEqual(validate_resume._check_role_roster(self._resume([]), []), [])

    def test_validate_omitting_the_roster_does_not_raise_or_flag(self):
        # polish.py validates partial documents and supplies no roster.
        violations = validate_resume.validate(self._resume(["Acme"]), {})
        self.assertFalse([v for v in violations if "Role roster" in v])

    def test_validate_threads_the_roster_through(self):
        violations = validate_resume.validate(
            self._resume(["Acme"]), {}, ["Acme", "VML"]
        )
        self.assertTrue(any("VML" in v for v in violations))


class TestRoleOrder(unittest.TestCase):
    """Mercor (08/2025) shipped rendered after Inside Sales Team (10/2015-
    08/2016) and Treering (08/2016-08/2024), even though profile.yml's
    roles: list -- already in correct reverse-chronological order -- had
    Mercor first. Nothing checked that the model's EXPERIENCE ordering
    actually matched the declared roster order."""

    def _resume(self, companies):
        return {
            "EXPERIENCE": [
                {
                    "title": "Some Title",
                    "company": c,
                    "period": "2020-2024",
                    "achievements": ["Did a thing."],
                }
                for c in companies
            ]
        }

    def test_correct_order_produces_no_violation(self):
        self.assertEqual(
            validate_resume._check_role_order(
                self._resume(["Mercor", "Treering", "Callahan Creek"]),
                ["Mercor", "Treering", "Callahan Creek"],
            ),
            [],
        )

    def test_out_of_order_company_is_a_violation(self):
        violations = validate_resume._check_role_order(
            self._resume(["Treering", "Inside Sales Team", "Mercor", "Callahan Creek"]),
            ["Mercor", "Treering", "Inside Sales Team", "Callahan Creek"],
        )
        self.assertEqual(len(violations), 1)
        self.assertIn("Mercor", violations[0])

    def test_a_missing_company_does_not_also_register_as_an_order_violation(self):
        # Absence is _check_role_roster()'s job; skip it here so one gap
        # doesn't burn a fix attempt on a phantom order problem too.
        self.assertEqual(
            validate_resume._check_role_order(
                self._resume(["Mercor", "Callahan Creek"]),
                ["Mercor", "Treering", "Callahan Creek"],
            ),
            [],
        )

    def test_an_annotated_company_name_still_matches_for_ordering(self):
        self.assertEqual(
            validate_resume._check_role_order(
                self._resume(["Mercor", "Inside Sales Team (Now Alleyoop)"]),
                ["Mercor", "Inside Sales Team"],
            ),
            [],
        )

    def test_extra_company_beyond_the_roster_does_not_break_ordering(self):
        self.assertEqual(
            validate_resume._check_role_order(
                self._resume(["Mercor", "Situational Co", "Treering"]),
                ["Mercor", "Treering"],
            ),
            [],
        )

    def test_empty_roster_skips_the_check(self):
        self.assertEqual(validate_resume._check_role_order(self._resume([]), []), [])

    def test_validate_threads_the_order_check_through(self):
        violations = validate_resume.validate(
            self._resume(["Treering", "Mercor"]),
            {},
            ["Mercor", "Treering"],
        )
        self.assertTrue(any("Work history order" in v for v in violations))


class TestBulletCounts(unittest.TestCase):
    """Element 8 / Strategy LLC, VML, and Callahan Creek each shipped with 2
    achievement bullets against a declared min_bullets of 3 -- the ROLE
    RULES block told the model the target, but nothing checked the model
    hit it."""

    def _resume(self, company_bullet_counts):
        return {
            "EXPERIENCE": [
                {
                    "title": "Some Title",
                    "company": c,
                    "period": "2020-2024",
                    "achievements": [f"Did thing {i}." for i in range(n)],
                }
                for c, n in company_bullet_counts.items()
            ]
        }

    def test_below_minimum_is_a_violation_naming_company_and_count(self):
        violations = validate_resume._check_bullet_counts(
            self._resume({"VML": 2}),
            {"VML": 3},
        )
        self.assertEqual(len(violations), 1)
        self.assertIn("VML", violations[0])
        self.assertIn("2", violations[0])
        self.assertIn("3", violations[0])

    def test_meeting_the_minimum_exactly_produces_no_violation(self):
        self.assertEqual(
            validate_resume._check_bullet_counts(self._resume({"VML": 3}), {"VML": 3}),
            [],
        )

    def test_exceeding_the_minimum_produces_no_violation(self):
        self.assertEqual(
            validate_resume._check_bullet_counts(self._resume({"VML": 5}), {"VML": 3}),
            [],
        )

    def test_every_deficient_company_is_reported(self):
        violations = validate_resume._check_bullet_counts(
            self._resume({"VML": 2, "Callahan Creek": 1, "Treering": 6}),
            {"VML": 3, "Callahan Creek": 3, "Treering": 6},
        )
        self.assertEqual(len(violations), 2)

    def test_an_annotated_company_name_still_matches_for_bullet_counts(self):
        self.assertEqual(
            validate_resume._check_bullet_counts(
                self._resume({"Callahan Creek (Now BarkleyOKRP)": 3}),
                {"Callahan Creek": 3},
            ),
            [],
        )

    def test_company_with_no_declared_minimum_is_skipped_not_flagged(self):
        self.assertEqual(
            validate_resume._check_bullet_counts(
                self._resume({"Situational Co": 1}),
                {"VML": 3},
            ),
            [],
        )

    def test_empty_minimums_skips_the_check(self):
        self.assertEqual(validate_resume._check_bullet_counts(self._resume({}), {}), [])

    def test_validate_threads_the_minimums_through(self):
        violations = validate_resume.validate(
            self._resume({"VML": 1}),
            {},
            role_bullet_minimums={"VML": 3},
        )
        self.assertTrue(any("Bullet count" in v for v in violations))


class TestBulletWidows(unittest.TestCase):
    """style_rules.yaml's bullet_structure has declared widow_min_words: 5
    since it was written, but nothing checked it -- a live resume shipped
    with bullets wrapping to a 2- and 4-word 2nd line. Confirmed against
    the actual rendered PDF: the char-120 cutoff correctly identified both
    real widows (off by one word on the shorter one, which is fine -- the
    approximation only needs to catch the case, not count exactly)."""

    LIMITS = {
        "bullet_structure": {
            "one_liner_max_chars": 120,
            "two_liner_max_chars": 220,
            "widow_min_words": 5,
        }
    }

    def _resume(self, bullets, company="Acme"):
        return {
            "EXPERIENCE": [
                {
                    "title": "Some Title",
                    "company": company,
                    "period": "2020-2024",
                    "achievements": bullets,
                }
            ]
        }

    def test_flags_a_bullet_with_a_short_widow(self):
        # Real example from a shipped resume: wraps with a 4-word 2nd line.
        bullet = (
            "Produced campaign-ready copy across multiple enterprise accounts, "
            "adapting voice and strategy across B2B tech, hospitality, and consumer categories"
        )
        violations = validate_resume._check_bullet_widows(
            self._resume([bullet]), self.LIMITS
        )
        self.assertEqual(len(violations), 1)
        self.assertIn(bullet, violations[0])

    def test_one_liner_that_fits_is_not_flagged(self):
        self.assertEqual(
            validate_resume._check_bullet_widows(
                self._resume(
                    ["Recovered $3M+ in stale pipeline through a systematic CRM audit"]
                ),
                self.LIMITS,
            ),
            [],
        )

    def test_two_liner_with_a_full_second_line_is_not_flagged(self):
        # Wraps to a 2nd line, but a substantial one -- not a widow.
        bullet = (
            "Architected a Content Systems case study by founding and chairing the Content "
            "Committee, governing 100+ campaign assets and establishing brand voice standards"
        )
        self.assertEqual(
            validate_resume._check_bullet_widows(self._resume([bullet]), self.LIMITS),
            [],
        )

    def test_bullet_past_two_liner_max_is_not_double_flagged(self):
        # _check_bullet_lengths()'s job, not this check's.
        self.assertEqual(
            validate_resume._check_bullet_widows(
                self._resume(["X" * 221]), self.LIMITS
            ),
            [],
        )

    def test_education_bullets_are_not_checked(self):
        """Education bullets are fixed Python content (fixed_content.py) with
        no LLM in the loop -- flagging one here would create a violation the
        4-attempt fix loop could never resolve, exhausting it every build
        that happens to select that achievement option."""
        resume = self._resume([])
        resume["EDUCATION"] = [
            {
                "institution": "KU",
                "bullets": [
                    "Marketing Intern, Lied Center of Performing Arts, drove 800% social media "
                    "follower growth through organic content strategy and audience engagement",
                ],
            }
        ]
        self.assertEqual(validate_resume._check_bullet_widows(resume, self.LIMITS), [])

    def test_validate_threads_the_widow_check_through(self):
        bullet = "Worked across the full creative development cycle, from brief and concepting through copy revisions and client presentation"
        violations = validate_resume.validate(self._resume([bullet]), self.LIMITS)
        self.assertTrue(any("widow" in v.lower() for v in violations))


class TestBulletsWithShortWidow(unittest.TestCase):
    """bullets_with_short_widow() is the shared helper both
    validate_resume._check_bullet_widows() and orchestrator.py's
    _short_widow_bullets() call, so the pre-render fix loop and the
    page-overflow trim step can never drift onto different thresholds."""

    LIMITS = {
        "bullet_structure": {
            "one_liner_max_chars": 120,
            "two_liner_max_chars": 220,
            "widow_min_words": 5,
        }
    }

    def test_returns_bullet_and_word_count_pairs(self):
        bullet = "Worked across the full creative development cycle, from brief and concepting through copy revisions and client presentation"
        results = validate_resume.bullets_with_short_widow([bullet], self.LIMITS)
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0][0], bullet)
        self.assertIsInstance(results[0][1], int)

    def test_empty_list_in_empty_list_out(self):
        self.assertEqual(validate_resume.bullets_with_short_widow([], self.LIMITS), [])


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
        report = validate_resume.check_keyword_coverage(
            _valid_resume(), jd_keywords, ATS_MATCH_RULES
        )
        self.assertEqual(report["score"], 100)
        self.assertEqual(report["band"], "excellent_match")
        self.assertEqual(report["missing"], [])

    def test_missing_keywords_are_reported_not_invented(self):
        jd_keywords = {
            "tools": ["Salesforce"],
            "hard_skills": ["Segmentation"],
            "core_functions": [],
        }
        report = validate_resume.check_keyword_coverage(
            _valid_resume(), jd_keywords, ATS_MATCH_RULES
        )
        self.assertEqual(report["missing"], ["Salesforce"])
        self.assertEqual(report["matched"], ["Segmentation"])
        self.assertEqual(report["score"], 50)
        self.assertEqual(report["band"], "weak_match")

    def test_no_keywords_extracted_scores_100_rather_than_dividing_by_zero(self):
        jd_keywords = {"tools": [], "hard_skills": [], "core_functions": []}
        report = validate_resume.check_keyword_coverage(
            _valid_resume(), jd_keywords, ATS_MATCH_RULES
        )
        self.assertEqual(report["score"], 100)
        self.assertEqual(report["missing"], [])

    def test_matching_is_case_insensitive_and_word_bounded(self):
        # "CRM" alone must not spuriously match inside an unrelated word,
        # and casing in the JD keyword must not matter.
        jd_keywords = {
            "tools": [],
            "hard_skills": ["crm strategy"],
            "core_functions": [],
        }
        report = validate_resume.check_keyword_coverage(
            _valid_resume(), jd_keywords, ATS_MATCH_RULES
        )
        self.assertEqual(report["matched"], ["crm strategy"])

    def test_below_weak_threshold_is_poor_match(self):
        jd_keywords = {
            "tools": ["Salesforce", "HubSpot", "Marketo"],
            "hard_skills": [],
            "core_functions": [],
        }
        report = validate_resume.check_keyword_coverage(
            _valid_resume(), jd_keywords, ATS_MATCH_RULES
        )
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
        resume["SUMMARY_TEXT"] = (
            "<strong>Lifecycle marketer with 8 years in CRM strategy.</strong> Builds durable revenue systems."
        )
        report = validate_resume.check_summary_specificity(resume)
        self.assertTrue(any("no concrete metric" in v.lower() for v in report))

    def test_a_bare_one_sentence_summary_is_not_flagged(self):
        # No "remaining sentences" at all is a different, narrower problem
        # than this check targets -- see the check's own docstring.
        resume = _valid_resume()
        resume["SUMMARY_TEXT"] = (
            "<strong>Lifecycle marketer with 8 years in CRM strategy.</strong>"
        )
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


class TestDistinctiveMetricsIgnoreTheContextWord(unittest.TestCase):
    """The context word exists so a bare "12" in two unrelated places isn't
    a false duplicate. But it cuts the other way for a big, specific figure:
    "$20M, 2,932-account portfolio" and "$20M+ portfolio" pick up different
    context words and stopped colliding, even though a reader plainly sees
    the same $20M twice. Distinctive figures therefore key on the number
    alone; small bare integers keep the context word."""

    def _sigs(self, text):
        return {sig for _n, sig in validate_resume._extract_metric_signatures(text)}

    def test_the_same_large_figure_collides_across_different_context_words(self):
        self.assertTrue(
            self._sigs("Managed a $20M, 2,932-account portfolio")
            & self._sigs("Grew the $20M+ portfolio by double digits")
        )

    def test_a_trailing_plus_is_not_a_different_figure(self):
        self.assertTrue(
            self._sigs("Drove $4M in pipeline") & self._sigs("Drove $4M+ in pipeline")
        )

    def test_a_digit_glued_to_a_letter_is_an_identifier_not_a_metric(self):
        """The "3" in "S3" is part of a service name. Left unguarded it
        collided with an unrelated Summary figure and failed a real build
        after all four retry attempts -- the bullet's only "3" was
        structural, so no repair could ever have resolved it."""
        self.assertFalse(self._sigs("Automated AWS ETL pipelines with Glue and S3"))
        self.assertFalse(self._sigs("Provisioned EC2 instances"))

    def test_identifier_guard_does_not_swallow_real_metrics(self):
        """The guard keys on a letter immediately before the digit, so
        ordinary measurements -- which never are -- still register."""
        self.assertTrue(self._sigs("Cut costs by $3M"))
        self.assertTrue(self._sigs("Improved accuracy 15%"))
        self.assertTrue(self._sigs("Managed a 2,932-account portfolio"))

    def test_small_bare_integers_still_need_a_matching_context_word(self):
        self.assertFalse(
            self._sigs("Led a 10-person team")
            & self._sigs("Ranked Top 10 Performer company-wide")
        )

    def test_a_four_digit_year_is_not_treated_as_a_distinctive_figure(self):
        # 2024 clears the 4-digit bar but is a date, not a metric -- two
        # bullets mentioning the same year aren't citing the same figure.
        self.assertFalse(
            self._sigs("Launched in 2024 across Europe")
            & self._sigs("Retired in 2024 after the merger")
        )

    def test_percentages_still_need_a_matching_context_word(self):
        self.assertFalse(
            self._sigs("Hit 22% reply rates")
            & self._sigs("Beat the 22% industry average")
        )


class TestStrictSemanticSkillGuardrail(unittest.TestCase):

    def test_allows_verified_skills_and_general_terms(self):
        resume = {
            "SKILLS": [
                "**Lifecycle & Campaign:** Outreach.io, Salesforce CRM, Segmentation",
                "**Marketing Enablement:** Onboarding, Coaching, Process Mapping",
            ]
        }
        violations = validate_resume._check_hallucinated_tools(resume)
        self.assertEqual(violations, [])

    def test_flags_hallucinated_skills(self):
        resume = {"SKILLS": ["**Technical Stack:** Kubernetes, React, Outreach.io"]}
        violations = validate_resume._check_hallucinated_tools(resume)
        # Kubernetes and React are definitely hallucinated, but Outreach.io is fine
        self.assertTrue(any("kubernetes" in v.lower() for v in violations))
        self.assertTrue(any("react" in v.lower() for v in violations))
        self.assertFalse(any("outreach" in v.lower() for v in violations))

    def test_reads_from_the_active_profiles_own_kb_dir_not_a_hardcoded_morgan_path(
        self,
    ):
        """F3: this used to call a function that never existed
        (profile_paths.get_kb_dir), so the except branch's hardcoded
        profiles/morgan/knowledge_base fallback fired unconditionally --
        for every profile, on every call. Proves the real profile_paths.
        kb_dir() is now actually used by patching it to a fixture
        directory for a *different* profile and confirming that fixture's
        verified_tools.json is what gets read, not morgan's real one."""
        import json
        import os
        import tempfile
        from unittest.mock import patch

        with tempfile.TemporaryDirectory() as tmpdir:
            with open(
                os.path.join(tmpdir, "verified_tools.json"), "w", encoding="utf-8"
            ) as f:
                json.dump(
                    {"tools": [{"name": "TotallyFakeToolXYZ", "category": ""}]}, f
                )

            with patch("profile_paths.kb_dir", return_value=tmpdir):
                resume = {"SKILLS": ["**Stack:** TotallyFakeToolXYZ"]}
                violations = validate_resume._check_hallucinated_tools(resume)
                # If this were still silently reading morgan's real kb_dir,
                # "TotallyFakeToolXYZ" (present only in this fixture) would
                # be flagged as hallucinated. It shouldn't be, since the
                # patched kb_dir says it's verified.
                self.assertFalse(any("TotallyFakeToolXYZ" in v for v in violations))

    def test_flags_demographic_and_age_bias(self):
        # 1. Graduation year > 15 years old
        resume_old_edu = {
            "EDUCATION": [
                {
                    "institution": "University of California",
                    "degree": "B.A. English",
                    "year": "2005",
                }
            ]
        }
        violations = validate_resume._check_demographic_and_age_bias(resume_old_edu)
        self.assertTrue(
            any("2005" in v and "Demographic/Age Bias Warning" in v for v in violations)
        )

        # 2. Marital status / non-inclusive wording
        resume_bias_text = {
            "SUMMARY_TEXT": "Married rockstar developer with 10 years experience logged 2000 man-hours.",
            "SKILLS": ["Master/Slave database clustering"],
            "EXPERIENCE": [],
        }
        violations_text = validate_resume._check_demographic_and_age_bias(
            resume_bias_text
        )
        self.assertTrue(any("Marital status" in v for v in violations_text))
        self.assertTrue(any("rockstar" in v for v in violations_text))
        self.assertTrue(any("man-hours" in v for v in violations_text))
        self.assertTrue(any("master/slave" in v for v in violations_text))

    def test_flags_excessive_keyword_density_ceiling(self):
        # Repeat word "optimization" enough times to exceed 3.5% of total words
        spammed_bullets = [
            "Drove optimization across optimization pipelines with optimization frameworks for optimization scale and optimization telemetry."
        ] * 3
        resume = {
            "SUMMARY_TEXT": "Senior product strategist with 8 years experience leading optimization.",
            "SKILLS": ["**Focus:** Optimization Strategy"],
            "EXPERIENCE": [
                {
                    "title": "Lead",
                    "company": "Co",
                    "period": "2020-2024",
                    "achievements": spammed_bullets,
                }
            ],
        }
        violations = validate_resume._check_keyword_density_ceiling(
            resume, max_density=0.035
        )
        self.assertTrue(
            any(
                "ATS Keyword Density Ceiling" in v and "optimization" in v
                for v in violations
            )
        )

    def test_summary_4element_formula_validation(self):
        # Complete summary
        good_summary = {
            "SUMMARY_TEXT": "<strong>Senior Lifecycle Marketer with 8 years in CRM and email automation.</strong> Scaled customer outreach to 50,000+ monthly contacts."
        }
        self.assertEqual(
            validate_resume._check_summary_4element_formula(good_summary), []
        )

    def test_flags_cross_section_redundancy(self):
        repeated_phrase = (
            "recovered three million dollars in dormant pipeline through workflows"
        )
        resume = {
            "SUMMARY_TEXT": f"<strong>Senior Lifecycle Marketer with 8 years in CRM.</strong> Scaled systems and {repeated_phrase}.",
            "EXPERIENCE": [
                {
                    "title": "Manager",
                    "company": "Acme",
                    "period": "2020-2024",
                    "achievements": [
                        f"Spearheaded CRM audit and {repeated_phrase} across territories",
                    ],
                }
            ],
        }
        violations = validate_resume._check_cross_section_redundancy(
            resume, min_gram_words=5
        )
        self.assertTrue(
            any(
                "Cross-Section Redundancy Warning" in v and "dormant pipeline" in v
                for v in violations
            )
        )


if __name__ == "__main__":
    unittest.main()

    def test_flags_surviving_date_anchor_as_soft_violation(self):
        # Final backstop: whatever path a school-year/calendar anchor takes
        # to the resume, the validator nudges it out ("the role's period
        # line already dates the work").
        resume = _valid_resume()
        resume["EXPERIENCE"][0]["achievements"] = [
            "Achieved a 38% reply rate across 751 contacts in the 2020-21 school year",
        ]
        violations = validate_resume.validate(resume, STYLE_RULES)
        self.assertTrue(any("Date anchor" in v for v in violations))

    def test_timeless_achievement_passes_the_date_anchor_check(self):
        resume = _valid_resume()
        resume["EXPERIENCE"][0]["achievements"] = [
            "Achieved a 38% reply rate across 751 district contacts",
        ]
        violations = validate_resume.validate(resume, STYLE_RULES)
        self.assertFalse(any("Date anchor" in v for v in violations))
