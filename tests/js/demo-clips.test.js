// @ts-check
import assert from "node:assert/strict";
import { test } from "node:test";

import { clipsForLanguage, oneLine, parseDemoClips } from "../../src/saathi/static/js/demo-clips.js";

test("keeps well-formed clips and drops everything else", () => {
  const clips = parseDemoClips([
    { id: "kn-gate", lang: "kn", label: "Gate 2", label_local: "ಗೇಟ್ 2" },
    { id: "ta-gate", lang: "ta", label: "Gate 3" },
    { id: "../x", lang: "kn", label: "bad id" },
    { id: "ok", lang: 5, label: "bad lang" },
    null,
    "text",
  ]);
  assert.deepEqual(clips, [
    { id: "kn-gate", lang: "kn", label: "Gate 2", labelLocal: "ಗೇಟ್ 2" },
    { id: "ta-gate", lang: "ta", label: "Gate 3", labelLocal: "" },
  ]);
});

test("an option reads local / English, or English alone when there is no local name", () => {
  assert.equal(oneLine("ಗೇಟ್ 2", "Gate 2"), "ಗೇಟ್ 2 / Gate 2");
  assert.equal(oneLine("", "Gate 2"), "Gate 2");
  assert.equal(oneLine("Gate 2", "Gate 2"), "Gate 2");
});

test("a non-list body gives no clips", () => {
  assert.deepEqual(parseDemoClips({ clips: [] }), []);
  assert.deepEqual(parseDemoClips(null), []);
});

test("a participant is offered only clips in their own language", () => {
  const clips = [
    { id: "a", lang: "kn", label: "A", labelLocal: "" },
    { id: "b", lang: "ta", label: "B", labelLocal: "" },
  ];
  assert.deepEqual(clipsForLanguage(clips, "ta").map((c) => c.id), ["b"]);
  assert.deepEqual(clipsForLanguage(clips, "hi"), []);
});
