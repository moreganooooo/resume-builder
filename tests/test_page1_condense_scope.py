import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))

import orchestrator  # noqa: E402


def _resume(*jobs):
    return {"EXPERIENCE": [{"company": c, "achievements": list(b)} for c, b in jobs]}


class TestMergeCondensedBullets(unittest.TestCase):
    def test_only_targeted_bullets_change(self):
        original = _resume(("Harbor Books", ["long target", "keep me"]))
        condensed = _resume(("Harbor Books", ["short", "drifted wording"]))
        merged = orchestrator._merge_condensed_bullets(
            original, condensed, {"long target"}
        )
        self.assertEqual(merged["EXPERIENCE"][0]["achievements"], ["short", "keep me"])
        self.assertEqual(original["EXPERIENCE"][0]["achievements"][0], "long target")

    def test_misaligned_job_is_left_alone(self):
        original = _resume(("Harbor Books", ["long target", "b"]))
        condensed = _resume(("Harbor Books", ["short"]))
        merged = orchestrator._merge_condensed_bullets(
            original, condensed, {"long target"}
        )
        self.assertEqual(merged, original)


class TestNewlyIntroduced(unittest.TestCase):
    def test_preexisting_violations_do_not_count(self):
        self.assertEqual(
            orchestrator._newly_introduced(["old widow", "new widow"], ["old widow"]),
            ["new widow"],
        )


class TestCondenseTargets(unittest.TestCase):
    def test_longest_page1_bullets_only(self):
        resume = _resume(
            ("Harbor Books", ["aa", "aaaa"]), ("Corner Bakery", ["a" * 50])
        )
        profile = {
            "roles": [
                {"name": "Harbor Books", "page": 1},
                {"name": "Corner Bakery", "page": 2},
            ]
        }
        targets = orchestrator._page1_condense_targets(resume, profile)
        self.assertEqual([b for _, _, b in targets], ["aaaa", "aa"])


if __name__ == "__main__":
    unittest.main()
