// @ts-check
/** @typedef {import('./_types.js').Provider} Provider */

const CURATED_README_URL =
  'https://raw.githubusercontent.com/lukasz-madon/awesome-remote-job/master/README.md';

/** @type {Provider} */
export default {
  id: 'remote_curated',
  detect(url) {
    if (/github\.com\/.*awesome-remote-job/i.test(url)) {
      return { provider: 'remote_curated', board: 'awesome-remote-job' };
    }
    return null;
  },
  async fetch(entry, ctx) {
    const text = await ctx.fetchText(CURATED_README_URL);
    if (!text) return [];

    /** @type {Array<import('./_types.js').ScrapedJob>} */
    const results = [];
    const linkRegex = /\[([^\]]+)\]\((https?:\/\/[^\)]+)\)/g;
    let match;

    while ((match = linkRegex.exec(text)) !== null) {
      const name = match[1].trim();
      const url = match[2].trim();

      if (
        !url.includes('github.com') &&
        !url.includes('twitter.com') &&
        !url.includes('linkedin.com') &&
        name.length > 2
      ) {
        results.push({
          title: `Remote Engineering at ${name}`,
          company: name,
          url: url,
          location: 'Remote',
          posted_at: new Date().toISOString(),
          description: `Curated remote company profile from awesome-remote-job repository. Careers URL: ${url}`,
        });
      }
    }

    return results.slice(0, 50);
  },
};
