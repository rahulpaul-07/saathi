"""One real turn, example pair kn -> bn: exactly 3 Gnani calls (TTS kn, STT kn, TTS bn).

Spends credits.

The pair is just an evaluation fixture, not a statement about who speaks what.

  uv run --no-sync python scripts/live_turn.py --dry-run  print the plan and ledger; sends nothing
  uv run --no-sync python scripts/live_turn.py --yes      really run it (only while author is awake)

The sentence is a synthetic gold one (default g02). The Bengali audio is saved to eval/audio/live/
(gitignored) to listen to. No transcript or translation text is ever printed. Logic and tests live
in saathi.evaluation.liveturn.
"""

import sys
from pathlib import Path

from saathi.evaluation.liveturn import main

if __name__ == "__main__":
    sys.exit(main(root=Path(__file__).resolve().parent.parent))
