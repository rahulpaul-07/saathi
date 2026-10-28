import itertools

import pytest

from saathi.languages import LANGUAGES
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


class EchoTranslator:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str]] = []

    def translate(self, text: str, src: str, tgt: str) -> str:
        self.calls.append((src, tgt))
        return f"{text} to {tgt}"


async def test_every_ordered_language_pair_runs_a_turn() -> None:
    pairs = list(itertools.permutations(LANGUAGES, 2))
    assert len(pairs) == 90
    translator = EchoTranslator()
    for src, tgt in pairs:
        gnani = FakeGnani("gate number 2")
        result = await run_turn(b"x", src, tgt, gnani, translator)  # type: ignore[arg-type]
        assert result.translation == f"gate number 2 to {tgt}"
        assert gnani.synthesized == [result.translation]
        assert [(f.kind, f.value) for f in result.facts] == [("gate", "2")]
    assert translator.calls == pairs


async def test_result_carries_facts_from_the_source_transcript_and_is_verified() -> None:
    gnani = FakeGnani("gate number 2")
    result = await run_turn(b"x", "en", "kn", gnani, FixedTranslator("ಬೇಗ ಬೇಗ"))  # type: ignore[arg-type]
    assert [(f.kind, f.value) for f in result.facts] == [("gate", "2")]
    assert result.verified is True
