// @ts-check
/** @typedef {import('./_types.js').Provider} Provider */
import { splitItems, extractTag } from './_rss.mjs';

const AUTHENTICJOBS_RSS_URL = 'https://authenticjobs.com/?feed=job_feed';

function matchesSearchTerm(title, description, term) {
  if (!term) return true;
  const needle = term.toLowerCase();
  return `${title} ${description || ''}`.toLowerCase().includes(needle);
}

/** @type {Provider} */
export default {
  id: 'authenticjobs',
  detect() {
    return null;
  },
  async fetch(entry, ctx) {
    const xml = await ctx.fetchText(AUTHENTICJOBS_RSS_URL);
    return splitItems(xml)
      .map((item) => ({
        title: extractTag(item, 'title'),
        link: extractTag(item, 'link'),
        description: extractTag(item, 'description'),
        pubDate: extractTag(item, 'pubDate'),
      }))
      .filter((j) => j.link && j.title)
      .filter((j) => matchesSearchTerm(j.title, j.description, entry.search_term))
      .map((j) => ({
        title: j.title,
        url: /** @type {string} */ (j.link),
        company: entry.name, // Authentic Jobs RSS titles/links don't expose a company field
        location: '',
        posted_at: j.pubDate || '',
        description: j.description || '',
      }));
  },
};
