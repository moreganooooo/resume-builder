"""
polish.py -- interactive chat loop for polishing an already-generated
resume or cover letter's JSON. Each turn sends the current document plus
one plain-English instruction to Gemini (schema-constrained, same
schema/model the builder already uses) and gets back the complete
updated document; a diff of exactly what changed is shown before
anything is saved. Accepting a turn re-renders HTML and regenerates the
PDF immediately, same as the main tailoring pipeline.
"""

import os

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(SCRIPT_DIR)
OUTPUT_JSON_DIR = os.path.join(PROJECT_ROOT, "output", "json")
OUTPUT_HTML_DIR = os.path.join(PROJECT_ROOT, "output", "html")
OUTPUT_PDF_DIR = os.path.join(PROJECT_ROOT, "output", "pdf")

RESUME_SUFFIX = "_Resume.json"
COVERLETTER_SUFFIX = "_CoverLetter.json"


def detect_doc_type(path: str) -> str | None:
    """Returns "resume", "coverletter", or None if the filename doesn't
    end in a recognized suffix."""
    name = os.path.basename(path)
    if name.endswith(RESUME_SUFFIX):
        return "resume"
    if name.endswith(COVERLETTER_SUFFIX):
        return "coverletter"
    return None


def stem_from_json_path(path: str, doc_type: str) -> str:
    """Strips the doc_type's known suffix, returning the shared stem used
    to derive matching html/pdf output paths."""
    name = os.path.basename(path)
    suffix = RESUME_SUFFIX if doc_type == "resume" else COVERLETTER_SUFFIX
    return name[: -len(suffix)]
