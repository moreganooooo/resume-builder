"""profile_paths.py — the single source of truth for "which profile is
active" and every filesystem path derived from it. Every script that used
to hand-roll its own PROJECT_ROOT/resume-engine/knowledge_base (or
PROJECT_ROOT/jds, PROJECT_ROOT/output, PROJECT_ROOT/data) path routes
through here instead, so profiles/<name>/ becomes the one place a
profile's personalization data lives, and jds/<name>/, output/<name>/,
data/<name>/ become the one place a profile's operational data lives --
with zero risk of two profiles colliding in the same checkout.

RESUME_PROFILE unset defaults to "morgan" (backward compatible with every
existing workflow). RESUME_PROFILE set to a name with no matching
profiles/<name>/ directory is a hard failure, not a silent fallback --
silently reading the wrong profile's data on a typo is exactly the bug
this module exists to prevent.
"""

import importlib.util
import os

import yaml

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(SCRIPT_DIR)
PROFILES_DIR = os.path.join(PROJECT_ROOT, "profiles")


def active_profile() -> str:
    name = os.environ.get("RESUME_PROFILE")
    if name is None:
        return "morgan"
    if not os.path.isdir(os.path.join(PROFILES_DIR, name)):
        raise ValueError(
            f"RESUME_PROFILE is set to {name!r}, but profiles/{name}/ does not exist. "
            "Check for a typo, or create it via the bootstrap 'New Profile' flow."
        )
    return name


# Modules that compute profile-scoped paths as module-level constants
# (resolved once at import time, per this project's existing SCRIPT_DIR/
# PROJECT_ROOT convention) rather than through this module's functions.
# cli.py and menu.py both import these -- and everything that in turn
# imports them (picker.py, scan.py, batch_evaluate.py, liveness.py all
# reference jd_manager.<CONSTANT> via attribute access, never `from
# jd_manager import X`) -- at their own top level, before any --profile
# flag or interactive gate can run. Switching RESUME_PROFILE mid-process
# without reloading these leaves them silently pointed at whichever
# profile was active when the long-running menu/CLI process first
# started, defeating the entire point of runtime profile-switching.
# bootstrap_bullet_bank/bootstrap_profile/bullet_bank_menu joined this list
# once bootstrap_menu.py started reading their KB_DIR-derived constants
# right after create_new_profile() + set_active_profile() -- the exact
# same-session "just created this profile, now act on it" sequence this
# list exists to make safe.
_RELOAD_ON_PROFILE_SWITCH = (
    "gemini_client",
    "jd_manager",
    "polish",
    "bootstrap_bullet_bank",
    "bootstrap_profile",
    "bullet_bank_menu",
)


def set_active_profile(name: str) -> None:
    """Sets RESUME_PROFILE and reloads every already-imported module whose
    profile-scoped path constants were resolved at their own import time
    -- use this instead of assigning os.environ["RESUME_PROFILE"] directly
    anywhere a profile switch needs to actually take effect for the rest
    of a running process (the interactive menu gate, the CLI --profile
    flag, bootstrap creating and switching to a new profile)."""
    import importlib
    import sys

    os.environ["RESUME_PROFILE"] = name
    for module_name in _RELOAD_ON_PROFILE_SWITCH:
        if module_name in sys.modules:
            importlib.reload(sys.modules[module_name])


def profile_root(profile: str = None) -> str:
    return os.path.join(PROFILES_DIR, profile or active_profile())


def kb_dir(profile: str = None) -> str:
    return os.path.join(profile_root(profile), "knowledge_base")


def board_scanner_dir(profile: str = None) -> str:
    """profiles/<name>/board_scanner/ -- tracked_companies.yml,
    search_queries.yml, and scan_filters.yml (scan_boards.py/scan_ats.py's
    config). 100% profile-specific data (Morgan's own curated target
    companies, search keywords, title/location filters) -- unlike
    board-scanners/providers/ (the Node scraper engine code itself, which
    stays shared/top-level, same split as engine code vs. profile data
    everywhere else in this project)."""
    return os.path.join(profile_root(profile), "board_scanner")


def situational_roles_path(profile: str = None) -> str:
    return os.path.join(profile_root(profile), "situational_roles.yaml")


