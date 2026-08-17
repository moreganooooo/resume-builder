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
        self.assertIsNotNone(
            margin_block_match, "Could not find margin: {...} block in generate-pdf.mjs"
        )
        margin_block = margin_block_match.group(1)
        self.assertNotIn("0.6in", margin_block)
        for side in ("top", "right", "bottom", "left"):
            self.assertIn(f"{side}: '0.5in'", margin_block)


class TestPdfFontEmbeddingLoadsViaRealFileNavigation(unittest.TestCase):
    """
    page.setContent() + baseURL resolves relative file:// URLs correctly but
    does NOT grant the page file:// fetch privileges, so every @font-face
    load silently failed ("Not allowed to load local resource") with no
    visible error -- verified directly against a real generated PDF (fonts
    fell back to Chromium's generic sans-serif instead of DM Sans).
    Only an actual navigation to a file:// URL grants those privileges, so
    generate-pdf.mjs must use page.goto('file://...') on a real temp file,
    not setContent(). This guards against silently reverting to setContent().
    """

    def test_uses_page_goto_file_url_not_set_content(self):
        with open(PDF_SCRIPT, "r", encoding="utf-8") as f:
            source = f.read()
        self.assertIn("page.goto(`file://", source)
        self.assertNotIn("await page.setContent(", source)


if __name__ == "__main__":
    unittest.main()
