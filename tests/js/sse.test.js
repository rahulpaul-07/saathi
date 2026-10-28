// @ts-check
import assert from "node:assert/strict";
import { test } from "node:test";

import { createSseParser } from "../../src/saathi/static/js/sse.js";

/** @param {string[]} chunks */
function parse(chunks) {
  /** @type {import("../../src/saathi/static/js/sse.js").SseEvent[]} */
  const events = [];
  const parser = createSseParser((event) => events.push(event));
  for (const chunk of chunks) parser.push(chunk);
  return events;
}

test("parses named JSON events and ignores keepalive comments", () => {
  const events = parse(['event: state\ndata: {"a":1}\n\n: keepalive\n\nevent: closed\ndata: {}\n\n']);
  assert.deepEqual(events, [
    { name: "state", data: { a: 1 } },
    { name: "closed", data: {} },
  ]);
});

test("handles chunks split anywhere, CRLF and multibyte text", () => {
  const whole = 'event: turn\r\ndata: {"t":"ನಮಸ್ಕಾರ"}\r\n\r\n';
  for (let cut = 1; cut < whole.length; cut++) {
    const events = parse([whole.slice(0, cut), whole.slice(cut)]);
    assert.deepEqual(events, [{ name: "turn", data: { t: "ನಮಸ್ಕಾರ" } }], `cut at ${cut}`);
  }
});

test("drops events with malformed JSON and keeps going", () => {
  const events = parse(["event: bad\ndata: {oops\n\nevent: ok\ndata: 1\n\n"]);
  assert.deepEqual(events, [{ name: "ok", data: 1 }]);
});

test("an incomplete event is not delivered", () => {
  assert.deepEqual(parse(["event: turn\ndata: {}\n"]), []);
});
