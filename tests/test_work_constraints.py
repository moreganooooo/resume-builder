"""A profile's physical/phone limits (scan_filters.yml work_constraints:)
are judged deterministically, and the evaluator's blocker list no longer
disqualifies a role for being what it is (its title, over-qualification)."""

import json
import os
import sys
import tempfile
import unittest

import yaml

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))

import content_settings  # noqa: E402
import orchestrator  # noqa: E402
import work_constraints  # noqa: E402

LIMITS = {
    "no_prolonged_standing": True,
    "no_manual_labor": True,
    "max_lift_lbs": 25,
    "heavy_lift_lbs": 40,
    "lift_penalty": 0.3,
    "phone_heavy_penalty": 0.75,
    "onsite_stress_multiplier": 2.0,
}


def kinds(text, settings=None):
    if settings is None:
        settings = LIMITS
    return {(f["kind"], f["severity"]) for f in work_constraints.detect(text, settings)}


class TestDetect(unittest.TestCase):
    def test_inert_without_settings(self):
        self.assertEqual(work_constraints.detect("Must lift 80 pounds daily.", {}), [])
        self.assertFalse(work_constraints.is_enabled(None))

    def test_prolonged_standing_is_a_blocker(self):
        self.assertIn(
            ("standing", "blocker"), kinds("Ability to stand for long periods of time.")
        )
        self.assertIn(
            ("standing", "blocker"),
            kinds("You will be on your feet for the entire shift."),
        )

    def test_desk_sit_or_stand_is_not_standing(self):
        text = "Ability to sit and/or stand at a desk and work with a computer for extended periods of time."
        self.assertEqual(kinds(text), set())

    def test_any_sitting_option_voids_standing(self):
        self.assertEqual(
            kinds(
                "Employee will bend, walk, stand and may sit for long periods of time."
            ),
            set(),
        )

    def test_regular_lifting_is_not_softened_by_a_later_clause(self):
        text = "Regular lifting of up to 30 pounds; occasional heavier lifting with assistance."
        self.assertIn(("lifting", "blocker"), kinds(text))

    def test_event_only_standing_is_not_a_blocker(self):
        self.assertEqual(
            kinds("Must stand for an extended period of time during special events."),
            set(),
        )

    def test_think_on_your_feet_is_not_standing(self):
        self.assertEqual(kinds("You think on your feet and love a challenge."), set())

    def test_lifting_thresholds(self):
        self.assertEqual(kinds("Occasionally lift and carry up to 20 pounds."), set())
        self.assertIn(
            ("lifting", "blocker"), kinds("Must be able to lift up to 50 lbs.")
        )
        self.assertIn(
            ("lifting", "blocker"), kinds("Frequently lift boxes up to 30 pounds.")
        )
        self.assertIn(
            ("lifting", "penalty"),
            kinds("The employee must occasionally lift and/or move up to 35 pounds."),
        )

    def test_negated_lifting_is_ignored(self):
        self.assertEqual(kinds("No lifting over 50 lbs is required."), set())

    def test_truck_unloading_is_manual_labor(self):
        self.assertIn(
            ("manual_labor", "blocker"),
            kinds("Complete truck unloading and merchandise duties."),
        )

    def test_phone_heavy_is_a_penalty_routine_phones_are_not(self):
        self.assertIn(
            ("phone_heavy", "penalty"), kinds("Handle a high volume of inbound calls.")
        )
        self.assertEqual(kinds("Answer phones and greet visitors."), set())
        self.assertEqual(
            kinds("Questions? Contact our Global Call Center (GCC)."), set()
        )

    def test_escaped_newlines_bound_sentences(self):
        text = "Great team.\\nMust lift 50 lbs.\\nWe offer PTO."
        finding = work_constraints.detect(text, LIMITS)[0]
        self.assertEqual(finding["text"], "Must lift 50 lbs")


def _fours(*keys):
    return {k: 4 for k in keys}


# Mid-range subscores, so a penalty's effect is never hidden by the 0-5 clamp.
BASE_EVAL = {
    "fit_subscores": _fours(
        "functional_alignment",
        "north_star_alignment",
        "level_plausibility",
        "work_style_sustainability",
        "tools_process_overlap",
    ),
    "interview_odds_subscores": _fours(
        "title_continuity",
        "evidence_match",
        "domain_credibility",
        "recruiter_legibility",
        "narrative_burden",
        "funnel_friction",
    ),
    "practical_pursue_subscores": _fours(
        "remote_quality",
        "compensation_viability",
        "growth_value",
        "time_to_offer",
        "company_reputation",
        "cultural_signals",
        "posting_legitimacy_score",
    ),
    "recommendation": "Selective pursue",
    "why": "",
    "posting_age_days": 0,
}


