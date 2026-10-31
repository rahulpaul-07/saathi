"""One interpreter turn: speech in the source language -> speech in the target language."""

import asyncio
import logging
import time
from collections.abc import Callable
from dataclasses import dataclass

from saathi.facts import Fact, extract_facts
from saathi.gnani import GnaniClient, GnaniError
from saathi.guard import has_repeated_phrase
from saathi.landmarks import localize_landmarks
from saathi.languages import LANGUAGES
from saathi.masking import MaskedTranslation, translate_masked
from saathi.summary import fact_summary
from saathi.translate import DegenerateTranslationError, Translator

log = logging.getLogger(__name__)

AUDIO_FILENAME = "turn.wav"  # the browser always uploads WAV, so the name is fixed


class TurnInputError(ValueError):
    """The requested language pair is not supported."""


class RecordingRejectedError(Exception):
    """Prisma refused this audio (a 4xx other than rate limiting): re-recording is the fix, a
    retry of the same bytes cannot work."""


class NoSpeechError(Exception):
    """Prisma returned an empty transcript, so there is nothing to translate or speak."""


class UnreliableTranslationError(Exception):
    """The translation looks like a runaway loop; speaking it would be paid nonsense."""

    def __init__(self, transcript: str) -> None:
        super().__init__("unreliable translation")
        self.transcript = transcript


class TranslationUnavailableError(Exception):
    """The translator itself failed (model error, out of memory), as opposed to a bad output."""


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
    # Facts come from the source transcript, not the translation, so they survive a bad translation.
    facts: tuple[Fact, ...] = ()
    # True when every number and loanword placeholder came back exactly once and the output passed
    # the runaway guards. False means `translation` is the fact summary (or, with no facts, the
    # unmasked translation); the chips are right either way.
    verified: bool = True


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
    try:
        transcript = (await gnani.transcribe(audio, AUDIO_FILENAME, src_lang.gnani_code)).strip()
    except GnaniError as exc:
        if 400 <= exc.status < 500 and exc.status != 429:
            raise RecordingRejectedError from exc
        raise
    t1 = time.perf_counter()
    if not transcript:
        raise NoSpeechError

    # Facts come from the source text, so they survive whatever the translation does. The model is
    # blocking and GPU-bound; keep it off the event loop.
    facts = tuple(extract_facts(transcript, src))
    translated = await _in_thread(_translate_checked, translator, transcript, src, tgt, facts, True)
    facts = await _in_thread(localize_landmarks, facts, src, tgt, translator)
    translation, verified = translated.text, translated.verified
    if not verified:
        # A number or loanword placeholder was lost: do not speak a sentence that may carry a
        # wrong number. The facts alone, spelled from tables, are safe; with no facts, plain text.
        log.warning("masked translation %s->%s lost a placeholder; speaking the fallback", src, tgt)
        translation = fact_summary(facts, tgt)
        if not translation:
            plain = await _in_thread(
                _translate_checked, translator, transcript, src, tgt, facts, False
            )
            translation = plain.text
    t2 = time.perf_counter()

    speech = await gnani.synthesize(translation, tgt_lang.gnani_code, tgt_lang.tts_voice)
    t3 = time.perf_counter()

    return TurnResult(
        transcript,
        translation,
        speech,
        Timings(_ms(t0, t1), _ms(t1, t2), _ms(t2, t3), _ms(t0, t3)),
        facts=facts,
        verified=verified,
    )


async def _in_thread[**P, R](fn: Callable[P, R], *args: P.args, **kwargs: P.kwargs) -> R:
    """Run blocking translator work off the loop; a translator crash becomes a typed error.

    Only the exception type is logged: the message of a model error can quote the input text.
    """
    try:
        return await asyncio.to_thread(fn, *args, **kwargs)
    except UnreliableTranslationError:
        raise
    except Exception as exc:
        log.error("translator failed: %s", type(exc).__name__)
        raise TranslationUnavailableError from exc


def _translate_checked(
    translator: Translator,
    transcript: str,
    src: str,
    tgt: str,
    facts: tuple[Fact, ...],
    use_mask: bool,
) -> MaskedTranslation:
    """Blocking. Translate (masked or plain) and refuse a runaway loop."""
    try:
        if use_mask:
            result = translate_masked(translator, transcript, src, tgt, facts)
        else:
            text = translator.translate(transcript, src, tgt)
            result = MaskedTranslation(text, verified=False, raw=text)
    except DegenerateTranslationError as exc:
        log.warning(
            "degenerate translation %s->%s: %s (transcript %d chars)",
            src,
            tgt,
            "output cap hit",
            len(transcript),
        )
        raise UnreliableTranslationError(transcript) from exc
    # The raw output is checked, not the restored text: restoring repeats words like "cross".
    if has_repeated_phrase(result.raw):
        log.warning(
            "degenerate translation %s->%s: %s (output %d chars, transcript %d chars)",
            src,
            tgt,
            "repeated phrase",
            len(result.raw),
            len(transcript),
        )
        raise UnreliableTranslationError(transcript)
    return result
