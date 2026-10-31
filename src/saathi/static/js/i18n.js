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

/**
 * A line of interface text in the viewer's language with its English twin. The page shows the
 * viewer's language as the main line and the English one smaller underneath; when the two are the
 * same (English pages, or a string with no translation) only one line is shown.
 */
export class Bi {
  /**
   * @param {string} local
   * @param {string} english
   */
  constructor(local, english) {
    this.local = local;
    this.english = english;
  }

  toString() {
    return this.local;
  }
}

/**
 * Like `t`, but keeps the English text so the page can show both.
 * @param {string} key
 * @param {string} fallback the English text for `key`
 */
export function tb(key, fallback) {
  return new Bi(t(key, fallback), fallback);
}

/** @param {Bi} text a message to carry across a page reload (the session notice) */
export function encodeBi(text) {
  return JSON.stringify({ local: text.local, english: text.english });
}

/**
 * @param {string} stored from `encodeBi`; anything else is shown as plain text
 * @returns {Bi}
 */
export function decodeBi(stored) {
  try {
    const value = JSON.parse(stored);
    if (typeof value?.local === "string" && typeof value?.english === "string") {
      return new Bi(value.local, value.english);
    }
  } catch {
    // Not encoded: fall through to plain text.
  }
  return new Bi(stored, stored);
}

/**
 * Template tag that joins text pieces in both languages at once:
 * bi`${tb("sent", "Sent")}: ${label}` gives local "Sent-in-kn: x" and English "Sent: x".
 * Plain values are used unchanged in both.
 * @param {TemplateStringsArray} strings
 * @param {...(string | number | Bi)} values
 */
export function bi(strings, ...values) {
  let local = strings[0];
  let english = strings[0];
  values.forEach((value, index) => {
    local += value instanceof Bi ? value.local : String(value);
    english += value instanceof Bi ? value.english : String(value);
    local += strings[index + 1];
    english += strings[index + 1];
  });
  return new Bi(local, english);
}

/**
 * Write text into an element: one line, or the viewer's language over a smaller English line.
 * The two lines are separate blocks with a space between, so textContent reads "local english".
 * @param {HTMLElement} el
 * @param {string | Bi} text
 */
export function renderText(el, text) {
  const { local, english } = typeof text === "string" ? new Bi(text, text) : text;
  if (local === english) {
    el.textContent = local;
    return;
  }
  const main = document.createElement("span");
  main.className = "l-main";
  main.textContent = local;
  const second = document.createElement("span");
  second.className = "l-en";
  second.lang = "en";
  second.textContent = english;
  el.replaceChildren(main, document.createTextNode(" "), second);
}

/** True when the page text in this language is machine output nobody has reviewed. */
export function isUnreviewed() {
  if (current === "en") return false;
  return Object.values(table[current] ?? {}).some((entry) => entry.review_status === "pending");
}

/**
 * Apply the current language to every marked element: data-i18n sets the text (local line over
 * the English line, see `renderText`), data-i18n-aria-label the accessible name, which stays in the
 * viewer's language. The English in the HTML is remembered on first use, so switching back
 * restores it. A <select> option cannot hold two blocks, so it reads "local / English".
 * @param {ParentNode} root
 */
export function applyChrome(root = document) {
  document.documentElement.lang = current;
  for (const el of root.querySelectorAll("[data-i18n]")) {
    const html = /** @type {HTMLElement} */ (el);
    html.dataset.en ??= html.textContent ?? "";
    const english = html.dataset.en;
    const text = tb(String(html.dataset.i18n), english);
    if (html instanceof HTMLOptionElement) {
      html.textContent = text.local === english ? english : `${text.local} / ${english}`;
    } else {
      renderText(html, text);
    }
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
