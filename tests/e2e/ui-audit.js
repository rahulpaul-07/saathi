// @ts-check
// Audits one rendered page of the interface in one language, from inside the browser, for the
// faults a translated interface can have that a text assertion does not see: a label that is empty,
// still English or a raw key, a line in the wrong script, a character the device has no glyph for
// (drawn as a box) and text cut off by its container. It measures what the browser drew at the size
// the page is in, so a page is audited once per viewport.
//
// The glyph check is a bitmap comparison, not `document.fonts.check`: that returns true for any
// text when the page declares no @font-face (this app ships none; the device supplies the fonts),
// so it cannot show a missing glyph. Here every non-ASCII character is drawn on a canvas in the
// element's own font and compared with a character no font has (U+10FFFF), which the browser draws
// as its "missing glyph" shape. Two controls guard the method: two different missing characters
// must draw the same, and a Latin letter must not. A script the device has no font for at all is
// reported as unavailable instead of failing every character of it, and then whether text fits its
// box is not judged for that page either: a stand-in font's widths say nothing about the real one
// (`fitJudged`). This tells whether each character has a glyph; it does not judge how a conjunct
// is shaped.

/**
 * The script each interface language is written in, by Unicode script name.
 * @type {Record<string, string>}
 */
export const SCRIPT = {
  bn: "Bengali",
  en: "Latin",
  gu: "Gujarati",
  hi: "Devanagari",
  kn: "Kannada",
  ml: "Malayalam",
  mr: "Devanagari",
  pa: "Gurmukhi",
  ta: "Tamil",
  te: "Telugu",
};

/**
 * The first consonant (KA) of each script, to find out whether the device has any font for it.
 * @type {Record<string, string>}
 */
const PROBE = {
  Bengali: "ক",
  Devanagari: "क",
  Gujarati: "ક",
  Gurmukhi: "ਕ",
  Kannada: "ಕ",
  Malayalam: "ക",
  Tamil: "க",
  Telugu: "క",
};

/** What was said or measured, not interface text: not held to the script and raw-key rules. */
const DATA = [
  "#translation",
  "#reply-text",
  "#transcript",
  "#code",
  "#link",
  "#code-input",
  ".chip-value",
  "#timings dd",
].join(", ");

/**
 * @typedef {object} Audit
 * @property {string[]} problems what is wrong, one line each
 * @property {{checked: number, unavailable: string[], controlsOk: boolean}} glyphs characters
 *   compared, scripts the device has no font for, and whether the method's controls held
 * @property {boolean} fitJudged false when the device has no font for a script on the page, so
 *   whether text fits its box was not judged (its width is a stand-in's)
 * @property {string[]} marked chosen options of a select that are wider than it and end in an
 *   ellipsis: cut, but not silently, so not a problem (empty when fit was not judged)
 * @property {number} webFonts fonts the page declares with a font-face rule (the app ships none)
 * @property {number} seen pieces of text looked at, so an audit of a blank page cannot pass
 */

/**
 * @param {import("@playwright/test").Page} page
 * @param {{lang: string, keys: string[], same: string[], names?: string[]}} input the page's
 *   interface language, every interface key, the keys whose text in this language is the English
 *   text (a term the language keeps, which the page shows once, so it has no local line to find),
 *   and the language names the page writes for this viewer ("कन्नड़ (Kannada)"): a value put into
 *   the line of both languages, so it is not held to the line's script
 * @returns {Promise<Audit>}
 */
export function auditPage(page, { lang, keys, same, names = [] }) {
  const input = { lang, script: SCRIPT[lang], probes: PROBE, keys, same, names, data: DATA };
  return page.evaluate(runAudit, input);
}

/**
 * Console errors and warnings (a CSP violation is one) and uncaught page errors, collected as they
 * happen. Any entry should fail the test.
 * @param {import("@playwright/test").Page} page
 * @returns {string[]}
 */
export function collectProblems(page) {
  /** @type {string[]} */
  const problems = [];
  page.on("console", (message) => {
    if (["error", "warning"].includes(message.type())) problems.push(message.text());
  });
  page.on("pageerror", (error) => problems.push(error.message));
  return problems;
}

/** @typedef {{el: Element, text: string, drawn: boolean}} Piece one piece of text on the page */

/**
 * Runs in the page. Playwright sends this function's source, so it can use nothing declared
 * outside it.
 * @param {{lang: string, script: string, probes: Record<string, string>, keys: string[],
 *   same: string[], names: string[], data: string}} input
 * @returns {Audit}
 */
