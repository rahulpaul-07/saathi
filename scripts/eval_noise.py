"""Noise evaluation of Gnani STT on the gold recordings (spends credits; replaces eval_turns.py).

  run --dry-run   print every planned call and the ledger total; sends nothing, needs no key
  run             mix noise, send each clip to Gnani STT through the ledger, save after each call
  report          fact precision/recall with bootstrap CIs from the saved results (no calls)

Recordings: eval/audio/gold/<gold id>.wav, 16 kHz mono 16-bit (gitignored, consented human
speech). Conditions: clean; street noise at 20, 10 and 5 dB SNR (primary; speech-active RMS over
noise RMS); pink noise at 10 dB (secondary). The street bed is a recorded WAV (--street-file,
default eval/audio/noise/street.wav, 16 kHz mono 16-bit, at least 30 s; make it with
scripts/convert_recording.py --street). Pink noise is seeded and synthetic. Street and pink are
reported separately. Rerunning resumes: finished clips are not sent again. Real runs only while the
author is awake, after reviewing --dry-run.
"""

import argparse
import asyncio
import logging
import sys
from pathlib import Path

from saathi.config import get_settings
from saathi.evaluation import noisemix
from saathi.evaluation.calls import (
    BudgetExceededError,
    CallLedger,
    MeteredGnani,
    SlidingWindowLimiter,
)
from saathi.evaluation.factscore import load_gold, select
from saathi.evaluation.noiseeval import (
    BOOTSTRAP_RESAMPLES,
    CONDITIONS,
    LEDGER_LABEL,
    REPORT_SETS,
    check_budget,
    format_plan,
    format_summary,
    load_results,
    plan_calls,
    prepare_clips,
    run_calls,
    save_results,
    summarize,
)
from saathi.evaluation.runinfo import git_commit
from saathi.evaluation.wavtools import RecordingError
from saathi.gnani import GnaniError

ROOT = Path(__file__).resolve().parent.parent
GOLD = ROOT / "eval" / "gold" / "directions.json"
AUDIO_DIR = ROOT / "eval" / "audio" / "gold"
RESULTS = ROOT / "eval" / "results" / "noise_stt.json"
SUMMARY = ROOT / "eval" / "results" / "noise_summary.md"
LEDGER = ROOT / "eval" / "state" / "gnani_ledger.json"
STREET = ROOT / "eval" / "audio" / "noise" / "street.wav"
DEFAULT_SEED = 20261029


def _meta(args: argparse.Namespace) -> dict[str, object]:
    return {
        "seed": args.seed,
        "noise": {
            "street": args.street_file.name,
            "pink": "seeded synthetic 1/f noise (not a recording of any place)",
        },
        "snr_definition": "speech-active RMS / whole-clip noise RMS",
        "activity": {
            "frame_s": noisemix.FRAME_S,
            "relative_db": noisemix.ACTIVE_RELATIVE_DB,
            "floor_dbfs": noisemix.ACTIVE_FLOOR_DBFS,
            "percentile": noisemix.LOUD_PERCENTILE,
        },
        "bootstrap_resamples": BOOTSTRAP_RESAMPLES,
        "git_commit": git_commit(),
    }


def cmd_run(args: argparse.Namespace) -> int:
    gold = load_gold(args.gold)
    calls = plan_calls(gold, args.audio_dir, CONDITIONS)
    results = load_results(args.results)
    ledger = CallLedger(args.ledger)
    street_wav = args.street_file.read_bytes() if args.street_file.is_file() else None
    street_note = (
        f"Street noise: {args.street_file.as_posix()} [{'found' if street_wav else 'MISSING'}]"
    )
    clips, problems = prepare_clips(calls, args.seed, street_wav)
    done = {c.key for c in calls if c.key in results}
    pending = [c for c in calls if c.key not in done]
    if args.dry_run:
        print(format_plan(calls, done, ledger, problems, street_note))
        try:
            check_budget(ledger, len(pending))
        except BudgetExceededError as exc:
            print(f"REFUSED: {exc}")
            return 2
        print("Dry run: nothing was sent.")
        return 0

    not_ready = [c.key for c in pending if c.key not in clips]
    if problems or not_ready:
        print(format_plan(calls, done, ledger, problems, street_note))
        print("Nothing was sent: fix the recordings above first.")
        return 1
    meta = _meta(args)
    gnani = MeteredGnani(get_settings(), ledger, LEDGER_LABEL)

    async def go() -> None:
        try:
            await run_calls(
                calls,
                clips,
                gnani,
                SlidingWindowLimiter(),
                ledger,
                results,
                lambda rows: save_results(args.results, meta, rows),
            )
        finally:
            await gnani.aclose()

    try:
        asyncio.run(go())
    except (BudgetExceededError, RecordingError) as exc:
        print(f"refused: {exc}", file=sys.stderr)
        return 2
    except GnaniError as exc:
        print(f"stopped by Gnani error {exc.status}; finished clips are saved", file=sys.stderr)
        return 1
    print(f"done; ledger {ledger.total}/{ledger.cap}")
    return cmd_report(args)


def cmd_report(args: argparse.Namespace) -> int:
    results = load_results(args.results)
    if not results:
        print("no results yet")
        return 1
    gold = load_gold(args.gold)
    parts = [
        f"# Noise evaluation (generated by scripts/eval_noise.py report)\n\nSeed {args.seed}.\n"
    ]
    for split in ("test", "dev"):
        for noise_label, conditions in REPORT_SETS:
            summaries = summarize(select(gold, split), results, conditions, args.seed)
            if summaries:
                parts.append(format_summary(f"{split} split, {noise_label}", summaries) + "\n")
    text = "\n".join(parts)
    print(text)
    args.summary.parent.mkdir(parents=True, exist_ok=True)
    args.summary.write_text(text, encoding="utf-8")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawTextHelpFormatter
    )
    parser.add_argument("command", choices=["run", "report"])
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--gold", type=Path, default=GOLD)
    parser.add_argument("--audio-dir", type=Path, default=AUDIO_DIR)
    parser.add_argument(
        "--street-file", type=Path, default=STREET, help="16 kHz mono 16-bit WAV, >= 30 s"
    )
    parser.add_argument("--seed", type=int, default=DEFAULT_SEED)
    parser.add_argument("--results", type=Path, default=RESULTS)
    parser.add_argument("--summary", type=Path, default=SUMMARY)
    parser.add_argument("--ledger", type=Path, default=LEDGER)
    args = parser.parse_args()
    if args.dry_run and args.command != "run":
        parser.error("--dry-run applies to `run`")
    logging.basicConfig(level=logging.WARNING)
    try:
        return cmd_run(args) if args.command == "run" else cmd_report(args)
    except (OSError, noisemix.NoiseMixError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
