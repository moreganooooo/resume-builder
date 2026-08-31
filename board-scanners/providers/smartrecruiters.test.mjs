// Unit tests for smartrecruiters.mjs's parsing + B36 description detail-fetch
// (docs/review/phase-9-backlog.md): the /postings list endpoint never
// carries a description -- only GET /postings/{id}'s jobAd.sections does.
//
// Run: npm test (from the project root)

import { test } from 'node:test';
import assert from 'node:assert/strict';
import { parseSmartRecruitersResponse, extractJobAdText } from './smartrecruiters.mjs';
import defaultExport from './smartrecruiters.mjs';

test('parseSmartRecruitersResponse: carries _postingId through for the detail-fetch loop', () => {
  const json = { content: [{ id: '123abc', name: 'Marketing Manager', ref: null, location: {} }] };
  const jobs = parseSmartRecruitersResponse(json, 'Acme');
  assert.equal(jobs[0]._postingId, '123abc');
});

test('parseSmartRecruitersResponse: _postingId is null when the item has no id', () => {
  const json = { content: [{ name: 'X', location: {} }] };
  const jobs = parseSmartRecruitersResponse(json, 'Acme');
  assert.equal(jobs[0]._postingId, null);
});

test('extractJobAdText: joins the free-text sections in a fixed order', () => {
  const detail = {
    jobAd: {
      sections: {
        jobDescription: { text: 'Do the work.' },
        companyDescription: { text: 'We are Acme.' },
        qualifications: { text: '5+ years.' },
      },
    },
  };
  assert.equal(
    extractJobAdText(detail),
    'We are Acme.\n\nDo the work.\n\n5+ years.',
  );
});

test('extractJobAdText: missing sections are skipped, not rendered as blank paragraphs', () => {
  const detail = { jobAd: { sections: { jobDescription: { text: 'Only this.' } } } };
  assert.equal(extractJobAdText(detail), 'Only this.');
});

test('extractJobAdText: a totally empty/unexpected shape returns an empty string, not a throw', () => {
  assert.equal(extractJobAdText({}), '');
  assert.equal(extractJobAdText(null), '');
  assert.equal(extractJobAdText(undefined), '');
});

test('fetch: bounds detail fetches to the cap and strips _postingId from the result', async () => {
  const entry = { careers_url: 'https://jobs.smartrecruiters.com/Acme' };
  let listCalls = 0;
  let detailCalls = 0;
  const ctx = {
    fetchJson: async (url) => {
      if (url.includes('/postings?')) {
        listCalls += 1;
        if (listCalls > 1) return { content: [] }; // stop pagination after page 1
        return {
          content: [
            { id: '1', name: 'Job One', location: {} },
            { id: '2', name: 'Job Two', location: {} },
          ],
        };
      }
      // Detail endpoint
      detailCalls += 1;
      return { jobAd: { sections: { jobDescription: { text: `Detail for ${url}` } } } };
    },
  };

  const jobs = await defaultExport.fetch(entry, ctx);

  assert.equal(jobs.length, 2);
  assert.equal(detailCalls, 2);
  assert.ok(jobs.every((j) => !('_postingId' in j)), '_postingId must not leak into the returned Job');
  assert.match(jobs[0].description, /^Detail for /);
});

test('fetch: a failing detail fetch degrades to an empty description, not a thrown error', async () => {
  const entry = { careers_url: 'https://jobs.smartrecruiters.com/Acme' };
  let listCalls = 0;
  const ctx = {
    fetchJson: async (url) => {
      if (url.includes('/postings?')) {
        listCalls += 1;
        if (listCalls > 1) return { content: [] };
        return { content: [{ id: '1', name: 'Job One', location: {} }] };
      }
      throw new Error('boom');
    },
  };

  const jobs = await defaultExport.fetch(entry, ctx);
  assert.equal(jobs.length, 1);
  assert.equal(jobs[0].description, '');
});

test('parseSmartRecruitersResponse: unwraps typeOfEmployment.label', () => {
  // SmartRecruiters nests the value under a label object. Passed through
  // in its own spelling; employment_type.py understands the shape.
  const jobs = parseSmartRecruitersResponse(
    { content: [{ id: '1', name: 'Job One', location: {}, typeOfEmployment: { label: 'Part-time' } }] },
    'Acme',
  );
  assert.equal(jobs[0].employment_type, 'Part-time');
});

test('parseSmartRecruitersResponse: a posting with no typeOfEmployment is empty, not undefined', () => {
  const jobs = parseSmartRecruitersResponse(
    { content: [{ id: '1', name: 'Job One', location: {} }] },
    'Acme',
  );
  assert.equal(jobs[0].employment_type, '');
});
