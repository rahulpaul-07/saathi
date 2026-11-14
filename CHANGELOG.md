# Changelog

User-facing changes, newest first. Evaluation numbers live in [`docs/EVAL.md`](docs/EVAL.md) and
the reasons for design choices in [`docs/DECISIONS.md`](docs/DECISIONS.md).

## 2026-11-15

From the live test with a native Kannada speaker on 14 November (details in the README and
[`docs/DECISIONS.md`](docs/DECISIONS.md#live-test-with-a-native-kannada-speaker-2026-11-14)). Checked
offline against stored transcripts and the local translator; not yet tried on the live site.

- Numbers now reach the other person unchanged, or the turn is marked unverified. Every number of ten
  or more and every number written in digits is held out of the translation and put back afterwards.
  Before, a Kannada "not 56, 57" reached a Bengali rider as 500 and 507. When a number does not come
  back the speaker is asked to repeat; the listener hears the tiles if the turn made any to speak, or
  the plain translation if it made none, and sees a line saying the translation could not be fully
  checked.
- Door, house and room numbers make a Flat tile in English, Kannada, Hindi and Bengali, in both word
  orders ("door number 57", "57 number door").
- A Kannada sentence with a door number, spoken to a Hindi listener, is now flagged unverified every
  time, because the Hindi translation drops the held-out number. The listener hears the Flat tile
  instead of a translated sentence, and the speaker is asked to repeat.
- Bengali numbers with "ঊন" or "উন" (one less than a tens word: ঊনষাট is 59) are read in both
  spellings, as one word or as two.
- "I" and words for the person spoken to ("brother") are no longer part of a landmark tile in Hindi,
  Bengali and Kannada, and Hindi "मंदिर के पास वाले गेट" stays one tile.
- Not fixed, and listed under Honest limits in the README: a landmark tile is cut at four words, so a
  name written letter by letter loses its start; "ಅಣ್ಣ" came out as "no" in one live turn and was not
  reproduced; and the rider page can say "Nothing sent yet." after a turn that made no tiles.

## 2026-11-14

- Ending a room takes both people to the home page with a one-time message ("The room has ended.") in
  their own language, and the room is forgotten, so a reload does not bring it back. End room now waits
  for the server before leaving; if the network is down the person stays in the room and is told.
- The rider has an End room button too. Either person ending closes the room for both.
- On the side-by-side demo page a reload keeps both people in their own rooms (the two screens used to
  share one saved room, so the second overwrote the first), and ending a room returns that screen to
  its start screen.
- A rider link for a different room now joins that room instead of reopening the one saved in the tab.
- A page restored with the browser's Back or Forward buttons reloads instead of showing a stale room.
- The browser warns before the tab is closed or left only while a recording is being made or is
  waiting to be sent.

## 2026-11-01

- Telugu is now beta. No speaker has checked it. Tiers are two: core (kn, en, hi, bn, evaluated on the
  synthetic gold set) and beta (gu, ml, mr, pa, ta, te, machine-verified only). "Reviewed by the author"
  applies only to bn and hi: all interface strings, quick replies, repeat prompts and the clip prompt.
- Phone layout: the delivery card sits directly under the header, the room status is one compact line,
  and the demo split page uses a larger base font and a four-column chip grid.
- Optional `SAATHI_MASKING_MODE=conditional` (default `current`, unchanged). The comparison is in
  `docs/EVAL.md`; the recommendation is to keep `current`.
- The English fact extractor now reads "Gate No. 2", "No. 2 cross" and "4 floors". Every published
  fact-recall number uses the fixed extractor; old values are kept in dated notes.
- Latency study rerun on AC power: p50 2.9 s, p95 4.0 s over 20 turns, no retries.
- README rewritten; MIT licence, third-party notices, architecture overview and design FAQ added.
  The run command now binds 127.0.0.1; LAN use is in `docs/LAN_CHECK.md` (the server has no login).

## 2026-10-31

- Bilingual interface: every string shows the viewer's language and an English line. Language names
  appear in the viewer's script ("कन्नड़ (Kannada)" on a Hindi page).
- Recordings that are empty, not WAV, shorter than 0.3 s or at an unsupported sample rate are refused
  before any Gnani call. A Gnani 4xx shows a localized "that recording can't be used" message.
- Interface loanwords ("room", "rider", "gate") are consistent across all ten languages.
- Phone-first customer and rider screens (the design proposal) implemented.
- Back link tap target raised to 44 px.

## 2026-10-30

- When a translation fails the placeholder check, the listener gets a spoken fact summary instead of a possibly wrong sentence. If the translator itself is unavailable, the turn returns a localized 502 error.
- Fact extraction for gu, ml, mr, pa, ta and te, built from real Gnani STT output
  (`docs/LEXICON_EVIDENCE.md`), with an evaluation across all ten languages.
- Translation-safety matrix across 90 language pairs, and the masking diagnosis.
- Load test for rooms; `/healthz`; failure-injection tests; optional Playwright job in CI.
- Rehearsal fixes: one retry on Gnani timeouts and 5xx, a "Gate 4 then gate 2" demo correction clip,
  old landmark shown in "changed, was".

## 2026-10-29

- Pinned delivery card with a "changed, was X" marker; the rider can confirm a chip or ask about it.
- "Please repeat" prompts, per-stage timings on the turn response, reconnect after a reload or a
  dropped connection (stored in `sessionStorage`, backoff with jitter), and a Content-Security-Policy on
  every response.
- Quick replies (3 phrases per role, all ten languages) with a review status per phrase.
- Roles are independent of languages: either person can use any of the ten.
- CI workflow and README badge.
