"""A neutral test identity.

The suite used to hardcode the repo author's real name, email, phone, home
town and ZIP code as fixture data across seventeen files. That is wrong for
three reasons, in increasing order of importance:

1. It is personal information sitting in a public GitHub repository.
2. It makes the tests read as though they only describe one person's
   resume, when they describe the pipeline.
3. It quietly couples the suite to whoever happens to be operating the
   checkout. Anyone else who clones this repo -- a second user on the same
   machine, or a stranger from GitHub -- should be able to run the tests
   and have them mean the same thing.

Import from here instead of typing a literal. If a test needs an identity,
it needs *an* identity, not *this* identity.

The location values are real, geocodable places (they resolve against the
bundled GeoNames data in assets/geodata/, which the distance and radius
tests genuinely need) chosen to have nothing to do with any contributor.

tests/test_no_operator_identity.py enforces this: it reads the ACTIVE
profile's own profile.yml and fails if those values appear anywhere in
tests/. That check works for whoever is running it, so it will catch the
next person hardcoding their own details just as readily.
"""

import contextlib
import os
import sys
import tempfile

sys.path.insert(
    0,
    os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts"
    ),
)


# --- identity -------------------------------------------------------
FULL_NAME = "Alex Rivera"
FIRST_NAME = "Alex"
LAST_NAME = "Rivera"
EMAIL = "alex.rivera@example.com"
# 555-01xx is the reserved fictional-number block (NANP), so this can
# never be a real person's phone.
PHONE = "555-0100"
PHONE_E164 = "+1-555-0100"
LINKEDIN_DISPLAY = "linkedin.com/in/alexrivera"
LINKEDIN_URL = "https://linkedin.com/in/alexrivera"
PORTFOLIO_URL = "https://alexrivera.example.com"

# --- location -------------------------------------------------------
# Real and geocodable, deliberately unrelated to any contributor.
CITY = "Springfield"
STATE = "IL"
ZIP = "62701"
LOCATION = f"{CITY}, {STATE}"
LOCATION_VERBOSE = f"{CITY}, {STATE} (Central Illinois)"

# A second, nearby-but-distinct city for radius/distance tests that need
# two points. ~175 miles apart, so it is comfortably outside any small
# commute radius a test might set.
FAR_CITY = "Chicago"
FAR_STATE = "IL"
FAR_LOCATION = f"{FAR_CITY}, {FAR_STATE}"

# --- profile --------------------------------------------------------
# Test profile name. Never "morgan" -- a test that names a real profile
# either reads that person's data or creates a directory beside it.
PROFILE = "testpersona"


CONTACT_INFO = {
    "NAME": FULL_NAME,
    "PHONE": PHONE,
    "EMAIL": EMAIL,
    "LINKEDIN_DISPLAY": LINKEDIN_DISPLAY,
    "LOCATION": LOCATION,
}


def candidate_block() -> dict:
    """The `candidate:` mapping as it appears in a profile.yml."""
    return {
        "full_name": FULL_NAME,
        "first_name": FIRST_NAME,
        "last_name": LAST_NAME,
        "email": EMAIL,
        "phone": PHONE_E164,
        "location": LOCATION,
        "linkedin": LINKEDIN_DISPLAY,
        "portfolio_url": PORTFOLIO_URL,
    }


# Bullet-bank tag taxonomy. tag_bullet_bank.tag_keywords()/fallback_tag()
# read profile.yml's `tags:` -- a freshly scaffolded profile has none, so
# tests that assert real tagging behaviour need a populated taxonomy. The
# fallback tag is the one with an EMPTY keyword list, which is how
# fallback_tag() identifies it.
FALLBACK_TAG = "[generalist]"


