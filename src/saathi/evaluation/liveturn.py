"""One real turn through the app's pipeline (spends exactly 3 Gnani calls).

The pair here (Kannada -> Bengali) is an evaluation fixture and only an example: the pipeline
treats every ordered language pair alike and no role is tied to either language.

The Kannada audio is made by Gnani TTS from a synthetic gold sentence, so no person's voice or
address is involved. By default nothing here prints transcript or translation text: the report shows
fact kinds, stage timings, byte lengths and the measured output level. `--show-text` also prints the
text, which is safe only because the sentence is a synthetic gold one.
"""

import argparse
import asyncio
import io
import math
import sys
import wave
from collections import Counter
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

import numpy as np
from pydantic import ValidationError

from saathi.config import get_settings
from saathi.evaluation.calls import (
    BudgetExceededError,
    CallLedger,
    MeteredGnani,
    SlidingWindowLimiter,
)
from saathi.evaluation.factscore import GoldUtterance, load_gold
from saathi.gnani import GnaniClient, GnaniError
from saathi.languages import LANGUAGES
from saathi.pipeline import NoSpeechError, Timings, UnreliableTranslationError, run_turn
from saathi.translate import RoutingTranslator, Translator

LEDGER_LABEL = "live_turn"
SOURCE_LANG = "kn"
TARGET_LANG = "bn"
DEFAULT_GOLD_ID = "g02"
CALLS_PLANNED = 3  # TTS kn (make the audio), STT kn, TTS bn
_TURN_CALLS = 2  # STT and TTS inside run_turn
_FULL_SCALE = 32768.0
_SILENT_DBFS = -120.0


class LiveTurnError(Exception):
    """The request cannot run (unknown sentence, budget); the message is safe to print."""


@dataclass(frozen=True)
class OutputLevel:
    rms_dbfs: float
    peak_dbfs: float
    seconds: float


@dataclass(frozen=True)
class LiveReport:
    fact_counts: dict[str, int]
    ambiguous_facts: int
    timings: Timings
    input_audio_bytes: int
    output_audio_bytes: int
    level: OutputLevel
    output_path: Path
    # Only printed with --show-text; the sentence is synthetic, so showing it exposes no address.
    transcript: str = ""
    translation: str = ""
    fact_lines: tuple[str, ...] = ()


def pick_sentence(gold_path: Path, gold_id: str) -> GoldUtterance:
    for utterance in load_gold(gold_path):
        if utterance.id == gold_id:
            if utterance.lang != SOURCE_LANG:
                raise LiveTurnError(f"gold sentence {gold_id} is not Kannada")
            return utterance
    raise LiveTurnError(f"no gold sentence with id {gold_id}")


def check_budget(ledger: CallLedger) -> None:
    if ledger.total + CALLS_PLANNED > ledger.cap:
        raise LiveTurnError(
            f"would pass the call cap: {ledger.total} spent + {CALLS_PLANNED} planned "
            f"> {ledger.cap}"
        )


def format_plan(utterance: GoldUtterance, ledger: CallLedger, target: str = TARGET_LANG) -> str:
    kn, bn = LANGUAGES[SOURCE_LANG], LANGUAGES[target]
    return "\n".join(
        [
            f"Live turn {SOURCE_LANG} -> {target}: exactly {CALLS_PLANNED} Gnani calls",
            f"  1. TTS  {kn.gnani_code} voice {kn.tts_voice}: speak the synthetic sentence "
            f"{utterance.id} (invented, not a real address; {len(utterance.text)} chars)",
            f"  2. STT  {kn.gnani_code}: transcribe that audio (run_turn)",
            f"     local: fact extraction, IndicTrans2 {SOURCE_LANG}->{target}",
            f"  3. TTS  {bn.gnani_code} voice {bn.tts_voice}: speak the translation, loudness "
            "normalized (run_turn)",
            f"Ledger '{LEDGER_LABEL}': {ledger.spent(LEDGER_LABEL)} spent so far; total "
            f"{ledger.total} spent + {CALLS_PLANNED} planned = {ledger.total + CALLS_PLANNED} "
            f"of cap {ledger.cap}",
        ]
    )


def measure_level(wav: bytes) -> OutputLevel:
    """RMS and peak of a 16-bit PCM WAV, in dBFS."""
    with wave.open(io.BytesIO(wav)) as source:
        if source.getsampwidth() != 2:
            raise LiveTurnError("output audio is not 16-bit PCM")
        rate, channels = source.getframerate(), source.getnchannels() or 1
        samples = np.frombuffer(source.readframes(source.getnframes()), dtype="<i2")
    if samples.size == 0:
        return OutputLevel(_SILENT_DBFS, _SILENT_DBFS, 0.0)
    floats = samples.astype(np.float64) / _FULL_SCALE
    rms = float(np.sqrt(np.mean(np.square(floats))))
    peak = float(np.abs(floats).max())

    def to_db(value: float) -> float:
        return 20.0 * math.log10(value) if value > 0 else _SILENT_DBFS

    return OutputLevel(
        round(to_db(rms), 1), round(to_db(peak), 1), round(samples.size / channels / rate, 2)
    )


def format_report(report: LiveReport) -> str:
    facts = ", ".join(f"{kind} x{n}" for kind, n in sorted(report.fact_counts.items())) or "none"
    t = report.timings
    return "\n".join(
        [
            f"facts found: {facts}; ambiguous: {report.ambiguous_facts}",
            f"timings ms: stt {t.stt_ms}, translate {t.translate_ms}, tts {t.tts_ms}, "
            f"total {t.total_ms}",
            f"audio bytes: input {report.input_audio_bytes}, output {report.output_audio_bytes}",
            f"output level: rms {report.level.rms_dbfs} dBFS, peak {report.level.peak_dbfs} dBFS, "
            f"{report.level.seconds} s",
            f"wrote {report.output_path.as_posix()}",
        ]
    )


