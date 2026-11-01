// Phone-sized rider-screen screenshots for docs/media (synthetic address, real local translation).
// Usage: node scripts/screenshots.mjs <replay.json>   (see scripts/screenshot_server.py)
import { spawn } from "node:child_process";
import { chromium } from "@playwright/test";

// Design mode: `node scripts/screenshots.mjs design <before|after>` drives the demo-mode app with
// scripted fakes (scripts/design_server.py) and writes docs/media/design/<set>/.
const DESIGN = process.argv[2] === "design";
const replay = DESIGN ? "" : process.argv[2];
const SHOTS = DESIGN ? [] : [
  { mode: "unmasked", port: 8771, file: "docs/media/rider-unmasked.png" },
  { mode: "masked", port: 8772, file: "docs/media/rider-masked.png" },
];

/** @param {string} url */
async function waitForServer(url) {
  for (let i = 0; i < 120; i++) {
    try {
      if ((await fetch(url)).ok) return;
    } catch {}
    await new Promise((resolve) => setTimeout(resolve, 500));
  }
  throw new Error("server did not start");
}

const browser = await chromium.launch({
  args: ["--use-fake-device-for-media-stream", "--use-fake-ui-for-media-stream"],
});

/** @param {number} port @returns {import("node:child_process").ChildProcess} */
function startDesignServer(port) {
  return spawn("uv", ["run", "--no-sync", "python", "scripts/design_server.py", String(port)], {
    stdio: "inherit",
  });
}

/** @param {import("node:child_process").ChildProcess} server */
function stopServer(server) {
  // uv spawns python as a child; kill the whole tree or the port stays bound.
  spawn("taskkill", ["/pid", String(server.pid), "/t", "/f"], { stdio: "ignore" });
}

/**
 * The five states, in order. `customer` and `rider` are a Page or a FrameLocator; `shoot` saves
 * every view that exists in this layout.
 * @param {any} customer @param {any} rider
 * @param {(state: string) => Promise<void>} shoot
 */
async function scenario(customer, rider, shootNow) {
  // Tiles pop in over 200 ms; wait it out so a capture never catches one mid-animation.
  const shoot = async (/** @type {string} */ state) => {
    await new Promise((resolve) => setTimeout(resolve, 400));
    await shootNow(state);
  };
  await customer.locator("#talk:not([disabled])").waitFor();
  await customer.locator("#demo-clip").waitFor(); // the send button waits for a chosen clip
  await shoot("1-empty-room");
  const send = async (/** @type {string} */ clip, /** @type {string} */ ready) => {
    await customer.locator("#demo-clip").selectOption(clip);
    await customer.locator("#demo-send:not([disabled])").click();
    await rider.locator(ready).waitFor();
  };
  await send("kn-bakery", "#card-chips .chip-landmark");
  await customer.locator("#timings-box:not([hidden])").waitFor();
  await shoot("2-first-clip");
  await send("kn-gate-correction", "#card-chips .chip-changed");
  await shoot("3-correction");
  await rider.locator("#card-chips .chip-gate .chip-confirm").click();
  await rider.locator("#card-chips .chip-main .chip-ask").click();
  await customer.locator("#card-chips .chip-confirmed").waitFor();
  await customer.locator("#card-chips .chip-question").waitFor();
  await shoot("4-confirm-and-ask");
  await rider.locator("#replies .reply-btn").first().click();
  await customer.locator("#reply:not([hidden])").waitFor();
  await shoot("5-quick-reply");
}

