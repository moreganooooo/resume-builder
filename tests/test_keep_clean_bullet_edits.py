import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))

import orchestrator  # noqa: E402


def _resume(*bullets):
    return {"EXPERIENCE": [{"title": "Analyst", "achievements": list(bullets)}]}


class TestKeepCleanBulletEdits(unittest.TestCase):
    def test_keeps_clean_edits_and_reverts_the_violating_one(self):
        original = _resume("long one", "long two", "long three")
        edited = _resume("short one", "BAD two", "short three")

        def check(data):
            return [
                b for b in data["EXPERIENCE"][0]["achievements"] if b.startswith("BAD")
            ]

        result = orchestrator._keep_clean_bullet_edits(original, edited, check)
        self.assertEqual(
            result["EXPERIENCE"][0]["achievements"],
            ["short one", "long two", "short three"],
        )
        self.assertEqual(original["EXPERIENCE"][0]["achievements"][0], "long one")

    def test_ignores_a_job_whose_bullet_count_changed(self):
        original = _resume("a", "b")
        edited = _resume("x")
        result = orchestrator._keep_clean_bullet_edits(original, edited, lambda d: [])
        self.assertEqual(result, original)


if __name__ == "__main__":
    unittest.main()
