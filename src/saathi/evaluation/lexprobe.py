"""Probe sentences for building a language's number and trigger lexicon from real STT output.

Each sentence is generated from word tables, so the intended value of every position is known.
The words below are written by Claude from general knowledge of Tamil and Telugu; they only decide
what the TTS speaks. What goes into the lexicon is the spelling the STT writes back, never these
strings. Entries built this way are "machine-verified, not native-reviewed".
"""

import asyncio
import json
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from saathi.evaluation.wavtools import resample_to_16k
from saathi.facts.types import FactKind
from saathi.gnani import GnaniError
from saathi.languages import LANGUAGES

LEDGER_LABEL = "lexicon-probe"
MAX_CALLS = 32
RETRY_WAIT_S = 5.0
LANGS = ("ta", "te")


@dataclass(frozen=True)
class ProbeItem:
    kind: FactKind
    value: int
    ordinal: bool  # "second cross" (True) or "gate number 2" (False)


@dataclass(frozen=True)
class ProbeSentence:
    id: str
    lang: str
    text: str
    items: tuple[ProbeItem, ...]
    cue: str  # landmark cue spoken at the end, "" for none


@dataclass(frozen=True)
class _Words:
    cardinals: tuple[str, ...]  # 1-20
    ordinals: tuple[str, ...]  # 1-20
    triggers: dict[FactKind, str]
    filler: str
    landmark: str
    cues: dict[str, str]  # opposite, near, next_to, behind: the postposition after the name
    alt_ordinals: dict[int, str]  # second spelling of some ordinals, used once (6-10)


_TA = _Words(
    cardinals=tuple(
        "ஒன்று இரண்டு மூன்று நான்கு ஐந்து ஆறு ஏழு எட்டு ஒன்பது பத்து பதினொன்று பன்னிரண்டு "
        "பதின்மூன்று பதினான்கு பதினைந்து பதினாறு பதினேழு பதினெட்டு பத்தொன்பது இருபது".split()
    ),
    ordinals=tuple(
        "முதல் இரண்டாவது மூன்றாவது நான்காவது ஐந்தாவது ஆறாவது ஏழாவது எட்டாவது ஒன்பதாவது "
        "பத்தாவது பதினொன்றாவது பன்னிரண்டாவது பதின்மூன்றாவது பதினான்காவது பதினைந்தாவது "
        "பதினாறாவது பதினேழாவது பதினெட்டாவது பத்தொன்பதாவது இருபதாவது".split()
    ),
    triggers={
        "gate": "கேட்", "cross": "கிராஸ்", "main": "மெயின்",
        "floor": "ஃப்ளோர்", "block": "பிளாக்", "flat": "பிளாட்",
    },  # fmt: skip
    filler="நம்பர்",
    landmark="பேக்கரி",
    cues={"opposite": "எதிரில்", "near": "அருகில்", "next_to": "பக்கத்தில்", "behind": "பின்னால்"},
    alt_ordinals={},
)

_TE = _Words(
    cardinals=tuple(
        "ఒకటి రెండు మూడు నాలుగు ఐదు ఆరు ఏడు ఎనిమిది తొమ్మిది పది పదకొండు పన్నెండు పదమూడు "
        "పద్నాలుగు పదిహేను పదహారు పదిహేడు పద్దెనిమిది పంతొమ్మిది ఇరవై".split()
    ),
    ordinals=tuple(
        "మొదటి రెండో మూడో నాలుగో ఐదో ఆరో ఏడో ఎనిమిదో తొమ్మిదో పదో పదకొండో పన్నెండో పదమూడో "
        "పద్నాలుగో పదిహేనో పదహారో పదిహేడో పద్దెనిమిదో పంతొమ్మిదో ఇరవయ్యో".split()
    ),
    triggers={
        "gate": "గేట్", "cross": "క్రాస్", "main": "మెయిన్",
        "floor": "ఫ్లోర్", "block": "బ్లాక్", "flat": "ఫ్లాట్",
    },  # fmt: skip
    filler="నంబర్",
    landmark="బేకరీ",
    cues={"opposite": "ఎదురుగా", "near": "దగ్గర", "next_to": "పక్కన", "behind": "వెనుక"},
    alt_ordinals={6: "ఆరవ", 7: "ఏడవ", 8: "ఎనిమిదవ", 9: "తొమ్మిదవ", 10: "పదవ"},
)

_WORDS = {"ta": _TA, "te": _TE}

# (kind, ordinal, first value, cue, use the alternative ordinal spellings)
_PLAN: tuple[tuple[FactKind, bool, int, str, bool], ...] = (
    ("gate", False, 1, "", False),
    ("flat", False, 6, "", False),
    ("floor", False, 11, "", False),
    ("block", False, 16, "", False),
    ("cross", True, 1, "opposite", False),
    ("floor", True, 6, "near", True),
    ("main", True, 11, "next_to", False),
    ("cross", True, 16, "behind", False),
)
_VALUES_PER_SENTENCE = 5


