// @ts-check
// Demo input mode: the list of prepared clips the server offers (only when SAATHI_DEMO_INPUT is on).

/** @typedef {{id: string, lang: string, label: string, labelLocal: string}} DemoClip */

/**
 * Keep only well-formed entries; anything else from the server is ignored, never rendered.
 * @param {unknown} body
 * @returns {DemoClip[]}
 */
export function parseDemoClips(body) {
  if (!Array.isArray(body)) return [];
  /** @type {DemoClip[]} */
  const clips = [];
  for (const item of body) {
    if (
      item &&
      typeof item.id === "string" &&
      /^[a-z0-9][a-z0-9_-]{0,39}$/.test(item.id) &&
      typeof item.lang === "string" &&
      typeof item.label === "string"
    ) {
      const local = typeof item.label_local === "string" ? item.label_local : "";
      clips.push({ id: item.id, lang: item.lang, label: item.label, labelLocal: local });
    }
  }
  return clips;
}

/**
 * An <option> holds text only, so the two lines go on one: "local / English".
 * @param {string} local
 * @param {string} english
 */
export function oneLine(local, english) {
  return local === "" || local === english ? english : `${local} / ${english}`;
}

/**
 * A participant sends clips spoken in their own language.
 * @param {DemoClip[]} clips
 * @param {string} language
 */
export function clipsForLanguage(clips, language) {
  return clips.filter((clip) => clip.lang === language);
}
