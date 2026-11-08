// @ts-check
// Landing page: the seven kinds of fact, each with its own colour and icon, as the rider sees them,
// and a sample delivery card drawn with the same code the rider's screen uses.
import { chipsFromFacts } from "./chips.js";
import { KINDS, kindIcon } from "./kind-icons.js";
import { SAMPLE_FACTS } from "./sample-card.js";
import { renderChips } from "./ui.js";

const strip = document.getElementById("kind-strip");
for (const kind of KINDS) {
  const item = document.createElement("li");
  item.className = `k-${kind}`;
  item.append(kindIcon(kind), kind.charAt(0).toUpperCase() + kind.slice(1));
  strip?.append(item);
}

const sample = document.getElementById("preview-chips");
if (sample) renderChips(sample, chipsFromFacts(SAMPLE_FACTS));
