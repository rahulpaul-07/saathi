// @ts-check
// Landing page: the seven kinds of fact, each with its own colour and icon, as the rider sees them.
import { KINDS, kindIcon } from "./kind-icons.js";

const strip = document.getElementById("kind-strip");
for (const kind of KINDS) {
  const item = document.createElement("li");
  item.className = `k-${kind}`;
  item.append(kindIcon(kind), kind.charAt(0).toUpperCase() + kind.slice(1));
  strip?.append(item);
}
