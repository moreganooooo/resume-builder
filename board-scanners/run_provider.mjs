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
 * Prints the provider's Job[] array as JSON to stdout. Any failure
 * (unknown provider, network error, malformed provider module) prints a
 * message to stderr and exits non-zero -- scan_boards.py treats that as
 * "this source produced nothing this run", not a fatal scan failure.
 */

import { pathToFileURL } from 'url';
import path from 'path';
import { fileURLToPath } from 'url';
import { makeHttpCtx } from './providers/_http.mjs';

const PROVIDERS_DIR = path.resolve(path.dirname(fileURLToPath(import.meta.url)), 'providers');

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
    console.error(`${providerId}: failed to load provider -- ${err.message}`);
    process.exit(1);
  }

  const provider = mod.default;
  if (!provider || typeof provider.fetch !== 'function') {
    console.error(`${providerId}: module has no default export with a fetch() function`);
    process.exit(1);
  }

  let entry = {};
  if (entryJson) {
    try {
      entry = JSON.parse(entryJson);
    } catch (err) {
      console.error(`${providerId}: entry_json is not valid JSON -- ${err.message}`);
      process.exit(1);
    }
  }

  try {
    const jobs = await provider.fetch(entry, makeHttpCtx());
    if (!Array.isArray(jobs)) {
      throw new Error('fetch() did not return an array');
    }
    process.stdout.write(JSON.stringify(jobs));
  } catch (err) {
    console.error(`${providerId}: ${err.message}`);
    process.exit(1);
  }
}

main();
