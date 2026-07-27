// @ts-check
/** @typedef {import('./_types.js').Provider} Provider */

const JOBICY_API_URL = 'https://jobicy.com/api/v2/remote-jobs';
const JOBICY_HEADERS = { Accept: 'application/json' };

function matchesSearchTerm(job, term) {
  if (!term) return true;
  const needle = term.toLowerCase();
  const haystack = `${job.jobTitle || ''} ${(job.jobIndustry || []).join(' ')}`.toLowerCase();
  return haystack.includes(needle);
}

/** @type {Provider} */
export default {
  id: 'jobicy',
  detect() {
    return null;
  },
  async fetch(entry, ctx) {
    const json = await ctx.fetchJson(JOBICY_API_URL, { headers: JOBICY_HEADERS });
    const jobs = Array.isArray(json?.jobs) ? json.jobs : [];
    return jobs
      .filter((j) => j.url && j.jobTitle)
      .filter((j) => matchesSearchTerm(j, entry.search_term))
      .map((j) => ({
        title: j.jobTitle || '',
        url: j.url,
        company: j.companyName || entry.name,
        location: j.jobGeo || '',
        posted_at: j.pubDate || '',
        description: j.jobDescription || j.jobExcerpt || '',
      }));
  },
};
