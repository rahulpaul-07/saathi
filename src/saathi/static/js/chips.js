// @ts-check
// Turns the server's structured facts into chip view models. Pure. Chips come from the facts the
// extractor found in the source transcript, not from the translation, so they stay right when the
// translation is poor. English labels only; localized labels are an optional later step.

/**
 * @typedef {{kind: string, value: string, heard: string, confidence: string,
 *   ambiguous: boolean, reading: string | null, local?: string | null}} Fact
 * @typedef {{kind: string, label: string, value: string, note: string | null}} Chip
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
      return { kind: fact.kind, label: KIND_LABELS[fact.kind], value, note };
    })
    .sort((a, b) => KIND_ORDER.indexOf(a.kind) - KIND_ORDER.indexOf(b.kind));
}
