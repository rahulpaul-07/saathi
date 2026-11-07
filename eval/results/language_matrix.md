# Language matrix: 90 ordered pairs through the guided demo

Run 2026-11-07T18:38:54+00:00 on NVIDIA GeForce RTX 3050 6GB Laptop GPU (battery power), commit 5ef51b1, torch 2.9.1+cu128, IndicTrans2 with 1 beam(s). Produced by `scripts/language_matrix.py`.

## Result

- 90 of 90 ordered pairs passed. A pair passes when every verified clip of the customer's language passed.
- Clip replays: 306, from 34 verified clips. 306 passed, 0 failed.
- Gnani calls made by this run: 0. The client the app was given refuses any use, and `.env` was not read.
- Replays where the rider got stored audio: 34; the text-only fallback: 272. Only the pairs recorded in `demo/bundle` have audio; that is the guided demo's design, so this run checks text, chips and routing for every pair and playback only for the recorded ones.

## Matrix

Rows are the customer's language, columns the rider's. Each cell is the result and the median response time in ms over that pair's clips; `n/a` is the same language twice, which a room refuses.

| from \ to | bn | en | gu | hi | kn | ml | mr | pa | ta | te |
|---|---|---|---|---|---|---|---|---|---|---|
| bn | n/a | ok 3652 | ok 3691 | ok 5742 | ok 4356 | ok 5818 | ok 5269 | ok 8428 | ok 4917 | ok 4756 |
| en | ok 3163 | n/a | ok 4387 | ok 3983 | ok 5088 | ok 5458 | ok 2427 | ok 4854 | ok 4083 | ok 4604 |
| gu | ok 5103 | ok 3963 | n/a | ok 6865 | ok 4720 | ok 5862 | ok 3956 | ok 6953 | ok 4575 | ok 4755 |
| hi | ok 4516 | ok 3766 | ok 4294 | n/a | ok 5303 | ok 5955 | ok 5359 | ok 8688 | ok 4830 | ok 3919 |
| kn | ok 3537 | ok 3262 | ok 3458 | ok 413 | n/a | ok 4216 | ok 2823 | ok 5610 | ok 3924 | ok 3570 |
| ml | ok 4988 | ok 2955 | ok 4060 | ok 5126 | ok 5136 | n/a | ok 4595 | ok 6921 | ok 4465 | ok 5180 |
| mr | ok 4477 | ok 5197 | ok 5510 | ok 5174 | ok 4300 | ok 4539 | n/a | ok 5232 | ok 4026 | ok 4870 |
| pa | ok 3726 | ok 3363 | ok 4404 | ok 4382 | ok 4611 | ok 5498 | ok 3790 | n/a | ok 4092 | ok 3695 |
| ta | ok 5536 | ok 4243 | ok 4886 | ok 2807 | ok 5888 | ok 2821 | ok 4952 | ok 7682 | n/a | ok 4720 |
| te | ok 4334 | ok 529 | ok 4526 | ok 6467 | ok 4924 | ok 7162 | ok 4488 | ok 7414 | ok 4659 | n/a |

## Failures

None: every replay passed.

## Response time

Wall-clock time of the one POST, in ms. A recorded pair replays the stored translation (landmarks are still localised live); any other pair runs the real local translator.

| path | replays | median | 95th percentile | slowest |
|---|---|---|---|---|
| stored translation and audio | 34 | 358 | 1730 | 1761 |
| local translation, text only | 272 | 4939 | 7602 | 12330 |

This is a correctness run, not a benchmark: nothing was done to quiet the machine, so these times show what a laptop in ordinary use did, not what the app can do. Latency under stated conditions is in `eval/results/latency.json`.

## By rider language

A translation counts as verified when every number and loanword placeholder came back from the model exactly once. When one did not, the rider gets the facts spelled out from tables instead of the model's sentence, and the delivery card is unaffected. Stored pairs are counted with the flag recorded when they were built.

