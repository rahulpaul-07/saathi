# Design proposal: phone-first customer and rider screens

**Status: proposal only. Nothing here is implemented.** It was written on 2026-10-30 from reading
`customer.html`, `rider.html` and `app.css` on the `features` branch. The look was frozen for the
rehearsal and recording, so this is for after that. Effort is for one developer: S under 2 hours,
M half a day, L a day or more. Test risk names what could break among the 61 JS unit tests, the 22
Playwright specs and the a11y spec (44 px targets, accessible names, AA contrast at 360 px).

## What is wrong today (observed in the markup and CSS)

- The delivery card, the thing the rider needs in one glance, is a section among many. On the rider
  screen it sits below the status lines, and below it come the live chips, the translation, Repeat,
  the customer reply, reply buttons, the microphone, status, retry actions, the demo picker and the
  "what the customer sees" list. On a 360 x 740 screen the rider scrolls to reach the reply buttons.
- Two lists of chips are on screen at once on the rider screen (`#card-chips` and `#chips`), under
  similar headings.
- Type sizes are ad hoc (0.85, 0.9, 0.95, 1, 1.1, 1.15, 1.2, 1.25, 1.6, 2.4, 2.75 rem) and spacing
  mixes 0.25, 0.4, 0.5, 0.6, 0.75, 0.9 and 1 rem.
- Button styles are `big-btn`, `talk-btn`, `talk-btn minor`, `reply-btn`, `secondary`, plain
  `button` in `.actions`, `.chip-actions button`. The primary action is not the same shape or place
  on the two screens.
- Colours are already tokens (`--bg --surface --text --muted --accent --accent-text --danger
  --border`, light and dark) but state colours (confirmed, changed, uncertain) are carried by border
  style and width only, and the danger colour is used for both errors and the recording state.
- Per-stage timings (`#timings`) are always visible to the speaker. They are useful in the demo and
  noise for a delivery person.
- Empty states are single grey lines ("Nothing sent yet.", "No address details yet.").

## Proposed changes

Each change is independent unless stated. Suggested order: 1, 2, 3 together, then 4 to 9.

### 1. Make the delivery card the hero (rider and customer)

- **What:** The card moves to the top of the room view, directly under one status line, and takes
  the full width with the largest type on the screen. Each fact is a row: label (small, upper case),
  value (2.4 rem, bold), and the original-language word underneath. The two chip lists on the rider
  screen are merged: the card is the only list of facts; "what this message said" becomes a
  one-line caption under the player.
- **Why:** The product's one job is to get gate, floor, cross/main and landmark across. Today they
  compete with 10 other blocks. A rider on a bike reads the first screen only.
- **Test risk:** High-medium. `rooms.spec.js` addresses `#card-chips`, `#chips`, `#sent-chips` by
  id, and the unit tests for `chips.js` render into those lists. Keeping the ids and moving the
  elements limits it to layout assertions; merging `#chips` into the card changes what several specs
  expect and needs those specs rewritten.
- **Effort:** M (move) to L (merge, with spec rewrites).

### 2. One type scale and one spacing scale

- **What:** Define tokens on `:root`: type `--text-sm 0.875rem`, `--text-md 1rem`, `--text-lg
  1.25rem`, `--text-xl 1.75rem`, `--text-hero 2.5rem`; spacing `--space-1 0.25rem`, `--space-2
  0.5rem`, `--space-3 1rem`, `--space-4 1.5rem`, `--space-5 2rem`. Replace the 11 font sizes and 8
  spacings with these. Keep a minimum of 16 px for body text (the page already sets this) and use
  `rem` so the browser's text size setting applies.
- **Why:** Consistency, and one place to change sizes. Indic scripts (Kannada, Malayalam, Telugu)
  have tall glyphs; the scale should be checked with them, not Latin text only.
- **Test risk:** Low, but visual: sizes change by fractions. The a11y 44 px check and the 360 px
  no-horizontal-scroll check will catch real regressions.
- **Effort:** M.

### 3. Colour tokens for state, not only border styles

- **What:** Add `--state-new`, `--state-changed`, `--state-confirmed`, `--state-uncertain` and
  `--recording` (separate from `--danger`), each with light and dark values. Every state keeps its
  non-colour cue (dashed border, thick border, check icon, text note), so colour is never the only
  signal. Contrast of every text-on-background pair is added to `a11y.spec.js` (already tests nine
  pairs at 4.5:1).
- **Why:** "Changed" and "confirmed" are the two states a rider must tell apart quickly; recording
  and error should not share a colour.
- **Test risk:** Low. Specs check text and roles, not colours; only the contrast spec is affected
  and it should be extended in the same change.
