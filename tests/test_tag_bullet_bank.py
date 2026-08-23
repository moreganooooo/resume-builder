import os
import sys
import unittest

SCRIPTS_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts"
)
sys.path.insert(0, SCRIPTS_DIR)
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import tag_bullet_bank  # noqa: E402


class TestTagBulletBankReadsProfileYaml(unittest.TestCase):
    """
    Regression tests: TAG_KEYWORDS/FALLBACK_TAG used to be hardcoded module
    constants here, duplicating (and, by 2026-07-17, already drifted from)
    orchestrator.py's/rewrite_bullets.py's own separate copies of the same
    marketing-specific taxonomy. Both tag_keywords() and fallback_tag() now
    read profile.yml's tags: instead -- these confirm a populated taxonomy
    still produces sane, unbroken tagging.

    Runs against tests/persona.py's taxonomy rather than whichever profile
    the operator happens to have configured: a freshly bootstrapped profile
    declares no tags at all, so these asserted nothing for anyone but the
    original author.
    """

    def setUp(self):
        import importlib

        import persona

        self._sandbox = persona.sandbox_profile()
        self._sandbox.__enter__()
        importlib.reload(tag_bullet_bank)

    def tearDown(self):
        import importlib

        self._sandbox.__exit__(None, None, None)
        importlib.reload(tag_bullet_bank)

    def test_assigns_a_confident_single_tag_on_a_unique_keyword_hit(self):
        tag_str, needs_review = tag_bullet_bank.assign_tags(
            "Owned Outreach.io as primary admin, led Salesforce integration and territory reporting."
        )
        self.assertEqual(tag_str, "[ops]")
        self.assertFalse(needs_review)

    def test_falls_back_to_the_catch_all_tag_when_nothing_matches(self):
        tag_str, needs_review = tag_bullet_bank.assign_tags(
            "Completely unrelated text with zero keyword hits."
        )
        self.assertEqual(tag_str, tag_bullet_bank.fallback_tag())
        self.assertFalse(needs_review)

    def test_fallback_tag_has_empty_keywords_in_the_real_taxonomy(self):
        keywords_by_tag = tag_bullet_bank.tag_keywords()
        self.assertEqual(keywords_by_tag[tag_bullet_bank.fallback_tag()], [])

    def test_score_bullet_accepts_an_explicit_taxonomy_without_reloading_profile_yaml(
        self,
    ):
        fake_taxonomy = {"[widgets]": ["widget", "gadget"], "[generalist]": []}
        scores = tag_bullet_bank.score_bullet(
            "Built and shipped a new widget pipeline.", fake_taxonomy
        )
        self.assertIn("[widgets]", scores)
        self.assertNotIn("[generalist]", scores)

    def test_fallback_tag_default_when_no_empty_keywords(self):
        from unittest.mock import patch

        with patch(
            "profile_paths.tags", return_value=[{"name": "tech", "keywords": ["code"]}]
        ):
            self.assertEqual(tag_bullet_bank.fallback_tag(), "[generalist]")

    def test_assign_tags_multi_tag_and_needs_review(self):
        from unittest.mock import patch

        # Taxonomy where shared words score < 1.0, unique words score 1.0
        tax = {
            "[alpha]": ["common", "unique_a"],
            "[beta]": ["common", "unique_b"],
            "[gamma]": [],
        }
        with patch("tag_bullet_bank.tag_keywords", return_value=tax):
            # Only common word matched -> scores < 1.0 -> needs_review=True
            tag_str, needs_review = tag_bullet_bank.assign_tags("Text with common word")
            self.assertTrue(needs_review)

            # Both unique_a and unique_b matched -> both score >= 1.0 -> dual tag!
            tag_str, needs_review = tag_bullet_bank.assign_tags(
                "unique_a and unique_b here"
            )
            self.assertEqual(tag_str, "[alpha][beta]")
            self.assertFalse(needs_review)


class TestMainFlow(unittest.TestCase):
    def test_main_cli_execution_and_error_handling(self):
        import csv
        import tempfile
        from unittest.mock import patch

        with tempfile.TemporaryDirectory() as tmpdir:
            input_csv = os.path.join(tmpdir, "bullets.csv")
            out_csv = os.path.join(tmpdir, "custom_tagged.csv")

            with open(input_csv, "w", newline="", encoding="utf-8") as f:
                w = csv.DictWriter(
                    f, fieldnames=["Role / Company", "Tags", "Bullet Point"]
                )
                w.writeheader()
                w.writerow(
                    {
                        "Role / Company": "Eng",
                        "Tags": "[existing]",
                        "Bullet Point": "Keep as is",
                    }
                )
                w.writerow(
                    {
                        "Role / Company": "Eng",
                        "Tags": "",
                        "Bullet Point": "Outreach admin",
                    }
                )
                w.writerow(
                    {"Role / Company": "Eng", "Tags": "", "Bullet Point": "Zero hits"}
                )

            with patch("sys.argv", ["tag_bullet_bank.py", input_csv, "-o", out_csv]):
                tag_bullet_bank.main()
                self.assertTrue(os.path.exists(out_csv))
                with open(out_csv, "r", encoding="utf-8") as f:
                    rows = list(csv.DictReader(f))
                    self.assertEqual(len(rows), 3)
                    self.assertEqual(rows[0]["Tags"], "[existing]")
                    self.assertTrue(rows[1]["Tags"])

    def test_main_cli_default_out_path_and_review_generation(self):
        import csv
        import tempfile
        from unittest.mock import patch

        with tempfile.TemporaryDirectory() as tmpdir:
            input_csv = os.path.join(tmpdir, "bullets.csv")
            with open(input_csv, "w", newline="", encoding="utf-8") as f:
                w = csv.DictWriter(
                    f, fieldnames=["Role / Company", "Tags", "Bullet Point"]
                )
                w.writeheader()
                w.writerow(
                    {
                        "Role / Company": "Eng",
                        "Tags": "",
                        "Bullet Point": "common keyword only",
                    }
                )

            tax = {"[a]": ["common"], "[b]": ["common"], "[c]": []}
            with (
                patch("tag_bullet_bank.tag_keywords", return_value=tax),
                patch("sys.argv", ["tag_bullet_bank.py", input_csv]),
            ):
                tag_bullet_bank.main()
                expected_out = os.path.join(tmpdir, "bullets-tagged.csv")
                review_out = os.path.join(tmpdir, "tag-review-needed.csv")
                self.assertTrue(os.path.exists(expected_out))
                self.assertTrue(os.path.exists(review_out))

    def test_main_cli_unexpected_columns(self):
        import csv
        import tempfile
        from unittest.mock import patch

        with tempfile.TemporaryDirectory() as tmpdir:
            input_csv = os.path.join(tmpdir, "extra_cols.csv")
            with open(input_csv, "w", newline="", encoding="utf-8") as f:
                w = csv.DictWriter(
                    f, fieldnames=["Role / Company", "Tags", "Bullet Point", "Extra"]
                )
                w.writeheader()
                w.writerow(
                    {
                        "Role / Company": "Eng",
                        "Tags": "",
                        "Bullet Point": "test",
                        "Extra": "bad",
                    }
                )

            with patch("sys.argv", ["tag_bullet_bank.py", input_csv]):
                with self.assertRaises(ValueError):
                    tag_bullet_bank.main()


if __name__ == "__main__":
    unittest.main()
