// @ts-check
// The in-room screen shared by the customer and the rider. Both roles can speak a turn, tap a quick
// reply, and receive the other person's turn (chips, translation, audio) or quick reply; only the
// page layout differs. The pages give the same element ids, so nothing here depends on the role
// or on any language.
import { AudioPlayer } from "./audio-player.js";
import { cardChips, chipsFromFacts } from "./chips.js";
import { clipsForLanguage, parseDemoClips } from "./demo-clips.js";
import { languageLabel } from "./languages.js";
import { parseQuickReplyTable, quickReplyOptions } from "./quick-replies.js";
import { followStream } from "./reconnect.js";
import { RecorderError, startRecording, toWav } from "./recorder.js";
import {
  fetchAudioUrl,
  fetchDemoClip,
  getJson,
  postTurn,
  readEvents,
  sendChipReply,
  sendQuickReply,
} from "./room-client.js";
import { byId, renderChips, renderTimings, setStatus } from "./ui.js";

/** @param {string} text */
const capitalize = (text) => text.charAt(0).toUpperCase() + text.slice(1);

/**
 * @param {import("./room-client.js").RoomInfo} room
 * @param {import("./languages.js").Language[]} languages
 * @param {AudioPlayer[]} players unlocked by the caller inside the tap that created or joined
 * @param {(end: "closed" | "gone") => void} onEnded the room is over for good (ended or expired)
 * @returns {{stop: () => void}} stop following the room (the caller closes it on the server)
 */
