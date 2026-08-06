// @ts-check
/** @typedef {import('./_types.js').Provider} Provider */

const THEMUSE_API_URL = 'https://www.themuse.com/api/public/jobs';
const THEMUSE_HEADERS = { Accept: 'application/json' };

function matchesSearchTerm(job, term) {
  if (!term) return true;
  const needle = term.toLowerCase();
  const categories = Array.isArray(job.categories) ? job.categories.map((c) => c.name).join(' ') : '';
  const haystack = `${job.name || ''} ${categories}`.toLowerCase();
  return haystack.includes(needle);
}

/** @type {Provider} */
export default {
  id: 'themuse',
  detect() {
    return null;
  },
  async fetch(entry, ctx) {
    // Was requesting only page 0 (20 rows) then filtering search_term
    // client-side against that one page -- any real match past the first 20
    // postings read as "0 jobs." Only worth paginating when there's actually
    // a term to match against; an unfiltered scan keeps the original
    // single-page request rather than hammering the API for nothing.
    let jobs = [];
    if (entry.search_term) {
      const MAX_PAGES = 25;
      for (let page = 0; page < MAX_PAGES; page++) {
        const json = await ctx.fetchJson(`${THEMUSE_API_URL}?page=${page}`, { headers: THEMUSE_HEADERS });
        const pageJobs = Array.isArray(json?.results) ? json.results : [];
        if (pageJobs.length === 0) break;
        jobs = jobs.concat(pageJobs);
      }
    } else {
      const json = await ctx.fetchJson(`${THEMUSE_API_URL}?page=0`, { headers: THEMUSE_HEADERS });
      jobs = Array.isArray(json?.results) ? json.results : [];
    }
    return jobs
      .filter((j) => j.refs?.landing_page && j.name)
      .filter((j) => matchesSearchTerm(j, entry.search_term))
      .map((j) => ({
        title: j.name || '',
        url: j.refs.landing_page,
        company: j.company?.name || entry.name,
        location: Array.isArray(j.locations) ? j.locations.map((l) => l.name).join(', ') : '',
        posted_at: j.publication_date || '',
        description: j.contents || '',
      }));
  },
};
