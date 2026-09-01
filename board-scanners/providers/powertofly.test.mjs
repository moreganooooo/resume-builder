// Unit tests for powertofly.mjs's feed mapping.
//
// The feed's `description` field holds the COMPANY NAME, not a
// description -- verified against the live endpoint 2026-08-31. Reading
// it as prose put a company name in every posting's description while
// `company` fell back to the feed entry's own name, so both fields were
// wrong at once. These tests pin the corrected mapping.
import { test } from 'node:test';
import assert from 'node:assert/strict';
import provider from './powertofly.mjs';

// One item in the shape the live endpoint actually returns.
const ITEM = {
  categories: ['Finance'],
  description: 'Morgan Stanley',
  guid: 'https://powertofly.com/jobs/detail/2498747',
  job_location: 'Atlanta, GA, United States',
  link: 'https://powertofly.com/jobs/detail/2498747',
  published_on: '2026-08-29',
  section: ['morgan-stanley'],
  title: 'Wealth Management Associate',
  type: 'Onsite',
};

function ctxReturning(items) {
  return { fetchJson: async () => ({ items }) };
}

test('company comes from the feed, not from the config entry name', async () => {
  const jobs = await provider.fetch({ name: 'PowerToFly' }, ctxReturning([ITEM]));
  assert.equal(jobs.length, 1);
  assert.equal(jobs[0].company, 'Morgan Stanley');
});

test('the company name is not written into the description', async () => {
  const jobs = await provider.fetch({ name: 'PowerToFly' }, ctxReturning([ITEM]));
  // Empty on purpose: this feed carries no body. scan_boards then falls
  // back to _fetch_posting_text(), and scan.run_scan() refuses to write a
  // JD that still has none -- an empty one would be permanent.
  assert.equal(jobs[0].description, '');
});

test('the section slug is a fallback company, not the first choice', async () => {
  const noName = { ...ITEM, description: '' };
  const jobs = await provider.fetch({ name: 'PowerToFly' }, ctxReturning([noName]));
  assert.equal(jobs[0].company, 'morgan-stanley');
});

test('the entry name is the last resort', async () => {
  const bare = { ...ITEM, description: '', section: [] };
  const jobs = await provider.fetch({ name: 'PowerToFly' }, ctxReturning([bare]));
  assert.equal(jobs[0].company, 'PowerToFly');
});

test('the workplace mode is passed through for the location gate', async () => {
  const jobs = await provider.fetch({ name: 'PowerToFly' }, ctxReturning([ITEM]));
  assert.equal(jobs[0].work_model, 'Onsite');
  assert.equal(jobs[0].location, 'Atlanta, GA, United States');
});
