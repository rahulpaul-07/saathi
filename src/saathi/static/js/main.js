// @ts-check
import { MAX_AUTO_RETRIES } from "./retry.js";
import { wavUrlFromBase64 } from "./player.js";
import { RecorderError, startRecording, toWav } from "./recorder.js";
import { parseLanguages } from "./languages.js";
import { getJson } from "./room-client.js";
import { sendTurn } from "./turn-client.js";
import { fillLanguageSelect, renderTimings as renderStageTimings } from "./ui.js";

/** @type {import("./languages.js").Language[]} */
let languages = [];

/**
 * @template {HTMLElement} T
 * @param {string} id
 * @param {new () => T} type
 * @returns {T}
 */
function byId(id, type) {
  const element = document.getElementById(id);
  if (!(element instanceof type)) throw new Error(`Missing element #${id}`);
  return element;
}

const talkButtons = [byId("talk-a", HTMLButtonElement), byId("talk-b", HTMLButtonElement)];
const statusEl = byId("status", HTMLElement);
const actionsEl = byId("actions", HTMLElement);
const retryButton = byId("retry", HTMLButtonElement);
const discardButton = byId("discard", HTMLButtonElement);
const resultEl = byId("result", HTMLElement);
const transcriptEl = byId("transcript", HTMLElement);
const translationEl = byId("translation", HTMLElement);
const replayButton = byId("replay", HTMLButtonElement);
const timingsEl = byId("timings", HTMLElement);
const pickers = [byId("lang-a", HTMLSelectElement), byId("lang-b", HTMLSelectElement)];

/**
 * @typedef {{wav: Blob, src: string, tgt: string}} Pending a recording not yet turned into a result
 */

/** @type {{recording: import("./recorder.js").Recording | null, side: number,
 *   busy: boolean, pending: Pending | null, audio: HTMLAudioElement | null,
 *   audioUrl: string | null}} */
const state = {
  recording: null,
  side: 0,
  busy: false,
  pending: null,
  audio: null,
  audioUrl: null,
};

/** @returns {string[] | null} the two chosen language codes, or null until they are two different ones */
function currentPair() {
  const [a, b] = pickers.map((picker) => picker.value);
  return a && b && a !== b ? [a, b] : null;
}

/** @param {string} code */
function languageName(code) {
  return languages.find((language) => language.code === code)?.name ?? code;
}

/**
 * @param {string} text
 * @param {boolean} [isError]
 */
function setStatus(text, isError = false) {
  statusEl.textContent = text;
  statusEl.classList.toggle("error", isError);
}

function renderControls() {
  const pair = currentPair();
  const recording = state.recording !== null;
  talkButtons.forEach((button, side) => {
    const label = button.querySelector(".label");
    const isRecordingThis = recording && state.side === side;
    if (label) {
      if (isRecordingThis) label.textContent = "Stop and translate";
      else label.textContent = pair ? `Speak ${languageName(pair[side])}` : "Choose two languages";
    }
    button.setAttribute("aria-pressed", String(isRecordingThis));
    button.disabled =
      !pair || state.busy || state.pending !== null || (recording && !isRecordingThis);
  });
  for (const picker of pickers) picker.disabled = state.busy || recording || state.pending !== null;
  actionsEl.hidden = state.pending === null || state.busy;
}

/** @param {number} side */
async function beginRecording(side) {
  state.busy = true;
  renderControls();
  try {
    state.recording = await startRecording(() => void finishRecording());
    state.side = side;
    setStatus("Recording... tap again to stop (60 s maximum).");
  } catch (error) {
    if (!(error instanceof RecorderError)) throw error;
    setStatus(error.message, true);
  } finally {
    state.busy = false;
    renderControls();
  }
}

