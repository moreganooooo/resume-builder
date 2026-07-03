"""
fixed_content.py — Canonical, unchanging resume content per ResumeDesignSystem.md.

Certifications and most of Education have zero legitimate per-JD variation,
so they live here as Python constants instead of LLM-generated fields: the
builder is never asked to produce this content and can't introduce drift.
The one genuine per-resume variable -- which pre-approved achievement bullet
to feature for KU and KCKCC -- is a selection from a fixed menu, not free
text; JCCC has no achievement bullet at all (spec: exactly 1 fixed bullet).

Source: resume-engine/knowledge_base/bullet-bank.md's EDUCATION section.
"""

# Contact info doesn't vary by JD either -- previously the builder was asked
# to reproduce name/phone/email/LinkedIn/location from knowledge-base context
# on every single run, risking the same kind of drift already fixed for
# Certifications/Education/company facts. Source: profile.yml. Portfolio link
# is intentionally not included here (removed resume-wide -- can read as an
# ATS red flag on some parsers, and LinkedIn is presented as plain text
# rather than a hyperlink for the same reason).
CONTACT_INFO = {
    "NAME": "Morgan Escott",
    "PHONE": "716-352-9050",
    "EMAIL": "escott.morgan@gmail.com",
    "LINKEDIN_URL": "https://linkedin.com/in/morganescott",
    "LINKEDIN_DISPLAY": "linkedin.com/in/morganescott",
    "LOCATION": "Getzville, NY",
}

# Company facts (size, revenue, location/work-type) don't vary by JD --
# only bullet selection and job-title reframing do -- so they're hard-coded
# here rather than left for the builder to reproduce correctly every run.
# Keyed on the exact company names tailor_resume.md instructs the builder
# to use (see its per-role bullet count table).
COMPANY_META = {
    "Mercor": {"size_revenue": "~800 employees; $75M+ revenue", "location": "Short-Term Contract | Remote"},
    "Treering Yearbooks": {"size_revenue": "~120 employees; $17M+ revenue", "location": "Remote"},
    "Inside Sales Team": {"size_revenue": "~150 employees; ~$21M revenue", "location": "Buffalo, NY"},
    "Element 8 / Strategy LLC": {"size_revenue": "~10–15 employees; ~$1M+ revenue", "location": "Lenexa, KS"},
    "VML": {"size_revenue": "~600+ employees; ~$75M+ revenue", "location": "Kansas City, MO"},
    "Callahan Creek": {"size_revenue": "~30 employees; ~$5M revenue", "location": "Lawrence, KS"},
}

CERTIFICATIONS = [
    {"title": "Email Marketing Software Certification", "org": "HubSpot", "year": "2026"},
    {"title": "Video for Sales Certification", "org": "Vidyard", "year": "2021"},
    {"title": "Camp Portfolio", "org": "Bernstein Rein, Kansas City", "year": "2008"},
]

KU_ACHIEVEMENT_OPTIONS = {
    "content_generalist": "Marketing Intern, Lied Center of Performing Arts, drove 800% social media follower growth through organic content strategy and audience engagement",
    "email_ops":          "Marketing Intern, Lied Center of Performing Arts, managed promotional campaigns and digital channels, growing social media following by 800%",
    "content":            "Marketing Intern, Lied Center of Performing Arts, produced editorial and promotional content across channels, built early instinct for audience-specific messaging",
}

KCKCC_ACHIEVEMENT_OPTIONS = {
    "writing_content": "Editor-in-Chief, student newspaper for 1.5 years, assigned coverage, led editorial team, and managed weekly publication from story conception through print",
    "enablement_mgmt": "Editor-in-Chief, student newspaper, led a team of reporters and columnists, managed editorial calendar, and upheld writing and voice standards across all content",
    "generalist":       "Editor-in-Chief, Kansas Colloquies student newspaper, managed publication end-to-end for 1.5 years while maintaining a full academic scholarship",
}


def build_education(ku_achievement_key: str, kckcc_achievement_key: str) -> list[dict]:
    """
    Assembles the fixed 3-item Education list. `ku_achievement_key` and
    `kckcc_achievement_key` select which pre-approved achievement bullet to
    feature per school; an unrecognized key falls back to that school's
    first option rather than raising, since every option is genuine,
    verified content -- an archetype-suboptimal pick is a quality issue,
    not a truthfulness issue.
    """
    if ku_achievement_key not in KU_ACHIEVEMENT_OPTIONS:
        print(f"  ⚠️  WARNING: unrecognized KU_ACHIEVEMENT_KEY {ku_achievement_key!r}, falling back to first option.")
    ku_bullet = KU_ACHIEVEMENT_OPTIONS.get(
        ku_achievement_key, next(iter(KU_ACHIEVEMENT_OPTIONS.values()))
    )
    if kckcc_achievement_key not in KCKCC_ACHIEVEMENT_OPTIONS:
        print(f"  ⚠️  WARNING: unrecognized KCKCC_ACHIEVEMENT_KEY {kckcc_achievement_key!r}, falling back to first option.")
    kckcc_bullet = KCKCC_ACHIEVEMENT_OPTIONS.get(
        kckcc_achievement_key, next(iter(KCKCC_ACHIEVEMENT_OPTIONS.values()))
    )
    return [
        {
            "degree": "Bachelor of Science, Journalism + Strategic Communication",
            "institution": "University of Kansas",
            "location": "Lawrence, KS",
            "year": "2006 – 2008",
            "bullets": [
                "3.56 GPA, Phi Theta Kappa Scholarship recipient",
                ku_bullet,
            ],
        },
        {
            "degree": "Associate of Arts, Journalism",
            "institution": "Kansas City Kansas Community College",
            "location": "Kansas City, KS",
            "year": "2004 – 2006",
            "bullets": [
                "3.75 GPA, Full academic scholarship, Graduated with honors",
                kckcc_bullet,
            ],
        },
        {
            "degree": "Relevant Coursework, Graphic Design",
            "institution": "Johnson County Community College",
            "location": "Overland Park, KS",
            "year": "2010 – 2011",
            "bullets": [
                "3.86 GPA, studied color theory, typography, illustration, 3D concepts, desktop publishing, and film photography",
            ],
        },
    ]
