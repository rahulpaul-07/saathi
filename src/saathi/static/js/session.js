// @ts-check
// The room session kept in sessionStorage so a reload rejoins the room. sessionStorage, not
// localStorage: it is per tab and gone when the tab closes, so the bearer token does not outlive
// the person's use of the room. Storage is passed in so tests need no browser, and every access is
// guarded because it can be missing or throw (private windows, blocked site data).

const SESSION_KEY = "saathi.session";
const NOTICE_KEY = "saathi.notice";
const CODE_PATTERN = /^[A-Z0-9]{6}$/;
const ROLES = ["customer", "rider"];
const FIELD_MAX = 64;

/**
 * @typedef {Pick<Storage, "getItem" | "setItem" | "removeItem">} KeyValueStore
 */

/** @param {unknown} value */
const shortText = (value) =>
  typeof value === "string" && value.length > 0 && value.length <= FIELD_MAX;

/**
 * Strictly validate what was stored, since it is only as trustworthy as the tab's storage.
 * @param {unknown} value
 * @returns {import("./room-client.js").RoomInfo | null}
 */
export function parseSession(value) {
  if (typeof value !== "object" || value === null) return null;
  const item = /** @type {Record<string, unknown>} */ (value);
  const peer = item.peer_language;
  if (
    typeof item.code !== "string" ||
    !CODE_PATTERN.test(item.code) ||
    !shortText(item.token) ||
    typeof item.role !== "string" ||
    !ROLES.includes(item.role) ||
    !shortText(item.language) ||
    !(peer === null || peer === undefined || shortText(peer))
  ) {
    return null;
  }
  return {
    code: item.code,
    token: /** @type {string} */ (item.token),
    role: item.role,
    language: /** @type {string} */ (item.language),
    peer_language: /** @type {string | null | undefined} */ (peer),
  };
}

/**
 * @param {KeyValueStore} store
 * @param {import("./room-client.js").RoomInfo} room
 */
export function saveSession(store, room) {
  const { code, token, role, language, peer_language: peer } = room;
  try {
    store.setItem(SESSION_KEY, JSON.stringify({ code, token, role, language, peer_language: peer ?? null }));
  } catch {
    // Without storage a reload just returns to the create/join screen.
  }
}

/**
 * The saved session for this page's role, or null. A malformed entry is removed.
 * @param {KeyValueStore} store
 * @param {string} role the role this page plays
 * @returns {import("./room-client.js").RoomInfo | null}
 */
export function loadSession(store, role) {
  try {
    const raw = store.getItem(SESSION_KEY);
    if (raw === null) return null;
    const session = parseSession(JSON.parse(raw));
    if (session === null) store.removeItem(SESSION_KEY);
    return session !== null && session.role === role ? session : null;
  } catch {
    return null;
  }
}

/** @param {KeyValueStore} store */
export function clearSession(store) {
  try {
    store.removeItem(SESSION_KEY);
  } catch {
    // Nothing to clear.
  }
}

/**
 * A one-shot message shown on the next create/join screen (after the room ended).
 * @param {KeyValueStore} store
 * @param {string} text
 */
export function setNotice(store, text) {
  try {
    store.setItem(NOTICE_KEY, text);
  } catch {
    // The message is a courtesy; losing it is fine.
  }
}

/**
 * @param {KeyValueStore} store
 * @returns {string | null}
 */
export function takeNotice(store) {
  try {
    const text = store.getItem(NOTICE_KEY);
    store.removeItem(NOTICE_KEY);
    return text;
  } catch {
    return null;
  }
}
