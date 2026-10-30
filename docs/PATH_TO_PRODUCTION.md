# Path to production

**Status: design, not built.** Nothing in this document exists in the code. It describes how the
current app could grow into a service a delivery partner calls, which numbers it would be sized
from, and what is still missing. The shipped app is a single-process portfolio demo (see
AGENTS.md "Out of scope": no accounts, no public deployment). Numbers marked MEASURED come from
this repo's docs; everything else is an ASSUMPTION or a PLACEHOLDER and is labelled as such.

## 1. Integration with a delivery partner

Today a person taps "Create room" and reads a 6-character code to the other person. A partner
would not want that. Design:

1. The partner backend calls `POST /v1/rooms` (server to server, API key in a header) with its
   own `order_id`, the customer's language and the rider's language.
2. The service returns two signed deep links, one per role, and an expiry:
   `https://<host>/r/<signed-token>`. The token is a signed, short-lived value naming the room
   and the role. The partner sends the customer link by SMS or in its app and shows the rider link
   in its rider app (or opens it in a webview).
3. Opening a link needs no install and no code. The page exchanges the signed token for the same
   128-bit room token the app uses today, so everything after the join is unchanged.
4. When the room ends (closed, idle or hard expiry), the service calls the partner's webhook
   `room.ended` with `order_id`, the reason and the duration. No transcript, audio or card
   content is in the payload. Webhooks are signed (HMAC over the body with a per-partner secret)
   and retried with backoff; the partner deduplicates on an event id.
5. `POST /v1/rooms` is idempotent on `order_id`: a retry returns the same links instead of
   making a second room, so a partner retry cannot double the cost.

Decisions that would need the partner: who sends the customer link, which languages they know
the parties speak (a wrong guess means the wrong STT language), and whether the rider app can
embed a webview with microphone permission.

## 2. Scale

Current limits: one process, rooms in a Python dict, `max_rooms` 50, per-process rate limiters,
the translator in the web process on one GPU. Design for horizontal scale:

| Concern | Today | Design |
|---|---|---|
| Room state | in-process dict | Redis, one hash per room with a TTL equal to the existing idle (30 min) and hard (2 h) limits; the card and catch-up entries expire with it |
| App servers | one process | stateless, any number behind a load balancer; no sticky sessions needed because state is in Redis |
| Event fan-out | in-process queues | Redis pub/sub or streams per room; the SSE endpoint on whichever server holds the connection subscribes; the "newer subscription replaces older" rule moves to a per-role connection id in Redis |
| Translation | in the web process, GPU | a worker pool (GPU) behind a queue; the app enqueues text and awaits the result with a timeout; the measured model time is small (below) so queue wait is the thing to watch |
| Gnani calls | per-process, no shared limit | one shared rate limiter (Redis token bucket) in front of all Gnani calls, sized from the plan's contractual limit; calls over the limit wait briefly, then fail with the existing 503 |
| Rate limits | per process, per IP | Redis counters with TTL, shared across processes (the in-process limiter already sweeps idle keys, see THREAT_MODEL.md); keyed by partner and order as well as IP |
| Audio | in memory, 60 s, 5 clips per room | object store with a short lifecycle rule (delete after minutes), or keep in Redis with a TTL; never long-term |

MEASURED, for sizing the translation tier (docs/DECISIONS.md "Translator latency"; one pair,
bn to kn, fp16 on an RTX 3050 laptop GPU, on AC power, model only): median 108 ms for 21
characters, 176 ms for 51, 280 ms for 79; p95 up to 402 ms. Directions are typically 40 to 80
characters, so one GPU worker handles roughly 3 to 5 translations per second on that card before
batching. A production GPU would be faster; this is a lower bound from the card that was
available, not a promise.

MEASURED, app overhead only (docs/EVAL.md "Load test (fake Gnani)"): the app's own work was a few
milliseconds per turn alone and rose under 50 concurrent rooms in one event loop. That says the
single-process version is not the bottleneck at demo scale. It says nothing about real Gnani or
real translation latency under load, which has not been measured (the Gnani latency study in
docs/EVAL.md is still pending).

## 3. Cost per delivery conversation

Cost is dominated by Gnani calls. Each turn makes exactly two (1 speech-to-text, 1
text-to-speech), by design (docs/DESIGN.md). Quick replies make a text-to-speech call only the
first time a phrase is needed in a language (cached after that). Chip replies make none. The
translation model is local, so its cost is the GPU instance, not a per-call price.

MEASURED: the project ledger (docs/HANDOFF.md) counts calls, not seconds or characters. It stands
at 110 of 780 calls after all development, eval and rehearsal, which is the only real spend so
far and is a count of calls, not money.

The model, with every assumption stated so it can be changed:

| Symbol | Meaning | Value |
|---|---|---|
| T | turns per delivery conversation | ASSUMPTION: 6 (customer speaks 3 times, rider speaks 1 and replies with chips or quick replies) |
| A | audio seconds sent to STT per turn | ASSUMPTION: 8 s (the cap is 60 s; short directions are a few sentences) |
| C | characters sent to TTS per turn | ASSUMPTION: 70 (about one translated direction, in line with the 40 to 80 character translator test sentences) |
| Q | uncached quick-reply TTS calls per conversation | ASSUMPTION: 0 once the phrase audio is warm; up to 3 cold |
| P_stt | Gnani STT price per audio minute | PLACEHOLDER: `<GNANI_STT_PRICE_PER_MINUTE>`, take it from the contract, not from this document |
| P_tts | Gnani TTS price per character | PLACEHOLDER: `<GNANI_TTS_PRICE_PER_CHARACTER>`, take it from the contract |
| G | GPU instance cost per hour, divided by conversations per hour | PLACEHOLDER: `<GPU_COST_PER_HOUR>` |

