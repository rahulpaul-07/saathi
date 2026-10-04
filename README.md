# Saathi

A live two-way voice interpreter between Indian languages. One person speaks Bengali and the other
hears Kannada, and the reply goes back the other way. Turns are walkie-talkie style (tap to talk).

Pipeline per turn: Gnani Prisma v2.5 (speech to text) -> IndicTrans2 (translation, runs locally)
-> Gnani Timbre v2.5 (text to speech). The translation step sits behind a `Translator` interface
so it can be swapped.

Status: work in progress. Done so far: the Gnani client and the IndicTrans2 translator.

## Requirements

- Windows, Python 3.12 (managed by `uv`), and an NVIDIA GPU (the model used 0.6 GB of VRAM in
  fp16 on an RTX 3050; the code falls back to CPU, which I have not tested)
- Microsoft C++ Build Tools ("Desktop development with C++"): IndicTransToolkit compiles a
  Cython extension on install
- A Hugging Face account that has accepted the terms for
  `ai4bharat/indictrans2-indic-indic-dist-320M` (gated), then `uv run hf auth login`
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

## Tests

```
uv run pytest              # fast tests, no GPU or network
uv run pytest -m model     # real IndicTrans2 model on the GPU (needs the cached weights)
uv run ruff check . ; uv run mypy src tests scripts
```

`uv run python scripts/smoke.py --langs bn` calls the real Gnani APIs and spends credits.
