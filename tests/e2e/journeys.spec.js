// @ts-check
import { expect, test } from "@playwright/test";

import { makeUi } from "./chrome-text.js";

// Full customer and rider journeys against the journey server (tests/e2e/serve.py --journey): fake
// Gnani and a fake translator that writes the target script. Every language appears once as the
// customer and once as the rider. The pairs are examples; nothing ties a role to a language.
test.use({ baseURL: "http://127.0.0.1:8767" });

/** @type {[string, string][]} */
const PAIRS = [
  ["kn", "hi"],
  ["ta", "hi"],
  ["te", "en"],
  ["bn", "kn"],
  ["hi", "ta"],
  ["en", "ml"],
  ["gu", "mr"],
  ["pa", "gu"],
  ["ml", "pa"],
  ["mr", "bn"],
];
// Journeys run on a 360x780 touch phone for these indexes (every control tapped, not clicked).
const PHONE_JOURNEYS = new Set([0, 4, 7]);

/** Interface text from the server's table, as the pages see it. @type {Record<string, any>} */
let CHROME = {};
test.beforeAll(async ({ playwright }) => {
  const api = await playwright.request.newContext({ baseURL: "http://127.0.0.1:8767" });
  CHROME = (await (await api.get("/chrome")).json()).languages;
  ui = makeUi(CHROME);
  await api.dispose();
});
/** The text a viewer in `language` sees for `key`. */
let ui = makeUi({});
/** True when some string of `language` still has the review status "pending". */
const isUnreviewed = (/** @type {string} */ language) =>
  Object.values(CHROME[language]).some((entry) => entry.review_status === "pending");

/** @type {Record<string, RegExp>} */
const SCRIPT = {
  bn: /^[\p{Script=Bengali}\p{N}\s‌‍?:,.()-]+$/u,
  hi: /^[\p{Script=Devanagari}\p{N}\s‌‍?:,.()-]+$/u,
  mr: /^[\p{Script=Devanagari}\p{N}\s‌‍?:,.()-]+$/u,
  kn: /^[\p{Script=Kannada}\p{N}\s‌‍?:,.()-]+$/u,
  te: /^[\p{Script=Telugu}\p{N}\s‌‍?:,.()-]+$/u,
  gu: /^[\p{Script=Gujarati}\p{N}\s‌‍?:,.()-]+$/u,
  ml: /^[\p{Script=Malayalam}\p{N}\s‌‍?:,.()-]+$/u,
  pa: /^[\p{Script=Gurmukhi}\p{N}\s‌‍?:,.()-]+$/u,
  ta: /^[\p{Script=Tamil}\p{N}\s‌‍?:,.()-]+$/u,
  en: /^[\p{Script=Latin}\p{N}\s‌‍?:,.()-]+$/u,
};

/**
 * Console errors, page errors and CSP violations; any entry fails the journey. A CSP violation is
 * caught twice: as the browser's console message and as a securitypolicyviolation event.
 * @param {import("@playwright/test").Page} page
 */
async function watch(page) {
  /** @type {string[]} */
  const problems = [];
  page.on("console", (message) => {
    if (["error", "warning"].includes(message.type())) problems.push(message.text());
  });
  page.on("pageerror", (error) => problems.push(error.message));
  await page.addInitScript(() => {
    document.addEventListener("securitypolicyviolation", (event) => {
      console.error(`CSP violation: ${event.violatedDirective}`);
    });
  });
  return problems;
}

/** Failed fetches are logged by the browser as console errors; only those expected are dropped. */
const expected = (/** @type {string} */ text) => /ERR_FAILED|status of 404/.test(text);

/**
 * @param {import("@playwright/test").Browser} browser
 * @param {boolean} phone
 */
async function newPage(browser, phone) {
  const context = await browser.newContext(
    phone ? { viewport: { width: 360, height: 780 }, hasTouch: true, isMobile: true } : {},
  );
  await context.grantPermissions(["microphone"]);
  const page = await context.newPage();
  return { page, problems: await watch(page) };
}

