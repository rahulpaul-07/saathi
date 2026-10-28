# Saathi

A delivery-directions interpreter. A customer gives directions by voice; a rider who uses another
Indian language gets the critical facts (gate, floor, cross/main, landmark) as big chips plus
translated audio, in a short-lived room. A rider cannot wait for a perfect sentence, so the chips
are the fast, redundant channel and the audio is the backup.

Roles are independent of languages: the customer and the rider can each use any of the 10
languages, in either direction, and either can answer by voice or with a quick reply. Any language
pair shown in demos or tests is only an example; the demo casting is not decided.

Pipeline per turn: Gnani Prisma (speech to text) -> fact extraction (native-script rules per
language) -> IndicTrans2 (translation, runs locally) -> Gnani Timbre (text to speech, loudness
normalized for outdoor playback). No hosted LLM.

Status: portfolio project, work in progress. The room backend, both screens and the offline
evaluation tooling are built and tested with fakes. The real-voice evaluation has not been run yet,
so this README makes no accuracy claim; results will be in `docs/EVAL.md` when they exist.

## Languages and support tiers

Any-to-any across the 10 languages Gnani supports for both speech input and output:
Bengali, English, Gujarati, Hindi, Kannada, Malayalam, Marathi, Punjabi, Tamil, Telugu.

| Tier | Languages | What backs it |
|---|---|---|
| Verified core | kn, en, hi, bn | native-word fact extraction rules and a synthetic gold set; quick replies in bn and hi partly author-reviewed (see below) |
| Reviewed | te | quick replies to be checked by a speaker |
| Beta | gu, ml, mr, pa, ta | the path is wired through the language table; labelled "beta" in the UI; quality is not evaluated |

Odia, Assamese and Urdu are not offered: Gnani supports none of them for both speech input and
output, and a translation-only language cannot be spoken or heard here.

Quick replies exist for both roles in all 10 languages and are sent in the recipient's language.
Rider: "I'm at the gate", "Which floor?", "Coming in 2 minutes". Customer: "Come to the gate",
"I'm coming down", "Leave it at the security desk". They are fixed phrases, not free speech.
Review is tracked per phrase: only the rider's bn and hi phrases are author-reviewed; every other
translation is machine output, marked unreviewed in the UI until a speaker checks it. The fixed
"Come to the gate" cannot carry a number, so a customer who needs to name a gate says it by voice.

## How it works

1. The customer creates a room and shares the 6-character code; the rider joins with it. Each
   participant gets a random 128-bit token, sent as a Bearer header.
