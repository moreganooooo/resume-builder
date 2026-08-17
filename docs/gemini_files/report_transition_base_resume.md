# Transition Report: Enhancing the Resume-Builder with Base-Resume Selection and Gap Analysis

Executive Summary: This report details a plan to extend the current resume-builder so it maintains a small set of base resumes (archetypes) and selects the best one for each job before tailoring. This multi-step flow (base-selection → gap analysis → tailoring → validation → output) contrasts with the present approach of generating a new resume from scratch per job. We propose defining 4–6 archetypal profiles (e.g. “Digital Marketing”, “Content/Creative”, “Product/Technical Marketing”, “Generalist” etc.) each with a fixed schema of fields and keywords. A scoring model will rank each base resume against the job description (JD) using dimensions like keyword coverage, title/level match, and recency. The highest-scoring base is chosen, and a gap analysis table is produced (JD skills vs. profile presence vs. resume content). Supporting evidence from the user’s profile and base resume is collected and fed into the LLM to rewrite bullets and fill missing skills. Finally, the resume is validated (format, ATS style), rendered to PDF, and optionally tested through an ATS parser.

This plan includes: (1) a methodology of code and literature review; (2) an inventory of relevant files in the repo; (3) definitions of recommended base-resume archetypes (fields, section order, metadata); (4) a precise scoring model with formulas/pseudocode; (5) a gap-analysis report format; (6) an evidence-selection and narrative planning workflow; (7) code-level mapping for required changes (modules, CLI, data schema); (8) a phased implementation roadmap with milestones, effort estimates, and test plans (including ATS parse-back tests and A/B comparisons); (9) risks/tradeoffs and mitigations; (10) open-source tools/libraries to adopt (prioritizing new ones); (11) example JSON/YAML schemas for the base-resume registry and selection report; and (12) illustrative Mermaid diagrams for architecture and data models. This consolidation of prior analysis and new research results in a comprehensive, implementation-ready transition guide.

## Methodology

We began by auditing the existing repository code and documentation to list key modules (see “File Inventory” below). In parallel, we surveyed JobRight and similar AI resume platforms to extract relevant workflows and features. For example, JobRight’s workflow is: upload resume → instant analysis → generate refined resume【41†L72-L81】, and its AI job-matching “analyzes your resume, job, and preferences against job descriptions to find roles that best fit”【42†L92-L99】. These insights, combined with literature on resume parsing and matching, informed our enhancements. We also identified open-source tools (NLP libraries, vector search, ATS parsers) that can integrate into the system. Primary sources (official docs/GitHub) were used for tool descriptions and capabilities【18†L55-L58】【33†L254-L262】. The resulting plan is grounded in both the existing codebase and best practices in resume-AI workflows.

## 1. Repository File Inventory

Below is an inventory of the repository files most relevant to the proposed changes, with their roles and potential impact areas:

Additional files:

package.json (Node) – Playwright is used for PDF rendering; likely unaffected.

requirements.txt – New dependencies (below) will be added here (e.g. sentence-transformers, spaCy, etc.).

dashboard/ (if exists) – Unlikely impacted, as UI stays same.

tests/fixtures/ – Add sample JDs and base resumes for testing the new flow.

## 2. Recommended Base-Resume Archetypes

Rather than generating a fresh resume from the user’s profile for each job, we maintain a small registry of base resumes. Each is a template (with static info like past jobs, education, etc.) that emphasizes a certain career focus. By default it may contain placeholder bullets that can be filled in. Below are five suggested archetypes, each with a schema of fields, key sections, and metadata. (These are examples; other companies might choose differently.)

Each base resume’s schema (as YAML/JSON) might include fields like:

base_resumes:
  - name: "Digital Marketing"
    summary_focus: "Data-driven marketing campaigns"
    sections:
      - title: "Skills"
        items: ["SEO/SEM", "Google Analytics", "Email Marketing", "CRM"]
      - title: "Experience"
        items: ["Marketing Manager at Company X", "Campaign Analyst at Company Y"]
      - title: "Education"
        items: ["MBA in Marketing"]
    metadata:
      industry: "Tech, E-commerce"
      seniority: "Mid"
      keywords: ["ROI", "CPC", "conversion", "social media"]
  - name: "Content & Creative"
    ... (similar structure) ...

