// Unit tests for workable.mjs's markdown-feed parsing + B36 per-posting
// description detail-fetch (docs/review/phase-9-backlog.md): the jobs.md
// table has no description column, but each row's own [View] link is
// itself a fetchable markdown detail page before this parser strips it
// down to the human-facing URL.
//
// Run: npm test (from the project root)

import { test } from 'node:test';
import assert from 'node:assert/strict';
import { parseWorkableMarkdown } from './workable.mjs';
import defaultExport from './workable.mjs';

const FEED = [
  '| Title | Department | Location | Type | Salary | Posted | Details |',
  '|---|---|---|---|---|---|---|',
  '| Marketing Manager | Marketing | Remote | Full-time |  | 2026-08-01 | [View](https://apply.workable.com/acme/jobs/view/123.md) |',
  '| Off Domain | Ops | Remote | Full-time |  | 2026-08-01 | [View](https://evil.example.com/jobs/view/999.md) |',
].join('\n');

test('parseWorkableMarkdown: strips .md for the public url but keeps _detailUrl for the fetchable page', () => {
  const jobs = parseWorkableMarkdown(FEED, 'Acme');
  assert.equal(jobs.length, 1); // the off-domain row is dropped
  assert.equal(jobs[0].url, 'https://apply.workable.com/acme/jobs/view/123');
  assert.equal(jobs[0]._detailUrl, 'https://apply.workable.com/acme/jobs/view/123.md');
});

test('fetch: bounds detail fetches to the cap and strips _detailUrl from the result', async () => {
  const entry = { careers_url: 'https://apply.workable.com/acme' };
  let feedCalls = 0;
  let detailCalls = 0;
  const ctx = {
    fetchText: async (url) => {
      if (url.endsWith('/jobs.md')) {
        feedCalls += 1;
        return FEED;
      }
      detailCalls += 1;
      return `# Marketing Manager\n\nFull job body for ${url}`;
    },
  };

  const jobs = await defaultExport.fetch(entry, ctx);

  assert.equal(feedCalls, 1);
  assert.equal(jobs.length, 1);
  assert.equal(detailCalls, 1);
  assert.ok(!('_detailUrl' in jobs[0]), '_detailUrl must not leak into the returned Job');
  assert.match(jobs[0].description, /^# Marketing Manager/);
});

test('fetch: a failing detail fetch degrades to an empty description, not a thrown error', async () => {
  const entry = { careers_url: 'https://apply.workable.com/acme' };
  const ctx = {
    fetchText: async (url) => {
      if (url.endsWith('/jobs.md')) return FEED;
      throw new Error('boom');
    },
  };

  const jobs = await defaultExport.fetch(entry, ctx);
  assert.equal(jobs.length, 1);
  assert.equal(jobs[0].description, '');
});

test('parseWorkableMarkdown: maps the Type column through as employment_type', () => {
  // Passed through in workable's own spelling ("Full-time"), not
  // normalized here -- scripts/employment_type.py owns the vocabulary and
  // logs values it cannot map, which only works if it sees what the
  // source actually said.
  const jobs = parseWorkableMarkdown(FEED, 'Acme');
  assert.equal(jobs[0].employment_type, 'Full-time');
});

test('parseWorkableMarkdown: a row with no Type column yields an empty employment_type', () => {
  // Absent means "not stated", and the gate keeps those -- so this must
  // not become the string "undefined", which would be logged as an
  // unmappable value on every scan.
  const feed = [
    '| Title | Department | Location | Type | Salary | Posted | Details |',
    '|---|---|---|---|---|---|---|',
    '| Copywriter | Marketing | Remote |  |  | 2026-08-01 | [View](https://apply.workable.com/acme/jobs/view/1.md) |',
  ].join('\n');
  assert.equal(parseWorkableMarkdown(feed, 'Acme')[0].employment_type, '');
});

test('parseWorkableMarkdown: maps the Salary column through as compensation', () => {
  // Free text, and passed through verbatim for the same reason as the
  // Type column -- scripts/compensation.py owns the parsing.
  const feed = [
    '| Title | Department | Location | Type | Salary | Posted | Details |',
    '|---|---|---|---|---|---|---|',
    '| Copywriter | Marketing | Remote | Full-time | $80,000 - $95,000 | 2026-08-01 | [View](https://apply.workable.com/acme/jobs/view/1.md) |',
  ].join('\n');
  assert.equal(parseWorkableMarkdown(feed, 'Acme')[0].compensation, '$80,000 - $95,000');
});

test('parseWorkableMarkdown: a blank Salary column yields an empty compensation', () => {
  // Workable renders the column whether or not the employer filled it
  // in, so blank is the common case and must not become "undefined".
  assert.equal(parseWorkableMarkdown(FEED, 'Acme')[0].compensation, '');
});

test('columns are resolved by header name, not by fixed position', () => {
  // Same feed with "Department" removed: every index after Title shifts
  // left. Fixed positions would read Location out of the Type column.
  const md = [
    '| Title | Location | Type | Salary | Posted | Details |',
    '| --- | --- | --- | --- | --- | --- |',
    '| Editor | Austin, TX | Part-time | $30/hr | 2026-01-01 | [View](https://apply.workable.com/acme/jobs/view/1.md) |',
  ].join('\n');
  const jobs = parseWorkableMarkdown(md, 'Acme');
  assert.equal(jobs.length, 1);
  assert.equal(jobs[0].location, 'Austin, TX');
  assert.equal(jobs[0].employment_type, 'Part-time');
  assert.equal(jobs[0].compensation, '$30/hr');
});

test('a feed omitting a column yields an empty field, not a shifted one', () => {
  const md = [
    '| Title | Department | Location | Posted | Details |',
    '| --- | --- | --- | --- | --- |',
    '| Editor | Content | Austin, TX | 2026-01-01 | [View](https://apply.workable.com/acme/jobs/view/1.md) |',
  ].join('\n');
  const jobs = parseWorkableMarkdown(md, 'Acme');
  assert.equal(jobs.length, 1);
  assert.equal(jobs[0].location, 'Austin, TX');
  // Salary is absent from this feed. Empty is correct; "2026-01-01" --
  // what the old fixed index would have read -- is not.
  assert.equal(jobs[0].compensation, '');
  assert.equal(jobs[0].employment_type, '');
});

test('parsing one feed without a column does not reshape the next', () => {
  const short = [
    '| Title | Location | Posted | Details |',
    '| --- | --- | --- | --- |',
    '| A | Austin, TX | 2026-01-01 | [View](https://apply.workable.com/a/jobs/view/1.md) |',
  ].join('\n');
  parseWorkableMarkdown(short, 'A');
  const normal = [
    '| Title | Department | Location | Type | Salary | Posted | Details |',
    '| --- | --- | --- | --- | --- | --- | --- |',
    '| B | Eng | Denver, CO | Full-time | $90k | 2026-01-01 | [View](https://apply.workable.com/b/jobs/view/2.md) |',
  ].join('\n');
  const jobs = parseWorkableMarkdown(normal, 'B');
  assert.equal(jobs[0].location, 'Denver, CO');
  assert.equal(jobs[0].compensation, '$90k');
});
