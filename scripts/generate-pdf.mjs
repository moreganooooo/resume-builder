#!/usr/bin/env node

/**
 * generate-pdf.mjs — HTML → PDF via Playwright
 *
 * Usage:
 *   node scripts/generate-pdf.mjs <input.html> <output.pdf> [--format=letter|a4]
 *
 * Requires: @playwright/test (or playwright) installed.
 * Uses Chromium headless to render the HTML and produce a clean, ATS-parseable PDF.
 */

import { chromium } from 'playwright';
import { resolve, dirname, join } from 'path';
import { readFile, writeFile, mkdtemp, rm } from 'fs/promises';
import { mkdirSync } from 'fs';
import { fileURLToPath } from 'url';
import { tmpdir } from 'os';

const __dirname = dirname(fileURLToPath(import.meta.url));

// Ensure output directory exists (fresh setup)
mkdirSync(resolve(__dirname, '../output'), { recursive: true });

// B45: this file's console output is printed verbatim by its Python callers
// (orchestrator.py, polish.py) rather than routed through theme.py's
// icon-set resolution, so it bypassed RESUME_BUILDER_ICONS entirely --
// same env var, same contract, just read directly here since there's no
// shared theming layer across the JS/Python boundary. Every glyph below is
// decorative next to an already-descriptive label, so the plain-Unicode
// fallback is simply to drop it rather than invent ASCII replacements.
const PLAIN_ICONS = process.env.RESUME_BUILDER_ICONS === 'unicode';
const ICON = {
  input: PLAIN_ICONS ? '' : '📄 ',
  output: PLAIN_ICONS ? '' : '📁 ',
  format: PLAIN_ICONS ? '' : '📏 ',
  cleanup: PLAIN_ICONS ? '' : '🧹 ',
  success: PLAIN_ICONS ? '' : '✅ ',
  pages: PLAIN_ICONS ? '' : '📊 ',
  size: PLAIN_ICONS ? '' : '📦 ',
  error: PLAIN_ICONS ? '' : '❌ ',
};

/**
 * Normalize text for ATS compatibility by converting problematic Unicode.
 *
 * ATS parsers and legacy systems often fail on em-dashes, smart quotes,
 * zero-width characters, and non-breaking spaces. These cause mojibake,
 * parsing errors, or display issues. See issue #1.
 *
 * Only touches body text — preserves CSS, JS, tag attributes, and URLs.
 * Returns { html, replacements } so the caller can log what was changed.
 */
function normalizeTextForATS(html) {
  const replacements = {};
  const bump = (key, n) => { replacements[key] = (replacements[key] || 0) + n; };

  const masks = [];
  const masked = html.replace(
    /<(style|script)\b[^>]*>[\s\S]*?<\/\1>/gi,
    (match) => {
      const token = `\u0000MASK${masks.length}\u0000`;
      masks.push(match);
      return token;
    }
  );

  let out = '';
  let i = 0;
  while (i < masked.length) {
    const lt = masked.indexOf('<', i);
    if (lt === -1) { out += sanitizeText(masked.slice(i)); break; }
    out += sanitizeText(masked.slice(i, lt));
    const gt = masked.indexOf('>', lt);
    if (gt === -1) { out += masked.slice(lt); break; }
    out += masked.slice(lt, gt + 1);
    i = gt + 1;
  }

  const restored = out.replace(/\u0000MASK(\d+)\u0000/g, (_, n) => masks[Number(n)]);
  return { html: restored, replacements };

  function sanitizeText(text) {
    if (!text) return text;
    let t = text;
    t = t.replace(/\u2014/g, () => { bump('em-dash', 1); return '-'; });
    t = t.replace(/\u2013/g, () => { bump('en-dash', 1); return '-'; });
    t = t.replace(/[\u201C\u201D\u201E\u201F]/g, () => { bump('smart-double-quote', 1); return '"'; });
    t = t.replace(/[\u2018\u2019\u201A\u201B]/g, () => { bump('smart-single-quote', 1); return "'"; });
    t = t.replace(/\u2026/g, () => { bump('ellipsis', 1); return '...'; });
    t = t.replace(/[\u200B\u200C\u200D\u2060\uFEFF]/g, () => { bump('zero-width', 1); return ''; });
    t = t.replace(/\u00A0/g, () => { bump('nbsp', 1); return ' '; });
    // Arrows often stripped by PDF text extractors — replace with ASCII for ATS safety.
    // Consume surrounding whitespace to avoid double-spacing in output.
    t = t.replace(/\s*\u2192\s*/g, () => { bump('right-arrow', 1); return ' to '; });
    t = t.replace(/\s*\u2190\s*/g, () => { bump('left-arrow', 1); return ' from '; });
    t = t.replace(/\s*[\u2191\u2193]\s*/g, () => { bump('vert-arrow', 1); return ' '; });
    // Middle dot and bullet glyphs garble in some extractors — replace with pipe.
    t = t.replace(/\s*\u00B7\s*/g, () => { bump('middot', 1); return ' | '; });
    t = t.replace(/\s*\u2022\s*/g, () => { bump('bullet', 1); return ' | '; });
    // Currency symbols sometimes stripped by font-subsetted PDFs — spell out
    // the unambiguous ones. \u00A5 is intentionally NOT converted: it maps to both
    // Japanese Yen (JPY) and Chinese Yuan (CNY), so any spelled-out code would be
    // wrong for half of users — better to leave the glyph than emit bad data.
    t = t.replace(/\u20AC/g, () => { bump('euro', 1); return 'EUR '; });
    t = t.replace(/\u00A3/g, () => { bump('pound', 1); return 'GBP '; });
    return t;
  }
}

