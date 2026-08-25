"""
schemas.py — Pydantic response schemas for resume-builder's Gemini calls.

Extracted out of orchestrator.py (F1, docs/review/master_audit_document.md):
these were previously defined inline inside a 4,200+ line module, forcing
any consumer that only wants a schema type to import orchestrator.py's
full dependency chain (pandas, numpy, requests, questionary, subprocess).
Pure data/response-shape definitions -- no pipeline logic lives here.
"""

from typing import List, Literal

from pydantic import BaseModel, Field


class BulletAuditSchema(BaseModel):
    action_taken: str = Field(
        description="The core objective action or task performed."
    )
    tools_used: List[str] = Field(
        description="Specific software, tools, or hard methodologies named."
    )
    metrics_claimed: str = Field(
        description="Any specific quantities, percentages, or numbers. Use 'None' if missing."
    )
    unsupported_claims: List[str] = Field(
        description="List of generic fluff phrases, buzzwords, or unmeasurable claims."
    )


class WorkExperience(BaseModel):
    title: str
    company: str
    period: str
    location: str = Field(
        default="", description="City, State or 'Remote'. Leave blank if unknown."
    )
    achievements: List[str]


class ResumeSchema(BaseModel):
    name: str
    role: str
    location: str
    skills: List[str]
    experience: List[WorkExperience]


class JDKeywordSchema(BaseModel):
    tools: List[str] = Field(
        description="Specific software, platforms, and tech stack e.g., Salesforce, Outreach.io, Figma."
    )
    hard_skills: List[str] = Field(
        description="Specific methodologies, metrics, and frameworks e.g., Lifecycle Marketing, A/B Testing, Pipeline Generation."
    )
    core_functions: List[str] = Field(
        description="Primary responsibilities and domain areas e.g., Content Governance, Enablement Training."
    )


class FitSubscores(BaseModel):
    functional_alignment: int = Field(
        description="1-5: direct match to core demonstrated work vs. weak/missing"
    )
    north_star_alignment: int = Field(
        description="1-5: fit to target role families vs. far from desired direction"
    )
    level_plausibility: int = Field(
        description="1-5: screen risk, not prestige; overqualified is safer than underqualified"
    )
    work_style_sustainability: int = Field(
        description="1-5: realistically sustainable/energizing vs. brute-force or burnout-prone"
    )
    tools_process_overlap: int = Field(
        description="1-5: overlap with JD's named tools/systems"
    )


class InterviewOddsSubscores(BaseModel):
    title_continuity: int = Field(
        description="1-5: does the resume's title path map cleanly onto this posting's title"
    )
    evidence_match: int = Field(
        description="1-5: can the resume prove the posting's core asks with concrete specifics"
    )
    domain_credibility: int = Field(
        description="1-5: does the company's world feel instantly credible for this candidate"
    )
    recruiter_legibility: int = Field(
        description="1-5: how quickly a recruiter can understand the match"
    )
    narrative_burden: int = Field(
        description="1-5: how little explanation is required before the match makes sense"
    )
    funnel_friction: int = Field(
        description="1-5: likely favorable vs. crowded/high-friction funnel"
    )


class PracticalPursueSubscores(BaseModel):
    remote_quality: int = Field(
        description="1-5: fully remote and workable vs. onsite/incompatible"
    )
    compensation_viability: int = Field(
        description="1-5: vs. stated target/floor, or likely range if unstated"
    )
    growth_value: int = Field(
        description="1-5: useful momentum/skill-building vs. likely dead end"
    )
    time_to_offer: int = Field(description="1-5: likely process speed/friction")
    company_reputation: int = Field(description="1-5: reputation/red flags")
    cultural_signals: int = Field(
        description="1-5: promising vs. concerning signals in the JD's own language"
    )
    posting_legitimacy_score: int = Field(
        description="1-5: confidence the posting is real, active, and worth energy"
    )


