"""The latency study: 20 full turns, 2 Gnani calls each (STT, TTS) = 40 calls.

Source audio is not generated here (that would add calls): it is 16 kHz mono WAV files already in a
directory, in the source language, none of them a real person's address. The translator is warmed up
locally with one throwaway call first, so the 20 measured turns include no model load. Output is
timings only; no transcript or translation text is printed or saved.

  uv run --no-sync python scripts/latency_study.py --dry-run
  uv run --no-sync python scripts/latency_study.py --yes     (only while the author is awake)
"""

import argparse
import asyncio
import json
import sys
from collections.abc import Callable
from dataclasses import asdict
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from saathi.config import get_settings
from saathi.evaluation.calls import (
    CALLS_PER_TURN,
    BudgetExceededError,
    CallLedger,
    MeteredGnani,
    SlidingWindowLimiter,
)
from saathi.evaluation.power import PowerError, PowerGuard
from saathi.evaluation.turns import TurnOutcome, measure_turn, summarize_latency
from saathi.gnani import GnaniClient
from saathi.languages import LANGUAGES
from saathi.pipeline import Timings
from saathi.translate import RoutingTranslator, Translator

LEDGER_LABEL = "latency"
TURNS = 20
CALLS_PLANNED = TURNS * CALLS_PER_TURN  # 40
DEFAULT_SRC, DEFAULT_TGT = "bn", "kn"  # an example pair, not a statement about who speaks what
WARMUP_TEXT = "namaskar"


class LatencyError(Exception):
    """The study cannot run; the message is safe to print."""


def find_audio(audio_dir: Path) -> list[Path]:
    """WAV files to cycle through; the study needs at least one and uses 20 turns."""
    files = sorted(audio_dir.glob("*.wav")) if audio_dir.is_dir() else []
    if not files:
        raise LatencyError(f"no .wav files in {audio_dir.as_posix()}")
    return files


def check_budget(ledger: CallLedger) -> None:
    if ledger.total + CALLS_PLANNED > ledger.cap:
        raise LatencyError(
            f"would pass the call cap: {ledger.total} spent + {CALLS_PLANNED} planned "
            f"> {ledger.cap}"
        )


def format_plan(src: str, tgt: str, files: list[Path], ledger: CallLedger) -> str:
    return "\n".join(
        [
            f"Latency study {src} -> {tgt}: {TURNS} turns x {CALLS_PER_TURN} calls = "
            f"{CALLS_PLANNED} Gnani calls (STT then TTS per turn)",
            f"  audio: {len(files)} file(s) cycled over {TURNS} turns, no TTS needed to make them",
            "  local: one throwaway translation first so no model load is timed",
            f"Ledger '{LEDGER_LABEL}': {ledger.spent(LEDGER_LABEL)} spent so far; total "
            f"{ledger.total} spent + {CALLS_PLANNED} planned = {ledger.total + CALLS_PLANNED} "
            f"of cap {ledger.cap}",
        ]
    )


async def run_study(
    files: list[Path],
    src: str,
    tgt: str,
    gnani: GnaniClient,
    translator: Translator,
    limiter: SlidingWindowLimiter,
    guard: PowerGuard,
) -> dict[str, Any]:
    translator.translate(WARMUP_TEXT, src, tgt)
    outcomes: list[TurnOutcome] = []
    for index in range(TURNS):
        guard.check()
        audio = files[index % len(files)].read_bytes()
        outcomes.append(await measure_turn(audio, src, tgt, gnani, translator, limiter))
    samples: list[Timings] = [o.timings for o in outcomes if o.timings is not None]
    return {
        "pair": f"{src}->{tgt}",
        "power": guard.state.value,
        "turns": TURNS,
        "clean_samples": len(samples),
        "retried_or_failed": sum(1 for o in outcomes if o.timings is None),
        "failures": [o.failure for o in outcomes if o.failure],
        "stages": {k: asdict(v) for k, v in summarize_latency(samples).items()} if samples else {},
        "note": "clean synthetic or consented audio; p95 is close to the maximum at this n",
    }


def main(
    argv: list[str] | None = None,
    *,
    root: Path,
    make_gnani: Callable[[CallLedger], GnaniClient] | None = None,
    make_translator: Callable[[], Translator] | None = None,
    limiter: SlidingWindowLimiter | None = None,
    guard_factory: Callable[[bool], PowerGuard] | None = None,
) -> int:
    """Exit codes: 0 ok, 1 the study ran but produced no clean sample, 2 refused (nothing sent)."""
    parser = argparse.ArgumentParser(description="Latency study: 20 turns, 40 Gnani calls.")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--yes", action="store_true", help="required to really spend the calls")
    parser.add_argument("--allow-battery", action="store_true", help="tag results as battery")
    parser.add_argument("--src", default=DEFAULT_SRC)
    parser.add_argument("--tgt", default=DEFAULT_TGT)
    parser.add_argument("--audio-dir", type=Path, default=root / "eval" / "audio" / "latency")
    parser.add_argument(
        "--ledger", type=Path, default=root / "eval" / "state" / "gnani_ledger.json"
    )
    parser.add_argument(
        "--out", type=Path, default=root / "eval" / "results" / "latency.json"
    )
    args = parser.parse_args(argv)

    try:
        if args.src not in LANGUAGES or args.tgt not in LANGUAGES or args.src == args.tgt:
            raise LatencyError("unsupported language pair")
        files = find_audio(args.audio_dir)
        ledger = CallLedger(args.ledger)
        print(format_plan(args.src, args.tgt, files, ledger))
        check_budget(ledger)
    except (LatencyError, OSError, ValueError) as exc:
        print(f"refused: {exc}", file=sys.stderr)
        return 2
    if args.dry_run:
        print("Dry run: nothing was sent.")
        return 0
    if not args.yes:
        print("refused: pass --yes to spend these calls (or --dry-run)", file=sys.stderr)
        return 2

    try:
        guard = (guard_factory or (lambda battery: PowerGuard(allow_battery=battery)))(
            args.allow_battery
        )
        gnani = (make_gnani or (lambda led: MeteredGnani(get_settings(), led, LEDGER_LABEL)))(
            ledger
        )
    except PowerError as exc:
        print(f"refused: {exc}", file=sys.stderr)
        return 2
    except ValidationError:
        print("refused: Gnani settings are missing (see .env.example)", file=sys.stderr)
        return 2

    async def go() -> dict[str, Any]:
        translator = (make_translator or (lambda: RoutingTranslator()))()
        pacing = limiter or SlidingWindowLimiter()
        try:
            return await run_study(files, args.src, args.tgt, gnani, translator, pacing, guard)
        finally:
            await gnani.aclose()

    try:
        result = asyncio.run(go())
    except (BudgetExceededError, PowerError) as exc:
        print(f"stopped: {exc}", file=sys.stderr)
        return 1
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(json.dumps(result["stages"].get("total_ms", {}), indent=2))
    print(f"clean samples {result['clean_samples']}/{TURNS}; wrote {args.out.as_posix()}")
    print(f"ledger {ledger.total}/{ledger.cap}")
    return 0 if result["clean_samples"] else 1