Formulas, which hold whatever the prices are:

- Gnani calls per conversation = 2 x T + Q (12 with the assumptions above).
- STT audio minutes per conversation = T x A / 60 (0.8 min).
- TTS characters per conversation = T x C (420).
- Gnani cost per conversation = (T x A / 60) x P_stt + (T x C) x P_tts + Q x C_phrase x P_tts.
- Translation cost per conversation = G / (conversations a GPU handles per hour). At about 4
  translations a second (above) and T translations per conversation, one card handles far more
  conversations than a city has deliveries per hour, so this term is expected to be small, but
  it is not measured end to end.

No price appears here because none was supplied, and guessing would make the table look more
certain than it is. Two things would cut the Gnani term without losing quality: ending silence
early on the client so A shrinks, and caching TTS for repeated sentences (quick replies already
do this).

Capacity for the rate limits: with 2 calls per turn, a Gnani plan of N requests per minute allows
N / 2 turns per minute across all conversations. That, not the app, is the first scaling limit.
The development limiter caps this at 3 calls per 10 seconds (`evaluation/calls.py`); a
production plan would be negotiated.

## 4. Telephony beside masked calling

Riders and customers in India usually talk through a masked number provided by the partner. This
service would not replace that. It would sit beside it:

- Option A, side channel (simplest, first to build): the call stays as is. The deep link is sent
  with the order, and the rider glances at the chips (gate, floor, cross/main, landmark) while on
  the call. No audio from the call is touched.
- Option B, bridge: the telephony provider forks the call audio to this service over a media
  stream; the service transcribes each side, translates, and plays the translation as a third
  voice on the call. This needs streaming interpretation, which is out of scope today (AGENTS.md)
  and would need a streaming STT contract, barge-in handling and echo control. It changes the
  latency budget from "turn-based, a few seconds" to "conversational".
- Option C, IVR: the customer is asked once, by a phone prompt, to say the address; the service
  posts the card to the rider's app. It reuses the turn pipeline per utterance and is the
  smallest telephony step, but its quality depends on 8 kHz phone audio, which has not been
  tested (the eval uses 16 kHz clips with added noise only).

Recommendation: build A first because it needs no telephony integration, measure whether riders
use the chips, and only then consider C or B.

## 5. Privacy (India's Digital Personal Data Protection Act)

This is a description of design properties, not a legal opinion, and the project has had no legal
review. Addresses and voice are personal data; the design already minimises what is held:

What the design already does:
- No account, no history, no stored audio or transcript. Rooms are in memory and expire (idle 30
  min, hard 2 h). Closing a room wipes the card and the catch-up state.
- Transcripts and card content are never logged (tests listed in THREAT_MODEL.md).
- The Gnani key never reaches the browser; Gnani's response bodies are not logged.
- Synthetic addresses only in tests, eval and demos. Recordings of people stay local and
  gitignored, and are reported as consented human speech.

What a real deployment would still need (to be confirmed with someone qualified, not assumed):
- A statement of purpose and notice shown to the customer before they speak, in their language,
  and a way for them to refuse and still get the delivery.
- A way to record that consent without storing the speech.
- A data processing agreement with Gnani that says what Gnani retains and where it processes the
  audio. This design sends voice to Gnani, so what Gnani keeps matters more than what we keep.
- A statement of where the app and the translation model run (data location).
- A breach process, and a contact for questions or complaints.
- Retention for operational logs (IP addresses and counts are kept in memory only today; a real
  deployment would add logs and must decide their retention).
- Handling of children's data and of recordings in shared spaces, if relevant to the partner.

## 6. Not production-ready

An honest list of what is missing or unproven today:

- No public deployment, TLS, or reverse proxy configuration has been done or tested.
- State is in one process; a restart ends every room.
- Rate limiters are per process and per client IP as the server sees it; behind a proxy all users
  would share one IP bucket unless forwarded addresses are handled.
- The limiter sweeps idle keys once per window (THREAT_MODEL.md, "Limiter memory growth"), but it
  is still per process.
- A translator failure returns a 502 with a localized message (pending, machine-written, not
  native-reviewed) and leaves the room untouched (`tests/test_failure_injection.py`). There is no
  automatic retry or fallback translator.
- No request body size limit before the framework reads an upload; needs a proxy limit.
- The SSE endpoint has no limiter of its own.
- There is no authentication of the partner, signed links, webhooks or idempotency: all of section
  1 is design only.
- Real-world latency and accuracy are only partly measured. The Gnani latency study and the
  noise and real-voice STT results are not run (docs/EVAL.md). Phone-quality (8 kHz) audio has
  not been tested at all.
- Quality tiers: kn, en, hi, bn verified; te reviewed; gu, ml, mr, pa, ta are beta and labelled so
  in the UI. A production launch would need native review of those five and of the quick-reply
  phrases per language.
- Facts come from rule-based extraction, so a direction that does not fit the rules gives no chip
  and a please-repeat prompt, never a guess. Coverage on real, unscripted speech is unknown.
- Accessibility is checked only for tap targets, names and contrast on the room pages at 360 px;
  no screen reader or keyboard-only pass has been done.
- Load testing used a fake Gnani and a fake translator, on one laptop, in one process
  (docs/EVAL.md). It is not a capacity plan.
- No monitoring, alerting or metrics endpoint; `/healthz` is liveness only. No automated
  dependency or secret scanning.
- Single developer, no on-call, no incident process.
