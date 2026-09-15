// Unit tests for icims.mjs and _title_priority.mjs: portal URL parsing,
// search-page and JSON-LD extraction, and the paginate-then-describe fetch
// flow (ctx is stubbed -- no network).
//
// Run: npm test (from the project root)

import { test } from 'node:test';
import assert from 'node:assert/strict';
import icims, { resolveOrigin, parseSearchPage, extractJobPosting, formatLocation } from './icims.mjs';
import { prioritizeByTitle, titleRank } from './_title_priority.mjs';

const ORIGIN = 'https://careers-acme.icims.com';

function anchor(id, slug, title) {
  return `<a href="${ORIGIN}/jobs/${id}/${slug}/job?in_iframe=1" class="iCIMS_Anchor" title="${id} - ${title}"><h3>${title}</h3></a>`;
}

function postingPage(fields) {
  return `<html><script type="application/ld+json">${JSON.stringify({ '@type': 'JobPosting', ...fields })}</script></html>`;
}

test('resolveOrigin: accepts icims hosts, rejects others', () => {
  assert.equal(resolveOrigin({ careers_url: 'https://careers-acme.icims.com/' }), ORIGIN);
  assert.equal(resolveOrigin({ careers_url: 'https://careers-acme.icims.com/jobs/search?ss=1' }), ORIGIN);
  assert.equal(resolveOrigin({ careers_url: 'http://careers-acme.icims.com/' }), null);
  assert.equal(resolveOrigin({ careers_url: 'https://icims.com.evil.example/' }), null);
  assert.equal(icims.detect({ careers_url: 'https://boards.greenhouse.io/acme' }), null);
});

test('parseSearchPage: ids, urls and titles, deduped, other hosts ignored', () => {
  const html = anchor(2583, 'aircraft-mechanic', 'Aircraft Mechanic')
    + anchor(2583, 'aircraft-mechanic', 'Aircraft Mechanic')
    + anchor(2590, 'data-analyst', 'Data &amp; Test Analyst')
    + '<a href="https://careers-other.icims.com/jobs/1/x/job" title="1 - Other">x</a>';
  assert.deepEqual(parseSearchPage(html, ORIGIN), [
    { id: '2583', url: `${ORIGIN}/jobs/2583/aircraft-mechanic/job`, title: 'Aircraft Mechanic' },
    { id: '2590', url: `${ORIGIN}/jobs/2590/data-analyst/job`, title: 'Data & Test Analyst' },
  ]);
});

test('extractJobPosting and formatLocation', () => {
  const posting = extractJobPosting('<script type="application/ld+json">{bad json</script>' + postingPage({
    title: 'Engineer',
    jobLocation: [
      { address: { addressLocality: 'Buffalo', addressRegion: 'NY' } },
      { address: { addressLocality: 'Niagara Falls', addressRegion: 'NY' } },
    ],
  }));
  assert.equal(posting.title, 'Engineer');
  assert.equal(formatLocation(posting), 'Buffalo, NY OR Niagara Falls, NY');
  assert.equal(extractJobPosting('<html></html>'), null);
});

test('fetch: paginates until a page adds nothing, then maps each posting', async () => {
  const urls = [];
  const ctx = {
    fetchText: async (url) => {
      urls.push(url);
      if (url.includes('pr=0')) return anchor(1, 'a', 'Mechanic') + anchor(2, 'b', 'Data Scientist');
      if (url.includes('pr=1')) return anchor(2, 'b', 'Data Scientist');
      if (url.includes('/jobs/2/')) {
        return postingPage({
          title: 'Data Scientist',
          description: '<p>Model things.</p>',
          datePosted: '2026-09-10',
          employmentType: 'FULL_TIME',
          jobLocation: [{ address: { addressLocality: 'Buffalo', addressRegion: 'NY' } }],
        });
      }
      return '<html></html>';
    },
  };
  const jobs = await icims.fetch(
    { name: 'Acme', careers_url: `${ORIGIN}/`, _title_filter: { positive: ['data'] } },
    ctx,
  );
  assert.equal(jobs.length, 2);
  assert.equal(urls.filter(u => u.includes('/jobs/search')).length, 2);
  // The title-filter match is described first.
  assert.equal(urls[2], `${ORIGIN}/jobs/2/b/job?in_iframe=1`);
  const ds = jobs.find(j => j.title === 'Data Scientist');
  assert.deepEqual(ds, {
    title: 'Data Scientist',
    url: `${ORIGIN}/jobs/2/b/job`,
    company: 'Acme',
    location: 'Buffalo, NY',
    description: '<p>Model things.</p>',
    posted_at: '2026-09-10',
    employment_type: 'FULL_TIME',
  });
  // No JSON-LD: kept with its listing title and no description.
  assert.equal(jobs.find(j => j.title === 'Mechanic').description, undefined);
});

test('titleRank / prioritizeByTitle: positives first, negatives last, stable', () => {
  const filter = { positive: ['data'], negative: ['principal'] };
  assert.equal(titleRank('Data Scientist', filter), 0);
  assert.equal(titleRank('Mechanic', filter), 1);
  assert.equal(titleRank('Principal Data Scientist', filter), 2);
  const jobs = ['Mechanic', 'Principal Data Engineer', 'Data Analyst', 'Clerk', 'Data Scientist'].map(title => ({ title }));
  assert.deepEqual(
    prioritizeByTitle(jobs, filter).map(j => j.title),
    ['Data Analyst', 'Data Scientist', 'Mechanic', 'Clerk', 'Principal Data Engineer'],
  );
  assert.deepEqual(prioritizeByTitle(jobs, undefined), jobs);
});