/**
 * A tap on a phone, a click on a desktop.
 * @param {import("@playwright/test").Locator} locator
 * @param {boolean} phone
 */
async function press(locator, phone) {
  if (phone) await locator.tap();
  else await locator.click();
}

/**
 * @param {import("@playwright/test").Page} page
 * @param {string} language the speaker's language
 * @param {boolean} phone
 */
async function speak(page, language, phone) {
  await press(page.locator("#talk"), phone);
  await expect(page.locator("#status")).toHaveText(ui(language, "recording"));
  await page.waitForTimeout(1500); // let the fake microphone produce some audio
  await press(page.locator("#talk"), phone);
  await expect(page.locator("#status")).not.toHaveText(ui(language, "recording"));
}

/**
 * Every chip label on this screen is written in the viewer's own script.
 * @param {import("@playwright/test").Page} page
 * @param {string} language
 */
async function expectLabelsIn(page, language) {
  const main = language === "en" ? ".chip-label" : ".chip-label .l-main";
  const labels = await page.locator(`#card-chips ${main}`).allTextContents();
  expect(labels.length).toBeGreaterThan(0);
  for (const label of labels) expect(label.trim(), `label for ${language}`).toMatch(SCRIPT[language]);
  // The English second line sits under every label of a non-English page, and only there.
  const english = await page.locator("#card-chips .chip-label .l-en").count();
  expect(english).toBe(language === "en" ? 0 : labels.length);
}

/** @param {import("@playwright/test").Page} page @param {string} kind */
const chip = (page, kind) => page.locator(`#card-chips .chip-${kind}`);

