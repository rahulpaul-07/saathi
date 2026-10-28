// @ts-check
import { AudioPlayer } from "./audio-player.js";
import { parseLanguages } from "./languages.js";
import { createRoom, getJson } from "./room-client.js";
import { enterRoom } from "./room-screen.js";
import { byId, fillLanguageSelect, requireChoice, setStatus } from "./ui.js";

const languageSelect = byId("language", HTMLSelectElement);
const createButton = byId("create", HTMLButtonElement);
const setupEl = byId("setup", HTMLElement);
const setupStatusEl = byId("setup-status", HTMLElement);
const roomEl = byId("room", HTMLElement);
const codeEl = byId("code", HTMLElement);
const linkEl = byId("link", HTMLElement);
const closeButton = byId("close", HTMLButtonElement);

/** @type {import("./languages.js").Language[]} */
let languages = [];
/** @type {import("./room-client.js").RoomInfo | null} */
let room = null;
/** @type {{stop: () => void} | null} */
let screen = null;

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
  room = result.data;
  setupEl.hidden = true;
  roomEl.hidden = false;
  codeEl.textContent = result.data.code;
  linkEl.textContent = `${location.origin}/rider.html?code=${result.data.code}`;
  screen = enterRoom(result.data, languages, players);
}

createButton.addEventListener("click", () => void onCreate());
closeButton.addEventListener("click", () => {
  screen?.stop();
  if (room) {
    void fetch(`/rooms/${room.code}`, {
      method: "DELETE",
      headers: { Authorization: `Bearer ${room.token}` },
    });
  }
  location.reload();
});

try {
  languages = parseLanguages(await getJson("/languages"));
  fillLanguageSelect(languageSelect, languages);
  requireChoice([languageSelect], [createButton]);
} catch {
  setStatus(setupStatusEl, "Could not load the language list. Reload the page.", true);
}