class FitEvaluationSchema(BaseModel):
    archetype: str = Field(
        description="Best-matching role archetype, or closest hybrid of two"
    )
    hard_blockers: List[str] = Field(
        description="Explicit disqualifying constraints found; empty list if none"
    )
    fit_subscores: FitSubscores
    interview_odds_subscores: InterviewOddsSubscores
    practical_pursue_subscores: PracticalPursueSubscores
    recommendation: Literal[
        "Strong pursue", "Selective pursue", "Low-priority pursue", "Skip"
    ]
    why: str = Field(
        description="2-4 plain-language sentences justifying the recommendation"
    )
    recruiter_read: str = Field(
        description="1-2 sentences on how a recruiter is likely to read this candidate for this role at first glance"
    )
    posting_legitimacy: Literal[
        "High Confidence", "Proceed with Caution", "Suspicious"
    ] = Field(description="Does this posting look real, active, and worth pursuing?")
    posting_legitimacy_notes: str = Field(
        description="1-2 sentences on the signals behind the posting_legitimacy assessment"
    )


class CapabilityEvaluationSchema(BaseModel):
    archetype: str = Field(
        description="Best-matching role archetype, or closest hybrid of two"
    )
    fit_subscores: FitSubscores
    capability_gaps: List[str] = Field(
        description="Conceptual capability gaps or narrative omissions; empty if none"
    )


class RecruiterEvaluationSchema(BaseModel):
    hard_blockers: List[str] = Field(
        description="Explicit disqualifying constraints found; empty list if none"
    )
    interview_odds_subscores: InterviewOddsSubscores
    practical_pursue_subscores: PracticalPursueSubscores
    prestige_tier: Literal["Tier-1", "Tier-2", "Tier-3"] = Field(
        description="Classification of the company size and volume risk"
    )
    recommendation: Literal[
        "Strong pursue", "Selective pursue", "Low-priority pursue", "Skip"
    ]
    why: str = Field(
        description="2-4 plain-language sentences justifying the recommendation"
    )
    recruiter_read: str = Field(
        description="1-2 sentences on how a recruiter is likely to read this candidate for this role at first glance"
    )
    posting_legitimacy: Literal[
        "High Confidence", "Proceed with Caution", "Suspicious"
    ] = Field(description="Does this posting look real, active, and worth pursuing?")
    posting_legitimacy_notes: str = Field(
        description="1-2 sentences on the signals behind the posting_legitimacy assessment"
    )
    ghost_job_red_flags: List[str] = Field(
        description="Explicit indicators of fake, stale, or evergreen listings; empty if none"
    )


class CoverLetterSchema(BaseModel):
    company_name: str = Field(
        description="The hiring company's name, exactly as it appears in the job description."
    )
    greeting: str = Field(
        description="e.g. 'Dear {Company} Hiring Team,' or a named hiring manager if the JD provides one."
    )
    contact_name: str = Field(
        default="",
        description="The specific hiring contact's name, only if the job description names one -- empty string otherwise.",
    )
    contact_title: str = Field(
        default="",
        description="That contact's job title, only if the job description states one -- empty string otherwise.",
    )
    body_paragraphs: List[str] = Field(
        description="2-3 first-person paragraphs, each grounded in a real JD requirement and a real fact from the background context."
    )
    sign_off: str = Field(description="e.g. 'Sincerely,'")


class VocabularySubstitution(BaseModel):
    generic_term: str = Field(
        description="The common/generic word the candidate's resume would normally use, e.g. 'customers'."
    )
    company_term: str = Field(
        description="The company's own preferred word for that same thing, e.g. 'guests'."
    )


class CompanyResearchSchema(BaseModel):
    overall_tone_adjective: str = Field(
        description="One short phrase describing the company's overall voice."
    )
    tone_register: Literal["formal", "conversational", "mixed"]
    pronoun_framing: Literal["we-centric", "you-centric", "mixed"]
    sentence_style: Literal["short and punchy", "long and flowing", "mixed"]
    jargon_density: Literal["high", "moderate", "low"]
    recurring_keywords: List[str] = Field(
        description="1-3 brand words/phrases that genuinely repeat in the source text."
    )
    company_facts: List[str] = Field(
        description="2-3 short, factual statements traceable directly to the source text."
    )
    company_hq_location: str = Field(
        default="",
        description="The company's headquarters city/state (e.g. 'New York, NY'), only if stated in the source text -- empty string otherwise.",
    )
    notable_highlights: List[str] = Field(
        default_factory=list,
        description="0-3 short, factual, impressive statements -- awards, funding, recognition, charitable/community work, notable stats, or recent/upcoming launches -- each traceable directly to the source text. Empty list if none genuinely qualify.",
    )
    vocabulary_substitutions: List[VocabularySubstitution] = Field(
        description="0-3 generic-term/company-term pairs where the source text clearly and repeatedly prefers its own word over the common one. Empty list if none genuinely qualify."
    )


