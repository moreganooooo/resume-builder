import os
import sys
import unittest

SCRIPTS_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts")
sys.path.insert(0, SCRIPTS_DIR)

from render_coverletter import render_coverletter  # noqa: E402


def _minimal_letter_data(**overrides):
    data = {
        "company_name": "Acme Corp",
        "greeting": "Dear Hiring Team,",
        "body_paragraphs": [
            "First paragraph, tying a JD requirement to real experience.",
            "Second paragraph, with another concrete example.",
        ],
        "sign_off": "Sincerely,",
    }
    data.update(overrides)
    return data


class TestRenderCoverLetter(unittest.TestCase):

    def setUp(self):
        self.out_path = os.path.join(os.path.dirname(__file__), "_tmp_coverletter.html")

    def tearDown(self):
        if os.path.exists(self.out_path):
            os.remove(self.out_path)

    def test_no_unfilled_tokens_remain(self):
        render_coverletter(_minimal_letter_data(), self.out_path)
        with open(self.out_path, "r", encoding="utf-8") as f:
            html = f.read()
        self.assertNotIn("{{", html)
        self.assertNotIn("}}", html)

    def test_recipient_block_contains_company_name(self):
        render_coverletter(_minimal_letter_data(company_name="Widget Co"), self.out_path)
        with open(self.out_path, "r", encoding="utf-8") as f:
            html = f.read()
        self.assertIn("Widget Co", html)
        self.assertIn('class="letter-address"', html)

    def test_body_paragraphs_each_wrapped_in_p_tag(self):
        render_coverletter(_minimal_letter_data(), self.out_path)
        with open(self.out_path, "r", encoding="utf-8") as f:
            html = f.read()
        self.assertIn("<p>First paragraph, tying a JD requirement to real experience.</p>", html)
        self.assertIn("<p>Second paragraph, with another concrete example.</p>", html)

    def test_contact_info_comes_from_fixed_content(self):
        render_coverletter(_minimal_letter_data(), self.out_path)
        with open(self.out_path, "r", encoding="utf-8") as f:
            html = f.read()
        self.assertIn("Morgan Escott", html)
        self.assertIn("escott.morgan@gmail.com", html)