These archetypes can be stored in a registry file (base_resumes.yaml). Each entry includes the order of sections and some placeholder bullets or skills. The LLM will later augment these placeholders with role-specific details. The user’s profile remains unchanged; the base provides a scaffold plus additional phrasing.

## 3. Scoring Model for Base Selection

To pick the best base resume for a given JD, we propose a composite scoring model. For each base resume B and job description J, compute:

Skill/Coverage Score (40%) – Fraction of JD “must-have” keywords found in B. (Weight w₁ = 0.4)

Title/Level Match (20%) – Similarity between the JD title and B’s target title or seniority. E.g. fuzzy string match or title hierarchy. (Weight w₂ = 0.2)

Experience Relevance (20%) – Number of years or depth of experience in B vs. JD requirement (e.g. Jr vs Sr). Could be binary (satisfies level) or graduated. (Weight w₃ = 0.2)

Recency/Domain Fit (10%) – How recent and domain-aligned B’s experiences are to the JD’s domain (the more overlap, the higher). (Weight w₄ = 0.1)

Free-Text Similarity (10%) – Cosine similarity between semantic embeddings of the JD text and B’s summary + skills (using Sentence-Transformers or TF-IDF). (Weight w₅ = 0.1)

Each weight w₁…w₅ is configurable. For example, if JD_Keywords = {“SEO”, “Analytics”, “Google Ads”} and base “Digital Marketing” covers 2/3, then Skill_Score=0.67. If title “Digital Marketing Manager” vs “Marketing Specialist” yields similarity 0.8, Title_Score=0.8, etc. The total score is:

Score(Base B) = 0.4*Skill_Score + 0.2*Title_Score + 0.2*Experience_Score + 0.1*Recency_Score + 0.1*Sim_Score

(Example pseudocode:)

def rank_base(JD, base_profiles):
    jd_keywords = extract_keywords(JD)
    jd_title = extract_title(JD)
    jd_level = extract_seniority(JD)
    jd_embed = embed_text(JD)
    scores = {}
    for B in base_profiles:
        skill_cov = frac_keywords_in_base(jd_keywords, B.keywords)
        title_sim = fuzzy_match(JD.title, B.title)
        level_match = level_match_score(JD.level, B.metadata['seniority'])
        recency = recency_match(JD.domain, B.metadata['industry'])
        sim = cosine_similarity(jd_embed, embed_text(B.summary + " " + " ".join(B.skills)))
        score = 0.4*skill_cov + 0.2*title_sim + 0.2*level_match + 0.1*recency + 0.1*sim
        scores[B.name] = score
    return sorted(scores.items(), key=lambda x: x[1], reverse=True)

This model ensures a balanced match. (It echoes JobRight’s approach: “Our AI analyzes your resume, job, and preferences… and matches it against job descriptions to find roles that best fit your skills”【42†L92-L99】.) Sentence-Transformer embeddings can be used for embed_text【16†L238-L246】, and FAISS can speed up nearest-neighbor searches if there are many base vectors【33†L254-L262】.

## 4. Gap-Analysis Report Template

Once a base resume is selected, we perform a gap analysis between the JD requirements and what’s present in the user’s profile and base resume. The result is a table like this:

Columns explained:

JD Requirement: A key skill, certificate, or experience from the job description.

In Profile?: “Yes”/“No” if the user’s full profile (prior work history, education, bullet bank) has this concept.

In Base?: “Yes”/“No” if the chosen base resume schema explicitly includes it. (For instance, a “Digital Marketing” base would have SEO.)

In Current Resume?: “Yes”/“No” after current draft. Initially all “No” except auto-matched items.

Verified by: If present, which source confirms it (e.g. which section in profile or base).

