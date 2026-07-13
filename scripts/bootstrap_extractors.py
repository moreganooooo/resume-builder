import os
import shutil
import subprocess

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(SCRIPT_DIR)

_EXTENSION_KIND_MAP = {
    "pdf": "pdf",
    "png": "image",
    "jpg": "image",
    "jpeg": "image",
    "heic": "image",
    "webp": "image",
    "docx": "docx",
    "doc": "doc",
    "odt": "odt",
    "pptx": "pptx",
    "xlsx": "spreadsheet",
    "xls": "spreadsheet",
    "csv": "spreadsheet",
    "txt": "text",
    "md": "text",
}


def detect_file_kind(path: str) -> str:
    ext = os.path.splitext(path)[1].lower().lstrip(".")
    return _EXTENSION_KIND_MAP.get(ext, "unsupported")


def convert_legacy_doc_to_pdf(path: str) -> str | None:
    soffice = shutil.which("soffice")
    if not soffice:
        return None
    out_dir = os.path.dirname(os.path.abspath(path))
    subprocess.run(
        [soffice, "--headless", "--convert-to", "pdf", "--outdir", out_dir, path],
        check=True,
        capture_output=True,
    )
    base = os.path.splitext(os.path.basename(path))[0]
    return os.path.join(out_dir, f"{base}.pdf")


def _extract_docx_text(path: str) -> str:
    import docx
    doc = docx.Document(path)
    return "\n".join(p.text for p in doc.paragraphs)


def _extract_pptx_text(path: str) -> str:
    from pptx import Presentation
    prs = Presentation(path)
    lines = []
    for slide in prs.slides:
        for shape in slide.shapes:
            if shape.has_text_frame:
                for paragraph in shape.text_frame.paragraphs:
                    text = "".join(run.text for run in paragraph.runs)
                    if text:
                        lines.append(text)
    return "\n".join(lines)


def _extract_odt_text(path: str) -> str:
    from odf.opendocument import load
    from odf import text as odf_text
    from odf import teletype
    doc = load(path)
    paragraphs = doc.getElementsByType(odf_text.P)
    return "\n".join(teletype.extractText(p) for p in paragraphs)


def _extract_spreadsheet_text(path: str) -> str:
    import pandas as pd
    ext = os.path.splitext(path)[1].lower()
    if ext == ".csv":
        df = pd.read_csv(path)
    else:
        df = pd.read_excel(path)
    return df.to_csv(index=False)


def _extract_plain_text(path: str) -> str:
    with open(path, "r", encoding="utf-8") as f:
        return f.read()


def extract_local_text(path: str, kind: str) -> str:
    if kind == "docx":
        return _extract_docx_text(path)
    if kind == "pptx":
        return _extract_pptx_text(path)
    if kind == "odt":
        return _extract_odt_text(path)
    if kind == "spreadsheet":
        return _extract_spreadsheet_text(path)
    if kind == "text":
        return _extract_plain_text(path)
    raise ValueError(f"extract_local_text does not support kind={kind!r} (path={path})")


import sys
from typing import Literal, Optional

from google import genai
from google.genai import types
from pydantic import BaseModel, Field

if SCRIPT_DIR not in sys.path:
    sys.path.insert(0, SCRIPT_DIR)

from gemini_client import GeminiClient  # noqa: E402

EXTRACTION_MODEL = "gemini-3.1-flash-lite"
UPLOAD_MODEL = "gemma-4-31b-it"


class RawAchievement(BaseModel):
    raw_text: str = Field(description="The achievement as written or lightly rephrased for clarity -- never invent detail not in the source.")
    company_hint: Optional[str] = Field(default=None, description="Company/employer name if stated or strongly implied nearby in the source text.")
    date_hint: Optional[str] = Field(default=None, description="Any date or date range mentioned near this achievement, verbatim as written.")
    title_hint: Optional[str] = Field(default=None, description="Job title mentioned near this achievement, if any.")
    confidence: Literal["high", "medium", "low"] = Field(description="high: company/date clearly stated. medium: implied but not explicit. low: no attribution context at all.")


class RawAchievementList(BaseModel):
    achievements: list[RawAchievement]


class Certificate(BaseModel):
    name: str
    issuer: Optional[str] = None
    date: Optional[str] = None


class WorkExperienceEntry(BaseModel):
    company: str
    title: Optional[str] = None
    start_date: Optional[str] = None
    end_date: Optional[str] = None
    achievements: list[str] = Field(default_factory=list)


