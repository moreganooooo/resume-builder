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
    "pandas": "pandas",
    "numpy": "numpy",
    "pyyaml": "yaml",
    "pydantic": "pydantic",
    "requests": "requests",
    "python-dotenv": "dotenv",
    "google-genai": "google.genai",
    "click": "click",
    "rich": "rich",
    "linkedin-jobs-scraper": "linkedin_jobs_scraper",
    "selenium": "selenium",
    "beautifulsoup4": "bs4",
    "questionary": "questionary",
    "python-docx": "docx",
    "python-pptx": "pptx",
    "pdfminer.six": "pdfminer",
    "pypdf": "pypdf",
    "odfpy": "odf",
    "openpyxl": "openpyxl",
}

FONT_FILES = [
    "DMSans-ExtraBold-static.ttf",
    "DMSans-Italic-static.ttf",
    "DMSans-Regular-static.ttf",
    "dm-serif-display-latin-ext.woff2",
    "dm-serif-display-latin.woff2",
]

PLAYWRIGHT_CACHE_DIR = (
    os.path.join(os.path.expanduser("~"), "Library", "Caches", "ms-playwright")
    if sys.platform == "darwin"
    else os.path.join(os.path.expanduser("~"), ".cache", "ms-playwright")
)


def _check(name: str, passed: bool, detail: str, fix: str = "") -> dict:
    return {
        "name": name,
        "passed": passed,
        "detail": detail,
        "fix": fix if not passed else "",
    }


def check_python_version() -> dict:
    ok = sys.version_info[:2] >= MIN_PYTHON
    return _check(
        "Python version",
        ok,
        f"{sys.version.split()[0]} (need >= {'.'.join(map(str, MIN_PYTHON))})",
        "Install Python 3.10+ and rebuild .venv/ (see CLAUDE.md Setup).",
    )


def check_venv() -> dict:
    venv_path = os.path.join(PROJECT_ROOT, ".venv")
    exists = os.path.isdir(venv_path)
    in_venv = getattr(sys, "prefix", "") != getattr(
        sys, "base_prefix", getattr(sys, "prefix", "")
    )
    has_python = os.path.isfile(os.path.join(venv_path, "bin", "python"))
    ok = exists and (in_venv or has_python)
    detail = (
        f".venv/ {'found' if exists else 'missing'}, "
        f"{'ready to use' if ok else 'not usable'}"
    )
    return _check(
        ".venv/ exists and is ready",
        ok,
        detail,
        f"Rebuild .venv/: {sys.executable} -m venv .venv && source .venv/bin/activate && "
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
        "Python packages (requirements.txt)",
        ok,
        "all installed" if ok else f"missing: {', '.join(missing)}",
        f"pip install {' '.join(missing)}" if missing else "",
    )


def check_node() -> dict:
    path = shutil.which("node")
    return _check(
        "Node.js",
        path is not None,
        path or "not found on PATH",
        "Install Node.js (https://nodejs.org) -- needed for PDF rendering via Playwright.",
    )


def check_npm() -> dict:
    # npm/npx ship with Node, but a broken/partial Node install can still
    # put `node` on PATH without them -- both Playwright checks below
    # prescribe `npm install`/`npx playwright install`, so this machine is
    # exactly the failure case those fixes need to detect first (B32).
    path = shutil.which("npm")
    has_npx = shutil.which("npx") is not None
    ok = path is not None and has_npx
    detail = (
        path
        if ok
        else f"npm {'found' if path else 'not found'}, npx {'found' if has_npx else 'not found'}"
    )
    return _check(
        "npm/npx",
        ok,
        detail,
        "Reinstall Node.js (https://nodejs.org) -- npm and npx ship with it. Playwright setup "
        "(`npm install` / `npx playwright install chromium`) needs both.",
    )


def check_playwright_npm_package() -> dict:
    ok = os.path.isdir(os.path.join(PROJECT_ROOT, "node_modules", "playwright"))
    has_npm = shutil.which("npm") is not None
    fix = (
        "npm install (package.json already lists playwright as a dependency)."
        if has_npm
        else "npm isn't available -- fix the npm/npx check above first, then npm install."
    )
    return _check(
        "Playwright npm package",
        ok,
        "installed" if ok else "node_modules/playwright not found",
        fix,
    )


def check_playwright_chromium() -> dict:
    ok = False
    if os.path.isdir(PLAYWRIGHT_CACHE_DIR):
        ok = any(
            name.startswith("chromium-") for name in os.listdir(PLAYWRIGHT_CACHE_DIR)
        )
    has_npx = shutil.which("npx") is not None
    fix = (
        "npx playwright install chromium"
        if has_npx
        else "npx isn't available -- fix the npm/npx check above first, then npx playwright install chromium."
    )
    return _check(
        "Playwright Chromium browser",
        ok,
        "found" if ok else f"no chromium-* install found under {PLAYWRIGHT_CACHE_DIR}",
        fix,
    )