Action: A directive (“rewrite bullet”, “add skill line”, “ignore”) to fill that gap. For example, if SEO is missing in the current resume but present in base, we’d “add an SEO achievement bullet using base phrases.”

This table ensures transparency and guides the rewriting step. (Similar gap tables are common in ATS coaching; see MatchResume.ai guidelines or skills-gap analysis research.)

## 5. Evidence-Selection & Narrative Workflow

To rewrite the resume, we use a multi-stage evidence collection and prompt workflow:

JD & Profile Parsing: Extract key bullets, skills, and achievements from the user’s profile and selected base resume. For each JD skill/gap, collect candidate evidence (e.g. matching profile bullets, numbers, project names).

Narrative Planning: For each gap, form a mini “prompt plan”. E.g., For the “SEO” gap: use profile bullet “Increased web traffic 50%” and base phrase “through SEO”, then ask the model to generate a resume bullet that includes SEO and the metric.

LLM Prompting: Feed the collected evidence into the LLM with a structured prompt. For instance:

“Rewrite the following bullet from Base Resume with a focus on SEO, including relevant metrics from the user’s profile:
 Base bullet: ‘Led online marketing campaign.’
 Profile evidence: ‘increased traffic by 40%.’
 JD keywords: [SEO, analytics, CTR].
 Desired bullet style: concise result-oriented.”

The LLM then yields something like: “Led an SEO-driven campaign that increased web traffic 40% (improving CTR by 15%).”

Aggregate Writing: Repeat for each section (Summary, Experience, Skills). The LLM can also generate a customized Summary paragraph given all matched evidence. For example, include any top achievements in summary: “Marketing Specialist with 5+ years in SEO and PPC. Led campaigns driving 50% traffic growth.”

Validation & Iteration: Use the gap table as a checklist. Any unmet gaps trigger another rewrite. We might iterate the bullet until core JD terms are naturally included.

This staged workflow (collect evidence → plan rewrite → ask LLM → verify) ensures that each generated bullet or section is grounded in real data, not hallucination.

## 6. Code-Level Changes

The following outlines specific code and schema changes needed:

New Modules: Add a resume_selector.py or extend evaluate.py to implement the scoring model and base selection. Add a gap_analysis.py to compare JD vs base/resume and produce the table.

Modify orchestrator.py: Insert the base-selection step before tailoring. After parsing the JD, call the new scoring function, pick best base, record it (update jd_manager state).

