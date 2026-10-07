import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))
import orchestrator  # noqa: E402

# Newest first, the order a profile's roles: list must be in. The fixer sorts
# by list position only, so a roster that is out of date order yields a resume
# that is too (USitek 07/2015 ran above Inside Sales 10/2015 until 2026-10-07).
ROSTER = [
    "Treering Yearbooks",
    "Inside Sales Team",
    "USitek",
    "DeJoy, Knauff & Blood",
    "OfficeTeam, Adecco, Greendox",
    "KU Payroll Office",
]


class ExperienceOrderTests(unittest.TestCase):
    def test_shuffled_entries_follow_roster(self):
        names = [
            "KU Payroll Office",
            "USitek",
            "OfficeTeam, Adecco, Greendox",
            "Treering Yearbooks",
            "Inside Sales Team (Now Alleyoop)",
            "DeJoy, Knauff & Blood",
        ]
        data = {"EXPERIENCE": [{"company": n} for n in names]}
        out, changed = orchestrator.auto_fix_experience_order(data, ROSTER)
        self.assertTrue(changed)
        self.assertEqual(
            [e["company"] for e in out["EXPERIENCE"]],
            [
                "Treering Yearbooks",
                "Inside Sales Team (Now Alleyoop)",
                "USitek",
                "DeJoy, Knauff & Blood",
                "OfficeTeam, Adecco, Greendox",
                "KU Payroll Office",
            ],
        )


if __name__ == "__main__":
    unittest.main()
