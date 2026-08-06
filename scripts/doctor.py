"""
doctor.py — dependency/asset/config checks plus a real test-suite run,
with a plain-English summary and a one-line suggested fix per problem
found. Prior art: job_automater's system_checker.py + config_validator.py
(see IDEAS_ARCHIVE.md); this version is scoped to resume-builder's own
real dependencies instead.

Pure logic module -- no printing here. cli_art.render_doctor_report()
handles display; menu.py/cli.py call run_checks()/run_test_suite() and
pass the results to it.
"""

import importlib
import os
import shutil
import subprocess
import sys

import profile_paths

PROJECT_ROOT = profile_paths.PROJECT_ROOT
MIN_PYTHON = (3, 10)

# pip package name -> the name actually used in `import ...`, wherever
# they differ, so this can check every line in requirements.txt for real
# rather than spot-checking a handful.
REQUIRED_PACKAGES = {
    "pandas": "pandas", "numpy": "numpy", "pyyaml": "yaml", "pydantic": "pydantic",
    "requests": "requests", "python-dotenv": "dotenv", "google-genai": "google.genai",
    "click": "click", "rich": "rich", "linkedin-jobs-scraper": "linkedin_jobs_scraper",
    "selenium": "selenium",
    "beautifulsoup4": "bs4", "browser_cookie3": "browser_cookie3", "questionary": "questionary",
    "python-docx": "docx", "python-pptx": "pptx", "pdfminer.six": "pdfminer", "pypdf": "pypdf",
    "odfpy": "odf", "openpyxl": "openpyxl",
}

FONT_FILES = [
    "DMSans-ExtraBold-static.ttf", "DMSans-Italic-static.ttf", "DMSans-Regular-static.ttf",
    "dm-serif-display-latin-ext.woff2", "dm-serif-display-latin.woff2",
]

PLAYWRIGHT_CACHE_DIR = (
    os.path.join(os.path.expanduser("~"), "Library", "Caches", "ms-playwright")
    if sys.platform == "darwin"
    else os.path.join(os.path.expanduser("~"), ".cache", "ms-playwright")
)


def _check(name: str, passed: bool, detail: str, fix: str = "") -> dict:
    return {"name": name, "passed": passed, "detail": detail, "fix": fix if not passed else ""}


def check_python_version() -> dict:
    ok = sys.version_info[:2] >= MIN_PYTHON
    return _check(
        "Python version", ok,
        f"{sys.version.split()[0]} (need >= {'.'.join(map(str, MIN_PYTHON))})",
        "Install Python 3.10+ and rebuild .venv/ (see CLAUDE.md Setup).",
    )


def check_venv() -> dict:
    venv_path = os.path.join(PROJECT_ROOT, ".venv")
    exists = os.path.isdir(venv_path)
    has_python = os.path.isfile(os.path.join(venv_path, "bin", "python"))
    ok = exists and has_python
    detail = f".venv/ {'found' if exists else 'missing'}, ready to use"
    return _check(
        ".venv/ exists and is ready", ok, detail,
        "Rebuild .venv/: /usr/local/bin/python3.13 -m venv .venv && source .venv/bin/activate && "
        "pip install -r requirements.txt.",
    )


def check_python_packages() -> dict:
    missing = []
    for pip_name, import_name in REQUIRED_PACKAGES.items():
        try:
            importlib.import_module(import_name)
        except ImportError:
            missing.append(pip_name)
    ok = not missing
    return _check(
        "Python packages (requirements.txt)", ok,
        "all installed" if ok else f"missing: {', '.join(missing)}",
        f"pip install {' '.join(missing)}" if missing else "",
    )


def check_node() -> dict:
    path = shutil.which("node")
    return _check(
        "Node.js", path is not None, path or "not found on PATH",
        "Install Node.js (https://nodejs.org) -- needed for PDF rendering via Playwright.",
    )


def check_playwright_npm_package() -> dict:
    ok = os.path.isdir(os.path.join(PROJECT_ROOT, "node_modules", "playwright"))
    return _check(
        "Playwright npm package", ok,
        "installed" if ok else "node_modules/playwright not found",
        "npm install (package.json already lists playwright as a dependency).",
    )


def check_playwright_chromium() -> dict:
    ok = False
    if os.path.isdir(PLAYWRIGHT_CACHE_DIR):
        ok = any(name.startswith("chromium-") for name in os.listdir(PLAYWRIGHT_CACHE_DIR))
    return _check(
        "Playwright Chromium browser", ok,
        "found" if ok else f"no chromium-* install found under {PLAYWRIGHT_CACHE_DIR}",
        "npx playwright install chromium",
    )


def check_go() -> dict:
    # Optional -- only needed for `resume dashboard` (dashboard/, a
    # vendored Go module); never a hard failure, so this always reports
    # passed=True.
    path = shutil.which("go")
    return _check(
        "Go toolchain (optional -- only for `resume dashboard`)", True,
        f"found: {path}" if path else "not found -- fine unless you use `resume dashboard`",
        "Install Go (https://go.dev, or `brew install go`) to use `resume dashboard`.",
    )


def _env_values() -> dict:
    from dotenv import dotenv_values
    path = profile_paths.env_path()
    return dotenv_values(path) if os.path.exists(path) else {}