def rescore(blockers=(), description=None, **kwargs):
    return orchestrator.rescore_evaluation_with_location(
        dict(BASE_EVAL, hard_blockers=list(blockers)),
        distance_miles=None,
        radius_miles=5.0,
        posting_age_days=0,
        description=description,
        **kwargs,
    )


class TestRescore(unittest.TestCase):
    def test_physical_blocker_forces_skip(self):
        ev = rescore(
            description="Must lift up to 50 pounds.", work_constraints_settings=LIMITS
        )
        self.assertEqual(ev["recommendation"], "Skip")
        self.assertEqual(ev["hard_blockers"][0]["category"], "physical_demands")

    def test_rescoring_twice_does_not_duplicate_the_blocker(self):
        once = rescore(
            description="Must lift up to 50 pounds.", work_constraints_settings=LIMITS
        )
        twice = orchestrator.rescore_evaluation_with_location(
            once,
            radius_miles=5.0,
            posting_age_days=0,
            description="Must lift up to 50 pounds.",
            work_constraints_settings=LIMITS,
        )
        self.assertEqual(len(twice["hard_blockers"]), 1)

    def test_no_settings_means_no_change(self):
        with_text = rescore(description="Must lift up to 50 pounds.")
        self.assertNotEqual(with_text["recommendation"], "Skip")

    def test_phone_penalty_lowers_the_composite(self):
        text = "Handle a high volume of inbound calls."
        plain = rescore(description=text)["composite_score"]
        limited = rescore(description=text, work_constraints_settings=LIMITS)[
            "composite_score"
        ]
        self.assertAlmostEqual(plain - limited, 0.75, places=2)

    def test_onsite_stress_counts_double(self):
        text = "Join our fast-paced environment and meet or exceed quotas."
        remote = rescore(
            description=text,
            work_constraints_settings=LIMITS,
            posting_workplace="remote",
        )
        onsite = rescore(
            description=text,
            work_constraints_settings=LIMITS,
            posting_workplace="onsite",
        )
        self.assertAlmostEqual(
            remote["composite_score"] - onsite["composite_score"], 0.5, places=2
        )

    def test_title_as_blocker_is_dropped(self):
        ev = rescore(
            [{"text": "Retail Sales Associate", "category": "other"}],
            job_title="Retail  sales associate",
        )
        self.assertNotEqual(ev["recommendation"], "Skip")
        self.assertEqual(ev["hard_blockers"], [])

    def test_over_qualified_in_any_category_is_dropped(self):
        ev = rescore(
            [
                {
                    "text": "Store associate",
                    "category": "other",
                    "direction": "over_qualified",
                }
            ]
        )
        self.assertNotEqual(ev["recommendation"], "Skip")

    def test_real_other_blocker_still_skips(self):
        ev = rescore(
            [{"text": "This position is unpaid", "category": "other"}],
            job_title="Intern",
        )
        self.assertEqual(ev["recommendation"], "Skip")


ROLES = {
    "situational_min_bullets": 2,
    "roles": {
        "Front Office Temp Work": {
            "bank_tag": "Temp",
            "trigger_keywords": ["receptionist", "office assistant"],
        },
    },
}


class TestSituationalTrackContext(unittest.TestCase):
    def test_title_match_adds_the_block(self):
        jd = json.dumps({"job_title": "Receptionist", "description": "Greet visitors."})
        block = orchestrator.build_situational_track_context(jd, ROLES)
        self.assertIn("SITUATIONAL TRACK", block)
        self.assertIn("Front Office Temp Work", block)

    def test_body_only_match_does_not(self):
        jd = json.dumps(
            {
                "job_title": "Marketing Manager",
                "description": "Work with our receptionist.",
            }
        )
        self.assertEqual(orchestrator.build_situational_track_context(jd, ROLES), "")

    def test_plain_text_jd_does_not(self):
        self.assertEqual(
            orchestrator.build_situational_track_context("Receptionist", ROLES), ""
        )


class TestSettingsReader(unittest.TestCase):
    def test_reads_known_keys_and_defaults_the_rest(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "scan_filters.yml")
            with open(path, "w") as f:
                yaml.safe_dump(
                    {"work_constraints": {"max_lift_lbs": 25, "bogus": 1}}, f
                )
            settings = content_settings.read_work_constraints(path)
        self.assertEqual(settings["max_lift_lbs"], 25)
        self.assertNotIn("bogus", settings)
        self.assertFalse(settings["no_prolonged_standing"])

    def test_missing_block_is_inert(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "scan_filters.yml")
            with open(path, "w") as f:
                yaml.safe_dump({"languages": ["en"]}, f)
            self.assertFalse(
                work_constraints.is_enabled(
                    content_settings.read_work_constraints(path)
                )
            )


if __name__ == "__main__":
    unittest.main()
