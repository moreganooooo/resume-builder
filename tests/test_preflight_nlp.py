import os
import sys
import unittest

SCRIPTS_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts"
)
if SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, SCRIPTS_DIR)

import preflight_nlp


class TestPreflightNlp(unittest.TestCase):
    def test_sanitize_text_encoding(self):
        raw = "It\u2019s a \u201cgreat\u201d project\u2014shipped on time."
        cleaned = preflight_nlp.sanitize_text_encoding(raw)
        self.assertEqual(cleaned, 'It\'s a "great" project -- shipped on time.')

    def test_detect_unfilled_placeholders(self):
        text = "I am excited to apply for [Role Name] at [Company Name]. TODO: add metrics."
        placeholders = preflight_nlp.detect_unfilled_placeholders(text)
        self.assertIn("[Role Name]", placeholders)
        self.assertIn("[Company Name]", placeholders)
        self.assertIn("TODO", placeholders)

    def test_validate_preflight_nlp_pass_and_fail(self):
        valid_text = "Shipped distributed consensus engine cutting latency 40%."
        passed, issues = preflight_nlp.validate_preflight_nlp(valid_text)
        self.assertTrue(passed)
        self.assertEqual(len(issues), 0)

        invalid_text = "I worked at [Insert Company] on TODO items."
        passed, issues = preflight_nlp.validate_preflight_nlp(invalid_text)
        self.assertFalse(passed)
        self.assertGreaterEqual(len(issues), 1)


if __name__ == "__main__":
    unittest.main()
