// @ts-check
import { MAX_AUTO_RETRIES, backoffDelayMs, classify } from "./retry.js";

const REQUEST_TIMEOUT_MS = 45_000;

/**
 * @typedef {{stt_ms: number, translate_ms: number, tts_ms: number, total_ms: number}} Timings
 * @typedef {{src: string, tgt: string, transcript: string, translation: string,
 *   audio_base64: string, audio_format: string, timings: Timings}} TurnResult
 * @typedef {{ok: true, data: TurnResult}
 *   | {ok: false, message: string, keepRecording: boolean}} TurnOutcome
 * @typedef {{fetchFn?: typeof fetch, sleep?: (ms: number) => Promise<void>,
 *   random?: () => number, onRetry?: (attempt: number, delayMs: number) => void}} TurnDeps
 */

/** @param {number} ms */
const defaultSleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));

/**
 * One request. A network error or timeout resolves to status null instead of throwing.
 * @param {Blob} wav
 * @param {string} src
 * @param {string} tgt
 * @param {typeof fetch} fetchFn
 * @returns {Promise<{status: number | null, body: unknown}>}
 */
async function postOnce(wav, src, tgt, fetchFn) {
  const form = new FormData(); // rebuilt per attempt; the Blob itself is never consumed
  form.append("audio", wav, "turn.wav");
  form.append("src", src);
  form.append("tgt", tgt);
  try {
    const response = await fetchFn("/turn", {
      method: "POST",
      body: form,
      signal: AbortSignal.timeout(REQUEST_TIMEOUT_MS),
    });
    const body = response.ok ? await response.json() : null;
    return { status: response.status, body };
  } catch {
    return { status: null, body: null };
  }
}

/**
 * Send a turn, retrying 503 and network errors with backoff. Always resends the same Blob.
 * @param {Blob} wav
 * @param {string} src
 * @param {string} tgt
 * @param {TurnDeps} [deps]
 * @returns {Promise<TurnOutcome>}
 */
export async function sendTurn(wav, src, tgt, deps = {}) {
  const { fetchFn = fetch, sleep = defaultSleep, random = Math.random, onRetry } = deps;
  for (let attempt = 0; ; attempt++) {
    const { status, body } = await postOnce(wav, src, tgt, fetchFn);
    const verdict = classify(status);
    if (verdict.outcome === "ok") return { ok: true, data: /** @type {TurnResult} */ (body) };
    if (verdict.outcome !== "transient" || attempt >= MAX_AUTO_RETRIES) {
      return { ok: false, message: verdict.message, keepRecording: verdict.keepRecording };
    }
    const delay = backoffDelayMs(attempt, random);
    onRetry?.(attempt + 1, delay);
    await sleep(delay);
  }
}
