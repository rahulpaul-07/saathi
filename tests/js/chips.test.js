// @ts-check
import assert from "node:assert/strict";
import { test } from "node:test";

import { chipsFromFacts } from "../../src/saathi/static/js/chips.js";

const base = { heard: "", confidence: "high", ambiguous: false, reading: null };

test("orders chips by kind and labels them", () => {
  const chips = chipsFromFacts([
    { ...base, kind: "landmark", value: "blue temple" },
    { ...base, kind: "gate", value: "2" },
    { ...base, kind: "floor", value: "3" },
  ]);
  assert.deepEqual(
    chips.map((c) => [c.label, c.value]),
    [["Gate", "2"], ["Floor", "3"], ["Landmark", "blue temple"]],
  );
});

test("the label comes from the server in the reader's language and flags unreviewed ones", () => {
  const chips = chipsFromFacts([
    { ...base, kind: "gate", value: "2", label: "গেট", label_status: "reviewed" },
    { ...base, kind: "cross", value: "2", label: "ক্রস", label_status: "pending" },
  ]);
  assert.deepEqual(
    chips.map((c) => [c.label, c.labelPending]),
    [["গেট", false], ["ক্রস", true]],
  );
});

test("ambiguous facts show the heard words with the reading as a note", () => {
  const [chip] = chipsFromFacts([
    { ...base, kind: "flat", value: "one four", ambiguous: true, reading: "14" },
  ]);
  assert.equal(chip.value, "one four");
  assert.equal(chip.note, "could be 14");
});

test("low confidence asks for a check", () => {
  const [chip] = chipsFromFacts([{ ...base, kind: "gate", value: "5", confidence: "low" }]);
  assert.equal(chip.note, "check this");
});

test("skips malformed entries and unknown kinds instead of throwing", () => {
  assert.deepEqual(chipsFromFacts(null), []);
  assert.deepEqual(
    chipsFromFacts([null, 5, { kind: "gate" }, { ...base, kind: "sauce", value: "x" }, { ...base, kind: "gate", value: "" }]),
    [],
  );
});

test("the listener sees the landmark in their language, the speaker sees what was said", () => {
  const facts = [{ ...base, kind: "landmark", value: "ಗಣೇಶ ದೇವಸ್ಥಾನ", local: "গণেশ মন্দির" }];
  assert.equal(chipsFromFacts(facts, true)[0].value, "গণেশ মন্দির");
  assert.equal(chipsFromFacts(facts)[0].value, "ಗಣೇಶ ದೇವಸ್ಥಾನ");
});

test("a landmark without a local name shows the class only to the listener", () => {
  const facts = [{ ...base, kind: "landmark", value: "ಗಣೇಶ ದೇವಸ್ಥಾನ", local: null }];
  const [chip] = chipsFromFacts(facts, true);
  assert.equal(chip.label, "Landmark");
  assert.equal(chip.value, "");
  assert.equal(chip.note, "name not available");
});

test("numbers are the same for both sides", () => {
  const facts = [{ ...base, kind: "gate", value: "2", local: null }];
  assert.equal(chipsFromFacts(facts, true)[0].value, "2");
});

test("markup in a value stays a plain string", () => {
  const [chip] = chipsFromFacts([{ ...base, kind: "landmark", value: "<img src=x onerror=1>" }]);
  assert.equal(chip.value, "<img src=x onerror=1>");
});
