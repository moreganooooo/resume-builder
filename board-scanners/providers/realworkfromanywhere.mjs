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
      .map((j) => ({
        title: /** @type {string} */ (j.title),
        url: /** @type {string} */ (j.link),
        company: entry.name, // feed exposes no company field on items
        location: '',
        posted_at: j.pubDate || '',
        description: j.description || '',
      }));
  },
};
