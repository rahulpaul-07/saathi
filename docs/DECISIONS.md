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
