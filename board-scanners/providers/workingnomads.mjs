// @ts-check
/** @typedef {import('./_types.js').Provider} Provider */

const WORKINGNOMADS_API_URL = 'https://www.workingnomads.co/api/exposed_jobs/';
const WORKINGNOMADS_HEADERS = { Accept: 'application/json' };

function matchesSearchTerm(job, term) {
  if (!term) return true;
  const needle = term.toLowerCase();
  const haystack = `${job.title || ''} ${job.category_name || ''} ${job.tags || ''}`.toLowerCase();
  return haystack.includes(needle);
}

/** @type {Provider} */
export default {
  id: 'workingnomads',
  detect() {
    return null;
  },
  async fetch(entry, ctx) {
    const json = await ctx.fetchJson(WORKINGNOMADS_API_URL, { headers: WORKINGNOMADS_HEADERS });
    const jobs = Array.isArray(json) ? json : [];
    return jobs
      .filter((j) => j.url && j.title)
      .filter((j) => matchesSearchTerm(j, entry.search_term))
      .map((j) => ({
        title: j.title || '',
        url: j.url,
        company: j.company_name || entry.name,
        location: j.location || '',
        posted_at: j.pub_date || '',
        description: j.description || '',
      }));
  },
};
