// @ts-check
import assert from "node:assert/strict";
import { test } from "node:test";

import { cardChips, chipsFromFacts } from "../../src/saathi/static/js/chips.js";

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

const original = "ಗಣೇಶ ದೇವಸ್ಥಾನ";

test("kn to hi: the listener sees the translation with the original in brackets", () => {
  const facts = [{ ...base, kind: "landmark", value: original, local: "गणेश मंदिर" }];
  const [chip] = chipsFromFacts(facts, true);
  assert.equal(chip.value, `गणेश मंदिर (${original})`);
  assert.equal(chip.original, original);
  assert.equal(chip.machineTranslated, true);
});

test("the speaker sees what was said, not marked as translated", () => {
  const facts = [{ ...base, kind: "landmark", value: original, local: "गणेश मंदिर" }];
  const [chip] = chipsFromFacts(facts);
  assert.equal(chip.value, original);
  assert.equal(chip.machineTranslated, false);
});

test("same language: local equal to the original shows the original only", () => {
  const facts = [{ ...base, kind: "landmark", value: original, local: original }];
  const [chip] = chipsFromFacts(facts, true);
  assert.equal(chip.value, original);
  assert.equal(chip.machineTranslated, false);
});

test("a failed or empty translation shows the original only", () => {
  for (const local of [null, "", "   ", undefined]) {
    const facts = [{ ...base, kind: "landmark", value: original, local }];
    const [chip] = chipsFromFacts(facts, true);
    assert.equal(chip.value, original);
    assert.equal(chip.note, null);
    assert.equal(chip.machineTranslated, false);
  }
});

test("numeric chips are untouched, even when the server sends a local value", () => {
  const kinds = ["gate", "cross", "main", "floor", "block", "flat"];
  const facts = kinds.map((kind) => ({ ...base, kind, value: "2", local: "दो" }));
  for (const chip of chipsFromFacts(facts, true)) {
    assert.equal(chip.value, "2");
    assert.equal(chip.machineTranslated, false);
  }
});

test("markup in a value stays a plain string", () => {
  const [chip] = chipsFromFacts([{ ...base, kind: "landmark", value: "<img src=x onerror=1>" }]);
  assert.equal(chip.value, "<img src=x onerror=1>");
});

const cardFact = { ...base, kind: "gate", value: "4" };

test("a card entry that replaced a value shows changed and the old value", () => {
  const [chip] = cardChips([{ fact: cardFact, previous: "2" }]);
  assert.equal(chip.changed, true);
  assert.equal(chip.value, "4");
  assert.equal(chip.note, "changed, was 2");
});

test("a card entry without a previous value is plain", () => {
  const [chip] = cardChips([{ fact: cardFact, previous: null }]);
  assert.equal(chip.changed, false);
  assert.equal(chip.note, null);
});

test("changed joins an existing note, and the card keeps the fixed order", () => {
  const low = { ...base, kind: "floor", value: "3", confidence: "low" };
  const chips = cardChips([
    { fact: low, previous: "1" },
    { fact: cardFact, previous: null },
  ]);
  assert.deepEqual(
    chips.map((chip) => chip.kind),
    ["gate", "floor"],
  );
  assert.equal(chips[1].note, "check this; changed, was 1");
});

test("a malformed card is empty and never throws", () => {
  assert.deepEqual(cardChips(undefined), []);
  assert.deepEqual(cardChips([null, { fact: 1 }, {}]), []);
});