2. Either person taps the talk button, speaks, and taps again. The server runs speech to text,
   fact extraction (on the speaker's language), translation and text to speech.
3. The other person's phone shows chips (gate, floor, cross/main, landmark) and auto-plays the
   audio. Repeat replays the audio locally with no network call. The speaker sees chips of what
   they said.
4. Either person can tap a quick reply; the other sees it as text and hears it. On the rider
   screen the talk button is secondary ("use when stopped") and the quick replies come first.

Privacy: addresses are personal data. Rooms are in memory and expire (30 min idle, 2 h hard).
Transcripts are never logged or stored. Tests, evaluation and demos use synthetic addresses only.

Honest limits: values the speech recognizer renders ambiguously (for example digit-by-digit flat
numbers) are shown as heard, not guessed; a "1/N" floor is shown with low confidence. Number and
landmark masking in translation is not built yet, so a translated number can still be wrong; the
chips are extracted from the original transcript for that reason.

## Requirements

- Windows, Python 3.12 (managed by `uv`), and an NVIDIA GPU (all three translation models together
  use about 1.4 GB of VRAM in fp16 on an RTX 3050 6 GB; the code falls back to CPU, which I have not
  tested)
- Microsoft C++ Build Tools ("Desktop development with C++"): IndicTransToolkit compiles a
  Cython extension on install
- A Hugging Face account that has accepted the terms for the three gated models
  `ai4bharat/indictrans2-indic-indic-dist-320M`, `ai4bharat/indictrans2-en-indic-dist-200M` and
  `ai4bharat/indictrans2-indic-en-dist-200M`, then `uv run hf auth login`
- ffmpeg (only to convert evaluation recordings)
- A Gnani API key in `.env` as `GNANI_API_KEY` (copy `.env.example`)

## Setup

```
uv sync
```

`uv.lock` takes torch from the official PyTorch `cu128` index, so this works on any machine with a
reasonable connection.

## Slow connection

torch is a single 2.7 GB download and `uv sync` cannot resume it. If it keeps stalling, download
the wheel with a resumable tool, check its hash, and install it by hand:

```
curl.exe -L -C - -o torch-2.9.1+cu128-cp312-cp312-win_amd64.whl https://download-r2.pytorch.org/whl/cu128/torch-2.9.1%2Bcu128-cp312-cp312-win_amd64.whl
```

The SHA256 must be `3a01f0b64c10a82d444d9fd06b3e8c567b1158b76b2764b8f51bfd8f535064b0`
(`Get-FileHash <file> -Algorithm SHA256`). Then:

```
uv sync --inexact --no-install-package torch
uv pip install <path-to>\torch-2.9.1+cu128-cp312-cp312-win_amd64.whl
```

After that, use the flags below, because uv sees the hand-installed torch as a different source
from the locked one:

- `uv run --no-sync <command>` (or set `UV_NO_SYNC=1`) to run without syncing.
- `uv sync --inexact --no-install-package torch` for any later sync. A plain `uv sync` or
  `uv run` tries to download torch again, and `--no-install-package torch` without `--inexact`
  uninstalls it.

Once, on a fast connection, run a plain `uv sync`. It fills the uv cache with the locked torch
wheel, and from then on the flags are not needed.

## Run

```
uv run --no-sync uvicorn saathi.app:create_app --factory --host 0.0.0.0 --port 8000
```

Startup loads the models and runs warm-up translations (about 12 s per model). Pages:

- `/customer.html` creates a room, shows what the rider says and sends quick replies.
- `/rider.html` joins with the code, shows chips, plays audio and sends quick replies; it can also
  record a turn.
- Neither page preselects a language.
- `/solo.html` is the original single-phone page (one device, both directions).

The microphone only works on localhost or HTTPS. On a laptop, use `http://localhost:8000`. For two
phones on a LAN, follow `docs/LAN_CHECK.md` (Android Chrome flag, hotspot, firewall rule and
cleanup). iOS Safari has no such flag; an iPhone can only be the rider, and that is untested.
This is a LAN-only project: no accounts, no history, no public deployment or tunnels.

Each turn spends Gnani credit. Real evaluation calls go through a persisted ledger with a hard cap,
and every evaluation script has a `--dry-run` that shows the planned calls first.

## Tests and checks

```
uv run --no-sync pytest              # fast tests, no GPU or network (fakes)
uv run --no-sync pytest -m model     # real IndicTrans2 models on the GPU (needs the cached weights)
uv run --no-sync ruff check . ; uv run --no-sync mypy src tests scripts
npm ci                               # once; dev tooling only
npm run typecheck                    # tsc --noEmit, strict
npm test                             # node --test for the UI logic
npm run e2e                          # Playwright, two browser contexts, fake Gnani and translator
```

Text-only fact extraction scores on the synthetic gold set: `uv run --no-sync python scripts/score_facts.py`.
Those scores are optimistic (the gold texts are written in the forms the recognizer was observed to
produce, not real recognizer output); the real test is the recorded-speech evaluation.

## Evaluation

- `docs/EVAL.md`: translation quality (done) and the speech evaluation (pending real results).
- `scripts/eval_noise.py run --dry-run`: the noise evaluation plan. Recorded gold utterances are
  played clean and mixed with real street-traffic noise at 20, 10 and 5 dB SNR, plus a pink-noise
  stressor; critical-fact precision and recall are reported with bootstrap confidence intervals.
  Recording instructions: `docs/recording/`.
- `docs/DESIGN.md` (architecture and plan) and `docs/DECISIONS.md` (why things are the way they are).
- Recordings of people stay in `eval/audio/` (gitignored) and are reported as consented human
  speech.
