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

import profile_paths

SCRIPT_DIR    = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT  = os.path.dirname(SCRIPT_DIR)
TEMPLATE_PATH = os.path.join(PROJECT_ROOT, "resume-engine", "templates", "coverletter-template.html")


def build_recipient_block_html(company_name: str) -> str:
    # Reuses the template's existing .letter-address CSS rule -- no new
    # CSS needed, it was already positioned exactly between .letter-date
    # and .letter-greeting for this purpose.
    return f'<div class="letter-address">{escape(company_name)}</div>'


def build_body_paragraphs_html(paragraphs: list) -> str:
    return "\n".join(f"<p>{escape(p)}</p>" for p in paragraphs)


def render_coverletter(cover_letter_data: dict, output_path: str) -> str:
    """
    Fill coverletter-template.html with cover_letter_data and write to
    output_path. Returns output_path on success.
    """
    with open(TEMPLATE_PATH, "r", encoding="utf-8") as f:
        html = f.read()

    company_name = cover_letter_data.get("company_name", "")
    contact = profile_paths.fixed_content_module().CONTACT_INFO
    title = f"{company_name} Cover Letter - {contact['NAME']}" if company_name else f"Cover Letter - {contact['NAME']}"

    scalars = {
        "LANG":             "en",
        "DOCUMENT_TITLE":   escape(title),
        "NAME":             escape(contact["NAME"]),
        "TAGLINE":          "",
        "PHONE":            escape(contact["PHONE"]),
        "EMAIL":            escape(contact["EMAIL"]),
        "LINKEDIN_DISPLAY": escape(contact["LINKEDIN_DISPLAY"]),
        "LOCATION":         escape(contact["LOCATION"]),
        "PAGE_WIDTH":       "8.5in",
        "DATE":             datetime.date.today().strftime("%B %-d, %Y"),
        "GREETING":         escape(cover_letter_data.get("greeting", "")),
        "SIGN_OFF":         escape(cover_letter_data.get("sign_off", "")),
        "TYPED_NAME":       escape(contact["NAME"]),
        "TYPED_CONTACT":    escape(f"{contact['EMAIL']} | {contact['PHONE']}"),
    }
    for token, value in scalars.items():
        html = html.replace(f"{{{{{token}}}}}", value)

    html = html.replace("{{RECIPIENT_BLOCK}}", build_recipient_block_html(company_name))
    html = html.replace("{{BODY_PARAGRAPHS}}", build_body_paragraphs_html(cover_letter_data.get("body_paragraphs", [])))

    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(html)

    print(f"  ✅ Cover letter HTML rendered → {output_path}")
    return output_path


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Render a cover letter JSON into HTML")
    parser.add_argument("input_json")
    parser.add_argument("output_html")
    args = parser.parse_args()
    with open(args.input_json, "r", encoding="utf-8") as f:
        data = json.load(f)
    render_coverletter(data, args.output_html)
