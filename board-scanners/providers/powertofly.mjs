// @ts-check
/** @typedef {import('./_types.js').Provider} Provider */

// NOTE: this endpoint's URL ends in `/rss` but returns JSON, not XML —
// confirmed against ever-jobs's PowertoflyApiResponse type ({ items, status }).
const POWERTOFLY_API_URL = 'https://powertofly.com/jobs/rss';
const POWERTOFLY_HEADERS = { Accept: 'application/json' };

function matchesSearchTerm(item, term) {
  if (!term) return true;
  const needle = term.toLowerCase();
  const categories = Array.isArray(item.categories) ? item.categories.join(' ') : '';
  const haystack = `${item.title || ''} ${categories}`.toLowerCase();
  return haystack.includes(needle);
}

/** @type {Provider} */
export default {
  id: 'powertofly',
  detect() {
    return null;
  },
  async fetch(entry, ctx) {
    const json = await ctx.fetchJson(POWERTOFLY_API_URL, { headers: POWERTOFLY_HEADERS });
    const items = Array.isArray(json?.items) ? json.items : [];
    return items
      .filter((item) => (item.link || item.guid) && item.title)
      .filter((item) => matchesSearchTerm(item, entry.search_term))
      .map((item) => ({
        title: item.title || '',
        url: item.link || item.guid,
        // `description` is the COMPANY NAME, not a description -- verified
        // against the live feed 2026-08-31, which returns
        // {"description":"Morgan Stanley", "title":"Wealth Management
        // Associate"}. Reading it as prose wrote a company name into the
        // description of every PowerToFly posting, and `company` fell back
        // to the feed entry's own name, so BOTH fields were wrong. That
        // breaks more than display: email_matcher.py selects the candidate
        // set for an incoming rejection by company, so a wrong company
        // attaches real status mail to the wrong application.
        // `section` is the same company as a slug; preferred only as a
        // fallback since it is hyphenated ("morgan-stanley").
        company: item.description || (Array.isArray(item.section) ? item.section[0] : '') || entry.name,
        location: item.job_location || '',
        posted_at: item.published_on || '',
        // Deliberately EMPTY: this feed carries no posting body at all.
        // scan_boards falls back to _fetch_posting_text() for an empty
        // description, which is the only way to get real text here, and
        // scan.run_scan() refuses to write a JD that still has none --
        // writing an empty one makes the emptiness permanent, since
        // job_key_known() then skips the posting on every later scan.
        description: '',
        // "Onsite" / "Remote" / "Hybrid". Free workplace signal the
        // location gate can use instead of inferring from a place name.
        work_model: item.type || '',
      }));
  },
};
