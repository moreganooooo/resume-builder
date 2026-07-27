// @ts-check
/** @typedef {import('./_types.js').Provider} Provider */

const USAJOBS_API_URL = 'https://data.usajobs.gov/api/Search';

function formatLocation(desc) {
  const loc = Array.isArray(desc.PositionLocation) ? desc.PositionLocation[0] : null;
  if (!loc) return '';
  return [loc.CityName, loc.CountrySubDivisionCode].filter(Boolean).join(', ');
}

/** @type {Provider} */
export default {
  id: 'usajobs',
  detect() {
    return null;
  },
  async fetch(entry, ctx) {
    const apiKey = process.env.USAJOBS_API_KEY;
    const email = process.env.USAJOBS_EMAIL;
    if (!apiKey || !email) {
      throw new Error('usajobs: missing USAJOBS_API_KEY / USAJOBS_EMAIL environment variables');
    }
    const headers = {
      Host: 'data.usajobs.gov',
      Accept: 'application/json',
      'Authorization-Key': apiKey,
      'User-Agent': email,
    };
    const params = new URLSearchParams({ Keyword: entry.search_term || '' });
    const url = `${USAJOBS_API_URL}?${params.toString()}`;
    const json = await ctx.fetchJson(url, { headers });
    const items = Array.isArray(json?.SearchResult?.SearchResultItems)
      ? json.SearchResult.SearchResultItems
      : [];
    return items
      .map((item) => item.MatchedObjectDescriptor)
      .filter((desc) => desc && desc.PositionURI && desc.PositionTitle)
      .map((desc) => ({
        title: desc.PositionTitle || '',
        url: desc.PositionURI,
        company: desc.OrganizationName || entry.name,
        location: formatLocation(desc),
        posted_at: desc.PublicationStartDate || '',
      }));
  },
};
