# Liveness Checker Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** `resume liveness` checks every pending JD's `source_url` via a ported, proven Playwright classifier and moves confirmed-`expired` postings to `jds/expired/`, so `resume run`/`tailor` never wastes real Gemini spend on dead postings.

**Architecture:** Career-ops's existing classification logic (`liveness-core.mjs`, `liveness-browser.mjs`) is ported verbatim; `check-liveness.mjs` gains a `--json-file` mode for structured batch input/output. A new Python module (`liveness.py`) gathers pending JDs with URLs, shells out to the Node script (same `subprocess.run` pattern as `generate-pdf.mjs`), and moves expired ones.

**Tech Stack:** Node/Playwright (already a dependency), Python 3.10+, `unittest.mock` for the Python-side tests.

## Global Constraints

- No MongoDB, no new persistence layer.
- `liveness-core.mjs`/`liveness-browser.mjs` are ported **verbatim** — no changes to the classification logic itself.
- Only a confident `expired` result moves a JD; `uncertain`/`likely_active` stay in place, flagged in the printed summary.
- Standalone command (`resume liveness`) — never auto-wired into `scan`/`run`/`tailor`.
- JDs without a `source_url` are silently skipped (counted separately), not flagged as anything.
- Temp input file lives at `output/liveness_input_tmp.json` (already-gitignored `output/` dir) and is always removed (`try`/`finally`), success or failure.
- No new JS test framework — `check-liveness.mjs`'s new mode is live-verified, matching how `generate-pdf.mjs` is already verified in this project.
- Spec: `docs/superpowers/specs/2026-07-05-liveness-checker-design.md`.

---

### Task 1: Port the Node/Playwright checker

**Files:**
- Create: `scripts/liveness-core.mjs`
- Create: `scripts/liveness-browser.mjs`
- Create: `scripts/check-liveness.mjs`