def _sentence(index: int, lang: str) -> ProbeSentence:
    kind, ordinal, first, cue, alt = _PLAN[index]
    words = _WORDS[lang]
    items = tuple(
        ProbeItem(kind, value, ordinal) for value in range(first, first + _VALUES_PER_SENTENCE)
    )
    parts: list[str] = []
    for item in items:
        trigger = words.triggers[item.kind]
        if item.ordinal:
            word = words.alt_ordinals.get(item.value) if alt else None
            parts.append(f"{word or words.ordinals[item.value - 1]} {trigger}")
        else:
            parts.append(f"{trigger} {words.filler} {words.cardinals[item.value - 1]}")
    if cue:
        parts.append(f"{words.landmark} {words.cues[cue]}")
    return ProbeSentence(f"{lang}-probe-{index + 1}", lang, ", ".join(parts), items, cue)


def probe_sentences(lang: str) -> tuple[ProbeSentence, ...]:
    return tuple(_sentence(index, lang) for index in range(len(_PLAN)))


def all_sentences() -> tuple[ProbeSentence, ...]:
    return tuple(s for lang in LANGS for s in probe_sentences(lang))


RECHECK_MAX_CALLS = 2


def ta_ordinal_5_recheck() -> ProbeSentence:
    """The one Tamil ordinal the full probe lost: the STT dropped "ஐந்தாவது கிராஸ்" from ta-probe-5."""
    words = _WORDS["ta"]
    text = f"{words.ordinals[4]} {words.triggers['cross']}"
    return ProbeSentence("ta-ordinal-5", "ta", text, (ProbeItem("cross", 5, True),), "")


def planned_calls() -> int:
    """One TTS and one STT call per sentence."""
    return 2 * len(all_sentences())


class Gnani(Protocol):
    async def synthesize(self, text: str, language_code: str, voice: str) -> bytes: ...
    async def transcribe(self, audio: bytes, filename: str, language_code: str) -> str: ...


class Limiter(Protocol):
    async def acquire(self, calls: int = 1) -> None: ...


class ProbeBudgetError(Exception):
    """The run would exceed its call limit; retries count against it."""


async def _call_with_retry[T](
    make_call: Callable[[], Awaitable[T]],
    attempts: list[int],
    max_calls: int,
    sleep: Callable[[float], Awaitable[None]],
) -> T:
    """One retry after RETRY_WAIT_S on a transport error or timeout (GnaniError status 0).

    Every attempt, retries included, counts against `max_calls`. An HTTP error status is not
    retried.
    """
    for attempt in (1, 2):
        if len(attempts) >= max_calls:
            raise ProbeBudgetError(f"call limit of {max_calls} reached")
        attempts.append(attempt)
        try:
            return await make_call()
        except GnaniError as exc:
            if exc.status != 0 or attempt == 2:
                raise
            await sleep(RETRY_WAIT_S)
    raise AssertionError("unreachable")


async def _probe_one(
    sentence: ProbeSentence,
    gnani: Gnani,
    limiter: Limiter,
    attempts: list[int],
    max_calls: int,
    sleep: Callable[[float], Awaitable[None]],
) -> str:
    voice = LANGUAGES[sentence.lang]

    async def speak() -> bytes:
        await limiter.acquire(1)
        return await gnani.synthesize(sentence.text, voice.gnani_code, voice.tts_voice)

    wav = resample_to_16k(await _call_with_retry(speak, attempts, max_calls, sleep))

    async def listen() -> str:
        await limiter.acquire(1)
        return await gnani.transcribe(wav, f"{sentence.id}.wav", voice.gnani_code)

    return await _call_with_retry(listen, attempts, max_calls, sleep)


async def run_probe(
    sentences: tuple[ProbeSentence, ...],
    gnani: Gnani,
    limiter: Limiter,
    out: Path,
    max_calls: int = MAX_CALLS,
    sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
) -> dict[str, str]:
    """TTS then STT for each sentence; returns {id: transcript}.

    `out` is rewritten after every sentence and read back on the next run, so a failure part-way
    keeps the calls already paid for and a rerun only does the rest. The sentences are synthetic
    number lists with no address, so keeping the transcripts as the evidence behind the lexicon
    does not store anything personal.
    """
    transcripts: dict[str, str] = json.loads(out.read_text("utf-8")) if out.exists() else {}
    attempts: list[int] = []
    for sentence in sentences:
        if sentence.id in transcripts:
            continue
        text = await _probe_one(sentence, gnani, limiter, attempts, max_calls, sleep)
        transcripts[sentence.id] = text.strip()
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(transcripts, ensure_ascii=False, indent=2), encoding="utf-8")
    return transcripts
