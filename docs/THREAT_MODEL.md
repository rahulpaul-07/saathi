# Threat model

Scope: the app as built today, one process on one host, used by two people in a short-lived room.
It is a portfolio project that has not been deployed publicly (AGENTS.md rules that out), so this
document describes what the code defends against, how that is tested, and what it does not
defend against. Test references are `file::test name`. "No test" is written where there is none.

## Assets

| Asset | Where it lives | Why it matters |
|---|---|---|
| Gnani API key | environment variable, `Settings.gnani_api_key` (a `SecretStr`), sent as `X-API-Key-ID` | Abuse spends the owner's credits |
| Gnani credit budget | the account; locally a call ledger for eval and demo-clip runs | Burning it stops the service |
| Spoken addresses (audio, transcripts, facts) | request memory, the in-memory room and its card, never disk or logs | Personal data |
| Room tokens (128-bit, one per role) | the room in memory; the browser's `sessionStorage` | Anyone holding one can act as that person in the room |
| Room code (6 characters) | shown on screen, in the rider link | Lets a stranger try to join |
| Process memory and CPU | the host | Exhaustion makes every room fail |

## Trust boundaries

1. Browser to server. Everything from the browser is untrusted: audio, room codes, tokens, JSON
   bodies, headers (including `X-Demo-Clip`).
2. Server to Gnani. The server trusts Gnani's answers only as data: a transcript is text to
   extract facts from, never an instruction. Gnani response bodies are never logged or forwarded.
3. Server to the translation model, in process. Its output is checked (placeholders, runaway
   guard) before it is spoken or shown.
4. Customer to rider, through the room. Each side gets only events addressed to its role.
5. Operator to the demo mode switch (`SAATHI_DEMO_INPUT`). Off by default; when on, the server is
   a rehearsal tool, not something to expose.

Out of scope: a malicious operator or host, a compromised dependency, and a person who can see or
hold the victim's unlocked phone.

## Threats

### Room code guessing

The code is 6 characters from a 31-letter alphabet (about 887 million values) and a token is
needed for everything after joining. An attacker guesses codes against `POST /rooms/{code}/join`.
With at most 50 live rooms (`max_rooms`), one guess hits a live room with probability about 5.6e-8.
Joining does not let the attacker take over an existing role: a room holds one customer and one
rider, so a third joiner gets 409, and a joiner that arrives first is a visible, wrong rider.

Mitigations and tests:
- Random unambiguous alphabet: `test_rooms.py::test_codes_use_the_unambiguous_alphabet`.
- Malformed codes rejected before lookup: `test_room_api.py::test_malformed_room_code_is_rejected`.
- Join attempts counted per IP before the lookup, hit or miss, 10 per minute by default:
  `test_room_api.py::test_join_attempts_are_rate_limited_per_ip`.
- Room full is refused: `test_room_api.py::test_third_joiner_is_refused`.
- Idle and hard expiry: `test_rooms.py::test_room_expires_when_idle_and_activity_extends_it`,
  `test_room_expires_at_the_hard_limit_even_when_busy`.
- Unknown room and wrong token give the same 404 on every route, so codes cannot be probed:
  `test_room_api.py::test_bad_or_missing_token_gets_the_same_404_on_every_route`.

Residual: the limit is per client IP as the server sees it. Behind a reverse proxy that is the
proxy's address unless the proxy is configured and the app reads the forwarded address, which it
does not. Many IPs multiply the guess rate. No test.

### Token theft

Tokens are 128 bits from `secrets`, sent in an `Authorization: Bearer` header, never in a URL or
cookie. That removes CSRF (nothing is sent automatically) and keeps tokens out of server logs,
history and Referer headers. The browser keeps the token in `sessionStorage` so a reload rejoins;
any script running on the origin can read it, so the defence is making sure none other than ours
runs, which is what the Content-Security-Policy does.

Mitigations and tests:
- Distinct 128-bit tokens, a token from another room is refused:
  `test_rooms.py::test_create_and_join_issue_distinct_128_bit_tokens`,
  `test_token_from_another_room_is_rejected`,
  `test_room_api.py::test_token_from_another_room_cannot_read_or_act`,
  `test_audio_from_another_room_is_not_served_even_with_a_valid_own_token`.
- Policy on every response, no inline script or style, no remote source:
  `test_security_headers.py::test_every_response_carries_the_policy`,
  `test_the_policy_has_no_inline_or_remote_allowance`,
  `test_error_and_stream_responses_carry_the_policy`.
