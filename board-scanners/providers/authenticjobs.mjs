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
        // dc:creator holds the poster's account slug, which names the real
        // employer (e.g. "hirediscord" for Discord) -- was previously
        // discarded and every listing fell back to the fixed provider
        // label "authenticjobs", which broke per-employer dedup.
        creator: extractTag(item, 'dc:creator'),
      }))
      .filter((j) => j.link && j.title)
      .filter((j) => matchesSearchTerm(j.title, j.description, entry.search_term))
      .map((j) => ({
        title: j.title,
        url: /** @type {string} */ (j.link),
        company: j.creator || entry.name,
        location: '',
        posted_at: j.pubDate || '',
        description: j.description || '',
      }));
  },
};
