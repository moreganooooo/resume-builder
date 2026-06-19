import os
import yaml
import json
import pandas as pd
from dotenv import load_dotenv
from google import genai
from google.genai import types
from pydantic import BaseModel, Field
from typing import List

# --- PATH RESOLUTION & ENV SETUP ---
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(SCRIPT_DIR)
load_dotenv(os.path.join(PROJECT_ROOT, ".env"))

client = genai.Client()

# ==========================================
# PYDANTIC SCHEMAS
# ==========================================

class BulletAuditSchema(BaseModel):
    action_taken: str = Field(description="The core objective action or task performed.")
    tools_used: List[str] = Field(description="Specific software, tools, or hard methodologies named.")
    metrics_claimed: str = Field(description="Any specific quantities, percentages, or numbers. Use 'None' if missing.")
    unsupported_claims: List[str] = Field(description="List of generic fluff phrases, buzzwords, or unmeasurable claims.")

class WorkExperience(BaseModel):
    title: str
    company: str
    period: str
    achievements: List[str]

class ResumeSchema(BaseModel):
    name: str
    role: str
    location: str
    skills: List[str]
    experience: List[WorkExperience]

class JDKeywordSchema(BaseModel):
    tools: List[str] = Field(description="Specific software, platforms, and tech stack (e.g., Salesforce, Outreach.io, Figma).")
    hard_skills: List[str] = Field(description="Specific methodologies, metrics, and frameworks (e.g., Lifecycle Marketing, A/B Testing, Pipeline Generation).")
    core_functions: List[str] = Field(description="Primary responsibilities and domain areas (e.g., Content Governance, Enablement Training).")

class CritiqueSchema(BaseModel):
    accuracy_score: int = Field(description="0-100 score")
    believability_score: int = Field(description="0-100 score based on believability.yaml")
    clarity_score: int = Field(description="0-100 score")
    ats_value: int = Field(description="0-100 score")
    manager_test: str = Field(description="Strictly 'PASS' or 'FAIL'")
    weaknesses: str = Field(description="Explanation of flaws")

class RewriteSchema(BaseModel):
    original: str
    rewritten: str
    reason: str

class TemplateSchema(BaseModel):
    NAME: str = Field(description="Must match candidate name.")
    TAGLINE: str = Field(description="Max 80 chars. Follows archetype tagging rules.")
    PHONE: str
    EMAIL: str
    LINKEDIN_URL: str
    LINKEDIN_DISPLAY: str
    PORTFOLIO_URL: str
    PORTFOLIO_DISPLAY: str
    LOCATION: str
    
    SECTION_SUMMARY: str = "Professional Summary"
    SUMMARY_TEXT: str = Field(description="Max 5 lines. First sentence MUST be bolded using <strong> tags. No generic filler.")
    
    SECTION_COMPETENCIES: str = "Core Competencies"
    COMPETENCIES: List[str] = Field(min_length=6, max_length=8, description="6-8 exact keywords extracted from JD requirements.")
    
    SECTION_EXPERIENCE: str = "Work Experience"
    EXPERIENCE: List[WorkExperience] = Field(description="Bulleted achievements. Must pass Jobright QA heuristics.")
    
    SECTION_PROJECTS: str = "Projects"
    PROJECTS: List[str] = Field(min_length=3, max_length=4, description="Top 3-4 most relevant projects for the role.")
    
    SECTION_EDUCATION: str = "Education"
    EDUCATION: List[str] = Field(description="KU, KCKCC, and JCCC items exactly as per design system.")
    
    SECTION_CERTIFICATIONS: str = "Training & Certifications"
    CERTIFICATIONS: List[str] = Field(min_length=3, max_length=3, description="Exact 3 certifications in order.")
    
    SECTION_SKILLS: str = "Skills"
    SKILLS: List[str] = Field(description="Technical skills mapped to JD.")

# ==========================================
# RESUME OPERATING SYSTEM ENGINE
# ==========================================

