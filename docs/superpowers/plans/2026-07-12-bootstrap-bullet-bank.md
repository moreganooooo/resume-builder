# Bootstrap Bullet Bank for New Users Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let a brand-new resume-builder user turn a folder of scattered personal documents (LinkedIn PDF export, resume, recommendation letters, achievement notes, certificates) into a real `bullet-bank-clean.csv`, then guide them through the existing six-stage pipeline, all from one menu entry point.

**Architecture:** Three new flat scripts (`bootstrap_extractors.py`, `bootstrap_timeline.py`, `bootstrap_bullet_bank.py`) implement ingestion → timeline-anchored attribution → auto-tagging → `bullet-bank-clean.csv`, then chain into the existing six pipeline scripts as subprocesses. A new menu entry point (`menu.py`/`cli_art.py`) drives the whole thing for someone with zero context on the system.

**Tech Stack:** Python 3.10+, `google-genai` SDK (file uploads) + the existing `GeminiClient` REST wrapper (text calls), `pydantic` for schemas, `python-docx`/`python-pptx`/`odfpy`/`pandas` for local text extraction, `questionary`/`rich` for CLI UX, stdlib `unittest`.

## Global Constraints

- New dependencies added to `requirements.txt`: `python-docx`, `python-pptx`, `odfpy` (pandas/openpyxl already present).
- None of the six existing pipeline scripts (`audit_bullet_bank.py`, `cluster_bullet_bank.py`, `rewrite_bullets.py`, `audit_keepers.py`, `score_keeper_gems.py`, `embed_bullet_bank.py`) may be modified — they are called unmodified, as subprocesses.
- All new path resolution follows the existing `SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))` / `PROJECT_ROOT = os.path.dirname(SCRIPT_DIR)` convention used throughout `scripts/`.
- All new tests follow the existing convention: `tests/test_*.py`, stdlib `unittest`, discovered via `python -m unittest discover -s tests -v`, importing scripts via `SCRIPTS_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts")` + `sys.path.insert(0, SCRIPTS_DIR)`.
- No automated test may make a real Gemini API call — every Gemini-calling function accepts a `dry_run: bool = False` parameter (matching `rewrite_bullets.py`'s existing convention: build the real prompt, print it, return a canned stub instead of calling the API) and/or gets mocked directly via `unittest.mock.patch`.
- All bootstrap-process artifacts live under `resume-engine/knowledge_base/bootstrap/`; the only file that ever leaves that folder is the final `resume-engine/knowledge_base/bullet-bank-clean.csv`.
- Extraction must stay strictly grounded: light rephrasing for clarity is fine; inventing or inferring a metric, scope, or detail not present in the source text is not. Every extraction system prompt must say so explicitly.
- The guided pipeline has exactly two confirmation gates — before `audit_bullet_bank.py` and before `rewrite_bullets.py` — and a `--yes` flag that skips both for an unattended run.

---

### Task 1: Add new dependencies

**Files:**
- Modify: `requirements.txt`
- Test: `tests/test_bootstrap_dependencies.py`

**Interfaces:**
- Produces: confirmation that `docx`, `pptx`, and `odf` (the import names for `python-docx`, `python-pptx`, `odfpy`) are importable — every later task relies on this.

- [ ] **Step 1: Write the failing test**

```python
import unittest


class TestBootstrapDependenciesImportable(unittest.TestCase):

    def test_python_docx_importable(self):
        import docx  # noqa: F401

    def test_python_pptx_importable(self):
        from pptx import Presentation  # noqa: F401

    def test_odfpy_importable(self):
        from odf.opendocument import load  # noqa: F401
        from odf import text, teletype  # noqa: F401


if __name__ == "__main__":
    unittest.main()
```

Save as `tests/test_bootstrap_dependencies.py`.

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m unittest tests.test_bootstrap_dependencies -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'docx'` (or `pptx`/`odf`).

- [ ] **Step 3: Add the dependencies**

Read the current `requirements.txt`, then append these three lines (keep existing lines untouched):

```
python-docx
python-pptx
odfpy
```

- [ ] **Step 4: Install and verify**

Run: `pip install -r requirements.txt`
Run: `python -m unittest tests.test_bootstrap_dependencies -v`
Expected: all 3 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add requirements.txt tests/test_bootstrap_dependencies.py
git commit -m "Add python-docx, python-pptx, odfpy for bootstrap document ingestion"
```

---

### Task 2: `bootstrap_extractors.py` — file-kind detection and local text extraction

**Files:**
- Create: `scripts/bootstrap_extractors.py`
- Test: `tests/test_bootstrap_extractors_local.py`

**Interfaces:**
- Consumes: nothing from earlier tasks (pure stdlib + the 3 new deps).
- Produces:
  - `detect_file_kind(path: str) -> str` — one of `"pdf"`, `"image"`, `"docx"`, `"doc"`, `"odt"`, `"pptx"`, `"spreadsheet"`, `"text"`, `"unsupported"`.
  - `extract_local_text(path: str, kind: str) -> str` — raises `ValueError` if `kind` is `"pdf"`/`"image"`/`"unsupported"` (those never call this).
  - `convert_legacy_doc_to_pdf(path: str) -> str | None` — returns a converted PDF path, or `None` if LibreOffice isn't available.
  - Module-level constant `SCRIPT_DIR` (for later tasks in the same file to build on).

- [ ] **Step 1: Write the failing tests**

```python
import os
import shutil
import sys
import tempfile
import unittest
from unittest.mock import patch

SCRIPTS_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts")
sys.path.insert(0, SCRIPTS_DIR)

import bootstrap_extractors  # noqa: E402


class TestDetectFileKind(unittest.TestCase):

    def test_pdf(self):
        self.assertEqual(bootstrap_extractors.detect_file_kind("resume.pdf"), "pdf")

    def test_images(self):
        for ext in ("png", "jpg", "jpeg", "heic", "webp"):
            with self.subTest(ext=ext):
                self.assertEqual(bootstrap_extractors.detect_file_kind(f"screenshot.{ext}"), "image")

    def test_docx(self):
        self.assertEqual(bootstrap_extractors.detect_file_kind("resume.docx"), "docx")

    def test_legacy_doc(self):
        self.assertEqual(bootstrap_extractors.detect_file_kind("old_resume.doc"), "doc")

    def test_odt(self):
        self.assertEqual(bootstrap_extractors.detect_file_kind("notes.odt"), "odt")

    def test_pptx(self):
        self.assertEqual(bootstrap_extractors.detect_file_kind("deck.pptx"), "pptx")

    def test_spreadsheet(self):
        self.assertEqual(bootstrap_extractors.detect_file_kind("achievements.xlsx"), "spreadsheet")
        self.assertEqual(bootstrap_extractors.detect_file_kind("achievements.csv"), "spreadsheet")

    def test_text(self):
        self.assertEqual(bootstrap_extractors.detect_file_kind("notes.txt"), "text")
        self.assertEqual(bootstrap_extractors.detect_file_kind("notes.md"), "text")

    def test_unsupported(self):
        self.assertEqual(bootstrap_extractors.detect_file_kind("archive.zip"), "unsupported")

    def test_case_insensitive(self):
        self.assertEqual(bootstrap_extractors.detect_file_kind("RESUME.PDF"), "pdf")


class TestExtractLocalTextDocx(unittest.TestCase):

    def test_round_trip(self):
        import docx
        tmp_dir = tempfile.mkdtemp()
        path = os.path.join(tmp_dir, "fixture.docx")
        doc = docx.Document()
        doc.add_paragraph("Led a 5-person team to launch the Q3 campaign.")
        doc.add_paragraph("Reduced churn by 12% over six months.")
        doc.save(path)

        text = bootstrap_extractors.extract_local_text(path, "docx")

        self.assertIn("Led a 5-person team to launch the Q3 campaign.", text)
        self.assertIn("Reduced churn by 12% over six months.", text)
        shutil.rmtree(tmp_dir)


class TestExtractLocalTextPptx(unittest.TestCase):

    def test_round_trip(self):
        from pptx import Presentation
        tmp_dir = tempfile.mkdtemp()
        path = os.path.join(tmp_dir, "fixture.pptx")
        prs = Presentation()
        slide = prs.slides.add_slide(prs.slide_layouts[1])
        slide.shapes.title.text = "Achievements"
        slide.placeholders[1].text = "Grew pipeline by $3M in one quarter."
        prs.save(path)

        text = bootstrap_extractors.extract_local_text(path, "pptx")

        self.assertIn("Grew pipeline by $3M in one quarter.", text)
        shutil.rmtree(tmp_dir)


class TestExtractLocalTextOdt(unittest.TestCase):

    def test_round_trip(self):
        from odf.opendocument import OpenDocumentText
        from odf.text import P
        tmp_dir = tempfile.mkdtemp()
        path = os.path.join(tmp_dir, "fixture.odt")
        doc = OpenDocumentText()
        doc.text.addElement(P(text="Migrated 2,900 accounts into Salesforce."))
        doc.save(path)

        text = bootstrap_extractors.extract_local_text(path, "odt")

        self.assertIn("Migrated 2,900 accounts into Salesforce.", text)
        shutil.rmtree(tmp_dir)


class TestExtractLocalTextSpreadsheet(unittest.TestCase):

    def test_csv_round_trip(self):
        tmp_dir = tempfile.mkdtemp()
        path = os.path.join(tmp_dir, "fixture.csv")
        with open(path, "w", encoding="utf-8") as f:
            f.write("Achievement,Year\nLaunched product X,2022\n")

        text = bootstrap_extractors.extract_local_text(path, "spreadsheet")

        self.assertIn("Launched product X", text)
        self.assertIn("2022", text)
        shutil.rmtree(tmp_dir)

    def test_xlsx_round_trip(self):
        import pandas as pd
        tmp_dir = tempfile.mkdtemp()
        path = os.path.join(tmp_dir, "fixture.xlsx")
        pd.DataFrame({"Achievement": ["Cut costs by 20%"], "Year": [2021]}).to_excel(path, index=False)

        text = bootstrap_extractors.extract_local_text(path, "spreadsheet")

        self.assertIn("Cut costs by 20%", text)
        shutil.rmtree(tmp_dir)


class TestExtractLocalTextPlain(unittest.TestCase):

    def test_txt_round_trip(self):
        tmp_dir = tempfile.mkdtemp()
        path = os.path.join(tmp_dir, "fixture.txt")
        with open(path, "w", encoding="utf-8") as f:
            f.write("Built a customer onboarding flow from scratch.")

        text = bootstrap_extractors.extract_local_text(path, "text")

        self.assertEqual(text, "Built a customer onboarding flow from scratch.")
        shutil.rmtree(tmp_dir)


class TestExtractLocalTextRejectsUnsupportedKinds(unittest.TestCase):

    def test_pdf_raises(self):
        with self.assertRaises(ValueError):
            bootstrap_extractors.extract_local_text("whatever.pdf", "pdf")

    def test_image_raises(self):
        with self.assertRaises(ValueError):
            bootstrap_extractors.extract_local_text("whatever.png", "image")


class TestConvertLegacyDocToPdf(unittest.TestCase):

    @patch("bootstrap_extractors.shutil.which", return_value=None)
    def test_returns_none_when_libreoffice_unavailable(self, mock_which):
        result = bootstrap_extractors.convert_legacy_doc_to_pdf("old.doc")
        self.assertIsNone(result)


if __name__ == "__main__":
    unittest.main()
```

Save as `tests/test_bootstrap_extractors_local.py`.

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m unittest tests.test_bootstrap_extractors_local -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'bootstrap_extractors'`.

- [ ] **Step 3: Write the implementation**

```python
#!/usr/bin/env python3
"""
bootstrap_extractors.py

File-type detection and text extraction for the new-user bootstrap pipeline
(see bootstrap_bullet_bank.py). Two families of document handling:

  - PDF and image files are never text-extracted locally -- they're uploaded
    directly to Gemini via the google-genai SDK's file API in a later task
    (extract_achievements/extract_certificate/extract_resume_timeline_and_
    achievements), the same multimodal pattern ingest.py already uses.
  - Everything else (.docx/.doc/.odt/.pptx/spreadsheets/plain text) gets its
    text pulled out locally first, then handled as plain text.

Legacy .doc is best-effort: if LibreOffice ("soffice") is on PATH, it gets
converted to PDF and treated as a normal PDF from then on. If not, the file
is skipped with a message telling the user to re-save it as .docx or .pdf.
"""

import os
import shutil
import subprocess
import tempfile

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(SCRIPT_DIR)

_EXTENSION_KIND_MAP = {
    ".pdf": "pdf",
    ".png": "image", ".jpg": "image", ".jpeg": "image",
    ".heic": "image", ".webp": "image",
    ".docx": "docx",
    ".doc": "doc",
    ".odt": "odt",
    ".pptx": "pptx",
    ".xlsx": "spreadsheet", ".csv": "spreadsheet",
    ".txt": "text", ".md": "text",
}


def detect_file_kind(path: str) -> str:
    """Routes a file to one of the supported kinds by extension, or
    'unsupported' if it isn't one this pipeline knows how to handle."""
    _, ext = os.path.splitext(path)
    return _EXTENSION_KIND_MAP.get(ext.lower(), "unsupported")


def convert_legacy_doc_to_pdf(path: str) -> str | None:
    """Best-effort .doc -> .pdf conversion via LibreOffice. Returns the
    converted PDF's path, or None if LibreOffice ("soffice") isn't on PATH
    or the conversion fails -- callers must handle None by skipping the
    file with a clear message, never a crash."""
    soffice = shutil.which("soffice")
    if not soffice:
        return None
    out_dir = tempfile.mkdtemp(prefix="bootstrap_doc_convert_")
    try:
        subprocess.run(
            [soffice, "--headless", "--convert-to", "pdf", "--outdir", out_dir, path],
            check=True, capture_output=True, timeout=60,
        )
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired):
        return None
    converted = os.path.join(out_dir, os.path.splitext(os.path.basename(path))[0] + ".pdf")
    return converted if os.path.exists(converted) else None