class ResumeExtraction(BaseModel):
    experience: list[WorkExperienceEntry]
    certifications: list[Certificate] = Field(default_factory=list)


class DocumentClassification(BaseModel):
    doc_type: Literal["resume", "linkedin_export", "recommendation_letter", "achievement_notes", "certificate", "other"]


_BASE_EXTRACTION_RULES = """
You are extracting real career achievements from a personal document so they can
become resume bullet points later. Follow these rules strictly:
- Extract only what the source text actually supports. Light rephrasing for
  clarity is fine (fixing grammar, tightening a run-on sentence). Inventing or
  inferring a metric, scope, team size, or outcome that is not stated or
  clearly implied in the source text is NOT fine.
- It is fine to lightly connect obvious dots within this one document (e.g. a
  job title mentioned in one line applying to an achievement described two
  lines later).
- Skip generic filler (objective statements, contact info, soft-skill lists
  with no evidence) -- only extract concrete achievements or accomplishments.
- For each achievement, capture whatever company, date, or job-title context
  appears near it in the source, even if incomplete. Do not guess a company
  name that never appears in the text.
- Set confidence to "high" only when the company AND a date or clear time
  period are both explicitly stated near the achievement. Use "medium" when
  attribution is implied but not explicit. Use "low" when there is no
  attribution context at all.
"""

_EXTRACTION_PROMPTS = {
    "recommendation_letter": _BASE_EXTRACTION_RULES + """
This document is a letter of recommendation written ABOUT this person by
someone else, in third person. Extract only the specific, concrete
achievements or projects the letter describes this person doing -- not the
letter-writer's own opinions, adjectives, or general praise with no
underlying specific action attached.
""",
    "achievement_notes": _BASE_EXTRACTION_RULES + """
This document is free-form notes the person wrote about their own past
achievements. Extract each distinct achievement as its own entry.
""",
    "other": _BASE_EXTRACTION_RULES + """
This document's type is unclear. Extract any concrete, achievement-shaped
statements you find; skip anything that is not a specific accomplishment.
""",
}

_RESUME_EXTRACTION_PROMPT = _BASE_EXTRACTION_RULES + """
This document is a resume or LinkedIn profile export. For each job/role
listed, extract the company name, job title, start/end dates as written,
and every achievement bullet under that role, verbatim or lightly
rephrased for clarity only.

Separately, if this document also lists any certifications or credentials
(e.g. a "Certifications" section), extract those into the certifications
list instead of treating them as achievement bullets -- a credential isn't
an achievement. Do not invent an issuer or date if the document doesn't
state one; use null instead.
"""

_CERTIFICATE_PROMPT = """
You are extracting a professional certificate or credential from a document.
Return the credential's name, issuing organization (if stated), and the date
issued or earned (if stated). Do not invent any of these fields if they are
not present in the source -- use null instead.
"""

_CLASSIFY_PROMPT = """
Classify this document into exactly one category: resume, linkedin_export,
recommendation_letter, achievement_notes, certificate, or other. Use the
filename and the content sample provided.
"""

_FILENAME_HEURISTICS = [
    (("linkedin",), "linkedin_export"),
    (("resume", "cv"), "resume"),
    (("certificate", "certification"), "certificate"),
    (("recommendation", "reference letter", "letter of rec"), "recommendation_letter"),
]


def _api_key() -> str | None:
    return os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")


def _generate_from_upload(path: str, system_prompt: str, response_schema) -> str | None:
    """Uploads a PDF/image file directly to Gemini and returns raw response
    text. GeminiClient's REST client has no file-upload support, so this
    uses the google-genai SDK client directly -- the same proven pattern
    ingest.py already uses for its single-resume parse."""
    client = genai.Client(api_key=_api_key())
    uploaded = client.files.upload(file=path)
    config = types.GenerateContentConfig(
        system_instruction=system_prompt,
        response_mime_type="application/json",
        response_schema=response_schema,
        temperature=0.0,
    )
    response = client.models.generate_content(
        model=UPLOAD_MODEL, contents=[uploaded, "Extract the requested information."], config=config,
    )
    return response.text


