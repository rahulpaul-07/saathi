// @ts-check
import assert from "node:assert/strict";
import { afterEach, test } from "node:test";

import { chipsFromFacts, cardChips } from "../../src/saathi/static/js/chips.js";
import { classify } from "../../src/saathi/static/js/retry.js";
import {
  Bi,
  currentLanguage,
  isUnreviewed,
  setChromeTable,
  setLanguage,
  t,
} from "../../src/saathi/static/js/i18n.js";

const table = {
  languages: {
    en: { check_this: { text: "check this", review_status: "source" } },
    hi: {
      check_this: { text: "इसे जाँचें", review_status: "pending" },
      changed_was: { text: "बदला, पहले था", review_status: "reviewed" },
      still_busy: { text: "अभी व्यस्त है। फिर कोशिश करें।", review_status: "pending" },
    },
  },
};

afterEach(() => {
  setChromeTable(null);
  setLanguage("en");
});

test("without a table every lookup returns the English fallback", () => {
  setChromeTable(null);
  setLanguage("hi");
  assert.equal(t("check_this", "check this"), "check this");
  assert.equal(currentLanguage(), "en");
});

test("a loaded language answers in that language, and falls back per missing id", () => {
  setChromeTable(table);
  setLanguage("hi");
  assert.equal(t("check_this", "check this"), "इसे जाँचें");
  assert.equal(t("not_translated", "English only"), "English only");
});

test("an unknown language code falls back to English", () => {
  setChromeTable(table);
  setLanguage("zz");
  assert.equal(currentLanguage(), "en");
  assert.equal(t("check_this", "check this"), "check this");
});

test("only languages with pending strings are flagged as unreviewed", () => {
  setChromeTable(table);
  setLanguage("en");
  assert.equal(isUnreviewed(), false);
  setLanguage("hi");
  assert.equal(isUnreviewed(), true);
});

test("chip notes and retry messages follow the language", () => {
  setChromeTable(table);
  setLanguage("hi");
  const base = { heard: "", confidence: "low", ambiguous: false, reading: null };
  const [chip] = chipsFromFacts([{ ...base, kind: "gate", value: "5" }]);
  assert.equal(chip.note, "इसे जाँचें");
  const [changed] = cardChips([{ fact: { ...base, confidence: "high", kind: "gate", value: "4" }, previous: "2" }]);
  assert.equal(changed.note, "बदला, पहले था 2");
  assert.deepEqual(classify(503), {
    outcome: "transient",
    message: new Bi("अभी व्यस्त है। फिर कोशिश करें।", "Still busy. Try again."),
    keepRecording: true,
  });
});