class ResumeEngine:
    def __init__(self):
        # Map out the exact folder locations based on the architecture
        self.engine_dir = os.path.join(PROJECT_ROOT, "resume-engine")
        
        self.prompts_dir = os.path.join(self.engine_dir, "prompts")
        self.rules_dir = os.path.join(self.engine_dir, "rules")
        self.scoring_dir = os.path.join(self.engine_dir, "scoring")
        self.kb_dir = os.path.join(self.engine_dir, "knowledge_base")
        self.templates_dir = os.path.join(self.engine_dir, "templates")
        
        self.output_json_dir = os.path.join(PROJECT_ROOT, "output", "json")
        self.jds_dir = os.path.join(PROJECT_ROOT, "jds")

    def _load_yaml(self, dir_path, filename):
        path = os.path.join(dir_path, filename)
        try:
            with open(path, "r") as f:
                return yaml.safe_load(f)
        except FileNotFoundError:
            return {}

    def _load_prompt(self, filename):
        path = os.path.join(self.prompts_dir, filename)
        try:
            with open(path, "r") as f:
                return f.read()
        except FileNotFoundError:
            return "Fallback prompt: Process the text."

    def _load_knowledge_base(self):
        """Stitches all text/markdown files in knowledge_base/ into a single context string."""
        master_context = "\n=== SYSTEM KNOWLEDGE BASE ===\n\n"
        
        if os.path.exists(self.kb_dir):
            for filename in os.listdir(self.kb_dir):
                # Skip CSVs here since Pandas handles them now
                if filename.endswith(('.md', '.yml', '.yaml', '.txt')):
                    filepath = os.path.join(self.kb_dir, filename)
                    with open(filepath, "r", encoding="utf-8") as f:
                        master_context += f"--- START OF {filename} ---\n{f.read()}\n--- END OF {filename} ---\n\n"
        return master_context

    def audit_and_refine_bullets(self, raw_bullets: List[str]):
            """Passes bullets through the Critique and Rewrite prompts."""
            print("🛡️ Starting the Skeptical Editor Audit Loop...")
            
            critique_prompt = self._load_prompt("critique_bullet.md")
            rewrite_prompt = self._load_prompt("rewrite_bullet.md")
            manager_test_rules = json.dumps(self._load_yaml(self.scoring_dir, "manager_test.yaml"))
            style_rules = json.dumps(self._load_yaml(self.rules_dir, "style_rules.yaml"))
            
            refined_bullets = []
            
            for i, bullet in enumerate(raw_bullets):
                print(f"   Analyzing bullet {i+1}/{len(raw_bullets)}...")
                
                try:
                    # STEP 1: CRITIQUE
                    critique_config = types.GenerateContentConfig(
                        system_instruction=f"{critique_prompt}\n\nRULES:\n{manager_test_rules}\n\nSTRICT INSTRUCTION: Return ONLY pure JSON.",
                        response_mime_type="application/json",
                        response_schema=CritiqueSchema,
                        temperature=0.0
                    )
                    
                    critique_res = client.models.generate_content(
                        model='gemma-4-26b-a4b-it', contents=bullet, config=critique_config
                    )
                    
                    if not critique_res.text:
                        refined_bullets.append(bullet)
                        continue

                    # Clean the response string safely
                    clean_text = critique_res.text.strip()
                    clean_text = clean_text.replace("```json", "")
                    clean_text = clean_text.replace("```", "")
                    
                    critique_data = json.loads(clean_text)
                    
                    # STEP 2: REWRITE
                    if critique_data.get('manager_test') == 'FAIL' or critique_data.get('believability_score', 100) < 80:
                        print(f"      ⚠️ Bullet failed Manager Test. Rewriting...")
                        
                        rewrite_config = types.GenerateContentConfig(
                            system_instruction=f"{rewrite_prompt}\n\nSTYLE RULES:\n{style_rules}\n\nWEAKNESSES TO FIX:\n{critique_data.get('weaknesses', 'None')}",
                            response_mime_type="application/json",
                            response_schema=RewriteSchema,
                            temperature=0.0
                        )
                        rewrite_res = client.models.generate_content(
                            model='gemma-4-26b-a4b-it', contents=bullet, config=rewrite_config
                        )
                        
                        if rewrite_res.text:
                            rewrite_text = rewrite_res.text.strip()
                            rewrite_text = rewrite_text.replace("```json", "")
                            rewrite_text = rewrite_text.replace("```", "")
                            
                            rewrite_data = json.loads(rewrite_text)
                            refined_bullets.append(rewrite_data.get('rewritten', bullet))
                        else:
                            refined_bullets.append(bullet)
                    else:
                        refined_bullets.append(bullet)
                        
                except Exception as e:
                    print(f"      ⚠️ AI Error: {e}. Skipping.")
                    refined_bullets.append(bullet)
                    
            print("✅ Audit complete.")
            return "\n".join([f"- {b}" for b in refined_bullets])

    # --- PHASE 2: PANDAS DATA EXTRACTION ---
    def extract_jd_keywords(self, jd_text: str):
        """Uses Gemini to extract structured requirements from the Job Description."""
        print("🔍 Analyzing JD to extract core tools and functional requirements...")
        
        config = types.GenerateContentConfig(
            system_instruction="You are an expert technical recruiter. Extract the tools, hard skills, and core functions from this job description. Return ONLY valid JSON.",
            response_mime_type="application/json",
            response_schema=JDKeywordSchema,
            temperature=0.1
        )
        
        response = client.models.generate_content(
            model='gemma-4-26b-a4b-it',
            contents=jd_text,
            config=config
        )
        return json.loads(response.text)

    def mine_bullet_bank(self, jd_text: str, top_k: int = 20):
        """Scores and extracts the top 20 most relevant bullets from the CSV."""
        print(f"⛏️  Mining bullet-bank-clean.csv for the top {top_k} best matches...")
        
        # 1. Get the structured keywords from the JD
        keywords_dict = self.extract_jd_keywords(jd_text)
        
        # 2. Flatten and weight the keywords
        # Give 'tools' double weight because they are hard ATS requirements
        weighted_kws = {kw.lower(): 2 for kw in keywords_dict.get('tools', [])}
        weighted_kws.update({kw.lower(): 1 for kw in keywords_dict.get('hard_skills', [])})
        weighted_kws.update({kw.lower(): 1 for kw in keywords_dict.get('core_functions', [])})
        
        # 3. Load the CSV database
        csv_path = os.path.join(self.kb_dir, "bullet-bank-clean.csv")
        if not os.path.exists(csv_path):
            print(f"⚠️ Warning: {csv_path} not found in knowledge_base/. Skipping extraction.")
            return "No CSV database found."
            
        try:
            df = pd.read_csv(csv_path)
            
            # 4. Define the scoring logic
            def score_row(row):
                # Convert the entire row to a single lowercase string for easy searching
                row_str = " ".join(str(val).lower() for val in row.values)
                # Sum the weights of any keyword found in this row
                score = sum(weight for kw, weight in weighted_kws.items() if kw in row_str)
                return score
                
            # 5. Apply the score and sort
            df['match_score'] = df.apply(score_row, axis=1)
            df_sorted = df.sort_values(by='match_score', ascending=False)
            
            # 6. Extract the top matches
            top_matches = df_sorted.head(top_k)
            
            # 7. Return as a list of dictionaries for the audit loop
            extracted_bullets = []
            for _, row in top_matches.iterrows():
                clean_row = row.drop('match_score').to_dict()
                bullet_string = str(clean_row) 
                extracted_bullets.append(bullet_string)
                
            print(f"🎯 Extracted {len(extracted_bullets)} highly relevant bullets based on {len(weighted_kws)} unique JD keywords.")
            return extracted_bullets
            
        except Exception as e:
            print(f"⚠️ Error reading CSV: {e}")
            return "Error reading CSV database."

    # --- AUDIT ENGINE ---
    def extract_evidence(self, bullet_text):
        base_prompt = self._load_prompt("extract_evidence.md")
        truthfulness_rules = self._load_yaml(self.rules_dir, "truthfulness_rules.yaml")
        ai_risk_rules = self._load_yaml(self.scoring_dir, "ai_risk.yaml")
        
        system_instruction = f"{base_prompt}\n# Truthfulness Rules: {json.dumps(truthfulness_rules)}\n# AI Risk Definitions: {json.dumps(ai_risk_rules)}"
        
        config = types.GenerateContentConfig(
            system_instruction=system_instruction,
            response_mime_type="application/json",
            response_schema=BulletAuditSchema,
            temperature=0.1
        )
        
        response = client.models.generate_content(
            model='gemma-4-26b-a4b-it',
            contents=bullet_text,
            config=config
        )
        return json.loads(response.text)

    # --- BUILDER ENGINE ---
    def build_tailored_resume(self, parsed_json_filename, jd_filename, output_filename="tailored_resume.json"):
        print(f"\n⚙️ INITIALIZING TAILORING ENGINE")
        
        # Read from mapped directories
        parsed_json_path = os.path.join(self.output_json_dir, parsed_json_filename)
        jd_path = os.path.join(self.jds_dir, jd_filename)
        output_path = os.path.join(self.output_json_dir, output_filename)
        
        with open(parsed_json_path, "r") as f:
            master_resume = f.read()
        with open(jd_path, "r") as f:
            job_description = f.read()
            
        # 1. Trigger Phase 2 extraction (Pandas)
        raw_mined_bullets = self.mine_bullet_bank(job_description)
            
        # 2. Trigger Phase C Audit Loop (Critique & Rewrite)
        polished_bullets = self.audit_and_refine_bullets(raw_mined_bullets)
            
        # 3. Load Tailoring prompt and Rules
        prompt_template = self._load_prompt("tailor_resume.md")
        knowledge_context = self._load_knowledge_base()
        schema_rules = json.dumps(TemplateSchema.model_json_schema(), indent=2)
        
        system_instruction = f"{prompt_template}\n{knowledge_context}\n\nOUTPUT FORMAT: Return ONLY valid JSON adhering to this schema:\n{schema_rules}"
        
        # 4. Inject the POLISHED bullets directly into the contents payload
        combined_contents = f"""
        # CANDIDATE DATA
        {master_resume}
        
        # TARGET JD
        {job_description}
        
        ### POLISHED BULLETS (Audited & Refined)
        {polished_bullets}
        """

        # 5. Define the config ONCE
        generation_config = types.GenerateContentConfig(
            system_instruction=system_instruction,
            response_mime_type="application/json",
            response_schema=TemplateSchema,
            temperature=0.2
        )
        
        # 6. Use the config in the call
        response = client.models.generate_content(
            model='gemma-4-26b-a4b-it',
            contents=combined_contents,
            config=generation_config
        )
        
        # 7. Save output to output/json/
        with open(output_path, "w") as f:
            json.dump(json.loads(response.text), f, indent=2)
        print(f"✅ Success! Tailored resume saved to {output_path}")

    # --- PHASE 4: THE RENDER PIPELINE ---
    def render_pdf(self, json_filename="tailored_resume.json", output_pdf_name="final_resume.pdf"):
        print("\n🖨️  INITIALIZING RENDER PIPELINE")
        import subprocess
        
        # 1. Load the generated JSON and the HTML template
        json_path = os.path.join(self.output_json_dir, json_filename)
        template_path = os.path.join(self.templates_dir, "cv-template.html")
        
        with open(json_path, 'r') as f:
            resume_data = json.load(f)
            
        with open(template_path, 'r') as f:
            html_content = f.read()

        # 2. Build the complex HTML chunks (Experience, Education, Competencies, etc.)
        experience_html = ""
        for job in resume_data.get("EXPERIENCE", []):
            bullets = "".join([f"<li>{b}</li>" for b in job.get("achievements", [])])
            experience_html += f"""
            <div class="job">
                <div class="job-header">
                    <div class="job-company">{job.get("company", "")}</div>
                    <div class="job-period">{job.get("period", "")}</div>
                </div>
                <div class="job-role">{job.get("title", "")}</div>
                <ul>{bullets}</ul>
            </div>
            """
            
        competencies_html = "".join([f'<span class="competency-tag">{c}</span>' for c in resume_data.get("COMPETENCIES", [])])
        
        # Formulate the remaining sections as clean HTML lists
        projects_html = "<ul>" + "".join([f"<li>{p}</li>" for p in resume_data.get("PROJECTS", [])]) + "</ul>" if resume_data.get("PROJECTS") else ""
        education_html = "<ul>" + "".join([f"<li>{e}</li>" for e in resume_data.get("EDUCATION", [])]) + "</ul>" if resume_data.get("EDUCATION") else ""
        certs_html = "<ul>" + "".join([f"<li>{c}</li>" for c in resume_data.get("CERTIFICATIONS", [])]) + "</ul>" if resume_data.get("CERTIFICATIONS") else ""
        
        # Skills are usually comma-separated at the bottom
        skills_html = f"<div class='skills-text'>{', '.join(resume_data.get('SKILLS', []))}</div>" if resume_data.get("SKILLS") else ""

        # 3. Perform the exact 1:1 text replacements mapped to your schema
        replacements = {
            "{{LANG}}": "en",
            "{{PAGE_WIDTH}}": "8.5in",
            "{{NAME}}": resume_data.get("NAME", ""),
            "{{PHONE}}": resume_data.get("PHONE", ""),
            "{{EMAIL}}": resume_data.get("EMAIL", ""),
            "{{LINKEDIN_URL}}": resume_data.get("LINKEDIN_URL", ""),
            "{{LINKEDIN_DISPLAY}}": resume_data.get("LINKEDIN_DISPLAY", ""),
            "{{PORTFOLIO_URL}}": resume_data.get("PORTFOLIO_URL", ""),
            "{{PORTFOLIO_DISPLAY}}": resume_data.get("PORTFOLIO_DISPLAY", ""),
            "{{LOCATION}}": resume_data.get("LOCATION", ""),
            
            # Section Headers & Content
            "{{SECTION_SUMMARY}}": resume_data.get("SECTION_SUMMARY", "Professional Summary"),
            "{{SUMMARY_TEXT}}": resume_data.get("SUMMARY_TEXT", ""),
            
            "{{SECTION_COMPETENCIES}}": resume_data.get("SECTION_COMPETENCIES", "Core Competencies"),
            "{{COMPETENCIES}}": competencies_html,
            
            "{{SECTION_EXPERIENCE}}": resume_data.get("SECTION_EXPERIENCE", "Work Experience"),
            "{{EXPERIENCE}}": experience_html,
            
            "{{SECTION_PROJECTS}}": resume_data.get("SECTION_PROJECTS", "Projects"),
            "{{PROJECTS}}": projects_html,
            
            "{{SECTION_EDUCATION}}": resume_data.get("SECTION_EDUCATION", "Education"),
            "{{EDUCATION}}": education_html,
            
            "{{SECTION_CERTIFICATIONS}}": resume_data.get("SECTION_CERTIFICATIONS", "Training & Certifications"),
            "{{CERTIFICATIONS}}": certs_html,
            
            "{{SECTION_SKILLS}}": resume_data.get("SECTION_SKILLS", "Skills"),
            "{{SKILLS}}": skills_html
        }
        
        for key, value in replacements.items():
            html_content = html_content.replace(key, str(value))

        # 4. Save the intermediate HTML file
        output_html_dir = os.path.join(PROJECT_ROOT, "output", "html")
        os.makedirs(output_html_dir, exist_ok=True)
        temp_html_path = os.path.join(output_html_dir, "temp_cv.html")
        
        with open(temp_html_path, "w") as f:
            f.write(html_content)

        # 5. Trigger the Node.js script via subprocess
        output_pdf_dir = os.path.join(PROJECT_ROOT, "output", "pdf")
        os.makedirs(output_pdf_dir, exist_ok=True)
        final_pdf_path = os.path.join(output_pdf_dir, output_pdf_name)
        
        node_script = os.path.join(SCRIPT_DIR, "generate-pdf.mjs")
        print(f"🚀 Firing Playwright Execution: {node_script}")
        
        try:
            subprocess.run(["node", node_script, temp_html_path, final_pdf_path, "--format=letter"], check=True)
            print(f"✅ ATS-Optimized PDF successfully rendered at {final_pdf_path}")
        except subprocess.CalledProcessError as e:
            print(f"❌ PDF Generation Failed: {e}")

if __name__ == "__main__":
    engine = ResumeEngine()
    print("Engine Ready. Starting the full Pipeline...")
    
    # 1. Define your input files
    # These should match the files currently sitting in your jds/ and output/json/ folders
    input_parsed_json = "parsed_resume.json" 
    input_jd_file = "dummy_jd.txt" 
    
    # 2. Define your desired output filenames
    output_tailored_json = "tailored_resume.json"
    output_final_pdf = "MorganEscott_Tailored_Resume.pdf"
    
    # 3. Execute Phase 2 & 3: Pandas Extraction + Skeptical Editor
    engine.build_tailored_resume(
        parsed_json_filename=input_parsed_json,
        jd_filename=input_jd_file,
        output_filename=output_tailored_json
    )
    
    # 4. Execute Phase 4: HTML Injection + Playwright Render
    engine.render_pdf(
        json_filename=output_tailored_json,
        output_pdf_name=output_final_pdf
    )
    
    print("\n🎉 Pipeline execution complete!")