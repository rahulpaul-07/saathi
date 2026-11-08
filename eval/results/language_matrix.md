# Language matrix: 90 ordered pairs through the guided demo

Run 2026-11-08T17:06:49+00:00 on NVIDIA GeForce RTX 3050 6GB Laptop GPU (ac power), commit 2f4b8f1, torch 2.9.1+cu128, IndicTrans2 with 1 beam(s). Produced by `scripts/language_matrix.py`.

## Result

- 90 of 90 ordered pairs passed. A pair passes when every verified clip of the customer's language passed.
- Clip replays: 306, from 34 verified clips. 306 passed, 0 failed.
- Gnani calls made by this run: 0. The client the app was given refuses any use, and `.env` was not read.
- Replays where the rider got stored audio: 306; the text-only fallback: 0. Every pair in `demo/bundle` has a stored translation, facts and audio; a text-only replay means a pair is missing from the bundle.

## Matrix

Rows are the customer's language, columns the rider's. Each cell is the result and the median response time in ms over that pair's clips; `n/a` is the same language twice, which a room refuses.

| from \ to | bn | en | gu | hi | kn | ml | mr | pa | ta | te |
|---|---|---|---|---|---|---|---|---|---|---|
| bn | n/a | ok 2 | ok 2 | ok 2 | ok 2 | ok 2 | ok 2 | ok 2 | ok 2 | ok 2 |
| en | ok 2 | n/a | ok 2 | ok 2 | ok 2 | ok 2 | ok 3 | ok 2 | ok 3 | ok 2 |
| gu | ok 2 | ok 2 | n/a | ok 2 | ok 2 | ok 2 | ok 3 | ok 2 | ok 3 | ok 2 |
| hi | ok 2 | ok 2 | ok 2 | n/a | ok 2 | ok 2 | ok 2 | ok 2 | ok 2 | ok 2 |
| kn | ok 2 | ok 3 | ok 3 | ok 4 | n/a | ok 3 | ok 3 | ok 2 | ok 2 | ok 2 |
| ml | ok 2 | ok 2 | ok 2 | ok 2 | ok 2 | n/a | ok 2 | ok 2 | ok 2 | ok 2 |
| mr | ok 2 | ok 2 | ok 2 | ok 2 | ok 2 | ok 1 | n/a | ok 2 | ok 2 | ok 2 |
| pa | ok 2 | ok 2 | ok 2 | ok 3 | ok 2 | ok 3 | ok 3 | n/a | ok 3 | ok 2 |
| ta | ok 3 | ok 3 | ok 2 | ok 2 | ok 2 | ok 2 | ok 2 | ok 2 | n/a | ok 2 |
| te | ok 2 | ok 2 | ok 2 | ok 2 | ok 2 | ok 2 | ok 2 | ok 2 | ok 2 | n/a |

## Failures

None: every replay passed.

## Response time

Wall-clock time of the one POST, in ms. A stored pair is a lookup: translation, facts and audio are read from the bundle. A pair missing from the bundle runs the real local translator.

| path | replays | median | 95th percentile | slowest |
|---|---|---|---|---|
| stored translation and audio | 306 | 2 | 3 | 18 |
| local translation, text only | 0 | - | - | - |

This is a correctness run, not a benchmark: nothing was done to quiet the machine, so these times show what a laptop in ordinary use did, not what the app can do. Latency under stated conditions is in `eval/results/latency.json`.

## By rider language

A translation counts as verified when every number and loanword placeholder came back from the model exactly once. When one did not, the rider gets the facts spelled out from tables instead of the model's sentence, and the delivery card is unaffected. Stored pairs are counted with the flag recorded when they were built.

Landmark chips are the open-vocabulary facts; one with no rendering in the rider's language is shown as it was heard.

| rider | replays | translation not verified | landmark chips | with a rendering |
|---|---|---|---|---|
| bn | 30 | 8 | 22 | 22 |
| en | 32 | 1 | 23 | 23 |
| gu | 30 | 0 | 21 | 21 |
| hi | 29 | 0 | 21 | 21 |
| kn | 30 | 0 | 23 | 23 |
| ml | 31 | 13 | 24 | 24 |
| mr | 31 | 0 | 22 | 22 |
| pa | 30 | 0 | 22 | 22 |
| ta | 32 | 2 | 24 | 24 |
| te | 31 | 0 | 23 | 23 |

## What was checked

Each replay is one `POST /rooms/{code}/turn` with the demo-clip header, made in process against the application in public mode with the shipped bundle and the real local translator (after the warm-up the app does at start). It passes when:

- the turn is accepted and raises no exception;
- the chips on the customer's screen and on the rider's screen equal the clip's expected facts, by the rule the demo-set scoring uses, and every rider chip has a label;
- the translation is not empty;
- the rider gets stored audio that loads as a WAV when the bundle holds one for that pair (all of them should), and the text-only fallback otherwise.

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
