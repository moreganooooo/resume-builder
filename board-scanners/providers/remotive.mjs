// @ts-check
/** @typedef {import('./_types.js').Provider} Provider */

const REMOTIVE_API_URL = 'https://remotive.com/api/remote-jobs';
const REMOTIVE_HEADERS = { Accept: 'application/json' };

/** @type {Provider} */
export default {
  id: 'remotive',
  detect() {
    return null;
  },
  async fetch(entry, ctx) {
    const url = entry.search_term
      ? `${REMOTIVE_API_URL}?search=${encodeURIComponent(entry.search_term)}`
      : REMOTIVE_API_URL;
    const json = await ctx.fetchJson(url, { headers: REMOTIVE_HEADERS });
    const jobs = Array.isArray(json?.jobs) ? json.jobs : [];
    return jobs
      .filter((j) => j.url && j.title)
      .map((j) => ({
        title: j.title || '',
        url: j.url,
        company: j.company_name || entry.name,
        location: j.candidate_required_location || '',
        posted_at: j.publication_date || '',
        description: j.description || '',
        employment_type: j.job_type || '',
        // Free text, and often empty or vague ("competitive"). Passed
        // through anyway -- compensation.py falls back to the prose
        // parser for strings, which either finds a figure or returns
        // None, and None is kept.
        compensation: j.salary || '',
      }));
  },
};