class CritiqueSchema(BaseModel):
    accuracy_score: int = Field(
        description="0-100: specific, grounded, traceable claim"
    )
    believability_score: int = Field(
        description="0-100: would a skeptical hiring manager believe this?"
    )
    clarity_score: int = Field(description="0-100: immediately clear on first read")
    ats_value: int = Field(
        description="0-100: high-value ATS keywords without stuffing"
    )
    hidden_gem_score: int = Field(description="0-100: memorability and evidence rarity")
    hidden_gem_flag: bool = Field(description="true if hidden_gem_score >= 90")
    manager_test: str = Field(description="Strictly 'PASS' or 'FAIL'")
    weaknesses: str = Field(
        description="Specific explanation of flaws. 'None' if PASS with high scores."
    )
    hidden_gem_reason: str = Field(
        description="One sentence: what makes this a gem, or what holds it back"
    )


class RewriteSchema(BaseModel):
    rewritten_bullet: str = Field(
        description="Single rewritten resume bullet sentence."
    )
    reasoning: str = Field(default="", description="Explanation of changes made.")
    context_gaps: str = Field(
        default="", description="Missing context that limited the rewrite."
    )


class RewriteMinimalSchema(BaseModel):
    rewritten_bullet: str = Field(
        description="Single rewritten resume bullet sentence."
    )


class ResumeCritiqueSchema(BaseModel):
    summary_alignment_score: int = Field(
        description="0-100: does the Summary match the JD role and tone?"
    )
    skills_relevance_score: int = Field(description="0-100: are Skills JD-relevant?")
    overall_fit_score: int = Field(description="0-100: holistic resume-to-JD fit")
    top_third_score: int = Field(
        description="0-100: does the top third of page one alone communicate fit within a 15-30 second first read (first-impression / above-the-fold test)?"
    )
    flags: List[str] = Field(description="Specific issues found")
    recommendations: List[str] = Field(description="Actionable fixes, one per flag")
    distinctive_moments: List[str] = Field(
        description=(
            "2-3 EXACT sentences or achievement bullets already present in the "
            "resume, quoted verbatim, that read as memorable and "
            "personality-forward rather than generic. Protected from later "
            "automated recommendation edits."
        )
    )
    flat_sections: List[str] = Field(
        description=(
            "Section names (e.g. 'Professional Summary', 'VML experience') "
            "that read as competent but generic -- interchangeable with other "
            "candidates' resumes."
        )
    )
    # Step 1 (professional_identity_score.yaml) -- see B49/B50 in
    # phase-9-backlog.md: these outputs were named by critique_resume.md's
    # evaluation sequence but had no schema field to return them in, so
    # steps 1-6 were being silently discarded at the schema boundary.
    primary_identity: str = Field(
        description="Step 1: the detected primary professional identity/archetype."
    )
    secondary_identity: str = Field(
        description="Step 1: the detected secondary identity, if any. Empty string if none."
    )
    tertiary_identity: str = Field(
        description="Step 1: the detected tertiary identity, if any. Empty string if none."
    )
    competing_narratives: List[str] = Field(
        description="Step 1: any competing/conflicting identity narratives found. Empty if none."
    )
    unsupported_positioning: List[str] = Field(
        description="Step 1: any positioning claims not supported by the resume content. Empty if none."
    )
    # Step 2 (resume_cohesion_score.yaml)
    recruiter_takeaway: str = Field(
        description="Step 2: one-sentence recruiter takeaway from the cohesion check."
    )
    strongest_alignment: str = Field(
        description="Step 2: name of the strongest-passing alignment_check."
    )
    weakest_alignment: str = Field(
        description="Step 2: name of the weakest-passing (or failing) alignment_check."
    )
    # Step 5 (skills_scoring.yaml)
    ungrouped_skills: List[str] = Field(
        description="Step 5: skills present but not cleanly grouped under a category. Empty if none."
    )
    unsupported_skills: List[str] = Field(
        description="Step 5: skills listed with no evidence elsewhere in the resume. Empty if none."
    )
    archetype_mismatch: bool = Field(
        description="Step 5: True if the skills grouping/ordering doesn't match the style_rules_archetype from Step 1."
    )
    # Step 6 (ats_match.yaml platform_overrides) -- named platforms instead of
    # a per-platform numeric score for every one of them: a legacy ATS's real
    # behavior (section-header sensitivity, acronym handling) isn't fully
    # captured by three match-weight multipliers, so the actionable output is
    # "which platform is weakest and why," not five more scores to interpret.
    weakest_ats_platform: str = Field(
        description="Step 6: the single weakest-scoring platform from ats_match.yaml's platform_overrides, plus a one-sentence reason."
    )
    platform_parsing_risks: List[str] = Field(
        description="Step 6: concrete platform-specific parsing risks found (missing standard section header, unexplained acronym, a paraphrased-not-quoted JD requirement a strict platform wouldn't credit). Empty if none."
    )
    # B51: every reject_if.score_below / pass_threshold / hard_failures trip
    # across every attached rubric, so a resume that fails a rubric's own
    # stated bar has a channel to say so instead of shipping silently.
    hard_failures_triggered: List[str] = Field(
        description=(
            "Every reject_if.score_below, pass_threshold, or hard_failures rule "
            "(from any attached scoring/rules file) that this resume actually "
            "trips, each as '<rubric file>: <specific reason>'. Empty list if "
            "the resume clears every attached rubric's stated bar."
        )
    )


