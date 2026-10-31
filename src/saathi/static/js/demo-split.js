// @ts-check
// Split-screen demo page: when the customer frame shows a room code, type it into the rider frame
// so the recording does not need a copy-paste step. Both frames are same-origin; nothing is sent.

const POLL_MS = 500;

/** @param {string} id @returns {HTMLIFrameElement} */
function frame(id) {
  const element = document.getElementById(id);
  if (!(element instanceof HTMLIFrameElement)) throw new Error(`Missing frame #${id}`);
  return element;
}

const customer = frame("customer-frame");
const rider = frame("rider-frame");

/** @param {HTMLIFrameElement} f @param {string} id */
const inner = (f, id) => f.contentDocument?.getElementById(id) ?? null;

setInterval(() => {
  const code = inner(customer, "code")?.textContent?.trim() ?? "";
  // The element belongs to the frame's own window, so `instanceof HTMLInputElement` is false here.
  const input = /** @type {HTMLInputElement | null} */ (inner(rider, "code-input"));
  if (code && input?.tagName === "INPUT" && input.value !== code) {
    input.value = code;
    input.dispatchEvent(new Event("input", { bubbles: true }));
  }
}, POLL_MS);
