// @ts-check
/** @typedef {import('./_types.js').Provider} Provider */

const ADZUNA_API_BASE_URL = 'https://api.adzuna.com/v1/api/jobs';
const ADZUNA_HEADERS = { Accept: 'application/json' };
const ADZUNA_COUNTRY_CODE = 'us';
const ADZUNA_RESULTS_PER_PAGE = 25;

/** @type {Provider} */
export default {
  id: 'adzuna',
  detect() {
    return null;
  },
  async fetch(entry, ctx) {
    const appId = process.env.ADZUNA_APP_ID;
    const appKey = process.env.ADZUNA_APP_KEY;
    if (!appId || !appKey) {
      throw new Error('adzuna: missing ADZUNA_APP_ID / ADZUNA_APP_KEY environment variables');
    }
    const params = new URLSearchParams({
      app_id: appId,
      app_key: appKey,
      results_per_page: String(ADZUNA_RESULTS_PER_PAGE),
    });
    if (entry.search_term) params.set('what', entry.search_term);
    const url = `${ADZUNA_API_BASE_URL}/${ADZUNA_COUNTRY_CODE}/search/1?${params.toString()}`;
    const json = await ctx.fetchJson(url, { headers: ADZUNA_HEADERS });
    const jobs = Array.isArray(json?.results) ? json.results : [];
    return jobs
      .filter((j) => j.redirect_url && j.title)
      .map((j) => ({
        title: j.title || '',
        url: j.redirect_url,
        company: j.company?.display_name || entry.name,
        location: j.location?.display_name || '',
        posted_at: j.created || '',
      }));
  },
};
