# Resume-Builder vs JobRight: Comprehensive Improvement Report

This report analyzes the current resume-builder pipeline and compares it against JobRight and related tools/research in resume generation, gap analysis, resume diagnosis, job matching, and ATS simulation. We surveyed the codebase and recent industry literature, and we propose prioritized, actionable improvements. Key findings: the existing system has a solid pipeline and strict truth-guardrails, but it can be enhanced with richer analysis (gap coverage, semantic checks, parse testing, and smarter matching). The recommendations below preserve the project’s factual integrity while making it far more useful and user-friendly.

## 1. Current System Overview

The resume-builder repo is a local CLI-driven pipeline with these major components:

Data/Profile Management: Each user profile has its own workspace (handled by profile_paths.py), containing the base resume, a bullet bank (evidence-backed bullet points), stored JDs, and output files.

CLI (scripts/cli.py): Exposes commands like run, scan, evaluate, tailor, coverletter, liveness, polish, and a web dashboard. Each invokes the orchestrator or helper scripts.

Orchestrator (orchestrator.py): Central coordination logic. It loads the profile and JD data, invokes LLM-based services (via Gemini REST) for tasks like critiquing and rewriting resumes, manages the pipeline flow (scan → evaluate → tailor → render → track), and persists results. Crucially, it separates the LLM prompts into critique vs. rewrite stages and enforces deterministic validation after generation.

JD Manager (jd_manager.py): Persists job application state and scores. It stores each JD’s metadata, match scores, application status, and liveness info in JSON.

Resume Rendering (render_html.py + Playwright): Converts the tailored resume HTML into PDF. Ensures consistent formatting (fonts, spacing) via a Node/Playwright step.

Validation (validate_resume.py): Rule-based checks on the resume text. This flags forbidden phrases, duplicate verbs, personal pronouns, tagline length, bullet length, and other ATS-breaking patterns. It prevents false or inflated claims (e.g. no invented metrics).

Bullet Feedback (bullet_feedback.py): After an LLM rewrite or user edit, accepted bullets can be fed back into the bullet bank for future reuse.

Tests & Fixtures: The repo includes unit tests (e.g. for validation rules) and sample PDF/HTML output for sanity checks.

Overall, the system is unusually disciplined: it avoids any “hallucinated” content by design. For example, validate_resume.py enforces strict formatting and content rules, and the prompts always emphasize evidence from the user’s bullet bank. This contrasts with many generic AI builders (which often produce plausible-sounding but unverifiable text). However, the current focus is mostly on structure and factuality, not on deeper semantic analysis or ATS simulation. In short: the process is strong, but the intelligence (planning, diagnosis, matching) can be enhanced.

## 2. Literature and Tool Survey

To inform improvements, we reviewed JobRight’s descriptions and broader sources:

JobRight & AI Tools: JobRight claims to match jobs semantically to your real skills and to generate ATS-friendly tailored resumes. (Their site highlights “personalized AI job matches” and “tailored resume that passes ATS”【12†L58-L66】【12†L76-L84】.) In practice, top tools in this space (Jobscan, Teal, Resume Worded, Kickresume, etc.) combine four main functions: parsing (simulating ATS), keyword matching to a JD, bullet rewriting, and format checks【38†L82-L90】. For instance, Jobscan’s strength is identifying exactly which JD keywords are missing from your resume【38†L104-L110】, while Resume Worded specializes in diagnosing weak verbs and missing metrics【41†L213-L217】【38†L125-L132】. Kickresume and Resume Worded offer “ATS simulation” that actually parses your file and shows extracted fields【41†L194-L203】【40†L257-L266】.

Resume Parsing/ATS: Academic reviews note that modern ATS parsing (using NLP or deep learning) still has significant errors. Benchmarks show ~15–25% error rates in skill extraction【36†L91-L99】. Common failures include misreading contact info or scrambling multi-column layouts【36†L82-L90】【41†L219-L227】. Experts emphasize the need for “smooth integration with ATS” and handling of unstructured/graphic resumes【22†L74-L77】【25†L496-L502】. These findings suggest that even small formatting issues can hide your skills from an ATS.

