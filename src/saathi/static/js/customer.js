// @ts-check
import { AudioPlayer } from "./audio-player.js";
import { applyChrome, decodeBi, setChromeTable, setLanguage, tb } from "./i18n.js";
import { parseLanguages } from "./languages.js";
import { createRoom, fetchQrUrl, getJson } from "./room-client.js";
import { leaveRoom, reloadWhenRestored } from "./room-exit.js";
import { enterRoom } from "./room-screen.js";
import { loadSession, saveSession, tabStorage, takeNotice } from "./session.js";
import { byId, fillLanguageSelect, requireChoice, setStatus } from "./ui.js";

const ROLE = "customer";

const languageSelect = byId("language", HTMLSelectElement);
const createButton = byId("create", HTMLButtonElement);
const setupEl = byId("setup", HTMLElement);
const setupStatusEl = byId("setup-status", HTMLElement);
const roomEl = byId("room", HTMLElement);
const codeEl = byId("code", HTMLElement);
const linkEl = byId("link", HTMLElement);
const qrEl = byId("qr", HTMLImageElement);
const store = tabStorage();

/** @type {import("./languages.js").Language[]} */
let languages = [];

/**
 * @param {import("./room-client.js").RoomInfo} info
 * @param {AudioPlayer[]} players
 */
function showRoom(info, players) {
  setupEl.hidden = true;
  roomEl.hidden = false;
  codeEl.textContent = info.code;
  linkEl.textContent = `${location.origin}/rider.html?code=${info.code}`;
  void showQr(info);
  enterRoom(info, languages, players, (end) => leaveRoom(ROLE, end));
}

/**
 * The QR code is a convenience: the code and link above it stay, so a failed load shows nothing.
 * @param {import("./room-client.js").RoomInfo} info
 */
async function showQr(info) {
  const url = await fetchQrUrl(info);
  if (url === null) return;
  qrEl.src = url;
  qrEl.hidden = false;
}

async function onCreate() {
  createButton.disabled = true;
  // Both players are started inside this tap, which lets the other person's audio play later.
  const players = [new AudioPlayer(), new AudioPlayer()];
  await Promise.all(players.map((player) => player.unlock()));
  const result = await createRoom(languageSelect.value);
  if (!result.ok) {
    createButton.disabled = false;
    setStatus(setupStatusEl, result.message, true);
    return;
  }
  saveSession(store, result.data);
  showRoom(result.data, players);
}

createButton.addEventListener("click", () => void onCreate());
reloadWhenRestored();

/** The page follows the language picked in the form, before a room exists. */
languageSelect.addEventListener("change", () => {
  setLanguage(languageSelect.value);
  applyChrome();
});

try {
  setChromeTable(await getJson("/chrome").catch(() => null));
  languages = parseLanguages(await getJson("/languages"));
  fillLanguageSelect(languageSelect, languages);
  requireChoice([languageSelect], [createButton]);
  const saved = loadSession(store, ROLE);
  if (saved) {
    // After a reload there is no tap, so audio stays locked until the person taps Repeat.
    showRoom(saved, [new AudioPlayer(), new AudioPlayer()]);
  } else {
    const notice = takeNotice(store, ROLE);
    if (notice) setStatus(setupStatusEl, decodeBi(notice));
  }
} catch {
  setStatus(setupStatusEl, tb("language_list_failed", "Could not load the language list. Reload the page."), true);
}
