// @ts-check
// Split-screen demo page. Both frames are same-origin; nothing is sent but one read of the language list.
// - When the customer frame shows a room code, type it into the rider frame, so the recording does
//   not need a copy-paste step.
// - Name the language each person picked in their pane header, so the split reads as who speaks what.
// - Tell demo.css how tall the taller page is (--content-h), so on a tablet or a laptop the panes are
//   as tall as their content and not a fixed size. A phone ignores it and keeps the stacked layout.

import { nameForViewer, parseLanguages } from "./languages.js";
import { getJson } from "./room-client.js";

const POLL_MS = 500;

/** @param {string} id @returns {HTMLIFrameElement} */
function frame(id) {
  const element = document.getElementById(id);
  if (!(element instanceof HTMLIFrameElement)) throw new Error(`Missing frame #${id}`);
  return element;
}

const customer = frame("customer-frame");
const rider = frame("rider-frame");

/** @param {HTMLIFrameElement} f @param {string} id */
const inner = (f, id) => f.contentDocument?.getElementById(id) ?? null;

/**
 * The height of a frame's page. It is the body's height: that follows the content, where the document's
 * scrollHeight is never less than the frame's own height and so could not shrink again.
 * @param {HTMLIFrameElement} f
 */
const contentHeight = (f) => Math.ceil(f.contentDocument?.body?.getBoundingClientRect().height ?? 0);

let fitted = 0;
function fit() {
  const height = Math.max(contentHeight(customer), contentHeight(rider));
  // A frame that has not loaded yet is 0 tall; keep the stylesheet's default until there is a page.
  if (height === 0 || height === fitted) return;
  fitted = height;
  // A custom property set through the CSSOM is not an inline style attribute, so the CSP allows it.
  document.documentElement.style.setProperty("--content-h", `${height}px`);
}

/** Refit as soon as a page changes size, not only on the next tick. @param {HTMLIFrameElement} f */
function watch(f) {
  const win = /** @type {(Window & typeof globalThis) | null} */ (f.contentWindow);
  if (win?.document.body) new win.ResizeObserver(fit).observe(win.document.body);
  fit();
}

for (const f of [customer, rider]) {
  f.addEventListener("load", () => watch(f));
  // The frame may have finished loading before this module ran.
  if (f.contentDocument?.readyState === "complete") watch(f);
}

/** @type {import("./languages.js").Language[]} */
let languages = [];
try {
  languages = parseLanguages(await getJson("/languages"));
} catch {
  // Without the list the headers name no language; the two pages inside work on their own.
}

/**
 * Write the language a frame's person picked into that pane's header, in its own script with the
 * English name in brackets.
 * @param {HTMLIFrameElement} f
 * @param {string} outputId
 */
function showLanguage(f, outputId) {
  const output = document.getElementById(outputId);
  const select = /** @type {HTMLSelectElement | null} */ (inner(f, "language"));
  if (!output || !select) return;
  const language = languages.find((entry) => entry.code === select.value);
  output.textContent = language ? nameForViewer(language, language.code, language.name) : "";
  if (language) output.lang = language.code;
  else output.removeAttribute("lang");
}

setInterval(() => {
  fit();
  showLanguage(customer, "customer-lang");
  showLanguage(rider, "rider-lang");
  const code = inner(customer, "code")?.textContent?.trim() ?? "";
  // The element belongs to the frame's own window, so `instanceof HTMLInputElement` is false here.
  const input = /** @type {HTMLInputElement | null} */ (inner(rider, "code-input"));
  if (code && input?.tagName === "INPUT" && input.value !== code) {
    input.value = code;
    input.dispatchEvent(new Event("input", { bubbles: true }));
  }
}, POLL_MS);