Job Matching & Recommendation: Recent research (e.g. “JobFormer”) tackles job-recommendation by embedding JDs and resumes in a semantic space. These models use transformer encoders with skill-aware features to better link candidate profiles to jobs【29†L39-L47】. Another pipeline, Smart-Hiring, extracts resume entities and matches to jobs using contextual embeddings, with emphasis on explainability【32†L26-L34】【32†L76-L84】. The consensus is that moving beyond simple keyword overlap to semantic similarity (e.g. using BERT or Sentence Transformers) yields more relevant matches.

Automation Workflows: Guides for job search (e.g. combining tools like Claude and JobRight) outline a multi-step workflow: read each JD, extract key skills, compare to your resume, suggest edits for gaps, generate tailored resume, update application trackers, and even draft cover letters【15†L122-L130】. This confirms that gap analysis and a feedback loop are essential parts of a modern system.

These sources highlight the state-of-the-art: match resumes to JDs via embeddings and skill-awareness【29†L39-L47】【32†L26-L34】; perform actual parse tests and expose parsed content【41†L194-L203】; provide detailed feedback on style and metrics【41†L213-L217】; and list missing keywords per JD【38†L104-L110】. We can borrow these concepts to strengthen the resume-builder.

## 3. Comparative Analysis

Below we compare resume-builder against JobRight/research by feature. Each table contrasts the repository’s current behavior with industry practice or recommendations. Sources are cited as needed.

### 3.1 Resume Generation

Insights: The generation approach is sound and conservative, but lacks explicit planning. Based on research, we recommend adding a structured pre-writing plan step: e.g. use an LLM or rule to identify which resume sections to prioritize for this JD, which bullets to keep or remove, and the overall section order. This “storyboarding” is what JobFormer-like systems do implicitly. It can leverage existing prompts in orchestrator.py or a new planner module.

### 3.2 Gap Analysis (Coverage Matrix)

Insights: A key improvement is to make gaps explicit. We should augment evaluate() and jd_manager.py to produce a JSON field like missing_skills (or coverage_matrix). For example, produce a JSON array:

{
  "gaps": [
    {"skill": "Python", "in_jd": true, "in_resume": false, "in_profile": true},
    {"skill": "Leadership", "in_jd": true, "in_resume": false, "in_profile": false}
  ]
}

This coverage matrix shows exactly what the JD asks for but the resume lacks. It turns the abstract score into actionable advice. (We could use the same keyword extraction logic already in the pipeline.) Then surface this in the CLI/dashboard so the user sees “Missing: Machine Learning, Project Management, ...”. This mirrors Jobscan/Teal behavior【38†L104-L110】.

### 3.3 Resume Diagnosis

Insights: To improve diagnosis, we should add semantic checks beyond the hard rules. For instance, catch bullets that have no numbers (“achieved results” vs “achieved a 20% increase in…”), or that mix multiple ideas. We can extend polish to emit reasons: e.g. return {"issue": "no_metric", "suggestion": "add a quantifiable result"} for each bullet. A set of additional regex or even simple model prompts can classify bullet quality. For example, detect passive voice or pronouns and explain why they hurt (Jobscan/ResumeWorded style). This turns polish into a coaching step, not just rewording.

### 3.4 Job Matching

Insights: The current workflow is reactive (user-driven). To get closer to JobRight’s approach, we should enable semantic ranking of jobs. For example, after scanning or importing multiple JDs, compute an embedding similarity score between each JD and the candidate profile (or base resume). We can use a sentence-transformer model or a small transformer finetuned on resume-text. In practice, adding one step to sort or filter jobs by this score before user review would save effort. This could be a parallel “matching” module, possibly added to jd_manager.py or a new match.py. For instance, take the profile’s skills/experience text and each JD’s description, embed them and compute cosine; present “Top matches” above others. This mirrors how research systems use a “recall” stage with skill distribution guidance【29†L39-L47】.