for (const [index, [customerLanguage, riderLanguage]] of PAIRS.entries()) {
  const phone = PHONE_JOURNEYS.has(index);
  test(`journey ${customerLanguage} customer to ${riderLanguage} rider${phone ? " on a 360 px phone" : ""}`, async ({
    browser,
  }) => {
    const { page: customer, problems: customerProblems } = await newPage(browser, phone);
    const { page: rider, problems: riderProblems } = await newPage(browser, phone);

    // Create and join.
    await customer.goto("/customer.html");
    await customer.locator("#language").selectOption(customerLanguage);
    await press(customer.getByRole("button", { name: ui(customerLanguage, "create_room") }), phone);
    await expect(customer.locator("#code")).toHaveText(/^[A-Z0-9]{6}$/);
    const code = (await customer.locator("#code").textContent()) ?? "";
    await rider.goto(`/rider.html?code=${code}`);
    await rider.locator("#language").selectOption(riderLanguage);
    await press(rider.getByRole("button", { name: ui(riderLanguage, "join_and_sound") }), phone);
    await expect(customer.locator("#talk")).toBeEnabled();
    await expect(customer.locator("#peer")).toContainText(ui.has(customerLanguage, "rider_joined"));

    // Quick replies go both ways first; the customer's "From the rider" block stays hidden until a
    // spoken turn arrives. Texts come from the catalog, in the recipient's language.
    const catalog = await (await customer.request.get("/quick-replies")).json();
    const phrase = (/** @type {string} */ language, /** @type {string} */ id) =>
      catalog.languages[language][id].text;
    await expect(customer.locator("#incoming")).toBeHidden();
    await press(rider.getByRole("button", { name: phrase(riderLanguage, "which_floor") }), phone);
    await expect(customer.locator("#reply-text")).toHaveText(phrase(customerLanguage, "which_floor"));
    await expect(customer.locator("#incoming")).toBeHidden();
    await press(customer.getByRole("button", { name: phrase(customerLanguage, "come_to_gate") }), phone);
    await expect(rider.locator("#reply-text")).toHaveText(phrase(riderLanguage, "come_to_gate"));

    // Turn 1: the card appears on both screens in each viewer's own language.
    await speak(customer, customerLanguage, phone);
    for (const page of [customer, rider]) {
      await expect(chip(page, "gate").locator(".chip-value")).toHaveText("2");
      await expect(chip(page, "floor").locator(".chip-value")).toHaveText("3");
      await expect(page.locator("#card-chips .chip-changed")).toHaveCount(0);
    }
    await expectLabelsIn(customer, customerLanguage);
    await expectLabelsIn(rider, riderLanguage);
    // The speaker sees what was said; the listener sees the landmark in their own script.
    await expect(chip(customer, "landmark").locator(".chip-value")).toHaveText("blue temple");
    const listenerLandmark = (await chip(rider, "landmark").locator(".chip-value").textContent()) ?? "";
    // The listener's value is the local rendering, then the original in brackets.
    const localRendering = listenerLandmark.split(" (")[0].trim();
    expect(localRendering).toMatch(SCRIPT[riderLanguage]);
    if (riderLanguage !== "en") expect(listenerLandmark).toContain("(blue temple)");

    // Turn 2 changes the gate only: just that chip says "changed, was 2".
    await speak(customer, customerLanguage, phone);
    for (const page of [customer, rider]) {
      await expect(chip(page, "gate").locator(".chip-value")).toHaveText("4");
      const viewer = page === customer ? customerLanguage : riderLanguage;
      await expect(chip(page, "gate").locator(".chip-note")).toHaveText(ui.with(viewer, "changed_was", "2"));
      await expect(page.locator("#card-chips .chip-changed")).toHaveCount(1);
    }

    // Ask: the customer sees the question in their own language; the marker stays. The floor
    // handle is taken before the re-render below, as a finger already on it would hold it.
    await press(chip(rider, "gate").locator(".chip-ask"), phone);
    const question = chip(customer, "gate").locator(".chip-question");
    await expect(question).toHaveText(/\?$/);
    if (customerLanguage === "en") {
      await expect(question).toHaveText("Gate?"); // English pages draw one line
    } else {
      expect((await question.locator(".l-main").textContent())?.trim()).toMatch(SCRIPT[customerLanguage]);
      await expect(question.locator(".l-en")).toHaveText("Gate?");
    }
    await expect(chip(customer, "gate").locator(".chip-note")).toHaveText(
      ui.with(customerLanguage, "changed_was", "2"),
    );
    const floorAsk = await chip(rider, "floor").locator(".chip-ask").elementHandle();

    // Confirm: the marker and the question go, the customer sees a check.
    await press(chip(rider, "gate").locator(".chip-confirm"), phone);
    await expect(chip(customer, "gate").locator(".chip-note")).toHaveCount(0);
    await expect(chip(customer, "gate").locator(".chip-question")).toHaveCount(0);
    await expect(chip(customer, "gate").locator(".icon-check")).toHaveCount(1);
    await expect(rider.locator("#card-chips .chip-changed")).toHaveCount(0);
    expect(await floorAsk?.evaluate((el) => el.isConnected)).toBe(true);

    // A reload rejoins the room with the card and the confirmation intact.
    await rider.reload();
    await expect(rider.locator("#room")).toBeVisible();
    await expect(rider.locator("#peer")).toContainText(ui.has(riderLanguage, "customer_joined"));
    await expect(chip(rider, "gate").locator(".chip-value")).toHaveText("4");
    await expect(rider.locator("#card-chips .chip-changed")).toHaveCount(0);
    await expect(chip(rider, "gate")).toHaveClass(/chip-confirmed/);
    await expect(rider.locator("#translation")).not.toBeEmpty();
    await expectLabelsIn(rider, riderLanguage);

    // The stream drops: Reconnecting shows, then the page recovers by itself.
    await rider.route("**/events", (route) => route.abort());
    await rider.reload();
    await expect(rider.locator("#reconnecting")).toBeVisible();
    await rider.unroute("**/events");
    await expect(rider.locator("#reconnecting")).toBeHidden({ timeout: 15_000 });
    await expect(rider.locator("#peer")).toContainText(ui.has(riderLanguage, "customer_joined"));

    // End the room: the other side is told, the stored session is gone, the stream stops retrying.
    let eventRequests = 0;
    rider.on("request", (request) => {
      if (request.url().endsWith("/events")) eventRequests += 1;
    });
    await press(customer.getByRole("button", { name: ui(customerLanguage, "end_room") }), phone);
    await expect(rider.locator("#setup")).toBeVisible();
    await expect(rider.locator("#join-status")).toHaveText(ui(riderLanguage, "room_ended"));
    await expect(customer.locator("#setup")).toBeVisible();
    const afterEnd = eventRequests;
    await rider.waitForTimeout(3000);
    expect(eventRequests).toBe(afterEnd);
    await rider.reload();
    await expect(rider.locator("#setup")).toBeVisible();
    await expect(rider.locator("#join-status")).toHaveText("");

    expect([...customerProblems, ...riderProblems].filter((text) => !expected(text))).toEqual([]);
  });
}