def check_gemini_api_key() -> dict:
    values = _env_values()
    in_file = bool(values.get("GEMINI_API_KEY"))
    has_key = in_file or bool(os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY"))
    detail = f"set in {profile_paths.env_path()}" if in_file else ("set in shell environment" if has_key else "not found")
    return _check(
        "GEMINI_API_KEY", has_key, detail,
        f"Add GEMINI_API_KEY=... to {profile_paths.env_path()} (or re-run the bootstrap wizard's secrets step).",
    )


def check_jobright_cookie() -> dict:
    # Optional -- only needed for `resume scan --source jobright`, never a
    # hard failure, so this always reports passed=True.
    values = _env_values()
    has_cookie = bool(values.get("JOBRIGHT_COOKIE_STRING") or os.environ.get("JOBRIGHT_COOKIE_STRING"))
    return _check(
        "JOBRIGHT_COOKIE_STRING (optional -- only for scan --source jobright)", True,
        "set" if has_cookie else "not set -- fine unless you use JobRight scanning",
    )


def check_fonts() -> dict:
    fonts_dir = os.path.join(PROJECT_ROOT, "resume-engine", "fonts")
    missing = [f for f in FONT_FILES if not os.path.exists(os.path.join(fonts_dir, f))]
    ok = not missing
    return _check(
        "DM Sans static font files", ok,
        "all present" if ok else f"missing: {', '.join(missing)}",
        f"Restore the missing font file(s) into {fonts_dir}/ (see git history).",
    )


def check_signature_image() -> dict:
    # Informational only -- profiles/<name>/signature.{png,jpg,jpeg} is
    # fully optional; render_coverletter.py already degrades gracefully
    # (no <img> tag at all) when it's missing, so this always reports
    # passed=True.
    path = profile_paths.signature_path()
    return _check(
        f"Signature image ({profile_paths.active_profile()}, optional)", True,
        f"found: {path}" if path else "not set -- cover letters render with no signature image, which is fine",
    )


def check_kb_allowlist() -> dict:
    """Checks KB_ALLOWLIST files for three failure modes doctor previously
    couldn't see (B13): (1) missing entirely -- the original check; (2)
    present but zero-byte or with a future mtime -- the signature of a
    truncated/corrupted write, since KB_ALLOWLIST is an explicit filename
    list (not a glob), a corrupt file here is never auto-excluded from
    the builder's context the way an unlisted file would be; (3) any
    `.sync-conflict-*` file sitting in the KB directory -- Syncthing's own
    conflict-copy naming, never ingested by the builder (again because
    KB_ALLOWLIST is explicit), but a sign of an unresolved multi-computer
    sync collision worth a human's attention."""
    import orchestrator
    import time

    kb_dir = profile_paths.kb_dir()
    missing = [f for f in orchestrator.KB_ALLOWLIST if not os.path.exists(os.path.join(kb_dir, f))]

    now = time.time()
    corrupted = []
    for f in orchestrator.KB_ALLOWLIST:
        path = os.path.join(kb_dir, f)
        if not os.path.exists(path):
            continue
        st = os.stat(path)
        if st.st_size == 0 or st.st_mtime > now + 60:
            corrupted.append(f)

    conflicts = sorted(f for f in os.listdir(kb_dir) if ".sync-conflict-" in f) if os.path.isdir(kb_dir) else []

    problems = []
    if missing:
        problems.append(f"missing: {', '.join(missing)}")
    if corrupted:
        problems.append(f"zero-byte or bad-mtime (likely corrupted): {', '.join(corrupted)}")
    if conflicts:
        problems.append(f"Syncthing conflict copies present: {', '.join(conflicts)}")

    ok = not problems
    return _check(
        f"Knowledge-base allowlist files ({profile_paths.active_profile()})", ok,
        "all present and healthy" if ok else "; ".join(problems),
        "" if ok else (
            f"Missing or corrupted files silently shrink or poison the builder's context -- restore "
            f"them into {kb_dir}/, or re-run bootstrap/Update My Knowledge if this is a fresh or "
            "partial profile. For Syncthing conflict copies: they are never auto-ingested, but "
            "resolve them by hand (compare the two versions, keep the correct one, delete the rest) "
            "before they're forgotten and pile up."
        ),
    )


CHECKS = [
    check_python_version,
    check_venv,
    check_python_packages,
    check_node,
    check_playwright_npm_package,
    check_playwright_chromium,
    check_go,
    check_gemini_api_key,
    check_jobright_cookie,
    check_fonts,
    check_signature_image,
    check_kb_allowlist,
]


def run_checks() -> list:
    return [check() for check in CHECKS]


def run_test_suite() -> tuple:
    """Runs the real test suite for real. Returns (passed: bool, summary:
    str) -- summary is unittest's own final report line(s) (e.g. "Ran 808
    tests in 19.7s" + "OK"/"FAILED (failures=2)"), not the full verbose
    output."""
    result = subprocess.run(
        [sys.executable, "-m", "unittest", "discover", "-s", "tests"],
        cwd=PROJECT_ROOT, capture_output=True, text=True,
    )
    passed = result.returncode == 0
    lines = [line for line in result.stderr.strip().splitlines() if line.strip()]
    summary = "\n".join(lines[-3:]) if lines else ("OK" if passed else "FAILED")
    return passed, summary
