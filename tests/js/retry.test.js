// @ts-check
import assert from "node:assert/strict";
import { test } from "node:test";

import { backoffDelayMs, classify } from "../../src/saathi/static/js/retry.js";

test("classify maps each status to the documented behaviour", () => {
  assert.equal(classify(200).outcome, "ok");
  assert.equal(classify(null).outcome, "transient");
  assert.equal(classify(503).outcome, "transient");
  assert.equal(classify(429).outcome, "rate_limited");
  assert.equal(classify(422).outcome, "no_speech");
  assert.equal(classify(422, "no_speech").outcome, "no_speech");
  assert.equal(classify(422, "unreliable_translation").outcome, "unreliable_translation");
  assert.equal(classify(422, "something_new").outcome, "no_speech");
  assert.equal(classify(503, "unreliable_translation").outcome, "transient");
  assert.equal(classify(400).outcome, "bad_input");
  assert.equal(classify(413).outcome, "bad_input");
  assert.equal(classify(502).outcome, "upstream");
});

test("recording is kept for retryable failures and dropped for unusable audio", () => {
  for (const status of [null, 503, 429, 502]) {
    const verdict = classify(status);
    assert.ok("keepRecording" in verdict && verdict.keepRecording, `status ${status}`);
  }
  for (const status of [400, 413, 422]) {
    const verdict = classify(status);
    assert.ok("keepRecording" in verdict && !verdict.keepRecording, `status ${status}`);
  }
  const unreliable = classify(422, "unreliable_translation");
  assert.ok("keepRecording" in unreliable && !unreliable.keepRecording);
});

test("backoffDelayMs doubles each attempt and stays within +-25% jitter", () => {
  assert.equal(backoffDelayMs(0, () => 0.5), 1000);
  assert.equal(backoffDelayMs(1, () => 0.5), 2000);
  assert.equal(backoffDelayMs(2, () => 0.5), 4000);
  assert.equal(backoffDelayMs(0, () => 0), 750);
  assert.equal(backoffDelayMs(0, () => 0.999999), 1000 * (0.75 + 0.5 * 0.999999));
});
