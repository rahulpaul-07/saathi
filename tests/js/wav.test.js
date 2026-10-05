// @ts-check
import assert from "node:assert/strict";
import { test } from "node:test";

import { MAX_SECONDS, clampToMaxDuration, encodeWav } from "../../src/saathi/static/js/wav.js";

/** @param {ArrayBuffer} buffer @param {number} offset @param {number} length */
const text = (buffer, offset, length) =>
  String.fromCharCode(...new Uint8Array(buffer, offset, length));

test("encodeWav writes a valid 16 kHz mono PCM16 header", () => {
  const wav = encodeWav(new Float32Array(160), 16000);
  const view = new DataView(wav);
  assert.equal(wav.byteLength, 44 + 320);
  assert.equal(text(wav, 0, 4), "RIFF");
  assert.equal(text(wav, 8, 4), "WAVE");
  assert.equal(view.getUint32(4, true), 36 + 320);
  assert.equal(view.getUint16(20, true), 1); // PCM
  assert.equal(view.getUint16(22, true), 1); // mono
  assert.equal(view.getUint32(24, true), 16000);
  assert.equal(view.getUint16(34, true), 16);
  assert.equal(text(wav, 36, 4), "data");
  assert.equal(view.getUint32(40, true), 320);
});

test("encodeWav converts and clips samples", () => {
  const view = new DataView(encodeWav(Float32Array.from([0, 1, -1, 2, -2, 0.5]), 16000));
  const sample = (/** @type {number} */ i) => view.getInt16(44 + i * 2, true);
  assert.deepEqual([0, 1, 2, 3, 4].map(sample), [0, 32767, -32768, 32767, -32768]);
  assert.equal(sample(5), Math.trunc(0.5 * 32767));
});

test("clampToMaxDuration truncates past 60 s and leaves shorter audio alone", () => {
  const long = new Float32Array(MAX_SECONDS * 100 + 5);
  assert.equal(clampToMaxDuration(long, 100).length, MAX_SECONDS * 100);
  const short = new Float32Array(10);
  assert.equal(clampToMaxDuration(short, 100), short);
});
