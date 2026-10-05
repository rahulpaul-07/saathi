import pytest

from saathi.pipeline import UnreliableTranslationError, run_turn
from saathi.translate import DegenerateTranslationError


class FakeGnani:
    def __init__(self, transcript: str = "namaskar") -> None:
        self.transcript = transcript
        self.synthesized: list[str] = []

    async def transcribe(self, audio: bytes, filename: str, language: str) -> str:
        return self.transcript

    async def synthesize(self, text: str, language: str, voice: str) -> bytes:
        self.synthesized.append(text)
        return b"wav"


class FixedTranslator:
    def __init__(self, output: str | Exception) -> None:
        self.output = output

    def translate(self, text: str, src: str, tgt: str) -> str:
        if isinstance(self.output, Exception):
            raise self.output
        return self.output


async def test_degenerate_error_skips_tts_and_carries_transcript() -> None:
    gnani = FakeGnani("garbled")
    translator = FixedTranslator(DegenerateTranslationError("hit the cap"))
    with pytest.raises(UnreliableTranslationError) as info:
        await run_turn(b"x", "bn", "kn", gnani, translator)  # type: ignore[arg-type]
    assert info.value.transcript == "garbled"
    assert gnani.synthesized == []


async def test_repeated_phrase_output_skips_tts() -> None:
    gnani = FakeGnani("garbled")
    translator = FixedTranslator("ಆ ಚಿಕ್ಕ ಆ ಚಿಕ್ಕ ಆ ಚಿಕ್ಕ ಆ ಚಿಕ್ಕ")
    with pytest.raises(UnreliableTranslationError):
        await run_turn(b"x", "bn", "kn", gnani, translator)  # type: ignore[arg-type]
    assert gnani.synthesized == []


async def test_normal_output_is_synthesized() -> None:
    gnani = FakeGnani()
    result = await run_turn(b"x", "bn", "kn", gnani, FixedTranslator("ಬೇಗ ಬೇಗ"))  # type: ignore[arg-type]
    assert result.translation == "ಬೇಗ ಬೇಗ"
    assert gnani.synthesized == ["ಬೇಗ ಬೇಗ"]
