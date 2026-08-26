// Unit tests for run_provider.mjs's classifyError() (B27,
// docs/review/phase-9-backlog.md) -- the error-envelope classification
// scan_boards.py's _run_node_provider() reads instead of guessing a reason
// from the last line of stderr.
//
// Run: node --test board-scanners/run_provider.test.mjs

import { test } from 'node:test';
import assert from 'node:assert/strict';
import { classifyError, executeBatch } from './run_provider.mjs';

test('classifyError: HTTP status takes priority over message text', () => {
  const err = new Error('some generic message');
  err.status = 401;
  assert.equal(classifyError(err), 'auth');
});

test('classifyError: 403 is auth, 429 is quota, 500+ is network', () => {
  assert.equal(classifyError(Object.assign(new Error('x'), { status: 403 })), 'auth');
  assert.equal(classifyError(Object.assign(new Error('x'), { status: 429 })), 'quota');
  assert.equal(classifyError(Object.assign(new Error('x'), { status: 503 })), 'network');
});

test('classifyError: a plain 404 is not one of the network/auth/quota buckets', () => {
  const err = Object.assign(new Error('x'), { status: 404 });
  assert.equal(classifyError(err), 'config');
});

test('classifyError: missing API key message is auth', () => {
  const err = new Error('websearch: BRAVE_API_KEY is not set. Add it to your .env file.');
  assert.equal(classifyError(err), 'auth');
});

test('classifyError: rate limit wording without a status is quota', () => {
  const err = new Error('Brave API error: rate limit exceeded, try again later');
  assert.equal(classifyError(err), 'quota');
});

test('classifyError: AbortError (timeout) is network', () => {
  const err = new Error('The operation was aborted');
  err.name = 'AbortError';
  assert.equal(classifyError(err), 'network');
});

test('classifyError: DNS/connection error codes are network', () => {
  assert.equal(classifyError(Object.assign(new Error('x'), { code: 'ENOTFOUND' })), 'network');
  assert.equal(classifyError(Object.assign(new Error('x'), { code: 'ECONNREFUSED' })), 'network');
});

test('classifyError: anything unrecognized falls back to config, not a guessed transient reason', () => {
  const err = new Error('cannot derive API URL for Acme');
  assert.equal(classifyError(err), 'config');
});

test('executeBatch: handles empty array', async () => {
  const results = await executeBatch([]);
  assert.deepEqual(results, []);
});

test('executeBatch: isolates errors across multiple items', async () => {
  const items = [
    { provider_id: 'nonexistent_provider_123', entry: {} },
    { provider_id: '', entry: {} },
  ];
  const results = await executeBatch(items);
  assert.equal(results.length, 2);
  assert.equal(results[0].status, 'rejected');
  assert.equal(results[0].provider_id, 'nonexistent_provider_123');
  assert.equal(results[0].error.kind, 'config');
  assert.equal(results[1].status, 'rejected');
  assert.equal(results[1].provider_id, 'unknown');
  assert.equal(results[1].error.kind, 'config');
});