### 3.5 ATS Simulation and Recovery

Insights: We should add ATS parse-back testing. Concretely, after rendering the PDF (or HTML), run it through a resume parser (open-source or a simple library) and compare the extracted fields to expected content. For example, extract plain text and ensure sections like “Experience” were found, that skills are listed, and that contact info is captured. We can use an HTML-to-text approach or a parser like [42], then assert the JSON fields match the input. Even a crude parse (splitting by headings) would catch major layout issues. This will reveal hidden failures: e.g. if our resume uses some uncommon formatting that an ATS would miss. Adding this to the CI/tests will ensure “what you see is what the ATS sees.” This aligns with best practice: don’t just trust design; verify it parses【41†L219-L227】【36†L91-L99】.

## 4. Improvement Proposals (Design Details)

Building on the above gaps, we propose the following enhancements. Where useful, we include JSON schema examples and prompt templates to illustrate implementation ideas.

Explicit Planning Layer: Before rewriting, generate a structured plan. For example, use an LLM prompt to output which sections to emphasize and which bullets to revise or drop. A prompt template might be:

System: You are a resume strategist.
User: I have a base resume and a job description. Identify the top 3 skills the job requires and whether the resume demonstrates each. Suggest which resume sections or bullets to expand or remove, and propose an ordering of sections for maximum impact. Output JSON with keys:
 - "missing_skills": [skill list],
 - "focus_sections": [section names],
 - "drop_bullets": [bullet ids].

The output could look like:

{
  "missing_skills": ["AWS", "Leadership"],
  "focus_sections": ["Experience", "Certifications"],
  "drop_bullets": ["old_company_internship"]
}

Implement this by adding a new plan step in orchestrator.py that runs before tailoring. This makes the tailoring smarter and more transparent. (JobFormer-like approaches do something similar implicitly【29†L39-L47】.)

Coverage/Gap Matrix: As noted, modify orchestrator.evaluate() and jd_manager.py to build a JSON array of JD requirements vs resume presence. For instance:

{
  "job_id": 123,
  "title": "Data Engineer",
  "skills": [
    {"name": "Python", "in_jd": true, "in_resume": true, "verified": true},
    {"name": "ETL", "in_jd": true, "in_resume": false, "verified": false},
    {"name": "SQL", "in_jd": true, "in_resume": true, "verified": true}
  ]
}

We would then show missing_skills = ["ETL"] to the user. This requires extracting skills/titles from JD (already done for scoring) and checking against resume content and the profile knowledge base. Store this in the JD JSON (e.g. add a "coverage" field). This gives users clear to-dos, as advocated by Jobscan and Teal【38†L104-L110】.

Semantic Diagnosis Rules: Extend polish and validate_resume with rules that flag issues like “no impact metric,” “generic phrasing,” or “too many actions (and).” For example, add checks to detect if a bullet contains no numbers or passive constructions. When such a rule fires, return an explanation: e.g.

{"bullet": "Improved efficiency of deployment", "issue": "no_metric", "message": "Consider adding a quantifiable result to show impact."}

(The Resume Worded scanner does this type of analysis【41†L213-L217】.) Implement these as extra regex or small LLM queries (e.g. ask GPT: “does this sentence contain a measurable achievement?”). Include this feedback in polish so users know why a sentence is weak. This is an upgrade from generic length checks to content quality checks.

ATS Parse-Back Simulation: Create a parser check after rendering. For example, a new simulate_ats_parse() function could convert the HTML/PDF to plain text (using pdfminer or html-to-text), then attempt to split it into sections (looking for “Experience,” “Education,” etc.) and extract key fields (name, dates). Compare the result to the intended data. We can reuse parts of validate_resume (it already knows the headings we want). Write unit tests (in tests/) using sample resumes (in fixtures/) to ensure this module catches hidden failures (e.g. two-column issues). Document the process in code comments. A schematic JSON for parsed output might be:

