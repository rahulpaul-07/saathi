// @ts-check
import { tb } from "./i18n.js";
import { MAX_SECONDS, TARGET_RATE, clampToMaxDuration, encodeWav } from "./wav.js";

/**
 * Thrown with a user-facing message; everything else is a bug and should surface. `text` holds
 * the message in both languages for the screen; `message` is the viewer's language alone.
 */
export class RecorderError extends Error {
  /** @param {import("./i18n.js").Bi} text */
  constructor(text) {
    super(text.local);
    this.text = text;
  }
}

/**
 * @typedef {{stop: () => Promise<Blob>}} Recording
 */

/**
 * Ask for the microphone and start recording. `onAutoStop` fires if the 60 s cap is reached;
 * the caller must then call `stop()` as usual to collect the audio.
 * @param {() => void} onAutoStop
 * @returns {Promise<Recording>}
 */
export async function startRecording(onAutoStop) {
  if (!window.isSecureContext || !navigator.mediaDevices?.getUserMedia) {
    throw new RecorderError(
      tb("mic_secure_page", "The microphone needs a secure page (HTTPS or localhost)."),
    );
  }
  /** @type {MediaStream} */
  let stream;
  try {
    stream = await navigator.mediaDevices.getUserMedia({
      audio: { channelCount: 1, echoCancellation: true, noiseSuppression: true },
    });
  } catch (error) {
    const name = error instanceof DOMException ? error.name : "";
    throw new RecorderError(
      name === "NotFoundError"
        ? tb("mic_not_found", "No microphone was found.")
        : tb(
            "mic_blocked",
            "Microphone access was blocked. Allow it in the browser's site settings, then try again.",
          ),
    );
  }

  const recorder = new MediaRecorder(stream);
  /** @type {Blob[]} */
  const chunks = [];
  recorder.addEventListener("dataavailable", (event) => {
    if (event.data.size > 0) chunks.push(event.data);
  });
  const stopped = new Promise((resolve) =>
    recorder.addEventListener("stop", resolve, { once: true }),
  );
  recorder.start();
  const timer = setTimeout(() => {
    if (recorder.state === "recording") onAutoStop();
  }, MAX_SECONDS * 1000);

  return {
    async stop() {
      clearTimeout(timer);
      if (recorder.state !== "inactive") recorder.stop();
      await stopped;
      for (const track of stream.getTracks()) track.stop();
      return new Blob(chunks, { type: recorder.mimeType });
    },
  };
}

/**
 * Decode a MediaRecorder blob and return a 16 kHz mono PCM16 WAV.
 * decodeAudioData on a 16 kHz offline context resamples; rendering through a mono context mixes
 * channels down.
 * @param {Blob} recorded
 * @returns {Promise<Blob>}
 */
export async function toWav(recorded) {
  const encoded = await recorded.arrayBuffer();
  let decoded;
  try {
    decoded = await new OfflineAudioContext(1, 1, TARGET_RATE).decodeAudioData(encoded);
  } catch {
    throw new RecorderError(
      tb("recording_unreadable", "This browser could not read the recording. Please try again."),
    );
  }
  const frames = Math.max(1, Math.ceil(decoded.duration * TARGET_RATE));
  const context = new OfflineAudioContext(1, frames, TARGET_RATE);
  const source = context.createBufferSource();
  source.buffer = decoded;
  source.connect(context.destination);
  source.start();
  const mono = await context.startRendering();
  const samples = clampToMaxDuration(mono.getChannelData(0), TARGET_RATE);
  return new Blob([encodeWav(samples, TARGET_RATE)], { type: "audio/wav" });
}