async function generatePDF() {
  const args = process.argv.slice(2);

  // Parse arguments
  let inputPath, outputPath, format = 'a4';

  for (const arg of args) {
    if (arg.startsWith('--format=')) {
      format = arg.split('=')[1].toLowerCase();
    } else if (!inputPath) {
      inputPath = arg;
    } else if (!outputPath) {
      outputPath = arg;
    }
  }

  if (!inputPath || !outputPath) {
    console.error('Usage: node generate-pdf.mjs <input.html> <output.pdf> [--format=letter|a4]');
    process.exit(1);
  }

  inputPath = resolve(inputPath);
  outputPath = resolve(outputPath);

  // Validate format
  const validFormats = ['a4', 'letter'];
  if (!validFormats.includes(format)) {
    console.error(`Invalid format "${format}". Use: ${validFormats.join(', ')}`);
    process.exit(1);
  }

  console.log(`${ICON.input}Input:  ${inputPath}`);
  console.log(`${ICON.output}Output: ${outputPath}`);
  console.log(`${ICON.format}Format: ${format.toUpperCase()}`);

  // Read HTML to inject font paths as absolute file:// URLs
  let html = await readFile(inputPath, 'utf-8');

  // BUG 2 FIX: fonts live in resume-engine/fonts/, not fonts/ at the repo root.
  // The old path '../fonts' resolved to resume-builder/fonts/ which doesn't exist,
  // causing Playwright to silently fall back to system fonts for every PDF render.
  const fontsDir = resolve(__dirname, '../resume-engine/fonts');
  html = html.replace(
    /url\(['"]?\.\/fonts\//g,
    `url('file://${fontsDir}/`
  );
  // Close any unclosed quotes from the replacement (handles all font formats)
  html = html.replace(
    /file:\/\/([^'")]+)\.(woff2?|ttf|otf)['"]?\)/g,
    `file://$1.$2')`
  );

  // Normalize text for ATS compatibility (issue #1)
  const normalized = normalizeTextForATS(html);
  html = normalized.html;
  const totalReplacements = Object.values(normalized.replacements).reduce((a, b) => a + b, 0);
  if (totalReplacements > 0) {
    const breakdown = Object.entries(normalized.replacements).map(([k, v]) => `${k}=${v}`).join(', ');
    console.log(`${ICON.cleanup}ATS normalization: ${totalReplacements} replacements (${breakdown})`);
  }

  // page.setContent() + baseURL resolves relative file:// URLs correctly,
  // but does NOT grant the page file:// fetch privileges -- only an actual
  // navigation to a file:// URL does. Every @font-face load was silently
  // failing ("Not allowed to load local resource") under setContent(), with
  // no visible error in the PDF output. This machine happened to mask it
  // for DM Serif Display (also installed as a real system font here), but
  // DM Sans isn't, so every resume was silently falling back to
  // Chromium's generic sans-serif (Helvetica) instead of the real font --
  // exactly the "looks different on someone else's machine" failure mode
  // this pipeline exists to avoid. Writing the transformed HTML to a real
  // temp file and navigating to it with page.goto('file://...') gives the
  // page genuine file:// origin privileges, so local font/image fetches
  // from the same directory actually succeed.
  const tmpDir = await mkdtemp(join(tmpdir(), 'resume-pdf-'));
  const tmpHtmlPath = join(tmpDir, 'resume.html');
  await writeFile(tmpHtmlPath, html, 'utf-8');

  const browser = await chromium.launch({ headless: true });
  try {
    const page = await browser.newPage();

    await page.goto(`file://${tmpHtmlPath}`, { waitUntil: 'networkidle' });

    // Wait for fonts to load. document.fonts.ready has no default timeout of
    // its own -- a font that never settles hung this call forever, with the
    // Python side's capture_output=True swallowing every hint (P4F8). Race
    // it against a real ceiling instead.
    await Promise.race([
      page.evaluate(() => document.fonts.ready),
      new Promise((_, reject) => setTimeout(
        () => reject(new Error('Timed out waiting for document.fonts.ready after 15s')),
        15000
      )),
    ]);

    // Generate PDF
    const pdfBuffer = await page.pdf({
      format: format,
      printBackground: true,
      margin: {
        top: '0.5in',
        right: '0.5in',
        bottom: '0.5in',
        left: '0.5in',
      },
      preferCSSPageSize: false,
    });

    // Write PDF
    await writeFile(outputPath, pdfBuffer);

    // Count pages (approximate from PDF structure)
    const pdfString = pdfBuffer.toString('latin1');
    const pageCount = (pdfString.match(/\/Type\s*\/Page[^s]/g) || []).length;

    console.log(`${ICON.success}PDF generated: ${outputPath}`);
    console.log(`${ICON.pages}Pages: ${pageCount}`);
    console.log(`${ICON.size}Size: ${(pdfBuffer.length / 1024).toFixed(1)} KB`);

    return { outputPath, pageCount, size: pdfBuffer.length };
  } finally {
    await browser.close();
    await rm(tmpDir, { recursive: true, force: true });
  }
}

generatePDF().catch((err) => {
  console.error(`${ICON.error}PDF generation failed:`, err.message);
  process.exit(1);
});