// The split page is framed, which the policy allows only in demo mode, so this runs on the demo
// server, where a Punjabi speaker alternates gate 2 and gate 4.
const DEMO = "http://127.0.0.1:8766";

test("demo split page: the code is carried across, a turn shows on both frames, a changed gate is marked", async ({
  page,
}) => {
  const problems = await watch(page);
  await page.setViewportSize({ width: 1920, height: 1080 });
  await page.goto(`${DEMO}/demo.html`);
  const customer = page.frameLocator("#customer-frame");
  const rider = page.frameLocator("#rider-frame");
  await customer.locator("#language").selectOption("pa");
  await customer.getByRole("button", { name: ui("pa", "create_room") }).click();
  await expect(customer.locator("#code")).toHaveText(/^[A-Z0-9]{6}$/);
  const code = (await customer.locator("#code").textContent()) ?? "";
  await expect(rider.locator("#code-input")).toHaveValue(code);
  await rider.locator("#language").selectOption("hi");
  await expect(rider.locator("#join")).toBeEnabled();
  await rider.getByRole("button", { name: ui("hi", "join_and_sound") }).click();
  await expect(customer.locator("#peer")).toContainText(ui.has("pa", "rider_joined"));
  await expect(customer.locator("#talk")).toBeEnabled();

  for (const gate of ["2", "4"]) {
    await customer.locator("#talk").click();
    await expect(customer.locator("#status")).toHaveText(ui("pa", "recording"));
    await page.waitForTimeout(1500);
    await customer.locator("#talk").click();
    await expect(rider.locator("#card-chips .chip-gate .chip-value")).toHaveText(gate);
  }
  await expect(rider.locator("#card-chips .chip-gate .chip-note")).toHaveText(
    ui.with("hi", "changed_was", "2"),
  );
  await expect(customer.locator("#card-chips .chip-gate .chip-note")).toHaveText(
    ui.with("pa", "changed_was", "2"),
  );
  await expect(rider.locator("#card-chips .chip-floor .chip-changed")).toHaveCount(0);
  expect(problems.filter((text) => !expected(text))).toEqual([]);
});

/**
 * Words the page shows in Latin letters, apart from content the person or the translator made
 * (chip values, the room code and link), the language pickers, whose names are English labels, and
 * the English second line (`.l-en`) that sits under every string by design. The main line of every
 * string must still be free of English.
 * @param {import("@playwright/test").Page} page
 */
async function latinWordsOnScreen(page) {
  return page.evaluate(() => {
    const skip =
      "select, option, #code, #link, #translation, .chip-value, .chip-original, .l-en, script, style";
    const visible = (/** @type {Element} */ el) => el.getClientRects().length > 0;
    /** @type {string[]} */
    const found = [];
    const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
    for (let node = walker.nextNode(); node; node = walker.nextNode()) {
      const parent = node.parentElement;
      if (parent && visible(parent) && !parent.closest(skip)) {
        const words = (node.textContent ?? "").match(/[A-Za-z]{2,}/g) ?? [];
        // Name the element so a failure says where the English is.
        found.push(...words.map((word) => `${word} @${parent.id || parent.className}`));
      }
    }
    for (const el of document.querySelectorAll("[aria-label]")) {
      if (!visible(el) || el.closest("select")) continue;
      const words = (el.getAttribute("aria-label") ?? "").match(/[A-Za-z]{2,}/g) ?? [];
      found.push(...words.map((word) => `${word} @aria-label of ${el.id || el.className}`));
    }
    // "ms" is a unit symbol, not a word. An English language name in brackets after the name in
    // the viewer's script ("कन्नड़ (Kannada)") is the point of the peer line.
    const languageNames = ["Bengali", "English", "Hindi", "Kannada", "Telugu", "Gujarati",
      "Malayalam", "Marathi", "Punjabi", "Tamil"];
    return found.filter(
      (entry) => !entry.startsWith("ms @") && !languageNames.some((name) => entry === `${name} @l-main`),
    );
  });
}

