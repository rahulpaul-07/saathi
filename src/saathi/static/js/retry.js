// @ts-check
// Retry policy for POST /turn (docs/DESIGN.md section 8). Pure, so it runs under node --test.

export const MAX_AUTO_RETRIES = 3;
const BASE_DELAY_MS = 1000;

/**
 * @typedef {"ok" | "transient" | "rate_limited" | "upstream" | "no_speech" | "bad_input"} Outcome
 * @typedef {{outcome: Exclude<Outcome, "ok">, message: string, keepRecording: boolean}} Verdict
 */

/** @type {Record<Exclude<Outcome, "ok">, Verdict>} */
const VERDICTS = {
  // 503 (Gnani is rate limiting us) and network errors: retried automatically, then manually.
  transient: { outcome: "transient", message: "Still busy. Try again.", keepRecording: true },
  // Our own per-IP limit can take up to 60 s to free, so no automatic retry.
  rate_limited: {
    outcome: "rate_limited",
    message: "Too many turns, wait a moment, then try again.",
    keepRecording: true,
  },
  upstream: {
    outcome: "upstream",
    message: "The speech service is unavailable. Try again.",
    keepRecording: true,
  },
  no_speech: {
    outcome: "no_speech",
    message: "Didn't catch that, please try again.",
    keepRecording: false,
  },
  bad_input: {
    outcome: "bad_input",
    message: "That recording can't be used. Please record again.",
    keepRecording: false,
  },
};

/**
 * Map an HTTP status (null for a network error or timeout) to what the UI should do.
 * @param {number | null} status
 * @returns {Verdict | {outcome: "ok"}}
 */
export function classify(status) {
  if (status !== null && status >= 200 && status < 300) return { outcome: "ok" };
  if (status === null || status === 503) return VERDICTS.transient;
  if (status === 429) return VERDICTS.rate_limited;
  if (status === 422) return VERDICTS.no_speech;
  if (status === 400 || status === 413) return VERDICTS.bad_input;
  // 502 and anything unexpected on the server side: keep the recording. Other 4xx: it is our bug.
  return status >= 500 ? VERDICTS.upstream : VERDICTS.bad_input;
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
