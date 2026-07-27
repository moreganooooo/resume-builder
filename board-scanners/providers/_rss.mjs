// @ts-check
//
// Minimal regex-based RSS/XML parsing helpers — no XML library dependency,
// matching the zero-dependency philosophy of providers/_http.mjs. Handles
// the small, predictable subset of RSS that job-board feeds actually use:
// <item> blocks, CDATA-wrapped tag content, and a handful of HTML entities.

const ITEM_RE = /<item\b[\s\S]*?<\/item>/gi;
const TAG_CACHE = new Map();

const ENTITIES = {
  amp: '&',
  lt: '<',
  gt: '>',
  quot: '"',
  apos: "'",
  '#39': "'",
  nbsp: ' ',
};

function tagRegex(tagName) {
  let re = TAG_CACHE.get(tagName);
  if (!re) {
    re = new RegExp(`<${tagName}\\b[^>]*>([\\s\\S]*?)<\\/${tagName}>`, 'i');
    TAG_CACHE.set(tagName, re);
  }
  return re;
}

/**
 * Split a raw RSS/XML document into individual `<item>...</item>` blocks.
 * @param {string} xml
 * @returns {string[]}
 */
export function splitItems(xml) {
  if (!xml) return [];
  return xml.match(ITEM_RE) || [];
}

/**
 * Decode the small set of HTML/XML entities that show up in RSS feed text
 * (named entities plus numeric `&#NNN;` / `&#xHH;` references).
 * @param {string} text
 * @returns {string}
 */
export function decodeEntities(text) {
  if (!text) return text;
  return text.replace(/&(#?\w+);/g, (full, entity) => {
    if (entity[0] === '#') {
      const isHex = entity[1] === 'x' || entity[1] === 'X';
      const code = isHex ? parseInt(entity.slice(2), 16) : parseInt(entity.slice(1), 10);
      return Number.isNaN(code) ? full : String.fromCharCode(code);
    }
    return Object.prototype.hasOwnProperty.call(ENTITIES, entity) ? ENTITIES[entity] : full;
  });
}

/**
 * Extract the text content of a tag from an `<item>` block, unwrapping
 * CDATA sections and decoding entities.
 * @param {string} item
 * @param {string} tagName
 * @returns {string|null}
 */
export function extractTag(item, tagName) {
  const match = item.match(tagRegex(tagName));
  if (!match) return null;
  let value = match[1].trim();
  const cdata = value.match(/^<!\[CDATA\[([\s\S]*?)\]\]>$/);
  if (cdata) value = cdata[1].trim();
  return decodeEntities(value);
}