Landmark chips are the open-vocabulary facts; one with no rendering in the rider's language is shown as it was heard.

| rider | replays | translation not verified | landmark chips | with a rendering |
|---|---|---|---|---|
| bn | 30 | 7 | 22 | 22 |
| en | 32 | 1 | 23 | 23 |
| gu | 30 | 0 | 21 | 21 |
| hi | 29 | 0 | 21 | 21 |
| kn | 30 | 1 | 23 | 23 |
| ml | 31 | 12 | 24 | 24 |
| mr | 31 | 0 | 22 | 22 |
| pa | 30 | 0 | 22 | 22 |
| ta | 32 | 0 | 24 | 24 |
| te | 31 | 0 | 23 | 23 |

## What was checked

Each replay is one `POST /rooms/{code}/turn` with the demo-clip header, made in process against the application in public mode with the shipped bundle and the real local translator (after the warm-up the app does at start). It passes when:

- the turn is accepted and raises no exception;
- the chips on the customer's screen and on the rider's screen equal the clip's expected facts, by the rule the demo-set scoring uses, and every rider chip has a label;
- the translation is not empty;
- the rider gets stored audio that loads as a WAV when the bundle holds one for that pair, and the text-only fallback otherwise.

A verified clip is one listed in `demo/clips/manifest.json`: its stored transcript yields exactly the expected facts. Speech recognition and synthesis are not run (the transcripts and audio are stored), so this does not test how a person's voice is heard.

16 clips of the 50-clip set are not in the manifest and are not replayed (see `eval/results/demo_set_after_fixes.md` for each): `bn-mixed`, `en-street`, `en-correction`, `en-mixed`, `kn-mixed`, `te-correction`, `te-landmark`, `gu-apartment`, `ml-street`, `ml-landmark`, `mr-street`, `mr-apartment`, `pa-mixed`, `ta-apartment`, `ta-mixed`, `ta-landmark`.

## Gnani language mapping

Each language's speech-to-text code (Prisma) and text-to-speech voice (Timbre) are in `src/saathi/languages.py`. The columns count what the 50-clip build (`scripts/build_demo_set.py`) stored for each language: the customer clip is Timbre speech in the clip's language and voice, the transcript is Prisma output for that language's code, and the rider recording is Timbre speech in the rider language's voice. They are counted from the files in `demo/`, the way the build decides what is missing; no call was made to produce this table.

| language | speech-to-text code | voice | customer speech | transcribed | rider speech |
|---|---|---|---|---|---|
| bn | bn-IN | Kirra | 5 of 5 | 5 of 5 | 3 of 4 |
| en | en-IN | Kaveri | 5 of 5 | 5 of 5 | 5 of 5 |
| gu | gu-IN | Falak | 5 of 5 | 5 of 5 | 4 of 4 |
| hi | hi-IN | Nalini | 5 of 5 | 5 of 5 | 4 of 4 |
| kn | kn-IN | Saanvi | 2 of 2 | 2 of 2 | 4 of 5 |
| ml | ml-IN | Reshma | 5 of 5 | 5 of 5 | 5 of 5 |
| mr | mr-IN | Zahira | 5 of 5 | 5 of 5 | 4 of 4 |
| pa | pa-IN | Mehuli | 5 of 5 | 4 of 5 | 5 of 5 |
| ta | ta-IN | Asmita | 4 of 4 | 4 of 4 | 4 of 4 |
| te | te-IN | Suhana | 4 of 4 | 3 of 4 | 5 of 5 |

Clips recorded by an earlier build are not counted: `kn-wrong-translation`, `kn-gate-correction`, `kn-bakery`, `te-gate`, `ta-gate`.

Clips that did not get all three calls stored:

- `te-correction` (te): gnani status 504; first call not stored: transcription
- `pa-mixed` (pa): gnani status 504; first call not stored: transcription
