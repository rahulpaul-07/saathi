// @ts-check
import { expect, test } from "@playwright/test";
import { loadUi, makeUi } from "./chrome-text.js";

/** The interface text a viewer in a language sees. @type {(language: string, key: string) => string} */
/** @type {ReturnType<typeof makeUi>} */
let ui = makeUi({});
test.beforeAll(async ({ playwright }) => {
  ui = await loadUi(playwright, "http://127.0.0.1:8765");
});

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
  await customer.getByRole("button", { name: ui("ta", "create_room") }).click();
  await expect(customer.locator("#code")).toHaveText(/^[A-Z0-9]{6}$/);
  const code = (await customer.locator("#code").textContent()) ?? "";
  await expect(customer.locator("#talk")).toBeDisabled();

  // Rider joins in Malayalam with the code, via the link the customer sees.
  const link = (await customer.locator("#link").textContent()) ?? "";
  expect(link).toContain(`/rider.html?code=${code}`);
  await rider.goto(`/rider.html?code=${code}`);
  await rider.locator("#language").selectOption("ml");
  await rider.getByRole("button", { name: ui("ml", "join_and_sound") }).click();
  await expect(rider.locator("#room")).toBeVisible();
  await expect(customer.locator("#peer")).toContainText(ui.has("ta", "rider_joined"));
  await expect(customer.locator("#talk")).toBeEnabled();

  // Customer speaks (fake microphone); both screens show the same chips.
  await customer.locator("#talk").click();
  await expect(customer.locator("#status")).toContainText(ui.has("ta", "recording"));
  await customer.waitForTimeout(1500); // let the fake microphone produce some audio
  await customer.locator("#talk").click();
  await expect(rider.locator("#translation")).toContainText("<b>ml</b>");
  // A customer turn has no per-turn chips on either screen: the card below is the one place the
  // facts appear, so no value shows twice.
  await expect(customer.locator("#sent-chips .chip")).toHaveCount(0);
  await expect(customer.locator("#sent-empty")).toHaveText(ui("ta", "sent_card_has_details"));
  await expect(rider.locator("#chips .chip")).toHaveCount(0);
  // The pinned card collects the customer's facts on both screens, with no "changed" marker yet.
  for (const page of [customer, rider]) {
    await expect(page.locator("#card-chips .chip-gate .chip-value")).toHaveText("2");
    await expect(page.locator("#card-chips .chip-floor .chip-value")).toHaveText("3");
    await expect(page.locator("#card-empty")).toBeHidden();
    await expect(page.locator("#card-chips .chip-changed")).toHaveCount(0);
  }
  // Only the speaker sees the stage timings of the turn they sent.
  await expect(customer.locator("#timings dt")).toHaveText([
    ui("ta", "time_stt"),
    ui("ta", "time_translate"),
    ui("ta", "time_tts"),
    ui("ta", "time_total"),
  ]);
  await expect(customer.locator("#timings dd")).toHaveText([/^\d+ ms$/, /^\d+ ms$/, /^\d+ ms$/, /^\d+ ms$/]);
  await expect(rider.locator("#timings")).toBeHidden();
  // Numbers match on both screens; the landmark differs on purpose. The speaker sees what was
  // said; the listener sees a translation in their script plus the original in brackets, or, as
  // with this fake translator (Latin text, not the listener's script), the original alone.
  await expect(customer.locator("#card-chips .chip-landmark .chip-value")).toHaveText(
    "blue temple",
  );
  await expect(rider.locator("#card-chips .chip-landmark .chip-value")).toHaveText("blue temple");

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
  await expect(rider.locator("#status")).toContainText(ui.has("ml", "recording"));
  await rider.waitForTimeout(1500);
  await rider.locator("#talk").click();
  await expect(rider.locator("#sent-chips .chip-gate .chip-value")).toHaveText("2");
  await expect(customer.locator("#chips .chip-gate .chip-value")).toHaveText("2");
  await expect(customer.locator("#translation")).toContainText("<b>ta</b>");
  await expect(customer.locator("#repeat")).toBeEnabled();
  // A rider turn does not touch the card.
  await expect(customer.locator("#card-chips .chip")).toHaveCount(3);
  await expect(customer.locator("#repeat-prompt")).toBeHidden();
  await expect(rider.locator("#repeat-prompt")).toBeHidden();

  // Quick replies go both ways, each in the recipient's language, with a review warning. Expected
  // texts come from the catalog so the test does not hardcode any phrase.
  const catalog = await (await customer.request.get("/quick-replies")).json();
  const text = (/** @type {string} */ language, /** @type {string} */ id) =>
    catalog.languages[language][id].text;

  await rider.getByRole("button", { name: text("ml", "which_floor") }).click();
  await expect(customer.locator("#reply-text")).toHaveText(text("ta", "which_floor"));
  await expect(customer.locator("#reply-note")).toContainText(ui.has("ta", "unreviewed_translation"));

  await customer.getByRole("button", { name: text("ta", "come_to_gate") }).click();
  await expect(rider.locator("#reply-text")).toHaveText(text("ml", "come_to_gate"));
  await expect(rider.locator("#reply-note")).toContainText(ui.has("ml", "unreviewed_translation"));

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
  await speaker.getByRole("button", { name: ui("hi", "create_room") }).click();
  await expect(speaker.locator("#code")).toHaveText(/^[A-Z0-9]{6}$/);
  const code = (await speaker.locator("#code").textContent()) ?? "";
  await listener.goto(`/rider.html?code=${code}`);
  await listener.locator("#language").selectOption("bn");
  await listener.getByRole("button", { name: ui("bn", "join_and_sound") }).click();
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
  await expect(speaker.locator("#repeat-note")).toContainText(ui.has("hi", "unreviewed_translation"));
  await expect(speaker.locator("#talk")).toBeEnabled(); // asking to repeat never blocks sending

  // A normal turn goes through the real server and the prompt disappears.
  await speaker.unroute("**/rooms/*/turn");
  await speaker.locator("#talk").click();
  await speaker.waitForTimeout(1500);
  await speaker.locator("#talk").click();
  await expect(speaker.locator("#status")).toContainText(ui.has("hi", "sent"));
  await expect(speaker.locator("#card-chips .chip-gate .chip-value")).toHaveText("2");
  await expect(speaker.locator("#repeat-prompt")).toBeHidden();
  expect(problems).toEqual([]);
});

