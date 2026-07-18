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
    "LINKEDIN_DISPLAY": "linkedin.com/in/morganescott",
    "LOCATION": "Getzville, NY (Buffalo Area)",
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
    # Situational/optional entries -- rare, deliberate use only (see
    # tailor_resume.md's "Situational/Optional Work History Entries"
    # section). No size_revenue: cv.md doesn't record it for these roles
    # either, so omitting rather than guessing.
    "Humane Society of Greater Kansas City": {"location": "Kansas City, MO"},
    "Unisource Document Products": {},
    "Kansas Colloquies": {"location": "Bonner Springs, KS"},
    "KU Payroll Office": {"location": "Lawrence, KS"},
    "DeJoy, Knauff & Blood": {"location": "Rochester, NY"},
    "USitek": {},
}

# Job-title parenthetical industry/role-type descriptors don't vary by JD --
# they're a fixed tag appended after whatever title (additive or plain) the
# builder produces for that company, per resume_example.pdf. Applied
# automatically by normalize_resume regardless of which Job Title Reframing
# format tailor_resume.md's builder chose for the title itself.
COMPANY_TITLE_DESCRIPTOR = {
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

# Client rosters don't vary by JD either. VML and Callahan Creek are
# "essential" -- always rendered.
CLIENTS = {
    "VML": {
        "list": "SAP, Equinix, HughesNet, The Children's Place, Welch Allyn, Waste Management, Carlson Hotels, Gatorade",
        "essential": True,
    },
    "Callahan Creek": {
        "list": "Hill's Pet Nutrition, CommunityAmerica Credit Union, Sprint, Dave Ramsey, Free State Brewery, KC Ad Club",
        "essential": True,
    },
}

# Some former employers were later acquired/renamed -- note that in the
# job-meta company line as "<Company> (Now <NewName>)", per resume_example.pdf.
COMPANY_RENAME_NOTE = {
    "Inside Sales Team": "Alleyoop",
    "Callahan Creek": "BarkleyOKRP",
}

# Element 8 / Strategy LLC's title doesn't vary by JD -- it's fixed to show
# the real in-role progression (Design Assistant promoted to Lead Designer)
# rather than being left to the builder's Job Title Reframing judgment call.
COMPANY_FIXED_TITLE = {
    "Element 8 / Strategy LLC": "Design Assistant → Lead Designer",
}

# Deeply personal, sensitive content describing a real health/caregiving
# situation -- hard-coded rather than left for an LLM to freshly paraphrase
# every run, given the risk of mangling tone on something this sensitive.
# Always follows CAREER_NOTE_COMPANY's entry, after its bullets.
CAREER_NOTE = (
    "After a fulfilling run at Treering, I took time in 2024–25 to support a loved one's "
    "health and invest in my professional growth. I'm excited to return to work with "
    "renewed focus."
)
# Which company's entry gets CAREER_NOTE attached (normalize_resume.py
# matches on this exact string, not a hardcoded company name) -- empty
# string is a valid "no career note" default for a profile that doesn't
# need one.
CAREER_NOTE_COMPANY = "Treering Yearbooks"

CERTIFICATIONS = [
    {"title": "Email Marketing Software Certification", "org": "HubSpot", "year": "2026"},
    {"title": "Video for Sales Certification", "org": "Vidyard", "year": "2021"},
    {"title": "Camp Portfolio", "org": "Bernstein Rein, Kansas City", "year": "2008"},
]

# Maps role/company keywords (matched case-insensitively as substrings of
# a bullet's Role/Company value) to the exact "### <heading>" line that
# starts that company's section in cv.md -- orchestrator.py's
# extract_cv_section() uses this to excerpt just the relevant section
# instead of sending the whole file on every bullet.
CV_SECTION_KEYWORDS = [
    (["treering", "tree ring", "yearbook"], "Treering Yearbooks"),
    (["inside sales", "alleyoop", "ist"],   "Inside Sales Team"),
    (["usitek"],                             "USitek"),
    (["element 8", "strategy llc"],         "Element 8"),
    (["vml"],                               "VML"),
    (["callahan"],                          "Callahan Creek"),
    (["unisource", "udp"],                  "Unisource"),
    (["humane society"],                    "Humane Society"),
    (["mercor"],                            "Mercor"),
]

KU_ACHIEVEMENT_OPTIONS = {
    "content_generalist": "Marketing Intern, Lied Center of Performing Arts, drove 800% social media follower growth through organic content strategy and audience engagement",
    "email_ops":          "Marketing Intern, Lied Center of Performing Arts, managed promotional campaigns and digital channels, growing social media following by 800%",
    "content":            "Marketing Intern, Lied Center of Performing Arts, produced editorial and promotional content across channels, built early instinct for audience-specific messaging",
}

KCKCC_ACHIEVEMENT_OPTIONS = {
    "writing_content": "Editor-in-Chief, student newspaper for 1.5 years, assigned coverage, led editorial team, and managed weekly publication from story conception through print",
    "enablement_mgmt": "Editor-in-Chief, student newspaper, led a team of reporters and columnists, managed editorial calendar, and upheld writing and voice standards across all content",
    "generalist":      "Editor-in-Chief, Kansas Colloquies student newspaper, managed publication end-to-end for 1.5 years while maintaining a full academic scholarship",
}


# Persona/background context injected into the audit-loop's per-bullet
# rewrite prompts (orchestrator.py's build_background_summary()).
# BACKGROUND_IDENTITY is always included; BACKGROUND_TAGS entries are
# added only when their bracketed tag (matching TAG_CONTEXT's keys)
# appears in the bullet's own tags.
BACKGROUND_IDENTITY = """
Morgan is a creative and strategic marketer with 10+ years of experience spanning journalism,
design, agency work, sales, CRM, and lifecycle content. She is the rare combination: writes
campaigns that perform AND operates the stack (Salesforce + Outreach.io). She brings structure
to creative work and energy to technical systems. She is seeking fully remote IC roles — not
management. She has consistently been the person companies come back to: Callahan Creek extended
her from intern to freelance; Element 8's CEO recruited her to lead Strategy LLC branding;
Treering headhunted her directly from IST.
""".strip()

BACKGROUND_TAGS = {
    "[email]": """
Email / Lifecycle context:
- Owned Outreach.io as primary admin: evaluated vendors, led integration with Salesforce, drove
  team-wide adoption for a 20+ person SDR org.
- Built 62+ sequences across 4 major categories (PTA, Hot Zone, Private School, Title 1).
- PTA Council: 74% open / 22% reply / 0 opt-outs. HZ Spring 1st Touch: 85% open / 39% reply.
- Jan 2022 run: 63% avg open across 6 sequences, 8.7% reply, 3,337 prospects added.
- Personalization at scale: variable logic, behavioral triggers, segmentation by district type.
- A/B tested subject lines, CTAs, and send windows systematically.
""".strip(),
    "[ops]": """
Ops / CRM context:
- Salesforce Classic & Lightning: territory management, pipeline reporting, data hygiene at scale.
- Uncovered $3M+ in stale pipeline via systematic CRM scrub; defined KPIs, dashboards, scope.
- National Hot Zone analysis: identified high-propensity districts using Salesforce data;
  trained team on strategy; the program scaled into a dedicated research function.
- Managed 2,000+ accounts simultaneously while also managing a 4-6 person SDR team.
- Led Outreach.io/Salesforce integration: data migration, deduplication, field mapping.
""".strip(),
    "[content]": """
Content / Enablement context:
- Founded and chaired the Content Committee: cross-department body owning brand voice,
  sequence library (100+ assets), campaign QA, and content governance.
- Built voice/tone guidelines adopted team-wide; peers held to Morgan's standard as benchmark.
- Created SDR Process Map (escottmorgan.wixsite.com/processmap) — official new-hire training.
- 100+ email campaigns across niche audiences, each with unique messaging and multi-touch logic.
- Designed branded slide decks for all monthly team trainings (20+ employees); consistently
  received outstanding feedback on quality and engagement.
""".strip(),
    "[enablement]": """
Enablement / Training context:
- Developed and delivered live + async training for 20+ employees on messaging, QA, platforms.
- Created the SDR Process Map website used as official onboarding infrastructure.
- Produced onboarding playbooks, interview guides, and campaign frameworks.
- Coached a remote pod of 4-6 SDRs on sequencing strategy, CRM hygiene, and territory work.
- Content Committee governed all sales content: 100+ assets, 129 sequences, QA checklists.
""".strip(),
    "[sales]": """
Sales / SDR context:
- First outbound hire to surpass $1M in sourced revenue at Treering; exceeded Year 1 target by 17%.
- 2x Top Seller at Inside Sales Team (now Alleyoop); Top 10 company-wide in first 2 months.
- Promoted within 6 months at IST to sole manager of a 12-person SDR team.
- Treering recruited Morgan directly from IST based on exceptional performance.
- Managed 2,000+ accounts; coached a pod of 4-6 SDRs on prospecting and outreach.
""".strip(),
    "[brand]": """
Brand / Agency context:
- VML (global ad agency): campaigns for Gatorade, SAP, HughesNet; pitch deck praised by CEO;
  wrote 200+ page digital strategy report for Carlson Hotels.
- Callahan Creek: worked in a real creative pod (copywriter, art director, designer); 2 campaigns
  selected for client rollout; extended to long-term freelance.
- Built Treering's voice/tone guidelines and Content Committee governance from scratch.
""".strip(),
    "[design]": """
Design context:
- Adobe Illustrator, Photoshop, InDesign: conference flyers, brand decks, COVID response flyer
  (posted on Treering homepage), monthly training decks, Georgia PTA council presentation.
- Element 8 / Strategy LLC: designed complete brand identity from scratch; still in use 15+ years later.
- Lead Graphic Designer title at Strategy LLC; recruited specifically by the CEO for the role.
- Canva, Figma (basic), CMS/WYSIWYG editors also in toolkit.
""".strip(),
    "[generalist]": """
Generalist / cross-functional context:
- Range: journalism foundation (KU BS), agency copywriting (VML, Callahan Creek), graphic design
  (Element 8/Strategy LLC), B2B SaaS sales + CRM (Treering 8 years), AI data work (Mercor).
- Comfortable moving between writing, ops, design, and strategy without losing quality in any lane.
- Non-Treering experience spans EdTech, regulated financial copy (CACU), K-12/education audiences,
  nonprofit (Humane Society of KC), print/publishing.
""".strip(),
}


def build_education(achievement_keys: dict = None) -> list[dict]:
    """
    Assembles the fixed 3-item Education list. `achievement_keys` maps
    institution name (exactly as written in profile.yml's
    fixed_credentials.education) to the selected achievement-bullet key for
    that school -- see profile_paths.education_achievement_slots(), which
    is what numbers the EDU_ACHIEVEMENT_KEY_<n> fields the builder actually
    answers against and normalize_resume.py maps back into this dict. A
    missing or unrecognized key falls back to that school's first option
    rather than raising, since every option is genuine, verified content --
    an archetype-suboptimal pick is a quality issue, not a truthfulness one.
    """
    achievement_keys = achievement_keys or {}
    ku_achievement_key = achievement_keys.get("University of Kansas", "")
    kckcc_achievement_key = achievement_keys.get("Kansas City Kansas Community College", "")

    if ku_achievement_key not in KU_ACHIEVEMENT_OPTIONS:
        print(f"  ⚠️  WARNING: unrecognized KU achievement key {ku_achievement_key!r}, falling back to first option.")
    ku_bullet = KU_ACHIEVEMENT_OPTIONS.get(
        ku_achievement_key, next(iter(KU_ACHIEVEMENT_OPTIONS.values()))
    )
    if kckcc_achievement_key not in KCKCC_ACHIEVEMENT_OPTIONS:
        print(f"  ⚠️  WARNING: unrecognized KCKCC achievement key {kckcc_achievement_key!r}, falling back to first option.")
    kckcc_bullet = KCKCC_ACHIEVEMENT_OPTIONS.get(
        kckcc_achievement_key, next(iter(KCKCC_ACHIEVEMENT_OPTIONS.values()))
    )
    return [
        {
            "degree": "BS, Journalism + Strategic Communication",
            "institution": "University of Kansas",
            "location": "Lawrence, KS",
            "year": "2006 – 2008",
            "bullets": [
                "3.56 GPA, Phi Theta Kappa Scholarship recipient",
                ku_bullet,
            ],
        },
        {
            "degree": "AA, Journalism",
            "institution": "Kansas City Kansas Community College",
            "location": "Kansas City, KS",
            "year": "2004 – 2006",
            "bullets": [
                "3.75 GPA, Full academic scholarship, Graduated with honors",
                kckcc_bullet,
            ],
        },
        {
            "degree": "Coursework, Graphic Design",
            "institution": "Johnson County Community College",
            "location": "Overland Park, KS",
            "year": "2010 – 2011",
            "bullets": [
                "3.86 GPA, studied color theory, typography, illustration, 3D concepts, desktop publishing, and film photography",
            ],
        },
    ]
