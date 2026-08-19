// Unit tests for workday.mjs's pagination safety net (B19,
// docs/review/phase-9-backlog.md) -- uses Node's built-in `node:test` +
// `node:assert`, matching smartrecruiters.mjs's pattern of exporting a pure
// function for unit testing rather than exercising a live network call.
//
// `resolveWorkdayLimit`, `paginateWorkdayJobs`, and (added for B36,
// docs/review/phase-9-backlog.md) `fetchJobDescription` are exercised here --
// all three are pure with respect to the network (fetch is injected via a
// mocked `ctx`), so none of this touches Playwright or a real Workday
// tenant.
//
// Run: npm test (from the project root)

import { test } from 'node:test';
import assert from 'node:assert/strict';
import { resolveWorkdayLimit, paginateWorkdayJobs, fetchJobDescription } from './workday.mjs';

const BASE_URL = 'https://acme.wd1.myworkdayjobs.com/External';
const API_BASE = 'https://acme.wd1.myworkdayjobs.com/wday/cxs/acme/External/jobs';

function makePosting(n) {
  return { title: `Job ${n}`, externalPath: `/job/${n}`, locationsText: 'Remote' };
}

function makeCtx(pages) {
  // `pages` is an array of either a response object or an Error to throw,
  // consumed in order -- one entry per paginated fetchJson call.
  let call = 0;
  return {
    fetchJson: async () => {
      const next = pages[call];
      call += 1;
      if (next instanceof Error) throw next;
      return next;
    },
    get callCount() { return call; },
  };
}

test('resolveWorkdayLimit: uses data.limit when positive', () => {
  assert.equal(resolveWorkdayLimit({ limit: 50 }), 50);
});

test('resolveWorkdayLimit: falls back to default when limit is 0 (not just missing)', () => {
  // This is the B19 `?? 20` bug: `data.limit: 0` with a truthy `total` used
  // to sail through `?? 20` (which only catches null/undefined) and turn
  // `offset += limit` into an infinite loop. `||` must catch the 0 case too.
  assert.equal(resolveWorkdayLimit({ limit: 0, total: 500 }), 20);
});

test('resolveWorkdayLimit: falls back to default when limit is missing', () => {
  assert.equal(resolveWorkdayLimit({}), 20);
  assert.equal(resolveWorkdayLimit(undefined), 20);
});

test('paginateWorkdayJobs: walks a paginated sequence to completion, respecting the page cap', async () => {
  // total=250, limit=100 -> first page already collected by the caller
  // (offset 0..99), this covers offset=100 and offset=200 (2 more pages).
  const ctx = makeCtx([
    { jobPostings: [makePosting(100), makePosting(101)] },
    { jobPostings: [makePosting(200), makePosting(201)] },
  ]);

  const jobs = await paginateWorkdayJobs(ctx, API_BASE, BASE_URL, 'Acme', 100, 250, {
    delayMs: 0, // skip the real politeness delay in tests
    maxPages: 50,
  });

  assert.equal(jobs.length, 4);
  assert.equal(ctx.callCount, 2);
  assert.deepEqual(jobs[0], {
    title: 'Job 100',
    url: `${BASE_URL}/job/100`,
    company: 'Acme',
    location: 'Remote',
    _externalPath: '/job/100',
  });
});

test('paginateWorkdayJobs: page cap stops the loop before a runaway total is exhausted', async () => {
  // total is huge; maxPages=2 must stop the loop at 2 fetchJson calls
  // regardless, mirroring smartrecruiters.mjs's SR_MAX_PAGES safety net.
  const ctx = {
    fetchJson: async () => ({ jobPostings: [makePosting(1)] }),
  };
  let calls = 0;
  const countingCtx = {
    fetchJson: async (...args) => {
      calls += 1;
      return ctx.fetchJson(...args);
    },
  };

  const jobs = await paginateWorkdayJobs(countingCtx, API_BASE, BASE_URL, 'Acme', 100, 100_000, {
    delayMs: 0,
    maxPages: 2,
  });

  assert.equal(calls, 2);
  assert.equal(jobs.length, 2);
});

test('paginateWorkdayJobs: a limit of 0 does not spin the loop forever', async () => {
  // If resolveWorkdayLimit's fallback were bypassed and 0 reached this
  // function directly, `offset += 0` would never advance -- the page cap is
  // the last line of defense, and must still terminate the loop.
  const ctx = {
    fetchJson: async () => ({ jobPostings: [makePosting(1)] }),
  };
  let calls = 0;
  const countingCtx = {
    fetchJson: async (...args) => {
      calls += 1;
      return ctx.fetchJson(...args);
    },
  };

  const jobs = await paginateWorkdayJobs(countingCtx, API_BASE, BASE_URL, 'Acme', 0, 500, {
    delayMs: 0,
    maxPages: 5,
  });

  assert.equal(calls, 5); // bounded by maxPages, not an infinite loop
  assert.equal(jobs.length, 5);
});

test('paginateWorkdayJobs: a mid-loop 429/non-ok failure returns jobs already collected, not nothing', async () => {
  // ctx.fetchJson (via _http.mjs's fetchWithTimeout) throws on a non-ok
  // response -- e.g. a 429. The loop must catch that and return what it has
  // instead of losing the pages already gathered.
  const rateLimitError = new Error('HTTP 429: rate limited');
  rateLimitError.status = 429;

  const ctx = makeCtx([
    { jobPostings: [makePosting(100)] },
    { jobPostings: [makePosting(200)] },
    rateLimitError,
    { jobPostings: [makePosting(400)] }, // never reached
  ]);

  const jobs = await paginateWorkdayJobs(ctx, API_BASE, BASE_URL, 'Acme', 100, 500, {
    delayMs: 0,
    maxPages: 50,
  });

  assert.equal(jobs.length, 2);
  assert.equal(ctx.callCount, 3); // stopped right after the failing call, no 4th
  assert.deepEqual(jobs.map(j => j.title), ['Job 100', 'Job 200']);
});

test('paginateWorkdayJobs: a wall-clock deadline in the past returns immediately with no jobs', async () => {
  const ctx = {
    fetchJson: async () => { throw new Error('should never be called'); },
  };

  const jobs = await paginateWorkdayJobs(ctx, API_BASE, BASE_URL, 'Acme', 100, 500, {
    delayMs: 0,
    maxPages: 50,
    deadline: Date.now() - 1, // already past
  });

  assert.equal(jobs.length, 0);
});

test('fetchJobDescription: swaps the trailing /jobs for the posting externalPath and extracts jobDescription', async () => {
  let requestedUrl;
  const ctx = {
    fetchJson: async (url) => {
      requestedUrl = url;
      return { jobPostingInfo: { jobDescription: '<p>Do the work.</p>' } };
    },
  };

  const description = await fetchJobDescription(ctx, API_BASE, '/job/Marketing-Manager_R1234');

  assert.equal(requestedUrl, 'https://acme.wd1.myworkdayjobs.com/wday/cxs/acme/External/job/Marketing-Manager_R1234');
  assert.equal(description, '<p>Do the work.</p>');
});

test('fetchJobDescription: a failed detail fetch degrades to an empty string, not a thrown error', async () => {
  const ctx = { fetchJson: async () => { throw new Error('boom'); } };
  assert.equal(await fetchJobDescription(ctx, API_BASE, '/job/x'), '');
});

test('fetchJobDescription: an unexpected response shape returns an empty string', async () => {
  const ctx = { fetchJson: async () => ({}) };
  assert.equal(await fetchJobDescription(ctx, API_BASE, '/job/x'), '');
});
