"""Add Gnani calls made by the live demo server to the evaluation ledger, by hand.

The server uses the plain client, so its calls (one STT and one TTS per clip turn, one TTS per
quick reply not already cached) never reach the ledger. After a recording session, count them
(docs/DEMO_SCRIPT.md, "Calls and the ledger") and run:

  uv run --no-sync python scripts/log_demo_calls.py 10            # label demo-live
  uv run --no-sync python scripts/log_demo_calls.py 10 --label demo-rehearsal

Refuses a count that would pass the cap, like every other ledger write.
"""

import argparse
import sys
from pathlib import Path

from saathi.evaluation.calls import BudgetExceededError, CallLedger

DEFAULT_LEDGER = Path(__file__).resolve().parent.parent / "eval" / "state" / "gnani_ledger.json"
MAX_PER_RUN = 100  # a typo guard: a recording session is tens of calls, not hundreds


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("calls", type=int, help="number of Gnani calls the server made")
    parser.add_argument("--label", default="demo-live")
    parser.add_argument("--ledger", type=Path, default=DEFAULT_LEDGER)
    args = parser.parse_args()
    if not 1 <= args.calls <= MAX_PER_RUN:
        print(f"calls must be between 1 and {MAX_PER_RUN}", file=sys.stderr)
        return 2
    ledger = CallLedger(args.ledger)
    try:
        ledger.spend(args.label, args.calls)
    except BudgetExceededError as exc:
        print(f"refused: {exc}", file=sys.stderr)
        return 2
    print(f"logged {args.calls} as {args.label}; ledger now {ledger.total}/{ledger.cap}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
