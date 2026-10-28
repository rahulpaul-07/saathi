"""Serve the real FastAPI app (and so the real static UI) for the Playwright checks.

Gnani and the model are never reached: the translator and Gnani client are fakes returning
synthetic text and a silent WAV. The solo-page spec also intercepts /turn in the browser.
Run: uv run --no-sync python tests/e2e/serve.py
"""

import io
import wave
from typing import cast

import uvicorn
from pydantic import SecretStr

from saathi.app import create_app
from saathi.config import Settings
from saathi.gnani import GnaniClient

PORT = 8765
TRANSCRIPT = "gate number 2 third floor near the blue temple"  # synthetic address


def silent_wav() -> bytes:
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(24000)
        wav.writeframes(b"\x00\x00" * 2400)
    return buf.getvalue()


class FakeGnani:
    async def transcribe(self, audio: bytes, filename: str, language: str) -> str:
        return TRANSCRIPT

    async def synthesize(self, text: str, language: str, voice: str) -> bytes:
        return silent_wav()

    async def aclose(self) -> None:
        return None


class FakeTranslator:
    def translate(self, text: str, src: str, tgt: str) -> str:
        return f"<b>{tgt}</b> {text}"  # markup on purpose: the UI must show it as text


if __name__ == "__main__":
    app = create_app(
        Settings(gnani_api_key=SecretStr("dummy")),
        gnani=cast(GnaniClient, FakeGnani()),
        translator=FakeTranslator(),
    )
    uvicorn.run(app, host="127.0.0.1", port=PORT, log_level="warning")
