/**
 * render-page-text.mjs -- visible text of pages that need JavaScript.
 *
 * company_research.py's fallback for sites whose plain HTML is an empty
 * shell until a browser runs their scripts. Usage:
 *   node render-page-text.mjs <url> [<url> ...]
 * Prints one JSON object, {url: text}, to stdout. A page that fails to
 * load maps to "".
 *
 * With --links, each url instead maps to {finalUrl, links}: where the page
 * ended up after redirects, plus every anchor href and iframe src on it --
 * what discover_local_employers.py reads to spot an embedded ATS board. A
 * page that fails to load maps to null. Pages are visited one at a time on a single page --
 * project rule: never run Playwright in parallel.
 */

import { chromium } from 'playwright';
import { pollForStableContent } from './liveness-browser.mjs';

const NAV_TIMEOUT_MS = 15_000;
const USER_AGENT =
  'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 ' +
  '(KHTML, like Gecko) Chrome/124.0 Safari/537.36';

async function main() {
  const args = process.argv.slice(2);
  const wantLinks = args.includes('--links');
  const urls = args.filter((a) => a !== '--links');
  const out = {};
  if (urls.length === 0) {
    process.stdout.write('{}');
    return;
  }
  const browser = await chromium.launch({ headless: true });
  try {
    const context = await browser.newContext({ userAgent: USER_AGENT });
    const page = await context.newPage();
    for (const url of urls) {
      try {
        await page.goto(url, { waitUntil: 'domcontentloaded', timeout: NAV_TIMEOUT_MS });
        // Same poll-until-painted read liveness uses: a client-rendered
        // page's body is often empty at DOMContentLoaded.
        const text = await pollForStableContent(
          () => page.evaluate(() => document.body?.innerText ?? ''),
          (ms) => page.waitForTimeout(ms),
        );
        out[url] = wantLinks
          ? {
              finalUrl: page.url(),
              links: await page.evaluate(() => [
                ...[...document.querySelectorAll('a[href]')].map((a) => a.href),
                ...[...document.querySelectorAll('iframe[src]')].map((f) => f.src),
              ]),
            }
          : text;
      } catch {
        out[url] = wantLinks ? null : '';
      }
    }
  } finally {
    await browser.close();
  }
  process.stdout.write(JSON.stringify(out));
}

main().catch((err) => {
  process.stderr.write(`render-page-text: ${err.message}\n`);
  process.exit(1);
});
