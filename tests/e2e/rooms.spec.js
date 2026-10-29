// @ts-check
import { expect, test } from "@playwright/test";

/**
 * Collect console errors and page errors; any entry fails the test.
 * @param {import("@playwright/test").Page} page
 */
function watchConsole(page) {
  /** @type {string[]} */
  const problems = [];
  page.on("console", (message) => {
    if (["error", "warning"].includes(message.type())) problems.push(message.text());
  });
  page.on("pageerror", (error) => problems.push(error.message));
  return problems;
}

// The pair is an arbitrary example; nothing in the app ties a role to a language.
test("both roles speak and reply in ta and ml: chips, audio, repeat, quick replies", async ({
  browser,
}) => {
  const customerContext = await browser.newContext();
  const riderContext = await browser.newContext();
  await customerContext.grantPermissions(["microphone"]);
  const customer = await customerContext.newPage();
  const rider = await riderContext.newPage();
  const problems = [...watchConsole(customer), ...watchConsole(rider)];
  /** @type {string[]} */
  const audioFetches = [];
  rider.on("request", (request) => {
    if (/\/turns\/[^/]+\/audio$/.test(request.url())) audioFetches.push(request.url());
  });

  // The picker offers all 10 languages with tier labels (plus the placeholder).
  await customer.goto("/customer.html");
  await expect(customer.locator("#language option")).toHaveCount(11);
  await expect(customer.locator("#language option", { hasText: "Tamil (beta)" })).toHaveCount(1);
  await customer.locator("#language").selectOption("ta");
  await customer.getByRole("button", { name: "Create room" }).click();
  await expect(customer.locator("#code")).toHaveText(/^[A-Z0-9]{6}$/);
  const code = (await customer.locator("#code").textContent()) ?? "";
  await expect(customer.locator("#talk")).toBeDisabled();

  // Rider joins in Malayalam with the code, via the link the customer sees.
  const link = (await customer.locator("#link").textContent()) ?? "";
  expect(link).toContain(`/rider.html?code=${code}`);
  await rider.goto(`/rider.html?code=${code}`);
  await rider.locator("#language").selectOption("ml");
  await rider.getByRole("button", { name: /Join/ }).click();
  await expect(rider.locator("#room")).toBeVisible();
  await expect(customer.locator("#peer")).toContainText("Rider joined");
  await expect(customer.locator("#talk")).toBeEnabled();

  // Customer speaks (fake microphone); both screens show the same chips.
  await customer.locator("#talk").click();
  await expect(customer.locator("#status")).toContainText("Recording");
  await customer.waitForTimeout(1500); // let the fake microphone produce some audio
  await customer.locator("#talk").click();
  await expect(customer.locator("#sent-chips .chip-gate .chip-value")).toHaveText("2");
  await expect(rider.locator("#chips .chip-gate .chip-value")).toHaveText("2");
  await expect(rider.locator("#chips .chip-floor .chip-value")).toHaveText("3");
  // Only the speaker sees the stage timings of the turn they sent.
  await expect(customer.locator("#timings dt")).toHaveText([
    "Speech to text",
    "Translation",
    "Text to speech",
    "Server total",
  ]);
  await expect(customer.locator("#timings dd")).toHaveText([/^\d+ ms$/, /^\d+ ms$/, /^\d+ ms$/, /^\d+ ms$/]);
  await expect(rider.locator("#timings")).toBeHidden();
  // Numbers match on both screens; the landmark differs on purpose. The speaker sees what was
  // said; the listener sees a translation in their script plus the original in brackets, or, as
  // with this fake translator (Latin text, not the listener's script), the original alone.
  await expect(customer.locator("#sent-chips .chip-landmark .chip-value")).toHaveText(
    "blue temple",
  );
  await expect(rider.locator("#chips .chip-landmark .chip-value")).toHaveText("blue temple");

  // Translation is shown as literal text (the fake translator returns markup on purpose).
  await expect(rider.locator("#translation")).toContainText("<b>ml</b>");
  await expect(rider.locator("#translation b")).toHaveCount(0);

  // The audio auto-played from one fetch; Repeat replays it without another call.
  await expect(rider.locator("#repeat")).toBeEnabled();
  expect(audioFetches).toHaveLength(1);
  await rider.locator("#repeat").click();
  await rider.waitForTimeout(300);
  expect(audioFetches).toHaveLength(1);

  // The rider speaks too: the customer gets the translation and chips, the rider sees their own.
  await rider.locator("#talk").click();
  await expect(rider.locator("#status")).toContainText("Recording");
  await rider.waitForTimeout(1500);
  await rider.locator("#talk").click();
  await expect(rider.locator("#sent-chips .chip-gate .chip-value")).toHaveText("2");
  await expect(customer.locator("#chips .chip-gate .chip-value")).toHaveText("2");
  await expect(customer.locator("#translation")).toContainText("<b>ta</b>");
  await expect(customer.locator("#repeat")).toBeEnabled();
  await expect(customer.locator("#repeat-prompt")).toBeHidden();
  await expect(rider.locator("#repeat-prompt")).toBeHidden();

  // Quick replies go both ways, each in the recipient's language, with a review warning. Expected
  // texts come from the catalog so the test does not hardcode any phrase.
  const catalog = await (await customer.request.get("/quick-replies")).json();
  const text = (/** @type {string} */ language, /** @type {string} */ id) =>
    catalog.languages[language][id].text;

  await rider.getByRole("button", { name: text("ml", "which_floor") }).click();
  await expect(customer.locator("#reply-text")).toHaveText(text("ta", "which_floor"));
  await expect(customer.locator("#reply-note")).toContainText("Unreviewed machine translation");

  await customer.getByRole("button", { name: text("ta", "come_to_gate") }).click();
  await expect(rider.locator("#reply-text")).toHaveText(text("ml", "come_to_gate"));
  await expect(rider.locator("#reply-note")).toContainText("Unreviewed machine translation");

  expect(problems).toEqual([]);
});