**Interfaces:**
- Consumes: nothing from other tasks (self-contained Node scripts, `playwright` only — already a `package.json` dependency).
- Produces: `node scripts/check-liveness.mjs --json-file <path>` — reads a JSON array of `{job_key, source_file, url}` from `<path>`, writes a JSON array of `{job_key, source_file, url, result, code, reason}` to **stdout** (human-readable progress goes to **stderr**), exits 0 on success regardless of how many postings are expired (that's a normal outcome, not a script failure) or 1 on a fatal error (bad input, browser launch failure). Task 2's `liveness.py` calls this exact command shape and parses this exact stdout format. The original bare-URL/`--file` text-mode usage is preserved unchanged (still prints to stdout, still exits 1 if any URL comes back `expired`/`uncertain` — that behavior is untouched).

- [ ] **Step 1: Port the classifier verbatim**

Create `scripts/liveness-core.mjs`:

```javascript
const HARD_EXPIRED_PATTERNS = [
  /job (is )?no longer available/i,
  /job.*no longer open/i,
  /position has been filled/i,
  /this job has expired/i,
  /job posting has expired/i,
  /no longer accepting applications/i,
  /this (position|role|job) (is )?no longer/i,
  /this job (listing )?is closed/i,
  /job (listing )?not found/i,
  /the page you are looking for doesn.t exist/i,
  /applications?\s+(?:(?:have|are|is)\s+)?closed/i,
  /closed on \d{1,2}\s+(?:jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)/i,
  /closed on (?:jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)\w*\s+\d{1,2}/i,
  /diese stelle (ist )?(nicht mehr|bereits) besetzt/i,
  /offre (expirée|n'est plus disponible)/i,
];

const LISTING_PAGE_PATTERNS = [
  /\d+\s+jobs?\s+found/i,
  /search for jobs page is loaded/i,
];

const EXPIRED_URL_PATTERNS = [
  /[?&]error=true/i,
];

const APPLY_PATTERNS = [
  /\bapply\b/i,
  /\bsolicitar\b/i,
  /\bbewerben\b/i,
  /\bpostuler\b/i,
  /apply (now|here|today)/i,
  /submit application/i,
  /easy apply/i,
  /start application/i,
  /ich bewerbe mich/i,
  /send (your )?resume/i,
  /apply for (this )?job/i,
];

const JD_SECTION_PATTERNS = [
  /job description/i,
  /responsibilities/i,
  /requirements/i,
  /qualifications/i,
  /what you.ll do/i,
  /about the role/i,
  /what we.re looking for/i,
  /benefits/i,
  /compensation/i,
  /salary/i,
  /equal opportunity employer/i,
];

const MIN_CONTENT_CHARS = 300;

function firstMatch(patterns, text = '') {
  return patterns.find((pattern) => pattern.test(text));
}

function hasApplyControl(controls = []) {
  return controls.some((control) => APPLY_PATTERNS.some((pattern) => pattern.test(control)));
}

/**
 * Classify the liveness of a job posting based on HTTP status, URL, body text, and visible controls.
 *
 * Results:
 * - active: Strong evidence the job is open (apply button found)
 * - likely_active: JD sections found, but no explicit apply button
 * - uncertain: Content is present but no strong signals either way
 * - expired: Strong evidence the job is closed (404, error redirect, hard patterns)
 */
export function classifyLiveness({ status = 0, finalUrl = '', bodyText = '', applyControls = [] } = {}) {
  if (status === 404 || status === 410) {
    return { result: 'expired', code: 'http_gone', reason: `HTTP ${status}` };
  }

  const expiredUrl = firstMatch(EXPIRED_URL_PATTERNS, finalUrl);
  if (expiredUrl) {
    return { result: 'expired', code: 'expired_url', reason: `redirect to ${finalUrl}` };
  }

  const expiredBody = firstMatch(HARD_EXPIRED_PATTERNS, bodyText);
  if (expiredBody) {
    return { result: 'expired', code: 'expired_body', reason: `pattern matched: ${expiredBody.source}` };
  }

  if (hasApplyControl(applyControls)) {
    return { result: 'active', code: 'apply_control_visible', reason: 'visible apply control detected' };
  }

  const listingPage = firstMatch(LISTING_PAGE_PATTERNS, bodyText);
  if (listingPage) {
    return { result: 'expired', code: 'listing_page', reason: `pattern matched: ${listingPage.source}` };
  }

  const hasJdSection = firstMatch(JD_SECTION_PATTERNS, bodyText);
  if (hasJdSection) {
    return { result: 'likely_active', code: 'jd_sections_found', reason: `JD keywords found: ${hasJdSection.source}` };
  }

  if (bodyText.trim().length < MIN_CONTENT_CHARS) {
    return { result: 'uncertain', code: 'insufficient_content', reason: 'insufficient content — likely nav/footer only' };
  }

  return { result: 'uncertain', code: 'no_apply_control', reason: 'content present but no strong liveness signals found' };
}
```

- [ ] **Step 2: Port the Playwright wrapper verbatim**

Create `scripts/liveness-browser.mjs`:

```javascript
/**
 * liveness-browser.mjs — Playwright browser layer for liveness checking
 *
 * Wraps liveness-core.mjs classification logic with actual page fetching.
 * Called by check-liveness.mjs. Never call directly.
 *
 * Project rule: never run Playwright in parallel — callers must sequence.
 */

import { classifyLiveness } from './liveness-core.mjs';

const NAV_TIMEOUT_MS = 15_000;
const RENDER_WAIT_MS = 1_200;

/**
 * Check whether a single URL points to an active job posting.
 *
 * @param {import('playwright').Page} page - A shared Playwright Page instance
 * @param {string} url - The job posting URL to check
 * @returns {Promise<{ result: 'active'|'expired'|'uncertain', reason: string }>}
 */
export async function checkUrlLiveness(page, url) {
  let status = 0;
  let finalUrl = url;

  try {
    const response = await page.goto(url, {
      waitUntil: 'domcontentloaded',
      timeout: NAV_TIMEOUT_MS,
    });

    status = response?.status() ?? 0;
    finalUrl = page.url();

    // Allow dynamic content a moment to render
    await page.waitForTimeout(RENDER_WAIT_MS);

    const bodyText = await page.evaluate(() => document.body?.innerText ?? '');

    // Collect visible button / link text for apply-control detection
    const applyControls = await page.evaluate(() =>
      Array.from(
        document.querySelectorAll('button, a[href], input[type="submit"]')
      ).map((el) => el.innerText?.trim() ?? el.value ?? '')
    );

    return classifyLiveness({ status, finalUrl, bodyText, applyControls });
  } catch (err) {
    // Navigation timeout or hard crash — treat as uncertain
    return {
      result: 'uncertain',
      reason: `navigation error: ${err.message.split('\n')[0]}`,
    };
  }
}
```

- [ ] **Step 3: Adapt check-liveness.mjs with the new --json-file mode**

Create `scripts/check-liveness.mjs`:

```javascript
#!/usr/bin/env node

/**
 * check-liveness.mjs — Playwright job link liveness checker
 *
 * Tests whether job posting URLs are still active or have expired.
 * Ported from career-ops (zero Claude/Gemini API tokens -- pure Playwright).
 *
 * Usage:
 *   node check-liveness.mjs <url1> [url2] ...
 *   node check-liveness.mjs --file urls.txt
 *   node check-liveness.mjs --json-file candidates.json
 *     candidates.json: [{"job_key": "...", "source_file": "...", "url": "..."}, ...]
 *     Writes a JSON array of {job_key, source_file, url, result, code, reason}
 *     to stdout; human-readable progress goes to stderr instead, keeping
 *     stdout parseable for the Python caller (scripts/liveness.py).
 *
 * Exit code (--json-file mode): 0 on success (regardless of how many
 * postings are expired -- that's a normal, expected outcome, not a script
 * failure), 1 on a fatal error (bad input, browser launch failure, etc.)
 */

import { chromium } from 'playwright';
import { readFile } from 'fs/promises';
import { checkUrlLiveness } from './liveness-browser.mjs';

async function runJsonMode(candidatesPath) {
  const text = await readFile(candidatesPath, 'utf-8');
  const candidates = JSON.parse(text);

  const browser = await chromium.launch({ headless: true });
  const page = await browser.newPage();

  const results = [];
  // Sequential — project rule: never Playwright in parallel
  for (const candidate of candidates) {
    const { result, code, reason } = await checkUrlLiveness(page, candidate.url);
    console.error(`  ${result.padEnd(14)} ${candidate.source_file}`);
    results.push({ ...candidate, result, code, reason });
  }

  await browser.close();
  console.log(JSON.stringify(results));
}

async function runTextMode(args) {
  let urls;
  if (args[0] === '--file') {
    const text = await readFile(args[1], 'utf-8');
    urls = text.split('\n').map(l => l.trim()).filter(l => l && !l.startsWith('#'));
  } else {
    urls = args;
  }

  console.log(`Checking ${urls.length} URL(s)...\n`);

  const browser = await chromium.launch({ headless: true });
  const page = await browser.newPage();

  let active = 0, expired = 0, uncertain = 0;

  // Sequential — project rule: never Playwright in parallel
  for (const url of urls) {
    const { result, reason } = await checkUrlLiveness(page, url);
    const icon = { active: '✅', expired: '❌', uncertain: '⚠️' }[result] || '❓';
    console.log(`${icon} ${result.padEnd(10)} ${url}`);
    if (result !== 'active') console.log(`           ${reason}`);
    if (result === 'active') active++;
    else if (result === 'expired') expired++;
    else uncertain++;
  }

  await browser.close();

  console.log(`\nResults: ${active} active  ${expired} expired  ${uncertain} uncertain`);
  if (expired > 0 || uncertain > 0) process.exit(1);
}

async function main() {
  const args = process.argv.slice(2);

  if (args.length === 0) {
    console.error('Usage: node check-liveness.mjs <url1> [url2] ...');
    console.error('       node check-liveness.mjs --file urls.txt');
    console.error('       node check-liveness.mjs --json-file candidates.json');
    process.exit(1);
  }

  if (args[0] === '--json-file') {
    await runJsonMode(args[1]);
  } else {
    await runTextMode(args);
  }
}

main().catch(err => {
  console.error('Fatal:', err.message);
  process.exit(1);
});
```

- [ ] **Step 4: Live verification (real network + real Playwright)**

```bash
cd /Users/morganescott/resume-builder
cat > /tmp/liveness_test_candidates.json << 'EOF'
[
  {"job_key": "test1", "source_file": "test1.json", "url": "https://example.com"},
  {"job_key": "test2", "source_file": "test2.json", "url": "https://example.com/definitely-not-a-real-page-404"}
]
EOF
node scripts/check-liveness.mjs --json-file /tmp/liveness_test_candidates.json
rm /tmp/liveness_test_candidates.json
```

Expected: stdout contains exactly one line -- a JSON array with 2 objects, each with `job_key`, `source_file`, `url`, `result`, `code`, `reason`. `example.com` should classify as `uncertain` (minimal real content -- not enough to trigger `likely_active` or `active`) and the 404 URL should classify as `expired` (`code: "http_gone"`). Progress lines print to stderr, not mixed into stdout.

- [ ] **Step 5: Commit**

```bash
git add scripts/liveness-core.mjs scripts/liveness-browser.mjs scripts/check-liveness.mjs
git commit -m "$(cat <<'EOF'
Port career-ops's liveness checker (Playwright, no MongoDB, no LLM)

liveness-core.mjs/liveness-browser.mjs ported verbatim. check-liveness.mjs
gains a --json-file batch mode for scripts/liveness.py to call; the
original bare-URL/--file text usage is untouched. Live-verified: a real
domain classifies uncertain, a 404 URL classifies expired. Part of the
liveness checker (see
docs/superpowers/specs/2026-07-05-liveness-checker-design.md).

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
EOF
)"
```

---

### Task 2: `liveness.py` orchestration + `jd_manager.EXPIRED_DIR`

**Files:**
- Modify: `scripts/jd_manager.py:20` (add `EXPIRED_DIR` constant, next to `COMPLETED_DIR`)
- Create: `scripts/liveness.py`
- Test: `tests/test_liveness.py`

**Interfaces:**
- Consumes: `jd_manager.get_pending_jds() -> list[str]` (existing), `jd_manager.compute_job_key(path) -> str` (existing), `jd_manager.EXPIRED_DIR` (new, this task), `node scripts/check-liveness.mjs --json-file <path>` (Task 1).
- Produces: `liveness.run_liveness_check() -> dict` with keys `active`, `likely_active`, `expired`, `uncertain`, `skipped`, `moved` (and `error: True` on a failure path). Task 3's CLI command calls this exact function.

- [ ] **Step 1: Add the constant**

In `scripts/jd_manager.py`, find:

```python
JDS_DIR = os.path.join(PROJECT_ROOT, "jds")
COMPLETED_DIR = os.path.join(JDS_DIR, "completed")
CHECKPOINTS_DIR = os.path.join(PROJECT_ROOT, "output", "checkpoints")
```

Change to:

```python
JDS_DIR = os.path.join(PROJECT_ROOT, "jds")
COMPLETED_DIR = os.path.join(JDS_DIR, "completed")
EXPIRED_DIR = os.path.join(JDS_DIR, "expired")
CHECKPOINTS_DIR = os.path.join(PROJECT_ROOT, "output", "checkpoints")
```

- [ ] **Step 2: Write the failing tests**

Create `tests/test_liveness.py`:

```python
import json
import os
import sys
import unittest
from unittest.mock import MagicMock, patch

SCRIPTS_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts")
sys.path.insert(0, SCRIPTS_DIR)

import jd_manager  # noqa: E402
import liveness  # noqa: E402


def _proc(returncode=0, stdout="", stderr=""):
    proc = MagicMock()
    proc.returncode = returncode
    proc.stdout = stdout
    proc.stderr = stderr
    return proc


class TestLiveness(unittest.TestCase):

    def setUp(self):
        self.tmp_dir = os.path.join(os.path.dirname(__file__), "_tmp_liveness")
        os.makedirs(self.tmp_dir, exist_ok=True)
        self.expired_dir = os.path.join(self.tmp_dir, "expired")

        self._real_expired_dir = jd_manager.EXPIRED_DIR
        jd_manager.EXPIRED_DIR = self.expired_dir

        self.with_url_path = os.path.join(self.tmp_dir, "with_url.json")
        self.no_url_path = os.path.join(self.tmp_dir, "no_url.json")
        with open(self.with_url_path, "w", encoding="utf-8") as f:
            json.dump({"source_url": "https://example.com/job/1", "job_title": "Test"}, f)
        with open(self.no_url_path, "w", encoding="utf-8") as f:
            json.dump({"job_title": "No URL Here"}, f)

    def tearDown(self):
        jd_manager.EXPIRED_DIR = self._real_expired_dir
        for root, dirs, files in os.walk(self.tmp_dir, topdown=False):
            for name in files:
                os.remove(os.path.join(root, name))
            for name in dirs:
                os.rmdir(os.path.join(root, name))
        if os.path.exists(self.tmp_dir):
            os.rmdir(self.tmp_dir)

    def test_gather_candidates_skips_jds_without_source_url(self):
        candidates = liveness._gather_candidates([self.with_url_path, self.no_url_path])
        self.assertEqual(len(candidates), 1)
        self.assertEqual(candidates[0]["url"], "https://example.com/job/1")
        self.assertEqual(candidates[0]["source_file"], self.with_url_path)

    @patch("liveness.jd_manager.get_pending_jds")
    @patch("liveness.subprocess.run")
    def test_expired_jd_gets_moved_to_expired_dir(self, mock_run, mock_get_pending):
        mock_get_pending.return_value = [self.with_url_path]
        mock_run.return_value = _proc(returncode=0, stdout=json.dumps([
            {"job_key": "abc", "source_file": self.with_url_path, "url": "https://example.com/job/1",
             "result": "expired", "code": "http_gone", "reason": "HTTP 404"},
        ]))

        summary = liveness.run_liveness_check()

        self.assertEqual(summary["expired"], 1)
        self.assertEqual(summary["moved"], 1)
        self.assertFalse(os.path.exists(self.with_url_path))
        self.assertTrue(os.path.exists(os.path.join(self.expired_dir, "with_url.json")))

    @patch("liveness.jd_manager.get_pending_jds")
    @patch("liveness.subprocess.run")
    def test_active_jd_stays_in_place(self, mock_run, mock_get_pending):
        mock_get_pending.return_value = [self.with_url_path]
        mock_run.return_value = _proc(returncode=0, stdout=json.dumps([
            {"job_key": "abc", "source_file": self.with_url_path, "url": "https://example.com/job/1",
             "result": "active", "code": "apply_control_visible", "reason": "visible apply control detected"},
        ]))

        summary = liveness.run_liveness_check()

        self.assertEqual(summary["active"], 1)
        self.assertEqual(summary["moved"], 0)
        self.assertTrue(os.path.exists(self.with_url_path))

    @patch("liveness.jd_manager.get_pending_jds")
    @patch("liveness.subprocess.run")
    def test_uncertain_jd_stays_in_place_and_is_flagged(self, mock_run, mock_get_pending):
        mock_get_pending.return_value = [self.with_url_path]
        mock_run.return_value = _proc(returncode=0, stdout=json.dumps([
            {"job_key": "abc", "source_file": self.with_url_path, "url": "https://example.com/job/1",
             "result": "uncertain", "code": "no_apply_control", "reason": "content present but no strong liveness signals found"},
        ]))

        summary = liveness.run_liveness_check()

        self.assertEqual(summary["uncertain"], 1)
        self.assertEqual(summary["moved"], 0)
        self.assertTrue(os.path.exists(self.with_url_path))

    @patch("liveness.jd_manager.get_pending_jds")
    def test_jds_without_source_url_are_counted_as_skipped(self, mock_get_pending):
        mock_get_pending.return_value = [self.no_url_path]

        summary = liveness.run_liveness_check()

        self.assertEqual(summary["skipped"], 1)
        self.assertEqual(summary["moved"], 0)

    @patch("liveness.jd_manager.get_pending_jds")
    @patch("liveness.subprocess.run")
    def test_subprocess_failure_moves_nothing(self, mock_run, mock_get_pending):
        mock_get_pending.return_value = [self.with_url_path]
        mock_run.return_value = _proc(returncode=1, stderr="Fatal: browser launch failed")

        summary = liveness.run_liveness_check()

        self.assertTrue(summary.get("error"))
        self.assertEqual(summary["moved"], 0)
        self.assertTrue(os.path.exists(self.with_url_path))

    @patch("liveness.jd_manager.get_pending_jds")
    @patch("liveness.subprocess.run")
    def test_malformed_json_output_moves_nothing(self, mock_run, mock_get_pending):
        mock_get_pending.return_value = [self.with_url_path]
        mock_run.return_value = _proc(returncode=0, stdout="not valid json{{{")

        summary = liveness.run_liveness_check()

        self.assertTrue(summary.get("error"))
        self.assertEqual(summary["moved"], 0)
        self.assertTrue(os.path.exists(self.with_url_path))

    @patch("liveness.jd_manager.get_pending_jds")
    @patch("liveness.subprocess.run")
    def test_temp_input_file_cleaned_up_after_success(self, mock_run, mock_get_pending):
        mock_get_pending.return_value = [self.with_url_path]
        mock_run.return_value = _proc(returncode=0, stdout=json.dumps([
            {"job_key": "abc", "source_file": self.with_url_path, "url": "https://example.com/job/1",
             "result": "active", "code": "apply_control_visible", "reason": "ok"},
        ]))

        liveness.run_liveness_check()

        self.assertFalse(os.path.exists(liveness.LIVENESS_INPUT_PATH))

    @patch("liveness.jd_manager.get_pending_jds")
    @patch("liveness.subprocess.run")
    def test_temp_input_file_cleaned_up_after_subprocess_failure(self, mock_run, mock_get_pending):
        mock_get_pending.return_value = [self.with_url_path]
        mock_run.return_value = _proc(returncode=1, stderr="boom")

        liveness.run_liveness_check()

        self.assertFalse(os.path.exists(liveness.LIVENESS_INPUT_PATH))
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `cd /Users/morganescott/resume-builder && source .venv/bin/activate && python -m unittest tests.test_liveness -v`
Expected: `ModuleNotFoundError: No module named 'liveness'` (file doesn't exist yet).

- [ ] **Step 4: Write the implementation**

Create `scripts/liveness.py`:

```python
"""
liveness.py — the `liveness` command: checks every pending JD's source_url
via a Node/Playwright subprocess, moving confirmed-expired postings out of
the active queue into jds/expired/.

No MongoDB, no LLM calls -- pure Playwright + deterministic classification,
ported from career-ops's already-proven liveness-core.mjs/liveness-browser.mjs.
See docs/superpowers/specs/2026-07-05-liveness-checker-design.md.
"""

import json
import os
import shutil
import subprocess

import jd_manager

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
LIVENESS_INPUT_PATH = os.path.join(jd_manager.PROJECT_ROOT, "output", "liveness_input_tmp.json")


def _gather_candidates(pending_paths: list) -> list:
    """Returns [{"job_key": ..., "source_file": ..., "url": ...}, ...] for
    every path in pending_paths whose JD data has a real source_url; the
    rest are silently excluded (not flagged as anything)."""
    candidates = []
    for path in pending_paths:
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
        except (json.JSONDecodeError, UnicodeDecodeError, OSError):
            continue
        url = data.get("source_url") if isinstance(data, dict) else None
        if not url:
            continue
        candidates.append({
            "job_key": jd_manager.compute_job_key(path),
            "source_file": path,
            "url": url,
        })
    return candidates


def run_liveness_check() -> dict:
    """
    Checks every pending JD's source_url, moves confirmed-expired ones to
    jds/expired/. Returns a summary dict with keys: active, likely_active,
    expired, uncertain, skipped, moved (plus error=True on a failure path).
    """
    pending_paths = jd_manager.get_pending_jds()
    candidates = _gather_candidates(pending_paths)
    skipped = len(pending_paths) - len(candidates)

    if not candidates:
        print(f"Nothing to check -- {len(pending_paths)} pending JD(s), none with a source_url.")
        return {"active": 0, "likely_active": 0, "expired": 0, "uncertain": 0, "skipped": skipped, "moved": 0}

    os.makedirs(os.path.dirname(LIVENESS_INPUT_PATH), exist_ok=True)
    with open(LIVENESS_INPUT_PATH, "w", encoding="utf-8") as f:
        json.dump(candidates, f)

    try:
        script = os.path.join(SCRIPT_DIR, "check-liveness.mjs")
        proc = subprocess.run(
            ["node", script, "--json-file", LIVENESS_INPUT_PATH],
            capture_output=True, text=True,
        )
        if proc.returncode != 0:
            print(f"  ⚠️  Liveness check failed:\n{proc.stderr}")
            return {"active": 0, "likely_active": 0, "expired": 0, "uncertain": 0, "skipped": skipped, "moved": 0, "error": True}

        try:
            results = json.loads(proc.stdout)
        except json.JSONDecodeError:
            print(f"  ⚠️  Liveness check produced unparseable output:\n{proc.stdout[:500]}")
            return {"active": 0, "likely_active": 0, "expired": 0, "uncertain": 0, "skipped": skipped, "moved": 0, "error": True}
    finally:
        if os.path.exists(LIVENESS_INPUT_PATH):
            os.remove(LIVENESS_INPUT_PATH)

    counts = {}
    moved = 0
    os.makedirs(jd_manager.EXPIRED_DIR, exist_ok=True)

    for r in results:
        outcome = r.get("result", "uncertain")
        counts[outcome] = counts.get(outcome, 0) + 1
        icon = {"active": "✅", "likely_active": "🟡", "expired": "❌", "uncertain": "⚠️"}.get(outcome, "❓")
        print(f"  {icon} {outcome:<14} {r.get('source_file')}")
        if outcome not in ("active", "likely_active"):
            print(f"       {r.get('reason', '')}")

        if outcome == "expired":
            source_file = r.get("source_file")
            if source_file and os.path.exists(source_file):
                dest = os.path.join(jd_manager.EXPIRED_DIR, os.path.basename(source_file))
                shutil.move(source_file, dest)
                moved += 1

    print(
        f"\nLiveness summary: {counts.get('active', 0)} active, "
        f"{counts.get('likely_active', 0)} likely active, "
        f"{counts.get('expired', 0)} expired (moved to jds/expired/), "
        f"{counts.get('uncertain', 0)} uncertain (left in place), "
        f"{skipped} skipped (no source_url)."
    )

    return {
        "active": counts.get("active", 0),
        "likely_active": counts.get("likely_active", 0),
        "expired": counts.get("expired", 0),
        "uncertain": counts.get("uncertain", 0),
        "skipped": skipped,
        "moved": moved,
    }
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd /Users/morganescott/resume-builder && source .venv/bin/activate && python -m unittest tests.test_liveness -v`
Expected: all 9 tests pass.

- [ ] **Step 6: Run the full suite to confirm no regressions**

Run: `source .venv/bin/activate && python -m unittest discover -s tests`
Expected: `OK`, test count increased by 9 from the prior total (181 → 190).

- [ ] **Step 7: Commit**

```bash
git add scripts/jd_manager.py scripts/liveness.py tests/test_liveness.py
git commit -m "$(cat <<'EOF'
Add liveness.py orchestration + jd_manager.EXPIRED_DIR

Gathers pending JDs with a source_url, shells out to check-liveness.mjs,
moves confirmed-expired ones to jds/expired/. Part of the liveness
checker (see docs/superpowers/specs/2026-07-05-liveness-checker-design.md).

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
EOF
)"
```

---

### Task 3: CLI wiring (`resume liveness`)

**Files:**
- Modify: `scripts/cli.py` (add `liveness` command)
- Modify: `scripts/resume-cli.sh` (add `liveness` case + help text)

**Interfaces:**
- Consumes: `liveness.run_liveness_check() -> dict` (Task 2), `cli_art.display_banner(subtitle: str) -> None` (existing).
- Produces: the `resume liveness` command, usable both via `python scripts/cli.py liveness` and the `resume liveness` shell shortcut.

- [ ] **Step 1: Add the CLI command**

In `scripts/cli.py`, find:

```python
import cli_art
import orchestrator
import scan as scan_module
```

Change to:

```python
import cli_art
import orchestrator
import scan as scan_module
import liveness as liveness_module
```

Then find:

```python
@cli.command(name="scan")
@click.option("--source", "sources", multiple=True, default=None,
              help="Source to scan (jobright, linkedin). Repeatable. Default: all configured sources.")
