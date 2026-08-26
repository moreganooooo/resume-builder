#!/usr/bin/env node

/**
 * run_provider.mjs — thin CLI shim so scripts/scan_boards.py can shell out
 * to a vendored career-ops provider module and get plain JSON back.
 *
 * Usage: node run_provider.mjs <provider_id> <entry_json>
 *   <provider_id>  matches the provider's `id` / filename in providers/
 *   <entry_json>   a PortalEntry object (see providers/_types.js), e.g.
 *                  {"name": "RemoteOK", "search_term": "marketing"}
 *
 * On success, prints the provider's Job[] array as JSON to stdout and exits
 * 0. On failure (unknown provider, network error, malformed provider
 * module), prints a human-readable message to stderr (unchanged, still the
 * most informative text available) AND writes a small JSON error envelope
 * to stdout -- `{"error":{"kind":"auth"|"quota"|"network"|"config","message":"…"}}`
 * -- then exits non-zero. See B27, docs/review/phase-9-backlog.md:
 * scan_boards.py's _run_node_provider() reads `kind` to log a specific
 * reason instead of guessing from the last line of stderr, which used to be
 * the only signal available and collapsed every failure mode (expired auth,
 * exhausted quota, a dead host, a bad tracked_companies.yml entry) into the
 * same "quiet Tuesday" shape as no results.
 */

import { pathToFileURL } from 'url';
import path from 'path';
import fs from 'fs';
import { fileURLToPath } from 'url';
import { makeHttpCtx } from './providers/_http.mjs';

const PROVIDERS_DIR = path.resolve(path.dirname(fileURLToPath(import.meta.url)), 'providers');

/**
 * Best-effort classification of a thrown error into one of four buckets
 * scan_boards.py can act on. Deliberately conservative -- "config" (this
 * script/provider/entry is broken, not the network) is the fallback for
 * anything not clearly identifiable, rather than guessing "network" and
 * potentially masking a real bug as a transient blip.
 * @param {any} err
 * @returns {"auth"|"quota"|"network"|"config"}
 */
export function classifyError(err) {
  const status = err && err.status;
  if (status === 401 || status === 403) return 'auth';
  if (status === 429) return 'quota';
  if (typeof status === 'number' && status >= 500) return 'network';

  const message = String((err && err.message) || err || '').toLowerCase();
  if (/api[_ ]?key|unauthorized|not set|not authenticated/.test(message)) return 'auth';
  if (/quota|rate limit|too many requests/.test(message)) return 'quota';
  if (
    (err && (err.name === 'AbortError' || ['ENOTFOUND', 'ECONNREFUSED', 'ECONNRESET'].includes(err.code)))
    || /fetch failed|timed out|network/.test(message)
  ) return 'network';
  return 'config';
}

/**
 * Executes a single provider's fetch logic.
 * @param {string} providerId
 * @param {object} entry
 * @returns {Promise<Array<object>>}
 */
export async function executeSingle(providerId, entry = {}) {
  const modPath = path.join(PROVIDERS_DIR, `${providerId}.mjs`);
  let mod;
  try {
    mod = await import(pathToFileURL(modPath).href);
  } catch (err) {
    throw new Error(`failed to load provider -- ${err.message}`);
  }

  const provider = mod.default;
  if (!provider || typeof provider.fetch !== 'function') {
    throw new Error('module has no default export with a fetch() function');
  }

  const jobs = await provider.fetch(entry, makeHttpCtx(providerId));
  if (!Array.isArray(jobs)) {
    throw new Error('fetch() did not return an array');
  }
  return jobs;
}

/**
 * Executes a batch of providers concurrently using Promise.allSettled.
 * @param {Array<{provider_id?: string, provider?: string, entry?: object}>} items
 * @returns {Promise<Array<{provider_id: string, status: "fulfilled"|"rejected", jobs?: Array<object>, error?: {kind: string, message: string}}>>}
 */
export async function executeBatch(items) {
  if (!Array.isArray(items)) {
    throw new Error('batch input must be an array of provider entries');
  }

  const tasks = items.map(async (item) => {
    const providerId = item.provider_id || item.provider || item.id;
    if (!providerId) {
      return {
        provider_id: 'unknown',
        status: 'rejected',
        error: { kind: 'config', message: 'missing provider_id in batch entry' },
      };
    }
    const entry = item.entry || {};
    try {
      const jobs = await executeSingle(providerId, entry);
      return {
        provider_id: providerId,
        status: 'fulfilled',
        jobs,
      };
    } catch (err) {
      return {
        provider_id: providerId,
        status: 'rejected',
        error: { kind: classifyError(err), message: String((err && err.message) || err) },
      };
    }
  });

  const settled = await Promise.allSettled(tasks);
  return settled.map((res, i) => {
    if (res.status === 'fulfilled') {
      return res.value;
    }
    const providerId = items[i] && (items[i].provider_id || items[i].provider || items[i].id) || 'unknown';
    return {
      provider_id: providerId,
      status: 'rejected',
      error: { kind: classifyError(res.reason), message: String((res.reason && res.reason.message) || res.reason) },
    };
  });
}

function failWith(providerId, err) {
  console.error(`${providerId}: ${err.message || err}`);
  process.stdout.write(JSON.stringify({ error: { kind: classifyError(err), message: String((err && err.message) || err) } }));
  process.exit(1);
}

async function main() {
  const args = process.argv.slice(2);
  if (args.length === 0) {
    console.error('Usage: node run_provider.mjs <provider_id> <entry_json> OR node run_provider.mjs --batch <batch_json>');
    process.exit(1);
  }

  if (args[0] === '--batch' || args[0] === '-b' || args[0] === '--batch-file') {
    let raw = '';
    if (args[0] === '--batch-file' || (args[1] && args[1].startsWith('@'))) {
      const filePath = args[0] === '--batch-file' ? args[1] : args[1].slice(1);
      try {
        raw = fs.readFileSync(filePath, 'utf-8');
      } catch (err) {
        process.stdout.write(JSON.stringify([{ provider_id: 'batch', status: 'rejected', error: { kind: 'config', message: `failed to read batch file: ${err.message}` } }]));
        process.exit(1);
      }
    } else {
      raw = args[1] || '[]';
    }

    let items;
    try {
      items = JSON.parse(raw);
    } catch (err) {
      process.stdout.write(JSON.stringify([{ provider_id: 'batch', status: 'rejected', error: { kind: 'config', message: `batch input is not valid JSON: ${err.message}` } }]));
      process.exit(1);
    }

    try {
      const results = await executeBatch(items);
      process.stdout.write(JSON.stringify(results));
      process.exit(0);
    } catch (err) {
      process.stdout.write(JSON.stringify([{ provider_id: 'batch', status: 'rejected', error: { kind: classifyError(err), message: String(err.message || err) } }]));
      process.exit(1);
    }
  }

  const [providerId, entryJson] = args;
  let entry = {};
  if (entryJson) {
    try {
      entry = JSON.parse(entryJson);
    } catch (err) {
      failWith(providerId, new Error(`entry_json is not valid JSON -- ${err.message}`));
      return;
    }
  }

  try {
    const jobs = await executeSingle(providerId, entry);
    process.stdout.write(JSON.stringify(jobs));
  } catch (err) {
    failWith(providerId, err);
  }
}

// Guarded so this file can be imported (e.g. run_provider.test.mjs
// importing classifyError or executeBatch) without running the CLI.
const isMain = process.argv[1] && import.meta.url === pathToFileURL(process.argv[1]).href;
if (isMain) {
  main();
}
