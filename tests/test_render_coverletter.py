import os
import sys
import unittest
from unittest.mock import patch

SCRIPTS_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts"
)
sys.path.insert(0, SCRIPTS_DIR)
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import render_coverletter as render_coverletter_module  # noqa: E402
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
        # Rendered against whoever's profile happened to be active, so the
        # assertions below were about one real person's contact details.
        # A throwaway persona profile makes them about the RENDERER.
        import persona

        self._sandbox = persona.sandbox_profile()
        self._sandbox.__enter__()
        self.out_path = os.path.join(os.path.dirname(__file__), "_tmp_coverletter.html")

    def tearDown(self):
        self._sandbox.__exit__(None, None, None)
        if os.path.exists(self.out_path):
            os.remove(self.out_path)

    def test_no_unfilled_tokens_remain(self):
        render_coverletter(_minimal_letter_data(), self.out_path)
        with open(self.out_path, "r", encoding="utf-8") as f:
            html = f.read()
        self.assertNotIn("{{", html)
        self.assertNotIn("}}", html)

    def test_recipient_block_contains_company_name(self):
        render_coverletter(
            _minimal_letter_data(company_name="Widget Co"), self.out_path
        )
        with open(self.out_path, "r", encoding="utf-8") as f:
            html = f.read()
        self.assertIn("Widget Co", html)
        self.assertIn('class="letter-address"', html)

    def test_recipient_block_shows_attn_line_when_contact_known(self):
        render_coverletter(
            _minimal_letter_data(
                contact_name="Maggie Smith", contact_title="HR Manager"
            ),
            self.out_path,
        )
        with open(self.out_path, "r", encoding="utf-8") as f:
            html = f.read()
        self.assertIn("Attn: Maggie Smith, HR Manager", html)

    def test_recipient_block_falls_back_to_hiring_team_line_without_contact(self):
        render_coverletter(
            _minimal_letter_data(company_name="Widget Co"), self.out_path
        )
        with open(self.out_path, "r", encoding="utf-8") as f:
            html = f.read()
        self.assertIn("Widget Co Hiring Team", html)

    def test_recipient_block_includes_location_when_present(self):
        render_coverletter(
            _minimal_letter_data(company_location="Austin, TX"), self.out_path
        )
        with open(self.out_path, "r", encoding="utf-8") as f:
            html = f.read()
        self.assertIn("Austin, TX", html)

    def test_tagline_rendered_in_header_when_present(self):
        render_coverletter(
            _minimal_letter_data(tagline="CONTENT STRATEGIST | SEO"), self.out_path
        )
        with open(self.out_path, "r", encoding="utf-8") as f:
            html = f.read()
        self.assertIn("CONTENT STRATEGIST | SEO", html)

    def test_body_paragraphs_each_wrapped_in_p_tag(self):
        render_coverletter(_minimal_letter_data(), self.out_path)
        with open(self.out_path, "r", encoding="utf-8") as f:
            html = f.read()
        self.assertIn(
            "<p>First paragraph, tying a JD requirement to real experience.</p>", html
        )
        self.assertIn("<p>Second paragraph, with another concrete example.</p>", html)

    def test_contact_info_comes_from_fixed_content(self):
        render_coverletter(_minimal_letter_data(), self.out_path)
        with open(self.out_path, "r", encoding="utf-8") as f:
            html = f.read()
        self.assertIn("Alex Rivera", html)
        self.assertIn("alex.rivera@example.com", html)

    @patch(
        "render_coverletter.profile_paths.signature_path",
        return_value="/x/profiles/testprofile/signature.png",
    )
    def test_signature_image_rendered_as_absolute_file_url_when_present(self, mock_sig):
        render_coverletter(_minimal_letter_data(), self.out_path)
        with open(self.out_path, "r", encoding="utf-8") as f:
            html = f.read()
        self.assertIn('src="file:///x/profiles/testprofile/signature.png"', html)
        self.assertIn('class="signature-img"', html)

    @patch("render_coverletter.profile_paths.signature_path", return_value=None)
    def test_no_img_tag_at_all_when_no_signature(self, mock_sig):
        render_coverletter(_minimal_letter_data(), self.out_path)
        with open(self.out_path, "r", encoding="utf-8") as f:
            html = f.read()
        # The .signature-img CSS *rule* stays in <style> either way (inert
        # if unused) -- what must be absent is an actual <img> element.
        self.assertNotIn("<img", html)

    def test_empty_company_name_title(self):
        render_coverletter(_minimal_letter_data(company_name=""), self.out_path)
        with open(self.out_path, "r", encoding="utf-8") as f:
            html = f.read()
        self.assertIn("<title>Cover Letter - Alex Rivera</title>", html)


class TestBuildSignatureBlockHtml(unittest.TestCase):

    @patch("render_coverletter.profile_paths.signature_path", return_value=None)
    def test_returns_empty_string_when_no_signature(self, mock_sig):
        self.assertEqual(render_coverletter_module.build_signature_block_html(), "")

    @patch(
        "render_coverletter.profile_paths.signature_path",
        return_value="/some/path/signature.jpg",
    )
    def test_returns_img_tag_with_absolute_file_url(self, mock_sig):
        result = render_coverletter_module.build_signature_block_html()
        self.assertEqual(
            result,
            '<img class="signature-img" src="file:///some/path/signature.jpg" alt="">',
        )


class TestBuildRecipientBlockHtml(unittest.TestCase):

    def setUp(self):
        # Resolves the ACTIVE profile, so this class required one to already
        # exist -- see tests/persona.py.
        import persona

        self._persona_sandbox = persona.sandbox_profile()
        self._persona_sandbox.__enter__()
        self.addCleanup(self._persona_sandbox.__exit__, None, None, None)

    def test_no_contact_no_location(self):
        html = render_coverletter_module.build_recipient_block_html("Acme Corp")
        self.assertEqual(
            html, '<div class="letter-address">Acme Corp Hiring Team<br>Acme Corp</div>'
        )

    def test_with_contact_and_location(self):
        html = render_coverletter_module.build_recipient_block_html(
            "Acme Corp",
            contact_name="Maggie Smith",
            contact_title="HR Manager",
            location="Austin, TX",
        )
        self.assertEqual(
            html,
            '<div class="letter-address">Attn: Maggie Smith, HR Manager<br>Acme Corp<br>Austin, TX</div>',
        )

    def test_contact_without_title(self):
        html = render_coverletter_module.build_recipient_block_html(
            "Acme Corp", contact_name="Maggie Smith"
        )
        self.assertIn("Attn: Maggie Smith<br>", html)
        self.assertNotIn("Attn: Maggie Smith,", html)

    def test_escapes_html_in_all_lines(self):
        html = render_coverletter_module.build_recipient_block_html(
            "A&B Corp", contact_name="Pat <b>Lee</b>", location="NY & NJ"
        )
        self.assertIn("A&amp;B Corp", html)
        self.assertIn("Pat &lt;b&gt;Lee&lt;/b&gt;", html)
        self.assertIn("NY &amp; NJ", html)

    def test_main_cli_execution(self):
        import json
        import tempfile
        from unittest.mock import patch

        with tempfile.TemporaryDirectory() as tmpdir:
            json_path = os.path.join(tmpdir, "letter.json")
            out_html = os.path.join(tmpdir, "letter.html")
            with open(json_path, "w", encoding="utf-8") as f:
                json.dump(_minimal_letter_data(), f)
            with patch("sys.argv", ["render_coverletter.py", json_path, out_html]):
                with patch("render_coverletter.cli_art.console.print"):
                    render_coverletter_module.main()
                    self.assertTrue(os.path.exists(out_html))