def scan_cmd(sources):
    """Scan configured sources and write new postings into jds/."""
    cli_art.display_banner("Scanning for new postings")
    scan_module.run_scan(list(sources) if sources else None)
```

Insert immediately after it:

```python


@cli.command(name="liveness")
def liveness_cmd():
    """Check every pending JD's source_url, moving expired ones to jds/expired/."""
    cli_art.display_banner("Checking posting liveness")
    liveness_module.run_liveness_check()
```

- [ ] **Step 2: Verify the command registers**

Run: `source .venv/bin/activate && python scripts/cli.py liveness --help`
Expected:
```
Usage: cli.py liveness [OPTIONS]

  Check every pending JD's source_url, moving expired ones to jds/expired/.

Options:
  --help  Show this message and exit.
```

- [ ] **Step 3: Wire the shell shortcut**

In `scripts/resume-cli.sh`, find:

```bash
    scan)
      ( cd "$_RESUME_BUILDER_DIR" && source .venv/bin/activate && python scripts/cli.py scan "$@" )
      ;;
```

Insert immediately after it:

```bash
    liveness)
      ( cd "$_RESUME_BUILDER_DIR" && source .venv/bin/activate && python scripts/cli.py liveness )
      ;;
```

In the same file, find:

```bash
      echo "  resume scan --source jobright   pull from just one source (jobright, linkedin)"