def _extract_docx_text(path: str) -> str:
    import docx
    doc = docx.Document(path)
    return "\n".join(p.text for p in doc.paragraphs if p.text.strip())


def _extract_pptx_text(path: str) -> str:
    from pptx import Presentation
    prs = Presentation(path)
    lines = []
    for slide in prs.slides:
        for shape in slide.shapes:
            if shape.has_text_frame and shape.text_frame.text.strip():
                lines.append(shape.text_frame.text)
    return "\n".join(lines)


def _extract_odt_text(path: str) -> str:
    from odf.opendocument import load
    from odf import text as odf_text, teletype
    doc = load(path)
    paragraphs = doc.getElementsByType(odf_text.P)
    return "\n".join(teletype.extractText(p) for p in paragraphs)


def _extract_spreadsheet_text(path: str) -> str:
    _, ext = os.path.splitext(path)
    if ext.lower() == ".csv":
        with open(path, encoding="utf-8") as f:
            return f.read()
    import pandas as pd
    sheets = pd.read_excel(path, sheet_name=None)
    parts = []
    for name, df in sheets.items():
        parts.append(f"=== Sheet: {name} ===\n{df.to_csv(index=False)}")
    return "\n\n".join(parts)


def _extract_plain_text(path: str) -> str:
    with open(path, encoding="utf-8") as f:
        return f.read()


def extract_local_text(path: str, kind: str) -> str:
    """Extracts plain text locally for every kind except 'pdf'/'image'
    (those are handled by direct Gemini file upload elsewhere) and
    'unsupported' -- raises ValueError for those, since callers should
    never reach this function with them."""
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
    raise ValueError(f"extract_local_text does not handle kind={kind!r}")
```

Save as `scripts/bootstrap_extractors.py`.

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m unittest tests.test_bootstrap_extractors_local -v`
Expected: all tests PASS.

- [ ] **Step 5: Commit**

```bash
git add scripts/bootstrap_extractors.py tests/test_bootstrap_extractors_local.py
git commit -m "Add file-kind detection and local text extraction for bootstrap ingestion"
```

---

### Task 3: `bootstrap_extractors.py` — schemas, classification, and Gemini-based extraction

**Files:**
- Modify: `scripts/bootstrap_extractors.py` (append to the file from Task 2)
- Test: `tests/test_bootstrap_extractors_llm.py`

**Interfaces:**
- Consumes: `SCRIPT_DIR` from Task 2 (already in the file).
- Produces (all in `bootstrap_extractors.py`, used by Task 5):
  - `class RawAchievement(BaseModel)` — `{raw_text: str, company_hint: str | None, date_hint: str | None, title_hint: str | None, confidence: Literal["high","medium","low"]}`
  - `class WorkExperienceEntry(BaseModel)` — `{company: str, title: str | None, start_date: str | None, end_date: str | None, achievements: list[str]}`
  - `class Certificate(BaseModel)` — `{name: str, issuer: str | None, date: str | None}`
  - `classify_document_type(filename: str, text: str | None, dry_run: bool = False) -> str` — one of `"resume"`, `"linkedin_export"`, `"recommendation_letter"`, `"achievement_notes"`, `"certificate"`, `"other"`.
  - `extract_achievements(doc_type: str, *, text: str | None = None, upload_path: str | None = None, dry_run: bool = False) -> list[RawAchievement]` — for `doc_type` in `("recommendation_letter", "achievement_notes", "other")`.
  - `extract_certificate(*, text: str | None = None, upload_path: str | None = None, dry_run: bool = False) -> Certificate | None`.
  - `extract_resume_timeline_and_achievements(*, text: str | None = None, upload_path: str | None = None, dry_run: bool = False) -> ResumeExtraction` — for `doc_type` in `("resume", "linkedin_export")`; `ResumeExtraction` has `{experience: list[WorkExperienceEntry], certifications: list[Certificate]}`. This is the one path where a document's own structure already states which company each achievement belongs to, so no separate attribution step is needed for these bullets. Certifications embedded in the same document (e.g. a resume's own "Certifications" section) are extracted here too, not left as achievement bullets.

