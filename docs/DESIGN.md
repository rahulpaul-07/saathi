# Design: Saathi

Status: direction changed on 2026-10-12 (approved). Slices 1-4 of the original generic interpreter
are built; slices 0-9 below are the delivery-directions product. The old generic design is kept in
git history.

## 1. Problem
A generic two-way interpreter is already covered by Google Translate conversation mode, Bhashini
and Samsung's interpreter. Saathi narrows to a problem they handle badly: a delivery customer
giving directions to a rider who speaks another language, often code-mixed
("2nd cross, 3rd main, gate number 2 ke paas, opposite Ganesha temple"), with the rider in
traffic on a bike.

## 2. Goals and non-goals
- Goals:
  1. The critical facts of an address (gate, floor, cross/main, block, flat, landmark) are
     extracted locally and shown as big chips on the rider screen, as well as spoken in the
     rider's language. Getting these facts right matters more than a fluent sentence.
  2. Numbers and landmarks survive translation (masking plus a check), and this is measured.
  3. It works in traffic noise, measured at 20, 10 and 5 dB SNR.
  4. Rider safety: audio first, readable at a glance, the rider never types, one tap for Repeat
     and for quick replies. Intended for use at a stop or pulled over; no claim of safety while
     riding.
  5. Any-to-any across the 10 languages Gnani supports for both STT and TTS.
- Non-goals: streaming interpretation, accounts, history, a native app, public deployment (the
  demo is a recorded video on a LAN), a hosted LLM, free-speech replies from the rider,
  Odia, Assamese and Urdu (Gnani supports none of them for STT or TTS; stated in the README).

## 3. Languages and support tiers
Verified against docs.gnani.ai: STT and TTS both support `bn en gu hi kn ml mr pa ta te`
(`xx-IN` codes). Odia is in neither. Code-mixing is documented only for English-Hindi; whether
Kannada-English mixing works is measured by the day-one probe (`scripts/probe_codemix.py`).

| Tier | Languages | What backs it |
|---|---|---|
| Verified core | kn, en, hi, bn | full evaluation, native-word extraction rules, reviewed quick replies |
| Reviewed | te | quick replies checked by a speaker, small human-speech smoke test (not in the main metric) |
| Beta | gu, ml, mr, pa, ta | labelled "beta" in the UI and README; one TTS-generated smoke test each proving the path works, not quality |

Language support is data, not code: one table (`languages.py`) holds, per language, the Gnani
code and voice, the IndicTrans2 code, the tier, the localized UI labels and the extraction
lexicon reference. No per-language branches in the pipeline.

## 4. Users and core flow
1. The customer creates a room and picks their language; the app shows a 6-character code and a
   link. The rider opens it on their phone and picks theirs.
