// @ts-check
// Tablet and laptop layouts. The phone sizes (360 and 412 px) are checked in phone.spec.js.
import { expect, test } from "@playwright/test";
import { loadUi, makeUi } from "./chrome-text.js";
import { collectProblems } from "./ui-audit.js";

const NORMAL = "http://127.0.0.1:8765"; // tests/e2e/serve.py
const DEMO = "http://127.0.0.1:8766"; // tests/e2e/serve.py --demo

const TABLET = { width: 768, height: 1024 };
const LAPTOP = { width: 1280, height: 800 };
const WIDE = { width: 1920, height: 1080 };

const MIN_CONTROL = 48; // the smallest tap target on any screen
const MAX_CONTROL = 64; // on a laptop nothing a person presses is taller than this
const PAGES = ["index.html", "customer.html", "rider.html", "solo.html"];

/** @type {ReturnType<typeof makeUi>} */
let ui = makeUi({});
test.beforeAll(async ({ playwright }) => {
  ui = await loadUi(playwright, NORMAL);
});

/** @typedef {import("@playwright/test").Page} Page */

/** Runs in the page: how far the document is wider than the window. */
const sidewaysScroll = () => document.documentElement.scrollWidth - document.documentElement.clientWidth;

/** Runs in the page: how far the document is taller than the window. */
const downwardScroll = () => document.documentElement.scrollHeight - document.documentElement.clientHeight;

/**
 * Heights of the controls a person presses or types into: big and mic buttons, the action buttons,
 * selects and text fields. Quick replies are left out: each holds a sentence in two languages and
 * grows with it.
 * @param {Page} page
 */
const controlHeights = (page) =>
  page.evaluate(() => {
    const selector = ".big-btn, .talk-btn, .actions button, .chip-actions button, select, input[type='text']";
    return [...document.querySelectorAll(selector)]
      .map((el) => ({ name: `${el.tagName}#${el.id || el.className}`, height: el.getBoundingClientRect().height }))
      .filter((c) => c.height > 0);
  });

/**
 * The split page has fitted once demo-split.js has told the stylesheet how tall the pages are.
 * @param {Page} page
 */
const fitted = (page) =>
  expect
    .poll(() => page.evaluate(() => document.documentElement.style.getPropertyValue("--content-h")))
    .toMatch(/^\d+px$/);

/**
 * Frame height less the taller page's height, in px. Zero to a pixel of rounding means the frame is
 * exactly as tall as its content.
 * @param {Page} page
 */
const spareHeight = (page) =>
  page.evaluate(() => {
    const sizes = ["customer-frame", "rider-frame"].map((id) => {
      const frame = /** @type {HTMLIFrameElement} */ (document.getElementById(id));
      return {
        frame: frame.getBoundingClientRect().height,
        page: frame.contentDocument?.body.getBoundingClientRect().height ?? 0,
      };
    });
    return Math.min(...sizes.map((s) => s.frame)) - Math.max(...sizes.map((s) => s.page));
  });

/**
 * @param {Page} customer @param {Page} rider
 * @param {string} base
 */
async function joinRoom(customer, rider, base) {
  await customer.goto(`${base}/customer.html`);
  await customer.locator("#language").selectOption("kn");
  await customer.getByRole("button", { name: ui("kn", "create_room") }).click();
  await expect(customer.locator("#code")).toHaveText(/^[A-Z0-9]{6}$/);
  const code = (await customer.locator("#code").textContent()) ?? "";
  await rider.goto(`${base}/rider.html?code=${code}`);
  await rider.locator("#language").selectOption("hi");
  await rider.getByRole("button", { name: ui("hi", "join_and_sound") }).click();
  await expect(customer.locator("#peer")).toContainText(ui.has("kn", "rider_joined"));
}

for (const size of [TABLET, LAPTOP, WIDE]) {
  test.describe(`${size.width} x ${size.height}`, () => {
    test.use({ viewport: size });

    for (const name of PAGES) {
      test(`${name} does not scroll sideways`, async ({ page }) => {
        const problems = collectProblems(page);
        await page.goto(`${NORMAL}/${name}`);
        expect(await page.evaluate(sidewaysScroll)).toBeLessThanOrEqual(0);
        expect(problems).toEqual([]);
      });
    }

    test("split page does not scroll sideways, in the page or in either frame, and logs nothing", async ({
      page,
    }) => {
      const problems = collectProblems(page);
      await page.goto(`${DEMO}/demo.html`);
      await expect(page.frameLocator("#customer-frame").locator("h1")).toHaveText("Customer");
      await expect(page.frameLocator("#rider-frame").locator("h1")).toHaveText("Rider");
      // Setting --content-h is the one place the page writes a style: it must run without a CSP error.
      await fitted(page);
      expect(await page.evaluate(sidewaysScroll)).toBeLessThanOrEqual(0);
      for (const frame of page.frames().filter((f) => f !== page.mainFrame())) {
        expect(await frame.evaluate(sidewaysScroll)).toBeLessThanOrEqual(0);
      }
      expect(problems).toEqual([]);
    });

    test("demo banner on a page of its own wraps: nothing cut, the English line under the local one", async ({
      page,
    }) => {
      await page.goto(`${DEMO}/customer.html`);
      await page.locator("#language").selectOption("kn");
      await page.getByRole("button", { name: ui("kn", "create_room") }).click();
      await expect(page.locator("#demo-banner")).toBeVisible();
      // A sentence far wider than the page, in letters every device has: this tests the box, not a font.
      await page.evaluate((sentence) => {
        for (const line of document.querySelectorAll("#demo-banner > span")) line.textContent = sentence;
      }, "Prepared clips, not live speech. ".repeat(20));
      const cut = await page
        .locator("#demo-banner > span")
        .evaluateAll((spans) => spans.map((span) => span.scrollWidth > span.clientWidth + 1));
      expect(cut).toEqual([false, false]);
      const local = await page.locator("#demo-banner > .l-main").boundingBox();
      const english = await page.locator("#demo-banner > .l-en").boundingBox();
      expect(english?.y ?? 0).toBeGreaterThanOrEqual((local?.y ?? 1) + (local?.height ?? 1) - 1);
    });
  });
}

