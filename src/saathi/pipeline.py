"""One interpreter turn: speech in the source language -> speech in the target language."""

import asyncio
import logging
import time
from dataclasses import dataclass

from saathi.gnani import GnaniClient
from saathi.guard import has_repeated_phrase
from saathi.languages import LANGUAGES
from saathi.translate import DegenerateTranslationError, Translator

log = logging.getLogger(__name__)

AUDIO_FILENAME = "turn.wav"  # the browser always uploads WAV, so the name is fixed


class TurnInputError(ValueError):
    """The requested language pair is not supported."""


class NoSpeechError(Exception):
    """Prisma returned an empty transcript, so there is nothing to translate or speak."""


class UnreliableTranslationError(Exception):
    """The translation looks like a runaway loop; speaking it would be paid nonsense."""

    def __init__(self, transcript: str) -> None:
        super().__init__("unreliable translation")
        self.transcript = transcript


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
    if src not in LANGUAGES or tgt not in LANGUAGES or src == tgt:
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
    try:
        translation = await asyncio.to_thread(translator.translate, transcript, src, tgt)
    except DegenerateTranslationError as exc:
        log.warning(
            "degenerate translation %s->%s: %s (transcript %d chars)",
            src,
            tgt,
            "output cap hit",
            len(transcript),
        )
        raise UnreliableTranslationError(transcript) from exc
    if has_repeated_phrase(translation):
        log.warning(
            "degenerate translation %s->%s: %s (output %d chars, transcript %d chars)",
            src,
            tgt,
            "repeated phrase",
            len(translation),
            len(transcript),
        )
        raise UnreliableTranslationError(transcript)
    t2 = time.perf_counter()

    speech = await gnani.synthesize(translation, tgt_lang.gnani_code, tgt_lang.tts_voice)
    t3 = time.perf_counter()

    return TurnResult(
        transcript,
        translation,
        speech,
        Timings(_ms(t0, t1), _ms(t1, t2), _ms(t2, t3), _ms(t0, t3)),
    )
