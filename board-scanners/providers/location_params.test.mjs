// Location/radius plumbing for the two providers that were registered
// but location-blind. Both APIs support a location + radius natively;
// neither was sending one, so a configured commute radius had no effect
// on either.
//
// The units differ between them, which is the whole reason this has
// tests: Adzuna's `distance` is KILOMETRES, USAJOBS' `Radius` is MILES.
//
// Run: npm test (from the project root)

import { test } from 'node:test';
import assert from 'node:assert/strict';
import adzuna from './adzuna.mjs';
import usajobs from './usajobs.mjs';

function capturingCtx(payload, capture) {
  return {
    transport: 'http',
    fetchText: async () => '',
    fetchJson: async (url) => {
      capture.url = url;
      return payload;
    },
  };
}

function withEnv(vars, fn) {
  const previous = {};
  for (const [k, v] of Object.entries(vars)) {
    previous[k] = process.env[k];
    if (v === null) delete process.env[k];
    else process.env[k] = v;
  }
  return Promise.resolve(fn()).finally(() => {
    for (const [k, v] of Object.entries(previous)) {
      if (v === undefined) delete process.env[k];
      else process.env[k] = v;
    }
  });
}

test('adzuna: converts the mile radius to kilometres', async () => {
  const capture = {};
  await withEnv({ ADZUNA_APP_ID: 'id', ADZUNA_APP_KEY: 'key' }, () =>
    adzuna.fetch(
      { name: 'adzuna', location: 'Getzville, NY', radius_miles: 25 },
      capturingCtx({ results: [] }, capture)
    )
  );
  const params = new URL(capture.url).searchParams;
  assert.equal(params.get('where'), 'Getzville, NY');
  // 25 mi -> 40 km. Sending 25 verbatim would search a radius 1.6x too
  // small, silently returning fewer local jobs than configured.
  assert.equal(params.get('distance'), '40');
});

test('adzuna: omits location params when no origin is configured', async () => {
  const capture = {};
  await withEnv({ ADZUNA_APP_ID: 'id', ADZUNA_APP_KEY: 'key' }, () =>
    adzuna.fetch({ name: 'adzuna' }, capturingCtx({ results: [] }, capture))
  );
  const params = new URL(capture.url).searchParams;
  assert.equal(params.get('where'), null);
  assert.equal(params.get('distance'), null);
});

test('usajobs: sends the radius in miles, unconverted', async () => {
  const capture = {};
  await withEnv({ USAJOBS_API_KEY: 'key', USAJOBS_EMAIL: 'a@b.c' }, () =>
    usajobs.fetch(
      { name: 'usajobs', search_term: 'marketing', location: 'Buffalo, NY', radius_miles: 25 },
      capturingCtx({ SearchResult: { SearchResultItems: [] } }, capture)
    )
  );
  const params = new URL(capture.url).searchParams;
  assert.equal(params.get('LocationName'), 'Buffalo, NY');
  assert.equal(params.get('Radius'), '25');
});

test('usajobs: omits location params when no origin is configured', async () => {
  const capture = {};
  await withEnv({ USAJOBS_API_KEY: 'key', USAJOBS_EMAIL: 'a@b.c' }, () =>
    usajobs.fetch(
      { name: 'usajobs', search_term: 'marketing' },
      capturingCtx({ SearchResult: { SearchResultItems: [] } }, capture)
    )
  );
  const params = new URL(capture.url).searchParams;
  assert.equal(params.get('LocationName'), null);
  assert.equal(params.get('Radius'), null);
});
