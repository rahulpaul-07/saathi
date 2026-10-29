// @ts-check
// Turns the server's structured facts into chip view models. Pure. Chips come from the facts the
// extractor found in the source transcript, not from the translation, so they stay right when the
// translation is poor. Labels arrive in the reader's language from the server.

/**
 * @typedef {{kind: string, value: string, heard: string, confidence: string,
 *   ambiguous: boolean, reading: string | null, local?: string | null, label?: string,
 *   label_status?: string}} Fact
 * @typedef {{kind: string, label: string, value: string, note: string | null,
 *   labelPending: boolean, machineTranslated: boolean, original: string | null,
 *   changed: boolean}} Chip
 * `value` is the full text; `original` is the bracketed part of it, set only for a translated
 * landmark, so the screen can show it smaller.
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
 * For the listener (`forListener`) a landmark shows the machine translation in their language
 * followed by the original in brackets (street signs are in the local script). Without a usable
 * translation (missing, empty or identical) it shows the original alone.
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
      let machineTranslated = false;
      /** @type {string | null} */
      let original = null;
      if (forListener && fact.kind === "landmark") {
        const local = typeof fact.local === "string" ? fact.local.trim() : "";
        if (local !== "" && local !== fact.value) {
          value = `${local} (${fact.value})`;
          original = fact.value;
          machineTranslated = true;
        }
      }
      // The server names the class in the reader's language; the English table is the fallback.
      const label =
        typeof fact.label === "string" && fact.label !== "" ? fact.label : KIND_LABELS[fact.kind];
      return {
        kind: fact.kind,
        label,
        value,
        note,
        labelPending: fact.label_status === "pending",
        machineTranslated,
        original,
        changed: false,
      };
    })
    .sort((a, b) => KIND_ORDER.indexOf(a.kind) - KIND_ORDER.indexOf(b.kind));
}

/**
 * Chips for the pinned delivery card. An entry the latest customer turn replaced gets a "changed,
 * was X" note and `changed` set, so the old value stays visible next to the new one.
 * @param {unknown} entries `{fact, previous}` items from the server
 * @param {boolean} [forListener]
 * @returns {Chip[]}
 */
export function cardChips(entries, forListener = false) {
  if (!Array.isArray(entries)) return [];
  /** @type {Map<string, string>} */
  const previousByKind = new Map();
  for (const entry of entries) {
    const fact = entry?.fact;
    if (isFact(fact) && typeof entry.previous === "string" && entry.previous !== "") {
      previousByKind.set(fact.kind, entry.previous);
    }
  }
  return chipsFromFacts(
    entries.map((entry) => entry?.fact),
    forListener,
  ).map((chip) => {
    const previous = previousByKind.get(chip.kind);
    if (previous === undefined) return chip;
    const changedNote = `changed, was ${previous}`;
    return { ...chip, changed: true, note: chip.note ? `${chip.note}; ${changedNote}` : changedNote };
  });
}
