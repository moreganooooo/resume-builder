import test from 'node:test';
import assert from 'node:assert/strict';

import { classifyNavigationError, pollForStableContent } from './liveness-browser.mjs';
import { MIN_CONTENT_CHARS } from './liveness-core.mjs';

const long = (text) => text.padEnd(MIN_CONTENT_CHARS + 1, ' .');
const noWait = async () => {};

test('a redirect loop reports expired, not uncertain', () => {
  const err = new Error(
    'page.goto: net::ERR_TOO_MANY_REDIRECTS at https://boards.greenhouse.io/bark/jobs/3783783\nCall log:\n  - navigating...'
  );
  const result = classifyNavigationError(err);
  assert.equal(result.result, 'expired');
  assert.equal(result.code, 'redirect_loop');
});

test('a plain navigation timeout stays uncertain', () => {
  const err = new Error('page.goto: Timeout 15000ms exceeded.');
  const result = classifyNavigationError(err);
  assert.equal(result.result, 'uncertain');
  assert.equal(result.code, 'navigation_error');
});

test('a DNS failure stays uncertain', () => {
  const err = new Error('page.goto: net::ERR_NAME_NOT_RESOLVED at https://example.invalid/');
  const result = classifyNavigationError(err);
  assert.equal(result.result, 'uncertain');
  assert.equal(result.code, 'navigation_error');
});

test('a page that is long enough on the first read skips the extra settle check', async () => {
  let reads = 0;
  const readText = async () => {
    reads += 1;
    return long('real content');
  };
  const result = await pollForStableContent(readText, noWait);
  assert.equal(result, long('real content'));
  assert.equal(reads, 1);
});

test('content that clears the bar via polling gets one more read before returning', async () => {
  // Simulates a cookie-consent banner (long enough to clear the bar)
  // being replaced by the real body one render tick later.
  const reads = [
    '',
    long('cookie consent banner'),
    long('the real job posting content'),
  ];
  let i = 0;
  const readText = async () => reads[Math.min(i++, reads.length - 1)];
  const result = await pollForStableContent(readText, noWait);
  assert.equal(result, long('the real job posting content'));
});

test('a page that never clears the bar returns whatever it has after the budget', async () => {
  const readText = async () => 'still too short';
  const result = await pollForStableContent(readText, noWait);
  assert.equal(result, 'still too short');
});
