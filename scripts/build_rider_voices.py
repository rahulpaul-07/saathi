"""Give every guided-demo pair a stored rider voice (demo/bundle).

For each clip listed in demo/clips/manifest.json and every rider language other than the clip's own,
the bundle gets one turn: the translation (local IndicTrans2, greedy, made once), the facts as the
rider sees them, the verified flag and Gnani text-to-speech audio of exactly that text.

  --dry-run   print the calls planned, the ledger before and after and the turns added per rider
              language; sends nothing, loads no model, needs no key
  --run       translate and speak every pair that has no stored audio, through the call ledger
  --retry-failed  also retry pairs that failed on an earlier run (a failed call is never retried
                  within a run, and never silently on the next one)

At least 3.5 s between calls, one HTTP attempt per call, progress saved after every call, so a
stopped run resumes without paying for the same pair twice. Real runs spend credits: read the
--dry-run output first.
"""

import argparse
import asyncio
import sys
from pathlib import Path

from saathi.config import get_settings
from saathi.evaluation.calls import (
    GNANI_CALL_CAP,
    BudgetExceededError,
    CallLedger,
    SingleAttemptGnani,
)
from saathi.evaluation.rider_voices import (
    MIN_GAP_S,
    build_voices,
    load_progress,
    missing_pairs,
    new_turns_per_language,
    picker_pairs,
    turns_without_facts,
)
from saathi.translate import RoutingTranslator

ROOT = Path(__file__).resolve().parent.parent
LEDGER = ROOT / "eval" / "state" / "gnani_ledger.json"
LEDGER_LABEL = "rider-voices"
DEFAULT_BUDGET = 272  # the calls this build is expected to need
HARD_CAP = 290  # no run may spend more than this, whatever --budget says


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--dry-run", action="store_true")
    mode.add_argument("--run", action="store_true")
    parser.add_argument("--retry-failed", action="store_true")
    parser.add_argument("--budget", type=int, default=DEFAULT_BUDGET, help="most calls to plan")
    parser.add_argument("--clips-dir", type=Path, default=ROOT / "demo" / "clips")
    parser.add_argument("--out-dir", type=Path, default=ROOT / "demo" / "bundle")
    parser.add_argument("--ledger", type=Path, default=LEDGER)
    args = parser.parse_args()
    if not 1 <= args.budget <= HARD_CAP:
        print(f"--budget must be between 1 and {HARD_CAP}", file=sys.stderr)
        return 1

    pairs = picker_pairs(args.clips_dir, args.out_dir)
    missing = missing_pairs(pairs, args.out_dir)
    progress = load_progress(args.out_dir)
    held_back = [p for p in missing if p.key in progress.failures and not args.retry_failed]
    todo = [p for p in missing if p not in held_back]
    ledger = CallLedger(args.ledger)

    clips = len({p.clip_id for p in pairs})
    print(
        f"Picker clips: {clips}; pairs wanted: {len(pairs)}; "
        f"already stored: {len(pairs) - len(missing)}"
    )
    print("Turns to add per rider language:")
    for tgt, count in new_turns_per_language(todo).items():
        print(f"  {tgt}: {count}")
    print(
        f"Stored turns that still need their facts attached (local, no call): "
        f"{turns_without_facts(args.out_dir)}"
    )
    if held_back:
        print(f"Failed earlier and not retried (use --retry-failed): {len(held_back)}")
    print(
        f"Gnani text-to-speech calls planned: {len(todo)} "
        f"(budget {args.budget}, hard cap {HARD_CAP}); "
        f"ledger {ledger.total}/{ledger.cap} -> {ledger.total + len(todo)}; "
        f"gap between calls {MIN_GAP_S} s"
    )
    if len(todo) > args.budget or ledger.total + len(todo) > ledger.cap:
        print("REFUSED: over the call budget.")
        return 2
    if args.dry_run:
        print("Dry run: nothing was sent.")
        return 0

    # The run's own ceiling: it can never pass the hard cap, even if a bug asked for more calls.
    run_ledger = CallLedger(args.ledger, cap=min(GNANI_CALL_CAP, ledger.total + HARD_CAP))
    gnani = SingleAttemptGnani(get_settings(), run_ledger, LEDGER_LABEL, min_gap_s=MIN_GAP_S)
    translator = RoutingTranslator()
    translator.load()

    async def go() -> int:
        try:
            report = await build_voices(
                todo, args.out_dir, gnani, translator, retry_failed=args.retry_failed
            )
        finally:
            await gnani.aclose()
        print(
            f"stored {len(report.stored)}, failed {len(report.failed)}, "
            f"skipped {len(report.skipped)}, facts attached to {report.facts_added} older turns"
        )
        for key, reason in sorted(report.failed.items()):
            print(f"  failed {key}: {reason}")
        return 1 if report.failed else 0

    try:
        status = asyncio.run(go())
    except BudgetExceededError as exc:
        print(f"stopped: {exc}", file=sys.stderr)
        status = 2
    finally:
        spent = CallLedger(args.ledger)
        print(
            f"Real Gnani calls this run: {spent.total - ledger.total}; "
            f"ledger {spent.total}/{spent.cap}"
        )
    return status


if __name__ == "__main__":
    sys.exit(main())