test.describe("laptop", () => {
  for (const size of [LAPTOP, WIDE]) {
    test.describe(`${size.width} x ${size.height}`, () => {
      test.use({ viewport: size });

      test("home: two columns, the sample card above the fold, text at the laptop size", async ({ page }) => {
        await page.goto(`${NORMAL}/index.html`);
        const box = async (/** @type {string} */ selector) => {
          const found = await page.locator(selector).boundingBox();
          if (!found) throw new Error(`${selector} has no box`);
          return found;
        };
        const main = await box("main.landing");
        const intro = await box(".intro");
        const preview = await box(".preview");
        const notes = await box(".notes");
        expect(main.width).toBeLessThanOrEqual(1120 + 1);
        expect(intro.x + intro.width).toBeLessThanOrEqual(preview.x + 1); // side by side
        expect(Math.abs(intro.y - preview.y)).toBeLessThan(40); // starting at the same height
        expect(notes.y).toBeGreaterThanOrEqual(preview.y + preview.height); // the long text is below both
        expect(notes.width).toBeGreaterThan(intro.width + preview.width);
        expect(preview.y + preview.height).toBeLessThanOrEqual(size.height); // above the fold
        await expect(page.locator("#preview-chips .chip")).toHaveCount(4);
        await expect(page.locator("#preview-chips .chip-gate .chip-value")).toHaveText("3");
        await expect(page.locator("#preview-chips button")).toHaveCount(0); // a picture, not controls
        const fontPx = (/** @type {string} */ selector) =>
          page.locator(selector).first().evaluate((el) => parseFloat(getComputedStyle(el).fontSize));
        expect(await fontPx(".headline")).toBe(40);
        expect(await fontPx("#preview-chips .chip-value")).toBe(40);
        for (const c of await controlHeights(page)) {
          expect(c.height, c.name).toBeGreaterThanOrEqual(MIN_CONTROL);
          expect(c.height, c.name).toBeLessThanOrEqual(MAX_CONTROL);
        }
      });

      test("customer and rider alone: one centred column, controls 48 to 64 px", async ({ browser }) => {
        const customer = await (await browser.newContext({ viewport: size })).newPage();
        const rider = await (await browser.newContext({ viewport: size })).newPage();
        await joinRoom(customer, rider, NORMAL);
        for (const page of [customer, rider]) {
          const main = await page.locator("main").boundingBox();
          expect(main?.width ?? 0).toBeLessThanOrEqual(640 + 1);
          const left = main?.x ?? 0;
          const right = size.width - left - (main?.width ?? 0);
          expect(Math.abs(left - right)).toBeLessThan(2); // centred
          expect(await page.evaluate(sidewaysScroll)).toBeLessThanOrEqual(0);
          for (const c of await controlHeights(page)) {
            expect(c.height, c.name).toBeGreaterThanOrEqual(MIN_CONTROL);
            expect(c.height, c.name).toBeLessThanOrEqual(MAX_CONTROL);
          }
        }
        // The Kannada customer's mic carries two lines (Kannada and English) and still fits.
        const mic = await customer.locator("#talk").boundingBox();
        expect(mic?.height ?? 0).toBeLessThanOrEqual(MAX_CONTROL);
      });

      test("split page: two panes side by side, each as tall as its page and inside the window", async ({
        page,
      }) => {
        await page.goto(`${DEMO}/demo.html`);
        await expect(page.frameLocator("#customer-frame").locator("#language")).toBeVisible();
        await expect(page.frameLocator("#rider-frame").locator("#code-input")).toBeVisible();
        await fitted(page);
        const customer = await page.locator(".pane-customer").boundingBox();
        const rider = await page.locator(".pane-rider").boundingBox();
        const stage = await page.locator(".stage").boundingBox();
        if (!customer || !rider || !stage) throw new Error("layout missing");
        expect(customer.x + customer.width).toBeLessThanOrEqual(rider.x + 1); // side by side
        expect(Math.abs(customer.y - rider.y)).toBeLessThan(2);
        expect(Math.abs(customer.height - rider.height)).toBeLessThan(2);
        expect(customer.height).toBeLessThan(size.height); // setup state: not a full-height pane
        expect(stage.width).toBeLessThanOrEqual(1280 + 1);
        expect(await page.evaluate(downwardScroll)).toBeLessThanOrEqual(0); // the setup screen fits
        // Sized to content: as tall as the taller page, to a pixel of rounding, and no more.
        await expect.poll(() => spareHeight(page)).toBeGreaterThanOrEqual(0);
        await expect.poll(() => spareHeight(page)).toBeLessThan(2);
      });
    });
  }

  test("split page after a demo clip: both panes and the mic stay inside a 1280 x 800 window", async ({
    browser,
  }) => {
    const page = await (await browser.newContext({ viewport: LAPTOP })).newPage();
    const problems = collectProblems(page);
    await page.goto(`${DEMO}/demo.html`);
    const customer = page.frameLocator("#customer-frame");
    const rider = page.frameLocator("#rider-frame");
    await customer.locator("#language").selectOption("kn");
    await customer.getByRole("button", { name: ui("kn", "create_room") }).click();
    await expect(customer.locator("#code")).toHaveText(/^[A-Z0-9]{6}$/);
    await expect(rider.locator("#code-input")).toHaveValue(/^[A-Z0-9]{6}$/);
    await rider.locator("#language").selectOption("hi");
    await rider.getByRole("button", { name: ui("hi", "join_and_sound") }).click();
    await expect(customer.locator("#peer")).toContainText(ui.has("kn", "rider_joined"));
    await customer.locator("#demo-clip").selectOption("clip-kn");
    await customer.locator("#demo-send").click();
    await expect(rider.locator("#card-chips .chip-gate .chip-value")).toHaveText("2");

    // In a frame the banner stays one line, local and English side by side (the demo bar above the
    // panes says the same): that line is part of why both panes fit the window below.
    for (const frame of [customer, rider]) {
      await expect(frame.locator("#demo-banner")).toBeVisible();
      const local = await frame.locator("#demo-banner > .l-main").boundingBox();
      const english = await frame.locator("#demo-banner > .l-en").boundingBox();
      expect(Math.abs((local?.y ?? 0) - (english?.y ?? 99))).toBeLessThan(2);
    }

    // The panes grow with the new content up to the window, never past it.
    await expect.poll(() => page.evaluate(downwardScroll)).toBeLessThanOrEqual(0);
    const mic = await customer.locator("#talk").boundingBox();
    const chips = await rider.locator("#card-chips").boundingBox();
    expect((mic?.y ?? 0) + (mic?.height ?? 0)).toBeLessThanOrEqual(LAPTOP.height);
    expect((chips?.y ?? 0) + (chips?.height ?? 0)).toBeLessThanOrEqual(LAPTOP.height);
    for (const selector of [".pane-customer", ".pane-rider"]) {
      const pane = await page.locator(selector).boundingBox();
      expect((pane?.y ?? 0) + (pane?.height ?? 0)).toBeLessThanOrEqual(LAPTOP.height);
    }
    expect(await page.evaluate(sidewaysScroll)).toBeLessThanOrEqual(0);
    expect(problems).toEqual([]);
  });
});

