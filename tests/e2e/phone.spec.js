// @ts-check
import { expect, test } from "@playwright/test";
import { loadUi, makeUi } from "./chrome-text.js";

const DEMO = "http://127.0.0.1:8766"; // tests/e2e/serve.py --demo
const NORMAL = "http://127.0.0.1:8765";
const MIN_TAP = 48;

/** @type {ReturnType<typeof makeUi>} */
let ui = makeUi({});
test.beforeAll(async ({ playwright }) => {
  ui = await loadUi(playwright, NORMAL);
});

/** @param {import("@playwright/test").Page} page */
const overflow = (page) =>
  page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);

/**
 * Visible, enabled buttons, links and selects smaller than the minimum tap size.
 * @param {import("@playwright/test").Page} page
 */
const smallTargets = (page) =>
  page.evaluate((min) => {
    const found = [];
    for (const el of document.querySelectorAll("button, a[href], select, summary")) {
      const box = el.getBoundingClientRect();
      if (box.width === 0 || box.height === 0) continue;
      if (box.width < min - 0.5 || box.height < min - 0.5) {
        found.push(`${el.tagName}#${el.id || el.className} ${Math.round(box.width)}x${Math.round(box.height)}`);
      }
    }
    return found;
  }, MIN_TAP);

for (const size of [
  { width: 360, height: 800 },
  { width: 412, height: 915 },
]) {
  test.describe(`phone ${size.width} x ${size.height}`, () => {
    test.use({ viewport: size });

    test("home: headline, both role buttons and the demo link are visible without scrolling", async ({
      page,
    }) => {
      await page.goto(`${NORMAL}/index.html`);
      for (const locator of [
        page.locator("h1"),
        page.locator("a.role-customer"),
        page.locator("a.role-rider"),
        page.locator("a[href='demo.html']"),
      ]) {
        const box = await locator.boundingBox();
        expect(box).not.toBeNull();
        expect((box?.y ?? 0) + (box?.height ?? 0)).toBeLessThanOrEqual(size.height);
      }
      expect(await overflow(page)).toBeLessThanOrEqual(0);
      expect(await smallTargets(page)).toEqual([]);
    });

    test("customer: the mic is large, inside the viewport, and the screen does not scroll sideways", async ({
      browser,
    }) => {
      const customer = await (await browser.newContext({ viewport: size })).newPage();
      const rider = await (await browser.newContext()).newPage();
      await customer.goto(`${DEMO}/customer.html`);
      await customer.locator("#language").selectOption("kn");
      await customer.getByRole("button", { name: ui("kn", "create_room") }).click();
      await expect(customer.locator("#code")).toHaveText(/^[A-Z0-9]{6}$/);
      const code = (await customer.locator("#code").textContent()) ?? "";
      await rider.goto(`${DEMO}/rider.html?code=${code}`);
      await rider.locator("#language").selectOption("hi");
      await rider.getByRole("button", { name: ui("hi", "join_and_sound") }).click();
      await expect(customer.locator("#peer")).toContainText(ui.has("kn", "rider_joined"));

      const mic = customer.locator("#talk");
      const box = await mic.boundingBox();
      expect(box?.height ?? 0).toBeGreaterThanOrEqual(64);
      expect((box?.y ?? 0) + (box?.height ?? 0)).toBeLessThanOrEqual(size.height);
      expect(await overflow(customer)).toBeLessThanOrEqual(0);
      expect(await smallTargets(customer)).toEqual([]);

      // The code box collapses once the rider is in, and opens again from its button.
      await expect(customer.locator("#code-box")).toHaveClass(/compact/);
      await expect(customer.locator("#qr")).toBeHidden();
      const toggle = customer.locator(".code-toggle");
      await expect(toggle).toHaveAttribute("aria-expanded", "false");
      await toggle.click();
      await expect(customer.locator("#code-box")).not.toHaveClass(/compact/);
      await expect(toggle).toHaveAttribute("aria-expanded", "true");
      await toggle.click();
      await expect(customer.locator("#code-box")).toHaveClass(/compact/);

      // Idle state is announced on the button, and the mic stays in view after scrolling.
      await expect(mic).toHaveAttribute("data-state", "idle");
      await customer.evaluate(() => window.scrollTo(0, document.body.scrollHeight));
      const after = await mic.boundingBox();
      expect((after?.y ?? 0) + (after?.height ?? 0)).toBeLessThanOrEqual(size.height);
    });

    test("rider after a demo clip: the delivery card is above the fold and the buttons are big", async ({
      browser,
    }) => {
      const customer = await (await browser.newContext()).newPage();
      const rider = await (await browser.newContext({ viewport: size })).newPage();
      await customer.goto(`${DEMO}/customer.html`);
      await customer.locator("#language").selectOption("kn");
      await customer.getByRole("button", { name: ui("kn", "create_room") }).click();
      await expect(customer.locator("#code")).toHaveText(/^[A-Z0-9]{6}$/);
      const code = (await customer.locator("#code").textContent()) ?? "";
      await rider.goto(`${DEMO}/rider.html?code=${code}`);
      await rider.locator("#language").selectOption("hi");
      await rider.getByRole("button", { name: ui("hi", "join_and_sound") }).click();
      await expect(customer.locator("#peer")).toContainText(ui.has("kn", "rider_joined"));
      await customer.locator("#demo-clip").selectOption("clip-kn");
      await customer.locator("#demo-send").click();
      await expect(rider.locator("#card-chips .chip-gate .chip-value")).toHaveText("2");

      const card = await rider.locator("#card-chips").boundingBox();
      expect((card?.y ?? 0) + (card?.height ?? 0)).toBeLessThanOrEqual(size.height);
      expect(await overflow(rider)).toBeLessThanOrEqual(0);
      expect(await smallTargets(rider)).toEqual([]);
      for (const kind of ["#card-chips .chip-gate button", "#card-chips .chip-floor button"]) {
        for (const button of await rider.locator(kind).all()) {
          const box = await button.boundingBox();
          expect(box?.width ?? 0).toBeGreaterThanOrEqual(MIN_TAP - 0.5);
          expect(box?.height ?? 0).toBeGreaterThanOrEqual(MIN_TAP - 0.5);
        }
      }
    });
  });
}

