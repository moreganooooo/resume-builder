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
