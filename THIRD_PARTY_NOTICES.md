# Third-party notices

The code and documents in this repository are MIT licensed (see `LICENSE`). Nothing below is
included in the repository unless the entry says so. Where this repository's own records do not
state a licence, the entry says "to verify" instead of guessing.

## Models and libraries used at run time

### IndicTrans2 (AI4Bharat) - translation models
- Used: `ai4bharat/indictrans2-indic-indic-dist-320M`, `ai4bharat/indictrans2-en-indic-dist-200M`,
  `ai4bharat/indictrans2-indic-en-dist-200M`, run locally.
- Included in this repo: no. Weights are downloaded from Hugging Face by the user; the models are
  gated, and the user must accept their terms there.
- Licence: to verify. The repository records only that the models are gated and "their terms apply"
  (README). Read the licence on each model card before redistributing anything derived from them.
- Reference: https://github.com/AI4Bharat/IndicTrans2

### IndicTransToolkit (AI4Bharat)
- Used: pre- and post-processing for IndicTrans2, installed as `IndicTransToolkit==1.1.1`.
- Included in this repo: no (a pinned dependency).
- Licence: to verify (not recorded in this repository).

### Other Python and JavaScript dependencies
- Pinned in `pyproject.toml`, `uv.lock`, `package.json` and `package-lock.json`, each under its own
  licence. This repository does not record those licences; a licence report from the lock files
  is to do before any redistribution.

## Services

### Gnani (Prisma speech to text, Timbre text to speech)
- Used through the author's own API key under Gnani's terms of service (to verify the current
  terms before any public use). No Gnani code, models or documentation are included here.
- Audio produced by Gnani TTS is used as synthetic evaluation and demo audio (clips are generated
  locally and gitignored). Whether that output may be redistributed is to verify under Gnani's terms.

## Data

### FLEURS (Google)
- Used: 100 read-speech clips (10 for each of bn, en, gu, hi, kn, ml, mr, pa, ta, te) for the
  speech-recognition error-rate evaluation.
- Licence: CC BY 4.0 (recorded in `eval/gold/fleurs_manifest.json` and `src/saathi/evaluation/fleurs.py`).
- Included in this repo: reference transcripts and SHA-256 pins in `eval/gold/fleurs_manifest.json`.
  The audio is downloaded by `scripts/fetch_fleurs.py` and is gitignored.
- Attribution: Conneau, A., Ma, M., Khanuja, S., Zhang, Y., Axelrod, V., Dalmia, S., Riesa, J.,
  Rivera, C., Bapna, A. (2022). FLEURS: Few-shot Learning Evaluation of Universal Representations
  of Speech. arXiv:2205.12446. https://huggingface.co/datasets/google/fleurs
- Changes: clips were converted from 32-bit float to 16-bit PCM WAV and, in the noise
  condition, mixed with street noise. Nothing else was changed.

### FLORES-200 devtest (Meta AI, NLLB team)
- Used: translation-quality evaluation (chrF++).
- Licence: CC BY-SA 4.0 (recorded in `scripts/fetch_flores.py` and `docs/DECISIONS.md`).
- Included in this repo: no source text (it is fetched into gitignored `eval/data/`).
  Result files under `eval/results/translation/` contain model outputs for FLORES inputs and
  therefore carry the same share-alike licence.

### "College Street" street-noise recording
- Author: Calcuttan. Freesound sound 181026. https://freesound.org/people/Calcuttan/sounds/181026/
- Licence: CC BY 4.0 (recorded in `scripts/fetch_noise.py` and `docs/EVAL.md`).
- Used: mixed into evaluation and demo audio at 20, 10 and 5 dB signal-to-noise ratio. Only
  Freesound's public lossy preview is used, converted to 16 kHz mono WAV.
- Included in this repo: no (fetched by `scripts/fetch_noise.py` into gitignored `eval/audio/`).
  Demo clips that contain it are gitignored.
- Changes: format conversion and level mixing.

## Fonts and icons

- The UI uses inline SVG icons drawn for this project and the system font stack; no third-party
  icon set or web font is bundled.
