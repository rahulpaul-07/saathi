// @ts-check
import assert from "node:assert/strict";
import { test } from "node:test";
import { scrollToClear } from "../../src/saathi/static/js/ui.js";

test("a button hidden behind the pinned control is scrolled up until it ends a gap above it", () => {
  // The button ends at 740 and the control starts at 692: scroll 56 so the button ends at 684, 8 above it.
  assert.equal(scrollToClear({ bottom: 740 }, { top: 692 }, 8), 56);
});

test("a button that already ends above the control with room to spare does not scroll", () => {
  assert.equal(scrollToClear({ bottom: 600 }, { top: 692 }, 8), 0);
});

test("a control that sits in the page under the button, not pinned over it, does not scroll", () => {
  assert.equal(scrollToClear({ bottom: 740 }, { top: 756 }, 8), 0);
});

test("a button that ends exactly a gap above the control is left alone", () => {
  assert.equal(scrollToClear({ bottom: 684 }, { top: 692 }, 8), 0);
});
