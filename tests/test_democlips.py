import asyncio
import io
import json
import wave
from pathlib import Path

import numpy as np
import pytest

from saathi.demo import load_demo_clips
from saathi.evaluation import noisemix
from saathi.evaluation.democlips import CLIP_SPECS, ClipSpec, build_clips, planned_calls
from saathi.languages import LANGUAGES


def _tone(rate: int, seconds: float = 2.0) -> bytes:
    t = np.arange(int(rate * seconds)) / rate
    pcm = (np.sin(2 * np.pi * 220 * t) * 8000).astype("<i2")
    out = io.BytesIO()
    with wave.open(out, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(pcm.tobytes())
    return out.getvalue()


class FakeGnani:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str]] = []

    async def synthesize(self, text: str, language_code: str, voice: str) -> bytes:
        self.calls.append((language_code, voice))
        return _tone(24000)


class NoLimit:
    async def acquire(self, calls: int = 1) -> None:
        return None


def _noise() -> noisemix.Samples:
    return noisemix.pink_noise(5.0, 1)


def test_specs_cover_three_pairs_and_use_supported_languages() -> None:
    assert {s.lang for s in CLIP_SPECS} == {"kn", "ta", "te"}
    assert all(s.lang in LANGUAGES for s in CLIP_SPECS)
    assert len({s.id for s in CLIP_SPECS}) == len(CLIP_SPECS)
    assert planned_calls() == len(CLIP_SPECS)


def test_build_writes_wavs_and_a_manifest_the_server_accepts(tmp_path: Path) -> None:
    gnani = FakeGnani()
    asyncio.run(build_clips(CLIP_SPECS, gnani, NoLimit(), _noise(), tmp_path))
    assert len(gnani.calls) == len(CLIP_SPECS)
    clips = load_demo_clips(tmp_path)
    assert set(clips) == {s.id for s in CLIP_SPECS}
    for spec in CLIP_SPECS:
        samples = noisemix.read_wav((tmp_path / f"{spec.id}.wav").read_bytes())
        assert len(samples) == 2 * noisemix.RATE
    assert json.loads((tmp_path / "manifest.json").read_text("utf-8"))["clips"][0]["lang"]


def test_a_clip_too_short_to_mix_is_refused(tmp_path: Path) -> None:
    class TooShort(FakeGnani):
        async def synthesize(self, text: str, language_code: str, voice: str) -> bytes:
            return _tone(24000, seconds=0.2)

    spec = ClipSpec("short", "kn", "x", "x", "x")
    with pytest.raises(noisemix.NoiseMixError):
        asyncio.run(build_clips((spec,), TooShort(), NoLimit(), _noise(), tmp_path))
    assert not (tmp_path / "manifest.json").exists()


def test_clip_whose_transcript_gives_no_chips_is_reported() -> None:
    from saathi.evaluation.democlips import clips_without_chips

    transcripts = {
        "kn-bakery": "ಮೂರನೇ ಕ್ರಾಸ್, ಐದನೇ ಮೇನ್, ಗೇಟ್ ನಂಬರ್ 4, ಬೇಕರಿ ಪಕ್ಕ",
        "ta-gate": "வணக்கம் நன்றி",  # nothing the extractor can use
    }
    assert clips_without_chips(transcripts) == ["ta-gate"]
