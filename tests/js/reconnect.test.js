// @ts-check
import assert from "node:assert/strict";
import { test } from "node:test";

import { backoffDelay, followStream } from "../../src/saathi/static/js/reconnect.js";

test("backoff doubles from 1 s and caps at 15 s with no jitter", () => {
  const delays = [0, 1, 2, 3, 4, 10].map((attempt) => backoffDelay(attempt, () => 0));
  assert.deepEqual(delays, [1000, 2000, 4000, 8000, 15_000, 15_000]);
});

test("jitter adds at most 30 percent", () => {
  assert.equal(backoffDelay(0, () => 0.999999), 1300);
  assert.equal(backoffDelay(2, () => 0.5), 4600);
  assert.equal(backoffDelay(9, () => 0.999999), 19_500);
});

/**
 * @param {import("../../src/saathi/static/js/reconnect.js").StreamEnd[]} ends
 * @param {{openOn?: number[]}} [options] attempts (0-based) that reach the open state first
 */
function run(ends, { openOn = [] } = {}) {
  const log = /** @type {string[]} */ ([]);
  const sleeps = /** @type {number[]} */ ([]);
  let call = 0;
  const controller = new AbortController();
  const result = followStream({
    connect: async (onOpen) => {
      const index = call++;
      if (openOn.includes(index)) onOpen();
      return ends[index] ?? "gone";
    },
    onDown: () => log.push("down"),
    onUp: () => log.push("up"),
    sleep: async (ms) => void sleeps.push(ms),
    random: () => 0,
    signal: controller.signal,
  });
  return { result, log, sleeps, calls: () => call };
}

test("retries with growing delays and shows down until a connection opens", async () => {
  const run1 = run(["dropped", "dropped", "dropped", "gone"]);
  assert.equal(await run1.result, "gone");
  assert.deepEqual(run1.sleeps, [1000, 2000, 4000]);
  assert.deepEqual(run1.log, ["down", "down", "down"]);
});

test("a successful connection resets the schedule and clears the indicator", async () => {
  const run2 = run(["dropped", "dropped", "dropped", "closed"], { openOn: [2] });
  assert.equal(await run2.result, "closed");
  assert.deepEqual(run2.sleeps, [1000, 2000, 1000]);
  assert.deepEqual(run2.log, ["down", "down", "up", "down"]);
});

test("stops at once, with no retry, when the room is gone or closed", async () => {
  for (const end of /** @type {const} */ (["gone", "closed"])) {
    const stopped = run([end]);
    assert.equal(await stopped.result, end);
    assert.equal(stopped.calls(), 1);
    assert.deepEqual(stopped.sleeps, []);
  }
});

test("an aborted signal ends the loop without retrying", async () => {
  const controller = new AbortController();
  let calls = 0;
  const result = await followStream({
    connect: async () => {
      calls += 1;
      controller.abort();
      return "dropped";
    },
    onDown: () => assert.fail("no indicator when stopped on purpose"),
    onUp: () => {},
    sleep: async () => assert.fail("no sleep when stopped on purpose"),
    random: () => 0,
    signal: controller.signal,
  });
  assert.equal(result, "stopped");
  assert.equal(calls, 1);
});
