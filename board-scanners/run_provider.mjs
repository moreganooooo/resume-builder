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

function failWith(providerId, err) {
  console.error(`${providerId}: ${err.message || err}`);
  process.stdout.write(JSON.stringify({ error: { kind: classifyError(err), message: String((err && err.message) || err) } }));
  process.exit(1);
}

async function main() {
  const [providerId, entryJson] = process.argv.slice(2);
  if (!providerId) {
    console.error('Usage: node run_provider.mjs <provider_id> <entry_json>');
    process.exit(1);
  }

  const modPath = path.join(PROVIDERS_DIR, `${providerId}.mjs`);
  let mod;
  try {
    mod = await import(pathToFileURL(modPath).href);
  } catch (err) {
    failWith(providerId, new Error(`failed to load provider -- ${err.message}`));
    return;
  }

  const provider = mod.default;
  if (!provider || typeof provider.fetch !== 'function') {
    failWith(providerId, new Error('module has no default export with a fetch() function'));
    return;
  }

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
    const jobs = await provider.fetch(entry, makeHttpCtx(providerId));
    if (!Array.isArray(jobs)) {
      throw new Error('fetch() did not return an array');
    }
    process.stdout.write(JSON.stringify(jobs));
  } catch (err) {
    failWith(providerId, err);
  }
}

// Guarded so this file can be imported (e.g. run_provider.test.mjs
// importing classifyError) without also running the CLI -- unguarded,
// import() would parse process.argv as if it were this script's own argv
// and likely process.exit(1) on "Usage: ...", killing the importing
// process too.
const isMain = process.argv[1] && import.meta.url === pathToFileURL(process.argv[1]).href;
if (isMain) {
  main();
}
