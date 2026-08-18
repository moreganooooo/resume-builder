// @ts-check
/** @typedef {import('./_types.js').Provider} Provider */

const OTTA_API_URL = 'https://app.otta.com/api/jobs/search';
const OTTA_HEADERS = {
  Accept: 'application/json',
  'User-Agent':
    'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36',
};

/** @type {Provider} */
export default {
  id: 'otta',
  detect(url) {
    if (/otta\.com\/jobs|app\.otta\.com/i.test(url)) {
      return { provider: 'otta', board: 'otta' };
    }
    return null;
  },
  async fetch(entry, ctx) {
    const query = entry.search_term || 'software engineer';
    const targetUrl = `${OTTA_API_URL}?q=${encodeURIComponent(query)}`;

    try {
      const resp = await ctx.fetchJson(targetUrl, { headers: OTTA_HEADERS });
      const listings = Array.isArray(resp?.results)
        ? resp.results
        : Array.isArray(resp?.jobs)
        ? resp.jobs
        : [];

      return listings.map((j) => ({
        title: j.title || j.job_title || 'Software Engineer',
        company: j.company?.name || j.company_name || entry.name || 'Tech Company',
        url: j.url || j.apply_url || `https://app.otta.com/jobs/${j.id || ''}`,
        location: j.location || 'Remote',
        posted_at: j.created_at || new Date().toISOString(),
        description: j.description || j.summary || '',
      }));
    } catch {
      return [];
    }
  },
};
