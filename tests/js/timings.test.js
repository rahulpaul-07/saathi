// @ts-check
import assert from "node:assert/strict";
import { test } from "node:test";
import { wasTimed } from "../../src/saathi/static/js/ui.js";

// The payloads the server sends: a timed turn, and a stored replay, which measures nothing.
const timedTurn = { stt_ms: 812, translate_ms: 905, tts_ms: 1104, total_ms: 2821 };
const storedReplay = { stt_ms: 0, translate_ms: 0, tts_ms: 0, total_ms: 0 };

test("a turn the server timed has a readout", () => {
  assert.equal(wasTimed(timedTurn), true);
});

test("a stored replay measures nothing, so it reports zeros and has no readout", () => {
  assert.equal(wasTimed(storedReplay), false);
});

test("a total that is not a positive number has no readout rather than a garbled one", () => {
  assert.equal(wasTimed({ total_ms: -1 }), false);
  assert.equal(wasTimed({ total_ms: Number.NaN }), false);
});