test("rider cannot join with a wrong code and sees a safe message", async ({ page }) => {
  const problems = watchConsole(page);
  await page.goto("/rider.html");
  await page.locator("#language").selectOption("ml");
  await page.locator("#code-input").fill("ABC");
  await page.getByRole("button", { name: ui("ml", "join_and_sound") }).click();
  await expect(page.locator("#join-status")).toHaveText(ui("ml", "enter_code"));
  await page.locator("#code-input").fill("ZZZZZZ");
  await page.getByRole("button", { name: ui("ml", "join_and_sound") }).click();
  await expect(page.locator("#join-status")).toHaveText(ui("ml", "room_not_found"));
  // The 404 is an expected response; Chromium logs it, nothing else may appear.
  expect(problems.filter((text) => !/status of 404/.test(text))).toEqual([]);
});

test("neither screen preselects a language and both offer all 10", async ({ page }) => {
  await page.goto("/customer.html");
  await expect(page.locator("#language")).toHaveValue("");
  await expect(page.locator("#language option")).toHaveCount(11); // placeholder + 10
  await expect(page.getByRole("button", { name: ui("en", "create_room") })).toBeDisabled();
  await page.locator("#language").selectOption("gu");
  await expect(page.getByRole("button", { name: ui("gu", "create_room") })).toBeEnabled();

  await page.goto("/rider.html");
  await expect(page.locator("#language")).toHaveValue("");
  await expect(page.locator("#language option")).toHaveCount(11);
  await expect(page.getByRole("button", { name: ui("en", "join_and_sound") })).toBeDisabled();
});

