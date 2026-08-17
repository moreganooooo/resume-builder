"""
render_coverletter.py — Fills coverletter-template.html with
ResumeEngine.build_tailored_coverletter()'s output.

Usage (standalone):
    python scripts/render_coverletter.py output/json/my_letter_coverletter.json output/html/my_letter_coverletter.html

Called programmatically by orchestrator.py's build_tailored_coverletter().
"""

import argparse
import datetime
import json
import os
from html import escape

import cli_art
import profile_paths
import theme

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(SCRIPT_DIR)
TEMPLATE_PATH = os.path.join(
    PROJECT_ROOT, "resume-engine", "templates", "coverletter-template.html"
)


def build_recipient_block_html(
    company_name: str,
    contact_name: str = "",
    contact_title: str = "",
    location: str = "",
) -> str:
    # Up to 3 lines in one .letter-address div (line-height 1.3, single
    # margin-top before the whole block) so it reads as a tight address
    # block rather than 3 separately-spaced paragraphs.
    lines = []
    if contact_name:
        contact_line = f"Attn: {contact_name}"
        if contact_title:
            contact_line += f", {contact_title}"
        lines.append(contact_line)
    elif company_name:
        lines.append(f"{company_name} Hiring Team")
    if company_name:
        lines.append(company_name)
    if location:
        lines.append(location)
    return f'<div class="letter-address">{"<br>".join(escape(line) for line in lines)}</div>'


def build_body_paragraphs_html(paragraphs: list) -> str:
    return "\n".join(f"<p>{escape(p)}</p>" for p in paragraphs)


def build_signature_block_html() -> str:
    """Empty string (no <img> at all) when this profile has no
    profiles/<name>/signature.{png,jpg,jpeg} -- true graceful
    degradation, not a broken image reference. Uses an absolute file://
    path rather than a relative one: generate-pdf.mjs writes the rendered
    HTML to a temp directory before navigating Chromium to it (a real
    file:// bug fix for font loading, see that file's own comment), so a
    relative "./signature.png" would resolve against the temp dir and
    never find the real file -- exactly the bug that made the old
    hardcoded "./docs/MorganEscottSignature2025.png" reference silently
    broken from the day the temp-file fix shipped, regardless of whether
    that file ever existed. Absolute file:// paths already work for fonts
    (see generate-pdf.mjs's own fontsDir rewrite) -- same fix, applied
    here instead of needing a second rewrite pass in the Node script."""
    path = profile_paths.signature_path()
    if not path:
        return ""
    return f'<img class="signature-img" src="file://{path}" alt="">'


def render_coverletter(cover_letter_data: dict, output_path: str) -> str:
    """
    Fill coverletter-template.html with cover_letter_data and write to
    output_path. Returns output_path on success.
    """
    with open(TEMPLATE_PATH, "r", encoding="utf-8") as f:
        html = f.read()

    company_name = cover_letter_data.get("company_name", "")
    contact = profile_paths.fixed_content_module().CONTACT_INFO
    title = (
        f"{company_name} Cover Letter - {contact['NAME']}"
        if company_name
        else f"Cover Letter - {contact['NAME']}"
    )

    scalars = {
        "LANG": "en",
        "DOCUMENT_TITLE": escape(title),
        "NAME": escape(contact["NAME"]),
        "TAGLINE": escape(cover_letter_data.get("tagline", "")),
        "PHONE": escape(contact["PHONE"]),
        "EMAIL": escape(contact["EMAIL"]),
        "LINKEDIN_DISPLAY": escape(contact["LINKEDIN_DISPLAY"]),
        "LOCATION": escape(contact["LOCATION"]),
        "PAGE_WIDTH": "8.5in",
        "DATE": datetime.date.today().strftime("%B %-d, %Y"),
        "GREETING": escape(cover_letter_data.get("greeting", "")),
        "SIGN_OFF": escape(cover_letter_data.get("sign_off", "")),
        "TYPED_NAME": escape(contact["NAME"]),
        "TYPED_CONTACT": escape(f"{contact['EMAIL']} | {contact['PHONE']}"),
    }
    for token, value in scalars.items():
        html = html.replace(f"{{{{{token}}}}}", value)

    html = html.replace(
        "{{RECIPIENT_BLOCK}}",
        build_recipient_block_html(
            company_name,
            cover_letter_data.get("contact_name", ""),
            cover_letter_data.get("contact_title", ""),
            cover_letter_data.get("company_location", ""),
        ),
    )
    html = html.replace(
        "{{BODY_PARAGRAPHS}}",
        build_body_paragraphs_html(cover_letter_data.get("body_paragraphs", [])),
    )
    html = html.replace("{{SIGNATURE_BLOCK}}", build_signature_block_html())

    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(html)

    cli_art.console.print(
        f"  {theme.colorize_icon('success')} Cover letter HTML rendered → {output_path}",
        soft_wrap=True,
    )
    return output_path


def main():
    parser = argparse.ArgumentParser(description="Render a cover letter JSON into HTML")
    parser.add_argument("input_json")
    parser.add_argument("output_html")
    args = parser.parse_args()
    with open(args.input_json, "r", encoding="utf-8") as f:
        data = json.load(f)
    render_coverletter(data, args.output_html)


if __name__ == "__main__":
    main()
