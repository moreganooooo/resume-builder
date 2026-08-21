// Regression tests for what a web search actually returns.
//
// Brave returned pre-cleaned titles and these paths were never
// exercised. DuckDuckGo returns the page's own <title>, which for ATS
// boards is boilerplate ("Job Application for <role> at <company>") and
// is often truncated mid-phrase. The first live sweep wrote 25 JDs
// titled that way, several with the SWEEP QUERY's name stamped on as
// the employer.
//
// Run: npm test (from the project root)

import { test } from 'node:test';
import assert from 'node:assert/strict';
import provider from './websearch.mjs';

async function sweep(results, name = 'Workday — Onboarding & Success remote') {
  return provider.fetch(
    { name, scan_query: 'q', _isSweep: true, _results: results },
    {}
  );
}

test('strips the Greenhouse "Job Application for ... at ..." boilerplate', async () => {
  const jobs = await sweep([
    {
      url: 'https://boards.greenhouse.io/engine/jobs/1',
      title: 'Job Application for Lifecycle Marketing Manager at Engine',
      description: 'x',
    },
  ]);
  assert.equal(jobs[0].title, 'Lifecycle Marketing Manager');
});

test('trims a dangling separator left by a truncated result', async () => {
  const jobs = await sweep([
    {
      url: 'https://boards.greenhouse.io/acme/jobs/2',
      title: 'Job Application for Technical Customer Success Lead | Contract | ',
      description: 'x',
    },
  ]);
  assert.ok(!jobs[0].title.endsWith('|'), `unexpected trailing pipe: ${jobs[0].title}`);
  assert.ok(!/\s$/.test(jobs[0].title));
});

test('recognizes a Workday subdomain as the employer', async () => {
  // Without this the sweep fell through to entry.name and stamped the
  // QUERY's name on the job, which also defeats dedup's
  // source_url+company_name match.
  const jobs = await sweep([
    {
      url: 'https://sharecare.wd1.myworkdayjobs.com/en-US/Sharecare_Careers/job/Forms_J1',
      title: 'Forms Completion Specialist - Remote',
      description: 'x',
    },
  ]);
  assert.equal(jobs[0].company, 'Sharecare');
});

test('never uses the sweep query name as a company', async () => {
  const jobs = await sweep([
    {
      url: 'https://example-ats.com/careers/job/7',
      title: 'Some Marketing Role',
      description: 'x',
    },
  ]);
  for (const job of jobs) {
    assert.notEqual(job.company, 'Workday — Onboarding & Success remote');
  }
});

test('falls back to the company named in the title', async () => {
  const jobs = await sweep([
    {
      url: 'https://jobs.example.com/posting/5',
      title: 'Job Application for Growth Marketer at Northwind',
      description: 'x',
    },
  ]);
  if (jobs.length) assert.equal(jobs[0].company, 'Northwind');
});

test('a tracked company entry still uses its own name', async () => {
  // Only sweeps have the ambiguity; a tracked entry's name IS the
  // employer and must keep winning.
  const jobs = await provider.fetch(
    {
      name: 'Acme Corp',
      scan_query: 'q',
      _results: [
        {
          url: 'https://boards.greenhouse.io/other/jobs/3',
          title: 'Marketing Manager',
          description: 'x',
        },
      ],
    },
    {}
  );
  assert.equal(jobs[0].company, 'Acme Corp');
});
