# Handoff

Source of truth: docs/DESIGN.md, docs/DECISIONS.md, AGENTS.md (delivery-rider bridge, approved
2026-10-12). Schedule from 2026-10-28: submission target Nov 7, hard deadline Nov 10. Priority order:
P1 demo core (slices 1-4, by Oct 31), P2 noise eval, P3 README/EVAL.md/demo script, P4 extras.

## Done
- Slice 0: language table, three-model routing (committed).
- HF access: all three IndicTrans2 models now load. VRAM with all three (RTX 3050 6 GB, AC power,
  `scripts/measure_vram.py`): weights 1423 MiB, torch peak 1435 MiB, device-wide 2466 MiB (982 MiB
  of that is pre-load), 3677 MiB free. Headroom is fine.
- Slice 1: fact extractor + 30-utterance gold set. pytest 198 passed, ruff, mypy, tsc, npm test pass.
  Text-only scores: dev P 1.00 / R 0.94, test P 1.00 / R 0.96 (optimistic; gold written by us, not
  real STT output; test split frozen, SHA pinned).

## Waiting on the author
- Recordings, LAN two-phone test, and quick-reply review: every phrase except the rider's bn and hi
  is still pending (the new customer bn/hi ones first; see the end of this file).

## Pending commit groups (author commits)
Slice 1:
1. `feat(facts): extract gate, floor, cross, main, block, flat and landmark from transcripts`
   - src/saathi/facts/, tests/test_facts.py
2. `feat(eval): add synthetic fact gold set and text-only scorer`
   - eval/gold/, src/saathi/evaluation/factscore.py, scripts/score_facts.py, tests/test_fact_gold.py
3. `docs(decisions): record slice 1 extraction decisions`
   - docs/DECISIONS.md

Slice 2 (room backend; pytest 252 passed, ruff, mypy, tsc, npm test pass):
1. `feat(rooms): add in-memory rooms with tokens, expiry and event queues`
   - src/saathi/rooms.py, tests/test_rooms.py
2. `feat(api): add room endpoints with SSE, turn upload and quick replies`
   - src/saathi/room_routes.py, src/saathi/app.py, src/saathi/config.py, .env.example,
     tests/test_room_api.py
3. `feat(pipeline): return extracted facts and a verified flag from run_turn`
   - src/saathi/pipeline.py, tests/test_pipeline.py
4. `docs(decisions): record slice 2 room backend decisions`
   - docs/DECISIONS.md

Slice 3 (screens; pytest 255, npm test 29, e2e 7 pass). Commit slice 2 groups first (shared files):
1. `feat(quickreplies): add unreviewed quick-reply table, catalog endpoints and audio on reply`
   - src/saathi/quickreplies.py, src/saathi/catalog_routes.py, src/saathi/room_routes.py,
     src/saathi/app.py, tests/test_room_api.py
2. `feat(ui): add customer and rider room screens with chips, audio and quick replies`
   - src/saathi/static/ (new pages, js/, index.html, app.css), tests/js/{sse,chips,quick-replies}.test.js
3. `test(e2e): add two-context room test and fake Gnani server`
   - tests/e2e/rooms.spec.js, tests/e2e/serve.py, tests/e2e/turn-retry.spec.js
4. `docs(decisions): record slice 3 UI decisions`
   - docs/DECISIONS.md (slice 2 and 3 edits are in one file; commit once after both)

Slice 3 notes: quick-reply id `cannot_find` renamed `which_floor`; quick-reply text is the
unreviewed machine output (hi/bn pending author review); first use of each phrase costs one Gnani
TTS call; old single-phone page now at /solo.html; reload leaves the room; not tried on a real phone.

Slice 4 offline part (pytest 269, npm test 29; e2e 7 passed at builder run):
1. `feat(audio): normalize TTS loudness with a peak limiter`
   - src/saathi/loudness.py, src/saathi/gnani.py, tests/test_loudness.py
2. `test: cover the customer-to-rider path through the real Gnani client`
   - tests/test_integration.py
3. `docs: add LAN two-phone checklist and slice 4 decisions`
   - docs/LAN_CHECK.md, docs/DECISIONS.md (commit once, after slices 2-3 doc edits)

Slice 4 open: real Gnani turn (needs --dry-run review and approval), listening check of normalized
audio, LAN two-phone test per docs/LAN_CHECK.md (author). numpy is imported by loudness.py but not
declared in pyproject.toml (comes via transformers/sacrebleu): author decides whether to declare it.

Priority 2 noise eval (offline; pytest 296 passed, ruff, mypy clean; only --dry-run was run):
1. `feat(eval): add seeded SNR noise mixer`
   - src/saathi/evaluation/noisemix.py, tests/test_noisemix.py
