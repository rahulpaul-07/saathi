// @ts-check
import { expect, test } from "@playwright/test";
import { loadUi, makeUi } from "./chrome-text.js";

const DEMO = "http://127.0.0.1:8766"; // tests/e2e/serve.py --demo
const NORMAL = "http://127.0.0.1:8765";

/** The interface text a viewer in a language sees. @type {(language: string, key: string) => string} */
/** @type {ReturnType<typeof makeUi>} */
let ui = makeUi({});
test.beforeAll(async ({ playwright }) => {
  ui = await loadUi(playwright, NORMAL);
});

test("demo mode: a prepared clip is sent, both screens say it is a demo clip", async ({
  browser,
}) => {
  const customer = await (await browser.newContext()).newPage();
  const rider = await (await browser.newContext()).newPage();
  /** @type {string[]} */
  const problems = [];
  for (const page of [customer, rider]) {
    page.on("console", (m) => {
      if (["error", "warning"].includes(m.type())) problems.push(m.text());
    });
    page.on("pageerror", (e) => problems.push(e.message));
  }

  await customer.goto(`${DEMO}/customer.html`);
  await customer.locator("#language").selectOption("kn");
  await customer.getByRole("button", { name: ui("kn", "create_room") }).click();
  await expect(customer.locator("#demo-banner")).toBeVisible();
  await expect(customer.locator("#code")).toHaveText(/^[A-Z0-9]{6}$/);
  const code = (await customer.locator("#code").textContent()) ?? "";
  await rider.goto(`${DEMO}/rider.html?code=${code}`);
  await rider.locator("#language").selectOption("bn");
  await rider.getByRole("button", { name: ui("bn", "join_and_sound") }).click();
  await expect(customer.locator("#peer")).toContainText(ui.has("kn", "rider_joined"));

  // The picker offers only clips in the speaker's own language.
  await expect(customer.locator("#demo-clip option")).toHaveText([
    `${ui.main("kn", "choose_a_clip")} / Choose a clip`,
    "ಮಾದರಿ ಕ್ಲಿಪ್ / Sample kn",
  ]);
  await expect(customer.locator("#demo-clip")).toHaveValue("");
  await expect(customer.locator("#demo-send")).toBeDisabled();
  await expect(customer.locator("#sent-demo-badge")).toBeHidden();
  await customer.locator("#demo-clip").selectOption("clip-kn");
  await customer.locator("#demo-send").click();
  await expect(rider.locator("#card-chips .chip-gate .chip-value")).toHaveText("2");
  await expect(rider.locator("#demo-badge")).toBeVisible();
  await expect(customer.locator("#sent-demo-badge")).toBeVisible();
  expect(problems).toEqual([]);
});

test("demo mode: the clip is fetched before the turn and its exact bytes are what is sent", async ({
  page,
}) => {
  /** @type {string[]} */
  const calls = [];
  // Chromium does not expose Blob parts of a multipart body to Playwright, so the page records
  // the size of the audio it uploads.
  await page.addInitScript(() => {
    const original = window.fetch;
    window.fetch = (input, init) => {
      const body = init?.body;
      if (body instanceof FormData) {
        const audio = body.get("audio");
        if (audio instanceof Blob) /** @type {any} */ (window).__uploadedAudioBytes = audio.size;
      }
      return original(input, init);
    };
  });
  page.on("request", (request) => {
    const path = new URL(request.url()).pathname;
    if (path.startsWith("/demo/clips/") && path.endsWith(".wav")) calls.push("clip");
    if (path.endsWith("/turn")) calls.push("turn");
  });
  await page.goto(`${DEMO}/customer.html`);
  await page.locator("#language").selectOption("kn");
  await page.getByRole("button", { name: ui("kn", "create_room") }).click();
  await expect(page.locator("#code")).toHaveText(/^[A-Z0-9]{6}$/);
  const code = (await page.locator("#code").textContent()) ?? "";
  const rider = await (await page.context().browser()?.newContext())?.newPage();
  if (!rider) throw new Error("no browser");
  await rider.goto(`${DEMO}/rider.html?code=${code}`);
  await rider.locator("#language").selectOption("bn");
  await rider.getByRole("button", { name: ui("bn", "join_and_sound") }).click();
  await expect(page.locator("#peer")).toContainText(ui.has("kn", "rider_joined"));

  const clipId = "clip-kn";
  await expect(page.locator("#demo-send")).toBeDisabled(); // nothing is sent until a clip is chosen
  await page.locator("#demo-clip").selectOption(clipId);
  const clip = await page.request.get(`${DEMO}/demo/clips/${clipId}.wav`);
  const clipBytes = await clip.body();
  expect(clipBytes.length).toBeGreaterThan(44);
  calls.length = 0; // the request above was the test's own

  await page.locator("#demo-send").click();
  await expect(rider.locator("#card-chips .chip-gate .chip-value")).toHaveText("2");
  expect(calls).toEqual(["clip", "turn"]);
  const uploaded = await page.evaluate(() => /** @type {any} */ (window).__uploadedAudioBytes);
  expect(uploaded).toBe(clipBytes.length);
});

test("demo input is absent when the flag is off", async ({ page }) => {
  await page.goto(`${NORMAL}/customer.html`);
  await expect(page.locator("#demo-banner")).toBeHidden();
  await expect(page.locator("#demo")).toBeHidden();
  const response = await page.request.get(`${NORMAL}/demo/clips`);
  expect(response.status()).toBe(404);
});

test("split-screen page loads both screens in one 16:9 stage", async ({ page }) => {
  await page.setViewportSize({ width: 1920, height: 1080 });
  await page.goto(`${DEMO}/demo.html`);
  await expect(page.frameLocator("#customer-frame").locator("h1")).toHaveText("Customer");
  await expect(page.frameLocator("#rider-frame").locator("h1")).toHaveText("Rider");
  await page.frameLocator("#customer-frame").locator("#language").selectOption("kn");
  await page
    .frameLocator("#customer-frame")
    .getByRole("button", { name: ui("kn", "create_room") })
    .click();
  // Wait for a real code first: read straight after the click it is still empty, and an empty
  // string would match the rider's empty input.
  await expect(page.frameLocator("#customer-frame").locator("#code")).toHaveText(/^[A-Z0-9]{6}$/);
  const code = await page.frameLocator("#customer-frame").locator("#code").textContent();
  await expect(page.frameLocator("#rider-frame").locator("#code-input")).toHaveValue(code ?? "");
});

test("demo mode: a language with no clips gets the banner but no empty clip picker", async ({
  page,
}) => {
  await page.route("**/demo/clips", (route) => route.fulfill({ json: { clips: [] } }));
  await page.goto(`${DEMO}/customer.html`);
  await page.locator("#language").selectOption("kn");
  await page.getByRole("button", { name: ui("kn", "create_room") }).click();
  await expect(page.locator("#demo-banner")).toBeVisible();
  await expect(page.locator("#demo")).toBeHidden();
});
