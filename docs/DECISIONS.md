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

## Latency numbers are not yet trustworthy
Warm-latency benchmarks of the translator varied 30x between runs (greedy, 21 characters: 0.5 s
and 15 s). The laptop was reporting battery power on the Balanced plan, which is the likely cause
but is unconfirmed. Do not quote latency until it is re-measured on AC power with a fixed power
plan, and record the power state with every latency run.

## Translation input limits
Text is capped at 2000 characters and split into sentences, translated as one batch. Unsupported
or identical language pairs are rejected at the boundary.