def check_go() -> dict:
    # Optional -- only needed for `resume dashboard` (dashboard/, a
    # vendored Go module); never a hard failure, so this always reports
    # passed=True.
    path = shutil.which("go")
    return _check(
        "Go toolchain (optional -- only for `resume dashboard`)",
        True,
        (
            f"found: {path}"
            if path
            else "not found -- fine unless you use `resume dashboard`"
        ),
        "Install Go (https://go.dev, or `brew install go`) to use `resume dashboard`.",
    )


def _env_values() -> dict:
    from dotenv import dotenv_values

    path = profile_paths.env_path()
    return dotenv_values(path) if os.path.exists(path) else {}


def check_gemini_api_key() -> dict:
    values = _env_values()
    in_file = bool(values.get("GEMINI_API_KEY"))
    has_key = in_file or bool(
        os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
    )
    detail = (
        f"set in {profile_paths.env_path()}"
        if in_file
        else ("set in shell environment" if has_key else "not found")
    )
    return _check(
        "GEMINI_API_KEY",
        has_key,
        detail,
        f"Add GEMINI_API_KEY=... to {profile_paths.env_path()} (or re-run the bootstrap wizard's secrets step).",
    )


def check_jobright_cookie() -> dict:
    # Optional -- only needed for `resume scan --source jobright`, never a
    # hard failure, so this always reports passed=True.
    values = _env_values()
    has_cookie = bool(
        values.get("JOBRIGHT_COOKIE_STRING") or os.environ.get("JOBRIGHT_COOKIE_STRING")
    )
    return _check(
        "JOBRIGHT_COOKIE_STRING (optional -- only for scan --source jobright)",
        True,
        "set" if has_cookie else "not set -- fine unless you use JobRight scanning",
    )


def check_fonts() -> dict:
    fonts_dir = os.path.join(PROJECT_ROOT, "resume-engine", "fonts")
    missing = [f for f in FONT_FILES if not os.path.exists(os.path.join(fonts_dir, f))]
    ok = not missing
    return _check(
        "DM Sans static font files",
        ok,
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
        f"Signature image ({profile_paths.active_profile()}, optional)",
        True,
        (
            f"found: {path}"
            if path
            else "not set -- cover letters render with no signature image, which is fine"
        ),
    )


def check_dashboard_theme_sync() -> dict:
    """dashboard/internal/theme/resumebuilder.go's accent colors are
    generated from theme.py by sync_dashboard_theme.py (B23/P2F9) --
    before that, they were hand-copied with comments merely claiming they
    matched, and nothing ever caught it when they drifted. This is that
    catch: regenerates the expected source in memory and diffs it against
    what's actually on disk, without writing anything itself."""
    import sync_dashboard_theme

    path = sync_dashboard_theme.DASHBOARD_THEME_PATH
    if not os.path.exists(path):
        return _check(
            "Dashboard theme sync (Go)",
            False,
            f"{path} not found",
            "Run `python scripts/sync_dashboard_theme.py` to generate it.",
        )
    expected = sync_dashboard_theme.build_go_theme_source()
    with open(path, "r", encoding="utf-8") as f:
        actual = f.read()
    ok = actual == expected
    return _check(
        "Dashboard theme sync (Go)",
        ok,
        (
            "in sync with theme.py"
            if ok
            else "out of sync with theme.py's color constants"
        ),
        "Run `python scripts/sync_dashboard_theme.py` to regenerate it.",
    )


def check_dashboard_color_lint() -> dict:
    """dashboard/tools/lint_colors.go catches hardcoded/off-token colors in
    the Go TUI, but it was previously a manual-only `go run
    ./tools/lint_colors.go` with nothing gating it -- unlike
    check_dashboard_theme_sync() above, which has exactly this kind of
    automated check for a sibling drift risk. Optional/never a hard
    failure when Go isn't installed, matching check_go()'s own reasoning:
    this binary is only needed for `resume dashboard`."""
    if not shutil.which("go"):
        return _check(
            "Dashboard color lint (Go)",
            True,
            "skipped -- Go not installed (only needed for `resume dashboard`)",
        )
    result = subprocess.run(
        ["go", "run", "./tools/lint_colors.go"],
        cwd=os.path.join(PROJECT_ROOT, "dashboard"),
        capture_output=True,
        text=True,
    )
    ok = result.returncode == 0
    detail = (
        "no hard-coded colors found"
        if ok
        else "hard-coded/non-token colors found -- see below"
    )
    fix = result.stdout.strip() or result.stderr.strip()
    return _check("Dashboard color lint (Go)", ok, detail, fix)


