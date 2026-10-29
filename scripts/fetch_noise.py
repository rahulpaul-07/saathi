"""Fetch the licensed street-noise bed and convert it to 16 kHz mono WAV.

Usage: uv run --no-sync python scripts/fetch_noise.py
No Gnani calls. Needs ffmpeg on PATH. Writes eval/audio/noise/street.wav (gitignored).

Source: "College Street" by Calcuttan, Freesound sound 181026, CC BY 4.0. A recording of road
traffic with horns and street hawkers in Kolkata. The public file is Freesound's lossy preview
(the original needs a login), and it contains distant hawker voices, so it is background noise
and not a speech-free bed. Attribution text for docs/EVAL.md lives there.
"""

import hashlib
import subprocess
import tempfile
from pathlib import Path

import httpx

SOURCE_PAGE = "https://freesound.org/people/Calcuttan/sounds/181026/"
PREVIEW_URL = "https://cdn.freesound.org/previews/181/181026_2474372-hq.mp3"
# Trust-on-first-use pin of the preview file.
PREVIEW_SHA256 = "1911ac0767d32a81cb80b984a2b21513ad37f930b97d110d751af8edc2d7f6ca"
OUTPUT = Path("eval/audio/noise/street.wav")


def main() -> None:
    response = httpx.get(PREVIEW_URL, follow_redirects=True, timeout=60)
    response.raise_for_status()
    digest = hashlib.sha256(response.content).hexdigest()
    print(f"sha256 {digest}")
    if not PREVIEW_SHA256:
        print("PREVIEW_SHA256 is not pinned yet: copy the hash above into this script")
    elif digest != PREVIEW_SHA256:
        raise SystemExit("the download does not match the pinned SHA-256; not converting it")
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as tmp:
        source = Path(tmp) / "street.mp3"
        source.write_bytes(response.content)
        subprocess.run(
            ["ffmpeg", "-y", "-loglevel", "error", "-i", str(source),
             "-ac", "1", "-ar", "16000", "-sample_fmt", "s16", str(OUTPUT)],
            check=True,
        )
    print(f"wrote {OUTPUT} from {SOURCE_PAGE}")


if __name__ == "__main__":
    main()
