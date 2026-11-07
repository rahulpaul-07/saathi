// @ts-check
// Every interface language, as the customer and as the rider, on a phone and on a laptop, against
// the demo server (fake speech and translation: this is about what the screens show, not about the
// models). Each scenario walks both screens through the states a person meets - before the room,
// room open, rider joined, a clip sent and received - and audits each one in the browser
// (ui-audit.js): labels present and in the right script, no raw key or "undefined", a glyph for
// every character the device can draw, and no text cut off by its box.
//
// The customer is the language at position i and the rider the next one in the list, so each of the
// ten languages is the customer once and the rider once per screen size (the demo server offers a
// clip only in the customer's own language).
import { expect, test } from "@playwright/test";
import { nameForViewer, parseLanguages } from "../../src/saathi/static/js/languages.js";
import { loadUi, makeUi } from "./chrome-text.js";
import { SCRIPT, auditPage, collectProblems } from "./ui-audit.js";

const DEMO = "http://127.0.0.1:8766"; // tests/e2e/serve.py --demo

const SCREENS = [
  { name: "phone", viewport: { width: 412, height: 915 } },
  { name: "laptop", viewport: { width: 1280, height: 800 } },
];
const LANGUAGES = Object.keys(SCRIPT);
// A page with less text than this has not rendered, whatever the audit found.
const LEAST_TEXTS = 8;

/** @typedef {import("@playwright/test").Page} Page */

/** @type {ReturnType<typeof makeUi>} */
let ui = makeUi({});
/** @type {ReturnType<typeof parseLanguages>} */
let offered = [];
test.beforeAll(async ({ playwright }) => {
  ui = await loadUi(playwright, DEMO);
  const api = await playwright.request.newContext({ baseURL: DEMO });
  offered = parseLanguages(await (await api.get("/languages")).json());
  await api.dispose();
});

/**
 * The language names the page writes for a viewer, composed by the app's own function.
 * @param {string} viewer
 */
const namesFor = (viewer) =>
  offered.map((language) => nameForViewer(language, viewer, language.name));

/**
 * Audits what a viewer sees now. Soft: a scenario reports every faulty screen, not only the first.
 * @param {Page} page
 * @param {string} lang the viewer's language
 * @param {string} state a name for the screen, for the failure message
 */
async function audit(page, lang, state) {
  await page.evaluate(() => {
    for (const details of document.querySelectorAll("details")) details.open = true;
  });
  const same = lang === "en" ? [] : ui.keys.filter((key) => ui.main(lang, key) === ui.english(key));
  const result = await auditPage(page, { lang, keys: ui.keys, same, names: namesFor(lang) });
  expect.soft(result.seen, `${state}: almost nothing on screen to audit`).toBeGreaterThan(LEAST_TEXTS);
  expect
    .soft(result.glyphs.controlsOk, `${state}: the missing-glyph reference cannot be trusted`)
    .toBe(true);
  expect.soft(result.problems, state).toEqual([]);
  return result;
}