{
  "name": "Morgan Smith",
  "contact": {"email": "morgan@example.com", "phone": "123-456-7890"},
  "sections": ["Experience", "Education", "Skills"],
  "raw_text": "Morgan Smith ...", 
  "errors": ["Skills section not found"] 
}

If errors is non-empty, trigger a resume reformat request. This aligns with Kickresume/Worded practice of showing exactly what the ATS sees【41†L219-L227】【40†L257-L266】.

Semantic Job Ranking: Implement a ranking step over saved jobs. For example, use a sentence-transformer to embed the candidate’s profile summary or skills list and each job title/description. Compute cosine similarity and sort jobs by this score. This could be integrated into the scan or dashboard command: show “Top Matches” first. Optionally refine with the existing 10-dim fit score or industry filters. This mirrors research: e.g. training a “semantic-enhanced” model for skill-aware matching【29†L39-L47】, or simply doing a cross-encoder rerank as suggested by experts【31†L41-L48】. Even a basic embedding approach is more powerful than the current date/time sort.

Enhanced UI/UX: Update the dashboard/CLI to display the new analysis. For instance, after running evaluate, present a table: which skills are matched/missing, current fit score, and any format issues flagged. Include the capability to view/edit multiple resume versions per job (like Teal, which ties a resume version to each application). Also consider adding a “Job Pipeline” view (not just list): which applications are in “applied”, “interview”, etc., since JobRight emphasizes tracking and referrals. These changes don’t require new algorithms but improve usability.

Privacy/Security: (Given user context: Morgan has ADHD and health issues. The system should avoid overwhelming feedback and protect personal data.) Ensure that personal contact info is only used for ATS simulation and not logged anywhere insecurely. In UX, display one clear suggestion at a time instead of multiple pop-ups, to avoid cognitive overload. (This aligns with empathetic design, though not specifically technical.) The code already stores data locally; just ensure any prompts or logs redact sensitive PII by default.

Testing & CI: Expand automated tests in tests/ to cover the new logic. For example, add tests that input a sample JD and resume and verify the coverage output JSON. Add parse-back tests as noted. Use fixtures/ to store typical input-resume pairs. Also add unit tests for any new prompt templates (by mocking LLM output) and JSON schema validators. This will help ensure the system remains reliable as we add complexity.

Data Schemas & Persistence: Define clear JSON schemas for any new outputs. For instance, a JobMatch schema could look like:

{
  "job": {"id": 123, "title": "Data Engineer"},
  "score": 0.92,
  "matched_skills": ["Python","SQL"],
  "missing_skills": ["AWS","ETL"]
}

Use a JSON Schema or Pydantic model (in Python) to validate such objects. This makes the code more maintainable and self-documenting. Similarly, document the JD JSON format after changes (including the new coverage or ranking fields).

Below is an example of how a redesigned Skill Coverage JSON might be structured for clarity:

{
  "job_id": 9876,
  "title": "Machine Learning Engineer",
  "required_skills": [
    {"name": "Python", "in_profile": true, "in_resume": true},
    {"name": "TensorFlow", "in_profile": false, "in_resume": false},
    {"name": "AWS", "in_profile": true, "in_resume": false}
  ]
}

And a sample prompt template for planning (as mentioned):

Assistant: You are a savvy career advisor.
Input: 
  Resume Text: "..."
  Job Description: "..."
Task: Identify missing skills and outline a resume revision plan.
Output JSON example:
  {
    "missing_skills": ["TensorFlow", "Kubernetes"],
    "sections_to_expand": ["Projects", "Skills"],
    "bullets_to_rewrite": ["gpu_cluster_setup"]
  }

