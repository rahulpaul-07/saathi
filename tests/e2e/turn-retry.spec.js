// @ts-check
import { createHash } from "node:crypto";

import { expect, test } from "@playwright/test";

import { encodeWav } from "../../src/saathi/static/js/wav.js";

const TIMINGS = { stt_ms: 300, translate_ms: 200, tts_ms: 700, total_ms: 1200 };
// Visible markup in the text proves it is rendered as text, not HTML.
const TRANSCRIPT = "<b>heard</b>";

/** A short silent WAV standing in for the TTS audio. */
function replyBase64() {
  return Buffer.from(encodeWav(new Float32Array(2400), 24000)).toString("base64");
}

/**
 * SHA-256 of the WAV inside a multipart body. The boundary differs on every FormData, so the whole
 * body cannot be compared, only the audio part.
 * @param {import("@playwright/test").Request} request
 */
function audioHash(request) {
  const body = request.postDataBuffer();
  const contentType = request.headers()["content-type"] ?? "";
  const boundary = /boundary=(.+)$/.exec(contentType)?.[1];
  if (!body || !boundary) throw new Error("not a multipart request");
  const start = body.indexOf(Buffer.from("RIFF"));
  const end = body.indexOf(Buffer.from(`\r\n--${boundary}`), start);
  return createHash("sha256").update(body.subarray(start, end)).digest("hex");
}

/**
 * Intercept /turn and answer with the given statuses in order; 200 returns a canned turn.
 * @param {import("@playwright/test").Page} page
 * @param {number[]} statuses
 * @returns {Promise<string[]>} the audio hash of every request, filled in as they arrive
 */
async function stubTurn(page, statuses) {
  /** @type {string[]} */
  const hashes = [];
  const queue = [...statuses];
  await page.route("**/turn", async (route) => {
    hashes.push(audioHash(route.request()));
    const status = queue.shift() ?? 200;
    if (status === 200) {
      await route.fulfill({
        status,
        json: {
          src: "bn",
          tgt: "kn",
          transcript: TRANSCRIPT,
          translation: "translated",
          audio_base64: replyBase64(),
          audio_format: "wav",
          timings: TIMINGS,
        },
      });
    } else {
      await route.fulfill({ status, json: { detail: "stub" } });
    }
  });
  return hashes;
}

/** @param {import("@playwright/test").Page} page */
function watchConsole(page) {
  /** @type {string[]} */
  const problems = [];
  page.on("console", (message) => {
    // Chromium logs every non-2xx response by itself; the 503s and 422s here are the stubbed failures.
    const stubbedFailure = /status of (503|422)/.test(message.text());
    if (["error", "warning"].includes(message.type()) && !stubbedFailure) {
      problems.push(message.text());
    }
  });
  page.on("pageerror", (error) => problems.push(error.message));
  return problems;
}

/** @param {import("@playwright/test").Page} page */
async function recordOneTurn(page) {
  await page.goto("/");
  await page.getByRole("button", { name: "Speak Bengali" }).click();
  await expect(page.getByRole("status")).toContainText("Recording");
  await page.waitForTimeout(1500); // let the fake microphone produce some audio
  await page.getByRole("button", { name: "Stop and translate" }).click();
}

test("503, 503, 200: retries automatically and resends the same recording", async ({ page }) => {
  const problems = watchConsole(page);
  const hashes = await stubTurn(page, [503, 503, 200]);

  await recordOneTurn(page);
  await expect(page.getByRole("status")).toContainText("One moment");
  await expect(page.locator("#transcript")).toHaveText(TRANSCRIPT, { timeout: 15_000 });

  expect(hashes).toHaveLength(3);
  expect(new Set(hashes).size).toBe(1);
  expect(await page.locator("#transcript b").count()).toBe(0);
  await expect(page.locator("#translation")).toHaveText("translated");
  await expect(page.locator("#timings")).toContainText("Server total");
  await expect(page.locator("#timings")).not.toContainText("waiting");
  expect(problems).toEqual([]);
});

test("still busy after 3 retries: Try again resends the same recording", async ({ page }) => {
  const problems = watchConsole(page);
  const hashes = await stubTurn(page, [503, 503, 503, 503, 200]);

  await recordOneTurn(page);
  await expect(page.getByRole("status")).toContainText("Still busy", { timeout: 20_000 });
  await expect(page.getByRole("button", { name: "Speak Bengali" })).toBeDisabled();
  await page.getByRole("button", { name: "Try again" }).click();
  await expect(page.locator("#transcript")).toHaveText(TRANSCRIPT, { timeout: 15_000 });

  expect(hashes).toHaveLength(5);
  expect(new Set(hashes).size).toBe(1);
  expect(problems).toEqual([]);
});

test("our own 429 is not retried automatically", async ({ page }) => {
  const hashes = await stubTurn(page, [429, 200]);

  await recordOneTurn(page);
  await expect(page.getByRole("status")).toContainText("Too many turns");
  expect(hashes).toHaveLength(1);
  await page.getByRole("button", { name: "Try again" }).click();
  await expect(page.locator("#transcript")).toHaveText(TRANSCRIPT);
  expect(new Set(hashes).size).toBe(1);
});

test("unreliable translation: shows the transcript as text, no retry, no stored recording", async ({
  page,
}) => {
  const problems = watchConsole(page);
  let requests = 0;
  await page.route("**/turn", async (route) => {
    requests += 1;
    await route.fulfill({
      status: 422,
      json: {
        detail: {
          code: "unreliable_translation",
          message: "could not translate reliably",
          transcript: TRANSCRIPT,
        },
      },
    });
  });

  await recordOneTurn(page);
  await expect(page.getByRole("status")).toHaveText(
    `I heard: ${TRANSCRIPT}. I couldn't translate that reliably. Please try again.`,
  );
  await page.waitForTimeout(2500); // longer than the first backoff, so a retry would show up
  expect(requests).toBe(1);
  expect(await page.locator("#status b").count()).toBe(0);
  await expect(page.getByRole("button", { name: "Try again" })).toBeHidden();
  await expect(page.getByRole("button", { name: "Speak Bengali" })).toBeEnabled();
  expect(problems).toEqual([]);
});
