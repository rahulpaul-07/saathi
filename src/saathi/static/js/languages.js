// @ts-check
// Language picker data. The table lives on the server (languages.py); this only labels it.

/**
 * @typedef {{code: string, name: string, tier: string, native?: string,
 *   names?: Record<string, string>}} Language
 * `names` is this language's name in each viewer's script, keyed by the viewer's language code.
 */

/**
 * The name of a language for a reader: in the reader's script, then the English name in brackets
 * ("कन्नड़ (Kannada)"). An English reader, or a language with no name in the reader's script,
 * gets the English name alone.
 * @param {Language | undefined} language
 * @param {string} viewer the reader's language code
 * @param {string} fallback shown when the language is unknown
 */
export function nameForViewer(language, viewer, fallback) {
  if (!language) return fallback;
  const local = language.names?.[viewer];
  return local && local !== language.name ? `${local} (${language.name})` : language.name;
}

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
    const { code, name, tier, native, names } = item ?? {};
    if (typeof code !== "string" || typeof name !== "string" || typeof tier !== "string") {
      throw new Error("bad language entry");
    }
    return {
      code,
      name,
      tier,
      native: typeof native === "string" ? native : undefined,
      names: typeof names === "object" && names !== null ? names : undefined,
    };
  });
}