// A page in Hindi or Kannada must not fall back to English anywhere the interface speaks, as the
// customer or as the rider. The roles and languages are examples; the check is the same for any pair.
for (const [customerLanguage, riderLanguage] of [
  ["hi", "kn"],
  ["kn", "hi"],
]) {
  // hi gained a hand-written, still unreviewed string (choose_a_clip), so both languages of the pair
  // now show the notice; the hidden case is covered by the English page test below.
  test(`${customerLanguage} customer and ${riderLanguage} rider pages show no English interface text`, async ({
    browser,
  }) => {
    const { page: customer, problems: customerProblems } = await newPage(browser, false);
    const { page: rider, problems: riderProblems } = await newPage(browser, false);
    await customer.goto("/customer.html");
    await customer.locator("#language").selectOption(customerLanguage);
    // The setup form already follows the picker.
    const create = customer.getByRole("button", { name: ui(customerLanguage, "create_room") });
    await expect(create).toBeVisible();
    expect(await latinWordsOnScreen(customer)).toEqual([]);
    await create.click();
    await expect(customer.locator("#code")).toHaveText(/^[A-Z0-9]{6}$/);
    const code = (await customer.locator("#code").textContent()) ?? "";
    await rider.goto(`/rider.html?code=${code}`);
    await rider.locator("#language").selectOption(riderLanguage);
    expect(await latinWordsOnScreen(rider)).toEqual([]);
    await rider.getByRole("button", { name: ui(riderLanguage, "join_and_sound") }).click();
    await expect(customer.locator("#peer")).toContainText(ui.has(customerLanguage, "rider_joined"));

    const viewers = /** @type {const} */ ([
      [customer, customerLanguage],
      [rider, riderLanguage],
    ]);
    for (const [page, language] of viewers) {
      await expect(page.locator("html")).toHaveAttribute("lang", language);
      // The machine-translation notice shows exactly for a language with unreviewed strings.
      const note = page.locator("#chrome-note");
      if (isUnreviewed(language)) await expect(note).toBeVisible();
      else await expect(note).toBeHidden();
      expect(await latinWordsOnScreen(page)).toEqual([]);
    }

    await speak(customer, customerLanguage, false);
    await expect(chip(rider, "gate").locator(".chip-value")).toHaveText("2");
    for (const [page] of viewers) expect(await latinWordsOnScreen(page)).toEqual([]);
    expect([...customerProblems, ...riderProblems].filter((text) => !expected(text))).toEqual([]);
  });
}

test("an English page needs no machine-translation notice and keeps English text", async ({ page }) => {
  await page.goto("/customer.html");
  await page.locator("#language").selectOption("en");
  await expect(page.locator("html")).toHaveAttribute("lang", "en");
  await expect(page.locator("#chrome-note")).toBeHidden();
  await expect(page.getByRole("button", { name: "Create room" })).toBeVisible();
});

/**
 * Bilingual check on one screen: every string the interface draws has a main line in the chosen
 * language and the English line under it; an English page has one line and no second line.
 * Returns the problems found.
 * @param {import("@playwright/test").Page} page
 * @param {string} language
 */
