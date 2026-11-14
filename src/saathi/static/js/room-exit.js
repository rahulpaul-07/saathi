// @ts-check
// How a room page is left, shared by the customer and the rider so both behave the same way: forget
// the room, say why, and go back to the start of the app.
import { encodeBi, tb } from "./i18n.js";
import { clearSession, setNotice, tabStorage } from "./session.js";

/**
 * @param {string} role
 * @param {"closed" | "gone"} end
 */
function endNotice(role, end) {
  if (end === "closed") return tb("room_ended", "The room has ended.");
  return role === "customer"
    ? tb("room_expired_customer", "The room has expired. Start a new one.")
    : tb("room_expired_rider", "The room has expired. Ask for a new code.");
}

/**
 * The room is over for good (ended by either person, or expired). The page goes to the home page,
 * replacing itself in the history so Back does not return to a dead room. Inside the split page the
 * frame has no home page to show, so it reloads to its own create or join screen instead; either way
 * the notice is shown once, on the screen the person lands on.
 * @param {string} role the role this page plays
 * @param {"closed" | "gone"} end
 */
export function leaveRoom(role, end) {
  const store = tabStorage();
  clearSession(store, role);
  setNotice(store, role, encodeBi(endNotice(role, end)));
  if (window.parent !== window) location.reload();
  else location.replace("/");
}

/**
 * A page the browser restores from its back-forward cache comes back exactly as it was left, with a
 * room screen that may be stale (the room may have ended meanwhile) and a dead event stream. Reloading
 * runs the normal start-up again: rejoin the saved room, or show the create or join screen.
 */
export function reloadWhenRestored() {
  window.addEventListener("pageshow", (event) => {
    if (event.persisted) location.reload();
  });
}