for (const { name, viewport } of SCREENS) {
  LANGUAGES.forEach((customerLang, index) => {
    const riderLang = LANGUAGES[(index + 1) % LANGUAGES.length];

    test(`${name}: ${customerLang} customer and ${riderLang} rider, every screen`, async ({
      browser,
    }) => {
      const customerContext = await browser.newContext({ viewport });
      const riderContext = await browser.newContext({ viewport });
      try {
        const customer = await customerContext.newPage();
        const rider = await riderContext.newPage();
        const problems = [collectProblems(customer), collectProblems(rider)];
        const audits = [];

        await customer.goto(`${DEMO}/customer.html`);
        await expect(customer.locator(`#language option[value="${customerLang}"]`)).toHaveCount(1);
        await customer.locator("#language").selectOption(customerLang);
        const create = customer.getByRole("button", { name: ui(customerLang, "create_room") });
        await expect(create).toBeVisible();
        audits.push(await audit(customer, customerLang, "customer before the room"));

        await create.click();
        await expect(customer.locator("#demo-banner")).toBeVisible();
        await expect(customer.locator("#code")).toHaveText(/^[A-Z0-9]{6}$/);
        const code = (await customer.locator("#code").textContent()) ?? "";
        audits.push(await audit(customer, customerLang, "customer with the room open"));

        await rider.goto(`${DEMO}/rider.html?code=${code}`);
        await expect(rider.locator(`#language option[value="${riderLang}"]`)).toHaveCount(1);
        await rider.locator("#language").selectOption(riderLang);
        const join = rider.getByRole("button", { name: ui(riderLang, "join_and_sound") });
        await expect(join).toBeVisible();
        audits.push(await audit(rider, riderLang, "rider before joining"));

        await join.click();
        await expect(rider.locator("#room")).toBeVisible();
        await expect(customer.locator("#peer")).toContainText(ui.has(customerLang, "rider_joined"));
        audits.push(await audit(customer, customerLang, "customer with the rider joined"));
        audits.push(await audit(rider, riderLang, "rider joined, nothing said yet"));

        await customer.locator("#demo-clip").selectOption(`clip-${customerLang}`);
        await customer.locator("#demo-send").click();
        await expect(rider.locator("#demo-badge")).toBeVisible();
        await expect(rider.locator("#translation")).toHaveText(/\S/);
        await expect(customer.locator("#sent-demo-badge")).toBeVisible();
        audits.push(await audit(customer, customerLang, "customer after sending a clip"));
        audits.push(await audit(rider, riderLang, "rider with the delivery card"));

        expect(problems.flat(), "console errors, warnings and page errors").toEqual([]);

        // One line per scenario, so a run shows what was and was not checked on this device.
        const glyphs = audits.reduce((sum, one) => sum + one.glyphs.checked, 0);
        const withoutFont = [...new Set(audits.flatMap((one) => one.glyphs.unavailable))];
        const fitJudged = audits.every((one) => one.fitJudged);
        const marked = [...new Set(audits.flatMap((one) => one.marked))];
        console.log(
          `languages ${name} ${customerLang}->${riderLang}: ${audits.length} screens, ` +
            `${audits.reduce((sum, one) => sum + one.seen, 0)} texts, ${glyphs} glyphs compared, ` +
            `no device font for: ${withoutFont.join(", ") || "none"}, ` +
            `fit judged: ${fitJudged}, cut with an ellipsis: ${marked.join("; ") || "none"}, ` +
            `web fonts declared: ${Math.max(...audits.map((one) => one.webFonts))}`,
        );
      } finally {
        await customerContext.close();
        await riderContext.close();
      }
    });
  });
}

test("every language the server offers is audited, with every interface string and a name in every script", () => {
  expect(offered.map((language) => language.code).sort()).toEqual([...LANGUAGES].sort());
  for (const lang of LANGUAGES) {
    for (const key of ui.keys) {
      expect.soft(ui.main(lang, key).trim(), `${lang} ${key}`).not.toBe("");
    }
  }
  // The audit leaves a language name out of its script check (the page puts it into the line of
  // both languages), so the names are checked here instead: each is written in the viewer's script.
  for (const viewer of LANGUAGES) {
    const inScript = new RegExp(`\\p{Script=${SCRIPT[viewer]}}`, "u");
    for (const language of offered) {
      const name = language.names?.[viewer] ?? "";
      expect
        .soft(inScript.test(name), `${language.code} named for a ${viewer} viewer: "${name}"`)
        .toBe(true);
    }
  }
});

test("the language picker and the clip picker end an option that is too wide in an ellipsis", async ({
  page,
}) => {
  // Whatever fonts a device has: an option wider than a select (the Tamil "Choose a clip" on a
  // phone) must not be cut with no sign.
  await page.goto(`${DEMO}/customer.html`);
  await page.locator("#language").selectOption("ta");
  await page.getByRole("button", { name: ui("ta", "create_room") }).click();
  await expect(page.locator("#demo-clip")).toBeVisible();
  for (const id of ["#language", "#demo-clip"]) {
    const overflow = await page.locator(id).evaluate((el) => getComputedStyle(el).textOverflow);
    expect(overflow, id).toBe("ellipsis");
  }
});