These concrete structures and prompts can guide implementation and future debugging.

## 5. Architecture Diagrams

Below is a simplified architecture of the enhanced pipeline:

flowchart LR
  CLI[CLI Interface] --> ORCH[Orchestrator Module]
  ORCH -->|uses| PROFILE_DB(Profile/Paths)
  ORCH --> PLAN[Plan Step (new)]
  PLAN --> ORCH
  ORCH --> EVAL[JD Evaluation]
  ORCH --> COVER[Cover Letter Writer]
  ORCH --> TAILOR[Resume Tailoring]
  TAILOR --> POLISH[Resume Polish/Validation]
  ORCH --> RENDER[Render to PDF]
  ORCH --> ATS_SIM[ATS Parse Simulator (new)]
  ATS_SIM --> ORCH
  ORCH --> JDDB[JD Manager]
  JDDB --> SEM_MATCH[Semantic Ranking (new)]
  SEM_MATCH --> JDDB
  JDDB --> DASH[Dashboard/UI]

This shows new components in green (Planning, ATS simulation, Semantic ranking). Data flows (e.g. JSON objects) between these modules would follow the schema examples above.

## 6. Roadmap and Checklist

Based on impact and effort, we prioritize improvements as follows. A rough Gantt timeline is illustrated, and a checklist of next steps is provided.

Checklist of Next Steps (with target files):

Implement coverage analysis: In orchestrator.py, after scoring, compute missing skills and add them to each JD’s JSON. Update jd_manager.py to store these fields. Create unit tests in tests/ using sample JD+resume fixtures.

Add ATS parse-back tests: Create a helper (e.g. resume_parser.py) that converts the resume HTML/PDF to plain text and extracts sections. Call this in validate_resume.py or as a post-process in orchestrator.run(). Include tests in tests/parse_tests.py to confirm fields are read correctly.

Develop planning prompt: Modify the tailoring pipeline in orchestrator.py to first call a new planning LLM prompt (as above). Store the plan in memory, and use its output to inform which bullets to rewrite or drop.

Extend polish for semantics: In validate_resume.py and bullet_feedback.py, add new rule checks (e.g. regex for numerals or passive voice). Encode identified issues in the returned JSON. Optionally, use the LLM (via Gemini) to suggest improvements on flagged bullets.

Integrate semantic ranking: Add an optional step in scripts/cli.py (or a new command) to rank saved jobs. Use a pre-trained model (e.g. sentence-transformers) to embed the profile’s “skills and experience” text and each job’s description. Sort and display top-N jobs.

Update CLI/dashboard: Modify dashboard templates (or CLI output) to show the new gap analysis and matching scores. Ensure that when the user views a JD, they see matched vs. missing skills.

Enhance tests: In tests/, add cases for all new features (coverage, parse simulation, planning JSON output). Use fixtures/ to store expected JSON results.

Document data schemas: In comments or docs (e.g. a new schemas.md), define the structure of the updated JD JSON (with coverage and parse fields) and of any new match/plan objects.

Privacy note: Ensure any log statements or debug prints redact personal contact details. Add a health-check prompt for each feedback (e.g. “Is this feedback clear?”) to accommodate the user’s cognitive context.

By following this roadmap, the resume-builder will evolve from a basic pipeline into a robust career assistant: proactively matching jobs, revealing gaps, coaching on writing, and verifying ATS compatibility. The system’s existing strength – factual, evidence-based output – remains intact, while these improvements make it far more comprehensive and aligned with cutting-edge job search tools【38†L82-L90】【41†L194-L203】.

Sources: Industry analyses and academic reviews of resume parsing and matching【22†L72-L77】【25†L496-L502】, plus modern AI resume tools【38†L82-L90】【41†L194-L203】【29†L39-L47】 (as cited above).




### [Table]

| Aspect | resume-builder (current) | JobRight/Other Tools (industry) |

