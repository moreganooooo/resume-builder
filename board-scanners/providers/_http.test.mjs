// Unit tests for _http.mjs's policy layer (B26, docs/review/phase-9-backlog.md):
// retry/backoff, Retry-After handling, the honest shared User-Agent, and
// makeHttpCtx()'s per-provider minGapMs pacing. Mocks the global `fetch` (and,
// where needed, timers) via node:test's built-in `t.mock` -- no real network
// calls, no real waiting on backoff delays.
//
// Run: npm test (from the project root) -- or directly:
//   NODE_ENV=test node --test board-scanners/providers/_http.test.mjs
// NODE_ENV=test is required here, not optional: the exponential-backoff
// retry test below ticks a mocked clock by fixed amounts that only match
// _http.mjs's real backoff delay when its jitter term is suppressed via
// `process.env.NODE_ENV === 'test'`. Without it, real Math.random() jitter
// routinely pushes the actual delay past the fixed tick(), so the retry's
// setTimeout never fires within the ticked window and the test hangs
// indefinitely instead of failing loudly.

import { test } from 'node:test';
import assert from 'node:assert/strict';
import { fetchWithTimeout, fetchJson, makeHttpCtx } from './_http.mjs';

// Drains the microtask queue via a real setImmediate (not faked -- mock
// timers below is scoped to just `setTimeout`). Needed before each
// t.mock.timers.tick() call below: the retry path under test is reached
// through several chained `await`s (the mocked fetch, res.text(), the
// throw/catch) that haven't run yet at the point `fetchJson()` is merely
// called-not-awaited -- ticking before that chain reaches its own
// setTimeout() call would advance the fake clock past a timer that doesn't
// exist yet, and the real one would never fire.
function flushMicrotasks() {
  return new Promise((resolve) => setImmediate(resolve));
}

test('fetchWithTimeout: sends the shared honest User-Agent', async (t) => {
  let sentHeaders;
  t.mock.method(globalThis, 'fetch', async (_url, opts) => {
    sentHeaders = opts.headers;
    return new Response('{}', { status: 200 });
  });

  await fetchWithTimeout('https://example.com');

  assert.equal(sentHeaders['user-agent'], 'resume-builder/1.0 (+https://github.com/moreganooooo/resume-builder)');
});

test('fetchWithTimeout: retries a 429 and honors Retry-After instead of guessing a backoff', async (t) => {
  t.mock.timers.enable({ apis: ['setTimeout'] });
  let calls = 0;
  t.mock.method(globalThis, 'fetch', async () => {
    calls += 1;
    if (calls === 1) {
      return new Response('rate limited', { status: 429, headers: { 'retry-after': '2' } });
    }
    return new Response('{"ok":true}', { status: 200 });
  });

  const promise = fetchJson('https://example.com');
  await flushMicrotasks();
  t.mock.timers.tick(2000); // exactly the Retry-After the mocked response sent
  const result = await promise;

  assert.equal(calls, 2);
  assert.deepEqual(result, { ok: true });
});

test('fetchWithTimeout: retries a 500 with exponential backoff when there is no Retry-After', async (t) => {
  t.mock.timers.enable({ apis: ['setTimeout'] });
  let calls = 0;
  t.mock.method(globalThis, 'fetch', async () => {
    calls += 1;
    if (calls <= 2) return new Response('boom', { status: 500 });
    return new Response('{"ok":true}', { status: 200 });
  });

  const promise = fetchJson('https://example.com');
  await flushMicrotasks();
  t.mock.timers.tick(500);        // attempt 0 -> base * 2^0
  await flushMicrotasks();
  t.mock.timers.tick(1000);       // attempt 1 -> base * 2^1
  const result = await promise;

  assert.equal(calls, 3);
  assert.deepEqual(result, { ok: true });
});

test('fetchWithTimeout: does not retry a plain 404', async (t) => {
  let calls = 0;
  t.mock.method(globalThis, 'fetch', async () => {
    calls += 1;
    return new Response('nope', { status: 404 });
  });

  await assert.rejects(() => fetchWithTimeout('https://example.com'), /HTTP 404/);
  assert.equal(calls, 1);
});

test('fetchWithTimeout: a timeout (AbortError) is not retried -- it already spent timeoutMs once', async (t) => {
  let calls = 0;
  t.mock.method(globalThis, 'fetch', async (_url, opts) => {
    calls += 1;
    return new Promise((_resolve, reject) => {
      opts.signal.addEventListener('abort', () => {
        const err = new Error('aborted');
        err.name = 'AbortError';
        reject(err);
      });
    });
  });

  await assert.rejects(
    () => fetchWithTimeout('https://example.com', { timeoutMs: 5 }),
    (err) => err.name === 'AbortError',
  );
  assert.equal(calls, 1);
});

test('makeHttpCtx: a provider with minGapMs configured serializes calls at least that far apart', async (t) => {
  const timestamps = [];
  t.mock.method(globalThis, 'fetch', async () => {
    timestamps.push(Date.now());
    return new Response('{}', { status: 200 });
  });

  const ctx = makeHttpCtx('hackernews'); // PROVIDER_HTTP_CONFIG.hackernews.minGapMs = 150
  await Promise.all([ctx.fetchJson('https://a'), ctx.fetchJson('https://b'), ctx.fetchJson('https://c')]);

  assert.equal(timestamps.length, 3);
  assert.ok(timestamps[1] - timestamps[0] >= 140, 'expected >=140ms gap before the 2nd call');
  assert.ok(timestamps[2] - timestamps[1] >= 140, 'expected >=140ms gap before the 3rd call');
});

test('makeHttpCtx: a provider with no minGapMs configured does not serialize calls', async (t) => {
  let concurrent = 0;
  let maxConcurrent = 0;
  t.mock.method(globalThis, 'fetch', async () => {
    concurrent += 1;
    maxConcurrent = Math.max(maxConcurrent, concurrent);
    await new Promise((resolve) => setTimeout(resolve, 20));
    concurrent -= 1;
    return new Response('{}', { status: 200 });
  });

  const ctx = makeHttpCtx('remoteok'); // not in PROVIDER_HTTP_CONFIG
  await Promise.all([ctx.fetchJson('https://a'), ctx.fetchJson('https://b')]);

  assert.ok(maxConcurrent >= 2, 'expected both calls to overlap');
});
