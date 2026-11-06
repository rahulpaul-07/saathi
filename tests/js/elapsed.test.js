// @ts-check
import assert from "node:assert/strict";
import { test } from "node:test";
import { formatElapsed } from "../../src/saathi/static/js/elapsed.js";

test("elapsed time is minutes and zero-padded seconds", () => {
  assert.equal(formatElapsed(0), "0:00");
  assert.equal(formatElapsed(7400), "0:07");
  assert.equal(formatElapsed(60000), "1:00");
  assert.equal(formatElapsed(59999), "0:59");
});

test("a negative duration (a clock that stepped back) shows zero, never a minus sign", () => {
  assert.equal(formatElapsed(-5000), "0:00");
});
