import csv
import os
import sys
import unittest

SCRIPTS_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts"
)
sys.path.insert(0, SCRIPTS_DIR)

import trim_detective_findings  # noqa: E402


class TestTrimDetectiveFindings(unittest.TestCase):

    def setUp(self):
        self.tmp_csv = os.path.join(
            os.path.dirname(__file__), "_tmp_detective_findings.csv"
        )
        with open(self.tmp_csv, "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(
                f,
                fieldnames=[
                    "Finding ID",
                    "Source File",
                    "URL",
                    "Finding Type",
                    "Persona / Context",
                    "Best Details",
                    "What This Proves",
                    "Portfolio Potential",
                    "Resume Potential",
                    "Confidence",
                    "Use Caveat",
                    "Reviewed",
                    "Next Follow-Up",
                    "Notes",
                ],
            )
            w.writeheader()
            w.writerow(
                {
                    "Finding ID": "DF-0001",
                    "Source File": "notes.docx",
                    "URL": "https://x",
                    "Finding Type": "Call notes",
                    "Persona / Context": "Title I school",
                    "Best Details": "Sold 45 books.",
                    "What This Proves": "Discovery skill",
                    "Portfolio Potential": "Good",
                    "Resume Potential": "Good",
                    "Confidence": "High",
                    "Use Caveat": "Led with TJ, not solo.",
                    "Reviewed": "2026-05-01",
                    "Next Follow-Up": "none",
                    "Notes": "internal note",
                }
            )

    def tearDown(self):
        if os.path.exists(self.tmp_csv):
            os.remove(self.tmp_csv)

    def test_only_keep_columns_present(self):
        rows = trim_detective_findings.trim_detective_findings(self.tmp_csv)
        self.assertEqual(len(rows), 1)
        self.assertEqual(
            set(rows[0].keys()),
            {"Source File", "Finding Type", "Best Details", "Confidence", "Use Caveat"},
        )

    def test_dropped_column_data_does_not_leak(self):
        rows = trim_detective_findings.trim_detective_findings(self.tmp_csv)
        values = list(rows[0].values())
        self.assertNotIn("https://x", values)
        self.assertNotIn("internal note", values)

    def test_kept_values_are_correct(self):
        rows = trim_detective_findings.trim_detective_findings(self.tmp_csv)
        self.assertEqual(rows[0]["Source File"], "notes.docx")
        self.assertEqual(rows[0]["Use Caveat"], "Led with TJ, not solo.")

    def test_row_count_preserved(self):
        rows = trim_detective_findings.trim_detective_findings(self.tmp_csv)
        self.assertEqual(len(rows), 1)


if __name__ == "__main__":
    unittest.main()
