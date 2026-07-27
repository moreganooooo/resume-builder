// @ts-check
/** @typedef {import('./_types.js').Provider} Provider */
import { splitItems, extractTag } from './_rss.mjs';

const NODESK_RSS_URL = 'https://nodesk.co/remote-jobs/index.xml';
const NODESK_HEADERS = { Accept: 'application/rss+xml, application/xml, text/xml' };

function splitTitle(rawTitle) {
  if (!rawTitle) return { company: '', title: '' };
  const idx = rawTitle.lastIndexOf(' at ');
  if (idx === -1) return { company: '', title: rawTitle };
  return { title: rawTitle.slice(0, idx).trim(), company: rawTitle.slice(idx + 4).trim() };
}

function matchesSearchTerm(title, description, term) {
  if (!term) return true;
  const needle = term.toLowerCase();
  return `${title} ${description || ''}`.toLowerCase().includes(needle);
}

/** @type {Provider} */
export default {
  id: 'nodesk',
  detect() {
    return null;
  },
  async fetch(entry, ctx) {
    const xml = await ctx.fetchText(NODESK_RSS_URL, { headers: NODESK_HEADERS });
    return splitItems(xml)
      .map((item) => {
        const rawTitle = extractTag(item, 'title') || '';
        const { company, title } = splitTitle(rawTitle);
        return {
          title,
          company,
          link: extractTag(item, 'link'),
          description: extractTag(item, 'description'),
          pubDate: extractTag(item, 'pubDate'),
        };
      })
      .filter((j) => j.link && j.title)
      .filter((j) => matchesSearchTerm(j.title, j.description, entry.search_term))
      .map((j) => ({
        title: j.title,
        url: /** @type {string} */ (j.link),
        company: j.company || entry.name,
        location: '',
        posted_at: j.pubDate || '',
        description: j.description || '',
      }));
  },
};
