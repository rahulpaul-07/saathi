// @ts-check
// Pure helpers: no DOM, so they run under node --test.

export const TARGET_RATE = 16000;
export const MAX_SECONDS = 60;
// Mirrors the server limit (saathi.audio.MAX_AUDIO_BYTES). 60 s of 16 kHz PCM16 is about 1.9 MB.
export const MAX_BYTES = 2_500_000;
const HEADER_BYTES = 44;

/**
 * Clamp a recording to the 60 s the server accepts.
 * @param {Float32Array} samples
 * @param {number} sampleRate
 * @returns {Float32Array}
 */
export function clampToMaxDuration(samples, sampleRate) {
  const max = Math.floor(MAX_SECONDS * sampleRate);
  return samples.length > max ? samples.subarray(0, max) : samples;
}

/**
 * Encode mono float samples (-1..1) as a 16-bit PCM WAV file.
 * @param {Float32Array} samples
 * @param {number} sampleRate
 * @returns {ArrayBuffer}
 */
export function encodeWav(samples, sampleRate) {
  const dataBytes = samples.length * 2;
  const buffer = new ArrayBuffer(HEADER_BYTES + dataBytes);
  const view = new DataView(buffer);
  /** @param {number} offset @param {string} text */
  const writeText = (offset, text) => {
    for (let i = 0; i < text.length; i++) view.setUint8(offset + i, text.charCodeAt(i));
  };

  writeText(0, "RIFF");
  view.setUint32(4, 36 + dataBytes, true);
  writeText(8, "WAVE");
  writeText(12, "fmt ");
  view.setUint32(16, 16, true); // fmt chunk size
  view.setUint16(20, 1, true); // PCM
  view.setUint16(22, 1, true); // mono
  view.setUint32(24, sampleRate, true);
  view.setUint32(28, sampleRate * 2, true); // byte rate
  view.setUint16(32, 2, true); // block align
  view.setUint16(34, 16, true); // bits per sample
  writeText(36, "data");
  view.setUint32(40, dataBytes, true);

  for (let i = 0; i < samples.length; i++) {
    const clipped = Math.max(-1, Math.min(1, samples[i]));
    view.setInt16(HEADER_BYTES + i * 2, clipped < 0 ? clipped * 0x8000 : clipped * 0x7fff, true);
  }
  return buffer;
}