```

Insert immediately after it:

```bash
      echo "  resume liveness         check every pending JD's posting URL, move expired ones out"
```

- [ ] **Step 4: Verify the shortcut works**

Run: `source scripts/resume-cli.sh && resume liveness --help`
Expected: same help text as Step 2 (Click's own `--help` handling; the shortcut just forwards to `python scripts/cli.py liveness`).

- [ ] **Step 5: Run the full test suite**

Run: `source .venv/bin/activate && python -m unittest discover -s tests`
Expected: `OK`, same test count as after Task 2 (this task adds no new automated tests — pure wiring, already verified via `--help` and Task 1/2's live checks).

- [ ] **Step 6: Live verification against real pending JDs**

```bash
source .venv/bin/activate
python scripts/cli.py liveness
```

Expected: checks every real pending JD in `jds/` that has a `source_url` (the 209+ from earlier scans), prints per-JD results and a final summary line, and moves any confirmed-`expired` ones into `jds/expired/`. Spot-check a handful of results by eye -- this will take a while (each URL is a real headless-browser navigation), so it's fine to let it run in the background.

- [ ] **Step 7: Commit**

```bash
git add scripts/cli.py scripts/resume-cli.sh
git commit -m "$(cat <<'EOF'
Wire resume liveness into the CLI and shell shortcut

Completes the liveness checker (see
docs/superpowers/specs/2026-07-05-liveness-checker-design.md). Live-
verified against real pending JDs.

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
EOF
)"
```
