import csv
import os
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))

import answer_library  # noqa: E402


class TestAnswerLibrary(unittest.TestCase):
    def test_append_preserves_header_and_deduplicates(self):
        with tempfile.TemporaryDirectory() as tmp:
            with patch.object(answer_library.profile_paths, "kb_dir", return_value=tmp):
                self.assertTrue(
                    answer_library.add_to_library("Why?", "Because.", "Role", "Acme")
                )
                self.assertFalse(
                    answer_library.add_to_library("Why?", "Because.", "Role", "Acme")
                )
            with open(
                os.path.join(tmp, "application-answers-index.csv"), newline=""
            ) as handle:
                rows = list(csv.DictReader(handle))
            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0]["Answer Length"], "1")


if __name__ == "__main__":
    unittest.main()
