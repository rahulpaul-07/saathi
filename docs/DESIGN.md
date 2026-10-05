# Design: Saathi

## 1. Problem
Two people who share no language (for example Bengali and Kannada speakers) need to talk face to
face. Saathi is a walkie-talkie style interpreter on one phone: one person taps and speaks, the
other hears the translation in their language, then they swap. Built on Gnani's Indic speech APIs
with IndicTrans2 running locally for translation.

## 2. Goals and non-goals
- Goals: a turn (end of speech to start of playback) in about 2 s on a laptop GPU; works in a
  phone browser; honest quality and latency numbers (slice 5).
- Non-goals: streaming or simultaneous interpretation, accounts, conversation history, a native
  app, languages beyond the two configured pairs.

## 3. Users and core flow
1. Pick a language pair (`bn`<->`kn` or `hi`<->`ta`).
2. Speaker A taps their button, speaks, taps again to stop.
3. The browser converts the recording to 16 kHz mono WAV and posts it to `POST /turn`.
4. The server runs STT -> translate -> TTS and returns text, translated audio and timings.
5. The browser shows both texts and plays the audio. Speaker B replies with their own button.

## 4. Architecture
```text
 Phone / laptop browser                       Laptop (uvicorn, one process)
+---------------------------+   POST /turn   +-------------------------------+
| static UI (ES modules)    | -------------> | FastAPI app.py                |
|  recorder -> WAV encoder  |  multipart WAV |  per-IP limiter, validation   |
|  turn client (retry/back- | <------------- |  pipeline.run_turn            |
|  off, keeps the WAV)      |  JSON + b64 WAV|   Gnani STT --> IndicTrans2   |
|  player + timings         |                |   (GPU) --> Gnani TTS         |
+---------------------------+                +-------------------------------+
         GET / (same origin, served by FastAPI StaticFiles)
```

| Component | Responsibility | Talks to |
|---|---|---|
| `static/` UI | record, encode WAV, send turn, retry, play, show timings | `/turn` |
| `app.py` | HTTP boundary: limit, validate, map errors to status codes | pipeline |
| `pipeline.py` | one turn, per-stage timings | Gnani client, translator |
| `gnani.py` | Prisma STT and Timbre TTS calls, WAV header repair | Gnani API |
| `translate.py` | `Translator` interface, IndicTrans2 implementation | local GPU |

## 5. Data model
None stored. A turn exists only in memory: request audio, transcript, translation, response audio.
The browser holds the current recording until its turn succeeds or the user discards it.

## 6. Interfaces
`POST /turn`: multipart `audio` (16 kHz mono WAV, max 2.5 MB / 60 s), `src`, `tgt`.
200 -> `{src, tgt, transcript, translation, audio_base64, audio_format, timings}`.
Errors: 400 bad input, 413 too large, 422 no speech, 429 our per-IP limit, 503 Gnani rate
limiting (retryable), 502 other Gnani failure. Details in `DECISIONS.md`.

## 7. Key decisions and trade-offs
- UI is plain ES modules with `// @ts-check` and JSDoc types, typechecked by `tsc --noEmit`
  (strict), served by FastAPI. Rejected: React + Vite, which adds a build step and a bundle for
  one screen; also rejected untyped JS.
