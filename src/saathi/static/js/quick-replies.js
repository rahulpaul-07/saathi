// @ts-check
// Which quick replies a person can send, and in what words. Pure.
// Each role has its own phrases. The sender reads each phrase in their own language (English when
// the table has none); the recipient hears it in theirs. If the recipient's language has no entry
// the server refuses, so the buttons are disabled with a reason instead.

/**
 * @typedef {{text: string, review_status: string}} Phrase
 * @typedef {{ids: Record<string, string[]>, languages: Record<string, Record<string, Phrase>>}} QuickReplyTable
 * @typedef {{enabled: boolean, reason: string | null, items: {id: string, label: string}[]}} QuickReplyOptions
 */

/**
 * @param {QuickReplyTable} table
 * @param {string} role the sender's role: "customer" or "rider"
 * @param {string} ownLanguage the sender's language
 * @param {string} peerLanguage the recipient's language
 * @returns {QuickReplyOptions}
 */
export function quickReplyOptions(table, role, ownLanguage, peerLanguage) {
  const own = table.languages[ownLanguage] ?? table.languages.en;
  const items = (table.ids[role] ?? []).map((id) => ({ id, label: own?.[id]?.text ?? id }));
  if (!(peerLanguage in table.languages)) {
    return {
      enabled: false,
      reason: "Quick replies are not available in the other person's language.",
      items,
    };
  }
  return { enabled: true, reason: null, items };
}

/**
 * @param {unknown} body parsed JSON from GET /quick-replies
 * @returns {QuickReplyTable}
 */
export function parseQuickReplyTable(body) {
  const value = /** @type {{ids?: unknown, languages?: unknown}} */ (body ?? {});
  const idsOk =
    typeof value.ids === "object" &&
    value.ids !== null &&
    Object.values(value.ids).every((list) => Array.isArray(list));
  if (!idsOk || typeof value.languages !== "object" || !value.languages) {
    throw new Error("bad quick reply table");
  }
  return /** @type {QuickReplyTable} */ (value);
}
