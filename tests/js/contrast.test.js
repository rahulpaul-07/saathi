// @ts-check
// WCAG 2.x contrast for every colour pair the pages use, read straight from the tokens in app.css,
// in both themes. Text pairs need 4.5:1; icons, borders and other UI graphics need 3:1.
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { test } from "node:test";

const CSS = readFileSync(new URL("../../src/saathi/static/app.css", import.meta.url), "utf8");

/** Custom properties declared in the first block whose selector starts with `selector`. */
function tokens(/** @type {string} */ selector) {
  const start = CSS.indexOf(`${selector} {`);
  assert.notEqual(start, -1, `${selector} block not found`);
  const body = CSS.slice(CSS.indexOf("{", start) + 1, CSS.indexOf("\n}", start));
  /** @type {Record<string, string>} */
  const out = {};
  for (const [, name, value] of body.matchAll(/(--[a-z0-9-]+):\s*([^;]+);/g)) out[name] = value.trim();
  return out;
}

const LIGHT = tokens(":root");
const THEMES = /** @type {const} */ ({
  light: LIGHT,
  dark: { ...LIGHT, ...tokens(':root[data-theme="dark"]') },
});

/** Resolve `var(--x)` references and return a #rrggbb string. */
function resolve(/** @type {Record<string, string>} */ theme, /** @type {string} */ name) {
  let value = theme[name];
  for (let depth = 0; value?.startsWith("var("); depth += 1) {
    assert.ok(depth < 5, `${name} loops`);
    value = theme[value.slice(4, -1)];
  }
  assert.match(value ?? "", /^#[0-9a-f]{6}$/i, `${name} is not a hex colour: ${value}`);
  return value;
}

function luminance(/** @type {string} */ hex) {
  const [r, g, b] = [1, 3, 5]
    .map((i) => Number.parseInt(hex.slice(i, i + 2), 16) / 255)
    .map((c) => (c <= 0.03928 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4));
  return 0.2126 * r + 0.7152 * g + 0.0722 * b;
}

function ratio(/** @type {string} */ a, /** @type {string} */ b) {
  const [hi, lo] = [luminance(a), luminance(b)].sort((x, y) => y - x);
  return (hi + 0.05) / (lo + 0.05);
}

const KINDS = ["gate", "floor", "cross", "main", "block", "flat", "landmark"];
const SURFACES = ["--bg", "--surface"];
const TILES = [...KINDS.map((k) => `--${k}-bg`), "--ok-bg", "--ask-bg"];

/** @type {[string, string][]} */
const TEXT = [
  ...SURFACES.flatMap((s) => ["--text", "--muted", "--accent", "--danger", "--rider", "--customer"].map((t) => /** @type {[string, string]} */ ([t, s]))),
  ...TILES.flatMap((t) => ["--text", "--muted"].map((f) => /** @type {[string, string]} */ ([f, t]))),
  ["--accent-text", "--accent"],
  ["--accent-text-muted", "--accent"],
  ["--danger-on", "--danger"],
  ["--rider-on", "--rider"],
  ["--customer-on", "--customer"],
  ["--warn-text", "--warn-bg"],
  ["--ask-text", "--ask-bg"],
  ["--muted", "--warn-bg"],
];

/** @type {[string, string][]} */
const GRAPHICS = [
  ...SURFACES.flatMap((s) => ["--control-border", "--accent"].map((t) => /** @type {[string, string]} */ ([t, s]))),
  ["--warn-border", "--warn-bg"],
  ["--ok", "--surface"],
  ["--ask", "--surface"],
  ["--danger", "--surface"],
  ...KINDS.map((k) => /** @type {[string, string]} */ ([`--${k}`, `--${k}-bg`])),
  ...TILES.flatMap((t) => ["--ok", "--ask"].map((f) => /** @type {[string, string]} */ ([f, t]))),
  ["--ok", "--ok-bg"],
  ["--ask", "--ask-bg"],
];

for (const [themeName, theme] of Object.entries(THEMES)) {
  for (const [pairs, minimum, what] of /** @type {const} */ ([
    [TEXT, 4.5, "text"],
    [GRAPHICS, 3, "graphic"],
  ])) {
    test(`${themeName}: every ${what} pair meets ${minimum}:1`, () => {
      for (const [fg, bg] of pairs) {
        const value = ratio(resolve(theme, fg), resolve(theme, bg));
        assert.ok(value >= minimum, `${fg} on ${bg} is ${value.toFixed(2)} (${themeName})`);
      }
    });
  }
}

test("the fact kinds share one recipe: their tile contrast stays within a narrow band", () => {
  for (const [themeName, theme] of Object.entries(THEMES)) {
    const values = KINDS.map((k) => ratio(resolve(theme, `--${k}`), resolve(theme, `--${k}-bg`)));
    assert.ok(Math.max(...values) - Math.min(...values) < 1, `${themeName}: ${values.map((v) => v.toFixed(2))}`);
  }
});

test("a token that is not a colour is caught rather than skipped", () => {
  assert.throws(() => resolve({ "--x": "1rem" }, "--x"));
});