This task defines two model constants used across all Gemini calls in this
file: `EXTRACTION_MODEL = "gemini-3.1-flash-lite"` for text-only calls
(matches `SCORE_MODEL`/`CRITIQUE_MODEL` elsewhere in this codebase — cheap,
reliable JSON compliance) and `UPLOAD_MODEL = "gemma-4-31b-it"` for
PDF/image file-upload calls (matches `ingest.py`'s `INGEST_MODEL` — already
proven with the google-genai SDK's multimodal file understanding).

- [ ] **Step 1: Write the failing tests**

```python
import os
import sys
import unittest
from unittest.mock import patch, MagicMock

SCRIPTS_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts")
sys.path.insert(0, SCRIPTS_DIR)

import bootstrap_extractors  # noqa: E402


class TestClassifyDocumentType(unittest.TestCase):

    def test_linkedin_filename_heuristic(self):
        result = bootstrap_extractors.classify_document_type("LinkedIn_Export.pdf", None)
        self.assertEqual(result, "linkedin_export")

    def test_resume_filename_heuristic(self):
        result = bootstrap_extractors.classify_document_type("My_Resume_2024.docx", "some text")
        self.assertEqual(result, "resume")

    def test_cv_filename_heuristic(self):
        result = bootstrap_extractors.classify_document_type("cv_final.pdf", None)
        self.assertEqual(result, "resume")

    def test_certificate_filename_heuristic(self):
        result = bootstrap_extractors.classify_document_type("AWS_Certificate.pdf", None)
        self.assertEqual(result, "certificate")

    def test_recommendation_filename_heuristic(self):
        result = bootstrap_extractors.classify_document_type("Recommendation_Letter_Jane.pdf", None)
        self.assertEqual(result, "recommendation_letter")

    def test_no_text_and_ambiguous_filename_defaults_to_achievement_notes(self):
        # PDFs/images have text=None; without a filename heuristic hit, we
        # don't spend a second multimodal API call just to classify --
        # default to the most general "look for achievements" framing.
        result = bootstrap_extractors.classify_document_type("scan0042.pdf", None)
        self.assertEqual(result, "achievement_notes")

    @patch("bootstrap_extractors.GeminiClient.generate")
    def test_ambiguous_filename_with_text_calls_llm(self, mock_generate):
        mock_generate.return_value = ('{"doc_type": "recommendation_letter"}', {})
        result = bootstrap_extractors.classify_document_type("document3.txt", "To whom it may concern...")
        self.assertEqual(result, "recommendation_letter")
        mock_generate.assert_called_once()

    def test_dry_run_skips_llm_call(self):
        with patch("bootstrap_extractors.GeminiClient.generate") as mock_generate:
            result = bootstrap_extractors.classify_document_type(
                "document3.txt", "some ambiguous text", dry_run=True
            )
            mock_generate.assert_not_called()
            self.assertEqual(result, "other")


class TestExtractAchievements(unittest.TestCase):

    @patch("bootstrap_extractors.GeminiClient.generate")
    def test_text_path_parses_achievements(self, mock_generate):
        mock_generate.return_value = (
            '{"achievements": [{"raw_text": "Led onboarding redesign", '
            '"company_hint": "Acme Corp", "date_hint": "2021", '
            '"title_hint": null, "confidence": "high"}]}',
            {},
        )
        result = bootstrap_extractors.extract_achievements(
            "achievement_notes", text="I led an onboarding redesign at Acme Corp in 2021."
        )
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0].raw_text, "Led onboarding redesign")
        self.assertEqual(result[0].company_hint, "Acme Corp")
        self.assertEqual(result[0].confidence, "high")

    def test_requires_exactly_one_of_text_or_upload_path(self):
        with self.assertRaises(ValueError):
            bootstrap_extractors.extract_achievements("achievement_notes")
        with self.assertRaises(ValueError):
            bootstrap_extractors.extract_achievements(
                "achievement_notes", text="a", upload_path="b"
            )

    @patch("bootstrap_extractors._generate_from_upload")
    def test_upload_path_calls_generate_from_upload(self, mock_upload):
        mock_upload.return_value = '{"achievements": []}'
        result = bootstrap_extractors.extract_achievements(
            "recommendation_letter", upload_path="/tmp/fake.pdf"
        )
        self.assertEqual(result, [])
        mock_upload.assert_called_once()

    def test_dry_run_returns_empty_without_calling_api(self):
        with patch("bootstrap_extractors.GeminiClient.generate") as mock_generate:
            result = bootstrap_extractors.extract_achievements(
                "achievement_notes", text="some notes", dry_run=True
            )
            mock_generate.assert_not_called()
            self.assertEqual(result, [])


class TestExtractCertificate(unittest.TestCase):

    @patch("bootstrap_extractors.GeminiClient.generate")
    def test_parses_certificate(self, mock_generate):
        mock_generate.return_value = (
            '{"name": "AWS Certified Solutions Architect", "issuer": "Amazon Web Services", "date": "2023"}',
            {},
        )
        cert = bootstrap_extractors.extract_certificate(text="AWS Certified Solutions Architect, issued 2023")
        self.assertEqual(cert.name, "AWS Certified Solutions Architect")
        self.assertEqual(cert.issuer, "Amazon Web Services")

    @patch("bootstrap_extractors.GeminiClient.generate")
    def test_returns_none_when_no_name_found(self, mock_generate):
        mock_generate.return_value = ('{"name": null, "issuer": null, "date": null}', {})
        cert = bootstrap_extractors.extract_certificate(text="not actually a certificate")
        self.assertIsNone(cert)


class TestExtractResumeTimelineAndAchievements(unittest.TestCase):

    @patch("bootstrap_extractors.GeminiClient.generate")
    def test_parses_experience_entries(self, mock_generate):
        mock_generate.return_value = (
            '{"experience": [{"company": "Acme Corp", "title": "Marketing Manager", '
            '"start_date": "2019", "end_date": "2022", '
            '"achievements": ["Grew email list by 40%", "Launched rebrand"]}], '
            '"certifications": []}',
            {},
        )
        result = bootstrap_extractors.extract_resume_timeline_and_achievements(text="fake resume text")
        self.assertEqual(len(result.experience), 1)
        self.assertEqual(result.experience[0].company, "Acme Corp")
        self.assertEqual(result.experience[0].achievements, ["Grew email list by 40%", "Launched rebrand"])
        self.assertEqual(result.certifications, [])

    @patch("bootstrap_extractors.GeminiClient.generate")
    def test_parses_embedded_certifications(self, mock_generate):
        mock_generate.return_value = (
            '{"experience": [], "certifications": '
            '[{"name": "PMP", "issuer": "PMI", "date": "2020"}]}',
            {},
        )
        result = bootstrap_extractors.extract_resume_timeline_and_achievements(text="fake resume text")
        self.assertEqual(len(result.certifications), 1)
        self.assertEqual(result.certifications[0].name, "PMP")

    def test_dry_run_returns_empty_resume_extraction(self):
        with patch("bootstrap_extractors.GeminiClient.generate") as mock_generate:
            result = bootstrap_extractors.extract_resume_timeline_and_achievements(
                text="fake resume text", dry_run=True
            )
            mock_generate.assert_not_called()
            self.assertEqual(result.experience, [])
            self.assertEqual(result.certifications, [])


class TestGenerateFromUpload(unittest.TestCase):

    @patch("bootstrap_extractors.genai.Client")
    def test_uploads_file_and_returns_response_text(self, mock_client_cls):
        mock_client = MagicMock()
        mock_client_cls.return_value = mock_client
        mock_client.files.upload.return_value = "uploaded-file-handle"
        mock_client.models.generate_content.return_value = MagicMock(text='{"achievements": []}')

        result = bootstrap_extractors._generate_from_upload(
            "/tmp/fake.pdf", "system prompt", bootstrap_extractors.RawAchievementList
        )

        self.assertEqual(result, '{"achievements": []}')
        mock_client.files.upload.assert_called_once_with(file="/tmp/fake.pdf")
        mock_client.models.generate_content.assert_called_once()


if __name__ == "__main__":
    unittest.main()
```

Save as `tests/test_bootstrap_extractors_llm.py`.

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m unittest tests.test_bootstrap_extractors_llm -v`
Expected: FAIL — `AttributeError: module 'bootstrap_extractors' has no attribute 'classify_document_type'` (and similar for the other new names).

- [ ] **Step 3: Write the implementation**

Append this to the end of `scripts/bootstrap_extractors.py` (keep everything from Task 2 in place):

```python
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
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m unittest tests.test_bootstrap_extractors_llm -v`
Expected: all tests PASS.

- [ ] **Step 5: Commit**

```bash
git add scripts/bootstrap_extractors.py tests/test_bootstrap_extractors_llm.py
git commit -m "Add Gemini-based document classification and achievement extraction"
```

---

### Task 4: `bootstrap_timeline.py` — timeline builder and achievement matcher

**Files:**
- Create: `scripts/bootstrap_timeline.py`
- Test: `tests/test_bootstrap_timeline.py`

**Interfaces:**
- Consumes: `bootstrap_extractors.WorkExperienceEntry`, `bootstrap_extractors.RawAchievement`, `bootstrap_extractors.EXTRACTION_MODEL` (Task 3); `GeminiClient` (already available via `gemini_client.py`).
- Produces (used by Task 5):
  - `class TimelineEntry(BaseModel)` — `{company: str, title: str | None, start_date: str | None, end_date: str | None, needs_review: bool, conflict_note: str | None}`
  - `build_timeline(by_source: dict[str, list[WorkExperienceEntry]]) -> list[TimelineEntry]` — keys are `"linkedin_export"`/`"resume"`.
  - `match_to_timeline(achievement: RawAchievement, timeline: list[TimelineEntry], dry_run: bool = False) -> tuple[str, str]` — returns `(company, confidence)`; confidence is `"high"`/`"medium"` for a real match, `"low"` for the `"Misc. / Unassigned"` fallback.

- [ ] **Step 1: Write the failing tests**

```python
import os
import sys
import unittest
from unittest.mock import patch

SCRIPTS_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts")
sys.path.insert(0, SCRIPTS_DIR)

import bootstrap_timeline  # noqa: E402
from bootstrap_extractors import WorkExperienceEntry, RawAchievement  # noqa: E402


class TestBuildTimelineNoConflict(unittest.TestCase):

    def test_linkedin_only(self):
        entries = bootstrap_timeline.build_timeline({
            "linkedin_export": [
                WorkExperienceEntry(company="Acme Corp", title="Manager", start_date="2019", end_date="2022"),
            ],
        })
        self.assertEqual(len(entries), 1)
        self.assertEqual(entries[0].company, "Acme Corp")
        self.assertFalse(entries[0].needs_review)

    def test_resume_and_linkedin_agree(self):
        entries = bootstrap_timeline.build_timeline({
            "linkedin_export": [
                WorkExperienceEntry(company="Acme Corp", title="Manager", start_date="2019", end_date="2022"),
            ],
            "resume": [
                WorkExperienceEntry(company="Acme Corp", title="Manager", start_date="2019", end_date="2022"),
            ],
        })
        self.assertEqual(len(entries), 1)
        self.assertFalse(entries[0].needs_review)

    def test_resume_only_company_included(self):
        entries = bootstrap_timeline.build_timeline({
            "resume": [
                WorkExperienceEntry(company="Beta Inc", title="Analyst", start_date="2015", end_date="2018"),
            ],
        })
        self.assertEqual(len(entries), 1)
        self.assertEqual(entries[0].company, "Beta Inc")

    def test_minor_date_overlap_not_flagged(self):
        entries = bootstrap_timeline.build_timeline({
            "linkedin_export": [
                WorkExperienceEntry(company="Acme Corp", title="Manager", start_date="2019", end_date="2022"),
            ],
            "resume": [
                WorkExperienceEntry(company="Acme Corp", title="Manager", start_date="2020", end_date="2022"),
            ],
        })
        self.assertEqual(len(entries), 1)
        self.assertFalse(entries[0].needs_review)
        # LinkedIn's range wins by default on a minor overlap discrepancy.
        self.assertEqual(entries[0].start_date, "2019")


class TestBuildTimelineConflict(unittest.TestCase):

    def test_non_overlapping_ranges_flagged_for_review(self):
        entries = bootstrap_timeline.build_timeline({
            "linkedin_export": [
                WorkExperienceEntry(company="Acme Corp", title="Manager", start_date="2019", end_date="2020"),
            ],
            "resume": [
                WorkExperienceEntry(company="Acme Corp", title="Manager", start_date="2022", end_date="2023"),
            ],
        })
        self.assertEqual(len(entries), 1)
        self.assertTrue(entries[0].needs_review)
        self.assertIsNotNone(entries[0].conflict_note)


class TestMatchToTimeline(unittest.TestCase):

    def setUp(self):
        self.timeline = [
            bootstrap_timeline.TimelineEntry(company="Acme Corp", title="Sales Manager", start_date="2019", end_date="2022"),
            bootstrap_timeline.TimelineEntry(company="Beta Inc", title="Analyst", start_date="2015", end_date="2018"),
        ]

    def test_matches_by_company_hint(self):
        achievement = RawAchievement(raw_text="Did a thing", company_hint="Acme Corp", date_hint=None, title_hint=None, confidence="high")
        company, confidence = bootstrap_timeline.match_to_timeline(achievement, self.timeline)
        self.assertEqual(company, "Acme Corp")
        self.assertEqual(confidence, "high")

    def test_matches_by_date_hint_when_unambiguous(self):
        achievement = RawAchievement(raw_text="Did a thing", company_hint=None, date_hint="2016", title_hint=None, confidence="medium")
        company, confidence = bootstrap_timeline.match_to_timeline(achievement, self.timeline)
        self.assertEqual(company, "Beta Inc")
        self.assertEqual(confidence, "medium")

    def test_matches_by_title_hint(self):
        achievement = RawAchievement(raw_text="Did a thing", company_hint=None, date_hint=None, title_hint="Sales Manager", confidence="medium")
        company, confidence = bootstrap_timeline.match_to_timeline(achievement, self.timeline)
        self.assertEqual(company, "Acme Corp")

    @patch("bootstrap_timeline._llm_match", return_value=None)
    def test_falls_back_to_misc_when_nothing_matches(self, mock_llm_match):
        achievement = RawAchievement(raw_text="did outbound sales work somewhere", company_hint=None, date_hint=None, title_hint=None, confidence="low")
        company, confidence = bootstrap_timeline.match_to_timeline(achievement, self.timeline)
        self.assertEqual(company, "Misc. / Unassigned")
        self.assertEqual(confidence, "low")

    @patch("bootstrap_timeline._llm_match", return_value="Acme Corp")
    def test_llm_fallback_used_when_hints_dont_match(self, mock_llm_match):
        achievement = RawAchievement(raw_text="while doing outbound sales", company_hint=None, date_hint=None, title_hint=None, confidence="low")
        company, confidence = bootstrap_timeline.match_to_timeline(achievement, self.timeline)
        self.assertEqual(company, "Acme Corp")
        self.assertEqual(confidence, "medium")

    def test_dry_run_skips_llm_fallback(self):
        achievement = RawAchievement(raw_text="ambiguous text", company_hint=None, date_hint=None, title_hint=None, confidence="low")
        with patch("bootstrap_timeline._llm_match") as mock_llm_match:
            company, confidence = bootstrap_timeline.match_to_timeline(achievement, self.timeline, dry_run=True)
            mock_llm_match.assert_not_called()
            self.assertEqual(company, "Misc. / Unassigned")


if __name__ == "__main__":
    unittest.main()
```

Save as `tests/test_bootstrap_timeline.py`.

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m unittest tests.test_bootstrap_timeline -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'bootstrap_timeline'`.

- [ ] **Step 3: Write the implementation**

```python
#!/usr/bin/env python3
"""
bootstrap_timeline.py

Builds a canonical company/role/date timeline from a new user's resume
and/or LinkedIn export, and matches every other extracted achievement
against it -- see bootstrap_bullet_bank.py for how this fits into the
overall ingestion flow.
"""

import os
import re
import sys
from typing import Optional

from pydantic import BaseModel

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
if SCRIPT_DIR not in sys.path:
    sys.path.insert(0, SCRIPT_DIR)

from bootstrap_extractors import EXTRACTION_MODEL, RawAchievement, WorkExperienceEntry  # noqa: E402
from gemini_client import GeminiClient  # noqa: E402


class TimelineEntry(BaseModel):
    company: str
    title: Optional[str] = None
    start_date: Optional[str] = None
    end_date: Optional[str] = None
    needs_review: bool = False
    conflict_note: Optional[str] = None


class TimelineMatchResult(BaseModel):
    matched_company: Optional[str] = None


def _normalize_company_name(name: str) -> str:
    """Lowercase, strip non-alphanumerics, for fuzzy same-company matching
    across documents that might spell a company name slightly differently."""
    return re.sub(r"[^a-z0-9]", "", name.lower())


def _extract_year(date_str: str | None) -> int | None:
    if not date_str:
        return None
    match = re.search(r"(19|20)\d{2}", date_str)
    return int(match.group(0)) if match else None


def _ranges_roughly_overlap(start_a, end_a, start_b, end_b) -> bool:
    """True if the two year ranges overlap at all. A missing/unparseable
    date on either side is treated as an open bound rather than a forced
    mismatch, since we'd rather under-flag than nag the user over dates
    we can't even parse."""
    ya_start, ya_end = _extract_year(start_a), _extract_year(end_a)
    yb_start, yb_end = _extract_year(start_b), _extract_year(end_b)
    if ya_start is None or yb_start is None:
        return True
    lo_a, hi_a = ya_start, (ya_end or 9999)
    lo_b, hi_b = yb_start, (yb_end or 9999)
    return lo_a <= hi_b and lo_b <= hi_a


def _year_in_range(year: int, start_date: str | None, end_date: str | None) -> bool:
    start_year = _extract_year(start_date) or 0
    end_year = _extract_year(end_date) or 9999
    return start_year <= year <= end_year


def build_timeline(by_source: dict[str, list[WorkExperienceEntry]]) -> list[TimelineEntry]:
    """
    Merges WorkExperienceEntry lists from the resume/LinkedIn documents
    (by_source keyed "linkedin_export"/"resume") into one canonical
    timeline. LinkedIn wins on date range when a same-company entry also
    appears in the resume with a differing-but-overlapping range. A
    same-company entry whose ranges disagree enough to suggest genuinely
    different stints is flagged needs_review instead of silently resolved.
    """
    primary = by_source.get("linkedin_export", [])
    secondary = by_source.get("resume", [])
    by_key: dict[str, TimelineEntry] = {}

    for e in primary:
        by_key[_normalize_company_name(e.company)] = TimelineEntry(
            company=e.company, title=e.title, start_date=e.start_date, end_date=e.end_date,
        )

    for e in secondary:
        key = _normalize_company_name(e.company)
        if key not in by_key:
            by_key[key] = TimelineEntry(
                company=e.company, title=e.title, start_date=e.start_date, end_date=e.end_date,
            )
            continue
        existing = by_key[key]
        if existing.start_date == e.start_date and existing.end_date == e.end_date:
            continue
        if _ranges_roughly_overlap(existing.start_date, existing.end_date, e.start_date, e.end_date):
            continue
        by_key[key] = TimelineEntry(
            company=existing.company,
            title=existing.title or e.title,
            start_date=existing.start_date,
            end_date=existing.end_date,
            needs_review=True,
            conflict_note=(
                f"LinkedIn shows {existing.start_date}-{existing.end_date}, "
                f"resume shows {e.start_date}-{e.end_date}"
            ),
        )

    return list(by_key.values())


def _llm_match(raw_text: str, timeline: list[TimelineEntry]) -> str | None:
    """LLM-assisted fallback for achievements whose wording implies a role
    ("while I was doing outbound sales") without a hint that matches any
    timeline entry by exact company/date/title substring."""
    options = "\n".join(
        f"- {e.company} ({e.title or 'unknown title'}, {e.start_date or '?'}-{e.end_date or '?'})"
        for e in timeline
    )
    raw, _ = GeminiClient.generate(
        model=EXTRACTION_MODEL,
        system_instruction=(
            "Given an achievement description and a list of a person's past "
            "roles, decide which single role (if any) this achievement most "
            "plausibly belongs to, based on context clues in the wording. "
            "Return matched_company as null if you are not reasonably confident."
        ),
        contents=f"Achievement: {raw_text}\n\nRoles:\n{options}",
        response_schema=TimelineMatchResult,
        temperature=0.0,
    )
    data = GeminiClient.parse_json(raw)
    return data.get("matched_company") or None


def match_to_timeline(
    achievement: RawAchievement, timeline: list[TimelineEntry], dry_run: bool = False,
) -> tuple[str, str]:
    """Returns (company, confidence). confidence is 'high'/'medium' for a
    real match, 'low' for the Misc./Unassigned fallback."""
    if achievement.company_hint:
        hint_key = _normalize_company_name(achievement.company_hint)
        for entry in timeline:
            if _normalize_company_name(entry.company) == hint_key:
                return entry.company, achievement.confidence

    if achievement.date_hint:
        year = _extract_year(achievement.date_hint)
        if year is not None:
            matches = [e for e in timeline if _year_in_range(year, e.start_date, e.end_date)]
            if len(matches) == 1:
                return matches[0].company, "medium"

    if achievement.title_hint:
        title_lower = achievement.title_hint.lower()
        matches = [e for e in timeline if e.title and title_lower in e.title.lower()]
        if len(matches) == 1:
            return matches[0].company, "medium"

    if dry_run:
        print(f"[DRY RUN] would ask the LLM to match: {achievement.raw_text[:60]!r}")
        return "Misc. / Unassigned", "low"

    if timeline:
        matched = _llm_match(achievement.raw_text, timeline)
        if matched:
            return matched, "medium"

    return "Misc. / Unassigned", "low"
```

Save as `scripts/bootstrap_timeline.py`.

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m unittest tests.test_bootstrap_timeline -v`
Expected: all tests PASS.

- [ ] **Step 5: Commit**

```bash
git add scripts/bootstrap_timeline.py tests/test_bootstrap_timeline.py
git commit -m "Add timeline builder and achievement-to-company matcher"
```

---

### Task 5: `bootstrap_bullet_bank.py` — Phase 0 ingestion orchestration

**Files:**
- Create: `scripts/bootstrap_bullet_bank.py`
- Test: `tests/test_bootstrap_bullet_bank_ingestion.py`

**Interfaces:**
- Consumes: `bootstrap_extractors.{detect_file_kind, convert_legacy_doc_to_pdf, extract_local_text, classify_document_type, extract_achievements, extract_certificate, extract_resume_timeline_and_achievements, RawAchievement, WorkExperienceEntry, Certificate}` (Tasks 2-3); `bootstrap_timeline.{build_timeline, match_to_timeline, TimelineEntry}` (Task 4); `tag_bullet_bank.assign_tags` (existing script, unmodified).
- Produces (used by Task 6 and the menu in Task 8):
  - Module-level path constants: `BOOTSTRAP_DIR`, `SOURCE_DOCS_DIR`, `TIMELINE_PATH`, `CHECKPOINT_PATH`, `DRAFT_CSV_PATH`, `REVIEW_CSV_PATH`, `CERTIFICATIONS_PATH`, `BULLET_BANK_CLEAN_PATH`.
  - `run_ingestion(dry_run: bool = False) -> dict` — returns `{"extracted": int, "attributed": int, "flagged": int, "certificates": int}`.
  - `print_ingestion_summary(summary: dict) -> None`.

- [ ] **Step 1: Write the failing tests**

```python
import json
import os
import shutil
import sys
import tempfile
import unittest
from unittest.mock import patch

SCRIPTS_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts")
sys.path.insert(0, SCRIPTS_DIR)

import bootstrap_bullet_bank  # noqa: E402
import bootstrap_extractors  # noqa: E402


class BootstrapIngestionTestCase(unittest.TestCase):
    """Redirects every bootstrap path constant to a fresh temp dir per test,
    mirroring how test_mine_bullet_bank.py redirects ResumeEngine.kb_dir."""

    def setUp(self):
        self.tmp_dir = tempfile.mkdtemp()
        self._patches = []
        for name in (
            "BOOTSTRAP_DIR", "SOURCE_DOCS_DIR", "TIMELINE_PATH", "CHECKPOINT_PATH",
            "DRAFT_CSV_PATH", "REVIEW_CSV_PATH", "CERTIFICATIONS_PATH", "BULLET_BANK_CLEAN_PATH",
        ):
            pass  # overwritten individually below for correct sub-paths

        self.bootstrap_dir = os.path.join(self.tmp_dir, "bootstrap")
        bootstrap_bullet_bank.BOOTSTRAP_DIR = self.bootstrap_dir
        bootstrap_bullet_bank.SOURCE_DOCS_DIR = os.path.join(self.bootstrap_dir, "source_documents")
        bootstrap_bullet_bank.TIMELINE_PATH = os.path.join(self.bootstrap_dir, "timeline.json")
        bootstrap_bullet_bank.CHECKPOINT_PATH = os.path.join(self.bootstrap_dir, "checkpoint.json")
        bootstrap_bullet_bank.DRAFT_CSV_PATH = os.path.join(self.bootstrap_dir, "bullet-bank-draft.csv")
        bootstrap_bullet_bank.REVIEW_CSV_PATH = os.path.join(self.bootstrap_dir, "review-needed.csv")
        bootstrap_bullet_bank.CERTIFICATIONS_PATH = os.path.join(self.bootstrap_dir, "certifications.json")
        bootstrap_bullet_bank.BULLET_BANK_CLEAN_PATH = os.path.join(self.tmp_dir, "bullet-bank-clean.csv")
        os.makedirs(bootstrap_bullet_bank.SOURCE_DOCS_DIR, exist_ok=True)

    def tearDown(self):
        shutil.rmtree(self.tmp_dir, ignore_errors=True)

    def _touch(self, filename: str) -> None:
        with open(os.path.join(bootstrap_bullet_bank.SOURCE_DOCS_DIR, filename), "w", encoding="utf-8") as f:
            f.write("placeholder")


class TestRunIngestionResumeOnly(BootstrapIngestionTestCase):

    @patch("bootstrap_bullet_bank.bootstrap_extractors.extract_resume_timeline_and_achievements")
    @patch("bootstrap_bullet_bank.bootstrap_extractors.classify_document_type", return_value="resume")
    @patch("bootstrap_bullet_bank.bootstrap_extractors.extract_local_text", return_value="fake resume text")
    @patch("bootstrap_bullet_bank.bootstrap_extractors.detect_file_kind", return_value="docx")
    def test_resume_achievements_land_directly_in_clean_csv(
        self, mock_detect, mock_extract_text, mock_classify, mock_extract_resume,
    ):
        self._touch("My_Resume.docx")
        mock_extract_resume.return_value = bootstrap_extractors.ResumeExtraction(
            experience=[
                bootstrap_extractors.WorkExperienceEntry(
                    company="Acme Corp", title="Manager", start_date="2019", end_date="2022",
                    achievements=["Grew email list by 40%"],
                )
            ],
            certifications=[],
        )

        summary = bootstrap_bullet_bank.run_ingestion()

        self.assertEqual(summary["extracted"], 1)
        self.assertEqual(summary["attributed"], 1)
        self.assertEqual(summary["flagged"], 0)
        with open(bootstrap_bullet_bank.BULLET_BANK_CLEAN_PATH, encoding="utf-8") as f:
            content = f.read()
        self.assertIn("Acme Corp", content)
        self.assertIn("Grew email list by 40%", content)


class TestRunIngestionAchievementNotes(BootstrapIngestionTestCase):

    @patch("bootstrap_bullet_bank.bootstrap_timeline.match_to_timeline")
    @patch("bootstrap_bullet_bank.bootstrap_extractors.extract_achievements")
    @patch("bootstrap_bullet_bank.bootstrap_extractors.classify_document_type", return_value="achievement_notes")
    @patch("bootstrap_bullet_bank.bootstrap_extractors.extract_local_text", return_value="some notes")
    @patch("bootstrap_bullet_bank.bootstrap_extractors.detect_file_kind", return_value="text")
    def test_low_confidence_achievement_goes_to_review(
        self, mock_detect, mock_extract_text, mock_classify, mock_extract_achievements, mock_match,
    ):
        self._touch("notes.txt")
        mock_extract_achievements.return_value = [
            bootstrap_extractors.RawAchievement(
                raw_text="Did something notable", company_hint=None, date_hint=None,
                title_hint=None, confidence="low",
            )
        ]
        mock_match.return_value = ("Misc. / Unassigned", "low")

        summary = bootstrap_bullet_bank.run_ingestion()

        self.assertEqual(summary["flagged"], 1)
        with open(bootstrap_bullet_bank.REVIEW_CSV_PATH, encoding="utf-8") as f:
            content = f.read()
        self.assertIn("Did something notable", content)


class TestRunIngestionCertificate(BootstrapIngestionTestCase):

    @patch("bootstrap_bullet_bank.bootstrap_extractors.extract_certificate")
    @patch("bootstrap_bullet_bank.bootstrap_extractors.classify_document_type", return_value="certificate")
    @patch("bootstrap_bullet_bank.bootstrap_extractors.extract_local_text", return_value="AWS cert text")
    @patch("bootstrap_bullet_bank.bootstrap_extractors.detect_file_kind", return_value="text")
    def test_certificate_goes_to_certifications_json_not_bullets(
        self, mock_detect, mock_extract_text, mock_classify, mock_extract_cert,
    ):
        self._touch("aws_cert.txt")
        mock_extract_cert.return_value = bootstrap_extractors.Certificate(
            name="AWS Certified Solutions Architect", issuer="AWS", date="2023",
        )

        summary = bootstrap_bullet_bank.run_ingestion()

        self.assertEqual(summary["certificates"], 1)
        self.assertEqual(summary["extracted"], 0)
        with open(bootstrap_bullet_bank.CERTIFICATIONS_PATH, encoding="utf-8") as f:
            certs = json.load(f)
        self.assertEqual(certs[0]["name"], "AWS Certified Solutions Architect")


class TestRunIngestionCheckpointResume(BootstrapIngestionTestCase):

    @patch("bootstrap_bullet_bank.bootstrap_extractors.extract_resume_timeline_and_achievements")
    @patch("bootstrap_bullet_bank.bootstrap_extractors.classify_document_type", return_value="resume")
    @patch("bootstrap_bullet_bank.bootstrap_extractors.extract_local_text", return_value="fake resume text")
    @patch("bootstrap_bullet_bank.bootstrap_extractors.detect_file_kind", return_value="docx")
    def test_already_done_file_is_not_reprocessed(
        self, mock_detect, mock_extract_text, mock_classify, mock_extract_resume,
    ):
        self._touch("My_Resume.docx")
        mock_extract_resume.return_value = bootstrap_extractors.ResumeExtraction(
            experience=[
                bootstrap_extractors.WorkExperienceEntry(
                    company="Acme Corp", title="Manager", start_date="2019", end_date="2022",
                    achievements=["Grew email list by 40%"],
                )
            ],
            certifications=[],
        )

        bootstrap_bullet_bank.run_ingestion()
        self.assertEqual(mock_extract_resume.call_count, 1)

        bootstrap_bullet_bank.run_ingestion()
        self.assertEqual(mock_extract_resume.call_count, 1, "second run should skip the already-done file")


class TestRunIngestionUnsupportedFile(BootstrapIngestionTestCase):

    def test_unsupported_file_is_skipped_not_crashed(self):
        self._touch("archive.zip")
        summary = bootstrap_bullet_bank.run_ingestion()
        self.assertEqual(summary["extracted"], 0)


if __name__ == "__main__":
    unittest.main()
```

Save as `tests/test_bootstrap_bullet_bank_ingestion.py`.

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m unittest tests.test_bootstrap_bullet_bank_ingestion -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'bootstrap_bullet_bank'`.

- [ ] **Step 3: Write the implementation**

```python
#!/usr/bin/env python3
"""
bootstrap_bullet_bank.py

Bootstraps a starter bullet bank for a new resume-builder user from a
folder of arbitrary personal documents (LinkedIn PDF export, resume,
recommendation letters, achievement notes, certificates, etc.), then
guides them through the existing six-stage pipeline (audit -> cluster ->
rewrite -> audit_keepers -> score_keeper_gems -> embed).

Phase 0 (this file's ingestion logic) is local/fast: extract, attribute to
a company via a resume/LinkedIn-anchored timeline, auto-tag, and write
bullet-bank-clean.csv directly -- there's no existing file to protect on a
first run, so no manual promotion step is needed.

Phases 1-6 call the existing pipeline scripts unmodified, as subprocesses,
with a confirmation gate before each of the two API-heavy stages
(audit_bullet_bank.py, rewrite_bullets.py). See run_full_pipeline() further
down this file (added in a later task).

Usage:
  python bootstrap_bullet_bank.py             # full run, with confirmation gates
  python bootstrap_bullet_bank.py --yes        # full run, unattended
"""

import csv
import json
import os
import sys

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(SCRIPT_DIR)
KB_DIR = os.path.join(PROJECT_ROOT, "resume-engine", "knowledge_base")

BOOTSTRAP_DIR = os.path.join(KB_DIR, "bootstrap")
SOURCE_DOCS_DIR = os.path.join(BOOTSTRAP_DIR, "source_documents")
TIMELINE_PATH = os.path.join(BOOTSTRAP_DIR, "timeline.json")
CHECKPOINT_PATH = os.path.join(BOOTSTRAP_DIR, "checkpoint.json")
DRAFT_CSV_PATH = os.path.join(BOOTSTRAP_DIR, "bullet-bank-draft.csv")
REVIEW_CSV_PATH = os.path.join(BOOTSTRAP_DIR, "review-needed.csv")
CERTIFICATIONS_PATH = os.path.join(BOOTSTRAP_DIR, "certifications.json")
BULLET_BANK_CLEAN_PATH = os.path.join(KB_DIR, "bullet-bank-clean.csv")

if SCRIPT_DIR not in sys.path:
    sys.path.insert(0, SCRIPT_DIR)

import bootstrap_extractors  # noqa: E402
import bootstrap_timeline  # noqa: E402
import tag_bullet_bank  # noqa: E402

DRAFT_CSV_FIELDS = ["Role / Company", "Tags", "Bullet Point", "source_file", "source_type"]


def _load_checkpoint() -> dict:
    if not os.path.exists(CHECKPOINT_PATH):
        return {}
    with open(CHECKPOINT_PATH, encoding="utf-8") as f:
        return json.load(f)


def _save_checkpoint(state: dict) -> None:
    os.makedirs(BOOTSTRAP_DIR, exist_ok=True)
    with open(CHECKPOINT_PATH, "w", encoding="utf-8") as f:
        json.dump(state, f, indent=2)


def _process_one_file(path: str, filename: str, dry_run: bool = False) -> dict:
    kind = bootstrap_extractors.detect_file_kind(path)
    if kind == "unsupported":
        print(f"  Skipping {filename}: unsupported file type.")
        return {"status": "error", "doc_type": "other"}

    if kind == "doc":
        converted = bootstrap_extractors.convert_legacy_doc_to_pdf(path)
        if converted is None:
            print(
                f"  Skipping {filename}: legacy .doc format and LibreOffice isn't "
                f"available. Please re-save it as .docx or .pdf."
            )
            return {"status": "error", "doc_type": "other"}
        path, kind = converted, "pdf"

    text = None if kind in ("pdf", "image") else bootstrap_extractors.extract_local_text(path, kind)
    doc_type = bootstrap_extractors.classify_document_type(filename, text, dry_run=dry_run)

    if doc_type == "certificate":
        cert = (
            bootstrap_extractors.extract_certificate(upload_path=path, dry_run=dry_run)
            if text is None
            else bootstrap_extractors.extract_certificate(text=text, dry_run=dry_run)
        )
        return {"status": "done", "doc_type": doc_type, "certificate": cert.model_dump() if cert else None}

    if doc_type in ("resume", "linkedin_export"):
        resume_extraction = (
            bootstrap_extractors.extract_resume_timeline_and_achievements(upload_path=path, dry_run=dry_run)
            if text is None
            else bootstrap_extractors.extract_resume_timeline_and_achievements(text=text, dry_run=dry_run)
        )
        return {
            "status": "done",
            "doc_type": doc_type,
            "work_experience": [e.model_dump() for e in resume_extraction.experience],
            "certificates_found": [c.model_dump() for c in resume_extraction.certifications],
        }

    achievements = (
        bootstrap_extractors.extract_achievements(doc_type, upload_path=path, dry_run=dry_run)
        if text is None
        else bootstrap_extractors.extract_achievements(doc_type, text=text, dry_run=dry_run)
    )
    return {"status": "done", "doc_type": doc_type, "achievements": [a.model_dump() for a in achievements]}


def _write_timeline(timeline: list) -> None:
    os.makedirs(BOOTSTRAP_DIR, exist_ok=True)
    with open(TIMELINE_PATH, "w", encoding="utf-8") as f:
        json.dump([e.model_dump() for e in timeline], f, indent=2)


def _write_draft_csv(matched_rows: list) -> None:
    os.makedirs(BOOTSTRAP_DIR, exist_ok=True)
    with open(DRAFT_CSV_PATH, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=DRAFT_CSV_FIELDS)
        writer.writeheader()
        for company, bullet, filename, doc_type, _confidence in matched_rows:
            writer.writerow({
                "Role / Company": company, "Tags": "", "Bullet Point": f"- {bullet}",
                "source_file": filename, "source_type": doc_type,
            })


def _write_review_csv(review_rows: list) -> None:
    os.makedirs(BOOTSTRAP_DIR, exist_ok=True)
    if not review_rows:
        if os.path.exists(REVIEW_CSV_PATH):
            os.remove(REVIEW_CSV_PATH)
        return
    with open(REVIEW_CSV_PATH, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=DRAFT_CSV_FIELDS)
        writer.writeheader()
        for company, bullet, filename, doc_type, _confidence in review_rows:
            writer.writerow({
                "Role / Company": company, "Tags": "", "Bullet Point": f"- {bullet}",
                "source_file": filename, "source_type": doc_type,
            })


def _write_certifications(certificates: list) -> None:
    os.makedirs(BOOTSTRAP_DIR, exist_ok=True)
    with open(CERTIFICATIONS_PATH, "w", encoding="utf-8") as f:
        json.dump(certificates, f, indent=2)


def _write_bullet_bank_clean(matched_rows: list) -> None:
    """Auto-tags every row (reusing tag_bullet_bank.assign_tags directly,
    in-process -- not shelled out to) and writes the final
    bullet-bank-clean.csv. No manual promotion step: a first-time user has
    no existing file at risk of being overwritten."""
    rows = []
    for company, bullet, _filename, _doc_type, _confidence in matched_rows:
        bullet_text = f"- {bullet}"
        tag_str, _needs_review = tag_bullet_bank.assign_tags(bullet_text)
        rows.append({"Role / Company": company, "Tags": tag_str, "Bullet Point": bullet_text})

    os.makedirs(os.path.dirname(BULLET_BANK_CLEAN_PATH), exist_ok=True)
    with open(BULLET_BANK_CLEAN_PATH, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=["Role / Company", "Tags", "Bullet Point"])
        writer.writeheader()
        writer.writerows(rows)


def run_ingestion(dry_run: bool = False) -> dict:
    """Runs Phase 0 end to end: extract every file in source_documents/,
    build a timeline from any resume/LinkedIn doc(s), attribute every other
    achievement against it, then auto-tag and write bullet-bank-clean.csv.
    Returns a summary dict: {extracted, attributed, flagged, certificates}."""
    os.makedirs(SOURCE_DOCS_DIR, exist_ok=True)
    checkpoint = _load_checkpoint()

    filenames = sorted(
        f for f in os.listdir(SOURCE_DOCS_DIR)
        if os.path.isfile(os.path.join(SOURCE_DOCS_DIR, f))
    )

    for filename in filenames:
        if checkpoint.get(filename, {}).get("status") == "done":
            continue
        path = os.path.join(SOURCE_DOCS_DIR, filename)
        try:
            checkpoint[filename] = _process_one_file(path, filename, dry_run=dry_run)
        except Exception as e:
            print(f"  Error processing {filename}: {e}")
            checkpoint[filename] = {"status": "error", "doc_type": "other"}
        _save_checkpoint(checkpoint)

    by_source: dict[str, list] = {}
    already_attributed_rows = []
    pending_achievements = []
    certificates = []

    for filename, result in checkpoint.items():
        if result.get("status") != "done":
            continue
        doc_type = result["doc_type"]
        if doc_type in ("resume", "linkedin_export"):
            entries = [bootstrap_extractors.WorkExperienceEntry(**e) for e in result.get("work_experience", [])]
            by_source.setdefault(doc_type, []).extend(entries)
            for entry in entries:
                for bullet in entry.achievements:
                    already_attributed_rows.append((entry.company, bullet, filename, doc_type))
            certificates.extend(result.get("certificates_found", []))
        elif doc_type == "certificate":
            if result.get("certificate"):
                certificates.append(result["certificate"])
        else:
            for a in result.get("achievements", []):
                pending_achievements.append((bootstrap_extractors.RawAchievement(**a), filename, doc_type))

    timeline = bootstrap_timeline.build_timeline(by_source)

    matched_rows = [(company, bullet, filename, doc_type, "high")
                     for company, bullet, filename, doc_type in already_attributed_rows]
    review_rows = []

    for achievement, filename, doc_type in pending_achievements:
        company, confidence = bootstrap_timeline.match_to_timeline(achievement, timeline, dry_run=dry_run)
        row = (company, achievement.raw_text, filename, doc_type, confidence)
        matched_rows.append(row)
        if confidence == "low":
            review_rows.append(row)

    _write_timeline(timeline)
    _write_draft_csv(matched_rows)
    _write_review_csv(review_rows)
    _write_certifications(certificates)
    _write_bullet_bank_clean(matched_rows)

    return {
        "extracted": len(matched_rows),
        "attributed": len(matched_rows) - len(review_rows),
        "flagged": len(review_rows),
        "certificates": len(certificates),
    }


def print_ingestion_summary(summary: dict) -> None:
    print(
        f"\nExtracted {summary['extracted']} achievement(s), "
        f"{summary['attributed']} confidently attributed, "
        f"{summary['flagged']} flagged for review, "
        f"{summary['certificates']} certificate(s) found."
    )
```

Save as `scripts/bootstrap_bullet_bank.py`.

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m unittest tests.test_bootstrap_bullet_bank_ingestion -v`
Expected: all tests PASS.

- [ ] **Step 5: Commit**

```bash
git add scripts/bootstrap_bullet_bank.py tests/test_bootstrap_bullet_bank_ingestion.py
git commit -m "Add bootstrap ingestion orchestration: extract, attribute, tag, write clean.csv"
```

---

### Task 6: `bootstrap_bullet_bank.py` — pipeline sequencer, CLI, and `main()`

**Files:**
- Modify: `scripts/bootstrap_bullet_bank.py` (append to the file from Task 5)
- Test: `tests/test_bootstrap_bullet_bank_pipeline.py`

**Interfaces:**
- Consumes: `run_ingestion`, `print_ingestion_summary`, `SCRIPT_DIR` (Task 5).
- Produces:
  - `PIPELINE_STAGES: list[str]` — the six existing script filenames, in order.
  - `run_stage(script_name: str) -> bool` — runs one script via `subprocess.run([sys.executable, path])`, returns `True` on exit code 0.
  - `run_full_pipeline(skip_confirm: bool = False) -> bool` — runs all six stages in order with the two confirmation gates; returns `True` only if every stage succeeded.
  - `main()` — argparse CLI with `--yes`.

- [ ] **Step 1: Write the failing tests**

```python
import os
import sys
import unittest
from unittest.mock import patch, MagicMock

SCRIPTS_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts")
sys.path.insert(0, SCRIPTS_DIR)

import bootstrap_bullet_bank  # noqa: E402


class TestPipelineStages(unittest.TestCase):

    def test_six_stages_in_correct_order(self):
        self.assertEqual(bootstrap_bullet_bank.PIPELINE_STAGES, [
            "audit_bullet_bank.py",
            "cluster_bullet_bank.py",
            "rewrite_bullets.py",
            "audit_keepers.py",
            "score_keeper_gems.py",
            "embed_bullet_bank.py",
        ])


class TestRunStage(unittest.TestCase):

    @patch("bootstrap_bullet_bank.subprocess.run")
    def test_returns_true_on_success(self, mock_run):
        mock_run.return_value = MagicMock(returncode=0)
        self.assertTrue(bootstrap_bullet_bank.run_stage("audit_bullet_bank.py"))

    @patch("bootstrap_bullet_bank.subprocess.run")
    def test_returns_false_on_nonzero_exit(self, mock_run):
        mock_run.return_value = MagicMock(returncode=1)
        self.assertFalse(bootstrap_bullet_bank.run_stage("audit_bullet_bank.py"))

    @patch("bootstrap_bullet_bank.subprocess.run")
    def test_invokes_with_current_interpreter_and_full_script_path(self, mock_run):
        mock_run.return_value = MagicMock(returncode=0)
        bootstrap_bullet_bank.run_stage("audit_bullet_bank.py")
        args, _kwargs = mock_run.call_args
        self.assertEqual(args[0][0], sys.executable)
        self.assertTrue(args[0][1].endswith("audit_bullet_bank.py"))


class TestRunFullPipeline(unittest.TestCase):

    @patch("bootstrap_bullet_bank.questionary.confirm")
    @patch("bootstrap_bullet_bank.run_stage", return_value=True)
    def test_all_stages_run_in_order_when_confirmed(self, mock_run_stage, mock_confirm):
        mock_confirm.return_value.ask.return_value = True
        result = bootstrap_bullet_bank.run_full_pipeline(skip_confirm=False)
        self.assertTrue(result)
        called_scripts = [call.args[0] for call in mock_run_stage.call_args_list]
        self.assertEqual(called_scripts, bootstrap_bullet_bank.PIPELINE_STAGES)

    @patch("bootstrap_bullet_bank.questionary.confirm")
    @patch("bootstrap_bullet_bank.run_stage")
    def test_stops_immediately_on_stage_failure(self, mock_run_stage, mock_confirm):
        mock_confirm.return_value.ask.return_value = True
        mock_run_stage.side_effect = [True, False]  # cluster_bullet_bank.py fails
        result = bootstrap_bullet_bank.run_full_pipeline(skip_confirm=False)
        self.assertFalse(result)
        self.assertEqual(mock_run_stage.call_count, 2)

    @patch("bootstrap_bullet_bank.questionary.confirm")
    @patch("bootstrap_bullet_bank.run_stage", return_value=True)
    def test_yes_flag_skips_all_confirmation_prompts(self, mock_run_stage, mock_confirm):
        result = bootstrap_bullet_bank.run_full_pipeline(skip_confirm=True)
        self.assertTrue(result)
        mock_confirm.assert_not_called()

    @patch("bootstrap_bullet_bank.questionary.confirm")
    @patch("bootstrap_bullet_bank.run_stage", return_value=True)
    def test_declining_first_gate_stops_before_any_stage_runs(self, mock_run_stage, mock_confirm):
        mock_confirm.return_value.ask.return_value = False
        result = bootstrap_bullet_bank.run_full_pipeline(skip_confirm=False)
        self.assertFalse(result)
        mock_run_stage.assert_not_called()

    @patch("bootstrap_bullet_bank.questionary.confirm")
    @patch("bootstrap_bullet_bank.run_stage", return_value=True)
    def test_two_confirmation_gates_total(self, mock_run_stage, mock_confirm):
        mock_confirm.return_value.ask.return_value = True
        bootstrap_bullet_bank.run_full_pipeline(skip_confirm=False)
        self.assertEqual(mock_confirm.call_count, 2)


class TestMainDryRun(unittest.TestCase):
    """--dry-run threads through to run_ingestion() (which mocks/skips every
    Gemini call per Tasks 3-5) and must never invoke the real six-stage
    pipeline -- running those scripts for real would defeat the point of a
    dry run."""

    @patch("bootstrap_bullet_bank.run_full_pipeline")
    @patch("bootstrap_bullet_bank.run_ingestion")
    @patch("sys.argv", ["bootstrap_bullet_bank.py", "--dry-run"])
    def test_dry_run_skips_full_pipeline(self, mock_run_ingestion, mock_run_full_pipeline):
        mock_run_ingestion.return_value = {"extracted": 0, "attributed": 0, "flagged": 0, "certificates": 0}
        bootstrap_bullet_bank.main()
        mock_run_ingestion.assert_called_once_with(dry_run=True)
        mock_run_full_pipeline.assert_not_called()

    @patch("bootstrap_bullet_bank.run_full_pipeline", return_value=True)
    @patch("bootstrap_bullet_bank.run_ingestion")
    @patch("sys.argv", ["bootstrap_bullet_bank.py"])
    def test_without_dry_run_calls_full_pipeline(self, mock_run_ingestion, mock_run_full_pipeline):
        mock_run_ingestion.return_value = {"extracted": 0, "attributed": 0, "flagged": 0, "certificates": 0}
        bootstrap_bullet_bank.main()
        mock_run_ingestion.assert_called_once_with(dry_run=False)
        mock_run_full_pipeline.assert_called_once()


if __name__ == "__main__":
    unittest.main()
```

Save as `tests/test_bootstrap_bullet_bank_pipeline.py`.

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m unittest tests.test_bootstrap_bullet_bank_pipeline -v`
Expected: FAIL with `AttributeError: module 'bootstrap_bullet_bank' has no attribute 'PIPELINE_STAGES'`.

- [ ] **Step 3: Write the implementation**

Append this to the end of `scripts/bootstrap_bullet_bank.py` (keep everything from Task 5 in place):

```python
import argparse
import subprocess

import questionary

PIPELINE_STAGES = [
    "audit_bullet_bank.py",
    "cluster_bullet_bank.py",
    "rewrite_bullets.py",
    "audit_keepers.py",
    "score_keeper_gems.py",
    "embed_bullet_bank.py",
]

# Gate before index 0 (audit_bullet_bank.py) and index 2 (rewrite_bullets.py)
# -- the two stages that make a real API call per bullet.
_CONFIRMATION_GATES = {
    0: "Ready to run the quality-audit stage? This calls the API once per "
       "bullet and may take a while.",
    2: "Ready to run the rewrite stage? This is the other API-heavy step "
       "and may take a while.",
}

_STAGE_HINTS = {
    0: "\U0001F4A1 Quality check time — every bullet gets scored the way a "
       "skeptical hiring manager would read it. This is the first API-heavy step.",
    1: "\U0001F4A1 Grouping near-duplicate bullets and keeping only the "
       "strongest version of each.",
    2: "\U0001F4A1 Rewriting anything that didn't pass the quality check — "
       "the other API-heavy step.",
    3: "\U0001F4A1 Quick re-check on the rewritten bullets to make sure they "
       "actually improved.",
    4: "\U0001F4A1 Flagging standout 'hidden gem' bullets — the ones a "
       "hiring manager would specifically remember.",
    5: "\U0001F4A1 Last step — converting everything into a format the "
       "system can use to intelligently match bullets to a job description "
       "later.",
}


def run_stage(script_name: str) -> bool:
    """Runs one existing pipeline script, unmodified, as its own
    subprocess. Returns True if it exited successfully."""
    script_path = os.path.join(SCRIPT_DIR, script_name)
    result = subprocess.run([sys.executable, script_path])
    return result.returncode == 0


def run_full_pipeline(skip_confirm: bool = False) -> bool:
    """Runs all six existing pipeline stages in order, with a confirmation
    gate before each of the two API-heavy stages. Stops immediately (and
    does not continue to later stages) the moment any stage fails or a
    gate is declined. Since each stage already checkpoints internally,
    simply re-running this function later resumes correctly."""
    for i, script_name in enumerate(PIPELINE_STAGES):
        if i in _CONFIRMATION_GATES and not skip_confirm:
            proceed = questionary.confirm(_CONFIRMATION_GATES[i], default=True).ask()
            if not proceed:
                print("Stopped. Re-run this same command later to continue from here.")
                return False

        print(f"\n{_STAGE_HINTS[i]}")
        print(f"Stage {i + 1} of {len(PIPELINE_STAGES)}: running {script_name}...")
        if not run_stage(script_name):
            print(f"\nStage {i + 1} ({script_name}) failed. Re-run this same command to resume from here.")
            return False

    print("\n\U0001F389 All done! Your bullet bank is ready.")
    return True


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--yes", action="store_true", help="Skip confirmation gates and run the full pipeline unattended.")
    parser.add_argument("--dry-run", action="store_true", help="Print prompts instead of calling the API, and skip the real six-stage pipeline entirely.")
    args = parser.parse_args()

    summary = run_ingestion(dry_run=args.dry_run)
    print_ingestion_summary(summary)

    if args.dry_run:
        print("\n--dry-run set: skipping the six-stage pipeline.")
        return

    run_full_pipeline(skip_confirm=args.yes)


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m unittest tests.test_bootstrap_bullet_bank_pipeline -v`
Expected: all tests PASS.

- [ ] **Step 5: Commit**

```bash
git add scripts/bootstrap_bullet_bank.py tests/test_bootstrap_bullet_bank_pipeline.py
git commit -m "Add guided pipeline sequencer and CLI entry point to bootstrap_bullet_bank.py"
```

---

### Task 7: `cli_art.py` — hint styling and the bootstrap intro panel

**Files:**
- Modify: `scripts/cli_art.py`
- Test: `tests/test_cli_art_bootstrap.py`

**Interfaces:**
- Consumes: nothing new from earlier tasks (this file only touches existing `cli_art.py` constants/functions).
- Produces (used by Task 8):
  - `HINT` constant, matching the existing `SUCCESS`/`ERROR`/`WARNING` pattern.
  - `QUESTIONARY_STYLE` gains a `'new_user'` token.
  - `display_bootstrap_intro(doc_count: int) -> None`.

- [ ] **Step 1: Write the failing tests**

```python
import os
import sys
import unittest

SCRIPTS_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts")
sys.path.insert(0, SCRIPTS_DIR)

import cli_art  # noqa: E402


class TestHintConstant(unittest.TestCase):

    def test_hint_constant_exists_and_is_styled(self):
        self.assertIn("\U0001F4A1", cli_art.HINT)
        self.assertIn("[bold cyan]", cli_art.HINT)


class TestNewUserStyleToken(unittest.TestCase):

    def test_new_user_token_registered(self):
        style_rules = dict(cli_art.QUESTIONARY_STYLE.style_rules)
        self.assertIn("class:new_user", style_rules)
        self.assertIn("#4caf50", style_rules["class:new_user"])


class TestDisplayBootstrapIntro(unittest.TestCase):

    def test_runs_without_error_and_mentions_doc_count(self):
        console = cli_art.Console(record=True)
        original_console = cli_art.console
        cli_art.console = console
        try:
            cli_art.display_bootstrap_intro(3)
        finally:
            cli_art.console = original_console
        output = console.export_text()
        self.assertIn("3", output)


if __name__ == "__main__":
    unittest.main()
```

Save as `tests/test_cli_art_bootstrap.py`.

Note: `questionary.Style.style_rules` is a list of `(name, value)` tuples where `name` already includes the `class:` prefix internally when compiled, but the raw list stored on `.style_rules` uses bare names like `'new_user'` (matching the existing entries — e.g. `'qmark'`, `'pointer'` — none of which are prefixed in the source list). Adjust the test to check for the bare key if a first run shows a mismatch:

```python
    def test_new_user_token_registered(self):
        style_rules = dict(cli_art.QUESTIONARY_STYLE.style_rules)
        self.assertIn("new_user", style_rules)
        self.assertIn("#4caf50", style_rules["new_user"])
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m unittest tests.test_cli_art_bootstrap -v`
Expected: FAIL — `AttributeError: module 'cli_art' has no attribute 'HINT'`.

- [ ] **Step 3: Write the implementation**

In `scripts/cli_art.py`, add `HINT` next to the existing `SUCCESS`/`ERROR`/`WARNING` constants:

```python
SUCCESS = "[bold green]✓[/bold green]"
ERROR = "[bold red]✗[/bold red]"
WARNING = "[bold yellow]⚠[/bold yellow]"
HINT = "[bold cyan]💡[/bold cyan]"
```

Add the `new_user` token to `QUESTIONARY_STYLE`'s list (insert after `'separator'`):

```python
QUESTIONARY_STYLE = Style([
    ('qmark', 'fg:#673ab7 bold'),
    ('question', 'bold'),
    ('answer', 'fg:#2196f3 bold'),
    ('pointer', 'fg:#673ab7 bold'),
    ('highlighted', 'fg:#673ab7 bold'),
    ('selected', 'fg:#4caf50'),
    ('separator', 'fg:#cc5454'),
    ('new_user', 'fg:#4caf50 bold'),
    ('instruction', ''),
    ('text', ''),
])
```

Add `display_bootstrap_intro` next to `display_whats_next_panel`:

```python
def display_bootstrap_intro(doc_count: int) -> None:
    body = (
        f"Here's what's about to happen:\n\n"
        f"I'll read through your {doc_count} document(s) and pull out real "
        f"achievements, figure out which company each one belongs to, tag "
        f"them by skill area, then run them through a quality-check, "
        f"cleanup, and rewrite pipeline so you end up with a polished "
        f"bullet bank.\n\n"
        f"Two of these steps make real API calls and can take a few "
        f"minutes — I'll let you know before each one."
    )
    console.print(Panel(body, title="New User Bootstrap", border_style="#4caf50", box=box.ROUNDED, padding=(1, 2)))
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m unittest tests.test_cli_art_bootstrap -v`
Expected: all tests PASS. If `test_new_user_token_registered` fails on the `"class:new_user"` variant, switch to the bare-key version shown above and re-run.

- [ ] **Step 5: Commit**

```bash
git add scripts/cli_art.py tests/test_cli_art_bootstrap.py
git commit -m "Add HINT styling and bootstrap intro panel to cli_art.py"
```

---

### Task 8: `menu.py` — the "New User? Start Here!" entry point

**Files:**
- Modify: `scripts/menu.py`
- Test: `tests/test_menu_bootstrap.py`

**Interfaces:**
- Consumes: `bootstrap_bullet_bank.{SOURCE_DOCS_DIR, SCRIPT_DIR}` (Task 5/6); `cli_art.{QUESTIONARY_STYLE, display_bootstrap_intro, console}` (Task 7).
- Produces: `menu._handle_bootstrap() -> bool`; `menu._CHOICES[0].value == "bootstrap"`; `menu._HANDLERS["bootstrap"]`.

- [ ] **Step 1: Write the failing tests**

```python
import os
import sys
import unittest
from unittest.mock import patch, MagicMock

SCRIPTS_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts")
sys.path.insert(0, SCRIPTS_DIR)

import menu  # noqa: E402


class TestBootstrapChoiceRegistered(unittest.TestCase):

    def test_bootstrap_is_first_choice(self):
        first = menu._CHOICES[0]
        self.assertEqual(first.value, "bootstrap")

    def test_bootstrap_handler_registered(self):
        self.assertIn("bootstrap", menu._HANDLERS)
        self.assertIs(menu._HANDLERS["bootstrap"], menu._handle_bootstrap)


class TestHandleBootstrapEmptyFolder(unittest.TestCase):

    @patch("menu.questionary.confirm")
    @patch("menu.os.listdir", return_value=[])
    @patch("menu.os.makedirs")
    def test_returns_false_and_does_not_prompt_when_empty(self, mock_makedirs, mock_listdir, mock_confirm):
        result = menu._handle_bootstrap()
        self.assertFalse(result)
        mock_confirm.assert_not_called()


class TestHandleBootstrapWithFiles(unittest.TestCase):

    @patch("menu.subprocess.run")
    @patch("menu.cli_art.display_bootstrap_intro")
    @patch("menu.questionary.confirm")
    @patch("menu.os.path.isfile", return_value=True)
    @patch("menu.os.listdir", return_value=["resume.pdf", "linkedin.pdf"])
    @patch("menu.os.makedirs")
    def test_confirms_and_runs_subprocess_when_files_present(
        self, mock_makedirs, mock_listdir, mock_isfile, mock_confirm, mock_intro, mock_run,
    ):
        mock_confirm.return_value.ask.return_value = True
        mock_run.return_value = MagicMock(returncode=0)

        result = menu._handle_bootstrap()

        self.assertTrue(result)
        mock_intro.assert_called_once_with(2)
        mock_run.assert_called_once()

    @patch("menu.subprocess.run")
    @patch("menu.questionary.confirm")
    @patch("menu.os.path.isfile", return_value=True)
    @patch("menu.os.listdir", return_value=["resume.pdf"])
    @patch("menu.os.makedirs")
    def test_declining_confirm_does_not_run_subprocess(
        self, mock_makedirs, mock_listdir, mock_isfile, mock_confirm, mock_run,
    ):
        mock_confirm.return_value.ask.return_value = False
        result = menu._handle_bootstrap()
        self.assertFalse(result)
        mock_run.assert_not_called()


if __name__ == "__main__":
    unittest.main()
```

Save as `tests/test_menu_bootstrap.py`.

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m unittest tests.test_menu_bootstrap -v`
Expected: FAIL — `menu._CHOICES[0].value` is `"scan"`, not `"bootstrap"` (and `_handle_bootstrap` doesn't exist yet).

- [ ] **Step 3: Write the implementation**

In `scripts/menu.py`, add two imports near the top (alongside the existing `import orchestrator` etc.):

```python
import subprocess
import sys

import bootstrap_bullet_bank
```

Change `_CHOICES` to add the new entry first, followed by a separator:

```python
_CHOICES = [
    questionary.Choice(title=[("class:new_user", "--> New User? Start Here!")], value="bootstrap"),
    questionary.Separator(),
    questionary.Choice(title="Scan for New Postings", value="scan"),
    questionary.Choice(title="Check Posting Liveness", value="liveness"),
    questionary.Choice(title="Evaluate ALL Pending JDs", value="evaluate_all"),
    questionary.Choice(title="Evaluate a Specific JD", value="evaluate_one"),
    questionary.Choice(title="Customize Resume for ALL Pending JDs (batch)", value="tailor_all"),
    questionary.Choice(title="Customize Resume for a Specific JD", value="tailor_one"),
    questionary.Choice(title="Write cover letter for a Specific JD", value="coverletter_one"),
    questionary.Choice(title="Polish a resume or cover letter", value="polish"),
    questionary.Choice(title="View Application Tracker", value="view_applications"),
    questionary.Choice(title="Exit", value="exit"),
]
```

Add the new handler, near `_handle_scan`:

```python
def _handle_bootstrap() -> bool:
    os.makedirs(bootstrap_bullet_bank.SOURCE_DOCS_DIR, exist_ok=True)
    files = [
        f for f in os.listdir(bootstrap_bullet_bank.SOURCE_DOCS_DIR)
        if os.path.isfile(os.path.join(bootstrap_bullet_bank.SOURCE_DOCS_DIR, f))
    ]

    if not files:
        cli_art.console.print(
            "Looks like there's nothing in the source_documents folder yet. "
            "Drop in your resume, LinkedIn export, certificates, "
            "recommendation letters, or notes — then come back and select "
            "this again when you're ready!"
        )
        return False

    proceed = questionary.confirm(
        f"Looks like you've got {len(files)} document(s) to process. Ready to get started?",
        default=True,
        style=cli_art.QUESTIONARY_STYLE,
    ).ask()
    if not proceed:
        return False

    cli_art.display_bootstrap_intro(len(files))
    script_path = os.path.join(bootstrap_bullet_bank.SCRIPT_DIR, "bootstrap_bullet_bank.py")
    result = subprocess.run([sys.executable, script_path])
    return result.returncode == 0
```

Add it to `_HANDLERS` (no `_CHAIN` entry needed — `bootstrap_bullet_bank.py` already guides the user through the entire pipeline internally):

```python
_HANDLERS = {
    "bootstrap": _handle_bootstrap,
    "scan": _handle_scan,
    "liveness": _handle_liveness,
    "evaluate_all": _handle_evaluate_all,
    "evaluate_one": _handle_evaluate_one,
    "tailor_all": _handle_tailor_all,
    "tailor_one": _handle_tailor_one,
    "coverletter_one": _handle_coverletter_one,
    "polish": _handle_polish,
    "view_applications": _handle_view_applications,
}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m unittest tests.test_menu_bootstrap -v`
Expected: all tests PASS.

- [ ] **Step 5: Run the full existing menu test suite to check for regressions**

Run: `python -m unittest tests.test_menu -v`
Expected: all tests PASS (the existing `_CHOICES`/`_HANDLERS` entries are unchanged, just added to).

- [ ] **Step 6: Commit**

```bash
git add scripts/menu.py tests/test_menu_bootstrap.py
git commit -m "Add 'New User? Start Here!' entry point to the interactive menu"
```

---

### Task 9: End-to-end fixture-based integration tests

**Files:**
- Create: `tests/test_bootstrap_end_to_end.py`

**Interfaces:**
- Consumes: everything from Tasks 2-6 (`bootstrap_extractors`, `bootstrap_timeline`, `bootstrap_bullet_bank`).
- Produces: no new production code — this task only adds tests. Two distinct checks, deliberately not duplicating Task 5's per-doc-type unit tests:
  1. A real (unmocked) local-extraction dry run over genuine fixture files, proving the file-kind-detection -> local-text-extraction -> classification -> dry-run-stubbed-extraction plumbing doesn't crash on real files.
  2. A mocked multi-document run combining a resume, a recommendation letter, and a certificate in one `run_ingestion()` call, proving they consolidate correctly together into one coherent `bullet-bank-clean.csv` (Task 5's tests only ever exercised one document type at a time).

- [ ] **Step 1: Write the failing tests**

```python
import json
import os
import shutil
import sys
import tempfile
import unittest
from unittest.mock import patch

SCRIPTS_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts")
sys.path.insert(0, SCRIPTS_DIR)

import bootstrap_bullet_bank  # noqa: E402
import bootstrap_extractors  # noqa: E402


class BootstrapEndToEndTestCase(unittest.TestCase):

    def setUp(self):
        self.tmp_dir = tempfile.mkdtemp()
        self.bootstrap_dir = os.path.join(self.tmp_dir, "bootstrap")
        bootstrap_bullet_bank.BOOTSTRAP_DIR = self.bootstrap_dir
        bootstrap_bullet_bank.SOURCE_DOCS_DIR = os.path.join(self.bootstrap_dir, "source_documents")
        bootstrap_bullet_bank.TIMELINE_PATH = os.path.join(self.bootstrap_dir, "timeline.json")
        bootstrap_bullet_bank.CHECKPOINT_PATH = os.path.join(self.bootstrap_dir, "checkpoint.json")
        bootstrap_bullet_bank.DRAFT_CSV_PATH = os.path.join(self.bootstrap_dir, "bullet-bank-draft.csv")
        bootstrap_bullet_bank.REVIEW_CSV_PATH = os.path.join(self.bootstrap_dir, "review-needed.csv")
        bootstrap_bullet_bank.CERTIFICATIONS_PATH = os.path.join(self.bootstrap_dir, "certifications.json")
        bootstrap_bullet_bank.BULLET_BANK_CLEAN_PATH = os.path.join(self.tmp_dir, "bullet-bank-clean.csv")
        os.makedirs(bootstrap_bullet_bank.SOURCE_DOCS_DIR, exist_ok=True)

    def tearDown(self):
        shutil.rmtree(self.tmp_dir, ignore_errors=True)


class TestDryRunSmokeTestOnRealFiles(BootstrapEndToEndTestCase):
    """Uses real fixture files and real local-extraction code (Task 2) --
    only the Gemini-calling functions are short-circuited, via dry_run,
    to prove the whole chain doesn't crash on genuine input."""

    def test_mixed_real_files_dry_run_completes_without_crashing(self):
        with open(os.path.join(bootstrap_bullet_bank.SOURCE_DOCS_DIR, "My_Resume.txt"), "w", encoding="utf-8") as f:
            f.write("Acme Corp, Marketing Manager, 2019-2022\n- Grew email list by 40%")
        with open(os.path.join(bootstrap_bullet_bank.SOURCE_DOCS_DIR, "achievement_notes.txt"), "w", encoding="utf-8") as f:
            f.write("I once led a cross-functional project that shipped early.")

        import docx
        doc = docx.Document()
        doc.add_paragraph("Some freeform career notes with no clear company.")
        doc.save(os.path.join(bootstrap_bullet_bank.SOURCE_DOCS_DIR, "notes.docx"))

        summary = bootstrap_bullet_bank.run_ingestion(dry_run=True)

        self.assertEqual(summary, {"extracted": 0, "attributed": 0, "flagged": 0, "certificates": 0})
        self.assertTrue(os.path.exists(bootstrap_bullet_bank.DRAFT_CSV_PATH))
        self.assertTrue(os.path.exists(bootstrap_bullet_bank.CERTIFICATIONS_PATH))
        self.assertTrue(os.path.exists(bootstrap_bullet_bank.TIMELINE_PATH))
        self.assertTrue(os.path.exists(bootstrap_bullet_bank.BULLET_BANK_CLEAN_PATH))


class TestMultiDocumentConsolidation(BootstrapEndToEndTestCase):
    """Combines a resume, a recommendation letter, and a certificate in one
    run_ingestion() call -- Task 5's tests only ever exercised one document
    type at a time; this proves they consolidate correctly together."""

    def _touch(self, filename: str) -> None:
        with open(os.path.join(bootstrap_bullet_bank.SOURCE_DOCS_DIR, filename), "w", encoding="utf-8") as f:
            f.write("placeholder")

    @patch("bootstrap_bullet_bank.bootstrap_timeline.match_to_timeline")
    @patch("bootstrap_bullet_bank.bootstrap_extractors.extract_certificate")
    @patch("bootstrap_bullet_bank.bootstrap_extractors.extract_achievements")
    @patch("bootstrap_bullet_bank.bootstrap_extractors.extract_resume_timeline_and_achievements")
    @patch("bootstrap_bullet_bank.bootstrap_extractors.classify_document_type")
    @patch("bootstrap_bullet_bank.bootstrap_extractors.extract_local_text", return_value="fixture text")
    @patch("bootstrap_bullet_bank.bootstrap_extractors.detect_file_kind", return_value="text")
    def test_resume_letter_and_certificate_combine_correctly(
        self, mock_detect, mock_extract_text, mock_classify,
        mock_extract_resume, mock_extract_achievements, mock_extract_cert, mock_match,
    ):
        self._touch("resume.txt")
        self._touch("recommendation_letter.txt")
        self._touch("cert.txt")

        def classify_side_effect(filename, text, dry_run=False):
            return {
                "resume.txt": "resume",
                "recommendation_letter.txt": "recommendation_letter",
                "cert.txt": "certificate",
            }[filename]

        mock_classify.side_effect = classify_side_effect
        mock_extract_resume.return_value = bootstrap_extractors.ResumeExtraction(
            experience=[
                bootstrap_extractors.WorkExperienceEntry(
                    company="Acme Corp", title="Manager", start_date="2019", end_date="2022",
                    achievements=["Grew email list by 40%"],
                )
            ],
            certifications=[],
        )
        mock_extract_achievements.return_value = [
            bootstrap_extractors.RawAchievement(
                raw_text="Delivered the migration ahead of schedule",
                company_hint="Acme Corp", date_hint=None, title_hint=None, confidence="medium",
            )
        ]
        mock_match.return_value = ("Acme Corp", "medium")
        mock_extract_cert.return_value = bootstrap_extractors.Certificate(
            name="PMP Certification", issuer="PMI", date="2020",
        )

        summary = bootstrap_bullet_bank.run_ingestion()

        self.assertEqual(summary["extracted"], 2)
        self.assertEqual(summary["certificates"], 1)

        with open(bootstrap_bullet_bank.BULLET_BANK_CLEAN_PATH, encoding="utf-8") as f:
            clean_content = f.read()
        self.assertIn("Grew email list by 40%", clean_content)
        self.assertIn("Delivered the migration ahead of schedule", clean_content)
        self.assertEqual(clean_content.count("Acme Corp"), 2)

        with open(bootstrap_bullet_bank.CERTIFICATIONS_PATH, encoding="utf-8") as f:
            certs = json.load(f)
        self.assertEqual(certs[0]["name"], "PMP Certification")


if __name__ == "__main__":
    unittest.main()
```

Save as `tests/test_bootstrap_end_to_end.py`.

- [ ] **Step 2: Run tests to verify they fail or pass for the right reasons**

Run: `python -m unittest tests.test_bootstrap_end_to_end -v`

Since every production function this test touches already exists from Tasks 2-6, these tests should actually PASS immediately if everything upstream was implemented correctly. If anything fails here, it's exposing a real integration bug between tasks (most likely a path-constant not being respected, or a mismatch in the checkpoint dict shape between `_process_one_file` and `run_ingestion`'s Pass B loop) — fix the root cause in the relevant earlier task's implementation rather than patching around it here.

- [ ] **Step 3: If needed, fix integration issues found**

Common issue to check first if `test_mixed_real_files_dry_run_completes_without_crashing` fails: confirm `classify_document_type` in dry-run mode still runs its filename-heuristic branch (it does — `dry_run` only short-circuits the LLM-fallback branch, per Task 3) so `"My_Resume.txt"` really does classify as `"resume"` even in dry-run.

- [ ] **Step 4: Run the full test suite to confirm no regressions**

Run: `python -m unittest discover -s tests -v`
Expected: every test in `tests/` PASSES, including all pre-existing tests untouched by this plan.

- [ ] **Step 5: Commit**

```bash
git add tests/test_bootstrap_end_to_end.py
git commit -m "Add end-to-end fixture-based integration tests for bootstrap ingestion"
```