function runAudit({ lang, script, probes, keys, same, names, data }) {
  /** @type {string[]} */
  const problems = [];
  const keySet = new Set(keys);
  const keptInEnglish = new Set(same);
  const probed = Object.entries(probes).map(([name, probe]) => ({
    name,
    probe,
    inScript: new RegExp(`\\p{Script=${name}}`, "u"),
  }));
  const english = lang === "en";
  const latin = /\p{Script=Latin}/gu;
  const letter = /\p{L}/u;
  const own = new RegExp(`\\p{Script=${script}}`, "gu");
  const ownOnce = new RegExp(`\\p{Script=${script}}`, "u");

  /** @param {Element} el */
  const describe = (el) => {
    const classes = typeof el.className === "string" ? el.className.trim().replace(/\s+/g, ".") : "";
    return `${el.tagName.toLowerCase()}${el.id ? `#${el.id}` : ""}${classes ? `.${classes}` : ""}`;
  };
  /** @param {Element} el */
  const shown = (el) =>
    el.getClientRects().length > 0 && getComputedStyle(el).visibility === "visible";
  /** @param {string} overflow */
  const cuts = (overflow) => overflow === "hidden" || overflow === "clip";

  // --- what is on the screen ---------------------------------------------------------------
  /** @type {Piece[]} */
  const pieces = [];
  const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
  for (let node = walker.nextNode(); node; node = walker.nextNode()) {
    const text = (node.textContent ?? "").trim();
    const el = node.parentElement;
    if (text && el && !el.closest("script, style, noscript, template") && shown(el)) {
      pieces.push({ el, text, drawn: true });
    }
  }
  // A closed <select> draws its chosen option only, but every option is text a person can read.
  for (const select of document.querySelectorAll("select")) {
    if (!shown(select)) continue;
    for (const option of select.options) {
      const text = (option.textContent ?? "").trim();
      if (text) pieces.push({ el: option, text, drawn: false });
      else problems.push(`${describe(select)}: an option with no text`);
    }
  }
  for (const el of document.querySelectorAll("[data-i18n-aria-label]")) {
    if (!shown(el)) continue;
    const text = (el.getAttribute("aria-label") ?? "").trim();
    if (text) pieces.push({ el, text, drawn: false });
    else problems.push(`${describe(el)}: empty aria-label`);
  }

  // --- labels: present, translated -----------------------------------------------------------
  for (const el of document.querySelectorAll("[data-i18n]")) {
    if (el instanceof HTMLOptionElement || !shown(el)) continue;
    const key = el.getAttribute("data-i18n") ?? "";
    if (!(el.textContent ?? "").trim()) problems.push(`${describe(el)}: empty label`);
    else if (!english && !keptInEnglish.has(key) && !el.querySelector(".l-main")) {
      problems.push(`${describe(el)}: English only, no ${lang} text ("${el.textContent?.trim()}")`);
    }
  }
  if (document.documentElement.lang !== lang) {
    problems.push(`<html lang> is "${document.documentElement.lang}", not "${lang}"`);
  }

  // --- each piece of text -------------------------------------------------------------------------
  for (const { el, text } of pieces) {
    const where = describe(el);
    if (/\b(?:undefined|null|NaN)\b|\[object |\{\{|\}\}|\$\{/.test(text)) {
      problems.push(`${where}: shows a placeholder or null ("${text}")`);
    }
    if (keySet.has(text) || text.split(/[^A-Za-z0-9_]+/).some((t) => t.includes("_") && keySet.has(t))) {
      problems.push(`${where}: shows a raw key ("${text}")`);
    }
    if (el.closest(data)) continue;
    const englishLine = english || el.closest(".l-en") !== null;
    // Letters of the viewer's script and Latin (a loanword, the brand) belong in a local line;
    // only Latin belongs in an English one. Any other letter is a string in the wrong script. A
    // language name is a value put into both lines, so it is taken out first.
    const bare = names.reduce((left, name) => left.split(name).join(" "), text);
    const rest = englishLine ? bare.replace(latin, "") : bare.replace(latin, "").replace(own, "");
    if (letter.test(rest)) {
      const stray = [...new Set([...rest].filter((ch) => letter.test(ch)))].join("");
      problems.push(`${where}: letters outside ${englishLine ? "Latin" : `${script} and Latin`}: ${stray} ("${text}")`);
    }
    if (el.classList.contains("l-main") && !ownOnce.test(text)) {
      problems.push(`${where}: local line has no ${script} ("${text}")`);
    }
    if (el instanceof HTMLOptionElement && el.hasAttribute("data-i18n") && !english) {
      if (!ownOnce.test(text.split(" / ")[0])) problems.push(`${where}: local part has no ${script} ("${text}")`);
    }
  }

  // --- text that does not fit ------------------------------------------------------------------
  // Measured with whatever font the device has; held back below when it has none for a script.
  /** @type {string[]} */
  const fit = [];
  const width = document.documentElement.clientWidth;
  if (document.documentElement.scrollWidth > width) fit.push("the page scrolls sideways");
  for (const { el, text, drawn } of pieces) {
    if (!drawn) continue;
    const box = el.getBoundingClientRect();
    if (box.width < 3 || box.height < 3) continue; // a visually hidden helper
    const where = describe(el);
    if (box.right > width + 1 || box.left < -1) fit.push(`${where}: runs off the side of the screen ("${text}")`);
    const style = getComputedStyle(el);
    if (cuts(style.overflowX) && el.scrollWidth > el.clientWidth + 1) {
      fit.push(`${where}: text wider than its box, cut off ("${text}")`);
    }
    if (cuts(style.overflowY) && el.scrollHeight > el.clientHeight + 1) {
      fit.push(`${where}: text taller than its box, cut off ("${text}")`);
    }
    for (let up = el.parentElement; up && up !== document.body; up = up.parentElement) {
      const parent = getComputedStyle(up);
      const frame = up.getBoundingClientRect();
      if (cuts(parent.overflowX) && (box.right > frame.right + 1 || box.left < frame.left - 1)) {
        fit.push(`${where}: cut off at the side by ${describe(up)} ("${text}")`);
      }
      if (cuts(parent.overflowY) && (box.bottom > frame.bottom + 1 || box.top < frame.top - 1)) {
        fit.push(`${where}: cut off at the bottom by ${describe(up)} ("${text}")`);
      }
    }
  }

  // A closed select shows its chosen option only; too wide, the browser cuts it at the control's
  // edge with no mark unless the control asks for an ellipsis.
  /** @type {string[]} */
  const marked = [];
  const measure = document.createElement("canvas").getContext("2d");
  for (const select of document.querySelectorAll("select")) {
    const chosen = select.selectedOptions[0]?.textContent?.trim();
    if (!chosen || !measure || !shown(select)) continue;
    const style = getComputedStyle(select);
    measure.font = `${style.fontWeight} ${style.fontSize} ${style.fontFamily}`;
    const room = select.clientWidth - parseFloat(style.paddingLeft) - parseFloat(style.paddingRight);
    if (measure.measureText(chosen).width <= room) continue;
    if (style.textOverflow === "ellipsis") marked.push(`${describe(select)} ("${chosen}")`);
    else fit.push(`${describe(select)}: chosen option wider than its select, cut off ("${chosen}")`);
  }

  // --- a glyph for every character ------------------------------------------------------------
  const glyphs = { checked: 0, unavailable: /** @type {string[]} */ ([]), controlsOk: true };
  const canvas = document.createElement("canvas");
  canvas.width = 96;
  canvas.height = 64;
  const ctx = canvas.getContext("2d", { willReadFrequently: true });
  const wanted = /[^\p{White_Space}\p{Cc}\p{Cf}\u0000-\u007f]/u;
  /** @type {Map<string, Set<string>>} */
  const byFont = new Map();
  for (const { el, text, drawn } of pieces) {
    if (!drawn) continue;
    const style = getComputedStyle(el);
    const font = `${style.fontWeight} 28px ${style.fontFamily}`;
    const chars = byFont.get(font) ?? new Set();
    for (const ch of text) if (wanted.test(ch)) chars.add(ch);
    byFont.set(font, chars);
  }
  if (!ctx) {
    glyphs.controlsOk = false;
  } else {
    // The dotted circle first, the way a shaper shows a combining mark on its own.
    /** @param {string} font @param {string} text */
    const ink = (font, text) => {
      ctx.clearRect(0, 0, canvas.width, canvas.height);
      ctx.font = font;
      ctx.fillText(`◌${text}`, 4, 44);
      const { data: pixels } = ctx.getImageData(0, 0, canvas.width, canvas.height);
      let signature = "";
      for (let i = 3; i < pixels.length; i += 4) signature += pixels[i] > 0 ? "1" : "0";
      return signature;
    };
    const unavailable = new Set();
    for (const [font, chars] of byFont) {
      // The reference has to be a visible shape that is the same for any character no font has and
      // unlike a letter; compared against anything else, "no glyph" would prove nothing.
      const missing = ink(font, "\u{10FFFF}");
      const trustworthy =
        missing === ink(font, "\u{10FFFE}") && missing !== ink(font, "A") && missing !== ink(font, "");
      if (!trustworthy) {
        glyphs.controlsOk = false;
        continue;
      }
      const noFont = new Set(
        probed.filter(({ probe }) => ink(font, probe) === missing).map(({ name }) => name),
      );
      for (const ch of chars) {
        const name = probed.find(({ inScript }) => inScript.test(ch))?.name;
        if (name && noFont.has(name)) {
          unavailable.add(name);
          continue;
        }
        glyphs.checked += 1;
        if (ink(font, ch) === missing) {
          const code = (ch.codePointAt(0) ?? 0).toString(16).toUpperCase().padStart(4, "0");
          problems.push(`no glyph for U+${code} (◌${ch}) on this device`);
        }
      }
    }
    glyphs.unavailable = [...unavailable].map(String);
  }

  // Text drawn in a stand-in box is the wrong width, so its fit says nothing about the real font.
  const fitJudged = glyphs.unavailable.length === 0;
  if (fitJudged) problems.push(...fit);

  return {
    problems: [...new Set(problems)],
    glyphs,
    fitJudged,
    marked: fitJudged ? [...new Set(marked)] : [],
    webFonts: document.fonts.size,
    seen: pieces.length,
  };
}