// The fake STT alternates gate 2 and gate 4 for a Punjabi speaker, so the second turn changes a value.
test("the rider confirms or asks on card chips; a changed value stays marked until confirmed", async ({
  browser,
}) => {
  const customerContext = await browser.newContext();
  const riderContext = await browser.newContext();
  await customerContext.grantPermissions(["microphone"]);
  const customer = await customerContext.newPage();
  const rider = await riderContext.newPage();
  const problems = [...watchConsole(customer), ...watchConsole(rider)];

  await customer.goto("/customer.html");
  await customer.locator("#language").selectOption("pa");
  await customer.getByRole("button", { name: ui("pa", "create_room") }).click();
  await expect(customer.locator("#code")).toHaveText(/^[A-Z0-9]{6}$/);
  const code = (await customer.locator("#code").textContent()) ?? "";
  await rider.goto(`/rider.html?code=${code}`);
  await rider.locator("#language").selectOption("hi");
  await rider.getByRole("button", { name: ui("hi", "join_and_sound") }).click();
  await expect(customer.locator("#talk")).toBeEnabled();

  const speak = async () => {
    await customer.locator("#talk").click();
    await expect(customer.locator("#status")).toContainText(ui.has("pa", "recording"));
    await customer.waitForTimeout(1500);
    await customer.locator("#talk").click();
  };
  const gate = (/** @type {import("@playwright/test").Page} */ page) =>
    page.locator("#card-chips .chip-gate");

  await speak();
  await expect(gate(rider).locator(".chip-value")).toHaveText("2");
  // Only the listener has controls; the customer has none.
  await expect(customer.locator("#card-chips button")).toHaveCount(0);
  await expect(gate(rider).locator(".chip-confirm")).toHaveCount(1);

  // A changed value is marked on both screens.
  await speak();
  for (const page of [customer, rider]) {
    await expect(gate(page).locator(".chip-value")).toHaveText("4");
    await expect(gate(page).locator(".chip-note")).toHaveText(
      ui.with(page === customer ? "pa" : "hi", "changed_was", "2"),
    );
  }

  // Ask: the customer sees the question in their own language; the marker stays.
  const askButton = gate(rider).locator(".chip-ask");
  const riderQuestion = (await askButton.textContent()) ?? "";
  expect(riderQuestion.endsWith("?")).toBe(true);
  await askButton.click();
  await expect(gate(customer).locator(".chip-question")).toHaveText(/\?$/);
  await expect(gate(customer).locator(".chip-note")).toHaveText(ui.with("pa", "changed_was", "2"));

  // Confirm: the marker and the question go, the customer sees a check.
  await gate(rider).locator(".chip-confirm").click();
  await expect(gate(customer).locator(".chip-note")).toHaveCount(0);
  await expect(gate(customer).locator(".chip-question")).toHaveCount(0);
  await expect(gate(customer).locator(".icon-check")).toHaveCount(1);
  await expect(gate(rider).locator(".chip-changed")).toHaveCount(0);

  // A newer value after a confirmation marks the chip again and drops the check. (Reconnect state
  // is covered by the API test: a reload leaves the room.)
  await speak();
  await expect(gate(customer).locator(".chip-value")).toHaveText("2");
  await expect(gate(customer).locator(".chip-note")).toHaveText(ui.with("pa", "changed_was", "4"));
  await expect(gate(customer).locator(".icon-check")).toHaveCount(0);

  expect(problems).toEqual([]);
});

/**
 * A customer (ta) and a rider (ml) in one room; the pair is an arbitrary example.
 * @param {import("@playwright/test").Browser} browser
 */
