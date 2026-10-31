// @ts-check
// The interface text a viewer sees, read from the server's /chrome table so specs do not hardcode
// translations. English is the source language of the table. A non-English viewer sees the
// chosen language first and the English text as a second line, so `ui` returns "local english"
// (the page's text content); `ui.main` and `ui.english` return the two lines; `ui.has` matches a
// line the page extends with more text ("The rider joined. Their language: ...").

/** @typedef {Record<string, Record<string, {text: string, review_status: string}>>} ChromeTable */

/** @param {string} text */
const escapeRegExp = (text) => text.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");

/** @param {ChromeTable} languages */
export function makeUi(languages) {
  const main = (/** @type {string} */ language, /** @type {string} */ key) =>
    languages[language][key].text;
  const english = (/** @type {string} */ key) => languages.en[key].text;
  const ui = (/** @type {string} */ language, /** @type {string} */ key) =>
    language === "en" ? english(key) : `${main(language, key)} ${english(key)}`;
  const has = (/** @type {string} */ language, /** @type {string} */ key) =>
    language === "en"
      ? new RegExp(escapeRegExp(english(key)))
      : new RegExp(`${escapeRegExp(main(language, key))}.*${escapeRegExp(english(key))}`, "s");
  // A note that ends in a value ("changed, was 2"): the value follows each line.
  const withValue = (
    /** @type {string} */ language,
    /** @type {string} */ key,
    /** @type {string} */ value,
  ) =>
    language === "en"
      ? `${english(key)} ${value}`
      : `${main(language, key)} ${value} ${english(key)} ${value}`;
  return Object.assign(ui, { main, english, has, with: withValue });
}

/**
 * @param {import("@playwright/test").PlaywrightWorkerArgs["playwright"]} playwright
 * @param {string} baseURL
 */
export async function loadUi(playwright, baseURL) {
  const api = await playwright.request.newContext({ baseURL });
  const languages = (await (await api.get("/chrome")).json()).languages;
  await api.dispose();
  return makeUi(languages);
}
