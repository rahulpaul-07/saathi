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

test("split-screen page loads both screens and copies the room code across", async ({ page }) => {
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

test("split-screen page names each person's language in the pane header and hides the Back link", async ({
  page,
}) => {
  await page.setViewportSize({ width: 1920, height: 1080 });
  await page.goto(`${DEMO}/demo.html`);
  await expect(page.locator("#customer-lang")).toHaveText(""); // nothing is preselected
  await page.frameLocator("#customer-frame").locator("#language").selectOption("kn");
  await page.frameLocator("#rider-frame").locator("#language").selectOption("hi");
  // The header names the language in its own script with the English name, and marks it as that language.
  await expect(page.locator("#customer-lang")).toHaveText(/\(Kannada\)$/);
  await expect(page.locator("#customer-lang")).toHaveAttribute("lang", "kn");
  await expect(page.locator("#rider-lang")).toHaveText(/\(Hindi\)$/);
  await expect(page.locator("#rider-lang")).toHaveAttribute("lang", "hi");
  // Back would load the home page into half the screen, so a framed page does not offer it.
  for (const id of ["customer-frame", "rider-frame"]) {
    await expect(page.frameLocator(`#${id}`).locator('a[href="index.html"]')).toBeHidden();
  }
});

test("split page: a reload keeps both people in their own rooms, and ending one returns each frame to its start screen", async ({
  page,
}) => {
  /** @type {string[]} */
  const problems = [];
  page.on("console", (m) => {
    if (["error", "warning"].includes(m.type())) problems.push(m.text());
  });
  page.on("pageerror", (e) => problems.push(e.message));
  await page.setViewportSize({ width: 1920, height: 1080 });
  await page.goto(`${DEMO}/demo.html`);
  const customer = page.frameLocator("#customer-frame");
  const rider = page.frameLocator("#rider-frame");
  await customer.locator("#language").selectOption("kn");
  await customer.getByRole("button", { name: ui("kn", "create_room") }).click();
  await expect(customer.locator("#code")).toHaveText(/^[A-Z0-9]{6}$/);
  await expect(rider.locator("#code-input")).toHaveValue(/^[A-Z0-9]{6}$/);
  await rider.locator("#language").selectOption("hi");
  await rider.getByRole("button", { name: ui("hi", "join_and_sound") }).click();
  await expect(rider.locator("#room")).toBeVisible();
  await expect(customer.locator("#talk")).toBeEnabled();

  // Both frames share the tab's storage; each must find its own room again, not the last one saved.
  await page.reload();
  await expect(customer.locator("#room")).toBeVisible();
  await expect(rider.locator("#room")).toBeVisible();
  await expect(customer.locator("#peer")).toContainText(ui.has("kn", "rider_joined"));
  await expect(rider.locator("#peer")).toContainText(ui.has("hi", "customer_joined"));

  // Ending a room reloads the frame, not the page around it, and each side is told in its language.
  await customer.getByRole("button", { name: ui("kn", "end_room") }).click();
  await expect(page).toHaveURL(/\/demo\.html$/);
  await expect(customer.locator("#setup-status")).toHaveText(ui("kn", "room_ended"));
  await expect(rider.locator("#join-status")).toHaveText(ui("hi", "room_ended"));
  await expect(customer.locator("#room")).toBeHidden();
  await expect(rider.locator("#room")).toBeHidden();
  expect(problems).toEqual([]);
});

test("replay: a rider language with no stored audio shows text and tiles, no error and no retry", async ({
  browser,
}) => {
  const REPLAY = "http://127.0.0.1:8768"; // tests/e2e/serve.py --replay: bundle holds kn -> hi only
  const customer = await (await browser.newContext()).newPage();
  const rider = await (await browser.newContext()).newPage();
  /** @type {string[]} */
  const problems = [];
  /** @type {string[]} */
  const requests = [];
  for (const page of [customer, rider]) {
    page.on("console", (m) => {
      if (["error", "warning"].includes(m.type())) problems.push(m.text());
    });
    page.on("pageerror", (e) => problems.push(e.message));
    page.on("request", (r) => {
      const path = new URL(r.url()).pathname;
      if (path.endsWith("/turn") || path.endsWith("/audio")) requests.push(path.split("/").pop() ?? "");
    });
  }
  await customer.goto(`${REPLAY}/customer.html`);
  await customer.locator("#language").selectOption("kn");
  await customer.getByRole("button", { name: ui("kn", "create_room") }).click();
  await expect(customer.locator("#code")).toHaveText(/^[A-Z0-9]{6}$/);
  const code = (await customer.locator("#code").textContent()) ?? "";
  await rider.goto(`${REPLAY}/rider.html?code=${code}`);
  await rider.locator("#language").selectOption("bn"); // never recorded for this clip
  await rider.getByRole("button", { name: ui("bn", "join_and_sound") }).click();
  await expect(customer.locator("#peer")).toContainText(ui.has("kn", "rider_joined"));

  await customer.locator("#demo-clip").selectOption("clip-kn");
  await customer.locator("#demo-send").click();
  await expect(rider.locator("#card-chips .chip-gate .chip-value")).toHaveText("2");
  await expect(rider.locator("#translation")).not.toHaveText("");
  await expect(rider.locator("#demo-badge")).toBeVisible();
  await expect(rider.locator("#incoming-status")).not.toContainText(ui.has("bn", "audio_failed"));
  await expect(rider.locator("#incoming-status")).not.toContainText(ui.has("bn", "speech_unavailable"));
  await expect(customer.locator("#sent-demo-badge")).toBeVisible();
  // One turn request, and the audio route was never asked for: no 404, so no retry either.
  expect(requests).toEqual(["turn"]);
  expect(problems).toEqual([]);
});

// A stored turn is a lookup that times nothing; the speaker's screen must not print "0.0 s" for it.
for (const riderLanguage of ["hi", "bn"]) {
  test(`replay: the speaker sees no timing readout for a stored turn (${riderLanguage} rider)`, async ({
    browser,
  }) => {
    const REPLAY = "http://127.0.0.1:8768"; // tests/e2e/serve.py --replay: bundle holds kn -> hi only
    const customer = await (await browser.newContext()).newPage();
    const rider = await (await browser.newContext()).newPage();
    await customer.goto(`${REPLAY}/customer.html`);
    await customer.locator("#language").selectOption("kn");
    await customer.getByRole("button", { name: ui("kn", "create_room") }).click();
    await expect(customer.locator("#code")).toHaveText(/^[A-Z0-9]{6}$/);
    const code = (await customer.locator("#code").textContent()) ?? "";
    await rider.goto(`${REPLAY}/rider.html?code=${code}`);
    await rider.locator("#language").selectOption(riderLanguage);
    await rider.getByRole("button", { name: ui(riderLanguage, "join_and_sound") }).click();
    await expect(customer.locator("#peer")).toContainText(ui.has("kn", "rider_joined"));

    await customer.locator("#demo-clip").selectOption("clip-kn");
    await customer.locator("#demo-send").click();
    await expect(customer.locator("#sent-demo-badge")).toBeVisible(); // the turn has come back
    await expect(customer.locator("#timings-box")).toBeHidden();
  });
}

test.describe("phone, 412 px wide", () => {
  test.use({ viewport: { width: 412, height: 800 } });

  test("split-screen page stacks two panes that fill the viewport height, with no sideways scroll", async ({
    page,
  }) => {
    await page.goto(`${DEMO}/demo.html`);
    const customer = await page.locator(".pane-customer").boundingBox();
    const rider = await page.locator(".pane-rider").boundingBox();
    const stage = await page.locator(".stage").boundingBox();
    if (!customer || !rider || !stage) throw new Error("layout missing");
    expect(rider.y).toBeGreaterThanOrEqual(customer.y + customer.height - 1); // stacked
    expect(stage.height).toBeGreaterThanOrEqual(800 - 1); // 100dvh at least
    expect(Math.abs(customer.height - rider.height)).toBeLessThan(2);
    const overflow = await page.evaluate(
      () => document.documentElement.scrollWidth - document.documentElement.clientWidth,
    );
    expect(overflow).toBeLessThanOrEqual(0);
  });

  test("demo banner wraps and is shown in full, and a long name wraps between words", async ({
    page,
  }) => {
    await page.goto(`${DEMO}/customer.html`);
    await page.locator("#language").selectOption("kn");
    await page.getByRole("button", { name: ui("kn", "create_room") }).click();
    await expect(page.locator("#demo-banner")).toBeVisible();
    await expect(page.locator("#code")).toHaveText(/^[A-Z0-9]{6}$/);
    const clipped = await page.evaluate(() =>
      [...document.querySelectorAll("#demo-banner > span")].map(
        (s) => s.scrollWidth > s.clientWidth + 1,
      ),
    );
    expect(clipped).toEqual([false, false]);
    const wrap = await page.evaluate(() => {
      const el = document.createElement("span");
      el.className = "chip-value";
      document.body.append(el);
      const style = getComputedStyle(el);
      return [style.overflowWrap, style.wordBreak];
    });
    expect(wrap).toEqual(["break-word", "normal"]);
    const overflow = await page.evaluate(
      () => document.documentElement.scrollWidth - document.documentElement.clientWidth,
    );
    expect(overflow).toBeLessThanOrEqual(0);
  });
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

// The single-phone page needs the legacy /turn route, which public mode switches off, so the home
// page links to it only where it works. The link starts hidden and /features reveals it.
const SOLO_LINK = "Single-phone test page";

test("local mode: the home page links to the single-phone test page", async ({ page }) => {
  await page.goto(`${NORMAL}/index.html`);
  await expect(page.getByRole("link", { name: SOLO_LINK })).toBeVisible();
});

test("public mode: the home page does not link to the single-phone test page", async ({ page }) => {
  const REPLAY = "http://127.0.0.1:8768"; // tests/e2e/serve.py --replay: public mode
  const features = page.waitForResponse((r) => new URL(r.url()).pathname === "/features");
  await page.goto(`${REPLAY}/index.html`);
  await features;
  await page.waitForLoadState("networkidle"); // landing.js has acted on the answer by now
  await expect(page.getByRole("link", { name: SOLO_LINK })).toBeHidden();
  // The paragraph that holds the link takes no space either, so the public page has no gap there.
  await expect(page.locator(".landing .sub")).toHaveCSS("display", "none");
  await expect(page.getByRole("link", { name: "Both screens side by side (demo)" })).toBeVisible();
});
