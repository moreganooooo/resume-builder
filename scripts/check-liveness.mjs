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

// B45: same RESUME_BUILDER_ICONS contract theme.py resolves on the Python
// side (see its icon_set_name() docstring) -- read directly here since
// there's no shared theming layer across the JS/Python boundary. Reuses
// theme.py's own success/warning/error glyphs (unicode_active/expired/
// uncertain) for consistency rather than inventing new ones; likely_active
// has no Python-side equivalent to match, so it gets its own plain pick.
const PLAIN_ICONS = process.env.RESUME_BUILDER_ICONS === 'unicode';
const RESULT_ICONS = PLAIN_ICONS
  ? { active: '✓', likely_active: '~', expired: '✗', uncertain: '⚠' }
  : { active: '✓', likely_active: '◐', expired: '✗', uncertain: '⚠' };
const UNKNOWN_ICON = PLAIN_ICONS ? '?' : '❓';

export function buildProgressEvent(index, total, candidate, result, code, reason) {
  return {
    type: 'progress',
    index: index + 1,
    total,
    result,
    code,
    reason: reason || null,
    source_file: candidate.source_file,
  };
}

async function runJsonMode(candidatesPath) {
  const text = await readFile(candidatesPath, 'utf-8');
  const candidates = JSON.parse(text);

  const browser = await chromium.launch({ headless: true, timeout: 30_000 });
  const page = await browser.newPage();

  const results = [];
  try {
    // Sequential — project rule: never Playwright in parallel
    for (let i = 0; i < candidates.length; i++) {
      const candidate = candidates[i];
      const { result, code, reason } = await checkUrlLiveness(page, candidate.url);

      console.error(JSON.stringify(buildProgressEvent(i, candidates.length, candidate, result, code, reason)));

      results.push({ ...candidate, result, code, reason });
    }
  } finally {
    // Both effects matter: closing the browser even on a throw (it
    // otherwise leaks a headless Chromium process), and printing
    // whatever's in `results` so far even on a throw (previously, a
    // failure on candidate 89 of 90 discarded all 88 already-checked
    // results instead of returning them) (B21).
    try {
      await browser.close();
    } catch {
      // Ignore browser close error (e.g. already disconnected) so results are always printed
    }
    console.log(JSON.stringify(results));
  }
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

  const browser = await chromium.launch({ headless: true, timeout: 30_000 });
  const page = await browser.newPage();

  let active = 0, expired = 0, uncertain = 0;

  // Sequential — project rule: never Playwright in parallel
  for (const url of urls) {
    const { result, reason } = await checkUrlLiveness(page, url);
    const icon = RESULT_ICONS[result] || UNKNOWN_ICON;
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

// Only auto-run when this file is the direct entry point (`node
// check-liveness.mjs ...`) -- ESM's equivalent of CommonJS's
// `require.main === module`. Without this, importing buildProgressEvent
// for a unit test (check-liveness.test.mjs) also runs main() as a side
// effect of the import, which sees no argv and exits the whole test
// process via the "no args" usage-and-exit(1) path above.
if (import.meta.url === `file://${process.argv[1]}`) {
  main().catch(err => {
    console.error('Fatal:', err.message);
    process.exit(1);
  });
}
