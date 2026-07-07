import os
import sys
import unittest

SCRIPTS_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts")
sys.path.insert(0, SCRIPTS_DIR)

import orchestrator  # noqa: E402


class TestParsePdfResult(unittest.TestCase):

    def test_extracts_page_count_and_size(self):
        stdout = (
            "📄 Input:  /x/y.html\n"
            "📁 Output: /x/y.pdf\n"
            "📏 Format: LETTER\n"
            "✅ PDF generated: /x/y.pdf\n"
            "📊 Pages: 3\n"
            "📦 Size: 69.2 KB\n"
        )
        page_count, size_str = orchestrator._parse_pdf_result(stdout)
        self.assertEqual(page_count, 3)
        self.assertEqual(size_str, "69.2 KB")

    def test_missing_pages_line_returns_none(self):
        page_count, size_str = orchestrator._parse_pdf_result("no pages line here\n📦 Size: 10.0 KB")
        self.assertIsNone(page_count)
        self.assertEqual(size_str, "10.0 KB")

    def test_missing_size_line_returns_unknown_size(self):
        page_count, size_str = orchestrator._parse_pdf_result("📊 Pages: 2\nno size line here")
        self.assertEqual(page_count, 2)
        self.assertEqual(size_str, "unknown size")


if __name__ == "__main__":
    unittest.main()
