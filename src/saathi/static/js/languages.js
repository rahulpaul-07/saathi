// @ts-check
// Language picker data. The table lives on the server (languages.py); this only labels it.

/**
 * @typedef {{code: string, name: string, tier: string}} Language
 */

/** @type {Record<string, string>} */
const TIER_SUFFIX = { core: "", reviewed: " (reviewed)", beta: " (beta)" };

/**
 * @param {Language} language
 * @returns {string} e.g. "Tamil (beta)"; the verified core languages carry no suffix
 */
export function languageLabel(language) {
  return `${language.name}${TIER_SUFFIX[language.tier] ?? ""}`;
}

/**
 * @param {unknown} body parsed JSON from GET /languages
 * @returns {Language[]}
 */
export function parseLanguages(body) {
  if (!Array.isArray(body)) throw new Error("bad language list");
  return body.map((item) => {
    const { code, name, tier } = item ?? {};
    if (typeof code !== "string" || typeof name !== "string" || typeof tier !== "string") {
      throw new Error("bad language entry");
    }
    return { code, name, tier };
  });
}
