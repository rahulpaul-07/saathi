// @ts-check
// Landing page: the seven kinds of fact, each with its own colour and icon, as the rider sees them,
// and a sample delivery card drawn with the same code the rider's screen uses.
import { chipsFromFacts } from "./chips.js";
import { decodeBi } from "./i18n.js";
import { KINDS, kindIcon } from "./kind-icons.js";
import { getJson } from "./room-client.js";
import { SAMPLE_FACTS } from "./sample-card.js";
import { takeAnyNotice, tabStorage } from "./session.js";
import { renderChips, setStatus } from "./ui.js";

// A room that just ended sends the person here with a one-time message in both languages. The page
// does not load the translation table, so the message arrives already encoded.
const noticeEl = document.getElementById("notice");
const notice = takeAnyNotice(tabStorage());
if (noticeEl && notice) setStatus(noticeEl, decodeBi(notice));

const strip = document.getElementById("kind-strip");
for (const kind of KINDS) {
  const item = document.createElement("li");
  item.className = `k-${kind}`;
  item.append(kindIcon(kind), kind.charAt(0).toUpperCase() + kind.slice(1));
  strip?.append(item);
}

const sample = document.getElementById("preview-chips");
if (sample) renderChips(sample, chipsFromFacts(SAMPLE_FACTS));

// The single-phone page needs the legacy /turn route, which a public host switches off. The link
// starts hidden and appears only when the server says the page works, so a failed or slow
// /features never shows a link that leads to an error.
try {
  const features = /** @type {any} */ (await getJson("/features"));
  const soloLink = document.getElementById("solo-link");
  if (soloLink && features?.solo_page === true) soloLink.hidden = false;
} catch {
  // No flag means no link; the page is a developer convenience.
}
