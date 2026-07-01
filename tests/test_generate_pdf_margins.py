import os
import re
import unittest

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PDF_SCRIPT = os.path.join(PROJECT_ROOT, "scripts", "generate-pdf.mjs")


class TestPdfMargins(unittest.TestCase):

    def test_pdf_margins_are_half_inch_per_design_spec(self):
        with open(PDF_SCRIPT, "r", encoding="utf-8") as f:
            source = f.read()
        margin_block_match = re.search(r"margin:\s*\{([^}]+)\}", source)
        self.assertIsNotNone(margin_block_match, "Could not find margin: {...} block in generate-pdf.mjs")
        margin_block = margin_block_match.group(1)
        self.assertNotIn("0.6in", margin_block)
        for side in ("top", "right", "bottom", "left"):
            self.assertIn(f"{side}: '0.5in'", margin_block)


if __name__ == "__main__":
    unittest.main()
