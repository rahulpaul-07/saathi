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
- Status codes: 400 bad input, 413 too large, 422 no speech detected, 429 our per-IP limit
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
