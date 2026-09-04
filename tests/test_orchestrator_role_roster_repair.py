"""Deterministic Role Roster repair -- see orchestrator._parse_cv_role_metadata /
_lookup_role_metadata / repair_violations_surgically's "5. Deterministic Role
Roster Repair" block.

Covers a real failure mode observed live: the LLM fix loop's "MISSING
EMPLOYERS -- ADD THESE ENTRIES" retry restated the instruction on every
attempt but never restored one specific missing company across all 4
attempts, failing the whole build (Role roster violations are fatal).
Uses synthetic cv.md text and a synthetic roster throughout -- not the
active profile's real employers -- per tests/test_no_operator_identity.py's
"use synthetic data, not the operator's own history" rule.
"""

import os
import sys
import unittest

SCRIPTS_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts"
)
sys.path.insert(0, SCRIPTS_DIR)

import orchestrator  # noqa: E402
import validate_resume  # noqa: E402

FAKE_CV = """## Work Experience

### Senior Widget Engineer
**Acme Robotics** · Remote · Jan 2020 – Present

- Did widget things.

---

### Widget Designer & Fabricator
**Ferrous & Co, LLC** · Topeka, KS · Mar 2015 – Dec 2019

- Designed widgets.

---

### Junior Widget Intern
**Bramblewood Studio (Now Bramblewood Creative)** · Wichita, KS · Jun–Aug 2014

- Interned on widgets.
"""


class TestParseCvRoleMetadata(unittest.TestCase):

    def setUp(self):
        self.meta = orchestrator._parse_cv_role_metadata(FAKE_CV)

    def test_parses_title_period_location_per_company(self):
        self.assertEqual(
            self.meta["acme robotics"],
            {
                "title": "Senior Widget Engineer",
                "location": "Remote",
                "period": "Jan 2020 – Present",
            },
        )

    def test_strips_rename_parenthetical_from_company_key(self):
        self.assertIn("bramblewood studio", self.meta)
        self.assertNotIn("bramblewood studio (now bramblewood creative)", self.meta)

    def test_single_field_after_company_with_digit_is_period(self):
        # "Jun 2015 – Oct 2015"-style single-field header
        meta = orchestrator._parse_cv_role_metadata(
            "### Some Title\n**Some Co** · Jun 2015 – Oct 2015\n"
        )
        self.assertEqual(meta["some co"]["period"], "Jun 2015 – Oct 2015")
        self.assertEqual(meta["some co"]["location"], "")

    def test_empty_cv_text_returns_empty_dict(self):
        self.assertEqual(orchestrator._parse_cv_role_metadata(""), {})


class TestLookupRoleMetadata(unittest.TestCase):

    def setUp(self):
        self.meta = orchestrator._parse_cv_role_metadata(FAKE_CV)

    def test_exact_match(self):
        self.assertEqual(
            orchestrator._lookup_role_metadata(self.meta, "Acme Robotics")["title"],
            "Senior Widget Engineer",
        )

    def test_loose_punctuation_mismatch_still_matches(self):
        # cv.md says "Ferrous & Co, LLC"; a caller spelling it "Ferrous & Co
        # LLC" (no comma) must still resolve -- matching must survive
        # punctuation drift the way validate_resume's own roster check does.
        result = orchestrator._lookup_role_metadata(self.meta, "Ferrous & Co LLC")
        self.assertEqual(result["title"], "Widget Designer & Fabricator")

    def test_unknown_company_returns_empty_dict(self):
        self.assertEqual(
            orchestrator._lookup_role_metadata(self.meta, "Nonexistent Corp"), {}
        )