def fixed_credentials() -> dict:
    """profile.yml's `fixed_credentials:` block.

    The two education entries with `achievement_options` are what
    profile_paths.education_achievement_slots() turns into the dynamic
    EDU_ACHIEVEMENT_KEY_<n> schema fields; the third deliberately has none,
    so the "entries without options are skipped" path stays covered.
    """
    return {
        "certifications": [
            {
                "name": "Lifecycle Marketing Certification",
                "issuer": "Example Org",
                "year": 2026,
            }
        ],
        "education": [
            {
                "institution": "Lakeshore University",
                "credential": "BS, Journalism + Strategic Communication",
                "bullet_count": 2,
                "achievement_options": {
                    "content_generalist": "Marketing Intern, campus arts centre, drove 800% social media follower growth",
                    "email_ops": "Marketing Intern, campus arts centre, managed promotional campaigns across digital channels",
                },
            },
            {
                "institution": "Fairview Community College",
                "credential": "AA, Journalism",
                "bullet_count": 1,
                "achievement_options": {
                    "writing_content": "Editor-in-Chief, student newspaper, led editorial team through weekly publication",
                    "generalist": "Editor-in-Chief, student newspaper, managed publication end-to-end",
                },
            },
            {
                # No achievement_options on purpose -- must be skipped.
                "institution": "Continuing Education",
                "credential": "Certificate, Data Analytics",
                "bullet_count": 1,
            },
        ],
    }


def tag_taxonomy() -> list:
    return [
        {
            "name": "email",
            "persona_description": "email or lifecycle marketing roles",
            "keywords": ["email", "open rate", "sequence", "campaign", "drip"],
        },
        {
            "name": "ops",
            "persona_description": "marketing operations, CRM, or analytics roles",
            "keywords": [
                "salesforce",
                "crm",
                "pipeline",
                "territory",
                "outreach.io",
                "reporting",
            ],
        },
        {
            "name": "content",
            "persona_description": "content, copywriting, or editorial roles",
            "keywords": ["copy", "editorial", "blog", "content"],
        },
        {
            # Catch-all: identified by having NO keywords.
            "name": "generalist",
            "persona_description": "anything not covered above",
            "keywords": [],
        },
    ]


@contextlib.contextmanager
def sandbox_profile(name: str = PROFILE):
    """A fully-formed profile built from this persona, in a temp directory.

    Several tests used to set RESUME_PROFILE="morgan" and assert on the
    values in that person's real profiles/morgan/fixed_content.py. Those
    tests passed only on that machine: anyone else cloning the repo has no
    such profile, and even on the original machine they were asserting
    facts about one resume rather than about the renderer.

    Redirects all four profile-data roots (so nothing touches the real
    checkout), scaffolds the profile, writes a profile.yml carrying this
    persona's candidate block, and points RESUME_PROFILE at it. On exit
    everything is restored and the temp directory is removed.

    CONTACT_INFO is left as the scaffold's empty strings on purpose: it
    then derives from profile.yml, which is the real contract
    (profile_paths._fill_contact_info_from_profile_yaml) and the thing
    worth exercising.
    """
    import bootstrap_bullet_bank
    import profile_paths
    import yaml

    orig = os.environ.get("RESUME_PROFILE")
    with tempfile.TemporaryDirectory() as tmp:
        with profile_paths.isolate_for_tests(tmp):
            bootstrap_bullet_bank.create_new_profile(name)
            # Overwrite the scaffold with the fictional-employer fixture so
            # tests can exercise company meta / rename / client branches.
            with open(
                os.path.join(profile_paths.profile_root(name), "fixed_content.py"),
                "w",
                encoding="utf-8",
            ) as f:
                f.write(FIXED_CONTENT_SOURCE)
            kb = profile_paths.kb_dir(name)
            os.makedirs(kb, exist_ok=True)
            with open(os.path.join(kb, "profile.yml"), "w", encoding="utf-8") as f:
                yaml.safe_dump(
                    {
                        "candidate": candidate_block(),
                        "tags": tag_taxonomy(),
                        "fixed_credentials": fixed_credentials(),
                    },
                    f,
                )
            with open(
                profile_paths.situational_roles_path(name), "w", encoding="utf-8"
            ) as f:
                f.write(SITUATIONAL_ROLES_SOURCE)
            with open(
                os.path.join(profile_paths.board_scanner_dir(name), "scan_filters.yml"),
                "w",
                encoding="utf-8",
            ) as f:
                f.write(SCAN_FILTERS_SOURCE)
            os.environ["RESUME_PROFILE"] = name
            try:
                yield name
            finally:
                if orig is None:
                    os.environ.pop("RESUME_PROFILE", None)
                else:
                    os.environ["RESUME_PROFILE"] = orig


