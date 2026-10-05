// @ts-check

/**
 * Decode base64 into a WAV blob URL. The caller revokes it.
 * @param {string} base64
 * @returns {string}
 */
export function wavUrlFromBase64(base64) {
  const binary = atob(base64);
  const bytes = new Uint8Array(binary.length);
  for (let i = 0; i < binary.length; i++) bytes[i] = binary.charCodeAt(i);
  return URL.createObjectURL(new Blob([bytes], { type: "audio/wav" }));
}
