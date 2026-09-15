// Unit tests for dayforce.mjs: portal URL parsing, response mapping, and
// the CSRF-then-paginate fetch flow (global fetch is stubbed -- no network).
//
// Run: npm test (from the project root)

import { test, afterEach } from 'node:test';
import assert from 'node:assert/strict';
import dayforce, { resolvePortal, parseDayforceResponse, cookieHeader } from './dayforce.mjs';

const PORTAL = { culture: 'en-US', namespace: 'acme', board: 'CANDIDATEPORTAL' };
const realFetch = globalThis.fetch;
afterEach(() => { globalThis.fetch = realFetch; });

test('resolvePortal: full portal URL', () => {
  assert.deepEqual(
    resolvePortal({ careers_url: 'https://jobs.dayforcehcm.com/en-US/acme/CANDIDATEPORTAL' }),
    PORTAL,
  );
});

test('resolvePortal: board segment defaults to CANDIDATEPORTAL', () => {
  assert.equal(resolvePortal({ careers_url: 'https://jobs.dayforcehcm.com/en-US/acme' }).board, 'CANDIDATEPORTAL');
});

test('resolvePortal: rejects other hosts, http, and unsafe segments', () => {
  assert.equal(resolvePortal({ careers_url: 'https://evil.example.com/en-US/acme' }), null);
  assert.equal(resolvePortal({ careers_url: 'http://jobs.dayforcehcm.com/en-US/acme' }), null);
  assert.equal(resolvePortal({ careers_url: 'https://jobs.dayforcehcm.com/en-US/a%2F..' }), null);
  assert.equal(resolvePortal({ careers_url: 'https://jobs.dayforcehcm.com/acme' }), null);
  assert.equal(dayforce.detect({ careers_url: 'https://boards.greenhouse.io/acme' }), null);
});

test('parseDayforceResponse: builds the posting URL and maps fields', () => {
  const jobs = parseDayforceResponse({
    jobPostings: [{
      jobPostingId: 39564,
      jobTitle: ' Title Clerk ',
      jobDescription: '<p>Process titles.</p>',
      postingLocations: [{ formattedAddress: 'Buffalo, NY, USA' }, { formattedAddress: 'Austin, TX, USA' }],
      postingStartTimestampUTC: '2026-09-15T06:00:00+00:00',
      hasVirtualLocation: false,
    }],
  }, 'Acme', PORTAL);
  assert.deepEqual(jobs[0], {
    title: 'Title Clerk',
    url: 'https://jobs.dayforcehcm.com/en-US/acme/CANDIDATEPORTAL/jobs/39564',
    company: 'Acme',
    location: 'Buffalo, NY, USA OR Austin, TX, USA',
    description: '<p>Process titles.</p>',
    posted_at: '2026-09-15T06:00:00+00:00',
  });
});

test('parseDayforceResponse: virtual location sets is_remote; bad id yields empty url', () => {
  const [job] = parseDayforceResponse({ jobPostings: [{ jobPostingId: 'x', jobTitle: 'X', hasVirtualLocation: true }] }, 'Acme', PORTAL);
  assert.equal(job.is_remote, true);
  assert.equal(job.url, '');
  assert.equal(job.description, '');
  assert.deepEqual(parseDayforceResponse({}, 'Acme', PORTAL), []);
});

test('cookieHeader: keeps name=value pairs only', () => {
  assert.equal(cookieHeader(['a=1; Path=/; HttpOnly', 'b=2; Secure']), 'a=1; b=2');
});

test('fetch: sends the CSRF token and cookie, and paginates to maxCount', async () => {
  const calls = [];
  const page = (ids, offset) => ({ jobPostings: ids.map(id => ({ jobPostingId: id, jobTitle: `Job ${id}` })), offset, count: ids.length, maxCount: 3 });
  globalThis.fetch = async (url, init = {}) => {
    calls.push({ url, init });
    if (url.endsWith('/api/auth/csrf')) {
      return new Response(JSON.stringify({ csrfToken: 'tok' }), {
        status: 200, headers: { 'set-cookie': '__Host-next-auth.csrf-token=abc; Path=/; HttpOnly' },
      });
    }
    const { paginationStart } = JSON.parse(init.body);
    return new Response(JSON.stringify(paginationStart === 0 ? page([1, 2], 0) : page([3], 2)), { status: 200 });
  };

  const jobs = await dayforce.fetch({ name: 'Acme', careers_url: 'https://jobs.dayforcehcm.com/en-US/acme' }, null, { delayMs: 0 });
  assert.deepEqual(jobs.map(j => j.title), ['Job 1', 'Job 2', 'Job 3']);
  assert.equal(calls.length, 3);
  const search = calls[1];
  assert.equal(search.url, 'https://jobs.dayforcehcm.com/api/geo/acme/jobposting/search');
  assert.equal(search.init.method, 'POST');
  assert.equal(search.init.headers['x-csrf-token'], 'tok');
  assert.equal(search.init.headers.cookie, '__Host-next-auth.csrf-token=abc');
  assert.equal(JSON.parse(calls[2].init.body).paginationStart, 2);
});

test('fetch: missing csrfToken is an error, not an empty result', async () => {
  globalThis.fetch = async () => new Response('{}', { status: 200 });
  await assert.rejects(
    dayforce.fetch({ name: 'Acme', careers_url: 'https://jobs.dayforcehcm.com/en-US/acme' }, null, { delayMs: 0 }),
    /no csrfToken/,
  );
});