class CertItem(BaseModel):
    title: str = Field(description="Full certification or training name.")
    org: str = Field(description="Issuing organization.")
    year: str = Field(description="4-digit year, e.g. '2023'. Leave blank if unknown.")


class EducationItem(BaseModel):
    degree: str = Field(description="Degree or program name.")
    institution: str = Field(description="School or university name.")
    year: str = Field(
        default="", description="Graduation year or date range. Leave blank if unknown."
    )
    description: str = Field(
        default="", description="Honors, GPA, relevant coursework. Leave blank if none."
    )


class ExperienceEntry(BaseModel):
    """
    A previous version used EXPERIENCE: List[dict] to avoid nested $defs in
    responseSchema, believing Gemini's structured-output API couldn't handle
    them -- but a real run then got EXPERIENCE back as several empty {}
    objects: List[dict]'s per-item schema has no required properties at all,
    so an empty object is entirely valid against what Gemini actually
    receives (the Field description explaining title/company/achievements
    lives only in Pydantic metadata, which GeminiClient.sanitize_schema()
    strips before submission). The real cause of the earlier 400 was
    sanitize_schema() deleting $defs unconditionally, leaving nested models'
    $ref pointers dangling -- fixed by GeminiClient.resolve_refs(), which
    inlines $ref/$defs before sanitize_schema runs. This model now lets
    "required" actually reach the API.
    """

    title: str = Field(
        description="Job title, reframed per this JD's archetype if applicable."
    )
    company: str = Field(
        description="Company name, exactly as used in tailor_resume.md's per-role bullet targets."
    )
    period: str = Field(description="Employment dates, MM/YYYY - MM/YYYY format.")
    location: str = Field(
        default="", description="City/state or Remote. Leave blank if unknown."
    )
    achievements: List[str] = Field(
        description="Achievement bullets for this role. Must not be empty."
    )
    career_note: str = Field(
        default="",
        description="Auto-filled after generation for Treering Yearbooks by normalize_resume; always output empty string here.",
    )