- `sessionStorage`, not `localStorage`, so the token dies with the tab; storage failures never
  break the page: `tests/js/session.test.js` (all six tests); a malformed stored session is
  rejected and removed: `session.test.js::a malformed stored session is rejected and removed`.
- A closed or expired room invalidates every token and clears the stored session:
  `test_room_api.py::test_expired_room_rejects_everything`, `tests/js/reconnect.test.js::stops at
  once, with no retry, when the room is gone or closed`.

Residual: a cross-site scripting bug in our own code would still expose the token, and the app
renders transcripts and translations as text (`textContent`), which is the control against that.
There is no automated scan for DOM injection. A token is not bound to a device.

### Reply and event flooding, and credit burn

Paid calls are speech to text and text to speech. A flood of turns, or of replies that trigger a
synthesis, burns credits and fills queues.

Mitigations and tests:
- Turns are limited per IP before any paid call (10 per minute by default):
  `test_room_api.py::test_turn_rate_limit_applies_before_paid_calls`,
  `test_app.py::test_rate_limit_returns_429_after_the_cap`.
- Quick replies and chip replies share one budget of 30 per minute per participant, separate from
  the turn budget, and a refused reply publishes nothing:
  `test_room_api.py::test_the_31st_chip_reply_gets_429_and_publishes_no_event`,
  `test_the_chip_reply_limit_is_per_participant`,
  `test_the_reply_limit_is_separate_from_the_turn_limit`,
  `test_quick_replies_are_limited_too_and_share_the_budget_with_chip_replies`.
- Quick replies cannot be free text; only a fixed phrase id for the sender's role is accepted, and
  the phrase audio is cached so repeats cost nothing:
  `test_room_api.py::test_a_role_cannot_send_the_other_roles_phrase_or_free_text`,
  `test_chip_reply_schema_rejects_unknown_kinds_actions_and_extras`.
- A turn before the rider joins is refused without a paid call:
  `test_room_api.py::test_turn_before_rider_joins_is_refused_without_a_paid_call`.
- A slow or absent listener cannot block the speaker: a full event queue drops the oldest event:
  `test_rooms.py::test_full_queue_drops_oldest_instead_of_blocking`.
- Gnani 429 is reported as a retryable 503 and not retried by the server; other failures retry
  once: `test_app.py::test_upstream_rate_limit_is_reported_as_retryable_503`,
  `test_gnani.py::test_rate_limits_client_errors_and_connect_errors_are_not_retried`.
- Failures leave the room unchanged and cost no further paid calls:
  `test_failure_injection.py` (all tests).
- Eval and demo-clip scripts go through a ledger with a hard cap:
  `test_eval_calls.py::test_ledger_counts_persists_and_refuses_past_the_cap`,
  `test_metered_client_counts_each_call_and_blocks_at_the_cap`.

Residual: limits are per IP and per process. Several IPs, or several processes, multiply them.
Rooms are the unit of cost and `max_rooms` caps how many can exist, but a participant inside a
room may still spend up to the turn limit every minute for two hours (the hard TTL).

### Upload abuse

Turns upload a WAV. Attackers send non-audio, huge or very long files, or wrong content types.

Mitigations and tests:
- Content type allow-list, WAV header parse, size cap (2.5 MB) and duration cap (60 s), all
  checked before any paid call: `test_room_api.py::test_bad_audio_is_rejected_before_any_paid_call`
  (not a WAV, too long, too large, two wrong content types), `test_audio.py` (header parsing).
- Audio is held in memory for 60 s, at most 5 clips per room, never written by us:
  `test_rooms.py::test_turn_audio_expires_and_is_capped`.
- Audio ids have a fixed shape, so there is no path to traverse:
  `test_room_api.py::test_bad_audio_id_shape_is_rejected`; static files cannot escape their
  directory: `test_app.py::test_static_mount_does_not_serve_files_outside_the_static_dir`.

Residual: the multipart body is received in full by the framework (spooled beyond 1 MB) before the
handler can say 413, because the app reads at most the cap but does not limit the request body
itself. A very large upload therefore costs bandwidth and temporary disk. The fix belongs at a
reverse proxy (a request size limit). No test.

### SSE exhaustion

`GET /rooms/{code}/events` holds a connection open. It needs a valid token, and each role has at
most one live subscription: a new one replaces the old, so one participant cannot hold many
streams. The ceiling is 2 streams per room times `max_rooms`. A keepalive every 15 s lets the
server notice rooms that ended.

