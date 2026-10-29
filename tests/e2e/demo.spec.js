// @ts-check
import { expect, test } from "@playwright/test";

const DEMO = "http://127.0.0.1:8766"; // tests/e2e/serve.py --demo
const NORMAL = "http://127.0.0.1:8765";

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
  await customer.getByRole("button", { name: "Create room" }).click();
  await expect(customer.locator("#demo-banner")).toBeVisible();
  const code = (await customer.locator("#code").textContent()) ?? "";
  await rider.goto(`${DEMO}/rider.html?code=${code}`);
  await rider.locator("#language").selectOption("bn");
  await rider.getByRole("button", { name: /Join/ }).click();
  await expect(customer.locator("#peer")).toContainText("Rider joined");

  // The picker offers only clips in the speaker's own language.
  await expect(customer.locator("#demo-clip option")).toHaveText(["Sample kn"]);
  await expect(customer.locator("#sent-demo-badge")).toBeHidden();
  await customer.locator("#demo-send").click();
  await expect(rider.locator("#chips .chip-gate .chip-value")).toHaveText("2");
  await expect(rider.locator("#demo-badge")).toBeVisible();
  await expect(customer.locator("#sent-demo-badge")).toBeVisible();
  expect(problems).toEqual([]);
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
  await page.frameLocator("#customer-frame").getByRole("button", { name: "Create room" }).click();
  const code = await page.frameLocator("#customer-frame").locator("#code").textContent();
  await expect(page.frameLocator("#rider-frame").locator("#code-input")).toHaveValue(code ?? "");
});
