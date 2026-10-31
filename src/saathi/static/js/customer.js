// @ts-check
import { AudioPlayer } from "./audio-player.js";
import { applyChrome, setChromeTable, setLanguage, t } from "./i18n.js";
import { parseLanguages } from "./languages.js";
import { createRoom, getJson } from "./room-client.js";
import { enterRoom } from "./room-screen.js";
import { clearSession, loadSession, saveSession, setNotice, takeNotice } from "./session.js";
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

/**
 * @param {import("./room-client.js").RoomInfo} info
 * @param {AudioPlayer[]} players
 */
function showRoom(info, players) {
  room = info;
  setupEl.hidden = true;
  roomEl.hidden = false;
  codeEl.textContent = info.code;
  linkEl.textContent = `${location.origin}/rider.html?code=${info.code}`;
  screen = enterRoom(info, languages, players, onEnded);
}

/** @param {"closed" | "gone"} end */
function onEnded(end) {
  clearSession(sessionStorage);
  setNotice(
    sessionStorage,
    end === "closed"
      ? t("room_ended", "The room has ended.")
      : t("room_expired_customer", "The room has expired. Start a new one."),
  );
  location.reload();
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
  saveSession(sessionStorage, result.data);
  showRoom(result.data, players);
}

createButton.addEventListener("click", () => void onCreate());
closeButton.addEventListener("click", () => {
  screen?.stop();
  clearSession(sessionStorage);
  if (room) {
    void fetch(`/rooms/${room.code}`, {
      method: "DELETE",
      headers: { Authorization: `Bearer ${room.token}` },
    });
  }
  location.reload();
});

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
  const saved = loadSession(sessionStorage, "customer");
  if (saved) {
    // After a reload there is no tap, so audio stays locked until the person taps Repeat.
    showRoom(saved, [new AudioPlayer(), new AudioPlayer()]);
  } else {
    const notice = takeNotice(sessionStorage);
    if (notice) setStatus(setupStatusEl, notice);
  }
} catch {
  setStatus(setupStatusEl, t("language_list_failed", "Could not load the language list. Reload the page."), true);
}
