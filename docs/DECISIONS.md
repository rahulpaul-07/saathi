# Decisions

## Gnani endpoints
The docs index lists `/api/STT/speech-to-text` and `/api/TTS/tts-inference`, but the reference
pages and real calls use `POST /stt/v3` and `POST /api/v1/tts/inference`. Verified with a live
Bengali round trip.

## Audio from the browser
Prisma documents WAV, MP3, OGG, FLAC, AAC and M4A, not WebM. Only WAV is verified. The browser
will decode its recording and upload 16 kHz mono WAV, which avoids an ffmpeg dependency and gives
the server one fixed input format to validate.

## Translation stack pins
- `transformers==4.46.3`. Version 5.x breaks IndicTransToolkit 1.1.1 on import. 4.57.6 loads but
  the model's remote decoder code crashes with the KV cache on (`past_key_values[0][0]` is None),
  which forced `use_cache=False`. 4.46.3 works with the cache and produced identical Kannada
  output on three test sentences.
- `torch==2.9.1` from the official cu128 index; the 2.7 GB wheel is reused locally only through
  the manual workflow in the README. uv ignores `--find-links` when the lockfile pins a URL.
- Decoding defaults to greedy (`TRANSLATOR_NUM_BEAMS=1`). Beam search is a setting so slice 5 can
  compare greedy against beams on FLORES quality before either is trusted.

## Translator latency (measured on AC power)
Earlier benchmarks varied 30x between runs (greedy, 21 characters: 0.5 s and 15 s) while the
laptop was on battery. Re-measured on AC with the Windows "Best performance" mode: bn -> kn,
fp16 on the RTX 3050, greedy, KV cache on, 3 warm-ups excluded, 20 runs per sentence,
through `IndicTrans2Translator.translate`.

| Input    | Median | p95    |
|----------|--------|--------|
| 21 chars | 108 ms | 129 ms |
| 51 chars | 176 ms | 211 ms |
| 79 chars | 280 ms | 402 ms |

nvidia-smi during the run: GPU util up to 40%, SM clock up to 1732 MHz, 60 C max, so the model is
on the GPU and not thermally throttled. The 30x swings were therefore a power-state effect.
Record the power state with every later latency run. These are model-only numbers for one
language pair and exclude load time (about 12 s).

## Translation input limits
Text is capped at 2000 characters and split into sentences, translated as one batch. Unsupported
or identical language pairs are rejected at the boundary.

## Turn API (`POST /turn`)
- Multipart `audio` (16 kHz mono WAV) plus `src` and `tgt`; returns the transcript, the
  translation, base64 WAV audio and per-stage timings (`stt_ms`, `translate_ms`, `tts_ms`,
  `total_ms`). `total_ms` covers the three stages only, not the upload or the browser's own work,
  so the UI should also measure tap-to-playback itself.
- JSON with base64 audio rather than a binary body: one request carries text, audio and timings,
  and the 24 kHz clip is under 200 KB for a short sentence.
