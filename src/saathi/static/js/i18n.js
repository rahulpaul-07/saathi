// @ts-check
// Interface text in the viewer's language. The server owns the table (GET /chrome, see
// saathi/chrome.py); this module only looks strings up and applies them to the page.
//
// Every lookup carries its English text, so the page still works, in English, when the table did
// not load. tests/test_chrome_wiring.py checks that each English fallback in the code and the
// HTML equals the source table, so the two cannot drift apart.

/** @typedef {Record<string, Record<string, {text: string, review_status: string}>>} ChromeTable */

/** @type {ChromeTable} */
let table = {};
let current = "en";

/** @param {unknown} body parsed JSON from GET /chrome */
export function setChromeTable(body) {
  const languages = /** @type {{languages?: unknown}} */ (body ?? {}).languages;
  table = typeof languages === "object" && languages !== null ? /** @type {ChromeTable} */ (languages) : {};
}

/** @param {string} code a language code; one the table lacks falls back to English */
export function setLanguage(code) {
  current = code in table ? code : "en";
}

export function currentLanguage() {
  return current;
}

/**
 * @param {string} key
 * @param {string} fallback the English text for `key`
 */
export function t(key, fallback) {
  if (current === "en") return fallback;
  return table[current]?.[key]?.text ?? fallback;
}

/** True when the page text in this language is machine output nobody has reviewed. */
export function isUnreviewed() {
  if (current === "en") return false;
  return Object.values(table[current] ?? {}).some((entry) => entry.review_status === "pending");
}

/**
 * Apply the current language to every marked element: data-i18n sets the text,
 * data-i18n-aria-label the accessible name. data-i18n-also-en shows the English after the local
 * text (the demo badge, so a bystander reading English still sees what it is). The English in the
 * HTML is remembered on first use, so switching back restores it.
 * @param {ParentNode} root
 */
export function applyChrome(root = document) {
  document.documentElement.lang = current;
  for (const el of root.querySelectorAll("[data-i18n]")) {
    const html = /** @type {HTMLElement} */ (el);
    html.dataset.en ??= html.textContent ?? "";
    const english = html.dataset.en;
    const local = t(String(html.dataset.i18n), english);
    html.textContent =
      html.hasAttribute("data-i18n-also-en") && local !== english ? `${local} / ${english}` : local;
  }
  for (const el of root.querySelectorAll("[data-i18n-aria-label]")) {
    const html = /** @type {HTMLElement} */ (el);
    html.dataset.enAria ??= html.getAttribute("aria-label") ?? "";
    html.setAttribute(
      "aria-label",
      t(String(html.dataset.i18nAriaLabel), html.dataset.enAria),
    );
  }
  const note = root.querySelector("#chrome-note");
  if (note instanceof HTMLElement) note.hidden = !isUnreviewed();
}
