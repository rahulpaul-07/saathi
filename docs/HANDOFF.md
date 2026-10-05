# Handoff

## Where we are
Slices 1-4 are built. Slice 4 (browser UI with Gnani 429 handling) passes on desktop; the
Android phone check is still open.

## Verified (slice 4)
pytest 42 passed, ruff and mypy clean, `npm run typecheck` clean, `npm test` 11 passed,
`npm run e2e` 3 passed (fake mic, stubbed `/turn`: 503, 503, 200 resends the identical WAV).
No real Gnani calls were made.

## Open
- Phone check: follow README "Run the UI" (uvicorn `--host 0.0.0.0`, Windows firewall rule,
  `chrome://flags/#unsafely-treat-insecure-origin-as-secure` on Android Chrome). Confirm
  recording, playback of the Gnani WAV, and the tap-to-playback timing. Then mark slice 4 done.
- Not browser-tested: the 60 s auto-stop and the mic-denied path.
- A retry re-runs STT, so a TTS-stage 429 can spend STT credit twice (accepted, in DECISIONS).
- `GET /turn` now returns 404 instead of 405 because of the static mount.

## Next
Slice 5: evaluation harness (FLORES chrF greedy vs beam, p50/p95 latency, paced calls with
429 backoff). See docs/DESIGN.md.
