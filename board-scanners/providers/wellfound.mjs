// @ts-check
/** @typedef {import('./_types.js').Provider} Provider */

const WELLFOUND_API_URL = 'https://wellfound.com/api/jobs';
const WELLFOUND_HEADERS = {
  Accept: 'application/json',
  'User-Agent':
    'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36',
};

/** @type {Provider} */
export default {
  id: 'wellfound',
  detect(url) {
    if (/wellfound\.com\/jobs|angel\.co\/jobs/i.test(url)) {
      return { provider: 'wellfound', board: 'wellfound' };
    }
    return null;
  },
  async fetch(entry, ctx) {
    const query = entry.search_term || 'software engineer';
    const targetUrl = `${WELLFOUND_API_URL}?keyword=${encodeURIComponent(query)}`;

    try {
      const resp = await ctx.fetchJson(targetUrl, { headers: WELLFOUND_HEADERS });
      const listings = Array.isArray(resp?.jobs) ? resp.jobs : [];

      return listings.map((j) => ({
        title: j.title || j.role || 'Startup Engineer',
        company: j.company?.name || entry.name || 'Startup',
        url: j.job_url || (j.slug ? `https://wellfound.com/jobs/${j.slug}` : 'https://wellfound.com/jobs'),
        location: j.remote ? 'Remote' : j.location || 'Remote',
        posted_at: j.posted_at || new Date().toISOString(),
        description: j.description || '',
      }));
    } catch {
      return [];
    }
  },
};
