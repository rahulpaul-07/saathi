// @ts-check
import assert from "node:assert/strict";
import { test } from "node:test";

import { nameForViewer, parseLanguages } from "../../src/saathi/static/js/languages.js";

const [kannada] = parseLanguages([
  {
    code: "kn",
    name: "Kannada",
    tier: "core",
    native: "ಕನ್ನಡ",
    names: { hi: "कन्नड़", kn: "ಕನ್ನಡ", en: "Kannada" },
  },
]);

test("a Hindi viewer sees the name in Devanagari plus English", () => {
  assert.equal(nameForViewer(kannada, "hi", "?"), "कन्नड़ (Kannada)");
});

test("an English viewer sees the English name once", () => {
  assert.equal(nameForViewer(kannada, "en", "?"), "Kannada");
});

test("a viewer with no spelling for the language gets the English name", () => {
  assert.equal(nameForViewer(kannada, "ta", "?"), "Kannada");
});

test("an unknown language gets the fallback", () => {
  assert.equal(nameForViewer(undefined, "hi", "other"), "other");
});