- Everything free is checked before anything paid: language pair, WAV header, size (2.5 MB) and
  duration (60 s, Prisma's limit). A bad request never spends credits.
- Status codes: 400 bad input, 413 too large, 422 no speech detected or an unreliable (looping) translation, told apart by `detail.code`, 429 our per-IP limit
  (default 10 turns a minute, `TURN_RATE_LIMIT_PER_MINUTE`), 503 Gnani is rate limiting us
  (retry), 502 any other Gnani failure. Upstream bodies are logged, never returned.
- The limiter is in memory and keyed on the socket IP, which is right for one process on one
  host. Behind a reverse proxy it would see only the proxy's address and needs a trusted
  forwarded-for header or a shared store.

## Gnani TTS returns a streaming WAV
Timbre responds with both WAV size fields set to 0xFFFFFFFF (verified on a live response).
`wave` reads that as 2^31 frames, and some browsers, iOS Safari in particular, may refuse it, so
`GnaniClient.synthesize` rewrites the sizes from the bytes received. Found because my own upload
validator rejected Gnani-made test audio as "longer than 60 seconds". Not yet tested in a real
phone browser; do that in slice 4.

## Gnani rate limits
Gnani returned 429 `RATE_LIMITED` on both STT and TTS when I made roughly four calls in under
ten seconds (two per turn, plus test-client calls). The limit itself is undocumented to me. The
eval harness in slice 5 must pace its calls and retry 429 with backoff.

## Startup warm-up
Loading takes about 12 s, and the first `generate()` adds about 2.5 s of one-time CUDA setup
(first live turn: 3.2 s translate vs 0.4 s afterwards). The app now loads and translates one
throwaway sentence at startup.

## Live turn timings (one-off, not a benchmark)
After warm-up, on AC power, real Gnani calls, short single-sentence turns:
STT 320-560 ms, translate 380-460 ms, TTS 680-860 ms, total 1.5-1.8 s (3 turns). Three turns
are an existence proof, not a distribution; slice 5 measures p50/p95 properly.

## Browser UI (slice 4)
- Plain ES modules with `// @ts-check` and JSDoc, strict `tsc --noEmit`, served by FastAPI
  `StaticFiles` mounted at `/` after the API routes (same origin, no CORS). `package.json` is
  dev-only (`typescript`, `@playwright/test`, `@types/node`, all pinned; nothing ships). TypeScript 7
  still provides the `tsc` command.
- Mounting at `/` means `GET /turn` now returns 404 instead of 405. `POST /turn` is unchanged.
- `.js` is registered as `text/javascript` at import: on Windows Python reads MIME types from the
  registry, where it can be `text/plain`, and browsers refuse ES modules served that way.
- WAV: `OfflineAudioContext(1, 1, 16000).decodeAudioData` decodes and resamples to 16 kHz, a second
  mono offline render mixes channels down, then PCM16 is written and clamped at 60 s (about 1.9 MB,
  under the 2.5 MB server cap).
- Retry policy lives in `retry.js` (pure) and `turn-client.js`: 503 and network errors or a 45 s
  timeout retry up to 3 times at about 1, 2, 4 s with +-25% jitter. Our own 429 is never auto
  retried. The recording `Blob` is held in `state.pending` until success or Discard; 400, 413 and
  422 drop it because resending cannot help.
- Double STT spend: a 503 means Gnani rate limited either STT or TTS. If it was TTS, the retry
  runs STT again and pays twice. A network timeout after the server finished does the same.
  Accepted; avoiding it needs a server-side cache keyed by recording hash or a split API.
- Tap-to-playback is measured in the browser from the stop tap (or Try again tap) to the audio
  element's `playing` event, so it includes WAV encoding, upload, the server stages and decoding.
- Transcripts and translations are set with `textContent` only. The Playwright test feeds
  `<b>heard</b>` and asserts it appears as literal text.
- Playwright check: `npm run e2e` starts the real app with a stub translator, uses Chromium's fake
  microphone and intercepts `/turn` (503, 503, 200; and 4x503 then Try again; and 429). It compares a
  SHA-256 of the WAV part of each request, because the multipart boundary differs per request.
  Chromium itself logs each 503 as a console error; those stubbed ones are filtered, anything else
  fails the test.
- Not verified yet: a real phone (Android Chrome with the insecure-origin flag), and playback of the
  Gnani-made WAV on iOS Safari.

## Runaway translations (found in the phone check)
- Root cause: Gnani misheard the first two words ("সেই শর্ট" for "হে ঈশ্বর"). Greedy decoding on that
  garbled input fell into a "ಆ ಚಿಕ್ಕ ಚಿಕ್ಕ ..." loop and ran to `max_length=256` (about 5.8 s, 1525
  characters), which then went to paid TTS (7.8 s). The ground-truth text translates correctly in
  0.7 s, so this is an STT error amplified by the decoding loop. Reproduced with the real model.
- Cap: `generate(max_new_tokens=min(2 * longest_input_tokens + 10, 256))`. Measured normal
  output/input token ratio is 0.9-1.2; the runaway is about 8x (256 tokens from 33). The input
  length is `input_ids.shape[1]` after tokenization (padded batch, so the longest sentence). 256 is
  the model's position limit and input truncation is unchanged. A separate length-ratio check is
  not needed: the cap makes a ratio above about 2x unreachable.
- Signal 1, EOS (in `IndicTrans2Translator.translate`): a row with no EOS id was cut off by the
  cap, so the translator raises `DegenerateTranslationError`. Checked per row, since shorter rows
  of a batch are padded. This model's decoder start token is also EOS (id 2), so column 0 is
  skipped; my first version checked the whole row and never fired (caught by the real-model test,
  and the fake-model unit tests now begin rows with the start token). Long legitimate sentences
  (64 and 69 input tokens, bn->kn and hi->ta) finish at about 1.0x with EOS, far below the cap.
- Signal 2, `guard.has_repeated_phrase` (any Translator's output, run by the pipeline): a phrase of
  1 to 3 words repeated 4 or more times consecutively, words split on whitespace with surrounding
  punctuation stripped. Three repeats ("না না না") are natural emphasis and pass; this also covers
  alternating loops and engines other than IndicTrans2.
- Either signal makes `run_turn` raise `UnreliableTranslationError(transcript)` before TTS, so no
  paid call is made. The event is logged with lengths and reason only, not text or audio.
- API: both 422s now carry a code so the UI can tell them apart:
  `{"code": "no_speech", "message": ...}` and
  `{"code": "unreliable_translation", "message": ..., "transcript": <STT text>}`. The transcript is
  untrusted; the UI renders it with `textContent`. The UI does not retry and drops the recording
  for both, and an unknown 422 code falls back to the no-speech message.
- Deferred: a repetition penalty or `no_repeat_ngram_size` would prevent the loop instead of
  detecting it, but it can hurt legitimate output (repeated words are normal in these languages).
  It waits for the slice 5 eval to measure the chrF cost. Beam search (4) happened not to loop on
  this one input; that is luck on one sample, not a guard.

## Evaluation harness (slice 5)
- chrF++ is sacrebleu `CHRF(word_order=2)` (pinned 2.6.0). Scores are corpus-level on the FLORES
  devtest sample; the greedy-vs-beam gain is also reported per sentence with a paired bootstrap
  confidence interval (fixed seed), because 50 sentences per pair is a noisy sample.
- Sample: 50 evenly spaced devtest sentences (`sample_indices`), the same for every pair, 12
  directed pairs, greedy vs 5 beams. Greedy is also run on all 1012 sentences for the 4 app
  directions, to give the token-ratio and guard checks more than 50 samples. The FLORES archive is
  pinned by SHA-256 (trust on first use) and kept in gitignored `eval/data/` (CC BY-SA 4.0).
- `IndicTrans2Translator.translate_with_stats` returns the text plus token counts and whether the
  cap was hit; `translate()` is a thin wrapper that still raises on a cap hit. Added so the eval
  can record a runaway and keep going instead of catching an exception.
- Power: every timed run reads the Windows power state, refuses to start off AC (`--allow-battery`
  runs but tags results as battery), aborts if the state changes mid-run, and never accepts
  "unknown". The translation script waits up to 8 h for AC and redoes a shard it started on a
  changed state. Battery and AC numbers are never pooled.
- Gnani budget: `plan` 132 expected calls (40 TTS, 41 turns x 2 = 82, 10 real STT) against a hard
  cap of 155 kept in a ledger file (`eval/state/`, gitignored) across runs. Every HTTP call is
  counted, retries included. Pacing is a sliding window of at most 3 calls per 10 s (Gnani allows
  about 4); a turn reserves both its calls up front, outside the timed region, so waiting never
  inflates latency. A first plan of one turn per 6 s was wrong (4 calls inside 10 s) and was
  replaced by the window. A 429 is retried 3 times with 10/20/30 s backoff; a retried turn is
  excluded from the latency sample and the retry count is reported.
- The first of the 41 turns is a warm-up and is discarded, so the latency sample is 40 turns. With
  n=40 the p95 is close to the maximum, so n is printed beside it.
- TTS-to-STT audio is Gnani's voice into Gnani's ears: clean, an optimistic best case. It is
  labeled "clean synthetic audio" everywhere. The real-speech set (10 clips, the author's own
  voice) is every 4th of those 40 sentences, so each recording has a synthetic twin. TTS output
  (24 kHz) is resampled to 16 kHz with `audioop.ratecv` (Python 3.12 only; it is removed in 3.13)
  to match what the browser uploads.
- STT text is normalized (NFC, punctuation to space, whitespace collapsed, case folded) before CER,
  chrF++ and word matching. Start-of-clip analysis aligns normalized words with difflib and
  compares the miss rate of the first 2 words with the rest.
- Not added: a `sounddevice` recording script (a new dependency that was not approved). Recording
  instructions use Audacity instead (docs/EVAL.md).

## Direction change: delivery directions (2026-10-12)
- Why: generic interpreters (Google conversation mode, Bhashini, Samsung) exist; the gap is a
  customer giving code-mixed directions to a rider in traffic. Product, scope, evaluation and
  slice plan are in DESIGN.md; this records the choices made at approval.
- Approved: landmark names via IndicTrans2 on the span alone, class-label-only fallback, no
  IndicXlit; rider has quick replies only (no free speech); no public tunnel, demo is a recorded
  LAN video; RNNoise and the local-LLM comparison are out.
- Any-to-any over the 10 languages Gnani supports for both STT and TTS. Odia is in neither (docs
  checked 2026-10-11). Tiers: kn en hi bn verified, te reviewed, gu ml mr pa ta beta.
- Fact extraction: universal layer (digits, English direction words) for all languages, native
  rules for the verified core only.
- Quick replies: English source, offline machine translation, static table, per-language review
  status. Audio generated on first use and cached on disk (fixed phrases, no personal data,
  gitignored).
- Gnani call cap raised from 155 to 290 for the new evaluation (breakdown in DESIGN.md 11). The
  old FLORES-based Gnani plan in `eval_turns.py` is replaced in slice 6; until then it still runs.
- Day-one probe (`scripts/probe_codemix.py`, 22 calls, probe cap 26): records how Gnani writes
  numbers and English words in Kannada and English transcripts. It uses synthetic TTS audio, so it
  shows the form of transcripts, not recognition accuracy on real code-mixed speech.

## Probe findings: how Gnani writes numbers (2026-10-12, 22 calls, synthetic audio)
- kn-IN STT output is all Kannada script: NO digits and NO Latin. Numbers are Kannada words
  (ಎರಡು, ಮೂರನೇ, ಮುನ್ನೂರ ನಾಲ್ಕು = 304); a split ordinal appears ("ಎರಡು ನೇ"); 14 came out as
  digit-by-digit words ("ಒಂದು ನಾಲ್ಕು"); English words are transliterated (ಗೇಟ್ ನಂಬರ್, ಕ್ರಾಸ್,
  ಮೇನ್, ಆಪೋಸಿಟ್, ಥರ್ಡ್ ಫ್ಲೋರ್, ಫೈವ್ ಬಿ) with spelling variants (ಫ್ಲ್ಯಾಟ್ / ಫ್ಲಾಟ್).
- en-IN on Kannada speech is worse: romanized Kannada, a wrong number ("gate number edu"), one
  empty transcript, one cut-off. Decision: use the speaker's own language code only; no second pass.
- en-IN English output mixes forms: "2nd cross 3rd main" (digits) but "gate number two" (word),
  and "fourth floor" came out as "1/4 floor" (a text-normalization error that turns a floor
  into a fraction).
- Consequence for the extractor: the digit-based universal layer is not enough for Indic output.
  Needed: (1) a number parser per core language (cardinals, ordinals incl. split "ನೇ", hundreds,
  digit-by-digit sequences) normalizing to Arabic digits; (2) trigger lexicons that include the
  native-script transliterations of English words, with spelling variants, normalized for
  ZWJ/virama differences; (3) a rule that reads "1/N floor" as floor N, flagged low confidence;
  (4) ambiguous values (14 vs "1 4") flagged so the chip shows what was heard. Beta languages
  without native rules get only what survives as digits or Latin text, which is a stated limit.
- Caveat: the audio is Gnani TTS, which itself reads "2nd" as "ಎರಡು ನೇ"; real speech will differ.
  The consented Kannada clips are the real test.

## Slice 1: fact extraction (text only)
- Structure: `saathi.facts` = tokenizer with original offsets (spans index the input), a `key()`
  normalizer (NFC, casefold, ZWJ/ZWNJ removed, nukta dropped, chandrabindu to anusvara, all Unicode
  digits to ASCII, trailing virama stripped) applied to transcripts and lexicon entries alike, a
  `Lexicon` dataclass per language, and number grammar in `numbers.py`. Language support is data
  (`lexicons.py`); the English layer is merged under kn, hi and bn. Other table languages get only
  the English/digit layer (stated limit).
- Rules come from the probe: no digits in kn output so Kannada number words incl. split ordinal
  "ನೇ" and tens sandhi; transliterated trigger words with spelling variants; "1/N floor" is read as
  floor N with confidence "low".
- Ambiguity: a run of two or more single digits ("ಒಂದು ನಾಲ್ಕು", "1 4") is never merged. `value` is
  the words as heard, `reading` the candidate ("14"), `ambiguous=True`, so the chip shows what was heard.
- Precision first: triggers combine with a value after or before (optionally through "number").
  Candidates are resolved by priority (explicit/trigger-first, then bare value-first, then bare
  value-after) and claim token ranges, so one value never feeds two facts. Range caps: gate, cross,
  main, block 99; floor 60; flat 9999 (larger is STT noise, not extracted).
- Landmarks: prefix trigger ("opposite X") or postposition after the name ("X के सामने"), capped at 4
  tokens, stopping at punctuation, claimed values, stopwords and other landmark words. Postposition
  landmarks are open-ended, so they are "low" confidence. "house" maps to the flat kind.
- Scoring (`evaluation/factscore.py`, `scripts/score_facts.py`): exact match on kind and normalized
  value. Ambiguous predictions are not asserted: excluded from precision, counted as a recall
  miss, reported separately with whether the candidate reading matched.
- Gold set `eval/gold/directions.json`: 30 synthetic utterances (12 en, 10 kn, 4 hi, 4 bn). Split
  rule: dev iff the number in the id is divisible by 3 (10 dev, 20 test). The test split is frozen by
  a SHA-256 pinned in `tests/test_fact_gold.py`; `--errors` is refused on test. Rules were tuned on
  dev only; test was scored once.
- Results (text only): dev precision 1.00, recall 0.94; test precision 1.00, recall 0.96 (3 misses:
  unsupported "ground floor", two ambiguous digit-by-digit flats). Caveat: the author wrote both the
  gold texts (in the probe's observed forms, not real STT output) and the lexicons, so these are
  optimistic and partly circular. Real accuracy needs the consented clips.
- Limits: no "ground floor"; Hindi and Bengali numbers cover roughly up to 50 plus tens and hundreds;
  native lexicons are not validated against real speaker STT.

## Slice 2: room backend
- Code: `rooms.py` (state, no HTTP) and `room_routes.py` (router built by `create_app`, managers and
  fakes injected). The old `POST /turn` is untouched; the UI of slice 3 moves to room turns.
- Room code: 6 symbols from a 31-symbol alphabet without I L O 0 1 (about 29.7 bits). Path format is
  validated; guessing is limited by a per-IP limiter on create and join (`ROOM_RATE_LIMIT_PER_MINUTE`,
  default 10) that counts every attempt, hit or miss, plus 50 rooms at most (`MAX_ROOMS`).
- Tokens: `secrets.token_urlsafe(16)` (128 bits), one per slot, sent as `Authorization: Bearer`. Not in
  the URL, because uvicorn logs URLs. Consequence: browser `EventSource` cannot set headers, so the
  slice 3 UI reads the SSE stream with `fetch` and a stream reader.
- Authorization fails closed with one answer: unknown room, expired room, wrong token and another
  room's token all return the same 404 `room not found`, so codes cannot be probed. Tokens are compared
  with `hmac.compare_digest`. Role rules after that: only the customer sends turns (403 otherwise),
  only the rider sends quick replies. Audio is served only inside its own room and only by id.
- Slots: the creator is the customer, the joiner is the rider; the same language on both sides is
  refused (nothing to interpret). The language pair comes from the room, never from the client.
- TTL: 30 min idle (touched by join, turn, quick reply; SSE keepalives do not count), 2 h hard.
  Expiry is lazy (checked on access and on create) with no background task; the room cap bounds memory.
- Events: one queue per role (32 slots, oldest dropped when a reader stalls). A new SSE connection
  replaces the old one for that role, which suits a phone that reconnects. Each stream starts with a
  `state` snapshot (so a join that happened before connecting is not missed). Events for a role with
  no open stream are dropped, not replayed; turns are not retried. `closed` ends the stream.
- Turn audio: kept in memory 60 s, last 5 per room, fetched at `/rooms/{code}/turns/{id}/audio`. The
  rider's `turn` event carries translation, facts, `verified` and the audio path. The customer's HTTP
  response carries facts and `verified` only: no transcript or translation is returned to anyone
  but the rider, and the unreliable-translation error no longer echoes the transcript.
- `verified`: `run_turn` now returns `facts` (from the source transcript, so chips survive a bad
  translation) and `verified=True` when the runaway guards passed. Real verification (number
  placeholders returning once) arrives with masking in slice 5; until then the flag means "guards passed".
- Quick replies: the endpoint accepts a `phrase_id` from three placeholder ids (`coming_2_min`,
  `reached_gate`, `cannot_find`). Text, translations and audio belong to the quick-reply table.
- Audio upload checks: content type must be a WAV type (415), WAV header and 60 s limit (400), 2.5 MB
  (413) via the existing validator. The size check happens after Starlette has spooled the multipart
  body, so an oversized upload still costs the server the transfer (fine on a LAN, not for the internet).
- Logs carry language codes, fact counts and timings only.

## Slice 3: rider and customer screens
- Pages: `index.html` (role choice), `customer.html`, `rider.html`, each a small ES module (`customer.js`,
  `rider.js`) over shared `room-client.js`, `ui.js`, `audio-player.js`. The old single-phone page moved
  unchanged to `solo.html` (still `main.js`, still `/turn`) so its retry e2e keeps guarding that logic.
- SSE: `fetch` streaming with `Authorization: Bearer`, parsed by the pure `sse.js` (chunk-split, CRLF,
  comments, bad JSON dropped). The stream reconnects after 2 s unless the room is closed or gone (404);
  events missed while disconnected are not replayed (slice 2 behaviour).
- Tokens live in JS memory only (no storage). A page reload leaves the room; the customer ends rooms
  with End room (DELETE). The rider link carries only the code (`rider.html?code=`), never a token.
- Audio: one persistent `<audio>` element. The rider's Join tap (and the customer's Create tap) plays
  50 ms of silence, which lets later turns auto-play. Audio needs the token, so it is fetched with
  fetch into an object URL; only paths under `/rooms/<own code>/turns/` are fetched. Repeat replays
  that object URL: no network call (the e2e counts audio requests).
- Room turns are sent once, with no automatic retry (unlike `/turn`), so a 503 cannot silently pay for
  STT twice. The WAV stays for "Try again" when the error class allows it (`classify` in `retry.js`).
- Chips (`chips.js`) come from `facts`, ordered gate, floor, cross, main, block, flat, landmark; an
  ambiguous fact shows the words heard plus "could be 14"; low confidence gets a dashed border and
  "check this". English labels only; localized labels were not done (cut first, per plan).
- Language picker: `GET /languages` (new, public, read-only) from `languages.py`; labels add
  "(reviewed)" for te and "(beta)" for the beta tier, none for the verified core.
- Quick replies (contract change, strictly needed): the rider's POST must reach the customer as words
  and audio, so the table now exists. `quickreplies.py` holds 3 phrases for en (source), hi, bn, kn
  (machine output supplied by the author, `review_status: "pending"`, shown to the customer as
  "Unreviewed machine translation"). `GET /quick-replies` serves the table. Ids changed:
  `cannot_find` became `which_floor` (the third phrase is "Which floor?"); `reached_gate` and
  `coming_2_min` are unchanged. The quick-reply event now carries `phrase_id`, `text`, `review_status`
  and `audio_path` (null if TTS failed; the text is still delivered). Text is chosen by the customer's
  language on the server; if the customer's language has no phrases the POST returns 400 and the rider
  UI disables the buttons with a reason. The rider sees labels in their own language when the table has
  it, else English. Audio is synthesized on first use per (language, phrase), cached in memory for the
  process (fixed phrases hold no personal data; no disk cache yet), and served through the existing
  turn-audio route. First use of each phrase therefore costs one Gnani TTS call.
- E2E: `tests/e2e/serve.py` now injects a fake Gnani and a fake translator (the translator returns
  markup to prove text-only rendering). `rooms.spec.js` uses two browser contexts, Chromium's fake
  microphone, and fails on any console error or warning.
- Not verified: real phones, iOS audio unlock, real Gnani audio in the new screens.

## Slice 4: TTS loudness and integration (offline part)
- Where: `GnaniClient.synthesize` is the one place TTS audio is produced (turns and quick replies),
  so `loudness.normalize_or_passthrough` runs there, after the streaming-WAV repair, in a worker thread.
- Algorithm (`loudness.py`): RMS level to -18 dBFS, then a smoothed look-around peak limiter with a
  -1 dBFS ceiling (required gain min-filtered then box-averaged over 5 ms, so the ceiling holds without
  clicks). Gain is capped at +30 dB. Clips below -70 dBFS RMS are treated as silence and returned as is.
  RMS, not LUFS: no K-weighting needed for short single-voice clips; simpler and testable.
- Formats: 16-bit PCM, any rate, mono or multichannel (levelled together). Anything else raises
  `AudioError` in `normalize_wav`.
- Failure policy: passthrough. Quiet audio beats no audio, and Gnani was already asked for 16-bit
  mono, so a rejection is logged as a warning (reason only) and the original WAV is served.
- Dependency: numpy is imported but not declared; it is a hard dependency of transformers and
  sacrebleu (both pinned). Declare it in pyproject if those ever change.
- Integration: `tests/test_integration.py` runs customer WAV -> real `GnaniClient` (respx) -> facts ->
  fake translator -> rider event -> audio fetch, and checks the served level. No gaps found; the
  e2e suite uses a fake Gnani, so it does not cover normalization.
- Not verified: how the normalized audio sounds on real Gnani output and phone speakers; the LAN check
  (`docs/LAN_CHECK.md`) is prepared, not run.

## Priority 2 / noise eval (offline part)
- Harness: `scripts/eval_noise.py` (`run [--dry-run]`, `report`) over `src/saathi/evaluation/noisemix.py`
  and `noiseeval.py`. It supersedes `scripts/eval_turns.py` (FLORES-based, old 155-call plan).
  Author approved 2026-10-29: `eval_turns.py`, `PLANNED_CALLS`, `planned_total` and the old clip
  counts are deleted; `evaluation/turns.py` (`measure_turn`) stays for the latency study, which
  needs a new script when it is planned.
- numpy is declared (`numpy==2.5.3`, the version already in uv.lock) because `loudness.py` and
  `noisemix.py` import it directly.
- Plan: 30 gold utterances x 4 conditions = 120 STT calls, ledger label `noise-stt`. Dry run prints
  every call, flags missing recordings, and fails (exit 2) if spent + planned passes the cap. A real
  run refuses unless every recording exists, passes `check_recording` and every mix succeeds, so no
  call is paid for before the inputs are known good. Results are saved after each call and a
  rerun skips finished clips (a crash or a 429 stop does not waste paid calls).
- Recordings: `eval/audio/gold/<gold id>.wav`, 16 kHz mono 16-bit (gitignored). Wrong rate is
  refused, never resampled, so the mixer cannot silently change what Gnani hears.
- SNR = speech-active RMS / whole-clip noise RMS. Activity detector: 20 ms frames, active when frame
  RMS is within 20 dB of the 95th-percentile frame RMS and above -60 dBFS. Settings are logged per
  mix and stored in the results meta. Noise RMS is over the whole clip because noise does not pause.
- Noise: a seeded window of a local WAV, or seeded 1/f pink noise (default; no downloads). Synthetic
  pink noise is a controlled stressor, not street audio: the write-up must not call it traffic.
  Per-clip seed = sha256(seed, utterance id, condition), so output is byte-identical for a seed.
- Peak handling: if speech plus noise passes 0.99 full scale the whole mix is scaled down, never
  clipped; SNR is unchanged. The clean condition sends the recording byte for byte.
- Scoring reuses `factscore` (`score_transcript`): STT transcript -> `extract_facts` -> same
  precision/recall rules as the text-only gold scores (ambiguous readings count as a miss).
  Bootstrap: 2000 resamples of utterances, seed fixed, percentile 95% CI; the same resampled
  indices are used for every condition so "recall drop vs clean" is a paired interval. Only
  utterances present in all four conditions are used. Test (20) and dev (10) are reported separately;
  the headline is test. With about 20 utterances the intervals are wide.

## Priority 2 / noise eval: recorded street noise primary (2026-10-29)
- Conditions are now clean, `street_20`, `street_10`, `street_5` (primary) and `pink_10` (secondary):
  150 planned STT calls, ledger 22 spent + 150 = 172 of cap 290, headroom 118 for 429 retries.
  Replaces the earlier `snr20/10/5` pink-only plan (no results had been produced under those names).
- Why: seeded pink noise is repeatable but is not traffic; a recording of real street noise is the
  claim worth making. Pink stays as one 10 dB stressor so there is a controlled reference.
- Street bed: `eval/audio/noise/street.wav` (`--street-file`), 16 kHz mono 16-bit, at least 30 s and at
  least as long as the longest utterance; `eval/audio/` is already gitignored. No upper limit (the
  60 s cap is for speech). Each clip uses a random window chosen by the per-clip seed. A missing or
  invalid file is one problem line; dry-run prints `Street noise: ... [MISSING]` and a real run
  refuses before any call. Pink clips are still prepared without it.
- The report prints street and pink as separate tables, each against clean. They are never pooled:
  different noise, different claim. `convert_recording.py --street` makes the bed from a phone
  recording (ffmpeg, argument list, output validated by `check_recording` with bounds 30 s and no
  maximum; written via a temp file so a failed conversion never replaces an existing file).
- Whatever the bed contains is whatever the author recorded: the write-up should describe it
  (place, time, phone) and not call it representative of all Indian streets.

## Quick replies reviewed; slice 5 priorities (2026-10-29)

- bn and hi quick replies were corrected by the author and are marked `reviewed`; kn stays
  `pending` until a friend checks it. hi "coming in 2 minutes" is "बस 2 मिनट" because "आ रहा हूँ"
  is gendered and the rider's gender is unknown.
- Loanwords used as-is in Indian addresses (cross, main, gate, floor, opposite, block, flat) must
  stay as transliterated loanwords in the target script. The live kn->bn turn mistranslated
  "opposite" and "main", so this is the top item of slice 5 (masking).
- Landmark chips must render in the rider's language, not the speaker's script (a Bengali rider
  could not read the Kannada landmark). Second top item of slice 5.

## Roles are independent of languages; two-way turns and per-role quick replies (2026-10-29)

- Product rule: the customer and the rider can each use any of the 10 languages, in both
  directions. No code, default, fixture or doc may tie a role to a language. Language pairs in
  tests, demos and the eval live-turn fixture (`evaluation/liveturn.py`, kn to bn) are examples
  only; demo casting is undecided. Both screens offer all 10 languages with no preselected choice
  (placeholder option; buttons stay disabled until chosen). The solo page has two pickers with the
  same rule.
- Either role may POST a turn. The source language is the speaker's, the target is the other
  participant's, and the `turn` event goes to the other role only; the sender gets the response and
  shows chips of what they said. Fact extraction already depends only on the spoken language, so
  the universal layer (all 10) and the native rules (kn en hi bn) apply to riders exactly as to
  customers. Landmark rendering in the listener's language is still slice 5, not done here.
- The rider's talk button is deliberately secondary ("use when stopped") and sits below the quick
  replies: riding is the case the product is designed around.
- Quick replies: three ids per sender role. Rider: `reached_gate`, `which_floor`, `coming_2_min`.
  Customer: `come_to_gate`, `coming_down`, `leave_at_security`. An id from the other role is
  rejected (422). The phrase is sent in the RECIPIENT's language. All 10 languages are covered.
- `come_to_gate` is "Come to the gate" with no number. A fixed, pre-translated phrase cannot carry
  a variable, and splicing a number into machine-translated text would be exactly the unverified
  number handling the product exists to avoid. The customer says the number by voice. This
  deliberately deviates from the brief's "Come to gate number ...".
- Review status is per phrase, not per language: the rider's bn and hi phrases the author corrected
  stay `reviewed` (texts unchanged); en is the source; everything else is `pending`, including the
  new customer bn and hi phrases and the rider's kn. The UI shows the "unreviewed machine
  translation" note for pending phrases.
- The table was generated once with `scripts/gen_quick_replies.py` (local en-indic model, no
  network) and pasted unedited as data. Known weaknesses of that output, left pending on purpose
  for a speaker to fix: some Tamil phrases look truncated or subjectless; Punjabi uses a decomposed
  nukta and an ASCII apostrophe; Hindi "I'm coming down" is gendered; Telugu rider phrases use a
  third-person verb; Marathi "gate" is an odd word; several phrases end in a danda or full stop.

## Slice 5: masking, listener-language landmarks, hi/bn numbers, latency tooling (2026-10-29)
- Toolkit finding: IndicProcessor only protects emails, URLs, multi-part numerals and
  `[A-Za-z0-9]*[#|@]\w+` tokens. Bare digits and words like "cross" are not protected, so the
  default path mistranslates them.
- Placeholder choice: `#L{n}`, numbered from 51. Probe on the dev split (30 sentences, real model),
  placeholder survived translation: `#L{n}` 29/30, `<{n}>` 24/30, `XQ{n}Z` 22/30, `<ID{n}>` 12/30,
  `[ID{n}]` 10/30, `ID{n}` 6/30 (eval/results/placeholder_probe.json). Numbering from 51 keeps
  the slots clear of small numbers the model might invent.
- `verified` means every slot came back exactly once and no unknown placeholder appeared. Fallback
  chain: verified masked text, then the fact summary in the listener's language, then the plain
  unmasked translation with verified False. The summary uses only extracted facts and the table.
- Digits are plain 0-9 in every language (author decision, 2026-10-29). `restore` also rewrites any
  native digit the model wrote itself, so chips, summaries and spoken text never mix numerals; the
  bn quick reply "coming in 2 minutes" now reads "2 মিনিটে আসছি" (still reviewed).
- Loanword spellings (src/saathi/loanwords.py) are hand-written and unreviewed. Beta languages are
  the likeliest to be wrong. Language support stays data in one table, never per-language branches.
- `Fact` gained `value_start`, `value_end` (spans for masking) and `local` (listener-language
  name). `FactOut` exposes `local`. The listener chip shows `local`, or "name not available" with
  the class only; the speaker still sees what was said.
- Landmark localization translates the span alone (masked) and accepts it only if verified and
  `plausible` (non-empty, no "#", no repeated phrase, bounded length, at least 80% target script).
  `plausible` catches runaway output, not wrong-but-fluent output; the author should eyeball it.
- hi and bn: numbers 51-99 added, hi flat trigger (फ्लैट, फ्लेट, मकान), bn digit-ordinal
  suffixes. Not validated against real STT. "বাড়ি/বাসা" skipped on purpose (too ambiguous).
  The gold test split stays frozen; nothing was tuned on it.
- Latency study: 20 measured turns x 2 calls = 40 calls; the translator is warmed locally first
  so no model load is timed; audio comes from eval/audio/latency/, so no TTS is spent making it;
  no text is printed or saved. `live_turn.py --target X` makes each beta language one 3-call smoke.
- Text A/B (eval/results/masking_ab.json, 90 gold turns, real models): default recall 0.674,
  masked 0.808, masked + summary 0.851; loanwords kept 128, 162, 168 of 255. Text only: it does
  not cover STT or TTS, and the gold text is ours, not recorded speech.

## No people in the evaluation or the demo (2026-10-29)
Nobody is recorded. Address-fact audio is Gnani TTS, labelled "clean synthetic"; real human speech
is FLEURS (CC BY 4.0), 10 clips per language. Rejected: friend recordings (consent, scheduling,
and the Kannada set would depend on one voice) and author recordings. Cost: no real-speaker
address result exists, and EVAL.md says so beside every number.

## FLEURS clip selection
First eligible clips in archive order (3 to 30 s, one per sentence id), streamed with early stop so
the 4.8 GB archives are not downloaded. No listening, so no cherry-picking. Pinned by SHA-256 of the
converted 16-bit WAV in a committed manifest (trust on first use, then enforced). FLEURS WAVs are
32-bit float; `float_wav_to_pcm16` converts before pinning so the pin matches what is scored.

## Street noise
One licensed recording ("College Street", Freesound 181026, CC BY 4.0). The public preview is a
lossy mp3 (originals need a login) with distant hawker voices; both limits are stated in EVAL.md.
Pink noise stays a secondary condition.

## Chip labels in the listener's language
`labels.py`: English is the source, bn and hi use the author-reviewed forms, other languages use the
loanword table and are marked "pending" in the UI. Chips themselves still come from the source
transcript, so a wrong label cannot change a value.

## Demo input mode
Behind `SAATHI_DEMO_INPUT` (off by default). The client sends a prepared clip with `X-Demo-Clip: 1`,
honoured only when the flag is on; clips are served only by id from a manifest, so a request cannot
name a path. Both screens show a badge so a clip is never mistaken for live speech. The clips are
generated offline (`make_demo_clips.py`), never at request time.
