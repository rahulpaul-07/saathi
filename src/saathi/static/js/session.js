// @ts-check
// The room session kept in sessionStorage so a reload rejoins the room. sessionStorage, not
// localStorage: it is per tab and gone when the tab closes, so the bearer token does not outlive
// the person's use of the room. Storage is passed in so tests need no browser, and every access is
// guarded because it can be missing or throw (private windows, blocked site data).
//
// One entry per role. The split page runs a customer frame and a rider frame in one tab, and the
// frames share this storage, so a single shared key would let the second room overwrite the first.

const SESSION_PREFIX = "saathi.session.";
const NOTICE_PREFIX = "saathi.notice.";
const CODE_PATTERN = /^[A-Z0-9]{6}$/;
const ROLES = ["customer", "rider"];
const FIELD_MAX = 64;

/**
 * @typedef {Pick<Storage, "getItem" | "setItem" | "removeItem">} KeyValueStore
 */

/** @type {KeyValueStore} */
const NO_STORAGE = { getItem: () => null, setItem: () => {}, removeItem: () => {} };

/**
 * This tab's storage. A browser that blocks site data can throw on the very first reference to
 * `sessionStorage`, which would break a page that only wanted to read a courtesy notice, so a blocked
 * tab gets a store that remembers nothing instead.
 * @returns {KeyValueStore}
 */
export function tabStorage() {
  try {
    return globalThis.sessionStorage ?? NO_STORAGE;
  } catch {
    return NO_STORAGE;
  }
}

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
    store.setItem(
      SESSION_PREFIX + role,
      JSON.stringify({ code, token, role, language, peer_language: peer ?? null }),
    );
  } catch {
    // Without storage a reload just returns to the create/join screen.
  }
}

/**
 * The saved session for this page's role, or null. A malformed entry, or one stored under the wrong
 * role, is removed. A link to a different room wins over the saved one: the person asked for that
 * room, so the old session is dropped and the page shows the join screen for the new code.
 * @param {KeyValueStore} store
 * @param {string} role the role this page plays
 * @param {string | null} [linkCode] the room code from the page's link, if it had one
 * @returns {import("./room-client.js").RoomInfo | null}
 */
export function loadSession(store, role, linkCode = null) {
  try {
    const raw = store.getItem(SESSION_PREFIX + role);
    if (raw === null) return null;
    const session = parseSession(JSON.parse(raw));
    const wanted = linkCode?.toUpperCase() ?? "";
    const otherRoom = CODE_PATTERN.test(wanted) && session !== null && session.code !== wanted;
    if (session === null || session.role !== role || otherRoom) {
      store.removeItem(SESSION_PREFIX + role);
      return null;
    }
    return session;
  } catch {
    return null;
  }
}

/**
 * @param {KeyValueStore} store
 * @param {string} role
 */
export function clearSession(store, role) {
  try {
    store.removeItem(SESSION_PREFIX + role);
  } catch {
    // Nothing to clear.
  }
}

/**
 * A one-shot message for the next screen (after the room ended): the home page, or the create/join
 * screen of a split-page frame.
 * @param {KeyValueStore} store
 * @param {string} role
 * @param {string} text
 */
export function setNotice(store, role, text) {
  try {
    store.setItem(NOTICE_PREFIX + role, text);
  } catch {
    // The message is a courtesy; losing it is fine.
  }
}

/**
 * @param {KeyValueStore} store
 * @param {string} role
 * @returns {string | null}
 */
export function takeNotice(store, role) {
  try {
    const text = store.getItem(NOTICE_PREFIX + role);
    store.removeItem(NOTICE_PREFIX + role);
    return text;
  } catch {
    return null;
  }
}

/**
 * The home page does not know which role's room just ended: take whichever notice is waiting, and
 * clear them all so none is shown late.
 * @param {KeyValueStore} store
 * @returns {string | null}
 */
export function takeAnyNotice(store) {
  const notices = ROLES.map((role) => takeNotice(store, role));
  return notices.find((text) => text !== null) ?? null;
}
