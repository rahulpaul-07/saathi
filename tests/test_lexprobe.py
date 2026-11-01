import asyncio
import io
import json
import wave
from pathlib import Path

import pytest

from saathi.evaluation.lexprobe import (
    LANGS,
    RECHECK_MAX_CALLS,
    ROUND2_LANGS,
    ROUND2_MAX_CALLS,
    ProbeBudgetError,
    ProbeSentence,
    all_sentences,
    planned_calls,
    probe_sentences,
    run_probe,
    ta_ordinal_5_recheck,
)
from saathi.gnani import GnaniError
from saathi.languages import LANGUAGES


def _wav() -> bytes:
    out = io.BytesIO()
    with wave.open(out, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(24000)
        w.writeframes(b"\x00\x00" * 2400)
    return out.getvalue()


class FakeGnani:
    def __init__(self) -> None:
        self.spoken: list[str] = []
        self.heard: list[str] = []

    async def synthesize(self, text: str, language_code: str, voice: str) -> bytes:
        self.spoken.append(text)
        return _wav()

    async def transcribe(self, audio: bytes, filename: str, language_code: str) -> str:
        self.heard.append(filename)
        return f"  heard {filename}  "


class NoLimit:
    async def acquire(self, calls: int = 1) -> None:
        return None


@pytest.mark.parametrize("lang", LANGS)
def test_eight_sentences_cover_every_number_1_to_20_as_cardinal_and_ordinal(lang: str) -> None:
    sentences = probe_sentences(lang)
    assert len(sentences) == 8
    for ordinal in (False, True):
        values = sorted(
            item.value for s in sentences for item in s.items if item.ordinal is ordinal
        )
        assert values == list(range(1, 21))


@pytest.mark.parametrize("lang", LANGS)
def test_sentences_cover_all_six_triggers_and_four_landmark_cues(lang: str) -> None:
    sentences = probe_sentences(lang)
    assert {item.kind for s in sentences for item in s.items} == {
        "gate", "cross", "main", "floor", "block", "flat"
    }  # fmt: skip
    assert {s.cue for s in sentences} == {"", "opposite", "near", "next_to", "behind"}


@pytest.mark.parametrize("lang", ROUND2_LANGS)
def test_round2_languages_have_the_same_coverage(lang: str) -> None:
    sentences = probe_sentences(lang)
    assert len(sentences) == 8
    for ordinal in (False, True):
        values = sorted(
            item.value for s in sentences for item in s.items if item.ordinal is ordinal
        )
        assert values == list(range(1, 21))
    assert {s.cue for s in sentences} == {"", "opposite", "near", "next_to", "behind"}


def test_round2_is_64_calls_within_its_limit_and_uses_supported_languages() -> None:
    sentences = all_sentences(ROUND2_LANGS)
    assert all(s.lang in LANGUAGES for s in sentences)
    assert len({s.id for s in sentences}) == len({s.text for s in sentences}) == 32
    assert planned_calls(ROUND2_LANGS) == 64 < ROUND2_MAX_CALLS


def test_ordinal_5_recheck_is_one_short_tamil_sentence_within_its_two_call_cap() -> None:
    sentence = ta_ordinal_5_recheck()
    assert sentence.lang == "ta"
    assert sentence.text == "ஐந்தாவது கிராஸ்"
    assert 2 * 1 == RECHECK_MAX_CALLS


def test_sentences_use_supported_languages_and_are_unique() -> None:
    sentences = all_sentences()
    assert all(s.lang in LANGUAGES for s in sentences)
    assert len({s.id for s in sentences}) == len({s.text for s in sentences}) == 16
    assert planned_calls() == 32


def test_run_probe_makes_one_tts_and_one_stt_per_sentence_and_saves_transcripts(
    tmp_path: Path,
) -> None:
    gnani = FakeGnani()
    sentences: tuple[ProbeSentence, ...] = probe_sentences("ta")[:2]
    out = tmp_path / "state" / "probe.json"
    transcripts = asyncio.run(run_probe(sentences, gnani, NoLimit(), out))
    assert gnani.spoken == [s.text for s in sentences]
    assert transcripts == {s.id: f"heard {s.id}.wav" for s in sentences}
    assert json.loads(out.read_text("utf-8")) == transcripts


class Flaky(FakeGnani):
    """Raises a GnaniError with `status` on the TTS calls whose 1-based numbers are in `fail_on`."""

    def __init__(self, fail_on: set[int], status: int = 0) -> None:
        super().__init__()
        self.fail_on, self.status, self.tts_calls = fail_on, status, 0

    async def synthesize(self, text: str, language_code: str, voice: str) -> bytes:
        self.tts_calls += 1
        if self.tts_calls in self.fail_on:
            raise GnaniError("down", self.status)
        return await super().synthesize(text, language_code, voice)


def _run(
    gnani: FakeGnani, tmp_path: Path, naps: list[float], max_calls: int = 32
) -> dict[str, str]:
    async def nap(seconds: float) -> None:
        naps.append(seconds)

    sentences = probe_sentences("ta")[:2]
    return asyncio.run(
        run_probe(sentences, gnani, NoLimit(), tmp_path / "p.json", max_calls=max_calls, sleep=nap)
    )


def test_a_transport_error_is_retried_once_after_five_seconds(tmp_path: Path) -> None:
    naps: list[float] = []
    gnani = Flaky({1})
    assert len(_run(gnani, tmp_path, naps)) == 2
    assert naps == [5.0]
    assert gnani.tts_calls == 3  # the failed call, its retry and the second sentence


def test_a_second_transport_error_stops_the_run(tmp_path: Path) -> None:
    naps: list[float] = []
    gnani = Flaky({1, 2})
    with pytest.raises(GnaniError):
        _run(gnani, tmp_path, naps)
    assert naps == [5.0] and gnani.tts_calls == 2
    assert not (tmp_path / "p.json").exists()


def test_an_http_error_status_is_not_retried(tmp_path: Path) -> None:
    naps: list[float] = []
    gnani = Flaky({1}, status=429)
    with pytest.raises(GnaniError):
        _run(gnani, tmp_path, naps)
    assert naps == [] and gnani.tts_calls == 1


def test_retries_count_against_the_call_limit(tmp_path: Path) -> None:
    naps: list[float] = []
    # 2 sentences need 4 calls; one retry makes 5, so a limit of 4 stops before the last call.
    with pytest.raises(ProbeBudgetError):
        _run(Flaky({1}), tmp_path, naps, max_calls=4)


def test_a_failure_keeps_finished_sentences_and_a_rerun_does_only_the_rest(
    tmp_path: Path,
) -> None:
    class FailsOnSecond(FakeGnani):
        async def synthesize(self, text: str, language_code: str, voice: str) -> bytes:
            if len(self.spoken) == 1:
                raise RuntimeError("tts timed out")
            return await super().synthesize(text, language_code, voice)

    sentences = probe_sentences("te")[:3]
    out = tmp_path / "probe.json"
    with pytest.raises(RuntimeError):
        asyncio.run(run_probe(sentences, FailsOnSecond(), NoLimit(), out))
    assert list(json.loads(out.read_text("utf-8"))) == [sentences[0].id]

    rerun = FakeGnani()
    transcripts = asyncio.run(run_probe(sentences, rerun, NoLimit(), out))
    assert rerun.spoken == [s.text for s in sentences[1:]]
    assert set(transcripts) == {s.id for s in sentences}
