"""Fact extraction on synthetic speech for ta, te, gu, ml, mr and pa (spends credits).

  run --dry-run   list the planned calls and the ledger total; sends nothing, needs no key
  run             TTS then STT for each sentence through the ledger; resumable
  report          score the saved transcripts with the fact extractor (no calls) and write
                  eval/results/facts_extra.json

Sentences: saathi.evaluation.extragold (synthetic, recombined lexicon words). The transcripts are
kept in eval/state/ (gitignored); they are synthetic number lists, not addresses.
"""

import argparse
import asyncio
import json
import sys
from pathlib import Path

from saathi.config import get_settings
from saathi.evaluation.calls import (
    BudgetExceededError,
    CallLedger,
    MeteredGnani,
    SlidingWindowLimiter,
)
from saathi.evaluation.extragold import (
    LEDGER_LABEL,
    MAX_CALLS,
    as_probe,
    gold_set,
    planned_calls,
)
from saathi.evaluation.factscore import score_transcript
from saathi.evaluation.lexprobe import ProbeBudgetError, run_probe
from saathi.gnani import GnaniError

ROOT = Path(__file__).resolve().parent.parent
LEDGER = ROOT / "eval" / "state" / "gnani_ledger.json"
TRANSCRIPTS = ROOT / "eval" / "state" / "facts_extra.json"
RESULTS = ROOT / "eval" / "results" / "facts_extra.json"


def run(dry_run: bool) -> int:
    gold = gold_set()
    ledger = CallLedger(LEDGER)
    calls = planned_calls(gold)
    for item in gold:
        print(f"  {item.id:8} TTS x1, STT x1  {item.text}")
    print(f"Calls: {calls} (max {MAX_CALLS}); ledger {ledger.total}/{ledger.cap} -> "
          f"{ledger.total + calls}")
    if calls > MAX_CALLS or ledger.total + calls > ledger.cap:
        print("REFUSED: over the call limit or the cap.")
        return 2
    if dry_run:
        print("Dry run: nothing was sent.")
        return 0
    gnani = MeteredGnani(get_settings(), ledger, LEDGER_LABEL)

    async def go() -> None:
        try:
            await run_probe(
                as_probe(gold), gnani, SlidingWindowLimiter(), TRANSCRIPTS, max_calls=MAX_CALLS
            )
        finally:
            await gnani.aclose()

    try:
        asyncio.run(go())
    except (BudgetExceededError, ProbeBudgetError) as exc:
        print(f"refused: {exc}", file=sys.stderr)
        return 2
    except GnaniError as exc:
        print(f"stopped by Gnani error {exc.status}; progress kept in {TRANSCRIPTS}; "
              f"ledger now {ledger.total}/{ledger.cap}", file=sys.stderr)
        return 1
    print(f"done; ledger now {ledger.total}/{ledger.cap}")
    return 0


def report() -> int:
    if not TRANSCRIPTS.exists():
        print("no transcripts yet; run first", file=sys.stderr)
        return 2
    heard: dict[str, str] = json.loads(TRANSCRIPTS.read_text("utf-8"))
    rows: dict[str, dict[str, int]] = {}
    misses: list[dict[str, object]] = []
    for item in gold_set():
        if item.id not in heard:
            continue
        result = score_transcript(item, heard[item.id])
        row = rows.setdefault(
            item.lang, {"sentences": 0, "all_correct": 0, "tp": 0, "fp": 0, "fn": 0}
        )
        overall = result.overall
        row["sentences"] += 1
        row["all_correct"] += result.all_correct
        row["tp"] += overall.tp
        row["fp"] += overall.fp
        row["fn"] += overall.fn
        if not result.all_correct:
            misses.append({"id": item.id, "sent": item.text, "heard": heard[item.id]})
    RESULTS.write_text(
        json.dumps({"by_language": rows, "misses": misses}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(f"{'lang':5} {'n':>3} {'all-right':>9} {'recall':>7} {'precision':>9}")
    for lang, row in rows.items():
        tp, fp, fn = row["tp"], row["fp"], row["fn"]
        recall = tp / (tp + fn) if tp + fn else float("nan")
        precision = tp / (tp + fp) if tp + fp else float("nan")
        print(f"{lang:5} {row['sentences']:>3} {row['all_correct']:>9} {recall:>7.2f} "
              f"{precision:>9.2f}")
    print(f"wrote {RESULTS}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    run_parser = sub.add_parser("run")
    run_parser.add_argument("--dry-run", action="store_true")
    sub.add_parser("report")
    args = parser.parse_args()
    return run(args.dry_run) if args.command == "run" else report()


if __name__ == "__main__":
    sys.exit(main())