2. The customer holds the talk button and speaks the directions.
3. The server runs STT, fact extraction, number masking, translation, restore, check, TTS.
4. The rider's phone receives the event: chips appear, the translated audio auto-plays.
5. The rider taps Repeat (replays locally, no call) or a quick reply ("I'm at the gate", "Which
   floor?", "Coming in 2 minutes"), which is pre-translated and spoken to the customer.

## 5. Architecture
```text
 Customer phone                  Laptop (uvicorn, one process)                 Rider phone
+----------------+  POST turn  +-----------------------------------------+  SSE +----------------+
| talk button    | ----------> | rooms (in memory, TTL, tokens)          | ---> | chips, auto-   |
| chips check    |  WAV        |  pipeline: Gnani STT -> facts.extract   |      | play, Repeat,  |
+----------------+             |   -> mask numbers -> IndicTrans2 (GPU)  |      | quick replies  |
                               |   -> restore + check -> Gnani TTS       | <--- | tap -> POST    |
                               +-----------------------------------------+      +----------------+
```

| Component | Responsibility |
|---|---|
| `languages.py` | the one language table (data-driven) |
| `translate.py` | routes each pair to indic-indic, en-indic or indic-en; one loaded model per route |
| `facts/` | universal layer + native-word layers; returns structured facts with spans |
| `masking.py` | placeholder masking before translation, restore and check after |
| `rooms.py` | in-memory rooms: code, two role slots, tokens, TTL, event queue, short-lived turn audio |
| `pipeline.py` | one turn, per-stage timings (existing, extended) |
| `gnani.py` | Prisma STT and Timbre TTS (existing) |
| `quickreplies` data | static table, English source, 10 translations, review status per language |
| `static/` UI | customer screen, rider screen, localized labels |

## 6. Data model
Nothing is stored. A room exists only in memory and expires (30 min idle, 2 h hard limit). Turn
audio is kept in memory for about 60 s so the other phone can fetch it. Transcripts, addresses and
translations are never logged and never written to disk. The quick-reply audio cache on disk holds
only fixed phrases (no personal data) and is gitignored. Addresses are personal data: tests, eval
and demos use only synthetic addresses; consented recordings of friends stay local and out of git.

## 7. Interfaces (planned, finalized in slice 2)
Create/join room, push events (SSE), upload a turn (multipart WAV, 16 kHz mono, max 2.5 MB), fetch
turn audio, send a quick reply. Every call after join carries the participant's random 128-bit
token; role and room are checked server-side. Join attempts are rate limited per IP (the code is
about 30 bits); a third participant is refused.

## 8. Key decisions
- Fact extraction is local and rule-based, on the source-language transcript, in two layers:
  1. Universal: digits and English direction words (gate, floor, cross, main, block, flat, tower,
     opposite, near, and the landmark after a trigger). In Indian cities these appear in English
     whatever language is spoken, so this layer works for all 10 languages.
  2. Native-word rules for the verified core only (kn, en, hi, bn): ordinals and number words,
     native triggers (ಎದುರು, ಹತ್ತಿರ, सामने, ...).
  Chips come from these structured facts, not from the translation, so they are right even when
  translation is garbled. Tuned for precision: a missing chip beats a wrong one. Limits: only
  patterns in the lexicon are found; landmark names are open vocabulary and the weakest fact type;
  everything depends on how STT writes numbers and English words (probe). Rejected: a fine-tuned
  tagger (30 utterances cannot train or validate it), a local LLM (weak Kannada, latency,
  non-determinism; comparison deferred indefinitely).
- Numbers and landmarks in translation: mask number spans with placeholders before translation,
  restore after, and verify each placeholder returns exactly once. If not, the turn is
  "unverified": the rider hears a templated fact summary instead of the full translation and the
  chips stay. Measured as three arms: toolkit default (IndicProcessor already wraps some
  entities), masked, masked plus fallback. Landmark names: translate the landmark span alone with
  IndicTrans2 (a); fall back to the landmark class label only (c). No IndicXlit for now.
- Translation: all 90 directed pairs route through three IndicTrans2 distilled models (indic-indic
  320M, en-indic 200M, indic-en 200M), loaded lazily by route. Greedy decoding with the runaway
  guard stays (docs/EVAL.md). VRAM with all three loaded is measured in slice 0 (estimate
  about 1.5 GB of 6 GB; not yet verified).
- Quick replies: written once in English, machine-translated offline into all 10, stored as a
  static table with a review status per language (bn, hi: author; kn, te: friends; the rest
  "unreviewed"). Never translated at runtime. Audio is synthesized on first use and cached.
- Noise: the STT API has no denoise option. Ship browser `noiseSuppression` and
  `autoGainControl`. Loudness-normalize TTS output for the rider (audibility in wind is checked
  by hand outdoors, not by SNR). RNNoise and a local LLM are out; revisit after Oct 19 only with
  spare time. Noise sources, in order: the author's own street recording, DEMAND "STRAFFIC" (CC BY
  4.0), generated noise as a fallback. SNR is computed against speech-active RMS, seeded.
