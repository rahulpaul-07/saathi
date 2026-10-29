# Handoff

## Overnight summary (2026-10-29, slice 5)
Done: loanword/number masking with restore, landmark chips in the listener's language, fact-summary
fallback, hi/bn number and trigger rules, A/B script, latency study and beta smoke scripts (dry-run
only). Checks: pytest 404 pass, ruff, mypy, tsc clean, npm test 33, e2e 7.
Text A/B on all 90 gold turns (30 utterances x 3 targets), real IndicTrans2, eval/results/masking_ab.json:
| arm | fact recall | wrong extras | all facts correct | loanwords kept |
|---|---|---|---|---|
| A toolkit default | 0.674 | 67 | 9/90 | 128/255 |
| B masked | 0.808 | 67 | 13/90 | 162/255 |
| C masked + summary fallback | 0.851 | 65 | 17/90 | 168/255 |
Masking helps (recall +13 points, summary fallback +4 more) but is not enough alone: most turns still
lose at least one fact in text, and 4/90 masked translations failed verification. Landmark
localization passed the plausibility rule 72/72, unreviewed by a human. Text only, no STT/TTS.
Blockers: none hit. No Gnani calls, git, deletes or new dependencies were used. The smokes and
latency study need you awake and audio in eval/audio/latency/.
Pending commit groups: see "Slice 5" below (8 groups).

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
- (Superseded 2026-10-29: nobody is recorded; see the no-people session below.)
- Quick-reply review: bn and hi done 2026-10-29; kn is still pending review.

## Slice 5 (masking), from the author's review of the live turn: DONE offline
1. Loanword preservation: DONE. Numbers and loanwords are masked as `#L51...` placeholders before
   IndicTrans2 and restored after (digits as Latin digits, loanwords from the table in
   src/saathi/loanwords.py). Not yet heard on real audio.
2. Landmark chips in the listener's language: DONE. The landmark span is translated alone and shown
   only if it passes `plausible`; otherwise the listener sees the class only ("name not available").
3. 3-arm text A/B: DONE, eval/results/masking_ab.json (see the summary at the top).
4. hi and bn native numbers 51-99 and triggers: DONE, tests in tests/test_facts.py.
5. Stale lines fixed: DONE.
6. Beta smokes and latency study prepared as --dry-run only: DONE. Nothing was sent to Gnani.

Commit groups for slice 5 (all uncommitted; pytest 404, ruff, mypy, tsc, npm test 33, e2e 7 pass):
1. `feat(masking): preserve loanwords and numbers through translation with placeholders`
   - src/saathi/masking.py, src/saathi/loanwords.py, tests/test_masking.py, tests/placeholders.py,
     scripts/probe_placeholders.py, eval/results/placeholder_probe.json
2. `feat(facts): carry value spans and a listener-language name on each fact`
   - src/saathi/facts/types.py, src/saathi/facts/extract.py, src/saathi/landmarks.py,
     src/saathi/summary.py, tests/test_summary_landmarks.py
3. `feat(pipeline): translate masked text, fall back to the fact summary, localize landmarks`
   - src/saathi/pipeline.py, src/saathi/room_routes.py, tests/test_pipeline.py,
     tests/test_integration.py, tests/test_room_api.py, tests/test_live_turn.py
4. `feat(ui): show the listener the landmark in their language`
   - src/saathi/static/js/chips.js, src/saathi/static/js/room-screen.js, tests/js/chips.test.js,
     tests/e2e/rooms.spec.js
5. `feat(facts): add hi and bn numbers 51-99, flat triggers and bn ordinal suffixes`
   - src/saathi/facts/lexicons.py, tests/test_facts.py
6. `feat(eval): add masking A/B script and results`
   - scripts/eval_masking.py, eval/results/masking_ab.json
7. `feat(eval): add latency study and a --target option for the beta smoke tests`
   - src/saathi/evaluation/latency.py, scripts/latency_study.py, tests/test_latency.py,
     src/saathi/evaluation/liveturn.py
8. `docs: record slice 5 decisions and handoff`
   - docs/DECISIONS.md, docs/HANDOFF.md (commit last)

Author actions for slice 5:
- Review the loanword table (src/saathi/loanwords.py). Spellings are hand-written and unreviewed;
  the beta languages are the likeliest to be wrong.
- Beta smokes (3 calls each, 18 for te gu ml mr pa ta):
  `uv run --no-sync python scripts/live_turn.py --target ta --dry-run`, then `--yes --show-text`.
  Do this awake; repeat for te, gu, ml, mr, pa.
