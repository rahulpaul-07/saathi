// @ts-check
// Small DOM helpers shared by the customer and rider screens. Received text is only ever set
// through textContent, never as HTML.
import { Bi, bi, renderText, t, tb } from "./i18n.js";
import { kindIcon } from "./kind-icons.js";
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
 * @param {string | Bi} text
 * @param {boolean} [isError]
 */
export function setStatus(el, text, isError = false) {
  renderText(el, text);
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
  // An <option> holds text only, so both lines go on one line.
  const choose = tb("choose_a_language", "Choose a language");
  placeholder.textContent =
    choose.local === choose.english ? choose.english : `${choose.local} / ${choose.english}`;
  placeholder.dataset.i18n = "choose_a_language";
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
 * @param {[string | Bi, string][]} rows
 */
export function renderRows(list, rows) {
  list.replaceChildren(
    ...rows.flatMap(([name, value]) => {
      const dt = document.createElement("dt");
      renderText(dt, name);
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
 * @param {[string | Bi, string][]} [extraRows]
 */
export function renderTimings(list, timings, extraRows = []) {
  const ms = (/** @type {number} */ value) => `${Math.round(value)} ms`;
  renderRows(list, [
    [tb("time_stt", "Speech to text"), ms(timings.stt_ms)],
    [tb("time_translate", "Translation"), ms(timings.translate_ms)],
    [tb("time_tts", "Text to speech"), ms(timings.tts_ms)],
    [tb("time_total", "Server total"), ms(timings.total_ms)],
    ...extraRows,
  ]);
}

/**
 * The whole turn on one line: "2.8 s: Speech to text 0.8, Translation 0.9, Text to speech 1.1".
 * @param {{stt_ms: number, translate_ms: number, tts_ms: number, total_ms: number}} timings
 */
export function timingsSummary(timings) {
  const s = (/** @type {number} */ value) => (value / 1000).toFixed(1);
  return bi`${s(timings.total_ms)} s: ${tb("time_stt", "Speech to text")} ${s(timings.stt_ms)}, ${tb("time_translate", "Translation")} ${s(timings.translate_ms)}, ${tb("time_tts", "Text to speech")} ${s(timings.tts_ms)}`;
}

/**
 * A check mark icon; the text alternative is the accessible name.
 * @param {string} name
 */
function checkIcon(name) {
  const svg = document.createElementNS("http://www.w3.org/2000/svg", "svg");
  svg.setAttribute("viewBox", "0 0 24 24");
  svg.setAttribute("class", "icon-check");
  svg.setAttribute("role", "img");
  svg.setAttribute("aria-label", name);
  const path = document.createElementNS("http://www.w3.org/2000/svg", "path");
  path.setAttribute("d", "M5 13l4 4L19 7");
  path.setAttribute("fill", "none");
  path.setAttribute("stroke", "currentColor");
  path.setAttribute("stroke-width", "3");
  path.setAttribute("stroke-linecap", "round");
  path.setAttribute("stroke-linejoin", "round");
  svg.append(path);
  return svg;
}

/** A question mark icon for the ask button; the button carries the accessible name. */
function askIcon() {
  const svg = document.createElementNS("http://www.w3.org/2000/svg", "svg");
  svg.setAttribute("viewBox", "0 0 24 24");
  svg.setAttribute("class", "icon-ask");
  svg.setAttribute("aria-hidden", "true");
  const path = document.createElementNS("http://www.w3.org/2000/svg", "path");
  path.setAttribute("d", "M9 9a3 3 0 1 1 4.5 2.6c-1 .6-1.5 1.1-1.5 2.4M12 17.5v.01");
  path.setAttribute("fill", "none");
  path.setAttribute("stroke", "currentColor");
  path.setAttribute("stroke-width", "2.5");
  path.setAttribute("stroke-linecap", "round");
  path.setAttribute("stroke-linejoin", "round");
  svg.append(path);
  return svg;
}

/**
 * Replace the chips in a live region (aria-live announces the change).
 * With `actions` (the listener's card) each chip gets a confirm icon button and an ask button that
 * reads the chip label plus "?"; without it a confirmed chip shows a check and an asked chip its
 * question.
 * @param {HTMLElement} container
 * @param {import("./chips.js").Chip[]} chips
 * @param {{confirm: (kind: string) => void, ask: (kind: string) => void}} [actions]
 */
export function renderChips(container, chips, actions) {
  // A chip that did not change keeps its element. Rebuilding every chip on each event destroys a
  // button the person is pressing (a tap whose target is removed before the finger lifts sends no
  // click), and the card is rebuilt by every card event, including the echo of the rider's own tap.
  const previous = rendered.get(container) ?? new Map();
  const next = new Map();
  const items = chips.map((chip) => {
    const signature = JSON.stringify([chip, actions !== undefined]);
    const kept = previous.get(chip.kind);
    const item = kept?.signature === signature ? kept.item : buildChip(chip, actions);
    next.set(chip.kind, { signature, item });
    return item;
  });
  rendered.set(container, next);
  const unchanged =
    container.childElementCount === items.length &&
    items.every((item, index) => container.children[index] === item);
  if (!unchanged) container.replaceChildren(...items);
}

/** @type {WeakMap<HTMLElement, Map<string, {signature: string, item: HTMLElement}>>} */
const rendered = new WeakMap();

/**
 * @param {import("./chips.js").Chip} chip
 * @param {{confirm: (kind: string) => void, ask: (kind: string) => void}} [actions]
 * @returns {HTMLElement}
 */
function buildChip(chip, actions) {
  const item = document.createElement("li");
  item.className = `chip chip-${chip.kind}${chip.note ? " chip-uncertain" : ""}${chip.changed ? " chip-changed" : ""}`;
  const label = document.createElement("span");
  label.className = "chip-label";
  renderText(label, new Bi(chip.label, chip.labelEn));
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
  item.append(kindIcon(chip.kind), label, value);
  if (chip.note) {
    const note = document.createElement("span");
    note.className = "chip-note";
    renderText(note, new Bi(chip.note, chip.noteEn ?? chip.note));
    item.append(note);
  }
  if (chip.confirmed) {
    item.classList.add("chip-confirmed");
    item.append(checkIcon(`${chip.label} ${t("confirmed", "confirmed")}`));
  }
  if (chip.question) {
    const question = document.createElement("span");
    question.className = "chip-question";
    // The server's question is the label plus "?", so its English twin is built the same way.
    renderText(question, new Bi(chip.question, `${chip.labelEn}?`));
    item.append(question);
  }
  if (actions) {
    const bar = document.createElement("span");
    bar.className = "chip-actions";
    const confirm = document.createElement("button");
    confirm.type = "button";
    confirm.className = "chip-confirm";
    confirm.setAttribute("aria-label", `${t("confirm", "Confirm")} ${chip.label}`);
    confirm.append(checkIcon(`${t("confirm", "Confirm")} ${chip.label}`));
    confirm.addEventListener("click", () => actions.confirm(chip.kind));
    const ask = document.createElement("button");
    ask.type = "button";
    ask.className = "chip-ask";
    ask.setAttribute("aria-label", `${chip.label}?`);
    ask.append(askIcon());
    ask.addEventListener("click", () => actions.ask(chip.kind));
    bar.append(confirm, ask);
    item.append(bar);
  }
  return item;
}
