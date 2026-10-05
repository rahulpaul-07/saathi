// @ts-check
import { MAX_AUTO_RETRIES, backoffDelayMs, classify } from "./retry.js";

const REQUEST_TIMEOUT_MS = 45_000;

/**
 * @typedef {{stt_ms: number, translate_ms: number, tts_ms: number, total_ms: number}} Timings
 * @typedef {{src: string, tgt: string, transcript: string, translation: string,
 *   audio_base64: string, audio_format: string, timings: Timings}} TurnResult
 * @typedef {{ok: true, data: TurnResult}
 *   | {ok: false, message: string, keepRecording: boolean, code?: string, transcript?: string}
 * } TurnOutcome
 * @typedef {{code: string | null, transcript: string | null}} ErrorDetail
 * @typedef {{fetchFn?: typeof fetch, sleep?: (ms: number) => Promise<void>,
 *   random?: () => number, onRetry?: (attempt: number, delayMs: number) => void}} TurnDeps
 */

/** @param {number} ms */
const defaultSleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));

/** @type {ErrorDetail} */
const NO_ERROR = { code: null, transcript: null };

/**
 * Read `detail.code` and `detail.transcript` from an error body. Anything unexpected (not JSON,
 * detail a plain string, wrong types) yields nulls instead of throwing.
 * @param {Response} response
 * @returns {Promise<ErrorDetail>}
 */
async function readErrorDetail(response) {
  try {
    const detail = (await response.json())?.detail;
    if (typeof detail !== "object" || detail === null) return NO_ERROR;
    const { code, transcript } = detail;
    if (typeof code !== "string") return NO_ERROR;
    if (code === "unreliable_translation" && typeof transcript !== "string") return NO_ERROR;
    return { code, transcript: typeof transcript === "string" ? transcript : null };
  } catch {
    return NO_ERROR;
  }
}

/**
 * One request. A network error or timeout resolves to status null instead of throwing.
 * @param {Blob} wav
 * @param {string} src
 * @param {string} tgt
 * @param {typeof fetch} fetchFn
 * @returns {Promise<{status: number | null, body: unknown, error: ErrorDetail}>}
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
    if (response.ok) return { status: response.status, body: await response.json(), error: NO_ERROR };
    return { status: response.status, body: null, error: await readErrorDetail(response) };
  } catch {
    return { status: null, body: null, error: NO_ERROR };
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
    const { status, body, error } = await postOnce(wav, src, tgt, fetchFn);
    const verdict = classify(status, error.code);
    if (verdict.outcome === "ok") return { ok: true, data: /** @type {TurnResult} */ (body) };
    if (verdict.outcome === "unreliable_translation" && error.transcript !== null) {
      return {
        ok: false,
        message: `I heard: ${error.transcript}. ${verdict.message}`,
        keepRecording: verdict.keepRecording,
        code: "unreliable_translation",
        transcript: error.transcript,
      };
    }
    if (verdict.outcome !== "transient" || attempt >= MAX_AUTO_RETRIES) {
      return { ok: false, message: verdict.message, keepRecording: verdict.keepRecording };
    }
    const delay = backoffDelayMs(attempt, random);
    onRetry?.(attempt + 1, delay);
    await sleep(delay);
  }
}