async function finishRecording() {
  const recording = state.recording;
  if (!recording || state.busy) return;
  const tappedStopAt = performance.now();
  const pair = currentPair();
  if (!pair) return; // pickers are locked while recording, so this cannot happen
  const [src, tgt] = state.side === 0 ? pair : [...pair].reverse();
  state.recording = null;
  state.busy = true;
  renderControls();
  setStatus("Preparing audio...");
  try {
    const wav = await toWav(await recording.stop());
    await submit({ wav, src, tgt }, tappedStopAt);
  } catch (error) {
    if (!(error instanceof RecorderError)) throw error;
    setStatus(error.message, true);
  } finally {
    state.busy = false;
    renderControls();
  }
}

/**
 * Send the recording. It stays in `state.pending` until the turn succeeds or the user discards it.
 * @param {Pending} pending
 * @param {number} tappedStopAt performance.now() when the user tapped stop (or Try again)
 */
async function submit(pending, tappedStopAt) {
  state.pending = pending;
  setStatus("Translating...");
  const outcome = await sendTurn(pending.wav, pending.src, pending.tgt, {
    onRetry: (attempt) => setStatus(`One moment... (retry ${attempt} of ${MAX_AUTO_RETRIES})`),
  });
  if (!outcome.ok) {
    if (!outcome.keepRecording) state.pending = null;
    setStatus(outcome.message, true);
    return;
  }
  state.pending = null;
  setStatus("Playing translation.");
  await showResult(outcome.data, tappedStopAt);
}

/**
 * @param {import("./turn-client.js").TurnResult} data
 * @param {number} tappedStopAt
 */
async function showResult(data, tappedStopAt) {
  // textContent only: transcripts and translations are untrusted text, never HTML.
  transcriptEl.textContent = data.transcript;
  translationEl.textContent = data.translation;
  resultEl.hidden = false;

  if (state.audioUrl) URL.revokeObjectURL(state.audioUrl);
  state.audioUrl = wavUrlFromBase64(data.audio_base64);
  state.audio = new Audio(state.audioUrl);
  const audio = state.audio;
  /** @type {number | null} */
  let playbackMs = null;
  audio.addEventListener(
    "playing",
    () => {
      playbackMs = performance.now() - tappedStopAt;
      renderTimings(data.timings, playbackMs);
    },
    { once: true },
  );
  renderTimings(data.timings, playbackMs);
  await playCurrent();
}

async function playCurrent() {
  if (!state.audio) return;
  try {
    await state.audio.play();
  } catch {
    // Browsers can block audio that did not start from a tap; the button always works.
    setStatus("Tap Play again to hear the translation.", true);
  }
}

/**
 * @param {import("./turn-client.js").Timings} timings
 * @param {number | null} tapToPlaybackMs
 */
function renderTimings(timings, tapToPlaybackMs) {
  renderStageTimings(timingsEl, timings, [
    [
      "Stop tap to playback",
      tapToPlaybackMs === null ? "waiting" : `${Math.round(tapToPlaybackMs)} ms`,
    ],
  ]);
}

talkButtons.forEach((button, side) => {
  button.addEventListener("click", () => {
    if (state.busy) return;
    if (state.recording) void finishRecording();
    else void beginRecording(side);
  });
});

retryButton.addEventListener("click", () => {
  const pending = state.pending;
  if (!pending || state.busy) return;
  state.busy = true;
  renderControls();
  submit(pending, performance.now()).finally(() => {
    state.busy = false;
    renderControls();
  });
});

discardButton.addEventListener("click", () => {
  state.pending = null;
  setStatus("Recording discarded. Ready.");
  renderControls();
});

replayButton.addEventListener("click", () => {
  if (state.audio) state.audio.currentTime = 0;
  void playCurrent();
});

for (const picker of pickers) picker.addEventListener("change", renderControls);

try {
  languages = parseLanguages(await getJson("/languages"));
  for (const picker of pickers) fillLanguageSelect(picker, languages);
} catch {
  setStatus("Could not load the language list. Reload the page.", true);
}
renderControls();
