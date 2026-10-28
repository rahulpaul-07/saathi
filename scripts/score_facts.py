"""Score the fact extractor on the synthetic gold set, text only (no Gnani calls, no network).

  uv run --no-sync python scripts/score_facts.py --split dev --errors   tune on dev
  uv run --no-sync python scripts/score_facts.py --split test           report; no error detail

The test split is frozen: its error details are refused so it cannot be tuned against by accident.
"""

import argparse
import sys
from pathlib import Path

from saathi.evaluation.factscore import KindScore, Report, Split, load_gold, score, select

DEFAULT_GOLD = Path(__file__).resolve().parent.parent / "eval" / "gold" / "directions.json"


def _pct(value: float | None) -> str:
    return "n/a" if value is None else f"{value:.2f}"


def _row(name: str, item: KindScore) -> str:
    return (
        f"{name:<9} P={_pct(item.precision):>4} R={_pct(item.recall):>4} "
        f"tp={item.tp:<3} fp={item.fp:<3} fn={item.fn:<3} "
        f"ambiguous={item.ambiguous} (reading right: {item.ambiguous_reading_correct})"
    )


def _print_report(report: Report, split: str) -> None:
    print(f"split={split} utterances={report.utterances} all-facts-right={report.all_correct}")
    for kind, item in sorted(report.by_kind.items()):
        print(_row(kind, item))
    print(_row("overall", report.overall))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0] if __doc__ else None)
    parser.add_argument("--split", choices=["dev", "test", "all"], default="dev")
    parser.add_argument("--gold", type=Path, default=DEFAULT_GOLD)
    parser.add_argument("--errors", action="store_true", help="print misses (dev split only)")
    args = parser.parse_args()
    split: Split = args.split
    if args.errors and split != "dev":
        print("--errors is only allowed with --split dev (test is frozen)", file=sys.stderr)
        return 2

    report, misses = score(select(load_gold(args.gold), split))
    _print_report(report, split)
    if args.errors:
        for miss in misses:
            print(f"\n{miss.utterance.id} [{miss.utterance.lang}] {miss.utterance.text}")
            for fact in miss.wrong:
                print(f"  wrong   {fact.kind}={fact.value!r} ({fact.confidence})")
            for gold in miss.missed:
                print(f"  missed  {gold.kind}={gold.value!r}")
            for fact in miss.ambiguous:
                print(f"  ambiguous {fact.kind}: heard {fact.value!r}, reading {fact.reading}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
