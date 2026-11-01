// @ts-check
// The in-room screen shared by the customer and the rider. Both roles can speak a turn, tap a quick
// reply, and receive the other person's turn (chips, translation, audio) or quick reply; only the
// page layout differs. The pages give the same element ids, so nothing here depends on the role
// or on any language.
import { AudioPlayer } from "./audio-player.js";
import { cardChips, chipsFromFacts } from "./chips.js";
import { clipsForLanguage, oneLine, parseDemoClips } from "./demo-clips.js";
import { nameForViewer } from "./languages.js";
import { applyChrome, Bi, bi, renderText, setLanguage, tb } from "./i18n.js";
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
import { byId, renderChips, renderTimings, setStatus, timingsSummary } from "./ui.js";

/**
 * @param {import("./room-client.js").RoomInfo} room
 * @param {import("./languages.js").Language[]} languages
 * @param {AudioPlayer[]} players unlocked by the caller inside the tap that created or joined
 * @param {(end: "closed" | "gone") => void} onEnded the room is over for good (ended or expired)
 * @returns {{stop: () => void}} stop following the room (the caller closes it on the server)
 */
export function enterRoom(room, languages, players, onEnded) {
  const [turnPlayer, replyPlayer] = players;
  // The page speaks the viewer's language from here on; this runs before the idle label is read.
  setLanguage(room.language);
  applyChrome();
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
  // The rider's page echoes what the customer received; the customer's page has no such block
  // because its delivery card already shows every fact.
  const sentEl = document.getElementById("sent");
  const sentChipsEl = document.getElementById("sent-chips");
  const sentEmptyEl = document.getElementById("sent-empty");
  const incomingEl = document.getElementById("incoming");
  const codeBoxEl = document.getElementById("code-box");
  const timingsBoxEl = byId("timings-box", HTMLDetailsElement);
  const timingsSummaryEl = byId("timings-summary", HTMLElement);
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

  // applyChrome has stored the page's English text on the element, so the idle label keeps both lines.
  const idleLabel = tb(String(talkLabel.dataset.i18n), talkLabel.dataset.en ?? "");
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

  /** The status line for an incoming turn: live or caught up, from the other role. */
  function incomingHeading(/** @type {boolean} */ live) {
    if (peerRole === "rider") {
      return live
        ? tb("new_message_rider", "New message from the rider.")
        : tb("last_message_rider", "Last message from the rider.");
    }
    return live
      ? tb("new_message_customer", "New message from the customer.")
      : tb("last_message_customer", "Last message from the customer.");
  }

  /**
   * What the sender is told after a send.
   * @param {boolean} demoClip
   * @param {boolean} verified
   */
  function sentMessage(demoClip, verified) {
    if (!verified) {
      return demoClip
        ? tb("sent_demo_check_translation", "Sent demo clip, but check the translation.")
        : tb("sent_check_translation", "Sent, but check the translation.");
    }
    if (peerRole === "rider") {
      return demoClip
        ? tb("sent_demo_rider_has_details", "Sent demo clip. The rider has these details.")
        : tb("sent_rider_has_details", "Sent. The rider has these details.");
    }
    return demoClip
      ? tb("sent_demo_customer_has_details", "Sent demo clip. The customer has these details.")
      : tb("sent_customer_has_details", "Sent. The customer has these details.");
  }

  /** @param {string} code */
  function languageName(code) {
    return nameForViewer(
      languages.find((item) => item.code === code),
      room.language,
      code,
    );
  }

  function render() {
    const recording = state.recording !== null;
    talkButton.setAttribute("aria-pressed", String(recording));
    talkButton.disabled = !state.peerJoined || state.busy || state.pending !== null;
    renderText(talkLabel, recording ? tb("tap_to_stop", "Tap to stop and send") : idleLabel);
    actionsEl.hidden = state.pending === null || state.busy;
    demoSendButton.disabled =
      !state.peerJoined ||
      state.busy ||
      state.pending !== null ||
      demoClips.length === 0 ||
      demoSelect.value === "";
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
    demoBannerEl.hidden = false; // demo mode is on for the room even if this person has no clips
    if (demoClips.length === 0) return; // an empty picker would only be noise
    // Start on a placeholder so a clip is never sent unless the presenter picked it.
    const placeholder = document.createElement("option");
    const choose = tb("choose_a_clip", "Choose a clip");
    placeholder.value = "";
    placeholder.textContent = oneLine(choose.local, choose.english);
    placeholder.dataset.i18n = "choose_a_clip";
    placeholder.disabled = true;
    placeholder.selected = true;
    demoSelect.replaceChildren(
      placeholder,
      ...demoClips.map((clip) => {
        const option = document.createElement("option");
        option.value = clip.id;
        option.textContent = oneLine(clip.labelLocal, clip.label);
        return option;
      }),
    );
    demoEl.hidden = false;
    // With a clip to send, the clip is the main action and the microphone steps back.
    document.body.classList.add("demo-on");
    talkButton.classList.add("minor");
    render();
  }

  async function sendDemoClip() {
    if (state.busy || state.pending !== null || !demoSelect.value) return;
    state.busy = true;
    render();
    try {
      setStatus(statusEl, tb("loading_demo_clip", "Loading demo clip..."));
      const clip = await fetchDemoClip(demoSelect.value);
      if (!clip) setStatus(statusEl, tb("demo_clip_failed", "Could not load the demo clip."), true);
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
        renderText(button, label);
        button.disabled = !options.enabled;
        button.addEventListener("click", () => void onReply(id, label));
        return button;
      }),
    );
    renderText(repliesNoteEl, state.peerJoined && options.reason ? options.reason : "");
  }

  /** @param {string} id @param {Bi} label */
  async function onReply(id, label) {
    const result = await sendQuickReply(room, id);
    setStatus(statusEl, result.ok ? bi`${tb("sent", "Sent")}: ${label}` : result.message, !result.ok);
  }

  /** @param {string} code */
  function showPeer(code) {
    peerLanguage = code;
    state.peerJoined = true;
    const joined =
      peerRole === "rider"
        ? tb("rider_joined", "The rider joined.")
        : tb("customer_joined", "The customer joined.");
    renderText(peerEl, bi`${joined} ${tb("their_language", "Their language")}: ${languageName(code)}.`);
    // The code has done its job; keep it as a small line in case the rider has to rejoin.
    codeBoxEl?.classList.add("compact");
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
    incomingStatusEl.hidden = false;
    if (incomingEl) incomingEl.hidden = false;
    // The customer's facts live on the delivery card; repeating them per turn showed every value twice.
    const chips = peerRole === "customer" ? [] : chipsFromFacts(data.facts, true);
    renderChips(chipsEl, chips);
    const notes = [
      chips.some((chip) => chip.labelPending) &&
        tb("labels_unreviewed", "Some labels are unreviewed machine spellings."),
      chips.some((chip) => chip.machineTranslated) &&
        tb("landmark_machine", "The landmark is machine-translated; the original is in brackets."),
    ].filter((note) => note !== false);
    renderText(
      chipsNoteEl,
      new Bi(
        notes.map((note) => note.local).join(" "),
        notes.map((note) => note.english).join(" "),
      ),
    );
    translationEl.textContent = typeof data.translation === "string" ? data.translation : "";
    demoBadgeEl.hidden = data.demo_clip !== true;
    const heading = incomingHeading(live);
    setStatus(
      incomingStatusEl,
      data.verified
        ? heading
        : bi`${heading} ${tb("translation_unchecked", "The translation could not be fully checked; trust the facts above.")}`,
    );
    if (typeof data.audio_path !== "string") return;
    const url = await fetchAudioUrl(room, data.audio_path);
    if (!url) {
      // Audio is kept for about a minute, so a late catch-up legitimately has none.
      if (live) {
        setStatus(incomingStatusEl, tb("audio_failed", "Could not load the audio. The facts above are still correct."), true);
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
    if (!played) setStatus(incomingStatusEl, tb("tap_repeat", "Tap Repeat to hear it."), true);
  }

  /**
   * @param {any} data
   * @param {boolean} live false when catching up after a reload: show it, but never play it
   */
  async function showIncomingReply(data, live) {
    if (typeof data.text !== "string") return;
    shownReplyKey = replyKey(data);
    // Before any turn, the status line still holds its "nothing yet" placeholder, which would
    // contradict the reply shown below it.
    if (shownTurnId === "") incomingStatusEl.hidden = true;
    replyTextEl.textContent = data.text;
    renderText(
      replyNoteEl,
      data.review_status === "pending"
        ? tb("unreviewed_translation", "Unreviewed machine translation.")
        : "",
    );
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
      setStatus(statusEl, tb("recording", "Recording. Tap again when you are done (60 s maximum)."));
    } catch (error) {
      if (!(error instanceof RecorderError)) throw error;
      setStatus(statusEl, error.text, true);
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
    setStatus(statusEl, tb("preparing_audio", "Preparing audio..."));
    try {
      await submit(await toWav(await recording.stop()));
    } catch (error) {
      if (!(error instanceof RecorderError)) throw error;
      setStatus(statusEl, error.text, true);
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
    renderText(
      repeatNoteEl,
      text !== "" && repeat?.review_status === "pending"
        ? tb("unreviewed_translation", "Unreviewed machine translation.")
        : "",
    );
  }

  /**
   * Send a recording. It stays in `state.pending` for Try again when resending could help.
   * @param {Blob} wav
   * @param {boolean} [demoClip] a prepared clip instead of live speech
   */
  async function submit(wav, demoClip = false) {
    state.pending = wav;
    state.pendingDemo = demoClip;
    setStatus(statusEl, tb("sending", "Sending..."));
    showRepeatPrompt(null);
    const result = await postTurn(room, wav, demoClip);
    if (!result.ok) {
      if (!result.keepRecording) state.pending = null;
      setStatus(statusEl, result.message, true);
      return;
    }
    state.pending = null;
    if (sentEl && sentChipsEl && sentEmptyEl) {
      renderChips(sentChipsEl, chipsFromFacts(result.data.facts));
      sentEmptyEl.hidden = sentChipsEl.childElementCount > 0;
      sentEl.hidden = false;
    }
    sentDemoBadgeEl.hidden = !demoClip;
    renderTimings(timingsEl, result.data.timings);
    // In demo mode the one-line summary is the readout; elsewhere the detail sits behind a toggle.
    const demoMode = document.body.classList.contains("demo-on");
    renderText(
      timingsSummaryEl,
      demoMode ? timingsSummary(result.data.timings) : tb("time_taken", "Time taken by your last message"),
    );
    timingsBoxEl.open = demoMode;
    timingsBoxEl.hidden = false;
    showRepeatPrompt(result.data.repeat);
    setStatus(statusEl, sentMessage(demoClip, result.data.verified === true));
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
    setStatus(statusEl, tb("recording_discarded", "Recording discarded. Ready."));
    render();
  });
  repeatButton.addEventListener("click", () => void turnPlayer.replay());
  replyReplayButton.addEventListener("click", () => void replyPlayer.replay());
  demoSendButton.addEventListener("click", () => void sendDemoClip());
  demoSelect.addEventListener("change", render);

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
      renderText(repliesNoteEl, tb("quick_replies_failed", "Quick replies could not be loaded."));
    }
  }

  return { stop: () => stream.abort() };
}