test("a repeat request shows in the speaker's language and clears on the next send", async ({
  browser,
}) => {
  const speakerContext = await browser.newContext();
  const listenerContext = await browser.newContext();
  await speakerContext.grantPermissions(["microphone"]);
  const speaker = await speakerContext.newPage();
  const listener = await listenerContext.newPage();
  const problems = watchConsole(speaker);

  await speaker.goto("/customer.html");
  await speaker.locator("#language").selectOption("hi");
  await speaker.getByRole("button", { name: "Create room" }).click();
  await expect(speaker.locator("#code")).toHaveText(/^[A-Z0-9]{6}$/);
  const code = (await speaker.locator("#code").textContent()) ?? "";
  await listener.goto(`/rider.html?code=${code}`);
  await listener.locator("#language").selectOption("bn");
  await listener.getByRole("button", { name: /Join/ }).click();
  await expect(speaker.locator("#talk")).toBeEnabled();

  // The server's answer is replaced by one that asks for a repeat.
  const prompt = "SAMPLE repeat prompt";
  await speaker.route("**/rooms/*/turn", (route) =>
    route.fulfill({
      json: {
        turn_id: "t1",
        facts: [],
        verified: true,
        timings: { stt_ms: 1, translate_ms: 2, tts_ms: 3, total_ms: 6 },
        repeat: { reason: "no_facts", text: prompt, review_status: "pending" },
      },
    }),
  );
  await speaker.locator("#talk").click();
  await speaker.waitForTimeout(1500);
  await speaker.locator("#talk").click();
  await expect(speaker.locator("#repeat-text")).toHaveText(prompt);
  await expect(speaker.locator("#repeat-text")).toHaveAttribute("lang", "hi");
  await expect(speaker.locator("#repeat-note")).toContainText("Unreviewed machine translation");
  await expect(speaker.locator("#talk")).toBeEnabled(); // asking to repeat never blocks sending

  // A normal turn goes through the real server and the prompt disappears.
  await speaker.unroute("**/rooms/*/turn");
  await speaker.locator("#talk").click();
  await speaker.waitForTimeout(1500);
  await speaker.locator("#talk").click();
  await expect(speaker.locator("#sent-chips .chip-gate .chip-value")).toHaveText("2");
  await expect(speaker.locator("#repeat-prompt")).toBeHidden();
  expect(problems).toEqual([]);
});

test("rider cannot join with a wrong code and sees a safe message", async ({ page }) => {
  const problems = watchConsole(page);
  await page.goto("/rider.html");
  await page.locator("#language").selectOption("ml");
  await page.locator("#code-input").fill("ABC");
  await page.getByRole("button", { name: /Join/ }).click();
  await expect(page.locator("#join-status")).toContainText("6-character");
  await page.locator("#code-input").fill("ZZZZZZ");
  await page.getByRole("button", { name: /Join/ }).click();
  await expect(page.locator("#join-status")).toContainText("not found");
  // The 404 is an expected response; Chromium logs it, nothing else may appear.
  expect(problems.filter((text) => !/status of 404/.test(text))).toEqual([]);
});

test("neither screen preselects a language and both offer all 10", async ({ page }) => {
  await page.goto("/customer.html");
  await expect(page.locator("#language")).toHaveValue("");
  await expect(page.locator("#language option")).toHaveCount(11); // placeholder + 10
  await expect(page.getByRole("button", { name: "Create room" })).toBeDisabled();
  await page.locator("#language").selectOption("gu");
  await expect(page.getByRole("button", { name: "Create room" })).toBeEnabled();

  await page.goto("/rider.html");
  await expect(page.locator("#language")).toHaveValue("");
  await expect(page.locator("#language option")).toHaveCount(11);
  await expect(page.getByRole("button", { name: /Join/ })).toBeDisabled();
});
