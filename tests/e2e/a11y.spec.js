// @ts-check
// Accessibility checks that need no extra tools: tap target size, accessible names and colour
// contrast of the design tokens. Room pages are checked at 360 px wide, the smallest supported.
import { expect, test } from "@playwright/test";
import { loadUi } from "./chrome-text.js";

/** The interface text a viewer in a language sees. @type {(language: string, key: string) => string} */
let ui = () => "";
test.beforeAll(async ({ playwright }) => {
  ui = await loadUi(playwright, "http://127.0.0.1:8765");
});

const MIN_TARGET_PX = 44;
const INTERACTIVE = "button, a[href], select, input, textarea, [role=button]";

/**
 * @param {import("@playwright/test").Page} page
 * @param {string} scope css selector limiting the check, or "body"
 */
async function interactiveReport(page, scope = "body") {
  return page.evaluate(
    ({ scope, selector, min }) => {
      /** @param {Element} el */
      const nameOf = (el) => {
        const labelled = el.getAttribute("aria-labelledby");
        if (labelled) {
          const text = labelled
            .split(/\s+/)
            .map((id) => document.getElementById(id)?.textContent ?? "")
            .join(" ")
            .trim();
          if (text) return text;
        }
        const aria = el.getAttribute("aria-label")?.trim();
        if (aria) return aria;
        const labels = /** @type {HTMLInputElement} */ (el).labels;
        if (labels && labels.length) return [...labels].map((l) => l.textContent).join(" ").trim();
        const own = (el.textContent ?? "").trim();
        if (own) return own;
        return el.getAttribute("title")?.trim() ?? "";
      };
      /** @type {{unnamed: string[], small: string[]}} */
      const report = { unnamed: [], small: [] };
      for (const el of document.querySelectorAll(`${scope} ${selector}`)) {
        const box = el.getBoundingClientRect();
        if (box.width === 0 || box.height === 0) continue; // hidden
        if (/** @type {HTMLInputElement} */ (el).type === "hidden") continue;
        const id = el.id ? `#${el.id}` : `${el.tagName.toLowerCase()}.${el.className}`;
        if (nameOf(el) === "") report.unnamed.push(id);
        if (box.height < min || box.width < min) {
          report.small.push(`${id} ${Math.round(box.width)}x${Math.round(box.height)}`);
        }
      }
      return report;
    },
    { scope, selector: INTERACTIVE, min: MIN_TARGET_PX },
  );
}

/**
 * Both people in one room at 360 px, with the customer's turn on the card.
 * @param {import("@playwright/test").Browser} browser
 */
async function roomAt360(browser) {
  const size = { width: 360, height: 740 };
  const customerContext = await browser.newContext({ viewport: size });
  const riderContext = await browser.newContext({ viewport: size });
  await customerContext.grantPermissions(["microphone"]);
  const customer = await customerContext.newPage();
  const rider = await riderContext.newPage();
  await customer.goto("/customer.html");
  await customer.locator("#language").selectOption("ta");
  await customer.getByRole("button", { name: ui("ta", "create_room") }).click();
  await expect(customer.locator("#code")).toHaveText(/^[A-Z0-9]{6}$/);
  const code = (await customer.locator("#code").textContent()) ?? "";
  await rider.goto(`/rider.html?code=${code}`);
  await rider.locator("#language").selectOption("ml");
  await rider.getByRole("button", { name: ui("ml", "join_and_sound") }).click();
  await expect(customer.locator("#talk")).toBeEnabled();
  await customer.locator("#talk").click();
  await customer.waitForTimeout(1500); // let the fake microphone produce some audio
  await customer.locator("#talk").click();
  await expect(rider.locator("#card-chips .chip-gate")).toBeVisible();
  return { customer, rider };
}

test("room pages at 360 px: buttons and controls have names and are tappable", async ({
  browser,
}) => {
  const { customer, rider } = await roomAt360(browser);
  for (const page of [customer, rider]) {
    const report = await interactiveReport(page, "main");
    expect(report.unnamed, "controls without an accessible name").toEqual([]);
    expect(report.small, `controls under ${MIN_TARGET_PX} px`).toEqual([]);
    const overflow = await page.evaluate(
      () => document.documentElement.scrollWidth - document.documentElement.clientWidth,
    );
    expect(overflow, "horizontal scroll").toBeLessThanOrEqual(0);
  }
});

test("join screens at 360 px: every control has a name", async ({ browser }) => {
  const context = await browser.newContext({ viewport: { width: 360, height: 740 } });
  const page = await context.newPage();
  for (const path of ["/index.html", "/customer.html", "/rider.html"]) {
    await page.goto(path);
    const report = await interactiveReport(page, "main");
    expect(report.unnamed, `${path} controls without a name`).toEqual([]);
  }
});

/** @param {string} hex */
function luminance(hex) {
  const [r, g, b] = [1, 3, 5].map((i) => {
    const c = parseInt(hex.slice(i, i + 2), 16) / 255;
    return c <= 0.03928 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4;
  });
  return 0.2126 * r + 0.7152 * g + 0.0722 * b;
}

/**
 * @param {string} a
 * @param {string} b
 */
function contrast(a, b) {
  const [hi, lo] = [luminance(a), luminance(b)].sort((x, y) => y - x);
  return (hi + 0.05) / (lo + 0.05);
}

// Text-on-background pairs the pages actually use. WCAG AA: 4.5 for normal text.
const PAIRS = [
  ["--text", "--bg"],
  ["--text", "--surface"],
  ["--muted", "--bg"],
  ["--muted", "--surface"],
  ["--accent", "--bg"],
  ["--accent", "--surface"],
  ["--accent-text", "--accent"],
  ["--danger", "--bg"],
  ["--danger", "--surface"],
];

for (const scheme of /** @type {const} */ (["light", "dark"])) {
  test(`colour tokens meet WCAG AA text contrast (${scheme})`, async ({ browser }) => {
    const context = await browser.newContext({ colorScheme: scheme });
    const page = await context.newPage();
    await page.goto("/rider.html");
    const tokens = await page.evaluate((names) => {
      const style = getComputedStyle(document.documentElement);
      return Object.fromEntries(names.map((n) => [n, style.getPropertyValue(n).trim()]));
    }, [...new Set(PAIRS.flat())]);
    for (const [fg, bg] of PAIRS) {
      const ratio = contrast(tokens[fg], tokens[bg]);
      expect(ratio, `${fg} on ${bg} (${scheme}) is ${ratio.toFixed(2)}`).toBeGreaterThanOrEqual(4.5);
    }
  });
}
