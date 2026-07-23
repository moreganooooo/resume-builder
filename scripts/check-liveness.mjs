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
  for (let i = 0; i < candidates.length; i++) {
    const candidate = candidates[i];
    const { result, code, reason } = await checkUrlLiveness(page, candidate.url);

    // Progress indicator: [i/total] + status + reason if applicable
    const icon = { active: '✅', likely_active: '🟡', expired: '❌', uncertain: '⚠️' }[result] || '❓';
    const progress = `[${i + 1}/${candidates.length}]`;
    console.error(`${progress} ${icon} ${result.padEnd(14)} ${candidate.source_file}`);
    if (reason && result !== 'active' && result !== 'likely_active') {
      console.error(`         → ${reason}`);
    }

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
