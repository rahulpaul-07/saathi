from typing import cast

import pytest
from pydantic import SecretStr

from saathi.app import create_app, warm_up_tts
from saathi.config import Settings
from saathi.gnani import GnaniClient, GnaniError


class RecordingGnani:
    def __init__(self, error: GnaniError | None = None) -> None:
        self.error = error
        self.calls: list[tuple[str, str, str]] = []

    async def synthesize(self, text: str, language: str, voice: str) -> bytes:
        self.calls.append((text, language, voice))
        if self.error:
            raise self.error
        return b"RIFF"

    async def aclose(self) -> None:
        return None


class IdleTranslator:
    def translate(self, text: str, src: str, tgt: str) -> str:
        return text


async def start_app(gnani: RecordingGnani, *, warm: bool) -> None:
    settings = Settings(gnani_api_key=SecretStr("k"), warm_tts=warm)
    app = create_app(settings, cast(GnaniClient, gnani), IdleTranslator())
    async with app.router.lifespan_context(app):
        pass


def test_warm_up_is_off_by_default() -> None:
    assert Settings(gnani_api_key=SecretStr("k")).warm_tts is False


async def test_enabled_warm_up_makes_exactly_one_short_tts_call_at_startup() -> None:
    gnani = RecordingGnani()
    await start_app(gnani, warm=True)
    assert len(gnani.calls) == 1
    text, language, _ = gnani.calls[0]
    assert len(text) < 20 and language == "en-IN"


async def test_disabled_warm_up_makes_no_call() -> None:
    gnani = RecordingGnani()
    await start_app(gnani, warm=False)
    assert gnani.calls == []


async def test_a_failed_warm_up_is_logged_and_does_not_stop_startup(
    caplog: pytest.LogCaptureFixture,
) -> None:
    gnani = RecordingGnani(GnaniError("down", 504))
    await start_app(gnani, warm=True)
    assert "warm-up failed (status 504)" in caplog.text


async def test_warm_up_function_swallows_gnani_errors() -> None:
    await warm_up_tts(cast(GnaniClient, RecordingGnani(GnaniError("x"))))
