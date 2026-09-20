"""
jd_image_ingest.py -- converts a screenshot/PDF job posting into a normal
JSON JD file the existing pipeline (jd_manager.get_pending_jds() / `resume
run`) can process unchanged.

WHY THIS EXISTS

Some employers (Tesla, notably -- see
docs/morgan_research/tesla-buffalo-implementation-spec.md) run no public ATS
and actively block scraping at the edge (Akamai "Access Denied" even on
robots.txt). A manual screenshot of the posting page is the only practical,
ToS-respecting way to get that JD into this pipeline at all.

pdfminer/pypdf extract NOTHING useful from a real screencapture-generated
PDF -- confirmed empirically against a real Tesla careers page screenshot:
2 characters extracted from a 2.7MB file, because a browser
"screencapture"-style export has no text layer, only a rendered image. OCR
would be one way around that, but this project has no other reason to
depend on a local OCR stack (pytesseract needs a system Tesseract binary;
easyocr needs multi-hundred-MB model downloads) when Gemini's own
multimodal input already reads an image or image-only PDF directly, with
no new dependency at all -- see gemini_client.GeminiClient.generate()'s
`inline_file` parameter.

WHY THIS IS A SEPARATE, EXPLICIT STEP

Deliberately NOT wired into jd_manager.get_pending_jds() or
scan.run_scan()'s batch listing path. Those are called from count-only /
display contexts (picker.py, the CLI banner) with zero expectation of a
network call, let alone a billable one -- folding image-to-JD conversion
in there would spend Gemini quota just from a user looking at their
pending-role count (the same class of accidental-spend bug
gemini_client._get_auth_headers()'s test-network guard and
db._is_unisolated_test_write() both exist to prevent, applied here at
design time instead of after the fact). Run this first; the JSON files it
writes are then indistinguishable from any other JD to `resume run`.

Usage:
    python scripts/jd_image_ingest.py <file-or-directory> [<file-or-directory> ...]
    python scripts/jd_image_ingest.py --profile dominick ~/Downloads/jobdescriptions
"""

from __future__ import annotations

import argparse
import datetime
import json
import mimetypes
import os
import sys

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
if SCRIPT_DIR not in sys.path:
    sys.path.insert(0, SCRIPT_DIR)

import cli_art  # noqa: E402
import jd_manager  # noqa: E402
import profile_paths  # noqa: E402
import schemas  # noqa: E402
from atomic_write import atomic_write  # noqa: E402

SUPPORTED_EXTENSIONS = {".pdf", ".png", ".jpg", ".jpeg"}

_MIME_OVERRIDES = {
    ".pdf": "application/pdf",
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
}


def _mime_type(path: str) -> str:
    ext = os.path.splitext(path)[1].lower()
    return (
        _MIME_OVERRIDES.get(ext)
        or mimetypes.guess_type(path)[0]
        or "application/octet-stream"
    )


def _unwrap_image_pdf(file_bytes: bytes) -> tuple[bytes, str] | None:
    """A browser screencapture PDF is one letter-size page wrapping a single
    ~5000px-tall screenshot, and Gemini rasterizes PDF pages at low
    resolution -- so the model read blurred digits. On a real Tesla posting
    that turned "2+ years" into "3+" and shifted all six pay figures, on
    3.5-flash-lite AND 3.6-flash alike; the same model given the embedded
    image as a PNG transcribed every figure exactly (Gemini tiles a large
    image at native resolution). Returns that image as PNG, or None for
    anything else (multi-page, a real text layer, several images), which is
    then sent unchanged."""
    import io

    try:
        from pypdf import PdfReader

        pages = PdfReader(io.BytesIO(file_bytes)).pages
        if (
            len(pages) != 1
            or len((pages[0].extract_text() or "").strip())
            > 50  # pylint: disable=no-member
        ):
            return None
        images = list(pages[0].images)  # pylint: disable=no-member
        if len(images) != 1:
            return None
        buf = io.BytesIO()
        if images[0].image is None:
            return None
        images[0].image.convert("RGB").save(buf, format="PNG")
        return buf.getvalue(), "image/png"
    except Exception:
        return None


def _dedupe_stems(paths: list) -> list:
    """A browser "screencapture"-style extension often writes the SAME
    posting twice, once as .pdf and once as .png, sharing a base filename
    -- exactly the pattern in a real Downloads folder this was built
    against. Ingesting both would burn a second API call and produce two
    JD files for one job. PDF wins when both exist: Gemini's PDF handling
    can also see the document's own title metadata, a signal a bare PNG
    doesn't carry, even though the rendered page content is identical."""
    by_stem: dict[str, str] = {}
    order: list[str] = []
    for path in paths:
        stem = os.path.splitext(path)[0]
        ext = os.path.splitext(path)[1].lower()
        if stem not in by_stem:
            by_stem[stem] = path
            order.append(stem)
        elif ext == ".pdf":
            by_stem[stem] = path
    return [by_stem[stem] for stem in order]


def discover_files(sources: list) -> list:
    """Expands a mix of file and directory arguments into the sorted,
    deduped list of image/PDF files to ingest. Directories are scanned
    non-recursively -- a flat "drop screenshots here" folder is the
    expected shape, not a nested archive."""
    found = []
    for src in sources:
        if os.path.isdir(src):
            for name in sorted(os.listdir(src)):
                path = os.path.join(src, name)
                if (
                    os.path.isfile(path)
                    and os.path.splitext(name)[1].lower() in SUPPORTED_EXTENSIONS
                ):
                    found.append(path)
        elif os.path.isfile(src):
            if os.path.splitext(src)[1].lower() in SUPPORTED_EXTENSIONS:
                found.append(src)
            else:
                cli_art.cli_error(
                    f"Skipping {src} -- not a supported type "
                    f"({', '.join(sorted(SUPPORTED_EXTENSIONS))})."
                )
        else:
            cli_art.cli_error(f"Skipping {src} -- not a file or directory.")
    return _dedupe_stems(found)


