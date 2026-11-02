# Deploying Saathi publicly

**Status: image built and started locally, not deployed.** The code paths here are covered by unit
and API tests with Gnani mocked. The image was built and run once on a laptop with the models
mounted from a local cache: `/healthz` answered, the process ran as a non-root user and Docker
reported it healthy (idle memory about 620 MiB). The first-start model download and any real
host are untested. This guide is
platform-neutral on purpose: it names no hosting provider and makes no claim about any provider's
free tier, limits or behaviour.

Public mode is off unless `SAATHI_PUBLIC=1`. With it unset, the app behaves exactly as in local
development.

## What public mode adds

| Guard | Setting | Default |
|---|---|---|
| Client IP from `X-Forwarded-For`, only from listed proxies | `SAATHI_TRUSTED_PROXIES` | empty (header ignored) |
| Daily Gnani budget, UTC day, persisted | `SAATHI_DAILY_GNANI_BUDGET`, `SAATHI_BUDGET_FILE` | 200, `data/gnani_budget.json` |
| Kill switch | `SAATHI_KILL_SWITCH`, `SAATHI_KILL_FILE` | off |
| Most rooms at once | `SAATHI_PUBLIC_MAX_ROOMS` | 20 |
| Room idle and hard lifetime (seconds) | `SAATHI_ROOM_IDLE_TTL_S`, `SAATHI_ROOM_HARD_TTL_S` | 600, 3600 |
| Room creations per IP per hour | `SAATHI_ROOM_CREATES_PER_HOUR` | 6 |
| Largest accepted audio upload (bytes) | `SAATHI_MAX_UPLOAD_BYTES` | 1000000 |
| Guided demo bundle directory | `SAATHI_DEMO_BUNDLE_DIR` | `demo/bundle` |
| Public origin printed in the room QR code | `SAATHI_PUBLIC_BASE_URL` | unset (request origin) |

The customer screen shows a QR code for the rider link (`GET /rooms/{code}/qr.svg`, needs the room
token, encodes only `/rider.html?code=...`). Behind a TLS-terminating proxy the app sees plain
`http`, so set `SAATHI_PUBLIC_BASE_URL=https://your.host` or the QR will carry the wrong scheme.

The per-minute limits (`ROOM_RATE_LIMIT_PER_MINUTE`, `TURN_RATE_LIMIT_PER_MINUTE`,
`REPLY_RATE_LIMIT_PER_MINUTE`) still apply. The defaults above are starting points chosen for a
small demo, not measured capacity.

The Gnani key is read from `GNANI_API_KEY`. Set it in the host's secret store, never in the image
or the repository.

## Steps

1. **Build the image** (`docker build -t saathi .`). It is CPU-only and contains no model weights
   and no key.
2. **Create two persistent volumes.** `/models` holds the translation models (downloaded on first
   start by `scripts/fetch_models.py`; allow time and several hundred MB to GB of disk, size
   unmeasured). `/data` holds the daily budget counter, so a restart cannot reset it. Without a
   volume on `/data` the budget restarts at zero on every redeploy.
3. **Set the environment**: `GNANI_API_KEY`, `HF_TOKEN`, `SAATHI_TRUSTED_PROXIES`, optionally the
   limits above. The translation models are gated on Hugging Face: without a token from an account
   that has accepted their terms, the container stops at start (seen locally as a 401 on
   `indictrans2-indic-indic-dist-320M`). A read-only token is enough.
   The image already sets `SAATHI_PUBLIC=1`.
4. **Put a reverse proxy with HTTPS in front.** Browsers only allow the microphone on HTTPS (or
   localhost). The proxy must set the real client address in `X-Forwarded-For` and must overwrite
   any value the client sent. Put its address or network in `SAATHI_TRUSTED_PROXIES`. The server
   starts with `--no-proxy-headers` so only this app interprets the header. Set a request body
   limit at the proxy as well (the app also rejects uploads above `SAATHI_MAX_UPLOAD_BYTES`).
5. **Support streaming.** Rooms use server-sent events (`/rooms/{code}/events`). The proxy must not
   buffer responses on that path and must allow long-lived connections.
