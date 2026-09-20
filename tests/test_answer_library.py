import csv
import os
import tempfile
import unittest
from unittest.mock import patch

from scripts import answer_library


class TestAnswerLibrary(unittest.TestCase):
    def test_append_preserves_header_and_deduplicates(self):
        with tempfile.TemporaryDirectory() as tmp:
            with patch.object(answer_library.profile_paths, "kb_dir", return_value=tmp):
                self.assertTrue(answer_library.add_to_library("Why?", "Because.", "Role", "Acme"))
                self.assertFalse(answer_library.add_to_library("Why?", "Because.", "Role", "Acme"))
            with open(os.path.join(tmp, "application-answers-index.csv"), newline="") as handle:
                rows = list(csv.DictReader(handle))
            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0]["Answer Length"], "1")


if __name__ == "__main__":
    unittest.main()
