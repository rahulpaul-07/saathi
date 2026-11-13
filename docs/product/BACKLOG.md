# Saathi: backlog

Date: 13 Nov 2026. Build-ready stories for the open gaps in `PRD.md` section 8.2, in roadmap order. File and test names come from the repo at commit `9929006`. Effort: S under half a day, M one to two days, L more.

---

## S-1 (G1) Pin the rider's reply controls

**As a** rider at a stop, **I want** Repeat and the quick replies always on screen, **so that** I can answer without scrolling.

Acceptance criteria
- Given a rider in a room at 360 x 740 with four tiles on the card, when the page loads, then Repeat and all three quick replies are inside the viewport.
- Given the card is taller than the screen, when the rider scrolls, then the reply bar stays fixed above the home-bar inset.
- Given keyboard navigation, when focus moves to a control under the bar, then it is never entirely hidden (the existing focus-not-obscured rule).
- All targets remain at least 48 px. No new interface text.

Notes: `app.css` already pins the customer's microphone with `position: sticky` and reserves `--mic-room`; reuse that pattern. The design proposal's item 8 describes this. Risk: a sticky layer can intercept Playwright clicks; check `tests/e2e`.
Effort: S to M. Depends on: nothing.

---

## S-2 (G2) Link-first rider join

**As a** rider who opened the customer's link, **I want** to pick my language and join, **so that** I never type a code.

Acceptance criteria
- Given `rider.html?code=XXXXXX`, when the page loads, then the code is shown as filled and the first interactive control is the language choice.
- Given no code in the URL, then the manual code field is shown as today.
- Given an invalid code from the link, then the error appears next to the code, in the rider's language.

Notes: `rider.js` already reads `?code=`. This is a layout and focus-order change. Any new label needs translation and review in ten languages; prefer reusing existing strings.
Effort: S. Depends on: nothing.

---

## S-3 Fix documentation inconsistencies

**As a** reader of the repo, **I want** the docs to match the code, **so that** I can trust the rest.

Acceptance criteria: each of the eight rows in `PRD.md` section 14 is either corrected or explained in the doc concerned.
Effort: S.

---

## S-4 Head-to-head against a general interpreter

**As the** product owner, **I want** the 50 demo clips run through Google Translate's live conversation mode, **so that** I know whether structured tiles add anything.

Acceptance criteria
- The same clips, the same expected facts, scored by whether each fact appears correctly in the output.
- Results published in `docs/EVAL.md` beside the 23 of 50 figure, with the method and its limits (manual playback, one run).
- The README states the comparison whichever way it goes.

Effort: S to M, manual. Depends on: nothing.

---

## S-5 (G3) Content-free instrumentation

**As the** product owner, **I want** counts of what happens in rooms, **so that** the PRD metrics can be measured without holding personal data.

Acceptance criteria
- Events from `PRD.md` section 9 are recorded when a flag is on, and nothing is recorded when it is off.
- A test builds a room with a known address, runs turns, confirms and asks, then asserts that no event contains the transcript, any fact value, the landmark, the room code, a token or an IP address.
- Counters are exposed on an endpoint that is not reachable publicly without a secret.
- `docs/THREAT_MODEL.md` gains a section on the new surface.

Notes: the pipeline already returns per-stage timings and the `verified` flag; `card.py` already distinguishes confirm, ask and changed.
Effort: M. Depends on: nothing.

---

## S-6 (G6) Consent notice

**As a** customer, **I want** to know what happens to my voice before I speak, **so that** I can choose.

Acceptance criteria
- Before the first recording in a room, a notice in the customer's language says that speech is sent to a speech service and that nothing is kept after the room ends.
- Declining closes nothing; the customer can still use quick replies.
- The choice is held for the room only and is not stored.
- Copy is reviewed by someone qualified before any real use.

Effort: S for the screen; the review is the real work. Depends on: G5 for each language.

---

## S-7 (G4) Real-audio evaluation

**As the** product owner, **I want** accuracy on real phone recordings, **so that** the synthetic numbers stop being the only evidence.

Acceptance criteria
- At least 20 consented recordings of spoken directions per launch language, made on phones, some outdoors, with invented addresses.
- Scored with `scripts/eval_noise.py --audio-dir` or its equivalent, reporting precision, recall and all-facts-right with intervals.
- Reported beside the synthetic numbers and labelled "consented human speech".
- Recordings stay in the gitignored audio folder.

Effort: L, mostly collection. Depends on: volunteers and a consent form.

---

## S-8 (G5) Native-speaker review

**As a** rider or customer, **I want** the text in my language to be correct, **so that** I am not misled.

Acceptance criteria: for each launch language, a native speaker reviews interface strings, quick replies, repeat prompts and the number and trigger lexicon; corrected entries move from "pending" to "reviewed"; the on-screen machine-translation notice disappears for that language.
Effort: M per language. Start with Kannada, the local customer language for a Bengaluru pilot and currently unreviewed.

---

## S-9 (G8) Hosted latency

Acceptance criteria: median and p95 turn time measured on the deployed machine, at least 20 turns, method and date in `docs/EVAL.md`, README limits section updated.
Effort: S. Spends live budget; plan the calls first.

---

## S-10 (G7) Number words above 20

Acceptance criteria: for Tamil, Telugu, Gujarati, Malayalam, Marathi and Punjabi, a held-out clip with a flat or floor number above 20 yields the right tile, or the limit stays documented.
Effort: M. Needs a probe run against the speech service.

---

## Not in the backlog on purpose

UX audit findings 3 to 7 (one "all clear" instead of per-tile confirm, language buttons, fewer bilingual lines, fewer status lines, distinct asked and uncertain badges). They are judgment calls. They wait for the interviews.
