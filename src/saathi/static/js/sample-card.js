// @ts-check
// The delivery card drawn on the home page. Its facts are the expected facts of the "en-street" demo
// clip ("Second cross, fourth main, gate number three, near the temple." in demo/clip_set.json), so
// the preview invents no values. They are what the sentence says, not what the pipeline made of the
// clip's audio: in the 50-clip run the speech service wrote "1/4 main", so that run has no main tile
// (eval/results/demo_set_after_fixes.md). tests/js/sample-card.test.js keeps the two equal.

/** @type {import("./chips.js").Fact[]} */
export const SAMPLE_FACTS = [
  { kind: "cross", value: "2", heard: "Second cross", confidence: "high", ambiguous: false, reading: null },
  { kind: "main", value: "4", heard: "fourth main", confidence: "high", ambiguous: false, reading: null },
  { kind: "gate", value: "3", heard: "gate number three", confidence: "high", ambiguous: false, reading: null },
  { kind: "landmark", value: "temple", heard: "the temple", confidence: "high", ambiguous: false, reading: null },
];