# --- employers ------------------------------------------------------
# Fictional companies with the same STRUCTURAL shapes the real ones have
# (meta, industry descriptor, rename note, fixed title, client list,
# career-break note), so tests can exercise every branch of
# normalize_resume without describing any real person's career.
EMPLOYER_WITH_META = "Northwind Labs"
EMPLOYER_LONG_TENURE = "Ridgeline Media"
EMPLOYER_WITH_CLIENTS = "Harbor Point Agency"
EMPLOYER_WITH_FIXED_TITLE = "Copper Fox Studio"
EMPLOYER_RENAMED = "Beacon Sales Group"

FIXED_CONTENT_SOURCE = f'''"""Generated by tests/persona.py -- fictional fixture data."""

CONTACT_INFO = {{
    "NAME": "",
    "PHONE": "",
    "EMAIL": "",
    "LINKEDIN_DISPLAY": "",
    "LOCATION": "",
}}

COMPANY_META = {{
    "{EMPLOYER_WITH_META}": {{
        "size_revenue": "~800 employees; $75M+ revenue",
        "location": "Short-Term Contract | Remote",
    }},
    "{EMPLOYER_WITH_CLIENTS}": {{
        "size_revenue": "~30 employees; ~$5M revenue",
        "location": "{LOCATION}",
    }},
    "{EMPLOYER_LONG_TENURE}": {{"location": "Remote"}},
    "{EMPLOYER_RENAMED}": {{"location": "{LOCATION}"}},
}}

COMPANY_TITLE_DESCRIPTOR = {{
    "{EMPLOYER_WITH_META}": "AI Training",
    "{EMPLOYER_WITH_CLIENTS}": "Agency/Creative/Brand",
    "{EMPLOYER_WITH_FIXED_TITLE}": "Design/Agency/Startup",
    "{EMPLOYER_LONG_TENURE}": "SaaS/EdTech",
    "{EMPLOYER_RENAMED}": "Outbound/Agency",
}}

CLIENTS = {{
    "{EMPLOYER_WITH_CLIENTS}": {{
        "list": "Aurora Foods, Cascade Credit Union, Fenwick Brewing",
        "essential": True,
    }},
}}

COMPANY_RENAME_NOTE = {{
    "{EMPLOYER_RENAMED}": "Larkspur",
    "{EMPLOYER_WITH_CLIENTS}": "Harborworks",
}}

COMPANY_FIXED_TITLE = {{
    "{EMPLOYER_WITH_FIXED_TITLE}": "Design Assistant to Lead Designer",
}}

CAREER_NOTE = (
    "After a long run at {EMPLOYER_LONG_TENURE}, I took time to support a "
    "family member and invest in professional growth."
)
CAREER_NOTE_COMPANY = "{EMPLOYER_LONG_TENURE}"

CAREER_BREAK_ENTRY = {{
    "company": "Career Break - Professional Development",
    "title": "Data Analytics & Automation",
    "period": "08/2024 - 08/2025",
    "location": "Remote",
    "achievements": ["Completed analytics and lifecycle marketing certifications."],
}}

CERTIFICATIONS = [
    {{"title": "Lifecycle Marketing Certification", "org": "Example Org", "year": "2026"}},
]

CV_SECTION_KEYWORDS = [
    (["northwind"], "{EMPLOYER_WITH_META}"),
    (["ridgeline"], "{EMPLOYER_LONG_TENURE}"),
    (["harbor point"], "{EMPLOYER_WITH_CLIENTS}"),
    (["copper fox"], "{EMPLOYER_WITH_FIXED_TITLE}"),
    (["beacon"], "{EMPLOYER_RENAMED}"),
]

BACKGROUND_IDENTITY = "A lifecycle marketer who also operates the stack."
BACKGROUND_TAGS = {{}}


def build_education(achievement_keys: dict = None) -> list:
    keys = achievement_keys or {{}}
    slot1 = {{
        "content_generalist": "Marketing Intern, campus arts centre, drove 800% social media follower growth",
        "email_ops": "Marketing Intern, campus arts centre, managed promotional campaigns across digital channels",
    }}
    slot2 = {{
        "writing_content": "Editor-in-Chief, student newspaper, led editorial team through weekly publication",
        "generalist": "Editor-in-Chief, student newspaper, managed publication end-to-end",
    }}
    return [
        {{
            "school": "Lakeshore University",
            "degree": "BS, Journalism + Strategic Communication",
            "bullets": [
                "Graduated with honours",
                slot1.get(keys.get("EDU_ACHIEVEMENT_KEY_1"), slot1["content_generalist"]),
            ],
        }},
        {{
            "school": "Fairview Community College",
            "degree": "AA, Journalism",
            "bullets": [
                slot2.get(keys.get("EDU_ACHIEVEMENT_KEY_2"), slot2["writing_content"]),
            ],
        }},
        {{
            "school": "Continuing Education",
            "degree": "Certificate, Data Analytics",
            "bullets": [],
        }},
    ]
'''


