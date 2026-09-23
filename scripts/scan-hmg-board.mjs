/**
 * scan-hmg-board.mjs -- every posting on a Haley Marketing ("hmg-jb")
 * staffing-agency job board, as JSON.
 *
 * staffing_boards.py's adapter for boards like jobs.lhtservices.com. Their
 * page HTML carries no postings: the cards are filled in by a call to
 * /json/index.smpl?arg=list_posts whose ticket (`h`/`t`) is minted by the
 * page's own scripts and rejected ("Ticket Mismatch!") when replayed from
 * outside it. So the page is loaded once in headless Chromium, its own
 * list_posts request is observed, and the same URL is re-issued from
 * inside the page with the page size raised -- one navigation returns
 * every posting with its full description. Usage:
 *   node scan-hmg-board.mjs <board-url>
 * Prints {"posts": [...]} or {"error": "..."} to stdout; always exits 0.
 */

import { chromium } from 'playwright';

const NAV_TIMEOUT_MS = 60_000;
const LIST_WAIT_MS = 30_000;
const PAGE_SIZE = 500;
const USER_AGENT =
  'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 ' +
  '(KHTML, like Gecko) Chrome/124.0 Safari/537.36';

// The endpoint's JSON has trailing commas, which JSON.parse rejects.
function parseLoose(text) {
  return JSON.parse(text.replace(/,(\s*[}\]])/g, '$1'));
}

async function main() {
  const url = process.argv[2];
  if (!url) {
    process.stdout.write(JSON.stringify({ error: 'no board url given' }));
    return;
  }
  const browser = await chromium.launch({ headless: true });
  try {
    const context = await browser.newContext({ userAgent: USER_AGENT });
    const page = await context.newPage();
    const listUrl = new Promise((resolve, reject) => {
      const timer = setTimeout(
        () => reject(new Error('board never requested list_posts -- not an hmg-jb board?')),
        LIST_WAIT_MS,
      );
      page.on('request', (req) => {
        if (req.url().includes('arg=list_posts')) {
          clearTimeout(timer);
          resolve(req.url());
        }
      });
    });
    await page.goto(url, { waitUntil: 'domcontentloaded', timeout: NAV_TIMEOUT_MS });
    const observed = await listUrl;
    const full = observed.includes('pp=')
      ? observed.replace(/pp=\d+/, `pp=${PAGE_SIZE}`)
      : `${observed}&pp=${PAGE_SIZE}`;
    const text = await page.evaluate(async (u) => (await fetch(u)).text(), full);
    const result = parseLoose(text).ResultSet || {};
    const msg = result.ticket?.msg;
    if (!Array.isArray(result.list)) {
      process.stdout.write(JSON.stringify({ error: `no posting list returned${msg ? `: ${msg}` : ''}` }));
      return;
    }
    process.stdout.write(JSON.stringify({ posts: result.list }));
  } catch (err) {
    process.stdout.write(JSON.stringify({ error: String(err?.message || err) }));
  } finally {
    await browser.close();
  }
}

main();
