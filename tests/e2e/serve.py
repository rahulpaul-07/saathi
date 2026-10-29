"""Serve the real FastAPI app (and so the real static UI) for the Playwright checks.

Gnani and the model are never reached: the translator and Gnani client are fakes returning
synthetic text and a silent WAV. The solo-page spec also intercepts /turn in the browser.
Run: uv run --no-sync python tests/e2e/serve.py
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
from saathi.gnani import GnaniClient
from saathi.languages import LANGUAGES

PORT = 8765
DEMO_PORT = 8766  # `--demo`: demo input mode on, clips from a temp folder
TRANSCRIPT = "gate number 2 third floor near the blue temple"  # synthetic address


def silent_wav() -> bytes:
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(24000)
        wav.writeframes(b"\x00\x00" * 2400)
    return buf.getvalue()


CHANGING_LANGUAGE = "pa-IN"  # Punjabi speakers alternate gate 2 and gate 4 per turn


class FakeGnani:
    def __init__(self) -> None:
        self.changing_calls = 0

    async def transcribe(self, audio: bytes, filename: str, language: str) -> str:
        if language == CHANGING_LANGUAGE:
            self.changing_calls += 1
            if self.changing_calls % 2 == 0:
                return TRANSCRIPT.replace("gate number 2", "gate number 4")
        return TRANSCRIPT

    async def synthesize(self, text: str, language: str, voice: str) -> bytes:
        return silent_wav()

    async def aclose(self) -> None:
        return None


class FakeTranslator:
    def translate(self, text: str, src: str, tgt: str) -> str:
        return f"<b>{tgt}</b> {text}"  # markup on purpose: the UI must show it as text


def demo_clips_dir() -> Path:
    """A throwaway clip folder: one synthetic 2 s tone clip per supported language."""
    directory = Path(tempfile.mkdtemp(prefix="saathi-e2e-demo-"))
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(16000)
        wav.writeframes(struct.pack("<h", 3000) * 32000)
    clips = [{"id": f"clip-{code}", "lang": code, "label": f"Sample {code}"} for code in LANGUAGES]
    for clip in clips:
        (directory / f"{clip['id']}.wav").write_bytes(buf.getvalue())
    (directory / "manifest.json").write_text(json.dumps({"clips": clips}), encoding="utf-8")
    return directory


if __name__ == "__main__":
    demo = "--demo" in sys.argv
    settings = Settings(gnani_api_key=SecretStr("dummy"))
    if demo:
        settings = Settings(
            gnani_api_key=SecretStr("dummy"), demo_input=True, demo_clips_dir=demo_clips_dir()
        )
    app = create_app(
        settings,
        gnani=cast(GnaniClient, FakeGnani()),
        translator=FakeTranslator(),
    )
    uvicorn.run(app, host="127.0.0.1", port=DEMO_PORT if demo else PORT, log_level="warning")
