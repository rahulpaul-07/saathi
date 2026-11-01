// @ts-check
// Retry policy for POST /turn (docs/DESIGN.md section 8). Pure, so it runs under node --test.

import { tb } from "./i18n.js";

export const MAX_AUTO_RETRIES = 3;
const BASE_DELAY_MS = 1000;

/**
 * @typedef {"ok" | "transient" | "rate_limited" | "upstream" | "no_speech" | "unreliable_translation" | "bad_input"} Outcome
 * @typedef {{outcome: Exclude<Outcome, "ok">, message: import("./i18n.js").Bi,
 *   keepRecording: boolean}} Verdict
 */

/**
 * Outcome to the text id, the English text and whether the recording is kept. The text is looked up
 * when a verdict is made, so it follows the viewer's language.
 * @type {Record<Exclude<Outcome, "ok">, {key: string, english: string, keepRecording: boolean}>}
 */
const SPECS = {
  // 503 (Gnani is rate limiting us) and network errors: retried automatically, then manually.
  transient: { key: "still_busy", english: "Still busy. Try again.", keepRecording: true },
  // Our own per-IP limit can take up to 60 s to free, so no automatic retry.
  rate_limited: {
    key: "too_many_turns",
    english: "Too many turns, wait a moment, then try again.",
    keepRecording: true,
  },
  upstream: {
    key: "speech_unavailable",
    english: "The speech service is unavailable. Try again.",
    keepRecording: true,
  },
  no_speech: {
    key: "no_speech",
    english: "Didn't catch that, please try again.",
    keepRecording: false,
  },
  // The message is built in turn-client.js, which has the transcript; this is the fallback text.
  unreliable_translation: {
    key: "unreliable",
    english: "I couldn't translate that reliably. Please try again.",
    keepRecording: false,
  },
  bad_input: {
    key: "bad_recording",
    english: "That recording can't be used. Please record again.",
    keepRecording: false,
  },
};

/**
 * @param {Exclude<Outcome, "ok">} outcome
 * @returns {Verdict}
 */
function verdict(outcome) {
  const spec = SPECS[outcome];
  return { outcome, message: tb(spec.key, spec.english), keepRecording: spec.keepRecording };
}

/**
 * Map an HTTP status (null for a network error or timeout) to what the UI should do.
 * @param {number | null} status
 * @param {string | null} [code] machine-readable error code from a 422 body, if there was one
 * @returns {Verdict | {outcome: "ok"}}
 */
export function classify(status, code = null) {
  if (status !== null && status >= 200 && status < 300) return { outcome: "ok" };
  if (status === null || status === 503) return verdict("transient");
  if (status === 429) return verdict("rate_limited");
  if (status === 422) {
    // An unknown code falls back to the generic message rather than failing.
    return code === "unreliable_translation" ? verdict("unreliable_translation") : verdict("no_speech");
  }
  if (status === 400 || status === 413) return verdict("bad_input");
  // 502 and anything unexpected on the server side: keep the recording. Other 4xx: it is our bug.
  return status >= 500 ? verdict("upstream") : verdict("bad_input");
}

/**
 * Jittered exponential backoff: about 1 s, 2 s, 4 s (each scaled by 0.75 to 1.25).
 * @param {number} attempt zero-based retry number
 * @param {() => number} [random] injectable for tests, returns [0, 1)
 * @returns {number} milliseconds
 */
export function backoffDelayMs(attempt, random = Math.random) {
  return BASE_DELAY_MS * 2 ** attempt * (0.75 + 0.5 * random());
}
