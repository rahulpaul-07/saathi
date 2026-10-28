// @ts-check
import { encodeWav } from "./wav.js";

/**
 * One persistent <audio> element. Browsers allow a later play() on an element that a tap already
 * started, so the rider's Join tap calls `unlock()` and every later turn can auto-play.
 */
export class AudioPlayer {
  constructor() {
    this.element = new Audio();
    /** @type {string | null} */
    this.url = null;
    this.unlocked = false;
  }

  /** Call from a user gesture. Plays a few milliseconds of silence to satisfy autoplay rules. */
  async unlock() {
    const silent = URL.createObjectURL(
      new Blob([encodeWav(new Float32Array(160), 16000)], { type: "audio/wav" }),
    );
    this.element.src = silent;
    try {
      await this.element.play();
      this.unlocked = true;
    } catch {
      this.unlocked = false;
    } finally {
      URL.revokeObjectURL(silent);
    }
    return this.unlocked;
  }

  /**
   * Load new audio (taking ownership of the object URL) and start it.
   * @param {string} url
   * @returns {Promise<boolean>} false when the browser refused to play
   */
  async play(url) {
    if (this.url) URL.revokeObjectURL(this.url);
    this.url = url;
    this.element.src = url;
    return this.replay();
  }

  /** Replay what is loaded, locally; no network call. */
  async replay() {
    if (!this.url) return false;
    this.element.currentTime = 0;
    try {
      await this.element.play();
      return true;
    } catch {
      return false;
    }
  }

  get hasAudio() {
    return this.url !== null;
  }
}