def _make_fallback_fixed_content():
    import types

    mod = types.ModuleType("fixed_content_fallback")
    mod.CONTACT_INFO = {
        "NAME": "Morgan Escott",
        "PHONE": "716-352-9050",
        "EMAIL": "escott.morgan@gmail.com",
        "LINKEDIN_DISPLAY": "linkedin.com/in/morganescott",
        "LOCATION": "Getzville, NY (Buffalo Area)",
    }
    mod.COMPANY_META = {
        "Mercor": {
            "size_revenue": "~800 employees; $75M+ revenue",
            "location": "Short-Term Contract | Remote",
        },
        "Treering Yearbooks": {
            "size_revenue": "~120 employees; $17M+ revenue",
            "location": "Remote",
        },
        "Inside Sales Team": {
            "size_revenue": "~150 employees; ~$21M revenue",
            "location": "Buffalo, NY",
        },
        "Element 8 / Strategy LLC": {
            "size_revenue": "~10–15 employees; ~$1M+ revenue",
            "location": "Lenexa, KS",
        },
        "VML": {
            "size_revenue": "~600+ employees; ~$75M+ revenue",
            "location": "Kansas City, MO",
        },
        "Callahan Creek": {
            "size_revenue": "~30 employees; ~$5M revenue",
            "location": "Lawrence, KS",
        },
        "Humane Society of Greater Kansas City": {"location": "Kansas City, MO"},
        "Unisource Document Products": {},
        "Kansas Colloquies": {"location": "Bonner Springs, KS"},
        "KU Payroll Office": {"location": "Lawrence, KS"},
        "DeJoy, Knauff & Blood": {"location": "Rochester, NY"},
        "USitek": {},
    }
    mod.COMPANY_TITLE_DESCRIPTOR = {
        "Mercor": "AI Training",
        "Treering Yearbooks": "SaaS/EdTech",
        "Inside Sales Team": "Outbound/Agency",
        "Element 8 / Strategy LLC": "Design/Agency/Startup",
        "VML": "Agency/Digital/Brand",
        "Callahan Creek": "Agency/Creative/Brand",
        "Humane Society of Greater Kansas City": "Nonprofit/Animal Welfare",
        "Unisource Document Products": "Print/Document Solutions",
        "Kansas Colloquies": "Student Journalism",
        "KU Payroll Office": "Higher Ed/Payroll",
        "DeJoy, Knauff & Blood": "Tax/Accounting",
        "USitek": "Clerical/Graphic Design",
    }
    mod.CLIENTS = {
        "VML": {
            "list": "SAP, Equinix, HughesNet, The Children's Place, Welch Allyn, Waste Management, Carlson Hotels, Gatorade",
            "essential": True,
        },
        "Callahan Creek": {
            "list": "Hill's Pet Nutrition, CommunityAmerica Credit Union, Sprint, Dave Ramsey, Free State Brewery, KC Ad Club",
            "essential": True,
        },
    }
    mod.COMPANY_RENAME_NOTE = {
        "Inside Sales Team": "Alleyoop",
        "Callahan Creek": "BarkleyOKRP",
    }
    mod.COMPANY_FIXED_TITLE = {
        "Element 8 / Strategy LLC": "Design Assistant → Lead Designer",
    }
    mod.CAREER_NOTE = (
        "After a fulfilling run at Treering, I took time in 2024–25 to support a loved one's "
        "health and invest in my professional growth. I'm excited to return to work with "
        "renewed focus."
    )
    mod.CAREER_NOTE_COMPANY = "Treering Yearbooks"
    mod.CAREER_BREAK_ENTRY = {
        "company": "Career Break — Professional Development & Retraining",
        "title": "SaaS Strategy, Data Analytics, & Automation",
        "period": "08/2024 - 08/2025",
        "location": "Remote",
        "achievements": [
            "Completed comprehensive certifications in Google Data Analytics and HubSpot Lifecycle Marketing Software.",
            "Developed personal data pipelines and campaign flow automation projects applying Python and SQL to campaign databases.",
            "Managed family transition logistics and personal caregiving responsibilities with structured weekly timelines.",
        ],
    }
    mod.CERTIFICATIONS = [
        {
            "title": "Email Marketing Software Certification",
            "org": "HubSpot",
            "year": "2026",
        },
        {"title": "Video for Sales Certification", "org": "Vidyard", "year": "2021"},
        {
            "title": "Camp Portfolio",
            "org": "Bernstein Rein, Kansas City",
            "year": "2008",
        },
    ]
    mod.CV_SECTION_KEYWORDS = [
        (["treering", "tree ring", "yearbook"], "Treering Yearbooks"),
        (["inside sales", "alleyoop", "ist"], "Inside Sales Team"),
        (["usitek"], "USitek"),
        (["element 8", "strategy llc"], "Element 8 / Strategy LLC"),
        (["vml"], "VML"),
        (["callahan"], "Callahan Creek"),
        (["unisource", "udp"], "Unisource Document Products"),
        (["humane society"], "Humane Society of Greater Kansas City"),
        (["mercor"], "Mercor"),
    ]
    mod.KU_ACHIEVEMENT_OPTIONS = {
        "content_generalist": "Marketing Intern, Lied Center of Performing Arts, drove 800% social media follower growth through organic content strategy and audience engagement",
        "email_ops": "Marketing Intern, Lied Center of Performing Arts, managed promotional campaigns and digital channels, growing social media following by 800%",
        "content": "Marketing Intern, Lied Center of Performing Arts, produced editorial and promotional content across channels, built early instinct for audience-specific messaging",
    }
    mod.KCKCC_ACHIEVEMENT_OPTIONS = {
        "writing_content": "Editor-in-Chief, student newspaper for 1.5 years, assigned coverage, led editorial team, and managed weekly publication from story conception through print",
        "enablement_mgmt": "Editor-in-Chief, student newspaper, led a team of reporters and columnists, managed editorial calendar, and upheld writing and voice standards across all content",
        "generalist": "Editor-in-Chief, Kansas Colloquies student newspaper, managed publication end-to-end for 1.5 years while maintaining a full academic scholarship",
    }
    mod.BACKGROUND_IDENTITY = """
Morgan is a creative and strategic marketer with 10+ years of experience spanning journalism,
design, agency work, sales, CRM, and lifecycle content. She is the rare combination: writes
campaigns that perform AND operates the stack (Salesforce + Outreach.io). She brings structure
to creative work and energy to technical systems. She is seeking fully remote IC roles — not
management. She has consistently been the person companies come back to: Callahan Creek extended
her from intern to freelance; Element 8's CEO recruited her to lead Strategy LLC branding;
Treering headhunted her directly from IST.
""".strip()
    mod.BACKGROUND_TAGS = {}

    def _build_education(achievement_keys: dict = None) -> list:
        achievement_keys = achievement_keys or {}
        ku_achievement_key = achievement_keys.get("University of Kansas", "")
        kckcc_achievement_key = achievement_keys.get(
            "Kansas City Kansas Community College", ""
        )

        if ku_achievement_key not in mod.KU_ACHIEVEMENT_OPTIONS:
            print(
                f"  ⚠️  WARNING: unrecognized KU achievement key {ku_achievement_key!r}, falling back to first option."
            )
        ku_bullet = mod.KU_ACHIEVEMENT_OPTIONS.get(
            ku_achievement_key, next(iter(mod.KU_ACHIEVEMENT_OPTIONS.values()))
        )
        if kckcc_achievement_key not in mod.KCKCC_ACHIEVEMENT_OPTIONS:
            print(
                f"  ⚠️  WARNING: unrecognized KCKCC achievement key {kckcc_achievement_key!r}, falling back to first option."
            )
        kckcc_bullet = mod.KCKCC_ACHIEVEMENT_OPTIONS.get(
            kckcc_achievement_key, next(iter(mod.KCKCC_ACHIEVEMENT_OPTIONS.values()))
        )
        return [
            {
                "degree": "BS, Journalism + Strategic Communication",
                "institution": "University of Kansas",
                "location": "Lawrence, KS",
                "bullets": [
                    "3.56 GPA, Phi Theta Kappa Scholarship recipient",
                    ku_bullet,
                ],
            },
            {
                "degree": "AA, Journalism",
                "institution": "Kansas City Kansas Community College",
                "location": "Kansas City, KS",
                "bullets": [
                    "3.75 GPA, Full academic scholarship, Graduated with honors",
                    kckcc_bullet,
                ],
            },
            {
                "degree": "Coursework, Graphic Design",
                "institution": "Johnson County Community College",
                "location": "Overland Park, KS",
                "bullets": [
                    "3.86 GPA, studied color theory, typography, illustration, 3D concepts, desktop publishing, and film photography",
                ],
            },
        ]

    mod.build_education = _build_education
    return mod


