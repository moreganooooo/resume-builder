"""Standard JSONResume Schema Exporter Module.

Converts internal resume dictionaries to the open JSON Resume v1.0.0 specification
(https://jsonresume.org/schema/).
"""

from __future__ import annotations

import json
import os
from typing import Any, Dict, List


def convert_to_json_resume(resume_data: Dict[str, Any]) -> Dict[str, Any]:
    """Converts internal resume_data format into JSON Resume schema."""
    contact = resume_data.get("CONTACT", {})
    name = contact.get("name", "Candidate")
    email = contact.get("email", "")
    phone = contact.get("phone", "")
    location = contact.get("location", "")
    linkedin = contact.get("linkedin", "")
    github = contact.get("github", "")
    portfolio = contact.get("portfolio", "")

    summary_text = resume_data.get("SUMMARY_TEXT", "")
    # Strip HTML bold tags from summary
    summary_clean = summary_text.replace("<strong>", "").replace("</strong>", "")

    profiles = []
    if linkedin:
        profiles.append({"network": "LinkedIn", "username": linkedin, "url": linkedin})
    if github:
        profiles.append({"network": "GitHub", "username": github, "url": github})
    if portfolio:
        profiles.append(
            {"network": "Portfolio", "username": portfolio, "url": portfolio}
        )

    work_entries: List[Dict[str, Any]] = []
    for exp in resume_data.get("EXPERIENCE", []):
        company = exp.get("company", "")
        role = exp.get("role", "")
        dates = exp.get("dates", "")
        bullets = exp.get("bullets", [])

        start_date = ""
        end_date = ""
        if " - " in dates:
            parts = dates.split(" - ", 1)
            start_date = parts[0].strip()
            end_date = parts[1].strip()
        elif dates:
            start_date = dates.strip()

        work_entries.append(
            {
                "name": company,
                "position": role,
                "startDate": start_date,
                "endDate": end_date,
                "summary": "",
                "highlights": bullets,
            }
        )

    edu_entries: List[Dict[str, Any]] = []
    for edu in resume_data.get("EDUCATION", []):
        institution = edu.get("institution", edu.get("school", ""))
        degree = edu.get("degree", "")
        dates = edu.get("dates", edu.get("year", ""))

        edu_entries.append(
            {
                "institution": institution,
                "studyType": degree,
                "startDate": "",
                "endDate": dates,
                "courses": [],
            }
        )

    skills_entries: List[Dict[str, Any]] = []
    for skill_group in resume_data.get("SKILLS", []):
        category = skill_group.get("category", "")
        items = skill_group.get("items", [])
        skills_entries.append(
            {
                "name": category,
                "level": "Competent",
                "keywords": items,
            }
        )

    project_entries: List[Dict[str, Any]] = []
    for proj in resume_data.get("PROJECTS", []):
        p_name = proj.get("name", "")
        p_desc = proj.get("description", "")
        p_tech = proj.get("technologies", [])
        project_entries.append(
            {
                "name": p_name,
                "description": p_desc,
                "highlights": [],
                "keywords": p_tech,
            }
        )

    json_resume = {
        "$schema": "https://raw.githubusercontent.com/jsonresume/resume-schema/v1.0.0/schema.json",
        "basics": {
            "name": name,
            "label": "",
            "image": "",
            "email": email,
            "phone": phone,
            "url": portfolio,
            "summary": summary_clean,
            "location": {"city": location, "countryCode": "US"},
            "profiles": profiles,
        },
        "work": work_entries,
        "education": edu_entries,
        "skills": skills_entries,
        "projects": project_entries,
    }
    return json_resume


def export_json_resume_file(resume_data: Dict[str, Any], output_path: str) -> str:
    """Exports resume data to a JSONResume file on disk."""
    os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)
    json_resume_data = convert_to_json_resume(resume_data)
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(json_resume_data, f, indent=2)
    return output_path
