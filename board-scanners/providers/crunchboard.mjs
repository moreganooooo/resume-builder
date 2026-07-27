// @ts-check
/** @typedef {import('./_types.js').Provider} Provider */
import { splitItems, extractTag } from './_rss.mjs';

const CRUNCH_RSS_URL = 'https://www.crunchboard.com/jobs.rss';
const CRUNCH_HEADERS = { Accept: 'application/rss+xml, application/xml, text/xml' };

function matchesSearchTerm(title, description, category, term) {
  if (!term) return true;
  const needle = term.toLowerCase();
  return `${title} ${description || ''} ${category || ''}`.toLowerCase().includes(needle);
}

/** @type {Provider} */
export default {
  id: 'crunchboard',
  detect() {
    return null;
  },
  async fetch(entry, ctx) {
    const xml = await ctx.fetchText(CRUNCH_RSS_URL, { headers: CRUNCH_HEADERS });
    return splitItems(xml)
      .map((item) => ({
        title: extractTag(item, 'title'),
        link: extractTag(item, 'link'),
        description: extractTag(item, 'description'),
        category: extractTag(item, 'category') || extractTag(item, 'dc:subject'),
        pubDate: extractTag(item, 'pubDate') || extractTag(item, 'dc:date'),
      }))
      .filter((j) => j.link && j.title)
      .filter((j) => matchesSearchTerm(j.title, j.description, j.category, entry.search_term))
      .map((j) => ({
        title: /** @type {string} */ (j.title),
        url: /** @type {string} */ (j.link),
        company: entry.name, // feed provides no explicit company field
        location: '',
        posted_at: j.pubDate || '',
        description: j.description || '',
      }));
  },
};
