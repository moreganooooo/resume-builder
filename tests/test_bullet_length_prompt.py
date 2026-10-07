import os
import unittest

import yaml

ROOT = os.path.join(os.path.dirname(__file__), "..", "resume-engine")


def _prompt() -> str:
    with open(os.path.join(ROOT, "prompts", "tailor_resume.md"), encoding="utf-8") as f:
        return f.read()


class BulletLengthPromptTests(unittest.TestCase):
    """The 70/30 one-liner mix once read as a quota: the model cut 150-230 char
    clerical bullets to <=99 chars and dropped their result clauses."""

    def test_prompt_preserves_bullets_within_two_liner_limit(self):
        text = _prompt()
        self.assertIn("stays WHOLE", text)
        self.assertIn("within 220 chars", text)
        self.assertIn("never cut its result/outcome clause", text)

    def test_prompt_does_not_present_mix_as_quota(self):
        text = _prompt()
        self.assertIn("not a quota to hit", text)
        self.assertNotIn("- ~70% one-liners, ~30% two-liners;", text)

    def test_limits_unchanged(self):
        with open(
            os.path.join(ROOT, "rules", "style_rules.yaml"), encoding="utf-8"
        ) as f:
            bs = yaml.safe_load(f)["bullet_structure"]
        self.assertEqual(bs["one_liner_max_chars"], 108)
        self.assertEqual(bs["two_liner_max_chars"], 220)
        self.assertIn("not a quota", bs["mix"])


if __name__ == "__main__":
    unittest.main()