/** @param {string} set */
async function designShots(set) {
  const out = `docs/media/design/${set}`;
  const port = 8780;
  const base = `http://127.0.0.1:${port}`;
  const phone = { viewport: { width: 360, height: 780 }, deviceScaleFactor: 2, baseURL: base };

  let server = startDesignServer(port);
  try {
    await waitForServer(`${base}/`);
    const context = await browser.newContext({ viewport: { width: 1920, height: 1080 }, baseURL: base });
    const page = await context.newPage();
    await page.goto("/demo.html");
    const customer = page.frameLocator("#customer-frame");
    const rider = page.frameLocator("#rider-frame");
    await customer.locator("#language").selectOption("kn");
    await customer.locator("#create").click();
    await customer.locator("#code").filter({ hasText: /^[A-Z0-9]{6}$/ }).waitFor();
    // The page copies the code across on a timer; filling it here makes the capture deterministic.
    await rider.locator("#code-input").fill((await customer.locator("#code").textContent()) ?? "");
    await rider.locator("#language").selectOption("hi");
    await rider.locator("#join:not([disabled])").click();
    await customer.locator("#talk").waitFor({ state: "visible" });
    await scenario(customer, rider, (state) => page.screenshot({ path: `${out}/split-1920-${state}.png` }).then(() => {}));
    await context.close();
  } finally {
    stopServer(server);
  }

  await new Promise((resolve) => setTimeout(resolve, 1500)); // let the port free
  server = startDesignServer(port);
  try {
    // One dark-theme split for comparison: a fresh server, so the scripted clips start over.
    await waitForServer(`${base}/`);
    const context = await browser.newContext({ viewport: { width: 1920, height: 1080 }, baseURL: base, colorScheme: "dark" });
    const page = await context.newPage();
    await page.goto("/demo.html");
    const customer = page.frameLocator("#customer-frame");
    const rider = page.frameLocator("#rider-frame");
    await customer.locator("#language").selectOption("kn");
    await customer.locator("#create").click();
    await customer.locator("#code").filter({ hasText: /^[A-Z0-9]{6}$/ }).waitFor();
    await rider.locator("#code-input").fill((await customer.locator("#code").textContent()) ?? "");
    await rider.locator("#language").selectOption("hi");
    await rider.locator("#join:not([disabled])").click();
    await customer.locator("#talk").waitFor({ state: "visible" });
    await scenario(customer, rider, async (state) => {
      if (state === "4-confirm-and-ask") await page.screenshot({ path: `${out}/split-1920-dark-${state}.png` });
    });
    await context.close();
  } finally {
    stopServer(server);
  }

  await new Promise((resolve) => setTimeout(resolve, 1500));
  server = startDesignServer(port);
  try {
    await waitForServer(`${base}/`);
    const customerContext = await browser.newContext(phone);
    const riderContext = await browser.newContext(phone);
    const customer = await customerContext.newPage();
    const rider = await riderContext.newPage();
    await customer.goto("/customer.html");
    await customer.locator("#language").selectOption("kn");
    await customer.locator("#create").click();
    await customer.waitForFunction(() =>
      /^[A-Z0-9]{6}$/.test(document.querySelector("#code")?.textContent ?? ""),
    );
    const code = (await customer.locator("#code").textContent()) ?? "";
    await rider.goto(`/rider.html?code=${code}`);
    await rider.locator("#language").selectOption("hi");
    await rider.locator("#join:not([disabled])").click();
    await customer.locator("#talk").waitFor({ state: "visible" });
    await scenario(customer, rider, async (state) => {
      await customer.screenshot({ path: `${out}/phone-360-customer-${state}.png`, fullPage: true });
      await rider.screenshot({ path: `${out}/phone-360-rider-${state}.png`, fullPage: true });
    });
    await customerContext.close();
    await riderContext.close();
  } finally {
    stopServer(server);
  }
}

if (DESIGN) await designShots(process.argv[3] ?? "after");
for (const { mode, port, file } of SHOTS) {
  const server = spawn(
    "uv",
    ["run", "--no-sync", "python", "scripts/screenshot_server.py", replay, mode, String(port)],
    { stdio: "inherit" },
  );
  try {
    const base = `http://127.0.0.1:${port}`;
    await waitForServer(`${base}/`);
    const phone = { viewport: { width: 390, height: 720 }, deviceScaleFactor: 2, baseURL: base };
    const customerContext = await browser.newContext(phone);
    await customerContext.grantPermissions(["microphone"]);
    const riderContext = await browser.newContext(phone);
    const customer = await customerContext.newPage();
    const rider = await riderContext.newPage();

    await customer.goto("/customer.html");
    await customer.locator("#language").selectOption("kn");
    await customer.getByRole("button", { name: "Create room" }).click();
    await customer.waitForFunction(() =>
      /^[A-Z0-9]{6}$/.test(document.querySelector("#code")?.textContent ?? ""),
    );
    const code = (await customer.locator("#code").textContent()) ?? "";
    await rider.goto(`/rider.html?code=${code}`);
    await rider.locator("#language").selectOption("hi");
    await rider.getByRole("button", { name: /Join/ }).click();
    await customer.locator("#talk").waitFor({ state: "visible" });
    await customer.waitForFunction(() => !document.querySelector("#talk").disabled);

    await customer.locator("#talk").click();
    await customer.waitForTimeout(1500);
    await customer.locator("#talk").click();
    await rider.locator("#chips .chip-landmark").waitFor();
    await rider.locator("#repeat:not([disabled])").waitFor();
    await rider.screenshot({ path: file, fullPage: true });
    await customerContext.close();
    await riderContext.close();
  } finally {
    // uv spawns python as a child; kill the whole tree or the port stays bound.
    spawn("taskkill", ["/pid", String(server.pid), "/t", "/f"], { stdio: "ignore" });
  }
}
await browser.close();