- **Effort:** S to M.

### 4. Button hierarchy: one primary per screen

- **What:** Three kinds only. Primary (filled accent, full width, 4.5 rem): customer = "Tap and
  speak", rider = the first quick reply row is not primary, the rider's primary is "Repeat".
  Secondary (outlined, 2.75 rem): replay, End room, Try again, Send demo clip. Tertiary (text link
  with a 44 px target, as the Back link now has): Discard recording. Quick replies stay large,
  outlined and full width, as the rider's most frequent action. All share one `.btn` base class
  with modifiers instead of five bespoke classes.
- **Why:** Today a screen has several full-weight buttons; the eye has nowhere to land.
- **Test risk:** Medium. Specs locate buttons by role and name, which do not change; unit tests on
  `ui.js` that set class names would need updates.
- **Effort:** M.

### 5. Icons with no new dependency

- **What:** Keep the inline SVG approach already used for mic, stop, repeat and check. Add four
  more paths in a single `icons.js` module (play, replay, close, warning), 24 x 24, `fill:
  currentColor`, `aria-hidden="true"`, with the visible text label always kept. No icon font and no
  library.
- **Why:** Fast recognition for riders who read little text, with no extra download or licence.
- **Test risk:** Low. Names come from the text, which stays.
- **Effort:** S.

### 6. Empty and error states that say what to do

- **What:** Replace one-line greys with a short state per block: "Waiting for the customer to join.
  Give them code ABC123" (code shown large), "No directions yet. They appear here as the customer
  speaks", "Connection lost. Trying again" with the existing reconnect indicator, and the new
  localized failure messages shown inside the speaker's own block, not as a floating status line.
  Messages come from the existing localized tables; machine-written strings stay marked "pending".
- **Why:** The frontend standard requires loading, empty and error states; the current ones are
  terse and some are English-only.
- **Test risk:** Medium. `rooms.spec.js` asserts exact texts such as "Nothing received yet." and
  "Waiting for directions."; those assertions change with the copy.
- **Effort:** M.

### 7. Timings behind a details toggle outside demo mode

- **What:** Wrap `#timings` in a `<details>` element with the summary "Timing". Closed by default
  when `demo_input` is off; open by default in demo mode (the page already knows the mode from
  `/quick-replies`'s `demo` flag or the banner state). Nothing is stored; the numbers are the same
  as today.
- **Why:** Useful for the demo and for debugging, noise for a delivery person. `<details>` is
  native, keyboard accessible and needs no script.
- **Test risk:** Medium-low. Specs that read the timing rows must open the details first when demo
  mode is off; the demo specs are unaffected.
- **Effort:** S.

### 8. Sticky bottom action area on the rider screen

- **What:** The rider's quick-reply buttons and microphone sit in a sticky container at the bottom
  (`position: sticky; bottom: 0`, safe-area padding), so they are always reachable while the card
  scrolls. The page content gets matching bottom padding so nothing is hidden behind it.
- **Why:** The rider's two actions after reading the card are to reply or to speak; on a small phone
  they are currently at the bottom of a long page.
- **Test risk:** Medium. A sticky layer can cover content in a viewport screenshot and can make
  Playwright clicks intercepted; the 44 px and no-overflow checks must pass at 360 x 740 and at a
  short 360 x 560 viewport with the on-screen keyboard.
- **Effort:** M.

### 9. Join screens: one decision per screen

- **What:** Customer: language, then "Create room" (already so). Rider: room code and language, with
  the code field using `inputmode="text"` and large type (already so), and a visible inline error
  under the field for a bad code instead of the status line. Add `autocomplete="off"` and keep
  upper-casing.
- **Why:** Small. These screens are already close to right; the gain is in the error state.
- **Test risk:** Low.
- **Effort:** S.

## Not proposed

- A new framework, CSS framework or component library: the page is 2.7k lines of plain modules and
  the constraint is that dependencies must earn their place.
- Animations: none carry meaning here.
- Localizing the UI labels beyond what exists: tracked separately (cut order in AGENTS.md puts
  localized labels first to cut).
- Any change to the quick-reply phrases or the card's content.

## Suggested rollout

1. Tokens (changes 2 and 3) in one commit, with the extended contrast spec.
2. Card as hero (1) with ids kept, then the button hierarchy (4) and icons (5).
3. Empty and error states (6) and timings toggle (7) together, since both rewrite spec text.
4. Sticky actions (8) last, because it needs real-phone testing (iOS Safari and Android Chrome)
   that this repo's tests cannot do.

Verify each step in a real browser at 360 px in light and dark, with a long Kannada or Malayalam
value in every chip, and on a phone before any demo.
