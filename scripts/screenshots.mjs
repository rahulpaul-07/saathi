// Phone-sized rider-screen screenshots for docs/media (synthetic address, real local translation).
// Usage: node scripts/screenshots.mjs <replay.json>   (see scripts/screenshot_server.py)
import { spawn } from "node:child_process";
import { chromium } from "@playwright/test";

const replay = process.argv[2];
const SHOTS = [
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
    await rider.screenshot({ path: file });
    await customerContext.close();
    await riderContext.close();
  } finally {
    // uv spawns python as a child; kill the whole tree or the port stays bound.
    spawn("taskkill", ["/pid", String(server.pid), "/t", "/f"], { stdio: "ignore" });
  }
}
await browser.close();
