// @ts-check
// Turns the server's structured facts into chip view models. Pure. Chips come from the facts the
// extractor found in the source transcript, not from the translation, so they stay right when the
// translation is poor. Labels arrive in the reader's language from the server.

/**
 * @typedef {{kind: string, value: string, heard: string, confidence: string,
 *   ambiguous: boolean, reading: string | null, local?: string | null, label?: string,
 *   label_status?: string}} Fact
 * @typedef {{kind: string, label: string, value: string, note: string | null,
 *   labelPending: boolean}} Chip
 */

const KIND_ORDER = ["gate", "floor", "cross", "main", "block", "flat", "landmark"];
/** @type {Record<string, string>} */
const KIND_LABELS = {
  gate: "Gate",
  floor: "Floor",
  cross: "Cross",
  main: "Main",
  block: "Block",
  flat: "Flat",
  landmark: "Landmark",
};

/**
 * @param {unknown} value
 * @returns {value is Fact}
 */
function isFact(value) {
  if (typeof value !== "object" || value === null) return false;
  const fact = /** @type {Record<string, unknown>} */ (value);
  return (
    typeof fact.kind === "string" &&
    typeof fact.value === "string" &&
    fact.value !== "" &&
    typeof fact.confidence === "string" &&
    typeof fact.ambiguous === "boolean"
  );
}

/**
 * Ordered chips for display. Unknown kinds and malformed entries are skipped. An ambiguous fact
 * shows what was heard with its best reading as a note; a low-confidence one asks to be checked.
 * For the listener (`forListener`) a landmark shows its name in their language, or the class
 * alone when the server found no plausible rendering: the speaker's script would be unreadable.
 * @param {unknown} facts
 * @param {boolean} [forListener]
 * @returns {Chip[]}
 */
export function chipsFromFacts(facts, forListener = false) {
  if (!Array.isArray(facts)) return [];
  return facts
    .filter(isFact)
    .filter((fact) => fact.kind in KIND_LABELS)
    .map((fact) => {
      /** @type {string | null} */
      let note = null;
      if (fact.ambiguous && fact.reading) note = `could be ${fact.reading}`;
      else if (fact.confidence === "low") note = "check this";
      let value = fact.value;
      if (forListener && fact.kind === "landmark") {
        value = typeof fact.local === "string" ? fact.local : "";
        if (value === "") note = "name not available";
      }
      // The server names the class in the reader's language; the English table is the fallback.
      const label =
        typeof fact.label === "string" && fact.label !== "" ? fact.label : KIND_LABELS[fact.kind];
      return { kind: fact.kind, label, value, note, labelPending: fact.label_status === "pending" };
    })
    .sort((a, b) => KIND_ORDER.indexOf(a.kind) - KIND_ORDER.indexOf(b.kind));
}