- Transport: upload with POST, push to the other phone with Server-Sent Events. Rejected:
  WebSocket (more machinery for one-way pushes), polling.
- Network: LAN only, no public tunnel. Mic needs a secure context, so only the customer phone
  needs HTTPS or the Chrome insecure-origin flag; the rider phone has no microphone use.
- Kept from the first design: plain ES modules with JSDoc and strict `tsc`; the browser encodes
  16 kHz mono WAV itself; UI and API on one origin (no CORS); Gnani 429 handling with backoff
  and a kept recording. Details in `DECISIONS.md`.

## 9. Failure modes
| What fails | Effect | Handling |
|---|---|---|
| Gnani 429 | turn fails | "One moment...", backoff retry of the same WAV (existing client logic) |
| STT mis-hears a number | wrong chip | extractor precision bias; customer sees the same chips and can repeat |
| Placeholder lost in translation | number may be wrong in speech | turn marked unverified, speak the templated fact summary |
| Translation runaway (cap hit) | nonsense | guard raises, same fact-summary fallback, chips stay |
| Room code guessed | stranger joins | rate limit plus tokens plus two slots; room is short-lived |
| Rider phone blocks autoplay | no sound | joining requires a tap that unlocks audio; chips are the redundant channel |
| Language unsupported (Odia etc.) | cannot pick | not offered; README says why |
| Model load (~12 s each) | slow start | warm-up at startup for configured routes |

## 10. Security and privacy
- Untrusted input: audio and language codes validated before any paid call; transcripts, chips
  and translations rendered with `textContent` only.
- Secrets stay on the server (`GNANI_API_KEY`).
- Addresses are personal data: no transcript logging (existing logs carry timings and character
  counts only; the Gnani error body log at `gnani.py` is to be dropped), in-memory rooms that
  expire, synthetic addresses only in tests, eval and demos, consented recordings gitignored.
- Not hardened for the public internet (no auth beyond room tokens); LAN use only.

## 11. Evaluation
Replaces the Gnani parts of old slice 5. The translation evaluation already run (FLORES, greedy
vs beam, guard) stays as is (docs/EVAL.md).

