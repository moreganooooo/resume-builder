"""A must-fit role that condensing cannot lift gets room from one bullet of
the profile's named trim role, never below that role's minimum."""

import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))

import orchestrator  # noqa: E402

PROFILE = {
    "page1_overflow_trim_role": "Harbor Books",
    "roles": [{"name": "Harbor Books", "min_bullets": 2}],
    "protected_bullets": ["Founded the reading club"],
}


def _resume(bullets):
    return {"EXPERIENCE": [{"company": "Harbor Books", "achievements": list(bullets)}]}


class TestPage1OverflowTrim(unittest.TestCase):
    def test_drops_a_metric_free_bullet_before_a_longer_metric_one(self):
        resume = _resume(
            [
                "Grew event attendance 40% across twelve months of author readings and signings",
                "Reorganized the stockroom",
                "Wrote staff picks shelf cards for new releases",
            ]
        )
        new, removed = orchestrator._page1_overflow_trim(resume, PROFILE)
        self.assertEqual(removed, "Wrote staff picks shelf cards for new releases")
        self.assertEqual(len(new["EXPERIENCE"][0]["achievements"]), 2)
        self.assertEqual(len(resume["EXPERIENCE"][0]["achievements"]), 3)

    def test_never_goes_below_min_bullets(self):
        self.assertIsNone(
            orchestrator._page1_overflow_trim(_resume(["a", "b"]), PROFILE)
        )

    def test_never_drops_a_protected_bullet(self):
        resume = _resume(
            ["Founded the reading club for teens", "Sold 30 books", "Ran 12 events"]
        )
        _, removed = orchestrator._page1_overflow_trim(resume, PROFILE)
        self.assertNotIn("reading club", removed)

    def test_inert_without_the_setting(self):
        self.assertIsNone(
            orchestrator._page1_overflow_trim(_resume(["a", "b", "c"]), {"roles": []})
        )


if __name__ == "__main__":
    unittest.main()