async function openRoom(browser) {
  const customerContext = await browser.newContext();
  const riderContext = await browser.newContext();
  await customerContext.grantPermissions(["microphone"]);
  const customer = await customerContext.newPage();
  const rider = await riderContext.newPage();
  const problems = [...watchConsole(customer), ...watchConsole(rider)];
  await customer.goto("/customer.html");
  await customer.locator("#language").selectOption("ta");
  await customer.getByRole("button", { name: ui("ta", "create_room") }).click();
  await expect(customer.locator("#code")).toHaveText(/^[A-Z0-9]{6}$/);
  const code = (await customer.locator("#code").textContent()) ?? "";
  await rider.goto(`/rider.html?code=${code}`);
  await rider.locator("#language").selectOption("ml");
  await rider.getByRole("button", { name: ui("ml", "join_and_sound") }).click();
  await expect(customer.locator("#talk")).toBeEnabled();
  return { customer, rider, problems };
}

/**
 * @param {import("@playwright/test").Page} page
 * @param {string} language the language of this page
 */
async function speak(page, language) {
  await page.locator("#talk").click();
  await expect(page.locator("#status")).toContainText(ui.has(language, "recording"));
  await page.waitForTimeout(1500);
  await page.locator("#talk").click();
}

test("a reload rejoins the room and catches up the last message without playing it", async ({
  browser,
}) => {
  const { customer, rider, problems } = await openRoom(browser);
  /** @type {string[]} */
  const played = [];
  rider.on("request", (request) => {
    if (/\/turns\/[^/]+\/audio$/.test(request.url())) played.push(request.url());
  });

  // The pages carry the policy and still work under it (the console watcher would catch a block).
  const page = await rider.request.get("/rider.html");
  expect(page.headers()["content-security-policy"]).toContain("script-src 'self'");
  expect(page.headers()["content-security-policy"]).toContain("frame-ancestors 'none'");

  await speak(customer, "ta");
  await expect(rider.locator("#card-chips .chip-gate .chip-value")).toHaveText("2");
  await expect(rider.locator("#translation")).not.toBeEmpty();
  expect(played).toHaveLength(1);

  await rider.reload();
  await expect(rider.locator("#room")).toBeVisible();
  await expect(rider.locator("#setup")).toBeHidden();
  await expect(rider.locator("#peer")).toContainText(ui.has("ml", "customer_joined"));
  await expect(rider.locator("#card-chips .chip-gate .chip-value")).toHaveText("2");
  await expect(rider.locator("#translation")).not.toBeEmpty();
  await expect(rider.locator("#incoming-status")).toContainText(ui.has("ml", "last_message_customer"));
  await expect(rider.locator("#repeat")).toBeEnabled();
  expect(played).toHaveLength(2); // fetched to be ready for Repeat, but not auto-played

  // The customer reloads too and is still in the same room.
  await customer.reload();
  await expect(customer.locator("#room")).toBeVisible();
  await expect(customer.locator("#peer")).toContainText(ui.has("ta", "rider_joined"));
  await expect(customer.locator("#talk")).toBeEnabled();

  expect(problems).toEqual([]);
});

test("a dropped stream shows Reconnecting and recovers by itself", async ({ browser }) => {
  const { rider, problems } = await openRoom(browser);
  await rider.route("**/events", (route) => route.abort());
  await rider.reload();
  await expect(rider.locator("#reconnecting")).toBeVisible();

  await rider.unroute("**/events");
  await expect(rider.locator("#reconnecting")).toBeHidden({ timeout: 15_000 });
  await expect(rider.locator("#peer")).toContainText(ui.has("ml", "customer_joined"));
  // Failed fetches are logged by the browser as console errors; nothing else may be.
  expect(problems.filter((text) => !text.includes("ERR_FAILED"))).toEqual([]);
});

test("when the room ends the other side returns to the join screen with a message", async ({
  browser,
}) => {
  const { customer, rider, problems } = await openRoom(browser);
  await customer.getByRole("button", { name: ui("ta", "end_room") }).click();

  await expect(rider.locator("#setup")).toBeVisible();
  await expect(rider.locator("#join-status")).toHaveText(ui("ml", "room_ended"));
  await expect(rider.locator("#room")).toBeHidden();
  // The stored session is gone, so another reload stays on the join screen.
  await rider.reload();
  await expect(rider.locator("#setup")).toBeVisible();
  await expect(rider.locator("#join-status")).toHaveText("");

  await expect(customer.locator("#setup")).toBeVisible();
  expect(problems).toEqual([]);
});

