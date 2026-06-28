import os
import json
from dotenv import load_dotenv
from google import genai
from google.genai import types
from pydantic import BaseModel, Field
from typing import List

# --- PATH RESOLUTION ---
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(SCRIPT_DIR)
TXT_OUTPUT_DIR = os.path.join(PROJECT_ROOT, "output", "txt")
JSON_OUTPUT_DIR = os.path.join(PROJECT_ROOT, "output", "json")

# Ensure .env is loaded from the project root
load_dotenv(os.path.join(PROJECT_ROOT, ".env"))

# Initialize client
client = genai.Client(api_key=os.environ.get("GEMINI_API_KEY", "YOUR_API_KEY"))

# --- MODEL STRATEGY ---
# gemma-4-31b-it: used here because parsed_resume.json is the foundation
# every tailoring run is built on. A bad parse here silently corrupts every
# resume generated until ingest is re-run. 31B has the strongest structured
# output compliance of the Gemma tier, and since ingest only runs once
# (result is cached as parsed_resume.json), the extra token cost is negligible.
INGEST_MODEL = "gemma-4-31b-it"

# 1. Define a Pydantic schema to guarantee perfectly structured JSON output
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

def parse_resume_to_json(file_path):
    print(f"Uploading {file_path} to the API...")
    
    # 2. Upload file using the correct SDK client
    resume_file = client.files.upload(file=file_path)    
    
    # 3. Configure the content generation call using types.GenerateContentConfig
    config = types.GenerateContentConfig(
        system_instruction="You are a precise Resume Parsing Engine. Output ONLY valid JSON matching the exact schema requested.",
        response_mime_type="application/json",
        response_schema=ResumeSchema,
        temperature=0.1 
    )
    
    try:
        response = client.models.generate_content(
            model=INGEST_MODEL,
            contents=[resume_file, "Extract the resume data into the required JSON schema."],
            config=config
        )
        return json.loads(response.text)
        
    finally:
        # 4. Cleanup inside a finally block to ensure the file is deleted even if generation fails
        print(f"Cleaning up uploaded file: {resume_file.name}")
        client.files.delete(name=resume_file.name)

if __name__ == "__main__":
    # Ensure output directory exists just in case
    os.makedirs(JSON_OUTPUT_DIR, exist_ok=True)

    # 1. Point directly to your master CV in the knowledge base
    master_resume_file = os.path.join(PROJECT_ROOT, "resume-engine", "knowledge_base", "cv.md")
    
    if not os.path.exists(master_resume_file):
        print(f"❌ Error: Could not find {master_resume_file}")
        print("Please ensure cv.md is sitting in the knowledge_base folder!")
    else:
        # 2. Parse YOUR actual resume
        parsed_resume = parse_resume_to_json(master_resume_file)
        
        # 3. Save the structured output to output/json/
        output_filename = os.path.join(JSON_OUTPUT_DIR, "parsed_resume.json")
        with open(output_filename, "w") as f:
            json.dump(parsed_resume, f, indent=2)
            
        print(f"✅ Success! Master CV converted to JSON and saved to {output_filename}")