| Functionality | Tailors the user’s existing bullets to the job: invokes an LLM to critique and rewrite points based on the JD and an evidence bank. Splits critique vs. rewrite. | Many AI builders (e.g. Rezi, Enhancv) offer real-time rewriting or generation, often from scratch or templates. Checkers like Resume Worded focus on rewriting for style/impact【38†L88-L90】. |

| Data flow | Input = base resume + JD. Orchestrator calls GPT: first to analyze (critique) then to rewrite bullets. Validates output, then renders to PDF. | Typically, user pastes text or data, tool makes one model call (or stepwise) to output final resume. Often less separation between planning and writing. No built-in evidence bank. |

| Outputs | Resume text + PDF, guaranteed factual (no made-up metrics). Uses fixed template for layout. | Often a stylized resume with graphics/templates. Some tools add extra phrasing, but may hallucinate details. |

| Verification | Post-generation checks (via validate_resume.py) ensure ATS-friendly format and no banned content. E.g. no tables/images, no “responsible for” verbs, no duplicates. | Jobscan/Worded similarly flag formatting issues. Worded flags weak verbs, missing metrics【41†L213-L217】. But many rely on LLM consistency rather than deterministic checks. |

| Feedback | The polish command re-invokes the LLM on flagged bullets for minor cleanup. Feedback is mostly “accepted vs. rewrite” using the bullet_feedback module. | Good checkers provide line-by-line suggestions (“add numbers”, “use active voice”【41†L213-L217】). For example, Resume Worded explicitly points out vague accomplishments or missing quantification. |

| Example insp. | (None externally; this repo is unique in its modular approach) | Jobscan: “tells you exactly which keywords appear in the JD but not on your resume”【38†L104-L110】 (i.e. identifies missing skills); Worded: flags vague verbs and adds metrics【41†L213-L217】. |





### [Table]

| Aspect | resume-builder (current) | JobRight/Other Tools (industry) |

| Functionality | The evaluate command scores fit (10 dimensions) but does not explicitly list missing skills or content gaps. | Tools like Jobscan, Teal, and Resume Worded explicitly highlight missing keywords and skills. They produce a “Match Rate” and enumerate absent JD terms【38†L104-L110】. |

| Data flow | JD keywords and experience are extracted and compared to profile; score computed (in orchestrator or jd_manager). But gaps aren’t surfaced to user beyond the score. | After parsing resume and JD, industry tools use simple set-difference (or semantic overlap) to output what JD terms are unmatched. |

| Outputs | Current output: a numeric score and a brief text summary. No actionable to-do list. | Desired output: a coverage table or JSON listing each key JD skill, whether it appears in profile, in current resume version, and if it is “verified” (from bullet bank) or missing. |

| Persistence | JD JSON (via jd_manager.py) holds fit scores and application flags. | No built-in persistence in most tools; they give one-off reports. (But Teal does save resumes per JD for tracking.) |

| Example insp. | – | Jobscan: highlights exactly which keywords from the JD are missing【38†L104-L110】. Resume Worded’s scanner similarly identifies “hard skills” and soft skills gaps【41†L201-L209】. |





### [Table]

| Aspect | resume-builder (current) | JobRight/Other Tools (industry) |

| Verbal style checks | Current validate_resume.py flags blacklisted words, duplicate verbs, pronouns, etc. Bullets are reformatted (e.g. removing endings). After LLM rewrite, the user can manually polish. | Resume checkers (Resume Worded, Teal) automatically detect semantic issues: missing metrics, weak verbs, passive voice, personal pronouns, cliché buzzwords, etc.【41†L213-L217】. They often suggest fixes or exact wording changes. |

| Level of feedback | Mostly binary “violation” alerts (e.g. bullet too long, tagline missing). The polish command only lightly refines grammar/style, not content. | Worded: “strongest feedback on language quality” – flags vague accomplishments and rephrases lines【41†L213-L217】. Teal’s match mode also scores writing quality inline. |

