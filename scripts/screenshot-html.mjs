/**
 * screenshot-html.mjs — Renders an HTML file to a high-DPI PNG screenshot using Playwright.
 */
import { chromium } from 'playwright';
import path from 'path';
import { fileURLToPath } from 'url';

const args = process.argv.slice(2);
if (args.length < 2) {
  console.error('Usage: node screenshot-html.mjs <input.html> <output.png>');
  process.exit(1);
}

const inputHtml = path.resolve(args[0]);
const outputPng = path.resolve(args[1]);

async function run() {
  const browser = await chromium.launch({ headless: true });
  const context = await browser.newContext({
    deviceScaleFactor: 2, // Crisp retina resolution
  });
  const page = await context.newPage();
  await page.goto(`file://${inputHtml}`);
  
  // Wait for body to render
  const element = await page.$('body');
  if (element) {
    await element.screenshot({ path: outputPng });
    console.log(`[✓] Captured high-res PNG to ${outputPng}`);
  } else {
    await page.screenshot({ path: outputPng, fullPage: true });
    console.log(`[✓] Captured fullpage PNG to ${outputPng}`);
  }

  await browser.close();
}

run().catch((err) => {
  console.error('[!] Error capturing screenshot:', err);
  process.exit(1);
});
