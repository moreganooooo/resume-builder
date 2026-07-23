"""fixed_content.py — this profile's contact info, company facts, and
fixed credentials. Fill in real values as they become known; every dict
here may start empty and grow over time."""

CONTACT_INFO = {
    "NAME": "",
    "PHONE": "",
    "EMAIL": "",
    "LINKEDIN_DISPLAY": "",
    "LOCATION": "",
}

COMPANY_META = {}
COMPANY_TITLE_DESCRIPTOR = {}
CLIENTS = {}
COMPANY_RENAME_NOTE = {}
COMPANY_FIXED_TITLE = {}
CAREER_NOTE = ""
CERTIFICATIONS = []
KU_ACHIEVEMENT_OPTIONS = {}
KCKCC_ACHIEVEMENT_OPTIONS = {}


def build_education(ku_achievement_key: str = "", kckcc_achievement_key: str = "") -> list:
    return []