class TemplateSchema(BaseModel):
    """
    Flattened schema for the builder call.
    NAME/PHONE/EMAIL/LINKEDIN_DISPLAY/LOCATION are not builder
    fields -- contact info doesn't vary by JD, so it's hard-coded in
    fixed_content.CONTACT_INFO and force-applied by normalize_resume,
    same pattern as Certifications/Education/company facts. There is no
    PORTFOLIO_URL/PORTFOLIO_DISPLAY field at all -- the portfolio link was
    removed resume-wide.
    """

    TAGLINE: str = Field(description="Max 80 chars. Follows archetype tagging rules.")
    SECTION_SUMMARY: str = Field(default="Professional Summary")
    SUMMARY_TEXT: str = Field(
        description="Max 5 lines. First sentence MUST be bolded using <strong> tags. No generic filler."
    )
    SECTION_EXPERIENCE: str = Field(default="Work Experience")
    EXPERIENCE: List[ExperienceEntry] = Field(
        description=(
            "One entry per company. Bullet counts per role must match the "
            "ROLE RULES block's Per-Role Bullet Count Targets table exactly."
        )
    )
    # No KU/KCKCC-named achievement-key fields here -- those were Morgan-
    # specific and hardcoded (both the field names and their Literal enum
    # values) directly into this class, which every profile's builder call
    # shares. The generic replacement -- EDU_ACHIEVEMENT_KEY_<n>, one per
    # profile.yml education entry that offers a pre-approved achievement-
    # bullet choice -- is built per-profile at call time by
    # ResumeEngine.build_education_achievement_schema_fields() and merged
    # into this schema via GeminiClient.generate()'s extra_schema_properties/
    # extra_required, not declared as static fields here. See that method's
    # docstring for why a plain str field wouldn't work (sanitize_schema()
    # strips `description`, so only a real `enum` constraint survives to
    # Gemini -- and the valid enum values differ per profile, unknowable at
    # this class's definition time).
    SECTION_SKILLS: str = Field(default="Skills")
    SKILLS: List[str] = Field(description="Technical skills mapped to JD.")
    SECTION_WHY: str = Field(
        default="",
        description=(
            "'Why [Real Company Name]?' -- ONLY set if space allows on a 2-page "
            "resume; leave blank ('') to omit the section entirely."
        ),
    )
    WHY_TEXT: str = Field(
        default="",
        description=(
            "Two short paragraphs (as HTML <p> tags), max 8 lines total, "
            "first-person voice -- the only section where pronouns are allowed. "
            "Only the first sentence of the first paragraph and the last "
            "sentence of the last paragraph are wrapped in <em> tags. Must "
            "reference specific company research connected to verified facts. "
            "Leave blank ('') to omit the section entirely if it would push "
            "the resume to 3 pages."
        ),
    )


class RecommendationApplySchema(TemplateSchema):
    """
    Same shape as a normal builder/trim call (TemplateSchema), plus three
    tracking lists so the holistic critique's recommendations can be acted
    on without silently doing something the recommendation never asked for.
    Only recommendations that are concrete edits to this resume's own
    content belong in applied_recommendations -- anything describing an
    action outside the document (networking, referrals, applying elsewhere)
    must go in skipped_recommendations untouched. A recommendation phrased
    as a reflective question about personal motivation/meaning that can't
    be grounded in the provided background context goes in
    needs_personal_input instead of being fabricated.
    """

    applied_recommendations: List[str] = Field(
        default_factory=list,
        description="Exact text of each recommendation that was a resume-content edit and was applied.",
    )
    skipped_recommendations: List[str] = Field(
        default_factory=list,
        description="Exact text of each recommendation that was not a resume-content edit, so nothing was changed for it.",
    )
    needs_personal_input: List[str] = Field(
        default_factory=list,
        description=(
            "Recommendations that ARE actionable edits to this resume's own "
            "content, phrased as a reflective question about personal "
            "motivation/meaning, but for which the provided background context "
            "does not already contain a grounded, verified answer. Left "
            "unapplied rather than inventing an answer -- exact original text "
            "here so Morgan can address it herself (e.g. via `resume polish`)."
        ),
    )


class FactItemSchema(BaseModel):
    """A single factual career claim extracted for staging and human verification."""

    label: str = Field(
        description="Short, descriptive label for this factual claim or initiative"
    )
    claim: str = Field(
        description="Concrete, verifiable claim detailing what was built, led, or achieved"
    )
    source: str = Field(
        default="",
        description="Source document name, meeting note reference, or artifact ID",
    )
    confidence: Literal["High", "Medium", "Low"] = Field(
        default="High",
        description="Confidence level in factual accuracy based on source evidence",
    )
    use_in_resume: bool = Field(
        default=True,
        description="Whether this fact is suitable for inclusion in resume bullets",
    )
    caveat: str = Field(
        default="",
        description="Specific boundaries, co-author splits, or caveats for external presentation",
    )
    category: str = Field(
        default="general",
        description="Functional category (e.g., leadership, platform_ops, enablement, content)",
    )


class StagedFactsExtractionSchema(BaseModel):
    """Collection of candidate facts extracted from career documents for the D10 staging gate."""

    facts: List[FactItemSchema] = Field(
        default_factory=list,
        description="Extracted candidate factual claims awaiting human review",
    )