- Latency study (40 calls): put 16 kHz mono WAVs in eval/audio/latency/, then
  `uv run --no-sync python scripts/latency_study.py --dry-run`, then `--yes` on AC power. The
  dry-run currently refuses because that folder has no audio.
- Check the landmark renderings by eye: the A/B accepted 72/72 landmark translations by the
  `plausible` rule only, which does not prove they are good Bengali, Hindi, Kannada or English.

## Session 2026-10-29 (after 14fabbe): digits, results docs, screenshots
Checks: pytest 415, ruff, mypy, tsc, npm test 33, e2e 7 all pass. No Gnani calls, git or new deps.
- Digits are plain 0-9 everywhere: `restore` rewrites any native digit; bn quick reply is now
  "2 মিনিটে আসছি" (still reviewed). Tests: tests/test_masking.py.
- docs/EVAL.md has the masking A/B table (0.674 / 0.808 / 0.851) and the chips-as-second-layer
  point; README says the same; the stale "latency study has no script" line is gone.
- docs/media/rider-unmasked.png and rider-masked.png: rider screen on real local IndicTrans2 output
  for gold g02 kn->bn (synthetic address), fake Gnani. Regenerate: capture the replay JSON (it was
  scratch/g02.json, gitignored), then `node scripts/screenshots.mjs scratch/g02.json`.
