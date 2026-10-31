"""Serve the real app in demo mode with scripted fakes, for the design screenshots.

No Gnani and no model. The customer's kn demo clips return the scripted synthetic transcripts of
saathi.evaluation.democlips in the order they are sent, and a small dictionary stands in for the
translator, so the page shows believable kn and hi text. Landmark words are synthetic.
Run: uv run --no-sync python scripts/design_server.py <port>
"""

import io
import json
import struct
import sys
import tempfile
import wave
from pathlib import Path
from typing import cast

import uvicorn
from pydantic import SecretStr

from saathi.app import create_app
from saathi.config import Settings
from saathi.evaluation.democlips import CLIP_SPECS
from saathi.gnani import GnaniClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tests" / "e2e"))
from serve import FakeGnani  # noqa: E402  (shares the silent-audio fake with the e2e server)

SCRIPT_IDS = ("kn-bakery", "kn-gate-correction")
LANDMARKS = {"bakery": "बेकरी", "ಬೇಕರಿ": "बेकरी"}


class ScriptedGnani(FakeGnani):
    """Returns the scripted transcripts in order, whatever the audio."""

    def __init__(self) -> None:
        self._texts = [spec.text for spec in CLIP_SPECS if spec.id in SCRIPT_IDS]
        self._sent = 0

    async def transcribe(self, audio: bytes, filename: str, language: str) -> str:
        text = self._texts[min(self._sent, len(self._texts) - 1)]
        self._sent += 1
        return text


class DictionaryTranslator:
    """A bare landmark maps through the table; a sentence keeps its placeholders, in Hindi words."""

    def translate(self, text: str, src: str, tgt: str) -> str:
        if text in LANDMARKS:
            return LANDMARKS[text]
        return text.replace("ಪಕ್ಕ", "के पास") if "#" in text else text


def clips_dir() -> Path:
    directory = Path(tempfile.mkdtemp(prefix="saathi-design-"))
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(16000)
        wav.writeframes(struct.pack("<h", 3000) * 32000)
    clips = [
        {"id": spec.id, "lang": spec.lang, "label": spec.label, "label_local": spec.label_local}
        for spec in CLIP_SPECS
        if spec.id in SCRIPT_IDS
    ]
    for clip in clips:
        (directory / f"{clip['id']}.wav").write_bytes(buf.getvalue())
    (directory / "manifest.json").write_text(json.dumps({"clips": clips}), encoding="utf-8")
    return directory


def main() -> None:
    open_limit = 10_000
    settings = Settings(
        gnani_api_key=SecretStr("dummy"),
        room_rate_limit_per_minute=open_limit,
        turn_rate_limit_per_minute=open_limit,
        reply_rate_limit_per_minute=open_limit,
        demo_input=True,
        demo_clips_dir=clips_dir(),
    )
    app = create_app(
        settings, gnani=cast(GnaniClient, ScriptedGnani()), translator=DictionaryTranslator()
    )
    uvicorn.run(app, host="127.0.0.1", port=int(sys.argv[1]), log_level="warning")


if __name__ == "__main__":
    main()
