// @ts-check
import { AudioPlayer } from "./audio-player.js";
import { parseLanguages } from "./languages.js";
import { getJson, joinRoom } from "./room-client.js";
import { enterRoom } from "./room-screen.js";
import { byId, fillLanguageSelect, requireChoice, setStatus } from "./ui.js";

const CODE_PATTERN = /^[A-Z0-9]{6}$/;

const codeInput = byId("code-input", HTMLInputElement);
const languageSelect = byId("language", HTMLSelectElement);
const joinButton = byId("join", HTMLButtonElement);
const joinStatusEl = byId("join-status", HTMLElement);
const setupEl = byId("setup", HTMLElement);
const roomEl = byId("room", HTMLElement);
const statusEl = byId("status", HTMLElement);

/** @type {import("./languages.js").Language[]} */
let languages = [];

async function onJoin() {
  const code = codeInput.value.trim().toUpperCase();
  if (!CODE_PATTERN.test(code)) {
    setStatus(joinStatusEl, "Enter the 6-character room code.", true);
    return;
  }
  joinButton.disabled = true;
  // Both players are started inside this tap: it is what lets later audio play without another tap.
  const players = [new AudioPlayer(), new AudioPlayer()];
  const unlocked = (await Promise.all(players.map((player) => player.unlock()))).every(Boolean);
  const result = await joinRoom(code, languageSelect.value);
  if (!result.ok) {
    joinButton.disabled = false;
    setStatus(joinStatusEl, result.message, true);
    return;
  }
  setupEl.hidden = true;
  roomEl.hidden = false;
  if (!unlocked) setStatus(statusEl, "Tap Repeat to hear each message.");
  enterRoom(result.data, languages, players);
}

joinButton.addEventListener("click", () => void onJoin());

const prefill = new URLSearchParams(location.search).get("code");
if (prefill) codeInput.value = prefill.toUpperCase().slice(0, 6);

try {
  languages = parseLanguages(await getJson("/languages"));
  fillLanguageSelect(languageSelect, languages);
  requireChoice([languageSelect], [joinButton]);
} catch {
  setStatus(joinStatusEl, "Could not load the language list. Reload the page.", true);
}