2. `feat(eval): add noise evaluation harness with bootstrap fact scores`
   - src/saathi/evaluation/noiseeval.py, src/saathi/evaluation/factscore.py, scripts/eval_noise.py,
     tests/test_noiseeval.py (factscore.py ships with slice 1's eval commit first)
3. `docs(decisions): record noise eval decisions`
   - docs/DECISIONS.md (commit last)

Dry-run: `uv run --no-sync python scripts/eval_noise.py run --dry-run` plans 120 STT calls; ledger
22 spent + 120 = 142 of cap 290. All 30 recordings MISSING (eval/audio/gold/ empty): the author must
record them before the real run. Proposal awaiting approval: delete scripts/eval_turns.py and its
PLANNED_CALLS in calls.py (keep evaluation/turns.py for latency).

Session 2026-10-29 additions (pytest 320, ruff, mypy, tsc clean; e2e 7 passed):
- Priority 2 group 2 now also includes the street-primary / pink-secondary change: noiseeval.py,
  eval_noise.py, tests/test_noiseeval.py and src/saathi/evaluation/wavtools.py. Dry-run plans 150
  calls (clean, street 20/10/5, pink 10): 22 spent + 150 = 172 of cap 290.
- New: `feat(eval): add ffmpeg recording converter`
  - src/saathi/evaluation/convert.py, scripts/convert_recording.py, tests/test_convert.py
- New: `feat(scripts): add guarded one-turn live kn->bn check`
  - scripts/live_turn.py, src/saathi/evaluation/liveturn.py, tests/test_live_turn.py
  (RUN 2026-10-29 with author approval, 3 calls; ledger now 25/290. Added `--show-text` after
  the run was approved; it has no test yet. Result: STT exact, 4 facts correct, bn audio at
  eval/audio/live/g02_kn_bn.wav, translate 14.3 s because the models were cold in the script.)
- New: `build: declare numpy`  - pyproject.toml, uv.lock (numpy==2.5.3)
- New: `chore(eval): remove superseded FLORES eval_turns plan`
  - scripts/eval_turns.py (deleted), src/saathi/evaluation/calls.py, tests/test_eval_calls.py
- New: `docs: LAN check, recording script, README and demo script drafts`
  - docs/LAN_CHECK.md (rewritten; Android Chrome flag over hotspot), docs/recording/rahul_script.md,
    docs/EVAL.md, README.md, docs/DEMO_SCRIPT.md
  (commit slice 4's LAN_CHECK.md group together with this; DECISIONS.md still last)
- `--show-text` now has a test (tests/test_live_turn.py); it folds into the live-turn commit group
  above, so remove the "no test yet" caveat. pytest 321, ruff, mypy, tsc, npm test 29 pass.
- New: `feat(quickreplies): use author-reviewed bn and hi phrases`
  - src/saathi/quickreplies.py (new status "reviewed"; kn stays pending), tests/test_room_api.py
  (commit with or after slice 3 group 1, which creates quickreplies.py)
- Author to record: 20 gold lines (docs/recording/rahul_script.md) and 60-90 s of street noise.
- Quick-reply review: bn and hi done 2026-10-29; kn still needs a friend's review.

## TOP of slice 5 (masking), from the author's review of the live turn
1. Loanword preservation: cross, main, gate, floor, opposite, block, flat stay as transliterated
   loanwords in the target script, never translated. g02 kn->bn must give
   "সেকেন্ড ক্রস, থার্ড মেইন, গেট নম্বর ২-এর কাছে, গণেশ মন্দিরের উল্টোদিকে" in spirit; the
   model currently mistranslates "opposite" and "main".
2. Landmark chips render in the rider's language (landmark was shown in Kannada script to a
   Bengali rider): translate or transliterate the landmark text into the rider's script.

## Known issues / notes
- Tokens are Bearer headers, so the UI must read SSE via fetch, not EventSource.
- SSE events are dropped (not replayed) while a role has no open stream.
- `verified` is only "guards passed" until masking (slice 5).
- Quick-reply ids are final: rider reached_gate, which_floor, coming_2_min; customer come_to_gate,
  coming_down, leave_at_security (see "Roles independent of languages" below).
- `gnani.py` still logs the upstream error body (DESIGN section 10 says drop); not yet fixed.
- Oversized uploads are rejected after multipart spooling: fine on LAN only.

## Next
Slice 4 (integration, TTS loudness normalization; needs a Gnani call, so show --dry-run first and
ask the author; then LAN two-phone check by the author). The quick-reply table has landed.

## Roles independent of languages (session 2026-10-29, after the groups above)
Product rule: customer and rider can each use any of the 10 languages, either can speak or send
quick replies, no language is preselected. pytest, ruff, mypy, tsc, npm test and e2e (7) pass.
Not run: real phones, real Gnani calls, the en-indic model beyond the one generation run.

Product changes (these edit files already named in earlier groups, so fold them in rather than
making duplicates; if the earlier groups are already committed, use the groups below as-is):
1. `feat(rooms): let either role speak a turn and send quick replies per role`
   - src/saathi/room_routes.py, src/saathi/quickreplies.py (6 ids, 10 languages, per-phrase review
     status), src/saathi/catalog_routes.py, src/saathi/app.py (comment only),
     tests/test_room_api.py, tests/test_pipeline.py, tests/test_translate.py, tests/test_facts.py
   - touches: slice 3 group 1 and "use author-reviewed bn and hi phrases"
2. `feat(scripts): add quick-reply translation generator`
   - scripts/gen_quick_replies.py
3. `feat(ui): neutral language pickers, shared room screen, rider talk button and customer replies`
   - src/saathi/static/ (customer.html, rider.html, solo.html, index.html, app.css, js/ui.js,
     js/room-screen.js, js/customer.js, js/rider.js, js/main.js, js/quick-replies.js,
     js/room-client.js), tests/js/quick-replies.test.js
   - touches: slice 3 group 2
4. `test(e2e): both roles speak, language-neutral pickers`
   - tests/e2e/rooms.spec.js, tests/e2e/turn-retry.spec.js
   - touches: slice 3 group 3
5. `docs: state that roles are language-independent`
   - README.md, AGENTS.md, docs/DESIGN.md, docs/DEMO_SCRIPT.md, docs/LAN_CHECK.md,
     docs/HANDOFF.md, src/saathi/evaluation/liveturn.py and scripts/live_turn.py (docstrings only)
   - touches: the earlier docs groups
6. `docs(decisions): record role-independence and per-role quick replies`
   - docs/DECISIONS.md (append only; commit last)

Review needs: all quick-reply phrases except the rider's bn and hi are machine output (pending).
Known odd outputs (ta, pa, te, mr, hi "coming down" gender) are listed in DECISIONS.md.
