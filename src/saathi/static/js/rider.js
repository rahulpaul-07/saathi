// @ts-check
import { AudioPlayer } from "./audio-player.js";
import { applyChrome, decodeBi, setChromeTable, setLanguage, tb } from "./i18n.js";
import { parseLanguages } from "./languages.js";
import { getJson, joinRoom } from "./room-client.js";
import { leaveRoom, reloadWhenRestored } from "./room-exit.js";
import { enterRoom } from "./room-screen.js";
import { loadSession, saveSession, tabStorage, takeNotice } from "./session.js";
import { byId, fillLanguageSelect, requireChoice, setStatus } from "./ui.js";

const ROLE = "rider";
const CODE_PATTERN = /^[A-Z0-9]{6}$/;

const codeInput = byId("code-input", HTMLInputElement);
const languageSelect = byId("language", HTMLSelectElement);
const joinButton = byId("join", HTMLButtonElement);
const joinStatusEl = byId("join-status", HTMLElement);
const setupEl = byId("setup", HTMLElement);
const roomEl = byId("room", HTMLElement);
const statusEl = byId("status", HTMLElement);
const store = tabStorage();

/** @type {import("./languages.js").Language[]} */
let languages = [];

async function onJoin() {
  const code = codeInput.value.trim().toUpperCase();
  if (!CODE_PATTERN.test(code)) {
    setStatus(joinStatusEl, tb("enter_code", "Enter the 6-character room code."), true);
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
  saveSession(store, result.data);
  showRoom(result.data, players);
  if (!unlocked) setStatus(statusEl, tb("tap_repeat_each", "Tap Repeat to hear each message."));
}

/**
 * @param {import("./room-client.js").RoomInfo} info
 * @param {AudioPlayer[]} players
 */
function showRoom(info, players) {
  setupEl.hidden = true;
  roomEl.hidden = false;
  enterRoom(info, languages, players, (end) => leaveRoom(ROLE, end));
}

joinButton.addEventListener("click", () => void onJoin());
reloadWhenRestored();

const prefill = new URLSearchParams(location.search).get("code");
if (prefill) codeInput.value = prefill.toUpperCase().slice(0, 6);

/** The page follows the language picked in the form, before a room is joined. */
languageSelect.addEventListener("change", () => {
  setLanguage(languageSelect.value);
  applyChrome();
});

try {
  setChromeTable(await getJson("/chrome").catch(() => null));
  languages = parseLanguages(await getJson("/languages"));
  fillLanguageSelect(languageSelect, languages);
  requireChoice([languageSelect], [joinButton]);
  // A link to another room wins over the room saved in this tab: the person asked for that one.
  const saved = loadSession(store, ROLE, prefill);
  if (saved) {
    // After a reload there is no tap, so audio stays locked until the person taps Repeat.
    showRoom(saved, [new AudioPlayer(), new AudioPlayer()]);
    setStatus(statusEl, tb("tap_repeat_each", "Tap Repeat to hear each message."));
  } else {
    const notice = takeNotice(store, ROLE);
    if (notice) setStatus(joinStatusEl, decodeBi(notice));
  }
} catch {
  setStatus(joinStatusEl, tb("language_list_failed", "Could not load the language list. Reload the page."), true);
}
