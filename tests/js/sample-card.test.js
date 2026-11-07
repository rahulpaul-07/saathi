// @ts-check
// The sample card on the home page must stay equal to the expected facts of the en-street demo clip.
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { test } from "node:test";
import { chipsFromFacts } from "../../src/saathi/static/js/chips.js";
import { SAMPLE_FACTS } from "../../src/saathi/static/js/sample-card.js";

const CLIP_SET = JSON.parse(
  readFileSync(new URL("../../demo/clip_set.json", import.meta.url), "utf8"),
);
const SOURCE = CLIP_SET.clips.find((/** @type {{id: string}} */ clip) => clip.id === "en-street");

/** kind to value, so the order a list was written in does not matter */
const byKind = (/** @type {{kind: string, value: string}[]} */ facts) =>
  Object.fromEntries(facts.map(({ kind, value }) => [kind, value]));

test("the sample card is the expected result of the en-street demo clip", () => {
  assert.ok(SOURCE, "en-street is missing from demo/clip_set.json");
  assert.deepEqual(byKind(SAMPLE_FACTS), byKind(SOURCE.expected));
});

test("the sample draws as four tiles in card order", () => {
  assert.deepEqual(
    chipsFromFacts(SAMPLE_FACTS).map((chip) => chip.kind),
    ["gate", "cross", "main", "landmark"],
  );
});

test("a sample that drifts from the clip is caught", () => {
  const drifted = SAMPLE_FACTS.map((fact) => (fact.kind === "gate" ? { ...fact, value: "9" } : fact));
  assert.notDeepEqual(byKind(drifted), byKind(SOURCE.expected));
  assert.notDeepEqual(byKind(SAMPLE_FACTS.slice(1)), byKind(SOURCE.expected));
});
