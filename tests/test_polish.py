import os
import sys
import unittest

SCRIPTS_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts")
sys.path.insert(0, SCRIPTS_DIR)

import polish  # noqa: E402


class TestDetectDocType(unittest.TestCase):

    def test_resume_suffix(self):
        self.assertEqual(polish.detect_doc_type("output/json/Foo_Bar_Resume.json"), "resume")

    def test_coverletter_suffix(self):
        self.assertEqual(polish.detect_doc_type("output/json/Foo_Bar_CoverLetter.json"), "coverletter")

    def test_unrecognized_suffix_returns_none(self):
        self.assertIsNone(polish.detect_doc_type("output/json/Foo_Bar.json"))


class TestStemFromJsonPath(unittest.TestCase):

    def test_resume_stem(self):
        stem = polish.stem_from_json_path(
            "output/json/MorganEscott_Title_Company_Resume.json", "resume",
        )
        self.assertEqual(stem, "MorganEscott_Title_Company")

    def test_coverletter_stem(self):
        stem = polish.stem_from_json_path(
            "output/json/MorganEscott_Title_Company_CoverLetter.json", "coverletter",
        )
        self.assertEqual(stem, "MorganEscott_Title_Company")


if __name__ == "__main__":
    unittest.main()