export function enterRoom(room, languages, players, onEnded) {
  const [turnPlayer, replyPlayer] = players;
  const peerRole = room.role === "customer" ? "rider" : "customer";

  const peerEl = byId("peer", HTMLElement);
  const reconnectingEl = byId("reconnecting", HTMLElement);
  const talkButton = byId("talk", HTMLButtonElement);
  const talkLabel = /** @type {HTMLElement} */ (talkButton.querySelector(".label"));
  const statusEl = byId("status", HTMLElement);
  const actionsEl = byId("actions", HTMLElement);
  const retryButton = byId("retry", HTMLButtonElement);
  const discardButton = byId("discard", HTMLButtonElement);
  const cardChipsEl = byId("card-chips", HTMLElement);
  const cardEmptyEl = byId("card-empty", HTMLElement);
  const sentChipsEl = byId("sent-chips", HTMLElement);
  const sentEmptyEl = byId("sent-empty", HTMLElement);
  const timingsEl = byId("timings", HTMLElement);
  const repeatEl = byId("repeat-prompt", HTMLElement);
  const repeatTextEl = byId("repeat-text", HTMLElement);
  const repeatNoteEl = byId("repeat-note", HTMLElement);
  const incomingStatusEl = byId("incoming-status", HTMLElement);
  const chipsEl = byId("chips", HTMLElement);
  const chipsNoteEl = byId("chips-note", HTMLElement);
  const translationEl = byId("translation", HTMLElement);
  const repeatButton = byId("repeat", HTMLButtonElement);
  const repliesEl = byId("replies", HTMLElement);
  const repliesNoteEl = byId("replies-note", HTMLElement);
  const replyEl = byId("reply", HTMLElement);
  const replyTextEl = byId("reply-text", HTMLElement);
  const replyNoteEl = byId("reply-note", HTMLElement);
  const replyReplayButton = byId("reply-replay", HTMLButtonElement);
  const demoBannerEl = byId("demo-banner", HTMLElement);
  const demoEl = byId("demo", HTMLElement);
  const demoSelect = byId("demo-clip", HTMLSelectElement);
  const demoSendButton = byId("demo-send", HTMLButtonElement);
  const demoBadgeEl = byId("demo-badge", HTMLElement);
  const sentDemoBadgeEl = byId("sent-demo-badge", HTMLElement);

  const idleLabel = talkLabel.textContent ?? "";
  /** @type {{recording: import("./recorder.js").Recording | null, busy: boolean,
   *   peerJoined: boolean, pending: Blob | null, pendingDemo: boolean}} */
  const state = {
    recording: null,
    busy: false,
    peerJoined: false,
    pending: null,
    pendingDemo: false,
  };
  /** @type {import("./demo-clips.js").DemoClip[]} */
  let demoClips = [];
  const stream = new AbortController();
  /** @type {import("./quick-replies.js").QuickReplyTable | null} */
  let quickReplies = null;
  let peerLanguage = room.peer_language ?? "";
  let renderedRepliesKey = "";
  // What is already on screen, so a snapshot after a reconnect does not redo it.
  let shownTurnId = "";
  let shownReplyKey = "";

  /** @param {string} code */
  function languageName(code) {
    const language = languages.find((item) => item.code === code);
    return language ? languageLabel(language) : code;
  }

  function render() {
    const recording = state.recording !== null;
    talkButton.setAttribute("aria-pressed", String(recording));
    talkButton.disabled = !state.peerJoined || state.busy || state.pending !== null;
    talkLabel.textContent = recording ? "Tap to stop and send" : idleLabel;
    actionsEl.hidden = state.pending === null || state.busy;
    sentEmptyEl.hidden = sentChipsEl.childElementCount > 0;
    demoSendButton.disabled =
      !state.peerJoined || state.busy || state.pending !== null || demoClips.length === 0;
    renderQuickReplies();
  }

  /** Offer prepared clips only when the server has demo input on (it is off by default). */
  async function setUpDemo() {
    try {
      const features = /** @type {any} */ (await getJson("/features"));
      if (features?.demo_input !== true) return;
      demoClips = clipsForLanguage(parseDemoClips(await getJson("/demo/clips")), room.language);
    } catch {
      return;
    }
    demoSelect.replaceChildren(
      ...demoClips.map((clip) => {
        const option = document.createElement("option");
        option.value = clip.id;
        option.textContent = clip.label;
        return option;
      }),
    );
    if (demoClips.length === 0) {
      const none = document.createElement("option");
      none.textContent = "No demo clips in this language";
      demoSelect.replaceChildren(none);
      demoSelect.disabled = true;
    }
    demoBannerEl.hidden = false;
    demoEl.hidden = false;
    render();
  }

  async function sendDemoClip() {
    if (state.busy || state.pending !== null || !demoSelect.value) return;
    state.busy = true;
    render();
    try {
      setStatus(statusEl, "Loading demo clip...");
      const clip = await fetchDemoClip(demoSelect.value);
      if (!clip) setStatus(statusEl, "Could not load the demo clip.", true);
      else await submit(clip, true);
    } finally {
      state.busy = false;
      render();
    }
  }

  function renderQuickReplies() {
    if (!quickReplies) return;
    const peer = state.peerJoined ? peerLanguage : "";
    const options = quickReplyOptions(quickReplies, room.role, room.language, peer);
    // Rebuilt only when something changed, so a tap is never lost to a re-render.
    const key = JSON.stringify(options);
    if (key === renderedRepliesKey) return;
    renderedRepliesKey = key;
    repliesEl.replaceChildren(
      ...options.items.map(({ id, label }) => {
        const button = document.createElement("button");
        button.type = "button";
        button.className = "reply-btn";
        button.textContent = label;
        button.disabled = !options.enabled;
        button.addEventListener("click", () => void onReply(id, label));
        return button;
      }),
    );
    repliesNoteEl.textContent = state.peerJoined ? (options.reason ?? "") : "";
  }

  /** @param {string} id @param {string} label */
  async function onReply(id, label) {
    const result = await sendQuickReply(room, id);
    setStatus(statusEl, result.ok ? `Sent: ${label}` : result.message, !result.ok);
  }

  /** @param {string} code */
  function showPeer(code) {
    peerLanguage = code;
    state.peerJoined = true;
    const name = capitalize(peerRole);
    peerEl.textContent = `${name} joined. ${name} language: ${languageName(code)}.`;
  }

  /**
   * @param {string} name
   * @param {any} data
   */
  function onEvent(name, data) {
    if (name === "card") {
      showCard(data.entries);
    } else if (name === "state") {
      showCard(data.card);
      if (data.peer_joined) showPeer(String(data.peer_language));
      else state.peerJoined = false;
      if (data.last_turn && turnKey(data.last_turn) !== shownTurnId) {
        void showIncomingTurn(data.last_turn, false);
      }
      if (data.last_reply && replyKey(data.last_reply) !== shownReplyKey) {
        void showIncomingReply(data.last_reply, false);
      }
    } else if (name === "peer_joined") {
      showPeer(String(data.language));
    } else if (name === "turn") {
      void showIncomingTurn(data, true);
    } else if (name === "quick_reply") {
      void showIncomingReply(data, true);
    }
    render();
  }

  /** @param {any} data */
  const turnKey = (data) => String(data.turn_id ?? "");
  /** @param {any} data */
  const replyKey = (data) => String(data.audio_path ?? data.text ?? "");

  /**
   * The pinned card, from a "card" event or the state snapshot after a reconnect.
   * @param {unknown} entries
   */
  function showCard(entries) {
    const listener = room.role === "rider";
    const chips = cardChips(entries, listener);
    renderChips(cardChipsEl, chips, listener ? { confirm: onChipConfirm, ask: onChipAsk } : undefined);
    cardEmptyEl.hidden = chips.length > 0;
  }

  /** @param {string} kind @param {"confirm" | "ask"} action */
  async function answerChip(kind, action) {
    const result = await sendChipReply(room, kind, action);
    if (!result.ok) setStatus(statusEl, result.message, true);
  }

  /** @param {string} kind */
  const onChipConfirm = (kind) => void answerChip(kind, "confirm");
  /** @param {string} kind */
  const onChipAsk = (kind) => void answerChip(kind, "ask");

  /**
   * @param {any} data
   * @param {boolean} live false when catching up after a reload: show it, but never play it
   */
  async function showIncomingTurn(data, live) {
    shownTurnId = turnKey(data);
    const chips = chipsFromFacts(data.facts, true);
    renderChips(chipsEl, chips);
    chipsNoteEl.textContent = [
      chips.some((chip) => chip.labelPending) && "Some labels are unreviewed machine spellings.",
      chips.some((chip) => chip.machineTranslated) &&
        "The landmark is machine-translated; the original is in brackets.",
    ]
      .filter(Boolean)
      .join(" ");
    translationEl.textContent = typeof data.translation === "string" ? data.translation : "";
    demoBadgeEl.hidden = data.demo_clip !== true;
    const heading = live ? "New message" : "Last message";
    setStatus(
      incomingStatusEl,
      data.verified
        ? `${heading} from the ${peerRole}.`
        : `${heading} from the ${peerRole}. The translation could not be fully checked; trust the facts above.`,
    );
    if (typeof data.audio_path !== "string") return;
    const url = await fetchAudioUrl(room, data.audio_path);
    if (!url) {
      // Audio is kept for about a minute, so a late catch-up legitimately has none.
      if (live) {
        setStatus(incomingStatusEl, "Could not load the audio. The facts above are still correct.", true);
      }
      return;
    }
    if (!live) {
      turnPlayer.load(url);
      repeatButton.disabled = false;
      return;
    }
    const played = await turnPlayer.play(url);
    repeatButton.disabled = false;
    if (!played) setStatus(incomingStatusEl, "Tap Repeat to hear it.", true);
  }

  /**
   * @param {any} data
   * @param {boolean} live false when catching up after a reload: show it, but never play it
   */
  async function showIncomingReply(data, live) {
    if (typeof data.text !== "string") return;
    shownReplyKey = replyKey(data);
    replyTextEl.textContent = data.text;
    replyNoteEl.textContent =
      data.review_status === "pending" ? "Unreviewed machine translation." : "";
    replyEl.hidden = false;
    if (typeof data.audio_path !== "string") return;
    const url = await fetchAudioUrl(room, data.audio_path);
    if (!url) return;
    if (live) await replyPlayer.play(url);
    else replyPlayer.load(url);
  }

  /** Keep one event stream open, backing off after drops, until the room is over. */
  async function followRoom() {
    const end = await followStream({
      connect: (onOpen) => readEvents(room, onEvent, stream.signal, onOpen),
      onDown: () => {
        reconnectingEl.hidden = false;
      },
      onUp: () => {
        reconnectingEl.hidden = true;
      },
      sleep: (ms) => new Promise((resolve) => setTimeout(resolve, ms)),
      random: Math.random,
      signal: stream.signal,
    });
    reconnectingEl.hidden = true;
    if (end !== "stopped") onEnded(end);
  }

  async function beginRecording() {
    state.busy = true;
    render();
    try {
      state.recording = await startRecording(() => void finishRecording());
      setStatus(statusEl, "Recording. Tap again when you are done (60 s maximum).");
    } catch (error) {
      if (!(error instanceof RecorderError)) throw error;
      setStatus(statusEl, error.message, true);
    } finally {
      state.busy = false;
      render();
    }
  }

  async function finishRecording() {
    const recording = state.recording;
    if (!recording || state.busy) return;
    state.recording = null;
    state.busy = true;
    render();
    setStatus(statusEl, "Preparing audio...");
    try {
      await submit(await toWav(await recording.stop()));
    } catch (error) {
      if (!(error instanceof RecorderError)) throw error;
      setStatus(statusEl, error.message, true);
    } finally {
      state.busy = false;
      render();
    }
  }

  /**
   * Ask the speaker, in their own language, to say it again. It never blocks sending.
   * @param {{text?: unknown, review_status?: unknown} | null | undefined} repeat
   */
  function showRepeatPrompt(repeat) {
    const text = typeof repeat?.text === "string" ? repeat.text : "";
    repeatEl.hidden = text === "";
    repeatTextEl.textContent = text;
    repeatTextEl.lang = room.language;
    repeatNoteEl.textContent =
      text !== "" && repeat?.review_status === "pending" ? "Unreviewed machine translation." : "";
  }

  /**
   * Send a recording. It stays in `state.pending` for Try again when resending could help.
   * @param {Blob} wav
   * @param {boolean} [demoClip] a prepared clip instead of live speech
   */
  async function submit(wav, demoClip = false) {
    state.pending = wav;
    state.pendingDemo = demoClip;
    setStatus(statusEl, "Sending...");
    showRepeatPrompt(null);
    const result = await postTurn(room, wav, demoClip);
    if (!result.ok) {
      if (!result.keepRecording) state.pending = null;
      setStatus(statusEl, result.message, true);
      return;
    }
    state.pending = null;
    renderChips(sentChipsEl, chipsFromFacts(result.data.facts));
    sentDemoBadgeEl.hidden = !demoClip;
    renderTimings(timingsEl, result.data.timings);
    timingsEl.hidden = false;
    showRepeatPrompt(result.data.repeat);
    const sent = demoClip ? "Sent demo clip" : "Sent";
    setStatus(
      statusEl,
      result.data.verified
        ? `${sent}. The ${peerRole} has these details.`
        : `${sent}, but check the translation.`,
    );
  }

  talkButton.addEventListener("click", () => {
    if (state.busy) return;
    if (state.recording) void finishRecording();
    else void beginRecording();
  });
  retryButton.addEventListener("click", () => {
    const pending = state.pending;
    if (!pending || state.busy) return;
    state.busy = true;
    render();
    void submit(pending, state.pendingDemo).finally(() => {
      state.busy = false;
      render();
    });
  });
  discardButton.addEventListener("click", () => {
    state.pending = null;
    setStatus(statusEl, "Recording discarded. Ready.");
    render();
  });
  repeatButton.addEventListener("click", () => void turnPlayer.replay());
  replyReplayButton.addEventListener("click", () => void replyPlayer.replay());
  demoSendButton.addEventListener("click", () => void sendDemoClip());

  if (room.peer_language) showPeer(room.peer_language);
  render();
  void followRoom();
  void loadQuickReplies();
  void setUpDemo();

  async function loadQuickReplies() {
    try {
      quickReplies = parseQuickReplyTable(await getJson("/quick-replies"));
      render();
    } catch {
      repliesNoteEl.textContent = "Quick replies could not be loaded.";
    }
  }

  return { stop: () => stream.abort() };
}