test.describe("tablet, 768 x 1024", () => {
  test.use({ viewport: TABLET });

  test("home: one column, headline and buttons between their phone and laptop sizes", async ({ page }) => {
    await page.goto(`${NORMAL}/index.html`);
    const intro = await page.locator(".intro").boundingBox();
    const preview = await page.locator(".preview").boundingBox();
    expect(preview?.y ?? 0).toBeGreaterThanOrEqual((intro?.y ?? 0) + (intro?.height ?? 0) - 1); // stacked
    const headline = await page.locator(".headline").evaluate((el) => parseFloat(getComputedStyle(el).fontSize));
    expect(headline).toBeGreaterThan(28);
    expect(headline).toBeLessThan(40);
    for (const c of await controlHeights(page)) {
      expect(c.height, c.name).toBeGreaterThan(56);
      expect(c.height, c.name).toBeLessThan(72);
    }
  });

  test("split page: two panes stacked in one phone-wide column, no sideways scroll", async ({ page }) => {
    await page.goto(`${DEMO}/demo.html`);
    await expect(page.frameLocator("#rider-frame").locator("#code-input")).toBeVisible();
    await fitted(page);
    const customer = await page.locator(".pane-customer").boundingBox();
    const rider = await page.locator(".pane-rider").boundingBox();
    if (!customer || !rider) throw new Error("layout missing");
    expect(rider.y).toBeGreaterThanOrEqual(customer.y + customer.height - 1); // stacked
    expect(customer.width).toBeLessThanOrEqual(640);
    expect(customer.width).toBeGreaterThan(400); // not squeezed
    expect(Math.abs(customer.width - rider.width)).toBeLessThan(2);
    expect(await page.evaluate(sidewaysScroll)).toBeLessThanOrEqual(0);
  });
});