test.describe("the audit itself", () => {
  const LABEL = `<span class="l-main">कमरा बनाएं</span> <span class="l-en" lang="en">Create room</span>`;

  /**
   * @param {Page} page
   * @param {string} lang the language the page is audited as
   * @param {string} body
   * @param {string} documentLang what the page declares, by default the audited language
   * @param {string[]} names the language names the page writes for this viewer
   */
  async function auditSample(page, lang, body, documentLang = lang, names = []) {
    await page.setContent(`<!doctype html><html><body>${body}</body></html>`);
    await page.evaluate((value) => (document.documentElement.lang = value), documentLang);
    return auditPage(page, { lang, keys: ["create_room", "join_and_sound"], same: [], names });
  }

  test("passes a screen with nothing wrong", async ({ page }) => {
    const result = await auditSample(
      page,
      "hi",
      `<p data-i18n="create_room">${LABEL}</p><p>Room code <b id="code">AB12CD</b></p>`,
    );
    expect(result.problems).toEqual([]);
    expect(result.glyphs.controlsOk).toBe(true);
    expect(result.seen).toBeGreaterThan(0);
  });

  test("finds each fault it exists for", async ({ page }) => {
    const result = await auditSample(
      page,
      "hi",
      [
        `<p data-i18n="join_and_sound">Join and sound</p>`, // English only in a Hindi screen
        `<p>தமிழ்</p>`, // the wrong script
        `<p>create_room</p>`, // a raw key
        `<p>Distance: undefined</p>`, // a value that never arrived
        `<div style="width: 60px; overflow: hidden; white-space: nowrap">A label too long to fit</div>`,
        `<p>\u{10FFFF}</p>`, // a character no font has
        `<div style="width: 2000px">wider than the window</div>`,
        `<select style="width: 90px"><option>An option far too long for this control</option></select>`,
      ].join(""),
    );
    const found = result.problems.join("\n");
    expect(found).toContain("English only, no hi text");
    expect(found).toContain("letters outside Devanagari and Latin");
    expect(found).toContain("shows a raw key");
    expect(found).toContain("shows a placeholder or null");
    expect(found).toContain("text wider than its box, cut off");
    expect(found).toContain("no glyph for U+10FFFF");
    expect(found).toContain("the page scrolls sideways");
    expect(found).toContain("chosen option wider than its select, cut off");
  });

  test("reports a select cut with an ellipsis as marked, not as a problem", async ({ page }) => {
    const select = (/** @type {string} */ style) =>
      `<select style="width: 90px; ${style}"><option>An option far too long for this control</option></select>`;
    const marked = await auditSample(page, "en", select("text-overflow: ellipsis"));
    expect(marked.problems).toEqual([]);
    expect(marked.marked).toHaveLength(1);
    const silent = await auditSample(page, "en", select(""));
    expect(silent.problems.join("\n")).toContain("chosen option wider than its select, cut off");
    expect(silent.marked).toEqual([]);
  });

  test("lets a language name stand in both lines, and nothing else in the wrong script", async ({
    page,
  }) => {
    const name = "कन्नड़ (Kannada)";
    const body =
      `<p><span class="l-main">राइडर जुड़ा। उनकी भाषा: ${name}.</span> ` +
      `<span class="l-en" lang="en">The rider joined. Their language: ${name}.</span></p>`;
    expect((await auditSample(page, "hi", body, "hi", [name])).problems).toEqual([]);
    // The same page without the name known: the Devanagari in the English line is reported.
    const found = (await auditSample(page, "hi", body)).problems.join("\n");
    expect(found).toContain("letters outside Latin");
    // The name does not excuse other text in the English line.
    const stray = body.replace("The rider joined.", "தமிழ்");
    expect((await auditSample(page, "hi", stray, "hi", [name])).problems.join("\n")).toContain(
      "letters outside Latin",
    );
  });

  test("finds a screen whose text and declared language are another language's", async ({
    page,
  }) => {
    const result = await auditSample(page, "ta", `<p data-i18n="create_room">${LABEL}</p>`, "hi");
    const found = result.problems.join("\n");
    expect(found).toContain('<html lang> is "hi", not "ta"');
    expect(found).toContain("letters outside Tamil and Latin");
    expect(found).toContain("local line has no Tamil");
  });
});
