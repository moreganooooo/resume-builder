// Unit tests for jooble.mjs. Network is mocked -- these assert the
// request SHAPE and the mapping, which is where this provider's two
// real hazards live: a ZIP-only location silently returns nothing, and
// the snippet is a teaser that must be declared as one.
//
// Run: npm test (from the project root)

import { test } from 'node:test';
import assert from 'node:assert/strict';
import provider from './jooble.mjs';

const SAMPLE = {
  totalCount: 2,
  jobs: [
    {
      title: 'Director of Marketing',
      location: 'Buffalo, NY',
      snippet: '&nbsp;...Job Description <b>Marketing </b>lead for the region',
      link: 'https://jooble.org/jdp/123',
      company: 'Acme',
      updated: '2026-08-19T00:00:00.0000000',
      id: '123',
    },
    { title: '', link: 'https://jooble.org/jdp/456' }, // dropped: no title
  ],
};

function ctxReturning(payload, capture) {
  return {
    transport: 'http',
    fetchText: async () => '',
    fetchJson: async (url, opts) => {
      if (capture) {
        capture.url = url;
        capture.opts = opts;
      }
      return payload;
    },
  };
}

function withKey(value, fn) {
  const previous = process.env.JOOBLE_API_KEY;
  if (value === null) delete process.env.JOOBLE_API_KEY;
  else process.env.JOOBLE_API_KEY = value;
  return Promise.resolve(fn()).finally(() => {
    if (previous === undefined) delete process.env.JOOBLE_API_KEY;
    else process.env.JOOBLE_API_KEY = previous;
  });
}

test('fetch: posts keywords, location and radius to the keyed endpoint', async () => {
  const capture = {};
  await withKey('test-key', async () => {
    await provider.fetch(
      { name: 'jooble', search_term: 'marketing', location: 'Getzville, NY', radius_miles: 25 },
      ctxReturning(SAMPLE, capture)
    );
  });

  // The key is part of the PATH, not a header -- Jooble's design.
  assert.equal(capture.url, 'https://jooble.org/api/test-key');
  assert.equal(capture.opts.method, 'POST');
  const body = JSON.parse(capture.opts.body);
  assert.equal(body.keywords, 'marketing');
  assert.equal(body.location, 'Getzville, NY');
  assert.equal(body.radius, '25');
});

test('fetch: maps the API shape onto the Job typedef', async () => {
  const jobs = await withKey('test-key', () =>
    provider.fetch({ location: 'Buffalo, NY' }, ctxReturning(SAMPLE))
  );

  assert.equal(jobs.length, 1); // the untitled row is dropped
  const job = jobs[0];
  assert.equal(job.title, 'Director of Marketing');
  assert.equal(job.url, 'https://jooble.org/jdp/123');
  assert.equal(job.company, 'Acme');
  assert.equal(job.location, 'Buffalo, NY');
  // Fractional-second tail trimmed to a plain date.
  assert.equal(job.posted_at, '2026-08-19');
});

test('fetch: cleans the HTML fragments Jooble embeds in snippet', async () => {
  const jobs = await withKey('test-key', () =>
    provider.fetch({ location: 'Buffalo, NY' }, ctxReturning(SAMPLE))
  );
  const description = jobs[0].description;
  assert.ok(!description.includes('<b>'), 'tags should be stripped');
  assert.ok(!description.includes('&nbsp;'), 'entities should be decoded');
  assert.ok(description.includes('Marketing'));
});

test('fetch: declares its description a teaser', async () => {
  // ~275 chars clears MIN_DESCRIPTION_CHARS, so without this flag these
  // postings ship looking complete while being far too thin to tailor
  // against -- and the real text is unrecoverable (the posting page
  // 403s every fetch).
  const jobs = await withKey('test-key', () =>
    provider.fetch({ location: 'Buffalo, NY' }, ctxReturning(SAMPLE))
  );
  assert.equal(jobs[0].description_is_teaser, true);
});

test('fetch: refuses a ZIP-only origin instead of returning nothing', async () => {
  // Jooble answers 200 with totalCount 0 for a bare ZIP -- a silent
  // empty result. Failing loudly is the only way that gets noticed.
  await withKey('test-key', async () => {
    await assert.rejects(
      () => provider.fetch({ name: 'jooble' }, ctxReturning(SAMPLE)),
      /city\/state location/
    );
  });
});

test('fetch: fails clearly when the API key is missing', async () => {
  await withKey(null, async () => {
    await assert.rejects(
      () => provider.fetch({ location: 'Buffalo, NY' }, ctxReturning(SAMPLE)),
      /JOOBLE_API_KEY/
    );
  });
});
