// @ts-check
import assert from "node:assert/strict";
import { test } from "node:test";

import {
  clearSession,
  loadSession,
  parseSession,
  saveSession,
  setNotice,
  takeNotice,
} from "../../src/saathi/static/js/session.js";

function memoryStore() {
  const items = new Map();
  return {
    getItem: (/** @type {string} */ key) => items.get(key) ?? null,
    setItem: (/** @type {string} */ key, /** @type {string} */ value) => void items.set(key, value),
    removeItem: (/** @type {string} */ key) => void items.delete(key),
  };
}

const room = { code: "ABC234", token: "tok-123", role: "rider", language: "ta", peer_language: "kn" };

test("a saved session loads back for the same role only", () => {
  const store = memoryStore();
  saveSession(store, room);
  assert.deepEqual(loadSession(store, "rider"), room);
  assert.equal(loadSession(store, "customer"), null);
});

test("a malformed stored session is rejected and removed", () => {
  const store = memoryStore();
  store.setItem("saathi.session", JSON.stringify({ ...room, code: "abc" }));
  assert.equal(loadSession(store, "rider"), null);
  assert.equal(store.getItem("saathi.session"), null);
  store.setItem("saathi.session", "{not json");
  assert.equal(loadSession(store, "rider"), null);
});

test("parseSession checks each field", () => {
  assert.equal(parseSession(null), null);
  assert.equal(parseSession({ ...room, role: "admin" }), null);
  assert.equal(parseSession({ ...room, token: "" }), null);
  assert.equal(parseSession({ ...room, token: "x".repeat(65) }), null);
  assert.equal(parseSession({ ...room, language: 5 }), null);
  assert.deepEqual(parseSession({ ...room, peer_language: null })?.peer_language, null);
});

test("clearing removes the session", () => {
  const store = memoryStore();
  saveSession(store, room);
  clearSession(store);
  assert.equal(loadSession(store, "rider"), null);
});

test("a notice is shown once", () => {
  const store = memoryStore();
  setNotice(store, "The room has ended.");
  assert.equal(takeNotice(store), "The room has ended.");
  assert.equal(takeNotice(store), null);
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
  setNotice(broken, "x");
  clearSession(broken);
  assert.equal(loadSession(broken, "rider"), null);
  assert.equal(takeNotice(broken), null);
});