class TestRepairViolationsSurgicallyRosterRepair(unittest.TestCase):

    def setUp(self):
        self.role_metadata = orchestrator._parse_cv_role_metadata(FAKE_CV)
        self.role_roster = ["Acme Robotics", "Ferrous & Co, LLC", "Bramblewood Studio"]
        self.role_bullet_minimums = {"Ferrous & Co, LLC": 2, "Bramblewood Studio": 2}
        self.role_bullet_maximums = {"Ferrous & Co, LLC": 3}
        self.bullet_tuples = [
            ("Did widget things.", "Acme Robotics", "eng"),
            ("Designed a widget.", "Ferrous & Co, LLC", "design"),
            ("Fabricated a widget.", "Ferrous & Co, LLC", "design"),
            ("Sourced widget materials.", "Ferrous & Co, LLC", "design"),
        ]

    def _base_resume(self):
        return {
            "EXPERIENCE": [
                {
                    "title": "Senior Widget Engineer",
                    "company": "Acme Robotics",
                    "period": "Jan 2020 - Present",
                    "location": "Remote",
                    "achievements": ["Did widget things."],
                    "career_note": "",
                }
            ],
            "SKILLS": [],
        }

    def test_missing_company_with_bullets_is_added_with_real_metadata(self):
        resume_data = self._base_resume()
        violations = validate_resume._check_role_roster(resume_data, self.role_roster)
        self.assertTrue(any("Ferrous" in v for v in violations))

        fixed, remaining = orchestrator.repair_violations_surgically(
            resume_data,
            violations,
            {},
            self.role_roster,
            self.role_bullet_minimums,
            self.bullet_tuples,
            role_bullet_maximums=self.role_bullet_maximums,
            role_metadata=self.role_metadata,
        )

        companies = {job["company"] for job in fixed["EXPERIENCE"]}
        self.assertIn("Ferrous & Co, LLC", companies)
        added = next(
            job for job in fixed["EXPERIENCE"] if job["company"] == "Ferrous & Co, LLC"
        )
        self.assertEqual(added["title"], "Widget Designer & Fabricator")
        self.assertEqual(added["period"], "Mar 2015 – Dec 2019")
        self.assertEqual(added["location"], "Topeka, KS")
        self.assertEqual(len(added["achievements"]), 3)  # capped at max_bullets=3
        self.assertFalse(any("Ferrous" in v for v in remaining))

    def test_missing_company_with_no_bullets_is_left_for_llm_loop(self):
        # Bramblewood Studio is in role_roster but has no bullet_tuples entry --
        # the deterministic repair must not fabricate an empty/stub entry, and
        # must leave its violation in place for the existing LLM retry path.
        resume_data = self._base_resume()
        violations = validate_resume._check_role_roster(resume_data, self.role_roster)

        fixed, remaining = orchestrator.repair_violations_surgically(
            resume_data,
            violations,
            {},
            self.role_roster,
            self.role_bullet_minimums,
            self.bullet_tuples,
            role_bullet_maximums=self.role_bullet_maximums,
            role_metadata=self.role_metadata,
        )

        companies = {job["company"] for job in fixed["EXPERIENCE"]}
        self.assertNotIn("Bramblewood Studio", companies)
        self.assertTrue(any("Bramblewood" in v for v in remaining))

    def test_added_entries_are_reordered_to_match_role_roster(self):
        resume_data = self._base_resume()
        violations = validate_resume._check_role_roster(resume_data, self.role_roster)

        fixed, _ = orchestrator.repair_violations_surgically(
            resume_data,
            violations,
            {},
            self.role_roster,
            self.role_bullet_minimums,
            self.bullet_tuples,
            role_bullet_maximums=self.role_bullet_maximums,
            role_metadata=self.role_metadata,
        )
        companies_in_order = [job["company"] for job in fixed["EXPERIENCE"]]
        # Acme Robotics must precede Ferrous & Co, LLC (role_roster order).
        self.assertLess(
            companies_in_order.index("Acme Robotics"),
            companies_in_order.index("Ferrous & Co, LLC"),
        )

    def test_no_role_metadata_still_adds_entry_with_blank_fields(self):
        # role_metadata is best-effort (cv.md may be unreadable) -- the
        # repair must still add the entry rather than skip it outright.
        resume_data = self._base_resume()
        violations = validate_resume._check_role_roster(resume_data, self.role_roster)

        fixed, _remaining = orchestrator.repair_violations_surgically(
            resume_data,
            violations,
            {},
            self.role_roster,
            self.role_bullet_minimums,
            self.bullet_tuples,
            role_bullet_maximums=self.role_bullet_maximums,
            role_metadata=None,
        )
        added = next(
            job for job in fixed["EXPERIENCE"] if job["company"] == "Ferrous & Co, LLC"
        )
        self.assertEqual(added["title"], "")
        self.assertEqual(added["period"], "")


if __name__ == "__main__":
    unittest.main()