6. **Check the health endpoint.** `GET /healthz` returns `{"status":"ok","live":true}` in public
   mode. `live` is false when the kill switch is on or the day's budget is spent. It reads local
   state only and spends no Gnani call.
7. **Mount the demo clips and bundle** (see below) at `/demo/clips` and `/demo/bundle`, or leave
   them out and the guided demo is simply not offered.

If the first start has no network access to download the models, the container stops with an
error instead of serving without a translator.

## Budget and kill switch

- Every Gnani HTTP attempt, retries included, is counted before it is sent. When the day's budget
  (UTC) is spent, no request is sent; the turn returns HTTP 503 with code `live_paused` and the
  client shows the existing "The speech service is unavailable. Try again." text (a dedicated
  "paused" string would need reviewed translations in nine languages, so none was added). The demo
  clips stay available through the clip picker.
- A corrupt or unwritable budget file counts as spent. This fails closed on purpose.
- **Kill file (no restart):** set `SAATHI_KILL_FILE` to a path, then create a file there (for
  example `touch /data/STOP`) and the next Gnani call is refused. Delete the file to resume.
- **Kill switch variable (restart needed):** `SAATHI_KILL_SWITCH=1`. Environment variables are
  read at startup, so changing it takes effect after a restart. Use the file for an emergency.
- Setting `SAATHI_DAILY_GNANI_BUDGET=0` turns live calls off the same way.
- The budget counts requests the app sends. It does not know the price per request or your Gnani
  plan limits, so choose the number from your own plan. Quick replies and the optional start-up
  warm-up (`SAATHI_WARM_TTS`) also go through it.

## Guided demo (no Gnani calls)

The guided demo replays stored turns (transcript, translation, spoken audio) through the real room
screens. It reuses the demo-clip picker: when a valid bundle is present in public mode, the picker
is shown, and a clip sent with the demo header is answered from the bundle. A clip that is not in
the bundle, or a language pair that was not stored, gets `422 demo_no_match`; it is never sent to
Gnani. The chips and the card are recomputed locally from the stored transcript with the same code
as a live turn.

The bundle is built once, by hand, with real Gnani calls:

```
uv run --no-sync python scripts/build_demo_bundle.py --dry-run   # prints the exact call budget
uv run --no-sync python scripts/build_demo_bundle.py --run       # spends the calls shown
```

`--dry-run` lists each clip and the call total (2 per clip: one speech-to-text, one text-to-speech)
and checks it against the evaluation ledger cap. It sends nothing and needs no key.

**To verify that guided-demo mode makes zero calls**, any of these:

1. Run the automated test: `uv run --no-sync pytest tests/test_public_app.py -k guided`. It
   replaces the Gnani client with an object that fails the test on any use.
2. On a running host, set `SAATHI_DAILY_GNANI_BUDGET=0` (or create the kill file), play a demo clip
   in a room, and confirm it still works while a microphone turn returns `live_paused`. With the
   gate closed, a replay that worked cannot have called Gnani.
3. Compare the Gnani dashboard's call count before and after a demo session.

## Not built

- Any platform-specific manifest or deploy script.
- Monitoring and alerting beyond `/healthz`.
- Rooms live in memory in one process; run one instance. A restart ends every room.

## Known limits to state honestly to users

- Translation runs on CPU in this image. Measured once (`scripts/cpu_latency.py`, result in
  `eval/results/cpu_latency.json`): with 2 CPUs allowed on a laptop, translation alone took a
  median of 2.9 to 3.0 s and a p95 of 5.5 to 5.8 s over 20 translations in each of two runs, and
  loading the three models took 34 to 37 s. This
  excludes speech-to-text and text-to-speech and is not a cloud measurement. The README latency
  figures were measured on a GPU laptop on AC power, so a CPU host will feel noticeably slower.
- The translation models run Hub-hosted code (`trust_remote_code=True`, required by IndicTrans2).
  Each repository is pinned to a full commit (`MODEL_REVISIONS` in `src/saathi/translate.py`), so
  a later push upstream cannot change what runs. The pins are the commits this project's own cache
  held; they were not independently audited, and the remote code itself was not reviewed line by
  line.