- The browser encodes WAV itself (decode the MediaRecorder output, resample to 16 kHz mono with
  `OfflineAudioContext`, write PCM16). Rejected: server-side ffmpeg (an extra system dependency,
  and Prisma's WebM support is undocumented).
- Same origin for UI and API, so no CORS configuration at all.
- Others (endpoints, pins, latency): `DECISIONS.md`.

## 8. Failure modes
| What fails | Effect | Handling |
|---|---|---|
| Gnani 429 (our 503) | turn fails | UI shows "One moment...", retries the same WAV up to 3 times with jittered backoff (about 1, 2, 4 s), then shows "Still busy" and a Try again button that resends the same recording. A retry re-runs STT, so it can spend credit twice; accepted for now. |
| Our per-IP 429 | turn refused | No automatic retry (the window can take up to 60 s to free). Recording kept; "Too many turns, wait a moment" and Try again. |
| Network error / timeout | turn fails | Treated like 503: backoff retries, recording kept. |
| 400 / 413 | bad recording | Not retried; clear message; recording discarded. |
| 422 no speech | nothing heard | Not retried; "Didn't catch that, please try again". |
| 502 | Gnani down | Not retried automatically; recording kept with Try again. |
| Mic permission denied / no secure context | cannot record | Explain that the page needs mic permission and HTTPS or localhost. |
| Model load (~12 s) | slow startup | Warm-up at startup, before the server accepts turns. |

## 9. Security
- Untrusted input: the uploaded audio and language codes are validated before any paid call;
  transcripts and translations are rendered with `textContent` only, never as HTML.
- Secrets: `GNANI_API_KEY` stays on the server; the browser never sees it.
- Abuse: every turn spends credit, so the per-IP limiter stays on. The app is meant for a laptop
  on a trusted LAN or localhost; it is not hardened for the public internet (no auth).

## 10. Scale and performance
One user pair at a time on one laptop. First bottleneck: Gnani rate limits (about 4 calls in
10 s triggered 429), then the single GPU. At 10x: a shared limiter store, a queue in front of the
translator, a negotiated Gnani quota. At 100x: hosted GPU inference and multiple workers.

## 11. Testing and evaluation
- Python: pytest with injected fakes (no network or GPU), `-m model` for the real model.
- UI: `node --test` for pure modules (WAV encoder, retry policy); `tsc --noEmit` strict;
  a Playwright check with a fake microphone and an intercepted `/turn` (503, 503, 200) proving
  the retry path and the clean console without spending credits; one manual phone test.
- Slice 5: FLORES-based quality (chrF) with greedy vs beam search, and p50/p95 turn latency,
  paced to respect Gnani's limits.

Real cases from the phone check (include in the slice 5 eval set):
1. bn->kn. Said "হে ঈশ্বর আমায় ভালো রাখো আমায় এই যন্ত্রণার জ্বালা দিও না ঠিক করো আমায় একটা
   বড় চাকরি দাও প্রিপারেশনটা ভালো করে করাও". Gnani heard the first two words as "সেই শর্ট".
   STT error at the start of the clip. With greedy decoding the garbled transcript made the
   translator emit "ಆ ಚಿಕ್ಕ ಚಿಕ್ಕ ..." to the length cap (reproduced; see DECISIONS.md).
   The ground-truth text translates correctly, so this is an STT error that the translator
   amplified.
2. bn->kn. "আমার লাইফ তো পুরো বেকারই চলছে": বেকার (pointless, wasted) was translated as
   ನಿರುದ್ಯೋಗಿ (unemployed). A translation word-sense error from correct STT (reproduced).
Laptop baseline from the first real run: STT 1470 ms, translation 502 ms, TTS 2056 ms, stop tap
to playback 4152 ms. The phone run was STT 1668, translation 5794, TTS 7817, 15845 total.

## 12. Scope
- Must: Gnani client, translator, `/turn` API, browser UI with 429 handling, evaluation.
- Should: README demo section with screenshots and measured numbers; phone HTTPS setup notes.
- Won't: streaming, accounts, history, more language pairs, public deployment.

## 13. Slice plan
| # | Slice (end-to-end, demo-able) | Proves | Time budget | Status |
|---|---|---|---|---|
| 1 | Scaffold + Gnani STT/TTS client + smoke test | real Gnani round trip works | - | done |
| 2 | Swappable IndicTrans2 translator on the GPU | local translation works and is fast | - | done |
| 3 | `POST /turn` with timings, validation, rate limiting | one full turn over HTTP | - | done |
| 4 | Browser UI: pair picker, two tap-to-talk buttons, WAV encoding, playback, timings incl. tap-to-playback; Gnani 429 handled ("One moment...", backoff retry, recording never lost); served by FastAPI; checked on a real phone | a person can use it | - | built and tested on desktop; Android phone check pending |
| 5 | Evaluation harness: FLORES chrF greedy vs beam, p50/p95 latency, paced calls with 429 backoff. Score STT errors separately from translation errors (feed ground-truth text to the translator to isolate it), and check whether STT errors cluster at the start of recordings (phone mic clipping the first syllables). Includes the real phone cases below. | honest numbers | - | |
| 6 | (Should) README demo section, phone HTTPS notes, final polish | presentable | - | |

## 14. Open questions
- Phone test: mic access needs a secure context. Assumed: Android Chrome over the LAN with the
  `unsafely-treat-insecure-origin-as-secure` flag for the test. iOS would need real HTTPS (for
  example a tunnel), which is out of slice 4 unless needed.