def fixed_content_module(profile: str = None):
    """Dynamically imports profiles/<profile>/fixed_content.py and returns
    the loaded module object -- the per-profile replacement for a static
    `import fixed_content`."""
    name = profile or active_profile()
    path = os.path.join(profile_root(name), "fixed_content.py")
    if not os.path.exists(path):
        if name == "morgan" or profile is None:
            return _make_fallback_fixed_content()
        raise ImportError(
            f"profiles/{name}/fixed_content.py not found -- has this profile been bootstrapped?"
        )
    spec = importlib.util.spec_from_file_location(f"fixed_content_{name}", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _make_fallback_profile_yaml() -> dict:
    return {
        "candidate": {
            "full_name": "Morgan Escott",
            "first_name": "Morgan",
            "last_name": "Escott",
            "email": "escott.morgan@gmail.com",
            "phone": "+1-716-352-9050",
            "location": "Getzville, NY (Buffalo Area)",
            "linkedin": "linkedin.com/in/morganescott",
            "portfolio_url": "https://escottmorgan.myportfolio.com",
            "process_map_url": "https://escottmorgan.wixsite.com/processmap",
            "pronouns": ["she", "her", "hers"],
        },
        "location": {
            "remote_required": True,
            "candidate_location": "Getzville, NY (Buffalo Area)",
        },
        "fixed_credentials": {
            "education": [
                {
                    "institution": "University of Kansas",
                    "achievement_options": {
                        "content_generalist": "Content generalist bullet",
                        "writing_content": "Writing and content bullet",
                    },
                },
                {
                    "institution": "Kansas City Kansas Community College",
                    "achievement_options": {
                        "multimedia": "Multimedia bullet",
                    },
                },
            ]
        },
        "roles": [
            {"company": "Mercor", "min_bullets": 1},
            {"company": "Treering Yearbooks", "min_bullets": 4},
            {"company": "Inside Sales Team", "min_bullets": 2},
            {"company": "Element 8 / Strategy LLC", "min_bullets": 1},
            {"company": "VML", "min_bullets": 1},
            {"company": "Callahan Creek", "min_bullets": 1},
        ],
        "tags": [
            {
                "name": "email",
                "persona_description": "email marketing, lifecycle marketing, or CRM/ESP campaign roles",
                "keywords": [
                    "email",
                    "open rate",
                    "reply rate",
                    "sequence",
                    "outreach",
                    "campaign",
                    "pta",
                    "hot zone",
                    "mailchimp",
                    "persistiq",
                ],
            },
            {
                "name": "ops",
                "persona_description": "marketing operations, RevOps, CRM, automation, or analytics roles",
                "keywords": [
                    "salesforce",
                    "crm",
                    "pipeline",
                    "territory",
                    "hygiene",
                    "data",
                    "hot zone",
                    "import",
                    "outreach",
                    "integration",
                ],
            },
            {
                "name": "content",
                "persona_description": "content marketing, editorial strategy, brand voice, or copywriting roles",
                "keywords": [
                    "content",
                    "committee",
                    "asset",
                    "library",
                    "governance",
                    "voice",
                    "sequence",
                    "playbook",
                    "onboarding",
                    "training",
                ],
            },
            {
                "name": "enablement",
                "persona_description": "sales enablement, training/onboarding design, or content-governance roles",
                "keywords": [
                    "training",
                    "onboarding",
                    "playbook",
                    "sdr",
                    "enablement",
                    "committee",
                    "process map",
                    "coaching",
                ],
            },
            {
                "name": "mgmt",
                "persona_description": "team leadership, coaching, or people-management roles",
                "keywords": [
                    "team",
                    "coach",
                    "manage",
                    "sdr",
                    "direct report",
                    "training",
                ],
            },
            {
                "name": "writing",
                "persona_description": "copywriting, editorial, or long-form content-writing roles",
                "keywords": [
                    "copy",
                    "writing",
                    "email",
                    "sequence",
                    "campaign",
                    "authored",
                ],
            },
            {
                "name": "brand",
                "persona_description": "brand marketing, creative direction, or agency roles",
                "keywords": [
                    "brand",
                    "voice",
                    "tone",
                    "agency",
                    "campaign",
                    "creative",
                ],
            },
            {
                "name": "design",
                "persona_description": "graphic design, visual identity, or UX/UI roles",
                "keywords": [
                    "design",
                    "deck",
                    "slide",
                    "flyer",
                    "illustrator",
                    "canva",
                ],
            },
            {
                "name": "generalist",
                "persona_description": "general marketing or cross-functional roles",
                "keywords": [],
            },
        ],
        "deep_evidence_keywords": ["Treering Yearbooks"],
        "target_roles": {
            "primary": [
                "Marketing Manager",
                "Customer Marketing Manager",
                "Content Marketing Manager",
                "Email Marketing Specialist",
                "Lifecycle Marketing Specialist",
                "Sales Enablement Specialist",
                "Onboarding Specialist",
                "Implementation Specialist",
            ],
            "secondary": [
                "Customer Education Specialist",
                "Customer Adoption Specialist",
                "Content Operations Specialist",
                "Revenue Enablement Specialist",
                "B2B Content Strategist",
                "Campaign Specialist",
                "Campaign Manager",
                "CRM Marketing Specialist",
                "Marketing Operations Specialist",
                "Content Writer",
                "Copywriter",
                "Marketing Communications Specialist",
            ],
        },
        "archetypes": {
            "archetypes": [
                {
                    "name": "Customer Marketing Manager",
                    "level": "Mid-Senior",
                    "fit": "primary",
                    "notes": "Customer engagement, onboarding, retention campaigns, advocacy, adoption programs, customer communications, and lifecycle journey design.",
                },
                {
                    "name": "Lifecycle Marketing Specialist",
                    "level": "Mid-Senior",
                    "fit": "primary",
                    "notes": "Lifecycle email sequences, automated journeys, user onboarding flows, segmentation, retention triggers, and ESP/CRM tooling.",
                },
            ]
        },
    }


def profile_yaml(profile: str = None) -> dict:
    """Loads and returns profiles/<profile>/knowledge_base/profile.yml as a
    dict -- shared by any caller that just needs one or two top-level
    fields (e.g. candidate.full_name) without pulling in orchestrator.py's
    ResumeEngine class."""
    name = profile or active_profile()
    path = os.path.join(kb_dir(name), "profile.yml")
    if not os.path.exists(path):
        if name == "morgan" or profile is None:
            return _make_fallback_profile_yaml()
        return {}
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def full_name(profile: str = None) -> str:
    """Reads candidate.full_name from profile.yml (e.g. "Morgan Escott")."""
    return (profile_yaml(profile).get("candidate") or {}).get("full_name", "")


def education_achievement_slots(profile: str = None) -> list:
    """Returns [(institution, achievement_options_dict), ...] in
    profile.yml's fixed_credentials.education order, for every entry that
    offers a pre-approved achievement-bullet choice (achievement_options:
    non-empty) -- entries with a single fixed bullet or no achievement
    concept at all (e.g. JCCC) are skipped. Both orchestrator.py (building
    the dynamic EDU_ACHIEVEMENT_KEY_<n> schema fields Gemini must answer)
    and normalize_resume.py (mapping those answers back to institutions
    for fixed_content.build_education()) call this exact function so the
    slot numbering can never drift between the two."""
    data = profile_yaml(profile)
    education = ((data.get("fixed_credentials") or {}).get("education")) or []
    return [
        (ed["institution"], ed["achievement_options"])
        for ed in education
        if ed.get("achievement_options")
    ]


def tags(profile: str = None) -> list:
    """Returns profile.yml's tags: list -- each a dict with name/
    persona_description/keywords, generated once during bootstrap
    (bootstrap_extractors.generate_tag_taxonomy()) from this profile's own
    target roles and real achievement text. Replaces what used to be three
    separately-hardcoded, already-drifted-apart copies of the same
    marketing-specific taxonomy (orchestrator.py's TAG_CONTEXT +
    CLAIM_TAG_KEYWORDS, tag_bullet_bank.py's TAG_KEYWORDS, and
    rewrite_bullets.py's own copies of both) -- every consumer now reads
    this one list, so they can't drift apart again. Empty for a profile
    that hasn't generated one yet; callers should degrade gracefully
    (e.g. treat every bullet as belonging to no specific tag) rather than
    assume a non-empty list."""
    return profile_yaml(profile).get("tags") or []


def env_path(profile: str = None) -> str:
    """Path to this profile's own .env (GEMINI_API_KEY, JOBRIGHT_COOKIE_STRING,
    etc.) -- every script's load_dotenv() call points here instead of a
    single project-root .env, so two profiles sharing one checkout can
    each carry their own API key/cookie without colliding. Missing file is
    not an error here (load_dotenv() itself already handles that
    gracefully) -- callers surface their own clear error the first time
    they actually need a var that isn't set."""
    return os.path.join(profile_root(profile), ".env")


SIGNATURE_EXTENSIONS = (".png", ".jpg", ".jpeg")


def signature_path(profile: str = None) -> str | None:
    """Path to this profile's own optional handwritten-style signature
    image (profiles/<name>/signature.{png,jpg,jpeg}), or None if the
    profile hasn't dropped one in -- render_coverletter() treats None as
    "render with no signature image," never an error. Checks each
    extension in SIGNATURE_EXTENSIONS in order, returns the first that
    exists."""
    root = profile_root(profile)
    for ext in SIGNATURE_EXTENSIONS:
        candidate = os.path.join(root, f"signature{ext}")
        if os.path.exists(candidate):
            return candidate
    return None


def jds_dir(profile: str = None) -> str:
    return os.path.join(PROJECT_ROOT, "jds", profile or active_profile())


def output_dir(profile: str = None) -> str:
    return os.path.join(PROJECT_ROOT, "output", profile or active_profile())


def checkpoints_dir(profile: str = None) -> str:
    return os.path.join(output_dir(profile), "checkpoints")


def data_dir(profile: str = None) -> str:
    return os.path.join(PROJECT_ROOT, "data", profile or active_profile())


def applications_md_path(profile: str = None) -> str:
    return os.path.join(data_dir(profile), "applications.md")


def tracker_csv_path(profile: str = None) -> str:
    return os.path.join(jds_dir(profile), "jd_tracker_log.csv")


def sync_roots(profile: str = None) -> list:
    """Returns [(label, path), ...] for the profile-scoped directories a
    multi-computer sync tool (Syncthing) should be pointed at -- see
    CLAUDE.md's "Multi-computer sync" section for the full design. Kept
    as one place so write_sync_ignore_files() and any future sync
    tooling can't drift apart on what "this profile's synced data" means.
    Deliberately excludes nothing (not even .env or signature.*) --
    Syncthing is direct device-to-device and encrypted in transit, so the
    git-secrecy reason those are gitignored doesn't apply to it."""
    name = profile or active_profile()
    return [
        ("profile", profile_root(name)),
        ("jds", jds_dir(name)),
        ("output", output_dir(name)),
        ("data", data_dir(name)),
    ]


_SYNC_STIGNORE_CONTENT = (
    "// Syncthing per-folder ignore file -- machine-local cruft that should\n"
    "// never sync between devices. Secrets/PII are deliberately NOT\n"
    '// excluded here; see CLAUDE.md\'s "Multi-computer sync" section for why.\n'
    "data.db-wal\n"
    "data.db-shm\n"
    "*.lock\n"
    "__pycache__\n"
    "*.pyc\n"
    ".DS_Store\n"
)


def write_sync_ignore_files(profile: str = None) -> None:
    """Ensures every directory sync_roots() names exists and carries a
    .stignore, so a profile is ready for Syncthing to point at without
    the user hand-authoring config per profile. Called once from
    bootstrap_bullet_bank.create_new_profile() for every new profile.
    Idempotent and non-destructive -- never overwrites an already-present
    .stignore, so hand-customization survives re-runs."""
    for _label, path in sync_roots(profile):
        os.makedirs(path, exist_ok=True)
        stignore_path = os.path.join(path, ".stignore")
        if not os.path.exists(stignore_path):
            with open(stignore_path, "w", encoding="utf-8") as f:
                f.write(_SYNC_STIGNORE_CONTENT)


def kb_snapshot_dir(profile: str = None) -> str:
    """profiles/<name>/knowledge_base/ has no backup or recovery path of
    its own (see B13 -- it's fully gitignored on purpose, and Syncthing
    propagates corruption rather than guarding against it), so
    kb_snapshot.snapshot_kb() needs somewhere durable to keep rotating
    pre-run copies. data/<name>/ is already a sync_roots() member for
    this profile's operational data (see tracker_csv_path()/
    applications_md_path()), so snapshots live under it rather than
    adding a fifth sync root."""
    return os.path.join(data_dir(profile), "kb_snapshots")


def maintenance_log_path(profile: str = None) -> str:
    """Where the Maintenance submenu persists "when did this task last
    run" per background/administrative task (doctor script, etc.) --
    already covered by .gitignore's existing `*_log.json` pattern, no
    gitignore change needed."""
    return os.path.join(profile_root(profile), "maintenance_log.json")


def ui_config_path(profile: str = None) -> str:
    """Where per-profile terminal-UI preferences persist -- today just the
    Nerd Font vs. Unicode icon-set choice from the first-launch prompt
    (B33), so it's asked once per profile and never again. Already covered
    by .gitignore's blanket `profiles/*/` pattern, no gitignore change
    needed."""
    return os.path.join(profile_root(profile), "ui_config.json")
