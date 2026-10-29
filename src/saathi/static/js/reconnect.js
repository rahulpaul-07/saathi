// @ts-check
// Keeping the event stream alive: exponential backoff with jitter, and stopping for good when the
// room is gone. Time and randomness are injected so the schedule is testable without real waits.

export const BASE_DELAY_MS = 1000;
export const MAX_DELAY_MS = 15_000;
export const JITTER_RATIO = 0.3;

/**
 * 1, 2, 4, 8 s, capped at 15 s, plus up to 30 percent random so many phones that lost the network
 * together do not come back in lockstep.
 * @param {number} attempt zero for the first retry
 * @param {() => number} random in [0, 1)
 * @returns {number} milliseconds
 */
export function backoffDelay(attempt, random) {
  const base = Math.min(BASE_DELAY_MS * 2 ** attempt, MAX_DELAY_MS);
  return Math.round(base * (1 + JITTER_RATIO * random()));
}

/**
 * @typedef {"closed" | "gone" | "dropped"} StreamEnd
 * closed: the server ended the room. gone: 404, expired or unknown. dropped: network or server
 * trouble, worth retrying.
 */

/**
 * @typedef {object} FollowOptions
 * @property {(onOpen: () => void) => Promise<StreamEnd>} connect one connection; calls onOpen once
 *   the stream is established
 * @property {() => void} onDown the stream dropped and a retry is scheduled
 * @property {() => void} onUp a connection was established
 * @property {(ms: number) => Promise<void>} sleep
 * @property {() => number} random
 * @property {AbortSignal} signal
 */

/**
 * Reconnect until the room is over or `signal` aborts.
 * @param {FollowOptions} options
 * @returns {Promise<"closed" | "gone" | "stopped">}
 */
export async function followStream({ connect, onDown, onUp, sleep, random, signal }) {
  let attempt = 0;
  while (!signal.aborted) {
    const end = await connect(() => {
      attempt = 0;
      onUp();
    });
    if (signal.aborted) break;
    if (end !== "dropped") return end;
    onDown();
    await sleep(backoffDelay(attempt, random));
    attempt += 1;
  }
  return "stopped";
}
