// @ts-check
// Small DOM helpers shared by the customer and rider screens. Received text is only ever set
// through textContent, never as HTML.
import { languageLabel } from "./languages.js";

/**
 * @template {HTMLElement} T
 * @param {string} id
 * @param {new () => T} type
 * @returns {T}
 */
export function byId(id, type) {
  const element = document.getElementById(id);
  if (!(element instanceof type)) throw new Error(`Missing element #${id}`);
  return element;
}

/**
 * @param {HTMLElement} el
 * @param {string} text
 * @param {boolean} [isError]
 */
export function setStatus(el, text, isError = false) {
  el.textContent = text;
  el.classList.toggle("error", isError);
}

/**
 * Fill a picker with every language behind an empty, unselectable placeholder, so nothing is
 * chosen for the person: a language is never implied by their role.
 * @param {HTMLSelectElement} select
 * @param {import("./languages.js").Language[]} languages
 */
export function fillLanguageSelect(select, languages) {
  const placeholder = document.createElement("option");
  placeholder.value = "";
  placeholder.textContent = "Choose a language";
  placeholder.disabled = true;
  placeholder.selected = true;
  select.replaceChildren(
    placeholder,
    ...languages.map((language) => {
      const option = document.createElement("option");
      option.value = language.code;
      option.textContent = languageLabel(language);
      return option;
    }),
  );
}

/**
 * Keep `button` disabled until every picker has a language.
 * @param {HTMLSelectElement[]} selects
 * @param {HTMLButtonElement[]} buttons
 * @returns {() => void} re-run the check (after code that re-enables the buttons)
 */
export function requireChoice(selects, buttons) {
  const sync = () => {
    const missing = selects.some((select) => select.value === "");
    for (const button of buttons) button.disabled = missing;
  };
  for (const select of selects) select.addEventListener("change", sync);
  sync();
  return sync;
}

/**
 * Fill a description list with name/value rows.
 * @param {HTMLElement} list
 * @param {[string, string][]} rows
 */
export function renderRows(list, rows) {
  list.replaceChildren(
    ...rows.flatMap(([name, value]) => {
      const dt = document.createElement("dt");
      dt.textContent = name;
      const dd = document.createElement("dd");
      dd.textContent = value;
      return [dt, dd];
    }),
  );
}

/**
 * The per-stage durations of one turn, as the server measured them.
 * @param {HTMLElement} list
 * @param {{stt_ms: number, translate_ms: number, tts_ms: number, total_ms: number}} timings
 * @param {[string, string][]} [extraRows]
 */
export function renderTimings(list, timings, extraRows = []) {
  const ms = (/** @type {number} */ value) => `${Math.round(value)} ms`;
  renderRows(list, [
    ["Speech to text", ms(timings.stt_ms)],
    ["Translation", ms(timings.translate_ms)],
    ["Text to speech", ms(timings.tts_ms)],
    ["Server total", ms(timings.total_ms)],
    ...extraRows,
  ]);
}

/**
 * Replace the chips in a live region (aria-live announces the change).
 * @param {HTMLElement} container
 * @param {import("./chips.js").Chip[]} chips
 */
export function renderChips(container, chips) {
  container.replaceChildren(
    ...chips.map((chip) => {
      const item = document.createElement("li");
      item.className = `chip chip-${chip.kind}${chip.note ? " chip-uncertain" : ""}${chip.changed ? " chip-changed" : ""}`;
      const label = document.createElement("span");
      label.className = "chip-label";
      label.textContent = chip.label;
      const value = document.createElement("span");
      value.className = "chip-value";
      value.textContent = chip.value;
      if (chip.original !== null) {
        // Keep textContent equal to the full value; only the original is restyled.
        const bracket = ` (${chip.original})`;
        value.textContent = chip.value.slice(0, chip.value.length - bracket.length);
        const original = document.createElement("span");
        original.className = "chip-original";
        original.textContent = bracket;
        value.append(original);
      }
      item.append(label, value);
      if (chip.note) {
        const note = document.createElement("span");
        note.className = "chip-note";
        note.textContent = chip.note;
        item.append(note);
      }
      return item;
    }),
  );
}
