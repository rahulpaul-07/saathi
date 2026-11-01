// @ts-check
import assert from "node:assert/strict";
import { test } from "node:test";

import { Bi } from "../../src/saathi/static/js/i18n.js";
import { sendTurn } from "../../src/saathi/static/js/turn-client.js";

const RESULT = {
  src: "bn",
  tgt: "kn",
  transcript: "a",
  translation: "b",
  audio_base64: "",
  audio_format: "wav",
  timings: { stt_ms: 1, translate_ms: 2, tts_ms: 3, total_ms: 6 },
};

/**
 * A fake fetch that answers with the given statuses in order (null = network error) and records
 * the audio file of every request. `errorBody` is the raw body of every non-200 answer.
 * @param {(number | null)[]} statuses
 * @param {string} [errorBody]
 */
function fakeFetch(statuses, errorBody = "{}") {
  /** @type {FormDataEntryValue[]} */
  const sentAudio = [];
  const queue = [...statuses];
  /** @type {typeof fetch} */
  const fetchFn = async (_url, init) => {
    sentAudio.push(/** @type {FormData} */ (init?.body).get("audio") ?? "");
    const status = queue.shift();
    if (status === undefined || status === null) throw new TypeError("network");
    return status === 200
      ? new Response(JSON.stringify(RESULT), { status })
      : new Response(errorBody, { status });
  };
  return { fetchFn, sentAudio };
}

const wav = new Blob([new Uint8Array([1, 2, 3, 4])], { type: "audio/wav" });
const noSleep = async () => {};

test("503, 503, 200: retries with backoff and resends the same recording", async () => {
  const { fetchFn, sentAudio } = fakeFetch([503, 503, 200]);
  /** @type {number[]} */
  const delays = [];
  const outcome = await sendTurn(wav, "bn", "kn", {
    fetchFn,
    sleep: noSleep,
    random: () => 0.5,
    onRetry: (_attempt, delay) => delays.push(delay),
  });
  assert.equal(outcome.ok, true);
  assert.deepEqual(delays, [1000, 2000]);
  assert.equal(sentAudio.length, 3);
  for (const file of sentAudio) assert.equal(/** @type {File} */ (file).size, wav.size);
});

test("gives up after 3 automatic retries and keeps the recording", async () => {
  const { fetchFn, sentAudio } = fakeFetch([503, 503, 503, 503, 200]);
  const outcome = await sendTurn(wav, "bn", "kn", { fetchFn, sleep: noSleep });
  assert.equal(sentAudio.length, 4); // 1 attempt + 3 retries
  assert.deepEqual(outcome, {
    ok: false,
    message: new Bi("Still busy. Try again.", "Still busy. Try again."),
    keepRecording: true,
  });
});

test("a network error is retried like a 503", async () => {
  const { fetchFn } = fakeFetch([null, 200]);
  const outcome = await sendTurn(wav, "bn", "kn", { fetchFn, sleep: noSleep });
  assert.equal(outcome.ok, true);
});

test("429 is not retried automatically", async () => {
  const { fetchFn, sentAudio } = fakeFetch([429, 200]);
  const outcome = await sendTurn(wav, "bn", "kn", { fetchFn, sleep: noSleep });
  assert.equal(sentAudio.length, 1);
  assert.equal(outcome.ok, false);
  assert.equal(!outcome.ok && outcome.keepRecording, true);
});

test("422 and 400 are not retried and discard the recording", async () => {
  for (const status of [422, 400]) {
    const { fetchFn, sentAudio } = fakeFetch([status]);
    const outcome = await sendTurn(wav, "bn", "kn", { fetchFn, sleep: noSleep });
    assert.equal(sentAudio.length, 1);
    assert.equal(!outcome.ok && outcome.keepRecording, false);
  }
});

const unreliableBody = (/** @type {unknown} */ transcript) =>
  JSON.stringify({
    detail: { code: "unreliable_translation", message: "m", transcript },
  });

test("unreliable_translation 422: no retry, recording dropped, transcript exposed", async () => {
  const { fetchFn, sentAudio } = fakeFetch([422, 200], unreliableBody("<b>heard</b>"));
  const outcome = await sendTurn(wav, "bn", "kn", { fetchFn, sleep: noSleep });
  assert.equal(sentAudio.length, 1);
  assert.deepEqual(outcome, {
    ok: false,
    message: new Bi(
      "I heard: <b>heard</b>. I couldn't translate that reliably. Please try again.",
      "I heard: <b>heard</b>. I couldn't translate that reliably. Please try again.",
    ),
    keepRecording: false,
    code: "unreliable_translation",
    transcript: "<b>heard</b>",
  });
});

test("no_speech 422 keeps the existing message", async () => {
  const body = JSON.stringify({ detail: { code: "no_speech", message: "no speech detected" } });
  const outcome = await sendTurn(wav, "bn", "kn", { fetchFn: fakeFetch([422], body).fetchFn });
  assert.equal(!outcome.ok && outcome.message.local, "Didn't catch that, please try again.");
  assert.equal(!outcome.ok && outcome.keepRecording, false);
});

test("422 with a non-JSON, unknown-code or malformed body falls back to the no-speech message", async () => {
  const bodies = [
    "<html>oops</html>",
    JSON.stringify({ detail: { code: "future_code" } }),
    JSON.stringify({ detail: "no speech detected" }),
    JSON.stringify({ detail: { code: "unreliable_translation", transcript: 5 } }),
    "null",
  ];
  for (const body of bodies) {
    const outcome = await sendTurn(wav, "bn", "kn", { fetchFn: fakeFetch([422], body).fetchFn });
    assert.equal(!outcome.ok && outcome.message.local, "Didn't catch that, please try again.", body);
  }
});
