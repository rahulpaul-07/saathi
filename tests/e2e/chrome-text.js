// @ts-check
// The interface text a viewer sees, read from the server's /chrome table so specs do not hardcode
// translations. English is the source language of the table.

/**
 * @param {import("@playwright/test").PlaywrightWorkerArgs["playwright"]} playwright
 * @param {string} baseURL
 * @returns {Promise<(language: string, key: string) => string>}
 */
export async function loadUi(playwright, baseURL) {
  const api = await playwright.request.newContext({ baseURL });
  const languages = (await (await api.get("/chrome")).json()).languages;
  await api.dispose();
  return (language, key) => languages[language][key].text;
}