# --- situational roles ----------------------------------------------
# Older/one-off jobs surfaced only when a JD's language matches. Fictional,
# but structurally identical to a real profile's situational_roles.yaml --
# including the two-keyword-group case (SITUATIONAL_COMBINED), which must
# match only when BOTH kinds of language appear.
SITUATIONAL_ANIMAL = "Riverbend Animal Shelter"
SITUATIONAL_PRINT = "Copperline Print Services"
SITUATIONAL_NEWS = "Fairview Herald"
SITUATIONAL_PAYROLL = "Lakeshore Payroll Office"
SITUATIONAL_TAX = "Whitfield & Prine Tax"
SITUATIONAL_COMBINED = "Marigold Office Group"

SITUATIONAL_ROLES_SOURCE = f"""situational_min_bullets: 2
roles:
  - display_name: "{SITUATIONAL_ANIMAL}"
    bank_tag: "{SITUATIONAL_ANIMAL}"
    trigger_keywords: ["animal welfare", "animal shelter", "animal rescue", "humane society", "veterinary"]
  - display_name: "{SITUATIONAL_PRINT}"
    bank_tag: "{SITUATIONAL_PRINT}"
    trigger_keywords: ["print production", "document management", "print services", "document solutions"]
  - display_name: "{SITUATIONAL_NEWS}"
    bank_tag: "{SITUATIONAL_NEWS}"
    trigger_keywords: ["newspaper", "reporter", "journalism", "editorial team"]
  - display_name: "{SITUATIONAL_PAYROLL}"
    bank_tag: "{SITUATIONAL_PAYROLL}"
    trigger_keywords: ["payroll processing", "payroll administration", "payroll"]
  - display_name: "{SITUATIONAL_TAX}"
    bank_tag: "{SITUATIONAL_TAX}"
    trigger_keywords: ["tax preparation", "bookkeeping", "audit readiness", "accounting firm"]
  - display_name: "{SITUATIONAL_COMBINED}"
    bank_tag: "{SITUATIONAL_COMBINED}"
    admin_keywords: ["clerical", "administrative support", "administrative assistant"]
    design_keywords: ["graphic design"]
"""


# --- board-scanner filters ------------------------------------------
# create_new_profile() scaffolds these EMPTY, and empty is permissive by
# design (an empty positive list means every title passes), so tests that
# assert filtering actually filters need a populated set.
SCAN_FILTERS_SOURCE = """title_filter:
  positive:
    - "marketing"
    - "lifecycle"
    - "crm"
    - "content"
  negative:
    - " engineer"
    - "warehouse"
    - "driver"
location_filter:
  always_allow:
    - "Remote"
  block:
    - "Onsite"
"""
