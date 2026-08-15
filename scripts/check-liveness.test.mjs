// Unit tests for check-liveness.mjs's buildProgressEvent() -- the
// structured per-item progress line liveness.py's _verify_candidates()
// parses to drive the shared themed ScanActivity step-log instead of
// passing raw stderr text through.
//
// Run: node --test scripts/check-liveness.test.mjs

import { test } from 'node:test';
import assert from 'node:assert/strict';
import { buildProgressEvent } from './check-liveness.mjs';

test('buildProgressEvent: 1-indexes the position and carries result/code/reason/source_file', () => {
  const event = buildProgressEvent(
    0, 25, { source_file: '/jds/acme.json', url: 'https://acme.com/job/1' },
    'active', 'apply_control_visible', 'visible apply control detected',
  );
  assert.deepEqual(event, {
    type: 'progress',
    index: 1,
    total: 25,
    result: 'active',
    code: 'apply_control_visible',
    reason: 'visible apply control detected',
    source_file: '/jds/acme.json',
  });
});

test('buildProgressEvent: null reason becomes JSON null, not undefined', () => {
  const event = buildProgressEvent(
    4, 25, { source_file: '/jds/widgets.json' }, 'active', 'apply_control_visible', undefined,
  );
  assert.equal(event.reason, null);
  assert.equal(JSON.stringify(event).includes('undefined'), false);
});