def extract_jd_from_image(path: str, engine=None) -> dict:
    """Runs the real Gemini vision call and returns a job dict in the same
    shape scan_indeed.py / the Node board-scanner providers produce, with
    source_platform="manual-screenshot" so it's identifiable later. Never
    raises on a bad/unreadable image -- returns a dict carrying
    "_ingest_error" instead, since one bad screenshot in a batch of
    several must not abort the rest."""
    import orchestrator

    engine = engine or orchestrator.ResumeEngine()
    try:
        with open(path, "rb") as f:
            file_bytes = f.read()
    except OSError as e:
        return {"_ingest_error": f"{type(e).__name__}: {e}", "_ingest_source": path}

    mime_type = _mime_type(path)
    if mime_type == "application/pdf":
        unwrapped = _unwrap_image_pdf(file_bytes)
        if unwrapped:
            file_bytes, mime_type = unwrapped
    prompt = engine.load_prompt("extract_jd_from_image.md")

    try:
        raw_text, _ = orchestrator.GeminiClient.generate(
            model=orchestrator.BUILDER_MODEL,
            system_instruction=prompt,
            contents="Transcribe the attached job posting per the instructions above.",
            response_schema=schemas.ScreenshotJdExtractionSchema,
            inline_file=(file_bytes, mime_type),
            temperature=0.0,
        )
    except Exception as e:
        return {"_ingest_error": f"{type(e).__name__}: {e}", "_ingest_source": path}

    parsed = orchestrator.GeminiClient.parse_json(raw_text or "") or {}
    if not parsed.get("job_title") and not parsed.get("description"):
        return {
            "_ingest_error": "Gemini returned no usable job_title/description -- "
            "the image may not be a readable job posting.",
            "_ingest_source": path,
        }

    job = {
        "job_title": parsed.get("job_title") or "",
        "company_name": parsed.get("company_name") or "",
        "source_platform": "manual-screenshot",
        "source_job_id": None,
        "source_url": parsed.get("source_url") or "",
        "location": parsed.get("location") or "",
        "is_remote": parsed.get("is_remote"),
        "posted_at": "",
        "description": parsed.get("description") or "",
    }
    if parsed.get("is_partial"):
        job["_ingest_partial"] = True
    return job


def ingest_one(path: str, profile: str | None = None, engine=None) -> str | None:
    """Converts one image/PDF into a JSON JD file in the given (or
    active) profile's jds/ directory, deletes the source file, and
    returns the new JD's path -- or None on failure, leaving the source
    file in place so a bad conversion never silently loses the original."""
    job = extract_jd_from_image(path, engine=engine)
    if "_ingest_error" in job:
        cli_art.cli_error(f"{os.path.basename(path)}: {job['_ingest_error']}")
        return None

    jds_dir = profile_paths.jds_dir(profile)
    os.makedirs(jds_dir, exist_ok=True)
    today = datetime.date.today().isoformat()
    filename = (
        f"{today}_{jd_manager.sanitize_for_filename(job['company_name'])}_"
        f"{jd_manager.sanitize_for_filename(job['job_title'])}.json"
    )
    dest = os.path.join(jds_dir, filename)
    counter = 1
    while os.path.exists(dest):
        dest = os.path.join(jds_dir, filename.replace(".json", f"_{counter}.json"))
        counter += 1

    with atomic_write(dest, encoding="utf-8") as f:
        json.dump(job, f, indent=2, ensure_ascii=False)

    partial_note = (
        " (partial -- image was cut off)" if job.get("_ingest_partial") else ""
    )
    cli_art.cli_info(
        f"{job['job_title'] or 'Untitled Role'} @ "
        f"{job['company_name'] or 'Unknown Company'}{partial_note} -> {dest}"
    )
    os.remove(path)
    # _dedupe_stems() skipped any same-stem sibling (job.png beside
    # job.pdf) because it is the same job; left on disk, the next run
    # would ingest it as a second JD and spend a second API call.
    stem = os.path.splitext(path)[0]
    for ext in SUPPORTED_EXTENSIONS:
        for sibling in (stem + ext, stem + ext.upper()):
            if sibling != path and os.path.isfile(sibling):
                os.remove(sibling)
    return dest


def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument(
        "sources", nargs="+", help="Image/PDF file(s) or a directory of them"
    )
    parser.add_argument("--profile", help="Target profile (default: active profile)")
    args = parser.parse_args()

    files = discover_files(args.sources)
    if not files:
        cli_art.cli_error("No .pdf/.png/.jpg/.jpeg files found in the given sources.")
        return 1

    import orchestrator

    engine = orchestrator.ResumeEngine()
    ok = 0
    for path in files:
        if ingest_one(path, profile=args.profile, engine=engine):
            ok += 1

    cli_art.cli_info(
        f"Ingested {ok}/{len(files)} file(s) into jds/{args.profile or profile_paths.active_profile()}/."
    )
    return 0 if ok == len(files) else 1


if __name__ == "__main__":
    raise SystemExit(main())