test("on a phone, ask and confirm on different chips each send exactly one chip-reply, and a re-render keeps untouched buttons", async ({
  browser,
}) => {
  const customerContext = await browser.newContext();
  const riderContext = await browser.newContext({
    viewport: { width: 360, height: 740 },
    hasTouch: true,
    isMobile: true,
  });
  await customerContext.grantPermissions(["microphone"]);
  const customer = await customerContext.newPage();
  const rider = await riderContext.newPage();
  const problems = [...watchConsole(customer), ...watchConsole(rider)];
  /** @type {string[]} */
  const posts = [];
  rider.on("request", (request) => {
    if (request.method() === "POST") posts.push(new URL(request.url()).pathname.split("/").pop() ?? "");
  });
  await customer.goto("/customer.html");
  await customer.locator("#language").selectOption("pa");
  await customer.getByRole("button", { name: ui("pa", "create_room") }).click();
  await expect(customer.locator("#code")).toHaveText(/^[A-Z0-9]{6}$/);
  const code = (await customer.locator("#code").textContent()) ?? "";
  await rider.goto(`/rider.html?code=${code}`);
  await rider.locator("#language").selectOption("hi");
  await rider.getByRole("button", { name: ui("hi", "join_and_sound") }).click();
  await expect(customer.locator("#talk")).toBeEnabled();
  await speak(customer, "pa");
  await expect(rider.locator("#card-chips .chip-floor")).toBeVisible();
  posts.length = 0;

  // Every card button is what a finger would hit at its centre (nothing overlaps it).
  const covered = await rider.evaluate(() =>
    [...document.querySelectorAll("#card-chips button")].filter((button) => {
      button.scrollIntoView({ block: "center" });
      const box = button.getBoundingClientRect();
      const top = document.elementFromPoint(box.x + box.width / 2, box.y + box.height / 2);
      return top !== button && !button.contains(top);
    }).length,
  );
  expect(covered).toBe(0);

  await rider.locator("#card-chips .chip-gate .chip-confirm").tap();
  await expect(rider.locator("#card-chips .chip-gate .icon-check").first()).toBeVisible();
  await rider.locator("#card-chips .chip-floor .chip-ask").tap();
  await expect(customer.locator("#card-chips .chip-floor .chip-question")).toHaveText(/\?$/);
  expect(posts).toEqual(["chip-reply", "chip-reply"]); // no quick-reply among them

  // A new customer turn changes the gate only: the floor chip and its buttons are the same
  // elements afterwards, so a tap in progress on them would not be lost.
  await expect(rider.locator("#card-chips .chip-floor .chip-question")).toHaveText(/\?$/); // echo done
  const floorAsk = await rider.locator("#card-chips .chip-floor .chip-ask").elementHandle();
  await speak(customer, "pa");
  await expect(rider.locator("#card-chips .chip-gate .chip-value")).toHaveText("4");
  expect(await floorAsk?.evaluate((el) => el.isConnected)).toBe(true);
  expect(problems).toEqual([]);
});

test("the customer's 'nothing received' placeholder goes away once a reply arrives", async ({
  browser,
}) => {
  const { customer, rider, problems } = await openRoom(browser);
  await expect(customer.locator("#incoming-status")).toHaveText(ui("ta", "nothing_received"));

  const catalog = await (await customer.request.get("/quick-replies")).json();
  await rider.getByRole("button", { name: catalog.languages.ml.which_floor.text }).click();
  await expect(customer.locator("#reply")).toBeVisible();
  await expect(customer.locator("#incoming-status")).toBeHidden();

  // A later spoken turn brings the status line back with its own message.
  await speak(rider, "ml");
  await expect(customer.locator("#incoming-status")).toContainText(ui.has("ta", "new_message_rider"));
  expect(problems).toEqual([]);
});