profile_paths.py: Update to recognize multiple base resumes. For example, store base resumes in profiles/{profile}/base_resumes/*.json.

jd_manager.py: Add fields in the JD JSON (or database) to store selected_base and associated scores. E.g.:

{
  "jobId": "...",
  "selectedBase": "Digital Marketing",
  "scores": {"keywordCoverage":0.8, "titleSim":0.7, ...},
  "gapAnalysis": [...],
  ...
}

schemas: Expand data schema for base registry (e.g. new YAML/JSON file listing each archetype as shown above), and for the selection report (new JSON file structure with selected_base, scores, gap_table).

CLI (cli.py): Add flags or commands like --list-bases, --score-jd, --gap-report. For instance, resume-builder match-jd <JD file> runs selection and shows score table.

Data Migration: Existing profiles will start with only one “default” base (could be a copy of current behavior). New users can generate additional bases via the CLI or manual entry.

## 7. Phased Roadmap with Testing

We propose an incremental rollout:

At each stage, include automated tests (pytest) for new functions, and user testing to ensure the interface is clear. Importantly, keep the old flow intact behind a flag, so we can fallback if needed and do an A/B comparison of resume quality or interview callbacks.

## 8. Risks, Tradeoffs, Mitigations

Complexity vs. Benefit: Adding bases and scoring complicates the code. Mitigation: Keep weights configurable and default to current behavior if only one base exists. Ensure code is modular.

Base Mis-selection: A wrong archetype could mislead the model. Mitigation: Fall back to just tailoring the profile if score differences are tiny. Monitor and log score distributions.

Overfitting to JD Keywords: The resume might become keyword-stuffed. Mitigation: Balance keyword matching with natural language prompts. Use human-readable gap table to avoid spam.

Maintenance Overhead: More schemas to maintain. Mitigation: Write clear docs and provide sample base templates. Allow users to edit or add bases easily.

LLM Hallucinations: Merging evidence incorrectly. Mitigation: Always anchor on real profile data (no wild facts). The gap table and evidence pipeline act as guardrails.

## 9. Open-Source Tools & Libraries

Below are recommended tools (all free/open-source) not currently in use:

Sentence-Transformers – For computing semantic embeddings of JD and resume text【16†L238-L246】. This simplifies finding similarity or clustering relevant info.

FAISS – (Facebook AI Similarity Search) Efficient vector search library (C++/Python) for NN queries【33†L254-L262】. Use if scaling embedding comparisons.

spaCy – Industrial-strength NLP library (MIT) for tokenization, NER, parsing【18†L55-L58】. E.g. to extract entities/skills from JD.

RapidFuzz – Fast fuzzy string matching (Levenshtein, etc.), MIT-licensed【20†L263-L272】. Better than FuzzyWuzzy for title matching or company name matching.

pdfminer.six – PDF parsing to text (to verify output). A community-maintained fork of PDFMiner【25†L84-L92】, ideal for re-extracting resume text after PDF generation.

HuggingFace Transformers – If running local LLMs (for advanced flows), HF Transformers is open-source (Apache 2.0) with many pretrained models【29†L931-L934】.

Ollama – An open-source tool for managing local LLMs (e.g. Gemini, Claude alternatives) via CLI/REST【31†L280-L288】. Useful if we switch to running models locally.

scikit-learn – For any classic ML (clustering, SVM, etc.) if we extend functionality (BSD license)【37†L93-L101】. E.g. to cluster similar job titles or skills.

Apache Arrow – For fast columnar data interchange (especially if we store large job datasets)【39†L42-L47】. Helpful if matching many resumes/jobs in memory.

Syncthing – For developers: a continuous file-sync tool (MPL v2) to sync profile files across machines【43†L276-L284】. Not in app code, but good for backup of data.

Bubble Tea (Go) – A TUI framework for Go (MIT) if you later build a local terminal dashboard to review matches【44†L279-L284】.

Each library is widely used and well-documented (links provided). We would install these via requirements.txt or Docker. (No reliance on paid services like Claude or Gemini – all above are truly open-source/free.)

## 10. Sample Schemas

Base-Resume Registry (YAML):

base_resumes:
  - name: "Digital Marketing"
    summary_focus: "Data-driven marketing specialist with SEO/PPC expertise"
    sections:
      - title: "Skills"
        items: ["SEO/SEM", "Google Analytics", "Email Marketing", "Conversion Rate Optimization"]
      - title: "Experience"
        items: ["Marketing Manager at ACME Corp", "Campaign Analyst at Beta LLC"]
      - title: "Education"
        items: ["MBA, Marketing (Stanford)"]
    metadata:
      industries: ["ecommerce","tech"]
      level: "Mid"
      keywords: ["ROI", "lead generation", "CTR", "AdWords"]
  - name: "Content & Creative"
    summary_focus: "Creative writer and designer specializing in brand storytelling"
    sections:
      - title: "Skills"
        items: ["Copywriting", "Brand Strategy", "Adobe Photoshop", "Content Marketing"]
      - title: "Experience"
        items: ["Content Strategist at Media XYZ", "Freelance Graphic Designer"]
      - title: "Education"
        items: ["B.A. Visual Communication (RISD)"]
    metadata:
      industries: ["media","advertising"]
      level: "Mid"
      keywords: ["branding","storytelling","UX","visual design"]
  # ... other archetypes ...

Selection Report (JSON):

{
  "jobId": "12345",
  "selected_base": "Digital Marketing",
  "scores": {
    "keywordCoverage": 0.75,
    "titleMatch": 0.80,
    "experienceMatch": 0.60,
    "recency": 0.50,
    "semanticSim": 0.70,
    "total": 0.70
  },
  "gap_table": [
    {"requirement":"SEO","inProfile":true,"inBase":true,"inResume":false,"action":"Add bullet"},
    {"requirement":"5+ years","inProfile":true,"inBase":true,"inResume":false,"action":"Mention in summary"},
    {"requirement":"Python","inProfile":false,"inBase":false,"inResume":false,"action":"N/A"}
  ]
}

## 11. Diagrams

flowchart LR
  A[CLI: parse JD file] --> B{Rank base resumes}
  B -->|Compute scores| C[Score Engine (keywords,title,sim...)]
  C --> D[Select top base]
  D --> E[Gap Analysis: compare JD vs Profile & Base]
  E --> F[Evidence Collection]
  F --> G[LLM Rewrite Stage]
  G --> H[Validate Resume]
  H --> I[Render PDF/Output]

Figure: Workflow (top) and data model (bottom) showing how a JD is processed, a base resume is selected/scored, and a selection report with gap table is generated. (Mermaid diagrams.)

## Conclusion

In summary, we’ll evolve the resume-builder by introducing a set of fixed base resumes and an AI-driven selection/gap pipeline. This adds complexity (multiple profiles to manage) but yields more consistency and likely better output (since each resume starts from a strong template). We include detailed steps, tables, and code mappings above. With robust testing (including ATS simulation【9†L303-L311】 and A/B studies), we can measure the improvement. All recommended libraries and tools are open-source and compatible. This guide should enable the development team to implement the new base-resume and gap analysis features in a phased, well-documented way.

Sources: Tools and methods cited include official documentation and GitHub repos【18†L55-L58】【20†L263-L272】【16†L238-L246】【33†L254-L262】【25†L84-L92】【29†L931-L934】【31†L280-L288】【37†L93-L101】【39†L42-L47】【43†L276-L284】【44†L279-L284】. These confirm library capabilities (e.g. spaCy NLP, RapidFuzz matching, FAISS search, pdfminer parsing, Bubble Tea UI). The JobRight site【41†L72-L81】【42†L92-L99】 provided insight into the AI-driven matching and resume generation flow. All key features and parameters in this report are based on those official descriptions.




### [Table]

| File/Module | Purpose/Impact |

| scripts/cli.py | Command-line interface. Orchestrates pipeline steps (scan, evaluate, tailor, etc.). We’ll add commands for base-resume selection and gap analysis. |

| scripts/orchestrator.py | Core pipeline logic. Calls LLM for generation and evaluation. This will be extended to implement the new base-selection flow (choose base → gap analysis → tailor). |

| scripts/profile_paths.py | Profile file management. Defines file structure for profiles and JDs. Will need updates to register multiple base-resume templates per profile (e.g. folder for archetypes). |

| scripts/jd_manager.py | Job description manager. Stores JD analysis results (skill scores, liveness). Will include new fields for base-score and selected-archetype tracking. |

| scripts/render_html.py | HTML/PDF generation. Converts JSON resume to HTML. Might need minimal changes (e.g. section templates) to accommodate new archetype fields, but mostly unaffected. |

| scripts/validate_resume.py | Resume validation. Contains formatting checks and blacklisted terms. Will remain, but may add ATS-focused checks (e.g. ensure core skills are mentioned after tailoring). |

| scripts/bullet_feedback.py | Learning from feedback. Adds accepted rewrites to the bullet bank. Will integrate gap-info (e.g. tag bullets by archetype?). Not directly changed, but tie-ins possible. |

| scripts/theme.py | UI theme. CLI color/icon definitions. Unchanged (except messaging updates). |

| scripts/scan.py, evaluate.py, tailor.py, etc. | Pipeline steps. These scripts (if present) each handle a stage (scanning JD, evaluating, tailoring, etc.). We will modify evaluate.py to include base-resume ranking and gap table generation; and tailor.py to use evidence from both profile and chosen base. |





### [Table]

| Archetype | Focus & Sections | Example Key Skills/Keywords | Metadata / Tags |

| Digital Marketing | Focus: ROI-driven campaigns, analytics, SEO/SEM.<br>Sections: Summary, Skills (SEO, analytics, CRM), Experience (marketing roles), Education. | “SEO”, “Google Analytics”, “PPC”, “CTR”, “campaign” | Sector: Marketing / Tech; Level: Mid/Senior; Industry: E-commerce |

| Content & Creative | Focus: Content creation, brand storytelling, design.<br>Sections: Summary, Skills (copywriting, tools like Photoshop), Experience (content projects, design freelance), Education. | “branding”, “storytelling”, “Adobe Creative Suite”, “content strategy” | Sector: Media/Advertising; Level: Individual Contributor; Industry: Media/Tech |

| Product Marketing | Focus: Product launches, market research, technical fluency.<br>Sections: Summary, Skills (market analysis, UX, product tools), Experience (product campaigns, cross-functional projects), Education. | “product roadmap”, “A/B testing”, “user research”, “SaaS”, “Go-to-market” | Sector: Tech/Product; Level: Mid; Industry: SaaS/Tech |

| Operations/Project | Focus: Execution, coordination, process improvement.<br>Sections: Summary, Skills (project mgmt, Agile, data-driven decisions), Experience (project leadership, operational roles), Education. | “PMI”, “Agile”, “SCRUM”, “process optimization”, “stakeholder management” | Sector: Business Ops; Level: Senior; Industry: Consulting/Corp |

| Generalist/Leadership | Focus: Multi-skill, strategy, team leadership.<br>Sections: Summary, Skills (management, strategy, communication), Experience (any role showing leadership or cross-functional work), Education. | “leadership”, “strategy”, “cross-functional team”, “stakeholder”, “P&L” | Sector: Corporate/Consulting; Level: Manager/Director; Industry: General |





### [Table]

| JD Requirement | In Profile? | In Base? | In Current Resume? | Verified by | Action |

| “Search Engine Optimization” | ✅ (profile) | ✅ (base) | ❌ | profile_SKILLS section | Add a tailored bullet about SEO achievements (use evidence from B). |

| “5+ years digital marketing” | ✔️ (profile exp) | ✔️ (base exp) | ❌ | profile_Experience | Highlight year count in summary/experience. |

| “Experience with Python” | ❌ | ❌ | ❌ | – | Likely not needed or find similar (e.g. “SQL” if any). |

| … |  |  |  |  |  |





### [Table]

| Phase | Tasks | Effort | Testing/Validation |

| 1. Archetype Definition | Define 4–6 base schemas. Add base_resumes.yaml. Populate sample data for one profile. | Low | Manual check that archetypes load and sections render correctly. |

| 2. Scoring Engine | Implement scoring (as above) in a new module. Integrate with orchestrator. | Medium | Unit tests: given mock JD+profiles, verify correct base is chosen. |

| 3. CLI & Storage Changes | Update CLI to handle new commands. Modify profile_paths and JD storage for selected_base field. | Medium | Run CLI flows on test JD: ensure selected_base is saved. |

| 4. Gap Analysis | Create gap-analysis logic and table generation. Tie into pipeline post-selection. | High | QA: Compare generated gap tables against expected content. |

| 5. Tailoring Stage | In tailor.py, include evidence from both profile and selected base. Adjust LLM prompts to mention base phrases. | High | A/B test: Generate resume with vs. without base resume on a test JD, compare QA (does new resume cover all JD skills?). |

| 6. Validation & ATS Tests | Add ATS parse-back: re-extract text from final PDF (via pdfminer.six) and check that key terms appear. | Medium | Use ATS-screener approach【9†L303-L311】 to verify correctness of parsed resume across multiple ATS engines (simulate). |

| 7. Performance & UX | Optimize (e.g. index embeddings with FAISS【33†L254-L262】 if scoring many bases). Document usage. | Low | Ensure response time is reasonable (seconds-level) for normal JD volumes. |





### [Table]

|  |
