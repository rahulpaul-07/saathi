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
from saathi.demobundle import BUNDLE_NAME, BUNDLE_VERSION, clip_digest
from saathi.gnani import GnaniClient
from saathi.languages import LANGUAGES

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))  # tests/ for the shared wavs.py
from wavs import require_speech_audio  # noqa: E402

PORT = 8765
DEMO_PORT = 8766  # `--demo`: demo input mode on, clips from a temp folder
JOURNEY_PORT = 8767  # `--journey`: script-aware fake translator, every language alternates the gate
REPLAY_PORT = 8768  # `--replay`: public mode, guided demo replayed from a stored bundle
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
    def __init__(self, *, alternate_all: bool = False) -> None:
        self._alternate_all = alternate_all
        self._calls: dict[str, int] = {}

    async def transcribe(self, audio: bytes, filename: str, language: str) -> str:
        require_speech_audio(audio)
        if self._alternate_all or language == CHANGING_LANGUAGE:
            self._calls[language] = self._calls.get(language, 0) + 1
            if self._calls[language] % 2 == 0:
                return TRANSCRIPT.replace("gate number 2", "gate number 4")
        return TRANSCRIPT

    async def synthesize(self, text: str, language: str, voice: str) -> bytes:
        return silent_wav()

    async def aclose(self) -> None:
        return None


class FakeTranslator:
    def translate(self, text: str, src: str, tgt: str) -> str:
        return f"<b>{tgt}</b> {text}"  # markup on purpose: the UI must show it as text


# One short word per script so a landmark rendering passes the listener-script check, the way a real
# translation would. Synthetic; the journey specs only need the script, not the meaning.
SCRIPT_WORDS: dict[str, str] = {
    "bn": "মন্দির",
    "hi": "मंदिर",
    "mr": "मंदिर",
    "kn": "ದೇವಾಲಯ",
    "te": "దేవాలయం",
    "gu": "મંદિર",
    "ml": "ക്ഷേത്രം",
    "pa": "ਮੰਦਰ",
    "ta": "கோவில்",
}


class ScriptFakeTranslator:
    """Writes the target script: a bare landmark becomes one word, a sentence keeps its slots."""

    def translate(self, text: str, src: str, tgt: str) -> str:
        word = SCRIPT_WORDS.get(tgt)
        if word is None:
            return text
        return f"{word} {text}" if "#" in text else word


def tone_clip() -> bytes:
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(16000)
        wav.writeframes(struct.pack("<h", 3000) * 32000)
    return buf.getvalue()


class NoGnani:
    """The replay server must never reach Gnani: any use fails the request loudly."""

    def __getattr__(self, name: str) -> object:
        raise AssertionError(f"Gnani was touched: {name}")


def replay_bundle_dir(clip: bytes) -> Path:
    """A bundle holding one stored turn, kn speaker -> hi listener, for the tone clip."""
    directory = Path(tempfile.mkdtemp(prefix="saathi-e2e-bundle-"))
    (directory / "turn.wav").write_bytes(silent_wav())
    turn = {
        "clip_sha256": clip_digest(clip),
        "src": "kn",
        "tgt": "hi",
        "transcript": TRANSCRIPT,
        "translation": "stored translation",
        "verified": True,
        "audio": "turn.wav",
    }
    body = {"version": BUNDLE_VERSION, "turns": [turn]}
    (directory / BUNDLE_NAME).write_text(json.dumps(body), encoding="utf-8")
    return directory


def demo_clips_dir() -> Path:
    """A throwaway clip folder: one synthetic 2 s tone clip per supported language."""
    directory = Path(tempfile.mkdtemp(prefix="saathi-e2e-demo-"))
    tone = tone_clip()
    clips = [
        {
            "id": f"clip-{code}",
            "lang": code,
            "label": f"Sample {code}",
            "label_local": "ಮಾದರಿ ಕ್ಲಿಪ್" if code == "kn" else "",
        }
        for code in LANGUAGES
    ]
    for clip in clips:
        (directory / f"{clip['id']}.wav").write_bytes(tone)
    (directory / "manifest.json").write_text(json.dumps({"clips": clips}), encoding="utf-8")
    return directory


if __name__ == "__main__":
    demo = "--demo" in sys.argv
    journey = "--journey" in sys.argv
    replay = "--replay" in sys.argv
    # Every spec shares one client IP and one server, so the production per-minute limits would make
    # a test fail depending on how fast the suite ran. The limits themselves are covered by pytest.
    open_limit = 10_000
    settings = Settings(
        gnani_api_key=SecretStr("dummy"),
        room_rate_limit_per_minute=open_limit,
        turn_rate_limit_per_minute=open_limit,
        reply_rate_limit_per_minute=open_limit,
    )
    if demo:
        settings = Settings(
            gnani_api_key=SecretStr("dummy"),
            room_rate_limit_per_minute=open_limit,
            turn_rate_limit_per_minute=open_limit,
            reply_rate_limit_per_minute=open_limit,
            demo_input=True,
            demo_clips_dir=demo_clips_dir(),
        )
    gnani: object = FakeGnani(alternate_all=journey)
    if replay:
        # Public mode with a stored bundle: the guided demo replays, so Gnani must stay untouched.
        gnani = NoGnani()
        settings = Settings(
            gnani_api_key=SecretStr("dummy"),
            public_mode=True,
            budget_file=Path(tempfile.mkdtemp(prefix="saathi-e2e-budget-")) / "budget.json",
            demo_bundle_dir=replay_bundle_dir(tone_clip()),
            demo_clips_dir=demo_clips_dir(),
            room_rate_limit_per_minute=open_limit,
            turn_rate_limit_per_minute=open_limit,
            reply_rate_limit_per_minute=open_limit,
        )
    app = create_app(
        settings,
        gnani=cast(GnaniClient, gnani),
        translator=ScriptFakeTranslator() if journey else FakeTranslator(),
    )
    port = REPLAY_PORT if replay else JOURNEY_PORT if journey else DEMO_PORT if demo else PORT
    uvicorn.run(app, host="127.0.0.1", port=port, log_level="warning")
