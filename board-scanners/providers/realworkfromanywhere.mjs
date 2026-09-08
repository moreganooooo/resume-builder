// @ts-check
/** @typedef {import('./_types.js').Provider} Provider */
import { splitItems, extractTag } from './_rss.mjs';

const RWFA_RSS_URL = 'https://www.realworkfromanywhere.com/rss.xml';
const RWFA_HEADERS = { Accept: 'application/rss+xml, application/xml, text/xml' };

function matchesSearchTerm(title, description, category, term) {
  if (!term) return true;
  const needle = term.toLowerCase();
  return `${title} ${description || ''} ${category || ''}`.toLowerCase().includes(needle);
}

// Every title in this feed ends "<role> at <Company>" -- the feed itself
// exposes no company field on items (see below), but the employer name is
// right there in the title. Previously discarded, so every listing fell
// back to the fixed provider label "realworkfromanywhere", which broke
// per-employer dedup and hid the real company from evaluation entirely.
const TITLE_COMPANY_RE = /^(.*)\s+at\s+([^,]+?)(\s*\(Remote\))?$/i;

function splitTitleCompany(rawTitle, fallbackName) {
  const match = rawTitle.match(TITLE_COMPANY_RE);
  if (!match) return { title: rawTitle, company: fallbackName };
  const suffix = match[3] || '';
  return { title: `${match[1].trim()}${suffix}`, company: match[2].trim() };
}

/** @type {Provider} */
export default {
  id: 'realworkfromanywhere',
  detect() {
    return null;
  },
  async fetch(entry, ctx) {
    const xml = await ctx.fetchText(RWFA_RSS_URL, { headers: RWFA_HEADERS });
    return splitItems(xml)
      .map((item) => ({
        title: extractTag(item, 'title'),
        link: extractTag(item, 'link'),
        description: extractTag(item, 'description'),
        category: extractTag(item, 'category'),
        pubDate: extractTag(item, 'pubDate'),
      }))
      .filter((j) => j.link && j.title)
      .filter((j) => matchesSearchTerm(j.title, j.description, j.category, entry.search_term))
      .map((j) => {
        const { title, company } = splitTitleCompany(/** @type {string} */ (j.title), entry.name);
        return {
          title,
          url: /** @type {string} */ (j.link),
          company,
          location: '',
          posted_at: j.pubDate || '',
          description: j.description || '',
        };
      });
  },
};
