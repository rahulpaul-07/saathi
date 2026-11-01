// @ts-check
// One simple line icon per fact kind. The tile's label carries the accessible name, so the icon is
// decorative; its colour comes from the tile (`currentColor`).

/** @type {Record<string, string>} */
const PATHS = {
  gate: "M3 21V6M21 21V6M3 6h18M8 6v15M12 6v15M16 6v15",
  floor: "M5 21V4h14v17M3 21h18M9 8h2M13 8h2M9 12h2M13 12h2M10 21v-4h4v4",
  cross: "M9 3v6H3M15 3v6h6M9 21v-6H3M15 21v-6h6",
  main: "M8 21L10 3M16 21L14 3M12 6v2M12 11v2M12 16v2",
  block: "M4 4h7v7H4zM13 4h7v7h-7zM4 13h7v7H4zM13 13h7v7h-7z",
  flat: "M6 21V3h12v18M3 21h18M15 12v.01",
  landmark: "M12 21s-7-6.2-7-11a7 7 0 0 1 14 0c0 4.8-7 11-7 11zM12 8a2 2 0 1 0 0 4 2 2 0 0 0 0-4z",
};

/** Fact kinds that have an icon, in display order. */
export const KINDS = Object.keys(PATHS);

/**
 * @param {string} kind one of KINDS
 * @returns {SVGSVGElement}
 */
export function kindIcon(kind) {
  const svg = document.createElementNS("http://www.w3.org/2000/svg", "svg");
  svg.setAttribute("viewBox", "0 0 24 24");
  svg.setAttribute("class", "icon-kind");
  svg.setAttribute("aria-hidden", "true");
  const path = document.createElementNS("http://www.w3.org/2000/svg", "path");
  path.setAttribute("d", PATHS[kind] ?? "");
  path.setAttribute("fill", "none");
  path.setAttribute("stroke", "currentColor");
  path.setAttribute("stroke-width", "2");
  path.setAttribute("stroke-linecap", "round");
  path.setAttribute("stroke-linejoin", "round");
  svg.append(path);
  return svg;
}