- Set: 30 synthetic direction utterances with gold critical facts: 12 en and 4 hi, 4 bn (the
  author's voice, Audacity), 10 kn and code-mixed (a consenting friend's voice, "consented human
  speech"). Split 10 dev / 20 test; the test split is frozen before extractor tuning on it, and
  only test numbers are reported. The Kannada texts are written by Claude from a script; the
  friend may change words, and the gold is corrected to what was actually said.
- Separate labelled condition: the same Kannada texts through Gnani TTS ("clean synthetic").
- Main metric: critical-fact accuracy (exact gate, floor, cross/main, block/flat, landmark with
  accepted spellings), as precision, recall and share of utterances with all facts right; clean
  vs 20, 10 and 5 dB. Stage split: extractor on gold text, on STT transcript.
- Translation survival: arms A (toolkit default), B (masked), C (masked plus fallback), judged on
  whether each gold number and landmark appears in the target text (bn and hi reviewed by the author).
- Smoke tests, not quality claims: te human clips (5), and one TTS-generated utterance per
  beta language through STT, translation and quick-reply TTS.
- Statistics: about 20 test utterances, so confidence intervals (bootstrap over utterances) are
  wide; the write-up says what cannot be detected.
- Gnani budget (hard cap 290, enforced by the ledger, `--dry-run` first, runs only while the
  author is awake, at most 3 calls per 10 s):

| Step | Calls |
|---|---|
| Day-one probe (8 TTS + 14 STT), spent | 22 |
| Main STT: 30 utterances x 4 conditions (clean, 20, 10, 5 dB) | 120 |
| Kannada clean synthetic: 10 TTS + 10 STT | 20 |
| Latency: 20 turns x 2 | 40 |
| Quick-reply audio, core + te (6 phrases x 5 languages) | 30 |
| Smoke: te + gu, ml, mr, pa, ta (TTS utterance, STT, quick-reply TTS = 3 each) | 18 |
| Telugu human clips STT | 5 |
| **Expected total** | **255** |
| Retry reserve (429s are counted) | 35 |
| **Hard cap** | **290** |

The old cap of 155 and the FLORES-based `eval_turns.py` plan are replaced (script replaced in
slice 6). The 290 cap is NOT approved until the author reports the credit balance after the probe, so the cost per call is known.

## 12. Scope
- Must: rooms, rider screen with chips and Repeat, universal extraction plus kn/en rules, masking
  with measurement, noise evaluation, any-to-any translation, 10-language table.
- Should: hi/bn native rules, quick replies in all 10, localized labels, README with demo video.
- Cut order if time runs out: localized labels first; never the chips or the minimal quick replies (3 phrases in en, kn, hi, bn; they are the rider's only way to respond). The full 10-language table follows after Oct 19.
- Won't: see section 2 non-goals.

## 13. Slice plan
Build days Oct 12-16; away Oct 17-18 (hackathon); Oct 19 to Nov 6; submit Nov 7. The demo core
(room, rider screen, chips) is due Oct 16.

| # | Dates | Delivers | Status |
|---|---|---|---|
| 0 | Oct 12 | Day-one probe (dry run reviewed, then run) and its findings; 10-language data table; three-model routing; VRAM with all three loaded; en-to-hi/bn and a rider-side route working locally | in progress (probe built) |
| 1 | Oct 13-14 | Fact extractor: universal layer and kn/en native rules, synthetic gold set with dev/test split, text-only scores (no Gnani); Kannada and Telugu recording scripts (due Oct 13) | |
| 2 | Oct 14-15 | Room backend: create/join, tokens, TTL, SSE, in-memory turn audio, rate limits; pipeline returns translation, facts, verified; fakes in tests | |
| 3 | Oct 15-16 | Rider and customer screens: chips, auto-play, Repeat, language picker for 10 languages, two-context Playwright test; minimal quick replies (3 phrases x en, kn, hi, bn) are CORE; localized labels only if time (cut first) | |
| 4 | Oct 16 | Demo core integrated: real Gnani turn (few calls), TTS loudness normalization, LAN two-phone check; buffer for slips | |
| - | Oct 17-18 | away | |
| 5 | Oct 19-21 | Number and landmark masking, restore, fact-summary fallback; 3-arm text A/B; hi and bn native extraction rules | |
| 6 | Oct 22-24 | Quick-reply table in 10 languages (machine-translated, reviews requested), localized labels, noise mixer (seeded SNR), eval harness replacing `eval_turns.py`, dry run | |
| 7 | Oct 25-28 | Recordings in; Gnani main eval (clean, 20, 10, 5 dB), Kannada synthetic condition, te human smoke, 5 beta smokes, latency | |
| 8 | Oct 29-Nov 2 | Error analysis, extractor fixes re-scored on the frozen test split, outdoor audibility check, README beta/odia statements | |
| 9 | Nov 3-5 | EVAL.md, README, demo video on LAN, final checks | |
| - | Nov 6-7 | buffer, submit | |

What moved after Oct 19 compared with the first plan, because of the 10-language scope: hi and bn
native extraction rules (the universal layer covers hi and bn speakers' English words until
then), the full 10-language quick-reply table and its reviews, and localized chip labels beyond
a minimal set. The demo core on Oct 16 keeps the chips and Repeat; if slice 2 or 3 slips, localized
labels go first.

## 14. Open questions
- Probe answered (2026-10-12, see DECISIONS.md): Kannada output has no digits.
- Is 290 calls within the credit balance?
- Which entities does `IndicProcessor` already protect (numbers?). Checked in slice 5.
- Phone test: mic access needs a secure context (Android Chrome flag on the LAN; iOS needs real
  HTTPS and is out unless needed). The old Android check from slice 4 is still open.