- Finding: with the real model, g02 kn->bn FAILS the placeholder check (the model rewrote every
  `#L5x` as "<আই. ডি. N>"). So "masking on" shows the fact-summary fallback ("2 ক্রস, 3 মেইন, গেট
  2, ল্যান্ডমার্ক গণেশ মন্দির"), not a fluent masked sentence, plus the "could not be fully
  checked" note. The unmasked sentence is fluent but renders "opposite" as "বিরোধিতা"
  (opposition) and drops "gate number" to "গেট নং দুটির কাছে". The chips are right in both.
  Keep that wording honest in the LinkedIn post.

Commit groups (after the slice 5 groups; the first two touch files from groups 1 and 5):
1. `feat(masking): write plain 0-9 digits in restored text and the bn quick reply`
   - src/saathi/facts/text.py, src/saathi/masking.py, src/saathi/quickreplies.py, tests/test_masking.py
2. `feat(scripts): add rider-screen screenshot harness`
   - scripts/screenshot_server.py, scripts/screenshots.mjs, docs/media/
3. `docs: add masking A/B results, chips-as-safety-layer note and handoff`
   - docs/EVAL.md, README.md, docs/DECISIONS.md, docs/HANDOFF.md (commit last)

## Known issues / notes
- Tokens are Bearer headers, so the UI must read SSE via fetch, not EventSource.
- SSE events are dropped (not replayed) while a role has no open stream.
- `verified` now means every placeholder slot came back exactly once and no unknown placeholder
  appeared (slice 5). It says nothing about translation quality.
- Quick-reply ids are final: rider reached_gate, which_floor, coming_2_min; customer come_to_gate,
  coming_down, leave_at_security (see "Roles independent of languages" below).
- `gnani.py` still logs the upstream error body (DESIGN section 10 says drop); not yet fixed.
- Oversized uploads are rejected after multipart spooling: fine on LAN only.

## Next
Author-gated work: approve the Gnani budget below, then run the generators and evals; LAN
two-phone check, beta smokes, latency study, review of the loanword table, kn quick replies and
the pending chip labels. Offline slices 1-5 are built. No recordings are needed (see below).

## Session 2026-10-29 (late): no-people plan, FLEURS, noise, labels, demo mode
Checks: pytest 458, ruff, mypy (106 files), tsc, npm test 37, e2e 10 all pass. No Gnani calls, git
or new dependencies. Nothing was spent: ledger is still 25/290.
- Plan change: no people in the demo or the evaluation. Address-fact audio is Gnani TTS ("clean
  synthetic"), real human speech is FLEURS (CC BY 4.0), noise is "College Street" (Freesound
  181026, CC BY 4.0). `docs/recording/` is optional (README there); EVAL.md "Audio sources and
  labels" says so plainly.
- FLEURS: `scripts/fetch_fleurs.py` fetched 100 clips (10 x 10 languages, archive order) into
  eval/audio/fleurs/, pinned in eval/gold/fleurs_manifest.json. Noise: `scripts/fetch_noise.py`
  (pinned preview mp3 converted to 16 kHz WAV). Both re-run reproduce the pins.
- Localized chip labels (bn and hi use the reviewed forms, others pending): src/saathi/labels.py.
  Please review: bn floor "তলা", hi floor "फ्लोर" (confirmed by you); the other eight are
  machine-chosen loanwords marked "pending" in the UI via `#chips-note`.
- Demo input mode (off by default, `SAATHI_DEMO_INPUT=1`, clips in `SAATHI_DEMO_CLIPS_DIR`):
  a participant sends a prepared clip; both screens show "Demo clip, not live speech" badges and a
  banner. Split-screen page: `/demo.html` (16:9 stage, room code copied across).
- Demo clips: `scripts/make_demo_clips.py` (4 TTS calls: kn-wrong-translation, kn-bakery, ta-gate,
  te-gate; street noise at 10 dB). Ta and te texts were written by Claude and need a native
  read-through before filming. Dry-run works; the real run is NOT done.
- Gold audio: `scripts/make_gold_tts.py` (30 TTS calls into eval/audio/gold_tts/). Then
  `eval_noise.py run --audio-dir eval/audio/gold_tts`. FLEURS STT: `scripts/eval_speech.py`.
- `docs/DEMO_SCRIPT.md` rewritten (shot list, captions, final caption verbatim).

Dry-runs (nothing sent): make_gold_tts 30, make_demo_clips 4, eval_noise 150, eval_speech 400.
Expected total 739 including the 25 spent; proposed cap 780 (table in DESIGN section 11). The
cap in calls.py is still 290, so eval_speech and eval_noise are refused until you approve a cap;
I then change `GNANI_CALL_CAP` and tests/test_eval_calls.py. Credit balance is unknown.

Commit groups (the author commits; touches files from earlier groups, so commit after them):
1. `feat(labels): show chip labels in the listener's language with a review status`
   - src/saathi/labels.py, src/saathi/room_routes.py, src/saathi/static/js/chips.js,
     src/saathi/static/js/room-screen.js, src/saathi/static/customer.html, rider.html,
     tests/test_labels.py, tests/test_room_api.py, tests/js/chips.test.js
2. `feat(eval): add pinned FLEURS fetch and speech evaluation`
   - src/saathi/evaluation/fleurs.py, speecheval.py, wavtools.py, noiseeval.py,
     scripts/fetch_fleurs.py, scripts/eval_speech.py, eval/gold/fleurs_manifest.json,
     tests/test_fleurs.py, tests/test_float_wav.py, tests/test_speecheval.py
3. `feat(eval): add pinned licensed street-noise fetch`
   - scripts/fetch_noise.py
4. `feat(demo): add demo input mode, split-screen page and clip generator`
   - src/saathi/demo.py, config.py, catalog_routes.py, app.py, room_routes.py, .env.example,
     .gitignore, src/saathi/static/{demo.html,app.css,js/demo-clips.js,js/demo-split.js,
     js/room-client.js,js/room-screen.js}, src/saathi/evaluation/democlips.py,
     scripts/make_demo_clips.py, tests/{test_demo.py,test_democlips.py,js/demo-clips.test.js}
5. `test(e2e): cover demo mode, the flag-off case and the split page`
   - tests/e2e/demo.spec.js, tests/e2e/serve.py, playwright.config.js
6. `feat(eval): add gold sentence TTS generator`
   - scripts/make_gold_tts.py
7. `docs: no-people plan, audio sources, FLEURS and noise attribution, demo script`
   - docs/EVAL.md, DESIGN.md, DEMO_SCRIPT.md, DECISIONS.md, HANDOFF.md, docs/recording/ (commit last)

## Demo clips run and STT check (session 2026-10-29, after commit 700df8c)
Spent 8 Gnani calls with approval: 4 TTS (make_demo_clips.py) and 4 STT (transcribe_demo.py).
Ledger 33/780 (cap raised to 780, approved). pytest 462, ruff, mypy (109 files) pass.
- Finding (STT of the TTS clips, street noise 10 dB): kn writes number words and the existing kn
  rules give correct chips for both kn clips. ta and te STT also write number words (Tamil
  "மூன்று", Telugu "ఒకటి", "నాలుగు"), and ta/te have no native rules, so both clips give NO chips.
- `scripts/transcribe_demo.py` prints transcript, chips and intended facts per clip (never saves
  them) and exits 1 if a clip yields no chips; `clips_without_chips` has a unit test.
  Right now it exits 1 for ta-gate and te-gate.
- Open decision: add a small ta and te number-word lexicon (1-20 cardinals and ordinals, gate,
  cross, main, floor as STT spells them), machine-verified by indic-en back-translation and STT,
  labelled "machine-verified, not native-reviewed". Extractor not changed yet.
- Back-translation of the sources (scripts/backtranslate_demo.py): all 4 faithful.
- Extra commit group: `feat(demo): add demo clip back-translation and STT checks`
  (scripts/backtranslate_demo.py, scripts/transcribe_demo.py, tests/test_backtranslate_demo.py,
  democlips.py, tests/test_democlips.py), plus the cap change (calls.py, three test files, docs).
- Not run: make_gold_tts.py (30 calls).

## ta and te lexicons from real STT output (session 2026-10-29, after the demo STT check)
Done: the open decision above. Spent 59 Gnani calls (ledger 33 -> 92 of 780): 23 on a probe run
that timed out and lost its transcripts (my bug, fixed), 32 on the rerun, 4 on transcribe_demo.py.
`transcribe_demo.py` now exits 0: all 4 clips give their chips.
- `src/saathi/facts/lexicons_ta_te.py` (new): ta and te cardinals and ordinals 1-20, triggers,
  fillers and landmark cues, only spellings the STT wrote. "machine-verified, not native-reviewed"
  in the code, docs/LEXICON_EVIDENCE.md (word, value or role, evidence), DECISIONS.md and DESIGN.md.
- `src/saathi/evaluation/lexprobe.py`, `scripts/probe_numbers.py` (`--table` back-translation,
  `--dry-run`, real run; saves after each sentence, resumes, one retry after 5 s on a transport
  error counted against its 32-call cap). Transcripts in eval/state/lexicon_probe.json (gitignored).
- Follow-up: script-purity test added (no entry failed); Tamil ordinal 5 rechecked with 2 calls
  (`probe_numbers.py --ordinal5`, ledger 92 -> 94), the STT wrote ஐந்தாவது, entry added.
- Gaps: numbers above 20, letters, noisy speech beyond the demo clips. Telugu ordinals 16/17/19/20 are written as cardinals, which already work.
- test_facts.py: the old "ta native words give nothing" assertion now uses gu.
- Next: the same probe for gu, ml, mr, pa (about 64 calls plus spare). Not started.
- Commit groups (after the earlier ones): `feat(facts): add machine-verified ta and te lexicons`
  (facts/lexicons_ta_te.py, lexicons.py, extract.py docstring, tests/test_facts_ta_te.py,
  tests/test_facts.py, docs/LEXICON_EVIDENCE.md) and `feat(eval): add lexicon probe`
  (evaluation/lexprobe.py, scripts/probe_numbers.py, tests/test_lexprobe.py), then docs.

## Hindi rider for the demo video (session 2026-10-29, after commit ed701c5)
Decision: no Bengali rider in the video; the rider is Hindi in every shot. No Gnani calls.
- `scripts/check_kn_hi.py` (local IndicTrans2): kn-wrong-translation on kn to hi. Unmasked Hindi
  mistranslates words (main road -> "main gate", opposite -> "opposition") but keeps the numbers;
  masked is correct and verified, so the fallback summary does NOT fire for this clip. Stills
  `docs/media/rider-unmasked.png` and `rider-masked.png` regenerated for a Hindi rider
  (`--replay scratch/kn_hi.json`, then `node scripts/screenshots.mjs scratch/kn_hi.json`).
- `scripts/backtranslate_quick_replies.py kn`: rider kn phrases are all "pending"; "I am at the
  gate" comes back as "I'm at the door", the other two are faithful. Shot 5 uses these.
- `scripts/log_demo_calls.py N [--label]` adds live-server calls to the ledger by hand
  (tests/test_log_demo_calls.py); noted in docs/DEMO_SCRIPT.md.
- Tests that assert the cap text use GNANI_CALL_CAP. Clip role strings and DESIGN.md say kn to hi.
- Left alone: docs/recording/rahul_script.md still names Bengali (a recording plan with people, which
  the no-people decision replaced).
- Commit groups: `docs(demo): use a Hindi rider in the demo script and stills` (docs/DEMO_SCRIPT.md,
  docs/media/*.png, scripts/screenshots.mjs, scripts/screenshot_server.py, evaluation/democlips.py,
  docs/DESIGN.md, docs/HANDOFF.md); `feat(scripts): add kn to hi check and quick-reply
  back-translation` (scripts/check_kn_hi.py, scripts/backtranslate_quick_replies.py);
  `feat(scripts): log live demo calls to the ledger` (scripts/log_demo_calls.py,
  tests/test_log_demo_calls.py); `test: use the cap constant in cap-text assertions`
  (tests/test_live_turn.py, tests/test_noiseeval.py).

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
