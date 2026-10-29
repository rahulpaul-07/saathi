// @ts-check
// HTTP and SSE calls for rooms. Tokens go in an Authorization header (never the URL).
import { classify } from "./retry.js";
import { createSseParser } from "./sse.js";

const REQUEST_TIMEOUT_MS = 45_000;

/**
 * @typedef {{code: string, token: string, role: string, language: string,
 *   peer_language?: string | null}} RoomInfo
 * @typedef {{kind: string, value: string, heard: string, confidence: string,
 *   ambiguous: boolean, reading: string | null}} TurnFact
 * @typedef {{ok: true, data: any} | {ok: false, status: number | null, message: string,
 *   keepRecording: boolean}} Result
 */

/** @param {string} token */
const bearer = (token) => ({ Authorization: `Bearer ${token}` });

/**
 * Error body to machine code: FastAPI sends {detail: "text"} or {detail: {code, message}}.
 * @param {Response} response
 * @returns {Promise<string | null>}
 */
async function errorCode(response) {
  try {
    const detail = (await response.json())?.detail;
    return typeof detail?.code === "string" ? detail.code : null;
  } catch {
    return null;
  }
}

/**
 * One JSON request. Never throws: network errors and timeouts become status null.
 * @param {string} path
 * @param {RequestInit} init
 * @returns {Promise<Result>}
 */
async function request(path, init) {
  try {
    const response = await fetch(path, { ...init, signal: AbortSignal.timeout(REQUEST_TIMEOUT_MS) });
    if (response.ok) {
      const body = response.status === 204 ? null : await response.json();
      return { ok: true, data: body };
    }
    const verdict = classify(response.status, await errorCode(response));
    const message = specificMessage(response.status) ?? ("message" in verdict ? verdict.message : "");
    return {
      ok: false,
      status: response.status,
      message,
      keepRecording: "keepRecording" in verdict && verdict.keepRecording,
    };
  } catch {
    const verdict = classify(null);
    return {
      ok: false,
      status: null,
      message: "No connection to the server. Check the network and try again.",
      keepRecording: "keepRecording" in verdict && verdict.keepRecording,
    };
  }
}

/**
 * Room-level failures whose meaning differs from the turn-upload messages in retry.js.
 * @param {number} status
 * @returns {string | null}
 */
function specificMessage(status) {
  if (status === 404) return "Room not found or it has expired. Check the code.";
  if (status === 409) return "Waiting for the other person to join, or the room is full.";
  if (status === 403) return "That action is not allowed here.";
  return null;
}

/**
 * @param {string} language
 * @returns {Promise<Result>}
 */
export function createRoom(language) {
  return request("/rooms", jsonPost({ language }));
}

/**
 * @param {string} code
 * @param {string} language
 * @returns {Promise<Result>}
 */
export function joinRoom(code, language) {
  return request(`/rooms/${encodeURIComponent(code)}/join`, jsonPost({ language }));
}

/**
 * @param {RoomInfo} room
 * @param {string} phraseId
 * @returns {Promise<Result>}
 */
export function sendQuickReply(room, phraseId) {
  return request(`/rooms/${room.code}/quick-reply`, {
    ...jsonPost({ phrase_id: phraseId }),
    headers: { ...bearer(room.token), "Content-Type": "application/json" },
  });
}

/**
 * The rider answers one delivery-card chip.
 * @param {RoomInfo} room
 * @param {string} kind
 * @param {"confirm" | "ask"} action
 * @returns {Promise<Result>}
 */
export function sendChipReply(room, kind, action) {
  return request(`/rooms/${room.code}/chip-reply`, {
    ...jsonPost({ kind, action }),
    headers: { ...bearer(room.token), "Content-Type": "application/json" },
  });
}

/**
 * @param {RoomInfo} room
 * @param {Blob} wav
 * @param {boolean} [demoClip] a prepared demo clip, not live speech; the listener is told
 * @returns {Promise<Result>}
 */
export function postTurn(room, wav, demoClip = false) {
  const form = new FormData();
  form.append("audio", wav, "turn.wav");
  return request(`/rooms/${room.code}/turn`, {
    method: "POST",
    body: form,
    headers: demoClip ? { ...bearer(room.token), "X-Demo-Clip": "1" } : bearer(room.token),
  });
}

/**
 * A prepared demo clip as a WAV blob (demo input mode only).
 * @param {string} clipId
 * @returns {Promise<Blob | null>}
 */
export async function fetchDemoClip(clipId) {
  try {
    const response = await fetch(`/demo/clips/${encodeURIComponent(clipId)}.wav`, {
      signal: AbortSignal.timeout(REQUEST_TIMEOUT_MS),
    });
    return response.ok ? await response.blob() : null;
  } catch {
    return null;
  }
}

/**
 * Fetch turn or quick-reply audio (needs the token, so an <audio src> cannot load it directly).
 * @param {RoomInfo} room
 * @param {string} audioPath path from an event
 * @returns {Promise<string | null>} an object URL the caller must revoke, or null on failure
 */
export async function fetchAudioUrl(room, audioPath) {
  // Only same-room audio paths are fetched; anything else in an event is ignored.
  if (!audioPath.startsWith(`/rooms/${room.code}/turns/`)) return null;
  try {
    const response = await fetch(audioPath, {
      headers: bearer(room.token),
      signal: AbortSignal.timeout(REQUEST_TIMEOUT_MS),
    });
    if (!response.ok) return null;
    return URL.createObjectURL(await response.blob());
  } catch {
    return null;
  }
}

/**
 * Read the event stream until it ends, errors or `signal` aborts. Resolves true when the server
 * ended the room ("closed" event) so the caller does not reconnect.
 * @param {RoomInfo} room
 * @param {(name: string, data: any) => void} onEvent
 * @param {AbortSignal} signal
 * @returns {Promise<boolean>}
 */
export async function readEvents(room, onEvent, signal) {
  let closed = false;
  const parser = createSseParser((event) => {
    if (event.name === "closed") closed = true;
    onEvent(event.name, event.data);
  });
  try {
    const response = await fetch(`/rooms/${room.code}/events`, {
      headers: bearer(room.token),
      signal,
    });
    if (response.status === 404) return true; // room gone: reconnecting cannot help
    if (!response.ok || !response.body) return false;
    const reader = response.body.pipeThrough(new TextDecoderStream()).getReader();
    for (;;) {
      const { done, value } = await reader.read();
      if (done) break;
      parser.push(value);
    }
  } catch {
    // Network drop or abort: the caller decides whether to reconnect.
  }
  return closed;
}

/**
 * @param {unknown} body
 * @returns {RequestInit}
 */
function jsonPost(body) {
  return {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  };
}

/**
 * Fetch static JSON the UI needs before anything else.
 * @param {string} path
 * @returns {Promise<unknown>}
 */
export async function getJson(path) {
  const response = await fetch(path);
  if (!response.ok) throw new Error(`${path} failed`);
  return response.json();
}