async function bilingualProblems(page, language) {
  return page.evaluate((lang) => {
    const visible = (/** @type {Element} */ el) => el.getClientRects().length > 0;
    /** @type {string[]} */
    const problems = [];
    const mains = [...document.querySelectorAll(".l-main")].filter(visible);
    const seconds = [...document.querySelectorAll(".l-en")].filter(visible);
    if (lang === "en") {
      if (mains.length || seconds.length) problems.push("English page has a second line");
    } else {
      if (!mains.length) problems.push("no main lines");
      for (const main of mains) {
        const second = main.nextElementSibling;
        const where = main.parentElement?.id || main.parentElement?.className || "?";
        if (!(main.textContent ?? "").trim()) problems.push(`empty main line @${where}`);
        if (!second?.classList.contains("l-en") || !(second.textContent ?? "").trim()) {
          problems.push(`missing English line @${where}`);
        }
      }
      for (const second of seconds) {
        if (!second.previousElementSibling?.classList.contains("l-main")) {
          problems.push(`English line without a main line @${second.parentElement?.id}`);
        }
      }
      // Translated elements that were never drawn bilingually.
      for (const el of document.querySelectorAll("[data-i18n]")) {
        if (!visible(el) || el.closest("option, select")) continue;
        if (!el.querySelector(".l-main")) problems.push(`not bilingual: ${el.getAttribute("data-i18n")}`);
      }
    }
    return problems;
  }, language);
}

/** Touch targets stay at least 44 px tall and wide, with two lines in a button. */
const TARGETS = "button, select, input:not([type=hidden]), a.button, summary";

/** @param {import("@playwright/test").Page} page */
async function smallTargets(page) {
  return page.evaluate((selector) => {
    return [...document.querySelectorAll(selector)]
      .filter((el) => el.getClientRects().length > 0)
      .map((el) => ({ el, box: el.getBoundingClientRect() }))
      .filter(({ box }) => box.height < 44 || box.width < 44)
      .map(({ el, box }) => `${el.id || el.textContent?.trim().slice(0, 20)} ${Math.round(box.width)}x${Math.round(box.height)}`);
  }, TARGETS);
}

for (const [customerLanguage, riderLanguage, seenByCustomer, riderNative, seenByRider] of [
  ["hi", "kn", "कन्नड़ (Kannada)", "ಕನ್ನಡ", "ಹಿಂದಿ (Hindi)"],
  ["en", "ta", "Tamil", "தமிழ்", "ஆங்கிலம் (English)"],
]) {
  test(`${customerLanguage} customer and ${riderLanguage} rider: every string has both lines, targets stay 44 px, the peer language is named in the viewer's script`, async ({
    browser,
  }) => {
    const { page: customer, problems: customerProblems } = await newPage(browser, true);
    const { page: rider, problems: riderProblems } = await newPage(browser, true);
    await customer.goto("/customer.html");
    await customer.locator("#language").selectOption(customerLanguage);
    const create = customer.getByRole("button", { name: ui(customerLanguage, "create_room") });
    await expect(create).toBeVisible();
    expect(await bilingualProblems(customer, customerLanguage)).toEqual([]);
    expect(await smallTargets(customer)).toEqual([]);
    await create.click();
    await expect(customer.locator("#code")).toHaveText(/^[A-Z0-9]{6}$/);
    const code = (await customer.locator("#code").textContent()) ?? "";
    await rider.goto(`/rider.html?code=${code}`);
    await rider.locator("#language").selectOption(riderLanguage);
    expect(await bilingualProblems(rider, riderLanguage)).toEqual([]);
    expect(await smallTargets(rider)).toEqual([]);
    await rider.getByRole("button", { name: ui(riderLanguage, "join_and_sound") }).click();
    await expect(customer.locator("#peer")).toContainText(ui.has(customerLanguage, "rider_joined"));

    // The other person's language: the viewer's script, then English; never the other's own script.
    await expect(customer.locator("#peer")).toContainText(seenByCustomer);
    expect((await customer.locator("#peer").textContent()) ?? "").not.toContain(riderNative);
    await expect(rider.locator("#peer")).toContainText(seenByRider);
    for (const [page, language] of /** @type {const} */ ([
      [customer, customerLanguage],
      [rider, riderLanguage],
    ])) {
      expect(await bilingualProblems(page, language)).toEqual([]);
      expect(await smallTargets(page)).toEqual([]);
    }
    expect([...customerProblems, ...riderProblems].filter((text) => !expected(text))).toEqual([]);
  });
}