test("customer at 412 x 915 after a demo clip: the status line scrolls clear of the sticky mic", async ({
  browser,
}) => {
  const customer = await (await browser.newContext({ viewport: { width: 412, height: 915 } })).newPage();
  const rider = await (await browser.newContext()).newPage();
  await customer.goto(`${DEMO}/customer.html`);
  await customer.locator("#language").selectOption("kn");
  await customer.getByRole("button", { name: ui("kn", "create_room") }).click();
  await expect(customer.locator("#code")).toHaveText(/^[A-Z0-9]{6}$/);
  const code = (await customer.locator("#code").textContent()) ?? "";
  await rider.goto(`${DEMO}/rider.html?code=${code}`);
  await rider.locator("#language").selectOption("hi");
  await rider.getByRole("button", { name: ui("hi", "join_and_sound") }).click();
  await expect(customer.locator("#peer")).toContainText(ui.has("kn", "rider_joined"));
  await customer.locator("#demo-clip").selectOption("clip-kn");
  await customer.locator("#demo-send").click();
  await expect(customer.locator("#sent-demo-badge")).toBeVisible();
  await expect(customer.locator("#status")).toContainText(ui.has("kn", "sent_demo_rider_has_details"));

  await customer.evaluate(() => window.scrollTo(0, document.body.scrollHeight));
  // At the end of the page no block that follows the mic in the page is covered by it.
  const covered = await customer.evaluate(() => {
    const mic = document.getElementById("talk");
    if (!mic) throw new Error("no mic");
    const m = mic.getBoundingClientRect();
    return [...document.querySelectorAll("#room > *:not([hidden])")]
      .filter((el) => mic.compareDocumentPosition(el) & Node.DOCUMENT_POSITION_FOLLOWING)
      .filter((el) => {
        const r = el.getBoundingClientRect();
        return r.height > 0 && r.top < m.bottom && r.bottom > m.top;
      })
      .map((el) => el.id || el.className);
  });
  expect(covered).toEqual([]);
  expect(await overflow(customer)).toBeLessThanOrEqual(0);
});

test("recording shows the clock and a pressed state, then returns to idle", async ({ browser }) => {
  const context = await browser.newContext({
    viewport: { width: 412, height: 915 },
    permissions: ["microphone"],
  });
  const page = await context.newPage();
  await page.addInitScript(() => {
    // A silent microphone: the page only needs a stream it can record.
    const audio = new AudioContext();
    const destination = audio.createMediaStreamDestination();
    navigator.mediaDevices.getUserMedia = async () => destination.stream;
  });
  const rider = await (await browser.newContext()).newPage();
  await page.goto(`${NORMAL}/customer.html`);
  await page.locator("#language").selectOption("kn");
  await page.getByRole("button", { name: ui("kn", "create_room") }).click();
  await expect(page.locator("#code")).toHaveText(/^[A-Z0-9]{6}$/);
  const code = (await page.locator("#code").textContent()) ?? "";
  await rider.goto(`${NORMAL}/rider.html?code=${code}`);
  await rider.locator("#language").selectOption("hi");
  await rider.getByRole("button", { name: ui("hi", "join_and_sound") }).click();
  await expect(page.locator("#peer")).toContainText(ui.has("kn", "rider_joined"));

  const mic = page.locator("#talk");
  await mic.click();
  await expect(mic).toHaveAttribute("data-state", "recording");
  await expect(mic).toHaveAttribute("aria-pressed", "true");
  await expect(page.locator(".talk-elapsed")).toBeVisible();
  await expect(page.locator(".talk-elapsed")).toHaveText(/^0:0\d$/);
  await page.emulateMedia({ reducedMotion: "reduce" });
  const animation = await mic.evaluate((el) => getComputedStyle(el).animationName);
  expect(animation).toBe("none"); // the pulse respects prefers-reduced-motion
  await mic.click();
  await expect(page.locator(".talk-elapsed")).toBeHidden();
  await expect(mic).not.toHaveAttribute("data-state", "recording");
});
