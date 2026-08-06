import os
import sys
import unittest
from unittest.mock import MagicMock, patch

SCRIPTS_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts")
sys.path.insert(0, SCRIPTS_DIR)

import orchestrator  # noqa: E402


class TestParsePdfResult(unittest.TestCase):

    @patch("orchestrator.PdfReader")
    def test_extracts_page_count_and_size(self, mock_pdf_reader):
        mock_pdf_reader.return_value.pages = [MagicMock()] * 3
        stdout = (
            "📄 Input:  /x/y.html\n"
            "📁 Output: /x/y.pdf\n"
            "📏 Format: LETTER\n"
            "✅ PDF generated: /x/y.pdf\n"
            "📦 Size: 69.2 KB\n"
        )
        page_count, size_str = orchestrator._parse_pdf_result(stdout, "/x/y.pdf")
        self.assertEqual(page_count, 3)
        self.assertEqual(size_str, "69.2 KB")

    @patch("orchestrator.PdfReader", side_effect=Exception("not a real PDF"))
    def test_unreadable_pdf_returns_none(self, mock_pdf_reader):
        page_count, size_str = orchestrator._parse_pdf_result("📦 Size: 10.0 KB", "/x/y.pdf")
        self.assertIsNone(page_count)
        self.assertEqual(size_str, "10.0 KB")

    @patch("orchestrator.PdfReader")
    def test_missing_size_line_returns_unknown_size(self, mock_pdf_reader):
        mock_pdf_reader.return_value.pages = [MagicMock()] * 2
        page_count, size_str = orchestrator._parse_pdf_result("no size line here", "/x/y.pdf")
        self.assertEqual(page_count, 2)
        self.assertEqual(size_str, "unknown size")


class TestSummarizeKeywords(unittest.TestCase):

    def test_summarizes_three_categories(self):
        result = orchestrator._summarize_keywords({
            "tools": ["LinkedIn", "Figma", "Adobe Creative Cloud"],
            "hard_skills": ["A", "B", "C", "D", "E", "F", "G", "H"],
            "core_functions": ["X", "Y", "Z"],
        })
        self.assertEqual(result, "3 tools, 8 hard skills, 3 core functions")

    def test_omits_empty_categories(self):
        result = orchestrator._summarize_keywords({
            "tools": ["LinkedIn"],
            "hard_skills": [],
            "core_functions": ["X"],
        })
        self.assertEqual(result, "1 tools, 1 core functions")

    def test_all_empty_returns_none_found(self):
        result = orchestrator._summarize_keywords({"tools": [], "hard_skills": [], "core_functions": []})
        self.assertEqual(result, "none found")


if __name__ == "__main__":
    unittest.main()
