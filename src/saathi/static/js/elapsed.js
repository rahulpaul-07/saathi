// @ts-check
// The recording clock on the microphone button: minutes and seconds, digits only, so it needs no
// translation.

/**
 * @param {number} milliseconds time since the recording started; negative counts as zero
 * @returns {string} such as "0:07" or "1:00"
 */
export function formatElapsed(milliseconds) {
  const seconds = Math.max(0, Math.floor(milliseconds / 1000));
  return `${Math.floor(seconds / 60)}:${String(seconds % 60).padStart(2, "0")}`;
}