def check_icon_set() -> dict:
    # Always passes -- purely informational (B33). Doctor previously had
    # nothing to say about RESUME_BUILDER_ICONS at all; this at least
    # states what will actually render and why, instead of a stranger
    # discovering tofu boxes with zero diagnostic help anywhere in the tool.
    import theme
    import ui_config

    env_override = os.environ.get("RESUME_BUILDER_ICONS")
    if env_override == "unicode":
        detail = "unicode (RESUME_BUILDER_ICONS override)"
    else:
        persisted = ui_config.get_icon_set()
        if persisted:
            detail = f"{persisted} (chosen at first launch, profile {profile_paths.active_profile()})"
        else:
            detail = (
                f"not yet chosen -- will be asked on next interactive launch (`resume` menu); "
                f"resolving to {theme._ICON_SET_NAME} for this run"
            )
    return _check("Icon set (RESUME_BUILDER_ICONS)", True, detail)


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
    import time

    import orchestrator

    kb_dir = profile_paths.kb_dir()
    missing = [
        f
        for f in orchestrator.KB_ALLOWLIST
        if not os.path.exists(os.path.join(kb_dir, f))
    ]

    now = time.time()
    corrupted = []
    for f in orchestrator.KB_ALLOWLIST:
        path = os.path.join(kb_dir, f)
        if not os.path.exists(path):
            continue
        st = os.stat(path)
        if st.st_size == 0 or st.st_mtime > now + 60:
            corrupted.append(f)

    conflicts = (
        sorted(f for f in os.listdir(kb_dir) if ".sync-conflict-" in f)
        if os.path.isdir(kb_dir)
        else []
    )

    # Every file missing and nothing else wrong is "never bootstrapped," not
    # "partially broken" -- collapse it to one actionable line instead of a
    # 19-filename wall doctor used to print, with the real instruction
    # buried at the end of a warning about shrunk context (B32).
    if (
        len(missing) == len(orchestrator.KB_ALLOWLIST)
        and not corrupted
        and not conflicts
    ):
        name = profile_paths.active_profile()
        return _check(
            f"Knowledge-base allowlist files ({name})",
            False,
            f"0 of {len(orchestrator.KB_ALLOWLIST)} present -- profile not bootstrapped yet",
            f"Profile `{name}` isn't set up yet -- run `resume` -> New User? Start Here! "
            "(or `resume bootstrap` directly).",
        )

    problems = []
    if missing:
        problems.append(f"missing: {', '.join(missing)}")
    if corrupted:
        problems.append(
            f"zero-byte or bad-mtime (likely corrupted): {', '.join(corrupted)}"
        )
    if conflicts:
        problems.append(f"Syncthing conflict copies present: {', '.join(conflicts)}")

    ok = not problems
    return _check(
        f"Knowledge-base allowlist files ({profile_paths.active_profile()})",
        ok,
        "all present and healthy" if ok else "; ".join(problems),
        (
            ""
            if ok
            else (
                f"Missing or corrupted files silently shrink or poison the builder's context -- restore "
                f"them into {kb_dir}/, or re-run bootstrap/Update My Knowledge if this is a fresh or "
                "partial profile. For Syncthing conflict copies: they are never auto-ingested, but "
                "resolve them by hand (compare the two versions, keep the correct one, delete the rest) "
                "before they're forgotten and pile up."
            )
        ),
    )


def check_data_db() -> dict:
    """Confirms the active profile's data.db is reachable and writable --
    jd_manager._sync_jd_to_db() swallows failures here as a warning-level
    log line (best-effort, so a broken data.db never blocks the JSON-file
    pipeline that's the real source of truth), which means it's easy for
    the SQLite mirror to silently stop updating with nothing else
    surfacing it. This check is the counterpart: a place that actually
    fails loudly if the DB itself can't be opened or queried (F5)."""
    import db

    name = profile_paths.active_profile()
    try:
        conn = db.get_db(name)
        try:
            conn.execute("SELECT 1;").fetchone()
        finally:
            conn.close()
    except Exception as e:
        return _check(
            f"SQLite data.db ({name})",
            False,
            f"could not open or query: {e}",
            f"Check disk space and file permissions on {db.get_db_path(name)}. If the file is "
            "corrupted, the JSON files in jds/ remain the real source of truth -- data.db can be "
            "rebuilt from them via `python scripts/migrate_filesystem_to_db.py`.",
        )
    return _check(f"SQLite data.db ({name})", True, "reachable and writable")


CHECKS = [
    check_python_version,
    check_venv,
    check_python_packages,
    check_node,
    check_npm,
    check_playwright_npm_package,
    check_playwright_chromium,
    check_go,
    check_gemini_api_key,
    check_jobright_cookie,
    check_fonts,
    check_signature_image,
    check_icon_set,
    check_dashboard_theme_sync,
    check_dashboard_color_lint,
    check_kb_allowlist,
    check_data_db,
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
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True,
    )
    passed = result.returncode == 0
    lines = [line for line in result.stderr.strip().splitlines() if line.strip()]
    if passed:
        summary = "\n".join(lines[-3:]) if lines else "OK"
    else:
        # Include failure tracebacks if tests fail so developer sees exact root cause
        summary = result.stderr.strip() if result.stderr else "FAILED"
    return passed, summary


if __name__ == "__main__":
    import cli_art

    results = run_checks()
    test_passed, test_summary = run_test_suite()
    cli_art.render_doctor_report(results, (test_passed, test_summary))