| Focus | Enforces ATS conventions (no images, no tables, section headers present), plus basic style rules. | Focuses on writing impact: checks if bullet has quantifiable results, uses active verbs, and doesn’t reuse verbs【41†L213-L217】. |

| Examples insp. | – | Worded: warns “missing metrics” or suggests replacing “led” with “managed” for clarity【41†L213-L217】. A good resume checker “tells you why a line is weak” and how to fix it【38†L94-L95】. |





### [Table]

| Aspect | resume-builder (current) | JobRight/Other Tools (industry) |

| Functionality | Users provide a JD or scan for jobs (via integrated scrapers). The system checks JD “liveness” (expiry), scores fit via 10-dim model, and tracks applications. There is no proactive ranking or recommendation of jobs. | Advanced platforms embed jobs and resumes in a shared semantic space. E.g. “JobFormer” uses a transformer to encode JDs guided by candidate skill distribution【29†L39-L47】. Smart-Hiring encodes resumes+JDs jointly and then computes similarity【32†L26-L34】. These systems can rank saved jobs by relevance automatically. |

| Data flow | Fetch jobs → user selects JD → evaluate with current resume → tailor+apply → update state. | Jobs could be continuously ranked: e.g., candidate profile → generate embedding; pre-fetch jobs → embed; compute cosine scores to recommend top matches. |

| Scoring model | Rule- and keyword-based scoring (via evaluate), yielding fit percentages across categories. | Learned or embedding-based scoring. For instance, the cited model uses “skill-aware” recall and ranking with Transformers【29†L39-L47】. Smart-Hiring uses contextual text embeddings for “semantically meaningful alignment”【32†L26-L34】. |

| Persistence/Tracking | The jd_manager stores fit scores and application status per JD. The user must manually review listings. | Tools like Teal or JobRight maintain job lists and histories, and provide dashboards of matched jobs. |

| Example insp. | – | The “JobFormer” abstract: “parse JDs and complete personalized job recommendation” using a transformer and skill guidance【29†L39-L47】. Smart-Hiring: “encodes both resumes and job descriptions in a shared vector space to compute similarity scores”【32†L26-L34】. JobRight touts “personalized AI job matches” based on your real skills【12†L58-L66】. |





### [Table]

| Aspect | resume-builder (current) | JobRight/Other Tools (industry) |

| Functionality | Generates ATS-friendly PDFs by construction (no images/tables, basic headings). Relies on post-generation validate_resume.py to enforce formatting. Does not simulate an ATS parse. | Some tools explicitly simulate the ATS parse. E.g., Resume Worded’s scanner “parses your file the way an ATS does and shows you the extracted text”【41†L219-L227】. Kickresume’s ATS checker “simulates a real ATS scan” with 20+ checks【40†L257-L266】. |

| Checks performed | Current checks catch common traps (multi-column layouts, images, etc.) in validate_resume.py. | In addition, simulators check that contact info, section headings, dates, and skills are recognized. Resume Worded flags if “Experience” or “Education” sections are missed【41†L219-L227】. |

| Failure modes | Without simulation, the resume might look fine to us but be parsed incorrectly. E.g. two-column formats will scramble as shown here: ![ATS parse example][41_L219-L227]{width=80%} (sidebar text interleaves with main column)【41†L219-L227】. Real-world stats back this up: ATS skill extraction can err ~15–25%【36†L91-L99】. | Industry wisdom: “hybrid screening workflows fail when they trust ATS parsing output as ground truth” – candidates may be lost if fields misparsed【36†L91-L99】. Good checkers show you exactly what the ATS sees. |

| Example insp. | – | Resume Worded: “the resume scanner runs over twenty tests… ATS parse simulation” and shows parsed output【41†L194-L203】【41†L219-L227】. Kickresume: “simulates a real ATS scan… checks for formatting, structure, and content”【40†L257-L266】. |





### [Table]

|  |