GnaniFactory = Callable[[CallLedger], GnaniClient]
TranslatorFactory = Callable[[], Translator]


def _real_gnani(ledger: CallLedger) -> GnaniClient:
    return MeteredGnani(get_settings(), ledger, LEDGER_LABEL)


def _real_translator() -> Translator:
    return RoutingTranslator(num_beams=get_settings().translator_num_beams)


def main(
    argv: list[str] | None = None,
    *,
    root: Path,
    make_gnani: GnaniFactory = _real_gnani,
    make_translator: TranslatorFactory = _real_translator,
    limiter: SlidingWindowLimiter | None = None,
) -> int:
    """Command line entry. Exit codes: 0 ok, 1 the turn failed, 2 refused (nothing was sent)."""
    parser = argparse.ArgumentParser(
        description="One real Kannada -> Bengali turn (3 Gnani calls, spends credits)."
    )
    parser.add_argument("--dry-run", action="store_true", help="print the plan; send nothing")
    parser.add_argument("--yes", action="store_true", help="required to really spend the 3 calls")
    parser.add_argument(
        "--show-text",
        action="store_true",
        help="also print the transcript, translation and facts (synthetic sentence only)",
    )
    parser.add_argument(
        "--target",
        default=TARGET_LANG,
        help="listener language; each beta language is one 3-call smoke test (te gu ml mr pa ta)",
    )
    parser.add_argument("--gold-id", default=DEFAULT_GOLD_ID)
    parser.add_argument("--gold", type=Path, default=root / "eval" / "gold" / "directions.json")
    parser.add_argument(
        "--ledger", type=Path, default=root / "eval" / "state" / "gnani_ledger.json"
    )
    parser.add_argument("--out-dir", type=Path, default=root / "eval" / "audio" / "live")
    args = parser.parse_args(argv)

    try:
        if args.target not in LANGUAGES or args.target == SOURCE_LANG:
            raise LiveTurnError("unsupported target language")
        utterance = pick_sentence(args.gold, args.gold_id)
        ledger = CallLedger(args.ledger)
        print(format_plan(utterance, ledger, args.target))
        check_budget(ledger)
    except (LiveTurnError, OSError, ValueError, KeyError) as exc:
        print(f"refused: {exc}", file=sys.stderr)
        return 2
    if args.dry_run:
        print("Dry run: nothing was sent.")
        return 0
    if not args.yes:
        print("refused: pass --yes to spend these calls (or --dry-run)", file=sys.stderr)
        return 2

    async def go() -> LiveReport:
        try:
            gnani = make_gnani(ledger)
        except ValidationError as exc:
            raise LiveTurnError("Gnani settings are missing (see .env.example)") from exc
        try:
            return await run_live_turn(
                utterance,
                gnani,
                make_translator(),
                limiter or SlidingWindowLimiter(),
                ledger,
                args.out_dir,
                args.target,
            )
        finally:
            await gnani.aclose()

    try:
        report = asyncio.run(go())
    except (LiveTurnError, BudgetExceededError) as exc:
        print(f"refused: {exc}", file=sys.stderr)
        return 2
    except GnaniError as exc:
        print(
            f"stopped by Gnani error {exc.status}; ledger {ledger.total}/{ledger.cap}",
            file=sys.stderr,
        )
        return 1
    except (NoSpeechError, UnreliableTranslationError):
        print("the turn produced no usable result; no text is printed by design", file=sys.stderr)
        return 1
    print(format_report(report))
    if args.show_text:
        print(f"source sentence: {utterance.text}")
        print(f"kn transcript: {report.transcript}")
        print(f"{args.target} translation: {report.translation}")
        print("facts: " + ("; ".join(report.fact_lines) or "none"))
    print(f"ledger {ledger.total}/{ledger.cap}")
    return 0


async def run_live_turn(
    utterance: GoldUtterance,
    gnani: GnaniClient,
    translator: Translator,
    limiter: SlidingWindowLimiter,
    ledger: CallLedger,
    out_dir: Path,
    target: str = TARGET_LANG,
) -> LiveReport:
    """Make the Kannada audio, run the turn, save the target audio. The ledger is checked first."""
    check_budget(ledger)
    kn = LANGUAGES[SOURCE_LANG]
    await limiter.acquire(1)
    source_audio = await gnani.synthesize(utterance.text, kn.gnani_code, kn.tts_voice)
    await limiter.acquire(_TURN_CALLS)
    result = await run_turn(source_audio, SOURCE_LANG, target, gnani, translator)

    out_dir.mkdir(parents=True, exist_ok=True)
    output_path = out_dir / f"{utterance.id}_{SOURCE_LANG}_{target}.wav"
    output_path.write_bytes(result.audio)
    return LiveReport(
        fact_counts=dict(Counter(fact.kind for fact in result.facts if not fact.ambiguous)),
        ambiguous_facts=sum(1 for fact in result.facts if fact.ambiguous),
        timings=result.timings,
        input_audio_bytes=len(source_audio),
        output_audio_bytes=len(result.audio),
        level=measure_level(result.audio),
        output_path=output_path,
        transcript=result.transcript,
        translation=result.translation,
        fact_lines=tuple(
            f"{fact.kind}: {fact.value}" + (" (ambiguous)" if fact.ambiguous else "")
            for fact in result.facts
        ),
    )
