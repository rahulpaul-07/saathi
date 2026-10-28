// @ts-check
import assert from "node:assert/strict";
import { test } from "node:test";

import { languageLabel, parseLanguages } from "../../src/saathi/static/js/languages.js";
import { parseQuickReplyTable, quickReplyOptions } from "../../src/saathi/static/js/quick-replies.js";

const table = parseQuickReplyTable({
  ids: { rider: ["reached_gate"], customer: ["come_to_gate"] },
  languages: {
    en: {
      reached_gate: { text: "I am at the gate", review_status: "source" },
      come_to_gate: { text: "Come to the gate", review_status: "source" },
    },
    hi: {
      reached_gate: { text: "मैं गेट पर हूँ", review_status: "reviewed" },
      come_to_gate: { text: "द्वार पर आ जाओ।", review_status: "pending" },
    },
  },
});

test("each role sees only its own phrase ids", () => {
  assert.deepEqual(quickReplyOptions(table, "rider", "hi", "en").items.map((i) => i.id), ["reached_gate"]);
  assert.deepEqual(quickReplyOptions(table, "customer", "hi", "en").items.map((i) => i.id), ["come_to_gate"]);
});

test("labels are in the sender's language, either role", () => {
  assert.equal(quickReplyOptions(table, "rider", "hi", "en").items[0].label, "मैं गेट पर हूँ");
  assert.equal(quickReplyOptions(table, "customer", "hi", "en").items[0].label, "द्वार पर आ जाओ।");
});

test("a sender language missing from the table falls back to English labels", () => {
  const options = quickReplyOptions(table, "customer", "ta", "hi");
  assert.equal(options.enabled, true);
  assert.equal(options.items[0].label, "Come to the gate");
});

test("disabled with a reason when the recipient language is not in the table", () => {
  const options = quickReplyOptions(table, "rider", "en", "ta");
  assert.equal(options.enabled, false);
  assert.match(options.reason ?? "", /other person's language/);
});

test("a malformed table is rejected", () => {
  assert.throws(() => parseQuickReplyTable({ ids: "x" }));
  assert.throws(() => parseQuickReplyTable({ ids: { rider: "x" }, languages: {} }));
});

test("tier labels: core none, reviewed and beta marked", () => {
  assert.equal(languageLabel({ code: "kn", name: "Kannada", tier: "core" }), "Kannada");
  assert.equal(languageLabel({ code: "te", name: "Telugu", tier: "reviewed" }), "Telugu (reviewed)");
  assert.equal(languageLabel({ code: "ta", name: "Tamil", tier: "beta" }), "Tamil (beta)");
});

test("parseLanguages rejects bad entries", () => {
  assert.throws(() => parseLanguages([{ code: 1 }]));
  assert.throws(() => parseLanguages({}));
});
