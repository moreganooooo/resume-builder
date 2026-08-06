// Unit tests for recruitee.mjs's parseRecruiteeResponse, focused on B36's
// description mapping (docs/review/phase-9-backlog.md): the /api/offers/
// list response already carries `description`/`requirements` -- no second
// detail fetch needed, unlike SmartRecruiters or Workday.
//
// Run: node --test board-scanners/providers/recruitee.test.mjs

import { test } from 'node:test';
import assert from 'node:assert/strict';
import { parseRecruiteeResponse } from './recruitee.mjs';

test('parseRecruiteeResponse: maps description and appends requirements', () => {
  const json = {
    offers: [{
      title: 'Marketing Manager',
      careers_url: 'https://acme.recruitee.com/o/marketing-manager',
      city: 'Remote',
      description: '<p>Own our lifecycle programs.</p>',
      requirements: '<ul><li>5+ years experience</li></ul>',
    }],
  };
  const jobs = parseRecruiteeResponse(json, 'Acme');
  assert.equal(jobs.length, 1);
  assert.equal(jobs[0].description, '<p>Own our lifecycle programs.</p>\n\n<ul><li>5+ years experience</li></ul>');
});

test('parseRecruiteeResponse: description-only offer (no requirements) is not padded with extra separators', () => {
  const json = { offers: [{ title: 'X', url: 'https://acme.recruitee.com/o/x', description: 'Just this.' }] };
  const jobs = parseRecruiteeResponse(json, 'Acme');
  assert.equal(jobs[0].description, 'Just this.');
});

test('parseRecruiteeResponse: missing description/requirements yields an empty string, not undefined', () => {
  const json = { offers: [{ title: 'X', url: 'https://acme.recruitee.com/o/x' }] };
  const jobs = parseRecruiteeResponse(json, 'Acme');
  assert.equal(jobs[0].description, '');
});

test('parseRecruiteeResponse: off-domain URL is still dropped (unrelated to the description change)', () => {
  const json = { offers: [{ title: 'X', url: 'https://evil.example.com/o/x', description: 'desc' }] };
  const jobs = parseRecruiteeResponse(json, 'Acme');
  assert.equal(jobs[0].url, '');
  assert.equal(jobs[0].description, 'desc');
});