def classify_document_type(filename: str, text: str | None, dry_run: bool = False) -> str:
    """Classifies a document by filename heuristic first; falls back to an
    LLM call over its text only when a heuristic doesn't match AND text is
    available. PDFs/images (text=None) with no filename match default to
    'achievement_notes' rather than spending a second multimodal API call
    just to classify -- most real filenames aren't that ambiguous, and this
    keeps ingestion cost proportionate."""
    lowered = filename.lower()
    for keywords, doc_type in _FILENAME_HEURISTICS:
        if any(kw in lowered for kw in keywords):
            return doc_type

    if text is None:
        return "achievement_notes"

    if dry_run:
        print(f"[DRY RUN] would classify {filename!r} via LLM over its text sample.")
        return "other"

    sample = text[:2000]
    raw, _ = GeminiClient.generate(
        model=EXTRACTION_MODEL,
        system_instruction=_CLASSIFY_PROMPT,
        contents=f"Filename: {filename}\n\nContent sample:\n{sample}",
        response_schema=DocumentClassification,
        temperature=0.0,
    )
    data = GeminiClient.parse_json(raw)
    return data.get("doc_type", "other")


def extract_achievements(
    doc_type: str, *, text: str | None = None, upload_path: str | None = None, dry_run: bool = False,
) -> list[RawAchievement]:
    """Extracts achievement-shaped content for doc_type in
    ('recommendation_letter', 'achievement_notes', 'other'). Exactly one of
    text or upload_path must be set."""
    if (text is None) == (upload_path is None):
        raise ValueError("extract_achievements requires exactly one of text or upload_path")

    system_prompt = _EXTRACTION_PROMPTS.get(doc_type, _EXTRACTION_PROMPTS["other"])

    if dry_run:
        print(f"[DRY RUN] would extract achievements (doc_type={doc_type!r}) with prompt:\n{system_prompt}")
        return []

    if upload_path is not None:
        raw = _generate_from_upload(upload_path, system_prompt, RawAchievementList)
    else:
        raw, _ = GeminiClient.generate(
            model=EXTRACTION_MODEL, system_instruction=system_prompt,
            contents=text, response_schema=RawAchievementList, temperature=0.0,
        )
    data = GeminiClient.parse_json(raw) if isinstance(raw, str) else (raw or {})
    return [RawAchievement(**a) for a in data.get("achievements", [])]


def extract_certificate(
    *, text: str | None = None, upload_path: str | None = None, dry_run: bool = False,
) -> Certificate | None:
    """Extracts a single credential (name/issuer/date) from a document
    classified as 'certificate'. Returns None if no credential name was
    found. Exactly one of text or upload_path must be set."""
    if (text is None) == (upload_path is None):
        raise ValueError("extract_certificate requires exactly one of text or upload_path")

    if dry_run:
        print("[DRY RUN] would extract a certificate.")
        return None

    if upload_path is not None:
        raw = _generate_from_upload(upload_path, _CERTIFICATE_PROMPT, Certificate)
    else:
        raw, _ = GeminiClient.generate(
            model=EXTRACTION_MODEL, system_instruction=_CERTIFICATE_PROMPT,
            contents=text, response_schema=Certificate, temperature=0.0,
        )
    data = GeminiClient.parse_json(raw) if isinstance(raw, str) else (raw or {})
    if not data.get("name"):
        return None
    return Certificate(**data)


def extract_resume_timeline_and_achievements(
    *, text: str | None = None, upload_path: str | None = None, dry_run: bool = False,
) -> ResumeExtraction:
    """Used specifically for documents classified as 'resume' or
    'linkedin_export' -- extracts the employment timeline (company, title,
    dates) AND each role's listed achievement bullets in one pass, since
    the source document already states which company each bullet belongs
    to (no separate attribution step needed for these). Also extracts any
    embedded certifications/credentials section into
    ResumeExtraction.certifications, rather than treating a credential as
    an achievement bullet. Exactly one of text or upload_path must be set."""
    if (text is None) == (upload_path is None):
        raise ValueError("extract_resume_timeline_and_achievements requires exactly one of text or upload_path")

    if dry_run:
        print("[DRY RUN] would extract resume/LinkedIn timeline, achievements, and certifications.")
        return ResumeExtraction(experience=[], certifications=[])

    if upload_path is not None:
        raw = _generate_from_upload(upload_path, _RESUME_EXTRACTION_PROMPT, ResumeExtraction)
    else:
        raw, _ = GeminiClient.generate(
            model=EXTRACTION_MODEL, system_instruction=_RESUME_EXTRACTION_PROMPT,
            contents=text, response_schema=ResumeExtraction, temperature=0.0,
        )
    data = GeminiClient.parse_json(raw) if isinstance(raw, str) else (raw or {})
    return ResumeExtraction(**data) if data else ResumeExtraction(experience=[], certifications=[])
