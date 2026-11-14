// @ts-check
import assert from "node:assert/strict";
import { test } from "node:test";

import {
  clearSession,
  loadSession,
  parseSession,
  saveSession,
  setNotice,
  tabStorage,
  takeAnyNotice,
  takeNotice,
} from "../../src/saathi/static/js/session.js";

function memoryStore() {
  const items = new Map();
  return {
    getItem: (/** @type {string} */ key) => items.get(key) ?? null,
    setItem: (/** @type {string} */ key, /** @type {string} */ value) => void items.set(key, value),
    removeItem: (/** @type {string} */ key) => void items.delete(key),
    keys: () => [...items.keys()],
  };
}

const room = { code: "ABC234", token: "tok-123", role: "rider", language: "ta", peer_language: "kn" };
const customerRoom = { ...room, code: "XYZ789", token: "tok-999", role: "customer", language: "kn" };

test("a saved session loads back for the role it was saved under", () => {
  const store = memoryStore();
  saveSession(store, room);
  assert.deepEqual(loadSession(store, "rider"), room);
  assert.equal(loadSession(store, "customer"), null);
});

test("both roles keep their own session in the same tab", () => {
  // The split page runs a customer and a rider frame in one tab, so they share this storage.
  const store = memoryStore();
  saveSession(store, customerRoom);
  saveSession(store, room);
  assert.deepEqual(loadSession(store, "customer"), customerRoom);
  assert.deepEqual(loadSession(store, "rider"), room);
});

test("a malformed stored session is rejected and removed", () => {
  const store = memoryStore();
  store.setItem("saathi.session.rider", JSON.stringify({ ...room, code: "abc" }));
  assert.equal(loadSession(store, "rider"), null);
  assert.equal(store.getItem("saathi.session.rider"), null);
  store.setItem("saathi.session.rider", "{not json");
  assert.equal(loadSession(store, "rider"), null);
});

test("an entry stored under the wrong role is rejected and removed", () => {
  const store = memoryStore();
  store.setItem("saathi.session.customer", JSON.stringify(room));
  assert.equal(loadSession(store, "customer"), null);
  assert.equal(store.getItem("saathi.session.customer"), null);
});

test("parseSession checks each field", () => {
  assert.equal(parseSession(null), null);
  assert.equal(parseSession({ ...room, role: "admin" }), null);
  assert.equal(parseSession({ ...room, token: "" }), null);
  assert.equal(parseSession({ ...room, token: "x".repeat(65) }), null);
  assert.equal(parseSession({ ...room, language: 5 }), null);
  assert.deepEqual(parseSession({ ...room, peer_language: null })?.peer_language, null);
});

test("a link to a different room wins over the saved session and replaces it", () => {
  const store = memoryStore();
  saveSession(store, room);
  assert.equal(loadSession(store, "rider", "QQQ222"), null);
  assert.equal(loadSession(store, "rider"), null);
});

test("a link to the saved room, or no usable link, keeps the saved session", () => {
  const store = memoryStore();
  saveSession(store, room);
  assert.deepEqual(loadSession(store, "rider", "ABC234"), room);
  assert.deepEqual(loadSession(store, "rider", null), room);
  assert.deepEqual(loadSession(store, "rider", ""), room);
  // Text that is not a room code is not a request for another room.
  assert.deepEqual(loadSession(store, "rider", "nope"), room);
});

test("a link code is compared as upper case", () => {
  const store = memoryStore();
  saveSession(store, room);
  assert.deepEqual(loadSession(store, "rider", "abc234"), room);
});

test("clearing removes only that role's session", () => {
  const store = memoryStore();
  saveSession(store, customerRoom);
  saveSession(store, room);
  clearSession(store, "rider");
  assert.equal(loadSession(store, "rider"), null);
  assert.deepEqual(loadSession(store, "customer"), customerRoom);
});

test("a notice is shown once, per role", () => {
  const store = memoryStore();
  setNotice(store, "rider", "The room has ended.");
  assert.equal(takeNotice(store, "customer"), null);
  assert.equal(takeNotice(store, "rider"), "The room has ended.");
  assert.equal(takeNotice(store, "rider"), null);
});

test("the home page takes whichever role's notice is waiting and clears both", () => {
  const store = memoryStore();
  setNotice(store, "customer", "first");
  setNotice(store, "rider", "second");
  assert.equal(takeAnyNotice(store), "first");
  assert.equal(takeNotice(store, "rider"), null);
  assert.equal(takeAnyNotice(store), null);
  assert.deepEqual(store.keys(), []);
});

test("a tab whose storage is blocked gets a store that remembers nothing", () => {
  // Node has no sessionStorage, which stands in for a browser that refuses access to it.
  const store = tabStorage();
  saveSession(store, room);
  setNotice(store, "rider", "x");
  assert.equal(loadSession(store, "rider"), null);
  assert.equal(takeAnyNotice(store), null);
});

test("storage that throws never breaks the page", () => {
  const broken = {
    getItem: () => {
      throw new Error("blocked");
    },
    setItem: () => {
      throw new Error("blocked");
    },
    removeItem: () => {
      throw new Error("blocked");
    },
  };
  saveSession(broken, room);
  setNotice(broken, "rider", "x");
  clearSession(broken, "rider");
  assert.equal(loadSession(broken, "rider"), null);
  assert.equal(takeNotice(broken, "rider"), null);
  assert.equal(takeAnyNotice(broken), null);
});
