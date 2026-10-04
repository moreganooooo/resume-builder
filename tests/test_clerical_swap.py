import os
import sys
import unittest

sys.path.insert(
    0,
    os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts"
    ),
)

import situational_roles

ROLES_DATA = {
    "situational_min_bullets": 2,
    "roles": {},
    "clerical_swap": {
        "title_keywords": ["data entry", "receptionist", r"\bclerk\b"],
        "exclude_title_keywords": ["marketing"],
        "replaces": ["VML", "Callahan Creek"],
        "adds": ["USitek"],
    },
}


class DetectClericalSwapTests(unittest.TestCase):
    def test_clerical_title_triggers_swap(self):
        swap = situational_roles.detect_clerical_swap("Data Entry Clerk", ROLES_DATA)
        self.assertEqual(
            swap, {"replaces": ["VML", "Callahan Creek"], "adds": ["USitek"]}
        )

    def test_marketing_title_never_swaps(self):
        self.assertIsNone(
            situational_roles.detect_clerical_swap("Marketing Manager", ROLES_DATA)
        )

    def test_excluded_title_stays_marketing(self):
        self.assertIsNone(
            situational_roles.detect_clerical_swap(
                "Marketing Coordinator / Receptionist", ROLES_DATA
            )
        )

    def test_empty_title_or_config(self):
        self.assertIsNone(situational_roles.detect_clerical_swap("", ROLES_DATA))
        self.assertIsNone(
            situational_roles.detect_clerical_swap("Receptionist", {"roles": {}})
        )


class ApplyClericalSwapTests(unittest.TestCase):
    PROFILE = {
        "roles": [
            {"name": "VML"},
            {"name": "Callahan Creek"},
            {"name": "USitek"},
            {"name": "IST"},
        ]
    }

    def test_swap_drops_replaced_and_marks_added(self):
        out = situational_roles.apply_clerical_swap(
            self.PROFILE, {"replaces": ["VML", "Callahan Creek"], "adds": ["USitek"]}
        )
        self.assertEqual([r["name"] for r in out["roles"]], ["USitek", "IST"])
        self.assertTrue(out["roles"][0]["swap_active"])
        self.assertNotIn("swap_active", out["roles"][1])

    def test_none_swap_is_noop(self):
        self.assertIs(
            situational_roles.apply_clerical_swap(self.PROFILE, None), self.PROFILE
        )


class RosterHelpersTests(unittest.TestCase):
    def test_swap_active_role_joins_roster_and_floors(self):
        import orchestrator

        profile = {"roles": [{"name": "USitek", "min_bullets": 2, "swap_active": True}]}
        self.assertEqual(orchestrator._required_role_roster(profile), ["USitek"])
        self.assertEqual(
            orchestrator._required_role_bullet_minimums(profile), {"USitek": 2}
        )


class StripClericalTests(unittest.TestCase):
    def test_strip_removes_adds_only(self):
        profile = {"roles": [{"name": "VML"}, {"name": "USitek"}]}
        cfg = {"clerical_swap": {"adds": ["USitek"]}}
        out = situational_roles.strip_clerical_roles(profile, cfg)
        self.assertEqual([r["name"] for r in out["roles"]], ["VML"])

    def test_strip_noop_without_config(self):
        profile = {"roles": [{"name": "USitek"}]}
        self.assertIs(situational_roles.strip_clerical_roles(profile, {}), profile)


if __name__ == "__main__":
    unittest.main()