Mitigations and tests:
- Newer subscription replaces the older: `test_rooms.py::test_newer_subscription_replaces_the_older_one`.
- Events reach only the addressed role: `test_rooms.py::test_events_reach_only_the_addressed_role`.
- Close and expiry end the streams and forget the room:
  `test_rooms.py::test_close_ends_streams_and_forgets_the_room`,
  `test_room_api.py::test_event_stream_delivers_state_turn_quick_reply_and_closes`.
- Clients back off with jitter and stop for a gone room, so a dropped server is not hammered:
  `tests/js/reconnect.test.js` (backoff, jitter, stop on 404).

Residual: the event endpoint has no rate limit of its own, and a client that reconnects in a tight
loop is only slowed by its own backoff. A full-capacity run is not covered by a test; the load
script in `scripts/load_rooms.py` drains events in process and does not open real streams.

### Limiter memory growth

`SlidingWindowLimiter` keeps one deque per key and removes expired hits only when the same key
comes back. Keys are IP addresses and `room code:role` strings, so a key that is never seen again
stays in memory for the life of the process. Growth is slow (well under a kilobyte per key) and
is bounded by how many distinct IPs and rooms arrive, but it is not bounded by design.

Mitigations and tests: none beyond the per-key window itself
(`test_ratelimit.py::test_blocks_over_limit_then_allows_after_window`,
`test_keys_are_independent`). **This is a known gap.** The fix is to sweep idle keys, or to move
limiting to Redis with TTLs (see PATH_TO_PRODUCTION.md). There is no test that the key table
shrinks, because it does not.

### Gnani key handling

The key is read from the environment into a `SecretStr`, so printing the settings or a traceback
shows a mask, and is sent only in the request header to the configured Gnani base URL. `.env` is
not committed and `.env.example` holds names with placeholders. Failure logs carry the status code
only, never Gnani's response body.

Mitigations and tests:
- The key is not in the settings representation or in failure logs:
  `test_gnani.py::test_the_api_key_is_not_in_the_settings_repr_or_in_failure_logs`.
- Response bodies are not logged or forwarded:
  `test_gnani.py::test_failures_log_the_status_but_never_the_response_body`,
  `test_app.py::test_upstream_failure_returns_generic_502`,
  `test_failure_injection.py::test_a_gnani_failure_is_reported_and_the_room_is_untouched`.
- Transcripts and card content are not logged:
  `test_room_api.py::test_card_content_is_never_logged`, `test_chip_replies_are_never_logged`,
  `test_no_speech_does_not_leak_the_transcript`.
- The key is never sent to the browser: there is no route that returns settings, and
  `/healthz` returns a fixed body (`test_app.py::test_healthz_needs_no_auth_and_no_upstream`).

Residual: the key sits in the process environment, readable by anything running as the same user.
The base URL is configurable, so a hostile environment could redirect the key; the environment is
inside the trust boundary. No secret scanner runs in CI today.

### Demo-mode exposure

Demo mode lets a page send prepared clips, serves them from `/demo/clips`, and allows the app to
be framed by itself. It exists for recording the demo on one machine.

Mitigations and tests:
- Off by default and exposes nothing when off:
  `test_demo.py::test_demo_is_off_by_default_and_exposes_nothing`.
- Only clips named in the manifest and present on disk are served; any other id is refused, so
  there is no file path from the request:
  `test_demo.py::test_demo_lists_and_serves_only_manifest_clips_with_a_file`,
  `test_demo_refuses_ids_outside_the_manifest`, `test_broken_or_missing_manifest_offers_no_clips`.
- The listener is told a turn was a demo clip only when demo mode is on, so a client cannot dress
  up a turn by sending the header: `test_demo.py::test_listener_is_told_a_turn_was_a_demo_clip_only_when_demo_is_on`.
- Frame permission is same-origin only in demo mode:
  `test_security_headers.py::test_frame_ancestors_allows_same_origin_only_in_demo_mode`.

Residual: with demo mode on, the clip list and clip audio are served without a token. The clips
are synthetic speech about invented addresses, so nothing private is exposed, but the mode must
not be switched on for a deployment that other people can reach.

### Framing (clickjacking)

Mitigation: `frame-ancestors 'none'` on every response (`'self'` in demo mode), tested by the
two policy tests above. No `X-Frame-Options` header is sent; current browsers honour the CSP
directive. Residual: very old browsers ignore it.

## Not covered by this model

Denial of service by network flood, TLS and certificate handling (the app is served over plain
HTTP locally and has no TLS of its own), dependency vulnerabilities (no audit is automated),
microphone permission prompts in the browser, and the privacy of the phone's own recording
buffers. See PATH_TO_PRODUCTION.md for what a deployment would still need.
