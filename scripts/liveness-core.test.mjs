import test from 'node:test';
import assert from 'node:assert/strict';

import { classifyLiveness, MIN_CONTENT_CHARS } from './liveness-core.mjs';

const body = (text) => text.padEnd(MIN_CONTENT_CHARS + 1, ' .');

test('an anti-bot interstitial reports blocked, not uncertain', () => {
  const result = classifyLiveness({ status: 200, bodyText: 'Just a moment...' });
  assert.equal(result.result, 'blocked');
  assert.equal(result.code, 'blocked_body');
});

test('a login wall URL reports blocked', () => {
  const result = classifyLiveness({
    status: 200,
    finalUrl: 'https://www.linkedin.com/authwall?trk=x',
    bodyText: body('Sign in'),
  });
  assert.equal(result.result, 'blocked');
  assert.equal(result.code, 'blocked_url');
});

test('an expired posting behind a login wall still reports expired', () => {
  // Ordering matters: blocked is checked AFTER the expired patterns, so a
  // real verdict is never downgraded to "we could not look".
  const result = classifyLiveness({
    status: 200,
    bodyText: body('This job has expired. Sign in to continue'),
  });
  assert.equal(result.result, 'expired');
});

test('a readable page is never called blocked', () => {
  const result = classifyLiveness({
    status: 200,
    bodyText: body('Responsibilities and qualifications'),
    applyControls: ['Apply now'],
  });
  assert.equal(result.result, 'active');
});

test('a short body is still insufficient_content, not blocked', () => {
  const result = classifyLiveness({ status: 200, bodyText: 'Home  About  Careers' });
  assert.equal(result.result, 'uncertain');
  assert.equal(result.code, 'insufficient_content');
});
