"""One interpreter turn: speech in the source language -> speech in the target language."""

import asyncio
import time
from dataclasses import dataclass

from saathi.gnani import GnaniClient
from saathi.languages import LANGUAGES, SUPPORTED_PAIRS
from saathi.translate import Translator

AUDIO_FILENAME = "turn.wav"  # the browser always uploads WAV, so the name is fixed


class TurnInputError(ValueError):
    """The requested language pair is not supported."""


class NoSpeechError(Exception):
    """Prisma returned an empty transcript, so there is nothing to translate or speak."""


@dataclass(frozen=True)
class Timings:
    """Wall-clock milliseconds per stage. `total` spans the three stages, not the upload."""

    stt_ms: float
    translate_ms: float
    tts_ms: float
    total_ms: float


@dataclass(frozen=True)
class TurnResult:
    transcript: str
    translation: str
    audio: bytes
    timings: Timings


def validate_pair(src: str, tgt: str) -> None:
    if frozenset({src, tgt}) not in SUPPORTED_PAIRS:
        raise TurnInputError("unsupported language pair")


def _ms(start: float, end: float) -> float:
    return round((end - start) * 1000, 1)


async def run_turn(
    audio: bytes, src: str, tgt: str, gnani: GnaniClient, translator: Translator
) -> TurnResult:
    validate_pair(src, tgt)
    src_lang, tgt_lang = LANGUAGES[src], LANGUAGES[tgt]

    t0 = time.perf_counter()
    transcript = (await gnani.transcribe(audio, AUDIO_FILENAME, src_lang.gnani_code)).strip()
    t1 = time.perf_counter()
    if not transcript:
        raise NoSpeechError

    # The model is blocking and GPU-bound; keep it off the event loop.
    translation = await asyncio.to_thread(translator.translate, transcript, src, tgt)
    t2 = time.perf_counter()

    speech = await gnani.synthesize(translation, tgt_lang.gnani_code, tgt_lang.tts_voice)
    t3 = time.perf_counter()

    return TurnResult(
        transcript,
        translation,
        speech,
        Timings(_ms(t0, t1), _ms(t1, t2), _ms(t2, t3), _ms(t0, t3)),
    )
