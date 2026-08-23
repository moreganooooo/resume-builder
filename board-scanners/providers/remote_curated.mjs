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

      let hostname = '';
      try {
        hostname = new URL(url).hostname.toLowerCase();
      } catch {
        continue;
      }

      const isSocialOrRepo =
        hostname === 'github.com' ||
        hostname.endsWith('.github.com') ||
        hostname === 'twitter.com' ||
        hostname.endsWith('.twitter.com') ||
        hostname === 'x.com' ||
        hostname.endsWith('.x.com') ||
        hostname === 'linkedin.com' ||
        hostname.endsWith('.linkedin.com');

      if (!isSocialOrRepo && name.length > 2) {
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
